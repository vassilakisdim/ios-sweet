#!/usr/bin/env python3
import hashlib, struct, sys

kernel_path, ramdisk_path, dtb_path, out_path = sys.argv[1:5]
kernel = open(kernel_path, "rb").read()
ramdisk = open(ramdisk_path, "rb").read()
dtb = open(dtb_path, "rb").read()

PAGE = 4096
def pad(b):
    rem = len(b) % PAGE
    return b + (b"\x00" * (PAGE - rem) if rem else b"")

cmdline = b"console=null"
sha = hashlib.sha1()
for blob in (kernel, ramdisk, b"", dtb):
    sha.update(blob)
    sha.update(struct.pack("<I", len(blob)))
img_id = sha.digest().ljust(32, b"\x00")

hdr = struct.pack(
    "<8s10I16s512s32s1024sIQI4s",
    b"ANDROID!",
    len(kernel), 0x00008000,
    len(ramdisk), 0x01000000,
    0, 0x00f00000,
    0x00000100, PAGE, 2, 0x18000165,
    b"\x00" * 16,
    cmdline.ljust(512, b"\x00"),
    img_id,
    b"\x00" * 1024,
    0, 0, 1660,
    struct.pack("<I", len(dtb))
) + struct.pack("<Q", 0x01f00000)

with open(out_path, "wb") as f:
    f.write(pad(hdr) + pad(kernel) + pad(ramdisk) + pad(dtb))
print(f"Packed {out_path} ({f.tell()} bytes)")
