# Bonito port: inventory and bring-up plan

**Date:** 2026-11-15

**Target:** Google Pixel 3a XL (`bonito`)

**Current state (2026-11-15):** the fork contains Bonito shim source and a Bonito hardware inventory; no iOS kernel or XNU payload has been built or booted. Shim CI run `43724648790` built the first image and experimental ADT after replacing Ubuntu's broken `mkbootimg` wrapper. Initial and Android-12-metadata variants were rejected by ABL. A local diagnostic image then returned `Booting OKAY` after its ARM64 kernel header and LZ4 frame were matched to the accepted TWRP image; it still used TWRP's ramdisk and DTB. The handset exposed neither ADB nor fastboot immediately after that handoff, and the screen state is awaiting user observation. No partition was flashed or erased.

## Goal and base

This is intended to run the real iOS 16-generation XNU kernel and iPhone X iOS 16 userland, following the `ios-sweet` design. It is not an iOS-style Android launcher. Apple's userland firmware is not included in the repository; the user must obtain it from Apple when the build reaches that stage.

The reference project targets the Redmi Note 10 Pro (`sweet`, Snapdragon 732G / SM7150), whose port has an XNU shim, software framebuffer, touch and button drivers, and a UFS-backed HFS+ system volume. The HackiOS compatibility guide classifies Snapdragon 670 as a possible older-Snapdragon target and calls out older cores and a different power-controller generation as extra work. It recommends starting from the nearest device port, but the 670 is not a drop-in 732G target. Sources: [`ios-sweet`](https://github.com/dipa-studio/ios-sweet), [compatibility guide](https://hackiosx.dev/compatibility), and [porting guide](https://hackiosx.dev/porting).

## Observed device state

Collected through read-only ADB queries and a temporary root recovery shell on the connected handset:

| Item | Observation |
| --- | --- |
| Product / model | `bonito` / Pixel 3a XL; SKU `G020A` |
| Android | 12, build `SP2A.220505.008`, patch `2022-05-05` |
| Bootloader | `ro.boot.vbmeta.device_state=unlocked`, `ro.boot.flash.locked=0` |
| Active slot | `_a` |
| Device-tree selectors | `ro.boot.dtb_idx=0`, `ro.boot.dtbo_idx=8` |
| SoC | `sdm670` (`ro.boot.hardware`); Google identifies the Pixel 3a XL as Snapdragon 670 |
| Memory visible to Android | `MemTotal=3,678,616 kB` in `/proc/meminfo` |
| Physical memory description | Live recovery FDT has banks `0x80000000–0xffffffff` and `0x100000000–0x17e2bffff`; `/proc/iomem` divides usable System RAM around reserved regions (details below) |
| Display | 1080 × 2160 physical size (`wm size`) |
| Touch | `synaptics_dsx`, raw axes 0–1079 × 0–2159 |
| Buttons | `gpio-keys` and `qpnp_pon` input devices |
| Internal storage | eMMC at `/dev/block/mmcblk0`; `userdata` is `/dev/block/mmcblk0p72`; live `sdhci@7c4000` status is `ok` |
| Data free space | about 46 GiB reported by `df -h /data` |
| ADB access | online; shell is unprivileged |

Google's Pixel specifications list 4 GB RAM and 64 GB storage. Android's unprivileged shell cannot read the live FDT or `/proc/iomem`, so I used the official [Pixel 3a XL TWRP image](https://dl.twrp.me/bonito/) through `fastboot boot` (temporary boot only). Its SHA-256 matched TeamWin's published checksum. The recovery FDT reported the same `dtb_idx=0` / `dtbo_idx=8` selection as Android. I read `/sys/firmware/fdt` and `/proc/iomem` without intentionally mounting or writing user data. TWRP automatically mounted `/data` and `/metadata` read-write, so incidental recovery writes cannot be ruled out; I did not flash or erase any partition. After `adb reboot`, the same Android build and slot returned. Raw captures stay ignored under `research/` because the FDT boot arguments contain device identifiers. Google's public artifacts remain useful for comparison, but the live recovery FDT is the primary hardware record here. See the [Google Pixel specifications](https://support.google.com/pixelphone/answer/16043605?hl=en) and [Google's Bonito kernel artifacts](https://android.googlesource.com/device/google/bonito-kernel/+/refs/heads/main/).

The normalized device profile and summarized live-tree facts are in [`targets/bonito/device.json`](../../targets/bonito/device.json). Device serials and raw partition contents are intentionally omitted.

### Live device-tree pass

The official [Pixel 3a XL TWRP image](https://dl.twrp.me/bonito/) was checksum-verified and booted temporarily with `fastboot boot`. Its recovery FDT is version 17, 450,375 bytes, and has 2,588 nodes. It reports `dtb_idx=0` / `dtbo_idx=8`, matching Android. Its boot arguments select `dsi_sofef00_sdc_1080p_cmd_display::timing0`, identifying the active Samsung `sofef00` 1080p command-mode panel. The tree includes the panel initialization sequence and eMMC controller description. Google's nearby public artifact, commit `ee16fca33c644a4d1b7059b627786968406217bd` (May 3, 2022; merge of `SP2A.220505.002`), remains a comparison point; the phone reports `SP2A.220505.008`.

## Boot image acceptance diagnosis

The first CI shim image used an uncompressed ARM64 Image and malformed Android 17 OS metadata. ABL rejected it with `Unsupported`. Correcting the metadata, adding an unsigned AVB footer, and using TWRP's ramdisk and DTB did not resolve the rejection while the shim kernel remained uncompressed.

The checksum-verified TWRP image uses an Android boot header v2 and an LZ4 frame beginning `04 22 4d 18 64 70 b9`. Decompressing its kernel produced a 51,591,192-byte Image with `text_offset=0x80000`, `image_size=0x3a84000`, and ARM64 flags `0xa`. The accepted diagnostic was built from the shim kernel padded to that expanded length, compressed with independent 4 MiB LZ4 blocks and a frame checksum, and packaged with TWRP's ramdisk, DTB, command line, AVB properties, and 51,810,304-byte pre-footer payload length. `fastboot boot` returned `Sending OKAY` and `Booting OKAY`; image SHA-256: `1e983adf8d4458f45ed01cdb34517708297b855b18d4795debe8aa7677f61cc3`.

This confirms ABL accepted and handed off a diagnostic image. It does not confirm shim execution, graphics output, XNU entry, or iOS startup. After the command, both ADB and fastboot device listings were empty, so the phone's screen state and return-to-bootloader path still need confirmation. No partition was written. The local source/build workflow is being updated to reproduce the observed Pixel LZ4/header/AVB profile. Google's ARM64 kernel build includes `Image.lz4-dtb` ([AOSP kernel Makefile](https://android.googlesource.com/kernel/msm/+/accb124b66e0dec5ec9444dcd5612ba7a52d1f3c/arch/arm64/Makefile)); LZ4 documents the independent block, block-size, and frame-checksum options used in the reproduction ([LZ4 CLI manual](https://github.com/lz4/lz4/blob/dev/programs/lz4.1.md)).

I added [`tools/fdt_dump.py`](../../tools/fdt_dump.py), a small standard-library parser for FDT blobs and Android DTBO table entries. Its text output redacts common serial, storage-CID, and verified-boot identifiers; raw device captures remain ignored. Running it on the live FDT found:

- `/memory` describes two banks: `0x80000000–0xffffffff` and `0x100000000–0x17e2bffff` (inclusive). `/proc/iomem` reports System RAM segments at `0x80000000–0x856fffff`, `0x85d00000–0x85dfffff`, `0x85f00000–0x85fbffff`, `0x88f00000–0x8aafffff`, `0x97a17000–0x9e3fffff`, `0x9f800000–0xa17fffff`, and `0xa1c11000–0x17e2bffff`. Secure, modem, DSP, GPU, splash, and ramoops areas occupy reserved ranges and holes; the XNU memory map must preserve those boundaries. A candidate initial contiguous XNU range is `0xa2000000` to exclusive end `0x17e2c0000` (32 MiB aligned, `0xdc2c0000` bytes). It lies within the final System RAM segment, but remains unvalidated by a built XNU target.
- The tree describes eight PSCI-started CPUs. CPU-map clusters contain nodes 0–5 and 6–7; MPIDR `reg` values are `0x0` through `0x700` in `0x100` steps. PSCI uses SMC. GICv3 distributor/redistributor are at `0x17a00000` and `0x17a60000`; the generic timer clock is 19.2 MHz.
- `sdhci@7c4000` is enabled (`status="ok"`), 8-bit, and matches Android's eMMC block device; the tree lists HS400/HS200/DDR at 1.8 V. This resolves the public-base-tree disabled-state mismatch, but XNU still needs a Bonito eMMC/SDHCI driver and a verified controller handoff/init path.
- The active `sofef00` panel runs 1080 × 2160 at 60 Hz in DSI command mode, 24 bpp with RGB-swap ordering. The tree also contains Samsung `s6e3fa7` and Tianma `nt37700f` variants, but they are not selected by this handset's active display argument. `cont_splash_region` reserves `0x9c000000–0x9e3fffff` (36 MiB).
- TWRP's active DRM debug state reports 1080 × 2160 `XB24` framebuffers with pitch 4352 bytes. Its two active buffer objects are outside `cont_splash_region`; this confirms the recovery's DRM buffer format/stride, not the bootloader splash buffer's format/stride. XNU must not assume the splash layout from this observation.
- The Synaptics DSX controller is on I²C at `0xa84000`, address `0x20`; its SoC GPIO IDs are IRQ `0x7d`, reset `0x63`, and switch `0x87`. Reset delay is 20 ms and active reset time is 1 ms. The wiring is known; XNU still needs the I²C/GENI driver, power sequencing, and event glue.

Generated DTB/DTBO extracts and reports are in the ignored `research/` folder and are not committed.

## Main engineering gaps

1. **Build path:** upstream builds XNU on a macOS GitHub Actions runner. Its [Releases page has no binaries](https://github.com/dipa-studio/ios-sweet/releases) (checked 2026-11-15); the workflow keeps build artifacts for seven days. This Windows host has no AArch64 cross-compiler and WSL has no installed Linux distribution. GitHub CLI authentication is now restored. The fork's existing shim workflow run `43717125955` (commit `a563d834b366cafbb3dd912ce4b45c68b9a12480`) failed at the `mkbootimg` step with `ModuleNotFoundError: No module named 'gki'`; a local workflow correction is in progress. No XNU compile has run.
2. **Boot description:** `tools/mkadt.py`, the shim, and the Sweet platform expert contain device-specific addresses and identity. The live FDT now gives RAM banks, reserved regions, GIC/timer/PSCI setup, and the selected panel. A Bonito ADT/platform definition and a verified framebuffer handoff/stride are still missing.
3. **Storage:** `ios-sweet` patch 0028 implements a UFS host/root path. Bonito's `userdata` resides on eMMC (`mmcblk0p72`), so that driver cannot read an iOS HFS+ root. The live tree enables the Qualcomm SDHCI host at `0x7c4000`; a new XNU eMMC driver and verified controller handoff/init path are required for a full root volume. The upstream `tools/mkpayload.py --ramdisk` path and `rd=md0` boot argument can support a small initial RAM-disk root test without eMMC; the actual iOS image size must be measured against the available RAM before relying on that for userland.
4. **Display and input:** software rendering is suitable for the first UI milestone, but the active `sofef00` panel updates in command mode and needs a verified refresh path. The live tree gives Synaptics DSX's I²C address and GPIOs; XNU still needs the GENI/I²C driver, power sequencing, reset handling, and event glue.
5. **CPU and power:** CPU topology, page-size/instruction constraints, interrupt setup, timers, and the relevant Qualcomm power-controller operations must be verified against the live device tree and kernel source. The Sweet CPU and touch assumptions should not be copied blindly.
6. **System image:** after the kernel and basic drivers work, the iPhone X iOS 16 system image needs to be built locally from Apple's firmware and adapted for Bonito. Writing it to `userdata` would erase Android's user data.

## Experimental ADT profile

`tools/mkadt.py OUT.adt --bonito` now generates an experimental Sweet-kernel-compatible ADT from the documented live facts. It uses the candidate RAM interval `0xa2000000–0x17e2c0000`, emits the Bonito CPU cluster IDs and the shared GIC/timer addresses, uses a 1080 × 2160 framebuffer geometry, and omits Sweet's UFS node. This profile passed Python syntax and ADT structure checks on 2026-11-15; it has not been consumed by an XNU build or boot.

This is a staging profile, not a Bonito XNU target. The root retains `xiaomi,sweet` only so the existing `MACHINE_CONFIG=SWEET` kernel can be selected for a first-CPU experiment; the real hardware identifiers `qcom,sdm670` and `google,bonito` are also present. Use `cpus=1` until XNU's SMC/PSCI and GIC path are validated on this board. The splash stride remains an open question: the profile's 4320-byte value matches the current shim assumption, while TWRP reports a 4352-byte pitch for its separate recovery DRM buffers. Neither proves the ABL splash pitch.

The ADT retains the iPhone X (`D22AP` / `iPhone10,3`) identity because that is the userland target. The real D22AP `/product` node must be extracted from the user's Apple firmware into ignored research storage before testing the full iOS userland; it is not checked into this repository.

## Bring-up sequence

Keep each milestone isolated and logged. The verified recovery boot confirmed that `fastboot boot` starts a candidate without flashing a boot partition on this handset.

1. **Prepare recovery and source data.** The official Bonito recovery was checksum-verified and booted temporarily; live FDT and memory-map facts are recorded above. Before any persistent change, obtain a verified Pixel 3a XL factory image and verify the host can restore it. Keep calibration partitions and raw captures out of git.
2. **Add a Bonito machine target.** The `--bonito` ADT profile is a first staging step only. Add a real platform expert and kernel config instead of relying on the temporary Sweet compatibility marker. Start with one CPU and validate the aligned `0xa2000000–0x17e2c0000` candidate against XNU's allocator and bootloader staging before use.
3. **Build the shim and a console payload.** Confirm that the bootloader accepts the image, then display a pattern and get a persistent or USB log. Do not continue if memory boundaries or the framebuffer are guesses.
4. **Boot a minimal XNU kernel.** Establish early console, GIC interrupts, timer, one CPU, and a deliberate stop before adding SMP or peripherals. Use CPU rendering; no GPU work is needed yet.
5. **Bring up eMMC read-only.** Implement the SDHCI/eMMC path and read the partition table without changing it. Prove stable, bounded reads before adding writes or a root mount.
6. **Add panel, touch, and keys.** First present the iPhone X layout scaled/cropped to the Bonito panel. Then add Synaptics DSX and power/volume HID events. Keep each driver behind a Bonito-only build flag.
7. **Build and boot iOS userland.** Use Apple's iPhone X iOS 16 firmware, document every root-image tweak, and capture kernel/userland logs through USB. A small `rd=md0` image can test early userspace; confirm the full HFS+ root fits available RAM before using it to avoid eMMC.
8. **Only then install a persistent root.** The planned root partition is Android `userdata`; formatting or replacing its contents erases Android data. Preserve a restorable factory image, verify backups, and make one partition change at a time. Keep bootloader, radio, persist, and calibration partitions untouched.

## Build and device actions so far

- Fetched `dipa-studio/ios-sweet` at commit `45263bee51df4a0f55cdf9c649af886399488ddb` into `ios-sweet-src`, then created the isolated `ios-bonito` branch from that source.
- Read both requested project references and the `ios-sweet` build/boot instructions.
- Queried `adb devices -l`, read-only `getprop`, `wm size`, `dumpsys input`, `/dev/block/by-name`, and `df -h /data`.
- Read device-tree selector properties; downloaded and parsed Google's nearby public SDM670 DTB/DTBO release artifacts using `tools/fdt_dump.py`.
- Confirmed ADB sees `bonito`; `fastboot getvar` independently reported `product=bonito`, `unlocked=yes`, and `current-slot=a`. After `fastboot reboot`, ADB saw the handset return to Android.
- Tried read-only `fastboot fetch boot_a`; the bootloader rejected it as unsupported. `fastboot reboot` returned the phone to Android.
- Tried the normal sandboxed GitHub clone first; network access was denied. The user approved the escalated GitHub source fetch, which completed.
- Checked the build host: `adb.exe` and `fastboot.exe` are present; no `clang`/GNU AArch64 tools were found on `PATH`; invoking WSL returned `Access is denied`; `gh auth status` says the saved GitHub token is invalid.
- Performed a reversible Android → bootloader → Android check. `fastboot getvar` worked; ADB reconnection required elevated host access after a transient local ADB-server reset.
- Downloaded the official [Bonito TWRP 3.7.1_12-1 image](https://dl.twrp.me/bonito/), verified SHA-256 `e0781b592354a87ef8369cce36a0ed61e5bd751058d0eadf68c632c3568678d0` against TeamWin's checksum, and booted it with `fastboot boot` (not `fastboot flash`); fastboot reported upload and boot `OKAY`.
- In its root ADB shell, read `/sys/firmware/fdt` and `/proc/iomem`; recorded the physical RAM segments, reserved ranges, selected panel, and enabled eMMC controller. Raw captures remain ignored under `research/` because the FDT includes device identifiers.
- Rebooted with `adb reboot`; verified Android `bonito`, build `SP2A.220505.008`, and active slot `_a` returned. Recovery had automatically mounted `/data` and `/metadata` read-write; no partition was flashed or erased, and incidental recovery writes cannot be ruled out.
- Read the fork's existing Bonito shim CI run `43717125955`; cross-compilation reached boot-image packaging, where Ubuntu's packaged `mkbootimg` failed due to its missing `gki` Python module. No artifact was uploaded.
- Committed locally, not yet published, a workflow change using AOSP's standalone Android boot header v2 tool at pinned commit `0efe12324857ad410d64677e66347434b2346526`.
- Pushed the reviewed branch `port/bonito-bringup` and ran shim workflow `43724648790` successfully; both `bonito-shim-boot` and `bonito-target-adt` artifacts uploaded. The 638,976-byte shim image has boot header v2, kernel/ramdisk/DTB addresses matching the known-good recovery image, and SHA-256 `95c4bc85557808900d70b46554a84566dbe51d483a6ca344c8e6bf2f05b75afe`.
- The first CI artifact was rejected with `Unsupported`; its OS metadata was Android 17 with no patch level. Changing this to Android 12 / May 2022 produced the expected `0x18000165` field but did not by itself make ABL accept the image.
- A local TWRP-shaped diagnostic with a raw shim kernel remained rejected. A default LZ4 frame changed the error to `Invalid Parameter`. A frame using TWRP's exact LZ4 header profile plus matching ARM64 Image layout and AVB footer returned `Booting OKAY` under `fastboot boot`. It used TWRP ramdisk/DTB; the repository's Bonito DTB and empty shim ramdisk have not yet been tried in an accepted image.
- The source build and CI workflow are being updated to reproduce that accepted layout. The update is not yet committed or run in CI.
- **No iOS kernel/XNU payload has been built or booted.** The temporary boot milestone only confirms ABL handoff for a diagnostic shim image.

## Immediate next action

Finish the local TWRP-compatible LZ4/header/AVB changes, publish them to the Bonito branch, run shim CI, inspect the artifact, and try it with temporary `fastboot boot`. Confirm phone display and regain a known bootloader/Android state before building the Bonito XNU target. Keep the experimental ADT as staging only; it does not make Sweet's XNU platform target Bonito-compatible by itself. Do not build a userdata image until eMMC read-only access and a restore plan are proven.
