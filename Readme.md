# Pixel 6 Pro (raven) Kernel Build

Builds a custom kernel for **Pixel 6 Pro (raven)** with:
- **AHK Fire** branding (KernelSU-Next + SUSFS + BBG + Networking + DroidSpaces)
- **NetHunter** wireless toolbox (RTL8188FU, ath9k, rt2x00, rtl8xxxu, mt7601u, USB/IP, Bluetooth)
- **DroidSpaces** container support (full namespaces, cgroups, overlayfs, veth)

## Source

| Component | Repo | Branch/Commit |
|-----------|------|---------------|
| Kernel | `ahksoft/AHK_kernal_gs` | `blu_spark-17` (6.1.157) |
| SUSFS | `simonpunk/susfs4ksu` | `gki-android14-6.1` |
| KernelSU-Next | `pershoot/KernelSU-Next` | `dev-susfs` |
| AnyKernel3 | `osm0sis/AnyKernel3` | `gki-2.0` |

## Dispatch

From the Actions page, select **Pixel 6 Pro Kernel Build (raven)** → Run workflow:

| Input | Default | Description |
|-------|---------|-------------|
| `feature_set` | `FULL` | KSUN, SUSFS, BBG, NET, DS, or FULL |
| `ksu_branch` | (empty) | KernelSU-Next branch override |
| `susfs_commit` | (empty) | SUSFS commit override |
| `kernel_branch` | `blu_spark-17` | AHK_kernal_gs branch |

## Architecture

AHK_kernal_gs has a **flat layout** (kernel source at root, no `common/` subdirectory). The workflow creates a symlink after cloning:

```
kernel/           ← AHK_kernal_gs clone root
kernel/common/    ← symlink → . (makes existing actions work)
```

The existing composite actions (kernelsu, susfs, bbg, networking, droidspaces, etc.) reference `kernel/common/` and work via this symlink.

## Build

The workflow runs `tools/bazel build --config=fast --config=stamp //common:kernel_aarch64` twice:
1. **Normal** build
2. **Bypass** build (patches `bad_version:` return in `kernel/module/version.c`)

## NetHunter Config Overlay

`.github/actions/pixel6pro-nh-config/action.yml` enables:

- WiFi vendor gates: ATH, MEDIATEK, RALINK, REALTEK
- Modules: cfg80211, mac80211, RTL8188FU, ath9k_htc, rt2x00, rtl8xxxu, mt7601u
- USB/IP, RNDIS gadget, CDC drivers
- Bluetooth full stack (RFCOMM, HIDP, HCIUART)
- HID devices, iptables TEE, PPP/PPPoE
- DroidSpaces: namespaces, cgroups, SYSVIPC, devtmpfs, binfmt_misc, veth, overlayfs, vsock

## Output

- `raven-AnyKernel3` artifact: flashable zip with kernel Image + 18 wireless modules + firmware
- `raven-build-summary` artifact: build status report

## Known Limitations

- SUSFS/networking/droidspaces patches are version-specific to GKI sublevels. Some may need adaptation for 6.1.157.
- BCM4389 (internal WiFi) needs separate firmware (`fw_bcmdhd_monitor.bin`) and `wifi_sniffer` utility — not included in this build.
- Private Google modules (bcmdhd, etc.) are not cloned; this builds only the GKI base kernel.
