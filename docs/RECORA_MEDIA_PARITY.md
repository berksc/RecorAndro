# Recora media-processing reference extraction

## Source identity and confidence

Extracted on 2026-10-08 from the actual accessible Recora working checkout:

| Identity | Observed value |
| --- | --- |
| Repository path | `C:\loxi\Recora` |
| Branch | `main` |
| HEAD commit | `9b886519ea623fa8bf0746f96ea512da18413bde` |
| Commit subject | `First Version Final Review - OK, Freezed` |
| Commit timestamp | `2026-09-29T23:23:30+03:00` |
| Local configuration | No `config.local.json` in this checkout; values below are source defaults, not a claim about another running instance. |

Access and identity were established before extraction. The 23 evidence files listed below were checked with `git rev-parse HEAD:<path>` and `git hash-object --path=<path> <path>`; all working-file Git blob identities matched HEAD. Git status/diff failed with `this operation must be run in a work tree` in this execution environment, so this is an evidence-file comparison, not a claim that the entire checkout is clean. Recora was read only: no source edits, configuration changes, installations, or test execution were performed.

Confidence order: actual implementation and its test assertions, then current detailed documentation, then broad prose. This is source inspection, not a new runtime qualification. `docs/FINAL_REVIEW.md` reports 254 tests, zero failures/errors, and nine skips at freeze: one ffprobe fixture and eight FFmpeg/ffprobe integration fixtures were skipped. Their presence establishes intended assertions, not an integration pass. No remembered or planning-document values are used here.

All RecorAndro candidates in this document are **provisional and unfrozen**. No media-processing implementation or Android workaround is introduced.

> Recora parity means media-processing behavior and invariants only.
> It does not imply code, filesystem, state-machine, deployment or architecture parity.

## Evidence inventory

Paths and symbols below refer to the Recora checkout and commit above. Line anchors identify entry points; the corresponding complete functions/tests were inspected.

| ID | Exact Recora evidence | Use |
| --- | --- | --- |
| E01 | [app/uploads.py](C:/loxi/Recora/app/uploads.py:21): `AUDIO_TYPES`, `IMAGE_TYPES`, `file_name_and_type`, `receive_lecture` | Extension/MIME acceptance; acceptance precedes probing. |
| E02 | [app/storage.py](C:/loxi/Recora/app/storage.py:147): `SessionWriter.begin_file`, `write_file`, `end_file`, `commit`, `safe_path` | One nonempty audio; optional images; immutable accepted bytes, byte sizes and SHA-256. |
| E03 | [app/audio.py](C:/loxi/Recora/app/audio.py:25): `probe_local_media`, `parse_probe`, `probe_audio`, `parse_quiet_regions`, `detect_quiet_regions`, `analyze_segmentation` | Probe, duration selection, quiet detection, verified analysis source. |
| E04 | [app/normalization.py](C:/loxi/Recora/app/normalization.py:19): constants, `parse_loudness`, `choose_gain`, `_input_args`, `_run`, `normalize_audio`, `_generate_boosted_copy` | Measurement, gain decision, encoding and verification. |
| E05 | [app/segmentation.py](C:/loxi/Recora/app/segmentation.py:8): `plan_boundaries`, `export_ranges` | Deterministic boundaries, coverage, overlap geometry. |
| E06 | [app/exports.py](C:/loxi/Recora/app/exports.py:66): `_source`, `export_audio_parts`, `read_export`, `part_download` | Source/plan checks, sample trimming, copy exception, output verification. |
| E07 | [app/config.py](C:/loxi/Recora/app/config.py:13): `Settings`, `__post_init__`, `load_settings` | Defaults and validated setting ranges. |
| E08 | [app/main.py](C:/loxi/Recora/app/main.py:391): `restart_processing`, `normalize`, `processed_audio` | No Force-mode parameter; original-download hash check and derived-download limitation. Routes are evidence, not architecture to adopt. |
| E09 | [app/resumable_uploads.py](C:/loxi/Recora/app/resumable_uploads.py:87): `create_upload`, `finalize_upload` | Reuses E01 media acceptance; publishes originals before probing. Network mechanism excluded from parity. |
| E10 | [app/start_time.py](C:/loxi/Recora/app/start_time.py:24): `metadata_candidates`, `initial_start_time`, `with_candidates` | Creation times are unverified candidates, never effective recording start automatically. |
| E11 | [app/images.py](C:/loxi/Recora/app/images.py:99): `read_image_metadata` | Read-only optional photo header/EXIF parsing and integrity checks; per-image failures. |
| E12 | [tests/test_uploads.py](C:/loxi/Recora/tests/test_uploads.py:22): `wav_bytes`, `UploadTests` | Audio-only, extension/MIME, duplicate/empty audio, original hashes. |
| E13 | [tests/test_audio.py](C:/loxi/Recora/tests/test_audio.py:19): `metadata`, `ParsingTests`, `ProbeTests` | Stream choice, duration fallback, invalid metadata/media, subprocess safety. |
| E14 | [tests/test_normalization.py](C:/loxi/Recora/tests/test_normalization.py:27): `fixture`, `GainTests`, `ProcessingTests`, `RealAudioTests` | Thresholds, skips, timing, clipping, generated quiet/loud/silent/stereo audio. |
| E15 | [tests/test_segmentation.py](C:/loxi/Recora/tests/test_segmentation.py:34): `synthetic_audio`, `PlannerTests`, `DetectionTests`, `AnalysisTests`, `RealAudioTests` | Ranking, quiet parser, 61-minute plan, scaled real audio, source integrity. |
| E16 | [tests/test_exports.py](C:/loxi/Recora/tests/test_exports.py:32): `RangeTests`, `ExportTests`, `RealExportTests` | ~90-minute arithmetic, overlap/end caps, copies, sample cuts, real 61-minute fixture. |
| E17 | [tests/test_images.py](C:/loxi/Recora/tests/test_images.py:31): `ImageMetadataTests` | JPEG/PNG/HEIF metadata, unchanged bytes/mtime, malformed images and hash failures. |
| E18 | [README.md](C:/loxi/Recora/README.md:314): conservative normalization, Step 2.3, Step 2.4, Tests | Detailed current media explanation and historical lecture regression. |
| E19 | [docs/SCOPE.md](C:/loxi/Recora/docs/SCOPE.md:48): invariants | Silence/timeline/original preservation; high-level duration prose. |
| E20 | [docs/ARCHITECTURE.md](C:/loxi/Recora/docs/ARCHITECTURE.md:351): Audio processing workflow | Current detailed media policies; stale acceptance-order prose. |
| E21 | [docs/FINAL_REVIEW.md](C:/loxi/Recora/docs/FINAL_REVIEW.md:21) and [docs/RELIABILITY_CHECKLIST.md](C:/loxi/Recora/docs/RELIABILITY_CHECKLIST.md:9) | Frozen test history, media skips, ~90-minute coverage limitation. |
| E22 | [config.example.json](C:/loxi/Recora/config.example.json) | Confirms source-default quiet/window/overlap values. |

