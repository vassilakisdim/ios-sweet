# Bonito port handoff

## Current state — 2026-11-15

- Local fork branch: `port/bonito-bringup`, based on the user's fork commit `a563d834b366cafbb3dd912ce4b45c68b9a12480`; that fork is two commits ahead of upstream and includes the SDM670 shim/DTB work.
- The Bonito shim image and experimental ADT were built successfully by shim CI run `43724648790`; no XNU kernel/payload or iOS root image exists yet.
- Re-authenticated GitHub CLI is available. The first shim CI run `43717125955` failed because Ubuntu's `mkbootimg` wrapper could not import `gki`. The fix and Bonito artifacts workflow are published on `port/bonito-bringup`.
- The first image (`95c4bc85557808900d70b46554a84566dbe51d483a6ca344c8e6bf2f05b75afe`) passed local header parsing, but `fastboot boot` was rejected by ABL with `Unsupported`. No partition was written; the device is currently in the bootloader. The header's `os_version` was Android 17 with no patch level; a local follow-up sets Android 12 / May 2022 metadata and passed the packer smoke check (`0x18000165`). The corrected image has not yet been rebuilt in CI or tried on-device.
- Device observed over ADB as Google Pixel 3a XL (`bonito`), Android 12 `SP2A.220505.008`, active slot `_a`, bootloader unlocked.
- Verified the reversible bootloader path: fastboot reports `product=bonito`, unlocked `yes`, slot `a`; `fastboot reboot` returned the phone to Android and ADB detected it again.
- The handset reports `dtb_idx=0` / `dtbo_idx=8`. Official TWRP 3.7.1_12-1 SHA-256 `e0781b592354a87ef8369cce36a0ed61e5bd751058d0eadf68c632c3568678d0` matched TeamWin's checksum; `fastboot boot` returned `OKAY` and recovery ADB ran as root for the FDT and `/proc/iomem` read.
- Live data identifies two physical RAM banks and their reserved holes, the Samsung `sofef00` command-mode panel, and an enabled eMMC SDHCI controller at `0x7c4000`. TWRP DRM reports 1080×2160 `XB24` buffers with 4352-byte pitch, but these are separate from the boot splash buffer. See `PORTING.md` for details.
- Recovery returned to Android with `adb reboot`; ADB confirmed the same Android 12 build and active slot. TWRP auto-mounted `/data` and `/metadata` read-write; no partition was flashed or erased, but incidental recovery writes cannot be ruled out.
- Initial hardware inventory and implementation sequence are in [`PORTING.md`](PORTING.md); structured observations are in [`device.json`](../../targets/bonito/device.json).
- The host has ADB/Git, no WSL distribution, and no AArch64 toolchain on `PATH`; GitHub Actions is the cross-build path. The XNU workflow is macOS-based.
- Main engineering blockers: a Bonito XNU platform target and memory-safe ADT, framebuffer handoff details, eMMC/SDHCI support, and Bonito input/display drivers. Sweet's current UFS root path is incompatible with Bonito's `/dev/block/mmcblk0`.
- `tools/mkadt.py --bonito` is now an experimental ADT staging profile. It emitted an 8,340-byte ADT; structure inspection confirmed RAM `0xa2000000–0x17e2c0000`, the 36 MiB splash reservation, 1080 × 2160 geometry, and cluster IDs 0 for CPUs 0–5 / 1 for CPUs 6–7. It omits UFS. The 4320-byte ABL splash stride remains an explicit unverified candidate; TWRP's 4352-byte recovery pitch describes other buffers.
- Local checks passed: the pinned AOSP packer plus repository unpacker round-tripped a dummy boot-header-v2 image, the Bonito ADT assertions passed, and `tools/validate-repo.py` validated all 81 patch files, 16 Python scripts, and 7 shell scripts. These checks do not replace the pending real shim CI build or device boot.

## Next concrete action

Commit and publish the corrected Android 12 boot-header metadata, rerun shim CI, inspect the rebuilt image, and retry `fastboot boot`. Keep eMMC and user partitions read-only; do not flash partitions until the XNU target, console, eMMC read path, and restore procedure are verified.
