# RecorAndro v0.1 media contract

Status: **frozen design requirements, 2026-10-08**. Android/Termux capability validation is pending; this document is not a statement that the audio engine exists or that the installed tools already satisfy these requirements.

Read with [SCOPE.md](C:/loxi/ReacorAndro/docs/SCOPE.md), [DEVICE_BASELINE.md](C:/loxi/ReacorAndro/docs/DEVICE_BASELINE.md), [RECORA_MEDIA_PARITY.md](C:/loxi/ReacorAndro/docs/RECORA_MEDIA_PARITY.md) and [BEHAVIOR_CONTRACT.md](C:/loxi/ReacorAndro/docs/BEHAVIOR_CONTRACT.md). The behavior contract owns mode decisions and boundary planning; this document owns admitted media, encoding and verification. The parity extraction remains a factual historical reference, not a competing contract.

The actual read-only Recora reference was reverified at `C:\loxi\Recora`, branch `main`, commit `9b886519ea623fa8bf0746f96ea512da18413bde`. Core implementation/test files checked for this freeze match that commit. Relevant evidence is `app/uploads.py`, `app/audio.py`, `app/config.py`, `app/normalization.py`, `app/segmentation.py`, `app/exports.py` and `tests/test_{normalization,segmentation,exports}.py`, identified precisely in the parity document (E01, E03–E07, E14–E16).

> Recora parity means media-processing behavior and invariants only. It does not imply code, filesystem, state-machine, deployment or architecture parity.

## A. Media input contract

Canonical session input is exactly **one audio file plus optional 0..N photos**. A zero-photo session is complete. Import preserves accepted original bytes, byte size and SHA-256; it never transcodes an input merely to import it. Any later normalization or canonical delivery encoding creates a separate derivative and does not redefine the original.

### Supported audio containers and extensions

Suffixes are case insensitive. Required v0.1 input demuxers are `mov`, `mp3`, `wav`, `aac`; the MOV family covers M4A's MP4-family container. Local file protocol only.

| Extension | Format family | Permitted specific MIME declarations, when supplied |
| --- | --- | --- |
| `.m4a` | MOV/MP4-family demuxer | `audio/mp4`, `audio/m4a`, `audio/x-m4a`, `video/mp4` |
| `.mp3` | MP3 demuxer | `audio/mpeg`, `audio/mp3`, `audio/x-mp3` |
| `.wav` | WAV demuxer | `audio/wav`, `audio/wave`, `audio/x-wav`, `audio/vnd.wave` |
| `.aac` | Raw AAC demuxer | `audio/aac`, `audio/x-aac` |

Missing MIME or `application/octet-stream` is an unverified declaration, not a reason to reject a supported suffix. Lowercase and trim declarations and ignore parameters after `;`, as in Recora. A different specific MIME is rejected. Android picker metadata never establishes actual codec/format support.

Both a supported extension and an allowed actual demuxer are required. Preserve Recora's distinction between suffix/MIME admission and content probing: do not infer the codec from the suffix or add a strict suffix-to-demuxer correspondence rule. A mismatch inside the permitted set is recorded diagnostically, not repaired by import transcoding. A playable FLAC, Ogg/Opus, WebM, playlist, extensionless file, `.mp4`, or any other unlisted input is rejected by v0.1 admission, even if an unrestricted ffprobe could read it. Renaming is not an import feature and cannot make a disallowed actual demuxer eligible.

### Codec handling

Required baseline decoding compatibility: **PCM S16LE in WAV, AAC in M4A/raw AAC, and MP3**. Raw AAC is a frozen support requirement with pending real-tool qualification, not a claim that Recora's inspected real fixtures covered it.

There is no exhaustive input codec allowlist. Another recognized codec in a permitted container is conditionally eligible only if the installed decoder can fully decode its selected stream without errors and all common duration/rate/channel checks pass. A codec name of `unknown`, a missing codec name, or a missing decoder is not supported. This policy does not promise every codec that can be named by ffprobe. No fallback install, external codec service, remote fetch, or import transcoding is allowed to rescue an unsupported input.

Select the **first recognized audio stream in ffprobe output order**, save its absolute stream index, and use that same index throughout processing. Do not choose by bitrate or stream disposition. Extra input streams are not processed; encoded derivatives map selected audio only and exclude video/subtitle/data, metadata and chapters. The full-length byte-copy exception requires exactly one input stream.

### Processing eligibility and rejection

Before normalization, segmentation analysis or delivery encoding, reject missing/multiple/empty audio, unsupported extension/MIME/demuxer, unsafe or unreadable local input, missing recognized audio/index/decoder, invalid required metadata, a known contradictory duration, source integrity mismatch, or unavailable required capabilities. A later decode error also fails the attempt; probing alone is not a successful media qualification. An already accepted original is retained on processing failure.