## A. Input/media support

### Audio acceptance and actual inspection

Exactly one nonempty audio file is required. Zero photos is valid. Extension checks are case insensitive after filename sanitization. E01 defines:

| Extension | Accepted declared MIME types |
| --- | --- |
| `.m4a` | `audio/mp4`, `audio/m4a`, `audio/x-m4a`, `video/mp4` |
| `.mp3` | `audio/mpeg`, `audio/mp3`, `audio/x-mp3` |
| `.wav` | `audio/wav`, `audio/wave`, `audio/x-wav`, `audio/vnd.wave` |
| `.aac` | `audio/aac`, `audio/x-aac` |

MIME values are lowercased, whitespace trimmed, and parameters after `;` ignored. Missing MIME and `application/octet-stream` are accepted as unverified originals. A supported suffix with a different specific MIME is rejected. Unsupported suffix/MIME raises 415; missing/duplicate audio or empty files raises 422. E12 tests FLAC/EXE refusal and WAV with `text/html` / MP3 with `image/png` refusal.

Technical inspection is separate from acceptance. ffprobe/FFmpeg inputs are restricted to demuxers `mov,mp3,wav,aac` and protocol `file`; this does not establish that file contents match their suffix. E12's `test_supported_audio_extensions` uses the same WAV bytes under several supported extensions and asserts acceptance. Malformed but accepted bytes remain stored; failed probing does not revoke acceptance (E01, E09, E13).

There is **no input codec allowlist** beyond a recognized audio stream whose `codec_name` is neither missing nor `unknown`. Actual codec decode availability depends on the installed tools. Tests exercise PCM S16LE WAV, AAC in M4A, and MP3 generated with `libmp3lame` (E13–E16). Raw `.aac` is accepted by extension/MIME and demuxer policy, but the inspected real-audio fixtures do not establish an end-to-end raw AAC case. Other codecs in permitted containers are not demonstrated by these tests. Encoding paths enforce AAC output; the compatible full-length copy exception also permits MP3.

### Optional photos

E01 accepts `.jpg`/`.jpeg` (`image/jpeg`), `.png` (`image/png`), `.heic` (`image/heic`, `image/heic-sequence`) and `.heif` (`image/heif`, `image/heif-sequence`), with the same generic/missing-MIME allowance. Default Recora admission limits are 1 GiB audio, 20 MiB per image, 20 images, and 2 GiB total request (E07); these are reference admission limits, not frozen RecorAndro requirements.

E11/E17 inspect JPEG/PNG headers and EXIF through Pillow and HEIC/HEIF through lazy `pillow-heif` container access. They verify size/SHA-256 before and after parsing, preserve bytes, and do not convert/re-encode photos. Corrupt or missing metadata is a per-image diagnostic and does not reject accepted audio or photos. This extraction does not extend into photo alignment or packaging behavior.

## B. ffprobe/media inspection

E03 requests JSON with these exact entries:

```text
format=format_name,duration,size,bit_rate,start_time:format_tags=creation_time:
stream=index,codec_type,codec_name,sample_rate,channels,channel_layout,bit_rate,
duration,duration_ts,time_base,start_time:stream_tags=creation_time
```

The strings are concatenated without the formatting newlines above. Probe options include `-v error -protocol_whitelist file -format_whitelist mov,mp3,wav,aac -enable_drefs 0 -use_absolute_path 0 -show_entries <entries> -of json -i <path>`.

