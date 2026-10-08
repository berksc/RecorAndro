# RecorAndro device baseline

This baseline records values supplied by the user from actual Redmi Note 10 Pro screenshots. Pending fields require further device verification. The installed build is the observed current baseline; it is not claimed to be the latest available build.

## Device

| Field | Baseline value |
| --- | --- |
| Manufacturer | Xiaomi |
| Model | Redmi Note 10 Pro |
| Storage capacity | 128 GB |
| Used storage at baseline | 31.3 GB |
| Approximate free storage at baseline | 96.7 GB (calculated estimate: 128 GB - 31.3 GB) |

This is a secondary device, not the user's primary phone.

## OS

| Field | Baseline value |
| --- | --- |
| Android version | 12 |
| Android build | SKQ1.210908.001 |
| MIUI release | Global 13.0.7 Stable |
| Exact MIUI version string | 13.0.7.0 (SKFTRXM) |
| Security patch date | 2023-02-01 |

An OTA update notification is present. This baseline reflects the installed build, pending the user's decision on OTA.

## Environment

| Field | Baseline value |
| --- | --- |
| Root status | Magisk installed; functional `su` access not independently verified yet |
| Magisk | 31.0 (31000), installed |
| Zygisk | Disabled |
| Ramdisk | Yes |
| Termux source and version, when installed | Pending step 1.1 |
| Python version, when installed | Pending step 1.1 |
| FFmpeg version, when installed | Pending step 1.1 |
| ffprobe version, when installed | Pending step 1.1 |
| Architecture / ABI | Pending verification |

## Operational notes

- The device is also used as an iPhone hotspot.
- Xiaomi/MIUI background restrictions are a future real-device constraint to observe and measure.
- Root is optional. The normal media-processing core must remain usable from an ordinary Termux user context and must not depend on root.