Require a positive finite duration of at least **0.000001 s**, a positive integer sample rate in **7350–192000 Hz**, and **one or two channels**. No automatic downmix of multichannel audio. Duration precedence is selected-stream duration, then selected-stream duration ticks times time base, then container duration. Other positive duration estimates differing by more than `max(1.0 s, selected_duration * 0.01)` cause processing refusal. Missing independent estimates remain an explicit warning rather than an invented value. Creation times and file mtime never shift or establish media-relative zero.

Known input byte size and SHA-256 must match the accepted original record at processing boundaries. Container-reported size is diagnostic and does not replace actual filesystem size. Root is not part of any eligibility requirement; the core must run from ordinary Termux user context even on the currently rooted baseline device.

### Optional photo admission

Retain Recora's optional photo extensions: **`.jpg`, `.jpeg`, `.png`, `.heic`, `.heif`**. Specific MIME declarations are `image/jpeg` for JPEG, `image/png` for PNG, `image/heic` or `image/heic-sequence` for HEIC, and `image/heif` or `image/heif-sequence` for HEIF. The same missing/generic-MIME rule applies. Unsupported declared photo types are not added to this allowlist. Accepted photo bytes are preserved; no photo conversion or OCR is required. Missing/malformed capture metadata is a per-photo diagnostic, not an audio prerequisite. Photo timing, header-reader implementation and associations cannot gate the audio capability validation or processing steps.

## B. Normalized output contract

These settings apply only when the behavior contract selects a useful positive gain. Auto skip, Force safe no-gain and Off do not create a normalized file.

| Property | Frozen requirement |
| --- | --- |
| Final basename | `normalized.m4a` in a new owned output location; no original/earlier-output overwrite |
| Container / muxer | M4A, explicit FFmpeg `-f ipod -movflags +faststart` |
| Codec / profile | Native `aac`, AAC-LC, `-profile:a aac_low` |
| Bitrate mode | Requested average bitrate via `-b:a`; **128000 bit/s mono**, **192000 bit/s stereo**; no quality-scale mode |
| Audio transform | `volume=<gain to three decimals>dB:precision=double`; no applied dynamic loudnorm, attenuation, compression, limiter, EQ, denoise or tempo change |
| Sample rate | Conditional preservation/conversion, as defined below |
| Channels | Preserve mono/stereo channel count; no forced mono, stereo upmix or multichannel downmix |
| Metadata | `-map_metadata -1 -map_chapters -1`; selected audio only |

Requested bitrate is not an exact measured bitrate or file-size guarantee. For an encode, preserve source rate if it is in this exact set:

```text
7350, 8000, 11025, 12000, 16000, 22050, 24000,
32000, 44100, 48000, 64000, 88200, 96000 Hz
```

Convert other admitted rates to **48000 Hz** without changing playback speed. Use the same rule for canonical part encoding. No Android-specific mono conversion or 16/24 kHz default is introduced. Byte-copy paths do not resample.

The normalized duration and output-stream start must satisfy:

```text
tolerance = max(0.05 s, 2048 / min(source_rate, output_rate))
abs(output_duration - original_duration) <= tolerance
abs(output_stream_start) <= tolerance
```

This is a fixed sample-rate/codec allowance, never a percentage of lecture length. Require nonempty size, positive duration, expected AAC codec/profile encoding configuration, expected rate and unchanged channels. Fully decode/measure the derivative with the frozen measurement filter in the behavior contract, verify its finite measured true peak, then recheck original integrity, hash the derivative and publish its final name. The gain decision targets -3 dBTP; encoded true peak **greater than -1 dBTP fails**, and **greater than -2.9 dBTP** produces an overshoot warning if otherwise accepted. Target LUFS is not an achieved-loudness guarantee.

Requiring a finite encoded true peak for a boosted copy intentionally closes Recora's documented null-peak acceptance gap. A malformed, inconsistent or unavailable peak measurement cannot establish the requested safety check; fail the derivative instead of accepting it. This adds no processing pipeline or further gain adjustment. Original/no-gain paths do not claim to repair or meet peak targets.

## C. Generated part and canonical single-output contract

Every processing result intended for packaging references **verified generated audio**, including a one-part result. Packaging does not point directly into original storage. For a one-part compatible source, create an independent byte copy; never a hardlink or alias to original bytes. This isolates packaging from the original while avoiding unnecessary encoding, following Recora's generated full-length copy behavior.

### Media format and copy exception