- **Selected stream:** first recognized audio stream in ffprobe's returned stream order. Unknown-codec audio is skipped; a video stream does not take precedence. This is not a highest-bitrate or default-disposition selection. The reported absolute stream index is saved and mapped explicitly as `-map 0:<index>` in FFmpeg (E03/E04; E13 `test_first_recognized_audio_and_stream_creation_time`).
- **Duration precedence:** positive selected-stream `duration`, else positive `duration_ts * time_base numerator / denominator`, else positive container duration. Video duration and wall-clock tags never define or shift the audio timeline. Positive duration minimum is `0.000001` seconds.
- **Validation:** numbers reject booleans, nonnumeric/nonfinite values, out-of-range values, and nonintegral integer fields; maximum numeric bound is `2**53`. Missing optional values remain null. Missing usable duration produces a warning; fewer than two estimates produces a no-independent-cross-check warning. Estimates differing from the selected duration by more than `max(1.0, duration * 0.01)` produce a disagreement warning. Initial probing can still succeed with these warnings; normalization/planning/export refuse known disagreement or required missing fields.
- **Codec/rate/channels:** codec name, rate, channel count/layout, selected-stream and container bitrate, start times, stream count and time base are recorded separately. Probe parsing itself does not enforce mono/stereo or the later processing sample-rate range.
- **Creation times:** whitelisted container/audio-stream tags are retained with `trusted: false`. E10 parses full ISO timestamps as candidates, retaining explicit offsets when valid. Candidates do not automatically establish recording start and do not shift media-relative time. File mtime is not used to establish audio recording start.
- **Failure:** no recognized audio, malformed/oversized JSON (over 1 MiB), bad metadata structure, tool nonzero exit, missing executable, inaccessible paths and a 30-second timeout fail probing. Accepted originals remain. `probe_audio` checks size and mtime before/after; this initial probe does not perform a SHA-256 comparison. A discrepancy between reported container size and actual size is a warning, not refusal. Raw diagnostic text is private and bounded to 4,096 characters (E03/E13).

## C. Normalization

### Measurement and decision

Actual method: `ebu_r128_low_level_boost_v2`, policy version 2 (E04). Normalization is an explicitly requested check; there is no Auto/Force mode enum. Its decision is the factual candidate for a future Auto mode.

1. Require successful prior probe, accepted filename/hash metadata, original SHA-256 matching the accepted record, and a fresh probe.
2. Require positive known duration, selected stream index, **7,350–192,000 Hz** rate and **1 or 2 channels**. Refuse duration disagreement.
3. Fully decode the selected audio with `-af loudnorm=I=-26:TP=-3:LRA=50:print_format=json -f null -`. The transformed measurement output is discarded; the JSON **input** values supply integrated LUFS, true peak dBTP, loudness range LU and threshold LUFS. This is EBU R128 measurement, not peak/RMS normalization. No media file is produced by measurement.
4. `parse_loudness` reads the last matching JSON block in the returned diagnostic tail. Invalid/nonfinite measurements fail; finite values are limited to `[-120,100]`, with nonnegative LRA. `-inf` integrated loudness/true peak/threshold becomes null; finite loudness with missing true peak fails.

| Parameter | Actual value / behavior |
| --- | --- |
| Low-level eligibility | Strictly below **-30 LUFS**; exactly -30 or louder skips. |
| Target | **-26 LUFS**, a desired gain target, not a guaranteed achieved level. |
| Maximum boost | **3 dB**, positive only; no attenuation. |
| Planning true-peak ceiling | **-3 dBTP** when choosing gain. |
| Minimum useful boost | **0.5 dB**; smaller gain skips. |
| Gain precision | Floor to **0.001 dB** before the minimum-useful check. |
| Encoded hard peak limit | Reject output if measured true peak is **greater than -1 dBTP**. Exactly -1 is not rejected by this condition. |
| Encoded overshoot warning | Warning when true peak is **greater than -2.9 dBTP** and passes the hard limit. |

For eligible finite measurements:

```text
desired = -26 - integrated_lufs
headroom = max(0, -3 - true_peak_dbtp)
gain = max(0, min(desired, 3, headroom))
gain = floor(gain * 1000) / 1000
if gain < 0.5: gain = 0
```

Below-gate loudness skips. Input peaks at or above 0 dBTP generate a possible-existing-clipping warning, not an attempted repair. Decisions are `low_level_safe_boost`, `below_measurement_gate`, `already_usable_level`, or `insufficient_safe_gain`. Gain raises background noise too. E14 tests -30/-30.001 LUFS and 0.49/0.5 dB headroom boundaries; the historical -27.70 LUFS / -1.39 dBTP lecture skips unchanged.

**Skip:** recheck original hash, return `not_needed`/successful with original as working source. No derived audio, gain filter, resampling, metadata stripping or re-encoding; duration/hash/bytes remain identical, with zero duration tolerance.

**Force:** no direct equivalent exists. E08's normalize and restart actions call the same E04 decision function without a force parameter. Restarting does not bypass the skip thresholds. A RecorAndro Force policy would require a separate later decision, not a claim of extracted parity.

