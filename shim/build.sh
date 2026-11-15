#!/bin/bash
# Build the shim and wrap it in a boot.img v2 that mirrors the stock PixelOS header.
set -euo pipefail
cd "$(dirname "$0")"
CC=aarch64-linux-gnu-gcc
OBJCOPY=aarch64-linux-gnu-objcopy
CFLAGS="-O2 -ffreestanding -nostdlib -fno-pic -mgeneral-regs-only -mstrict-align -fno-stack-protector -Wall -Wextra"
mkdir -p out
for f in start.S shim.c console.c mmu.c fdt.c loader.c ufs.c; do
	$CC $CFLAGS -c $f -o out/${f%.*}.o
done
# The image runs wherever ABL puts it with no relocation pass: only the
# header's image_size field may be an absolute address.
abs=$(aarch64-linux-gnu-readelf -r out/shim.o out/console.o out/mmu.o out/fdt.o out/loader.o out/ufs.o | grep -c ABS64 || true)
[ "$abs" = 0 ] || { echo "error: $abs absolute relocations in C objects" >&2; exit 1; }
$CC $CFLAGS -static -T shim.ld -Wl,--build-id=none -Wl,--no-warn-rwx-segments -Wl,-N \
	out/start.o out/shim.o out/console.o out/mmu.o out/fdt.o out/loader.o out/ufs.o -o out/shim.elf
$OBJCOPY -O binary out/shim.elf out/Image
# The Pixel 3a ABL expects the same ARM64 Image layout as its stock kernel.
# Keep the file's expanded LZ4 length at the accepted TWRP kernel length;
# image_size in start.S reserves the larger kernel/BSS footprint.
size=$(aarch64-linux-gnu-nm out/shim.elf | awk '$3=="_end"{print strtonum("0x"$1)}')
truncate -s "$size" out/Image
# TWRP's decompressed Image.lz4-dtb is 51,591,192 bytes on this Bonito build.
kernel_file_size=51591192
[ "$size" -le "$kernel_file_size" ] || { echo "error: shim Image exceeds Bonito LZ4 size" >&2; exit 1; }
truncate -s "$kernel_file_size" out/Image
# Match the accepted LZ4 frame: independent 4 MiB blocks and frame checksum.
lz4 -f -q -B7 -BI --frame-crc out/Image out/Image.lz4
lz4 -tq out/Image.lz4
python3 -c 'from pathlib import Path; assert Path("out/Image.lz4").read_bytes()[:7] == bytes.fromhex("04224d186470b9")'
# Ramdisk: an xnu payload (tools/mkpayload.py) if given as $1, else an empty
# newc cpio (ABL dislikes a zero-size ramdisk on some builds) -> diagnostics.
if [ -n "${1:-}" ]; then
	cp "$1" out/ramdisk.bin
else
	(cd out && rm -rf rd && mkdir rd && cd rd && find . | cpio -o -H newc --quiet | gzip -9 > ../ramdisk.bin)
fi
mkbootimg --header_version 2 --kernel out/Image.lz4 --ramdisk out/ramdisk.bin \
	--dtb sdm670.dtb --base 0 --kernel_offset 0x8000 --ramdisk_offset 0x1000000 \
	--tags_offset 0x100 --dtb_offset 0x1f00000 --pagesize 4096 \
	--os_version 99.87.36 --os_patch_level 2099-12-31 \
	--cmdline "console=ttyMSM0,115200n8 androidboot.console=ttyMSM0 printk.devkmsg=on msm_rtb.filter=0x237 ehci-hcd.park=3 service_locator.enable=1 firmware_class.path=/vendor/firmware cgroup.memory=nokmem lpm_levels.sleep_disabled=1 loop.max_part=7 androidboot.boot_devices=soc/7c4000.sdhci twrpfastboot=1 androidboot.super_partition=system buildvariant=eng" \
	-o out/shim-boot.img
# Host render of the console layout.
# host_test skipped for 1080x2160 bonito panel
ls -l out/Image out/Image.lz4 out/shim-boot.img
