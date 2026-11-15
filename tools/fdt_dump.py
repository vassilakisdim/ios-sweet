#!/usr/bin/env python3
"""Print useful nodes from a flattened device tree (FDT) using only stdlib."""

import argparse
import struct
import sys

FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9
DT_TABLE_MAGIC = 0xD7B7AB1E
SENSITIVE_PROPERTIES = {
    "serial", "serial-number", "serialnumber", "device-serial",
    "qcom,serial-num", "qcom,serial-number", "imei", "cid", "mmc-cid",
}
SENSITIVE_CMDLINE_KEYS = {
    "androidboot.serialno", "androidboot.cid", "androidboot.vbmeta.digest",
    "androidboot.vbmeta.device",
}

DEFAULT_MATCHES = (
    "memory", "reserved", "/cpus", "timer", "interrupt-controller", "gic",
    "sdhci", "ufshc", "synaptics", "touch", "display", "dsi", "panel",
    "framebuffer", "fb", "splash", "geni", "i2c", "gpio", "tlmm",
    "rpmh", "spmi", "pmic", "psci", "cma",
)


def align4(offset):
    return (offset + 3) & ~3


def cstring(data, offset, limit):
    end = data.find(b"\0", offset, limit)
    if end < 0:
        raise ValueError("unterminated FDT string")
    return data[offset:end].decode("utf-8", "replace"), end + 1