### Applied transform and delivery format

When gain is useful, the only audio transform is:

```text
volume=<gain formatted to 3 decimal places>dB:precision=double
```

E04 encodes a separate M4A using native `aac`, `-profile:a aac_low`, `-b:a 128000` mono or `192000` stereo, `-movflags +faststart -f ipod`. Channels remain unchanged; there is no `-ac` downmix. Input metadata/chapters are stripped with `-map_metadata -1 -map_chapters -1`; only selected audio is mapped, excluding video/subtitle/data. These bitrate values are requested targets, not exact measured bitrate/size guarantees; no quality-scale setting is used.

Preserve the source rate if it is in `AAC_RATES`:

```text
7350, 8000, 11025, 12000, 16000, 22050, 24000,
32000, 44100, 48000, 64000, 88200, 96000 Hz
```

Other admitted source rates are resampled to **48,000 Hz** without a speed change. There is no compressor, limiter, EQ, denoise, silence removal, trim, tempo change, or dynamic loudnorm pass applied to the delivered audio.

### Verification and failures

Probe the pending encoded file; require nonempty size, AAC codec, retained channels, requested rate, positive duration and start near zero. Duration delta and absolute output-stream start must each be within:

```text
max(0.05 seconds, 2048 / min(input_rate, output_rate))
```

This fixed allowance never scales with lecture length. At 16 kHz it is 0.128 seconds. Fully decode and measure the output with the same measurement filter; apply the encoded peak rules above, recheck original SHA-256, hash the derived file, then publish its final name. There is no achieved-LUFS or achieved-gain acceptance assertion. A below-gate/null output peak is not rejected by the finite-peak comparisons themselves.

Missing tools, invalid metadata, decode/encode errors, malformed measurements, timeout, empty/wrong-format output, timing failure, unsafe original change or an existing final output fail processing. Originals and earlier completed outputs remain; an unsuccessful pending derivative may remain for diagnosis and is not accepted as a successful output. Per-pass timeout is `min(21600, max(120, ceil(duration * 2 + 60)))` seconds (E04; E14).

## D. Segmentation analysis

E03 analyzes the verified working source: normalized M4A after successful boost, or the original after `not_needed`. It requires a successful processing record, checks both original/source hashes, freshly probes source duration/rate/index, refuses disagreement, and requires the probed duration to match the processing record within `1e-6` seconds. Hashes are checked again before accepting the plan.

| Source default | Exact value | Validated configurable range |
| --- | --- | --- |
| Target nominal duration | **1500 s (25 min)** | `1 <= window_min <= target <= window_max <= 86400` |
| Search-window minimum | **1200 s (20 min)** after previous chosen boundary | Same ordering constraint |
| Search-window maximum | **1620 s (27 min)** after previous chosen boundary | Same ordering constraint |
| Quiet threshold | **-40 dBFS** | -90 to -10 dBFS |
| Minimum quiet duration | **1 s** | 0.1 to 60 s |

Exact default detector filter (E03/E15):

```text
asetpts=PTS-STARTPTS,silencedetect=noise=-40dB:duration=1:mono=0
```

Output goes to the null muxer. Channels are combined (`mono=0`), so silence in only one stereo channel is insufficient when the other remains active. Analysis timestamp rebasing preserves sample spacing; it does not modify the source. Parse the **complete** spooled log, not a diagnostic tail, only after full decoding succeeds.

`parse_quiet_regions` recognizes ordered silence start/end pairs including leading quiet; an open trailing interval extends to the probed source end. Timestamp tolerance is `max(0.05, 2048 / sample_rate)`; within-tolerance values are clamped to `[0,duration]`. Invalid, unmatched, duplicate or unordered events fail. Intervals qualify when length plus `1e-5` is at least the minimum; more than 100,000 retained intervals fails.

E05 boundary algorithm:

1. Start at `previous = 0`. Continue while remaining duration is **greater than** target.
2. Ideal = `previous + target`; inclusive window = `[previous + window_min, min(previous + window_max, source_duration)]`.
3. Use each qualifying quiet interval's full midpoint if inside the window. If outside, use its intersection midpoint only when the intersection is at least the minimum quiet length (with `1e-5` allowance). Candidate must be strictly before source end.
4. Rank by **distance from ideal ascending**, **full quiet-interval duration descending**, **candidate timestamp ascending**, then interval start/end ascending. Ranking uses the full interval length even when its intersection supplies the midpoint.
5. If there is no qualifying candidate, choose the exact ideal and record `fallback_target`; do not label it quiet. The next ideal/window is relative to the chosen boundary, not fixed multiples from zero.
6. Build contiguous nominal segments from zero, chosen boundaries, and exact source end. Duration at or below 1500 seconds is one segment. A long all-quiet interval can supply an intersection midpoint rather than the ideal; E15 tests a first boundary at 1410 seconds for an all-quiet 3660-second source.

**Tiny-part protection is limited:** no empty nominal segment; candidates cannot equal source end; nonfinal choices are bounded by the configured window minimum. There is **no minimum final-part duration or tail-merging rule**. A 1500.1-second no-candidate source produces a 0.1-second final nominal remainder (E16). Export also rejects sample ranges with no samples, but does not impose a useful minimum part length.