Cut parts and an encoded single full-length output use the exact M4A/AAC-LC/bitrate/rate/channel/metadata policy in B. Filenames are `part_01.m4a`, `part_02.m4a`, etc., with a one-based index padded to at least two digits. A one-part byte-copy MP3 uses **`part_01.mp3`**; its MP3 container/codec/rate/channels/bitrate/metadata are retained. A copied AAC/M4A uses `part_01.m4a` and retains its existing AAC profile; the AAC-LC requirement applies to new encodes.

The exception is allowed only when the requested range is the full selected working source, there is one generated part, the probe reports exactly one stream, and source codec/suffix is AAC/`.m4a` or MP3/`.mp3`. Otherwise encode selected audio as AAC-LC/M4A. A single WAV or raw AAC source is encoded for delivery, not for import. Multi-part exports always **decode, trim by samples and re-encode**; no FFmpeg packet stream-copy cuts or `-c copy` policy is adopted.

### Cut accuracy and source ranges

All cuts come independently from the same verified working master, never from a previous part. Use source sample counters with nearest-integer, ties-to-even rounding (Recora/Python `round` semantics):

```text
start_sample = round(global_start_seconds * source_rate)
end_sample = round(global_end_seconds * source_rate)
atrim=start_sample=<start_sample>:end_sample=<end_sample>,asetpts=PTS-STARTPTS
```

Start sample is inclusive; end sample is exclusive. Rounding of each endpoint is at most **0.5/source_rate seconds**. The same shared nominal boundary has the same rounded sample index in adjacent parts. Reject an empty rounded sample range. No fast packet seek, `-ss`/`-t` packet cut, silence deletion or concat of disjoint spans. This preserves predictable source positions instead of optimizing decode time at the expense of boundaries.

The behavior contract defines nominal boundaries `b_0 = 0 < ... < b_N = D`, where `D` is freshly verified working-source duration. Part `i` starts at `b_(i-1)` and ends at **`min(D, b_i + 5 s)`**. The following part begins at the unchanged `b_i`; overlap extends ends only. Nominal internal ownership intervals are half-open; final source endpoint belongs to the last interval. Exported time spans describe source coverage; the final logical end is `D`, although sample rounding and encoded measured duration have their documented allowances. Encoding tolerance must never be used to excuse a missing planned source interval.

Store original duration and working duration separately. If normalization was applied, its allowed timing delta does not reset source time or imply exact sample identity after lossy encoding; audio time remains relative to the original first decoded sample. Working `D` is the exact plan/export endpoint, consistent with Recora. Wall-clock tags and photo timing do not redefine it.

### Verification and failure requirements

Before export, verify source identity/index/hash/actual size, source duration against its processing record, and the exact approved plan. Nominal intervals must be ordered and contiguous, start at zero, end at `D`, have positive lengths and no gaps. Length/record consistency allowance is **0.000001 s**; shared endpoints themselves must match. There may be at most **10000 parts**, following Recora's plan-validation bound. Reject a stale or changed plan instead of silently detecting quiet again.

For every new output require nonempty bytes, positive probed duration, expected format/codec/rate/channel policy, and full error-free FFmpeg decoding. Encoded outputs use the same fixed tolerance as B for requested source span and output start near zero. Byte copies require exact source SHA-256, exact byte size and **zero duration tolerance**; existing source start tags are preserved and not subjected to encoded-start-zero validation.

Record nominal/exported starts and ends, requested/measured durations, source identity/hash/index, method (`byte_copy` or `decode_sample_trim_aac`), rate/channels, requested bitrate for encodes, actual size/SHA-256, verification results and overlaps. Measured part duration does not replace global source ranges. Re-encoded segments have full-decode/probe validation; no extra loudness or peak adjustment/measurement is required, matching Recora. Do not advertise a hard delivered -3 dBTP ceiling for every part.

Only a fully verified set is a completed export. On missing/changed input, decode/encode error, wrong format/timing, empty output or timeout, retain originals and earlier complete outputs and mark the attempt failed. Pending/partial derivatives cannot be reported as complete. Reuse requires matching plan/source/policy/modes and current file size/hash checks; changed facts get new owned output. File names specify media identity only; the complete on-device directory/state design is not frozen here.

## Integrity and tool execution

Originals remain immutable. Preserve all source timeline content including silence. Use exclusive new outputs and `-n`, argument arrays, `shell=False`, disconnected stdin/`-nostdin`, explicit stream mapping, file-only input protocol, `mov,mp3,wav,aac` demuxer allowlist, disabled MOV external data references and absolute external-track paths, and `-err_detect explode`/`-xerror`. Raw logs remain private and bounded when retained. Windows executable/autostart conventions are not Android requirements.

Freeze Recora's **30 s ffprobe timeout** and FFmpeg per-pass timeout:

```text
min(21600 s, max(120 s, ceil(working_duration_seconds * 2 + 60 s)))
```

