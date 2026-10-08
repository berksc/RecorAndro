# RecorAndro device baseline

This baseline records values supplied by the user from actual Redmi Note 10 Pro screenshots and reviewed Step 1.1 tests on that device. The installed build is the observed current baseline; it is not claimed to be the latest available build.

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
| MIUI version reported during Step 1.1 validation | V13.0.7.0.SKFTRXM |
| Security patch date | 2023-02-01 |

An OTA update notification is present. Current Android/MIUI build accepted as RecorAndro v0.1 development baseline; OTA intentionally deferred by user.

## Environment

| Field | Baseline value |
| --- | --- |
| Root status | Rooted — verified functional; per-app authorization via Magisk. |
| Magisk | 31.0 (31000), installed |
| Zygisk | Disabled |
| Ramdisk | Yes |
| Termux source and version | F-Droid 0.118.3 |
| Python version | 3.14.6 |
| FFmpeg version | 8.1.3 |
| ffprobe version | 8.1.3 |
| Architecture / ABI | aarch64 / arm64-v8a |
| Ordinary Termux UID | 10274 |
| running_as_root | false |
| Configured data root writable | Verified |
| Available storage at Step 1.1 validation | 95020343296 bytes (measured; distinct from the initial estimate) |

## Step 1.1 actual-device validation

The user successfully ran these checks on the actual Xiaomi Redmi Note 10 Pro
in ordinary Termux context. The user reports that `capability-result.txt` was
independently reviewed; these are actual-device results, not inferred host results.

| Check | Verified result |
| --- | --- |
| Doctor | PASS |
| Python foundation unit tests | 12/12 PASS |
| Synthetic Android media capability checks | 41/41 PASS |
| Step 1.1 acceptance | FINAL PASS |

MEDIA_CONTRACT Android-capability-validated

Raw AAC duration estimation and effective AAC bitrate observations remain
nonblocking follow-up requirements, documented in [STEP_1_1_REPORT.md](STEP_1_1_REPORT.md).

## Operational notes

- The device is also used as an iPhone hotspot.
- Xiaomi/MIUI background restrictions are a future real-device constraint to observe and measure.
- Root is optional. The normal media-processing core must remain usable from an ordinary Termux user context and must not depend on root.