Analysis writes only factual plan/detection metadata. Decode failure, timeout, bad intervals, missing/stale duration or hash changes fail without an accepted plan. Silence is not removed (E03/E05/E15).

## E. Segment export

### Geometry and global timeline

E06 requires a current successful plan tied to the verified processing source. It checks processing identity/hash/duration, exact equality of saved analysis and current analysis, original/source hashes, selected stream, rate, mono/stereo and duration metadata. Export uses the saved plan; it does not detect quiet again or move nominal boundaries.

E05 requires supported schema, zero start, positive finite end, `silence_removed: false`, 1–10,000 ordered segments, matching boundary count/indices/timestamps, exact contiguous starts/ends, length agreement within `1e-6`, and final nominal end exactly equal to source duration. No gaps are permitted.

Overlap defaults to **5 seconds**, configurable from 0 to 60. Only nominal ends extend:

```text
nominal [start, end] -> export [start, min(source_duration, end + overlap)]
```

The following part starts at the unchanged boundary. No start is shifted backward; overlap is not five seconds on each side. Global start/end represent source-relative seconds; measured encoded duration is recorded separately and does not redefine the geometry. Before/after overlap values are computed from actual capped intersections. The final part ends at exact source end and has no after-overlap. A tiny final remainder can be repeated in its entirety in the preceding part.

For a 3660-second fallback plan: nominal `[0,1500]`, `[1500,3000]`, `[3000,3660]`; export `[0,1505]`, `[1500,3005]`, `[3000,3660]`. Requested durations are 1505, 1505 and 660 seconds. For 5437 seconds with no candidate: nominal ends 1500, 3000, 4500, 5437, with four covering exports (E16 `RangeTests`).

### Encoding versus copying

Policy identifier: `aac_m4a_sample_trim_v1`. Every cut part is decoded directly from the same verified full source and independently encoded as AAC-LC/M4A with the **same rate/channel/bitrate rules as C**. It does not use a prior part as input, apply gain again, or strip silence.

Exact trimming operation:

```text
start_sample = round(global_start_seconds * source_rate)
end_sample   = round(global_end_seconds * source_rate)
atrim=start_sample=<start_sample>:end_sample=<end_sample>,asetpts=PTS-STARTPTS
```

Python `round` is used; start is inclusive and end exclusive in decoded sample counters. Rounding is at most half a source sample. No `-ss` packet seek or `-t` cut is used. Re-encoding supports sample-based boundaries and predictable local timing rather than packet-aligned stream-copy cuts. M4A limits delivery size relative to PCM WAV. Each part may decode from source start again; this code does not optimize that Android performance cost.

**Exception:** one full-length range, exactly one probed stream, and either AAC with `.m4a` source suffix or MP3 with `.mp3` suffix: copy the source bytes directly to that same extension. This is a byte copy, **not FFmpeg `-c copy`**. No cut/remux/re-encode is performed. It preserves original rate/channels/bitrate/metadata. A single WAV or raw AAC source takes the encoding path. The code resolves FFmpeg before this exception and still uses it for full-decode verification (E06/E16).

### Output verification and failures

Every pending part is probed, must be nonempty, have positive duration matching requested span, and preserve channel count. Encoded parts must be AAC at the expected rate with stream start near zero; delta and start tolerance is `max(0.05, 2048 / min(source_rate, output_rate))`. Full-length copies use **zero duration tolerance** and must match source SHA-256; their start timestamp is not subjected to the encoded-start-zero condition.

Each part fully decodes to null under error-failing options, is hashed, then renamed to its final filename. Only after all parts pass and source/original hashes are rechecked does the export report overall success and verified coverage. Prior matching exports are reused only after saved metadata and actual size/hash checks; this reuse path does not repeat full decoding. A missing/corrupt derivative can cause a new run rather than an overwrite. Partial success is not a completed export; some already-verified files may remain when a later part fails.

Failure cases include stale/tampered plans or sources, gap/boundary mismatch, missing media, no samples, duration/start/format mismatch, empty output, full-decode error, timeout or source changes during export. Sources and earlier outputs remain. There is no new loudness/true-peak verification of re-encoded segment outputs (E06/E16).

## F. Media integrity invariants and subprocess behavior