Timeout is a failed attempt, not permission to accept a partial file. Root, server, network upload, Cloudflare, databases, web UI, OpenAI/Notion APIs, transcription, OCR and cloud sync are not dependencies.

## Pending after real-device measurement

### Required step 1.1 capability gate — before audio-engine implementation

Record the actual Termux source/version, Python, FFmpeg, ffprobe and ABI; do not install them automatically. Check capabilities in ordinary Termux context without relying on `su`. Version strings or successful `-version` alone do not pass this gate.

| Required capability | Evidence to record at step 1.1 |
| --- | --- |
| Input demuxers and protocol safety | Actual `mov`, `mp3`, `wav`, `aac` and local `file` support; functioning external-reference/protocol restrictions. |
| Required source decoding / probing | Actual PCM WAV, AAC M4A, raw AAC and MP3 fixtures; JSON selected-stream/duration/start/rate/channel fields; error rejection for malformed media. |
| Output muxer and encoder | `ipod` M4A muxer, native `aac` encoder with AAC-LC profile, bitrate settings and `+faststart`; verified playable output. |
| Loudness/gain filters | `loudnorm` input JSON with frozen `I/TP/LRA`, and `volume` with double precision; full-decode output measurement. |
| Quiet/sample filters | `silencedetect` combined-channel behavior, `asetpts` and sample-index `atrim`; complete log and retained pause positions. |
| Rates / channels | Actual preservation of required AAC rates for mono/stereo, and conditional conversion of an admitted unsupported encode rate to 48000 Hz; no unwanted downmix, speed change or timing loss. |
| Verification / safety options | Full decode, nonzero failures on decode errors, no-overwrite, fixed timing checks, correct copied-source hash/size; executable invocation from normal user context. |

If a required capability is absent or cannot be validated, **stop before audio-engine implementation**, record command/fixture/tool-version/error evidence, and propose only the smallest justified contract change. An installed version difference alone is not justification for changing inherited rates, bitrates, thresholds, formats or safety limits. These documents remain frozen until an explicit evidence-backed revision is made; no silent substitute is allowed.

After that gate, runtime/storage/thermal/background/hotspot measurements and real 61-/90-minute behavior still need qualification. Full-archive Lecture default, storage-reserve/budget values, per-profile archive choices, directory/UI integration and any measured Android mitigation remain pending as specified in the behavior contract. Pending implementation details do not relax the frozen media rules.

## Canonical media constants and decisions

| Constant / decision | Frozen value |
| --- | --- |
| Audio input suffixes / actual demuxers | `.m4a`, `.mp3`, `.wav`, `.aac` / `mov,mp3,wav,aac`; local `file` protocol only |
| Optional photo suffixes | `.jpg`, `.jpeg`, `.png`, `.heic`, `.heif`; byte-preserving, no required timing |
| Required baseline codecs | PCM S16LE WAV, AAC M4A/raw AAC, MP3; other recognized decodable codecs conditional within allowed containers |
| Original import | Byte-preserving; no import transcode |
| Source duration / rate / channels | Duration >=0.000001 s; rate 7350–192000 Hz; channels 1 or 2 |
| Duration disagreement rule | More than `max(1 s, selected_duration * 0.01)` refuses processing |
| Encoded format / profile | M4A / `ipod` / native `aac` / `aac_low` / `+faststart` |
| Requested bitrate | Mono 128000 bit/s; stereo 192000 bit/s; no quality-scale mode |
| Preserved encode rates | 7350, 8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000, 64000, 88200, 96000 Hz |
| Other admitted encode rates | Convert to 48000 Hz at unchanged playback speed |
| Channels / metadata for encodes | Preserve mono/stereo; selected audio only; metadata/chapters stripped |
| Filenames | `normalized.m4a` when gain applied; `part_<index padded to at least 2 digits>.m4a`; `.mp3` only for compatible one-part byte copy |
| Copy exception | One full-length, single-stream AAC/M4A or MP3; independent byte copy; no packet stream-copy cuts |
| Encoded duration/start tolerance | `max(0.05 s, 2048 / min(source_rate, output_rate))`; copies/skips: 0 s |
| Cut rounding / plan record allowance | Nearest sample, ties-to-even, <=0.5/source_rate s per endpoint; record length/source consistency 0.000001 s |
| Export nominal/global semantics | Unchanged shared boundaries; export end `min(D, nominal_end + 5 s)`; complete no-gap coverage |
| Maximum part count | 10000 |
| Boosted output peak verification | Finite measured true peak required; reject >-1 dBTP; warning >-2.9 dBTP |
| Probe / FFmpeg timeouts | 30 s / `min(21600, max(120, ceil(D*2+60)))` s per pass |