def format_value(value):
    if not value:
        return "<empty>"

    if value.endswith(b"\0"):
        strings = value[:-1].split(b"\0")
        if strings and all(
            item and all(byte == 9 or 32 <= byte < 127 for byte in item)
            for item in strings
        ):
            return " | ".join(repr(item.decode("utf-8", "replace")) for item in strings)

    if len(value) % 4 == 0 and len(value) <= 128:
        cells = struct.unpack(">" + "I" * (len(value) // 4), value)
        return "<" + " ".join(f"0x{cell:x}" for cell in cells) + ">"
    return "0x" + value.hex()


def format_property(name, value):
    """Format an FDT property while redacting common device identifiers."""
    normalized_name = name.lower().replace("_", "-")
    if normalized_name in SENSITIVE_PROPERTIES:
        return "<redacted>"

    if normalized_name in {"bootargs", "linux,cmdline"} and value.endswith(b"\0"):
        try:
            text = value[:-1].decode("ascii")
        except UnicodeDecodeError:
            return format_value(value)
        tokens = []
        for token in text.split():
            key, separator, _item = token.partition("=")
            if separator and key.lower() in SENSITIVE_CMDLINE_KEYS:
                token = key + "=<redacted>"
            tokens.append(token)
        return repr(" ".join(tokens))

    return format_value(value)


def parse_fdt(data):
    if len(data) < 40:
        raise ValueError("file is shorter than an FDT header")

    (magic, total_size, struct_offset, strings_offset, _reserve_offset,
     version, _last_compatible, _boot_cpuid, strings_size,
     struct_size) = struct.unpack_from(">10I", data)
    if magic != FDT_MAGIC:
        raise ValueError(f"unexpected FDT magic 0x{magic:08x}")
    if total_size > len(data) or total_size < 40:
        raise ValueError("FDT totalsize is outside the input file")
    struct_end = struct_offset + struct_size
    strings_end = strings_offset + strings_size
    if struct_offset < 40 or struct_end > total_size or strings_end > total_size:
        raise ValueError("FDT structure or strings table is outside totalsize")

    strings = data[strings_offset:strings_end]
    pos = struct_offset
    stack = []
    nodes = []
    current = None

    while pos + 4 <= struct_end:
        token = struct.unpack_from(">I", data, pos)[0]
        pos += 4
        if token == FDT_BEGIN_NODE:
            name, pos = cstring(data, pos, struct_end)
            pos = align4(pos)
            stack.append(name)
            path = "/" + "/".join(part for part in stack if part)
            current = {"path": path or "/", "properties": []}
            nodes.append(current)
        elif token == FDT_END_NODE:
            if not stack:
                raise ValueError("unbalanced FDT_END_NODE")
            stack.pop()
            current = None
        elif token == FDT_PROP:
            if current is None or pos + 8 > struct_end:
                raise ValueError("property outside node or truncated property header")
            length, name_offset = struct.unpack_from(">II", data, pos)
            pos += 8
            if name_offset >= len(strings) or pos + length > struct_end:
                raise ValueError("property name or value is outside its table")
            name, _ = cstring(strings, name_offset, len(strings))
            value = data[pos:pos + length]
            current["properties"].append((name, value))
            pos = align4(pos + length)
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            if stack:
                raise ValueError("FDT ended with unclosed nodes")
            return nodes, version, total_size
        else:
            raise ValueError(f"unknown FDT token 0x{token:08x} at offset 0x{pos - 4:x}")

    raise ValueError("FDT structure has no FDT_END token")


def select_dtbo_entry(data, index):
    if len(data) < 32:
        raise ValueError("file is shorter than a DTBO table header")
    (magic, total_size, header_size, entry_size, entry_count,
     entries_offset, _page_size, version) = struct.unpack_from(">8I", data)
    if magic != DT_TABLE_MAGIC:
        raise ValueError(f"unexpected DTBO table magic 0x{magic:08x}")
    if total_size > len(data) or header_size < 32 or entry_size < 32:
        raise ValueError("invalid DTBO table sizes")
    if index < 0 or index >= entry_count:
        raise ValueError(f"DTBO index {index} is outside 0..{entry_count - 1}")

    entry_offset = entries_offset + index * entry_size
    if entry_offset + 32 > total_size:
        raise ValueError("DTBO entry table is outside totalsize")
    dt_size, dt_offset, entry_id, revision, *custom = struct.unpack_from(
        ">8I", data, entry_offset
    )
    if dt_offset + dt_size > total_size:
        raise ValueError("selected DTBO entry is outside totalsize")
    metadata = {
        "index": index,
        "entry_count": entry_count,
        "id": entry_id,
        "revision": revision,
        "custom": custom,
        "dt_size": dt_size,
        "dt_offset": dt_offset,
        "table_version": version,
    }
    return data[dt_offset:dt_offset + dt_size], metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fdt", help="input .dtb or extracted DTBO entry")
    parser.add_argument("--all", action="store_true", help="show every node")
    parser.add_argument(
        "--dtbo-index", type=int,
        help="extract this zero-based entry from an Android dtbo.img before parsing",
    )
    parser.add_argument(
        "--match", action="append", default=[],
        help="show nodes whose path contains this case-insensitive string (repeatable)",
    )
    args = parser.parse_args()

    try:
        with open(args.fdt, "rb") as source:
            image = source.read()
        if args.dtbo_index is not None:
            image, entry = select_dtbo_entry(image, args.dtbo_index)
            print(
                f"DTBO entry {entry['index']}/{entry['entry_count'] - 1}: "
                f"id=0x{entry['id']:x} rev=0x{entry['revision']:x} "
                f"custom={','.join(f'0x{x:x}' for x in entry['custom'])} "
                f"size={entry['dt_size']} offset=0x{entry['dt_offset']:x}"
            )
        nodes, version, total_size = parse_fdt(image)
    except (OSError, ValueError, struct.error) as exc:
        parser.error(str(exc))

    matches = tuple(item.lower() for item in args.match) or DEFAULT_MATCHES
    print(f"FDT v{version}; {total_size} bytes; {len(nodes)} nodes")
    for node in nodes:
        if not args.all and not any(word in node["path"].lower() for word in matches):
            continue
        print(f"\n{node['path']}")
        for name, value in node["properties"]:
            print(f"  {name}: {format_property(name, value)}")


if __name__ == "__main__":
    main()