- **Silence removal policy:** never remove silence or concatenate disjoint quiet/nonquiet regions. Quiet detection only chooses boundaries. Normalization applies constant gain; export selects overlapping contiguous source intervals. No speed change, denoise, EQ or compression chain is present (E04–E06, E14–E16, E19).
- **Timeline:** wall-clock creation/start tags are separate. Analysis rebases discarded PTS; export rebases only each part to local zero. Coverage is of the verified working source. With amplification, that source's measured duration can differ slightly from original within normalization tolerance; E03/E06 use the working duration as exact plan/export endpoint. This does not prove sample identity or exact original-duration equality after lossy encoding.
- **Original immutability:** admission records SHA-256 and byte count; originals are opened with exclusive create and never transformed in place. Normalization and subsequent analysis/export compare original hashes before and after work. Skips are byte-identical. Reruns preserve earlier completed output. E11 verifies optional image size/hash around metadata reads.
- **Derived verification:** normalization re-probes, measures/decode-checks, verifies timing/format/nonempty size, and hashes before publication. Export checks plan/source identity and ranges, probes and decodes every new part, stores sizes/hashes, and rechecks sources. A hash check proves byte identity to a recorded file, not perceptual equivalence or completeness of unrecorded metadata.
- **Check limits:** the initial audio probe checks size/mtime, not hash; reported size mismatch is a warning. E08's skipped-original delivery checks SHA-256, but its derived `processed_audio` route only checks file existence, unlike E06's part delivery size/hash check. Do not generalize that every Recora read re-verifies hashes or every media stage rechecks accepted byte size.
- **Subprocess safety:** argument lists, `shell=False`, stdin disconnected and `-nostdin` where using FFmpeg; configured executable resolution, bounded timeouts; file-only protocols, permitted demuxers, disabled MOV external references/absolute external paths; explicit selected audio map with `-vn -sn -dn`; `-err_detect explode` and `-xerror` for decoding/processing; exclusive outputs and FFmpeg `-n` to refuse overwrite. No user filename becomes a shell command or arbitrary input URL. Windows `.exe` enforcement/hidden windows are observed platform details, excluded from Android parity (E03/E04/E06/E13/E14).
- **Diagnostics:** ffprobe uses captured JSON/stderr with a 30-second timeout. FFmpeg logs spool to disk; `_run` returns at most its last 65,536 bytes for measurement parsing and keeps at most 4,096 diagnostic characters. Quiet analysis parses the entire spool then keeps the bounded tail. FFmpeg per-pass timeout follows C and is also used for analysis/export. This is bounded retained diagnostics, not a proven constant-memory/disk bound for every subprocess output.

## G. Test fixtures worth semantic reuse

Fixtures are generated by test functions; they are not bundled real lecture recordings. Names below identify exact tests in E12–E16. Mock/unit tests assert decisions and metadata; guarded real-tool tests assert playable media when actually run.

| Need | Exact Recora test / fixture | Semantics and coverage limit |
| --- | --- | --- |
| Very short audio | E12 `wav_bytes`; E13 `ProbeTests.test_real_generated_wav_and_invalid_media` | 0.025 s, mono 8 kHz S16LE WAV; real probe test guarded by ffprobe on PATH. |
| Short / at-target | E15 `PlannerTests.test_short_at_target_and_subsecond_files_are_one_segment`; E16 `RealExportTests.test_short_files_and_untrimmed_compatible_sources` | Arithmetic: 0.02, 10, 1499.9, 1500 s remain one nominal segment. Real exports: 0.2/19 s WAV re-encode; 10 s AAC/M4A and MP3 copy unchanged. |
| ~61 minute | E15 `PlannerTests.test_default_61_minute_plan_and_full_contiguous_coverage`; E16 `RangeTests.test_61_minute_plan_overlap_and_coverage`; E16 `RealExportTests.test_real_61_minute_fixture_exports_three_playable_parts` | 3660 s plan; pauses around 1500/3000; real generated mono 8 kHz WAV with 1498–1502 and 2998–3002 s pauses, three playable covering outputs. Real test was among frozen skipped integrations. |
| Long timing regression | E14 `ProcessingTests.test_long_lecture_duration_tolerance_never_scales_with_length` | Mock 3691.787029 s source: exact duration passes; +1 s fails; tolerance remains 0.128 s at 16 kHz. |
| ~90 minute | E16 `RangeTests.test_near_90_minute_no_silence_keeps_final_source_end` | **5437 s (90 min 37 s), plan/range arithmetic only**, four parts, fallback boundaries, exact end coverage. No real 90-minute transcode fixture demonstrated. |
| Quiet / loud / silent / stereo | E14 `fixture`; `GainTests.test_quiet_loud_usable_and_peak_limited_inputs`; `GainTests.test_silence_and_below_gate_do_not_receive_boost`; `RealAudioTests.test_quiet_loud_silent_stereo_and_invalid_media` | 8 s 16 kHz modulated 440 Hz tone with leading/middle/trailing pauses. Amplitude/channel cases `(0.01,1)`, `(0.7,1)`, `(0,1)`, `(0.02,2)`. Assert boost vs unchanged skip and preserved pauses. |
| Existing usable lecture | E14 `ProcessingTests.test_real_lecture_levels_skip_gain_and_reencoding` | **Mock measured levels**, -27.7 LUFS / -1.39 dBTP; unchanged original, no derived encoding. Test name does not mean bundled real lecture audio. |
| No suitable silence | E15 `PlannerTests.test_fallbacks_ignore_tiny_and_outside_window_pauses`; `RealAudioTests.test_synthetic_detection_and_deterministic_planning` | Ignore 0.2 s/out-of-window pauses. Real scaled 61 s case has 5–7 s and 24.9–25.1 s quiet, target/window 25/20–27 s; exact 25/50 s fallback. |
| Ranking / long quiet | E15 `PlannerTests.test_ranking_nearest_then_longest_then_earliest_and_input_order`; `test_long_quiet_region_crossing_window_still_supplies_a_candidate` | Deterministic ties/order and full-interval/window-intersection midpoint semantics. |
| Stereo active channel | E15 `RealAudioTests.test_verified_boosted_source_and_stereo_active_channel` | A continuing active second channel prevents a quiet candidate; verified boosted source is used when applicable. |
| Overlap / source end / tiny tail | E16 `RangeTests.test_zero_overlap_short_final_and_no_negative_or_excess_ranges`; `test_invalid_or_gapped_plans_refused` | Durations 0.02, 10, 1500, 1500.1, 3002, 3660; overlap 0/5/60; capped endpoints and no gaps. Tiny tails permitted, not merged. |
| Sample cuts / paused stereo | E16 `RealExportTests.test_sample_boundaries_preserve_tones_pauses_and_stereo`; `test_boosted_aac_source_and_mp3_cuts` | Scaled 61 s stereo, quiet 24–26/49–51, target 25 s, 192 kb/s requested; quiet positions stay at source-relative local offsets. Derived AAC and multi-part MP3 sources re-encode. |
| Malformed media / metadata | E13 `ParsingTests.test_bad_json_structure_and_no_audio`; `ProbeTests.test_invalid_media_timeout_bad_json_and_execution_failure`; E14 `RealAudioTests.test_quiet_loud_silent_stereo_and_invalid_media` | Broken JSON, no audio, unknown codec selection, invalid numbers, timeout/tool failure and `not media` WAV bytes. Retain accepted original, refuse successful processing. |
| Integrity / partial failure | E14 timing/clipping/changed-original tests; E15 `AnalysisTests.test_source_changes_during_analysis_are_refused`; E16 stale/tampered-source, partial-output and output-mismatch tests | Refuse wrong timing, tampering, stale source identity and incomplete export; preserve sources. These are integrity assertions worth adapting without Recora server machinery. |

The scaled 61-second real fixtures are distinct from the generated 3660-second test. E21 explicitly warns that skips are not integration passes. Reuse semantic expectations and fixture generation ideas; no test harness, filesystem layout, server state model or fixture file is copied here.

## Conflicts, caveats and remaining ambiguity

### Code/tests versus documentation

| Observation | Evidence | Resolution for extraction |
| --- | --- | --- |
| Introductory README and scope say approximately 20–25 minute parts. | E18 introduction; E19 Responsibilities; E07/E15 | Actual search window is 20–27 minutes, target 25. E18's detailed Step 2.3 agrees with code. Export can add overlap; final remainder can be arbitrarily short. |
| Architecture workflow says probe then finalize the original. | E20 Audio processing workflow item 1; E01 `receive_lecture`; E09 `finalize_upload`; E13 failures | Actual originals/session are accepted and committed **before** probing; failed probe retains them. Use implementation/tests. |
| README broadly says peaks between -3 and -1 warn. | E18 normalization prose; E04 `_generate_boosted_copy` | Exact code warning is `peak > -2.9`, with rejection only at `peak > -1`. Use those comparisons. |
| Older PCM working-copy proposal appears as historical context. | E20 explicitly says AAC/M4A replaces it; E04/E06 | Current normalization and cut outputs are AAC/M4A. No PCM-working-copy candidate is extracted. |
| Checklist has 253 tests; final review has 254. | E21 | Different historical checkpoints, not evidence that integrations ran. Both record nine skips; final review is later freeze documentation. |

No contradiction was found between inspected core media code and its asserted main-policy tests. Core media tests were inspected, not rerun. Some broad architecture prose also calls ZIP/photo mapping deferred despite later implementation; that prose is outside this extraction's media contract.

### Unresolved or unqualified media behavior

1. **Tool/codec qualification:** no new FFmpeg/ffprobe version or real-device run was verified. Raw AAC and codecs beyond tested PCM/AAC/MP3 lack demonstrated end-to-end coverage here. Demuxer allowance is not a complete compatibility matrix.
2. **Missing Force equivalent:** Recora supplies no direct Force behavior; designing it for RecorAndro cannot be justified as extracted parity.
3. **Tiny tails:** the absence of a final-tail minimum/merge rule is definite. The usefulness of such outputs and any future Android change require a later product decision.
4. **Source-duration basis:** normalization allows a fixed lossy-codec timing delta, then planning/export use measured working-source duration. Exact original-versus-derived endpoint equivalence beyond that allowance is not established.
5. **Rate variants:** preservation/fallback rules are explicit, but inspected tests do not cover every permitted source rate or the full AAC rate set. Rate conversion defaults are left to FFmpeg; no resampler-quality option is specified.
6. **Encoded loudness/peak:** no assertion requires reaching target LUFS or expected gain, output true peak can be null under the measurement gate, and segment re-encodes are not re-measured for peak overshoot. These are validation limits, not guarantees of target loudness or a hard -3 dBTP delivered ceiling.
7. **Verification strength:** probe can accept duration without an independent estimate; the >1 s / >1% disagreement-warning rule is coarser than derived timing checks. Normalization/output decode checks do not prove source-sample equivalence. The derived processed-audio route lacks a per-request hash check.
8. **Long real media:** ~90 minutes is arithmetic coverage only; frozen real-tool integrations were skipped. Android runtime, storage, background behavior and hotspot coexistence are unmeasured and not addressed by this extraction.

## OUT OF SCOPE FOR PARITY

- FastAPI
- Remote upload
- Resumable network upload
- Cloudflare
- Windows runtime
- Windows autostart
- Server authentication
- Web UI
- Remote downloads
- Recora server-state architecture

Recora paths, route names, run identifiers and status strings above locate evidence and explain media acceptance/failure. They are not RecorAndro filesystem, code, deployment or state-machine prescriptions.

## Behavior mapping — candidates only, not frozen

| Behavior | Actual Recora implementation | RecorAndro baseline candidate | Evidence |
| --- | --- | --- | --- |
| Session media shape | Exactly one nonempty audio; optional images including none. | Preserve one-audio / zero-or-more-photo semantics. | E01/E02/E12 |
| Audio admission | `.m4a`, `.mp3`, `.wav`, `.aac`; declared MIME checks separate from probing. | Evaluate the same supported extensions with local-file validation; raw AAC qualification pending. | E01/E03/E12/E13 |
| Codec support | First recognized audio; no exhaustive input codec allowlist; PCM/AAC/MP3 tested. | Preserve explicit stream choice; qualify actual installed codecs. | E03/E13/E14/E16 |
| Optional photos | JPEG/PNG/HEIC/HEIF header/EXIF reads preserve bytes; errors per image. | Preserve optional/nonblocking media role; photo details remain later scope. | E01/E11/E17 |
| Duration | Stream duration, stream ticks/time base, then container; known disagreement blocks processing. | Evaluate the same precedence and transparent validation warnings. | E03/E13 |
| Creation time | Untrusted candidates, no automatic start/timeline shift. | Preserve separation of metadata candidates and media time. | E03/E10 |
| Measurement | Full-decode loudnorm input JSON, `I=-26:TP=-3:LRA=50`, discarded output. | Candidate measurement method; qualify Termux tools later. | E04/E14 |
| Auto decision | Eligible below -30 LUFS; target -26; cap +3; headroom under -3; floor 0.001; minimum 0.5 dB. | Evaluate as Auto candidate; no values frozen by this document. | E04/E14 |
| Skip | Original byte-identical, no derived encode. | Preserve byte-identical skip invariant. | E04/E14 |
| Force | No direct equivalent; rerun repeats decision. | Unresolved; define only in a later step if required. | E04/E08 |
| Normalized output | Constant double-precision volume gain, AAC-LC/M4A; 128 kb/s mono / 192 kb/s stereo. | Evaluate compact delivery policy without adopting Recora storage architecture. | E04/E14 |
| Rates/channels | Mono/stereo retained; supported source AAC rate else 48 kHz; admitted 7350–192000 Hz. | Candidate policy; rate/tool coverage pending. | E04/E06/E14/E16 |
| Normalization integrity | Fixed duration/start allowance, full output decode/measurement, format/nonempty checks, original/output hashes. | Preserve guarded publication; evaluate exact allowance later. | E04/E14 |
| True peak | Gain planned under -3; reject encoded peak >-1; warn >-2.9; no segment peak measurement. | Evaluate this two-stage safety policy; do not claim delivered hard -3 ceiling. | E04/E06/E14 |
| Quiet detection | -40 dBFS / 1 s defaults, combined channels, analysis-only PTS rebasing, complete log. | Evaluate same detector semantics and explicit parameters. | E03/E07/E15/E22 |
| Target/window | 1500 s target; 1200–1620 s after previous chosen boundary. | Provisional 25-minute target / 20–27-minute search candidate. | E05/E07/E15/E22 |
| Boundary ranking | Midpoint/intersection nearest ideal, longest full quiet interval, earliest deterministic tie. | Preserve deterministic selection as candidate behavior. | E05/E15 |
| Fallback/short file | Exact ideal fallback; <=target one part; tiny final remainder allowed. | Preserve transparent fallback and short-file validity; tail policy remains a later decision. | E05/E15/E16 |
| Overlap | 5 s default; extend nominal end only, cap at source end; unchanged following start. | Evaluate same overlap geometry and no-gap invariant. | E05/E06/E07/E16 |
| Cut exports | Independent sample-trim/re-encode from verified master; AAC/M4A; no packet stream-copy cuts. | Evaluate same sample boundaries and delivery encoding; Android performance unqualified. | E06/E16/E18/E20 |
| Copy exception | One full-length single-stream AAC/M4A or MP3 source copied byte-for-byte. | Evaluate full-length copy optimization without inventing cut stream-copy parity. | E06/E16 |
| Export integrity | Positive duration/nonempty/format, fixed tolerance, full decode, saved-plan/source checks, hashes; reuse rechecks size/hash. | Preserve verified-source/no-gap/failure invariants with independently designed local state. | E05/E06/E16 |
| Silence/master timeline | No silence removal/time compression; source coverage retained, wall time separate. | Preserve media invariant including zero-photo sessions. | E03–E06/E19 |
| Subprocess safety | Argument arrays, no shell/network inputs, selected stream, error-failing decode, timeouts, no overwrite. | Preserve platform-neutral safety behavior; no Windows runtime adoption. | E03/E04/E06/E13/E14 |
