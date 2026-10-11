# PART 1 media-behavior parity report

Review date: **2026-10-11**. Media parity classification: **PASS WITH INTENTIONAL DIVERGENCE**, for the evaluated scope below. This is not a blanket certification of every codec, device condition or Part 1 acceptance requirement.

The comparison excludes architecture, servers, filesystem-layout equivalence, state-machine equivalence, UI and deployment. Paths/status fields appear only to locate evidence or establish media success/failure. No implementation, test or frozen contract was changed; Recora was read only.

## Revisions and evidence method

- Frozen Recora: `C:\loxi\Recora`, reference branch `main`, **`9b886519ea623fa8bf0746f96ea512da18413bde`**.
- Current RecorAndro: `C:\loxi\ReacorAndro`, `main`, **`3cb337b19dbfee9bfeabe7980ff29d478a87f390`**, matching the local `origin/main` reference; working tree clean before review. No live remote update is claimed.
- Actual Recora core, configuration and relevant tests were read, not inferred from its documentation. Eleven examined files match the reference Git blobs after CRLF/LF normalization. Their exact current byte SHA-256 values and Git blob IDs are retained in [reference evidence][E0]. Recora's general worktree-status command was denied in this environment; no assertion of whole-reference-worktree cleanliness is made. The compared core files are revision-verified.
- Host execution used **Python 3.12.10**, **FFmpeg/ffprobe 9.0.2-full_build-www.gyan.dev**, the same executables for both projects. Tool byte hashes are in [E1]. These host executions are not Android executions.
- Recora media settings were read from `Settings`, `config.example.json` and the available local media configuration: **no local segmentation overrides**. Target 1500 s, window 1200–1620 s, quiet -40 dBFS/1 s, combined channels and overlap 5 s. Only review-owned output roots and common executable locations were supplied to the fixture adapter. [R5]

Evidence classes are kept separate:

| Class | Meaning |
| --- | --- |
| M — directly measured | Both actual media cores executed on input bytes with the same SHA-256. Actual probes, measurements, plans, exports, full decoding and independent file checks are recorded. |
| S — code/test-supported | Actual code and relevant assertions support the behavior; some pure functions were additionally executed on identical synthetic metadata/region lists. This is not an executed audio-file comparison. |
| D — contract-defined intentional divergence | An observed difference is explicitly required by the already frozen RecorAndro contracts. It is not a parity failure. |
| N — not evaluated / insufficient evidence | Required source/artifacts or execution evidence is unavailable. No measured PASS is claimed. |
| A — accepted Android history | Previously approved user-supplied device evidence reused from Steps 1.2–2.4; not a new device run or direct Recora comparison. |

Fourteen full-pipeline shared fixtures completed. For each, both managed originals and the input were independently SHA-256 checked before/after; input levels and common probe fields matched. **21 Recora and 20 RecorAndro generated parts** passed their actual core full-decode checks, followed by independent output size/hash/probe checks. Logical coverage/overlap was independently checked for all sets. Six additional exported-part pause checks on the 61-minute case passed. See [E1], [E2], [E3], [E5].

The thin Recora adapter created accepted media records from its actual `SessionWriter` byte-copy/hash functions, then called original `probe_audio`, `normalize_audio`, `analyze_segmentation` and `export_audio_parts`. It did not exercise Recora's upload/photo/UI finalization: that unrelated path imports Pillow, absent in this host interpreter. No functions were mocked or replaced in the compared media operations; no original code was copied into RecorAndro. The full Recora test suite was **not run**. Its relevant media test bodies were inspected; historical skipped integrations were not counted as passes.

Review inputs and raw results remain in ignored, local `data/`; the tables in this report retain the important measured facts even when that scratch evidence is not distributed. Fixture recipes and calls are in [main fixture harness](C:/loxi/ReacorAndro/data/part1-parity-run.py), [extra fixture harness](C:/loxi/ReacorAndro/data/part1-parity-extra.py), [rate fixture harness](C:/loxi/ReacorAndro/data/part1-parity-rate.py), [edge harness](C:/loxi/ReacorAndro/data/part1-parity-edges.py) and [independent checker](C:/loxi/ReacorAndro/data/part1-parity-check.py). Importing the reference used disabled bytecode writes; all review outputs were confined to RecorAndro scratch storage.

An initial long scratch-name rate-conversion attempt failed during pending metadata publication, before RecorAndro media processing. A shorter review-owned fixture path completed; no application change was made. This environmental harness failure is not presented as a media parity mismatch or a completed run. Successful evidence and full source hashes below identify the runs used.

## Exact common media rules and frozen planning exception

The following rules were checked against actual commands/parsers/planners and the frozen contracts, rather than inferred from equal output bytes:

- Probe: arguments with shell disabled/disconnected stdin, error verbosity, file-only protocol, demuxers `mov,mp3,wav,aac`, MOV external references disabled, the same selected-field JSON query and **30-second timeout**. The first audio stream with a nonmissing/non-unknown codec is selected in output order, retaining its absolute index and total stream count. Both numeric helpers reject booleans/nonfinite numbers and use the `2**53` upper bound; integer fields must be integral. RecorAndro additionally rejects duplicate JSON keys/invalid stream indices and enforces live output caps. Recora's parser checks the 1 MiB payload limit after subprocess capture; live bounded capture is not claimed for Recora. [R1], [A1], [T1], [U1]
- Duration: positive finite **>=0.000001 s**, precedence stream, ticks times positive rational time base, then container. Preserve available estimates; warn when fewer than two exist, and when any positive estimate differs by **more than max(1 s, chosen duration * 0.01)**. Both processing cores reject known contradictions. Tags and container size are informational, never timeline zero or filesystem integrity. [R1], [R2], [R4], [A1], [A2], [C1]
- Processing: **7350–192000 Hz**, mono/stereo only, recognized selected audio followed by actual decoder qualification. No silent channel conversion. FFmpeg uses local input restrictions, explicit absolute audio mapping, no video/subtitles/data, `-nostdin`, `-err_detect explode`, `-xerror` and no overwrite for generated media. Each pass uses **min(21600,max(120,ceil(D*2+60)))** seconds. Measurement is discarded; successful outputs are probed and fully decoded. RecorAndro's interruption/output bounding and before/after source checks strengthen the frozen safety invariant. These are code/test-supported safeguards, not cross-measured hostile-input or cancellation coverage. [R1], [R2], [R4], [A2], [A4], [C1], [U2], [U4]
- Encode: native AAC, **AAC-LC/M4A (`-f ipod`, `+faststart`)**, explicit **128000 mono / 192000 stereo bit/s**, metadata/chapters stripped and only selected audio mapped. Preserve source rate in **7350,8000,11025,12000,16000,22050,24000,32000,44100,48000,64000,88200,96000 Hz**; otherwise use **48000 Hz**, without changing speed. Compatible full-length one-stream AAC/`.m4a` or MP3/`.mp3` is byte-copied; every multi-part output is sample-trimmed and re-encoded, never packet-copy cut. [R2], [R4], [A2], [A4], [C1]
- Quiet planning: combined-channel **asetpts=PTS-STARTPTS,silencedetect=noise=-40dB:duration=1:mono=0**, target **1500 s**, normal window **[p+1200,p+1620]**. Full midpoint if inside search; otherwise qualifying intersection midpoint, retaining **0.00001 s** minimum-quiet allowance. Rank by ideal distance, longest full quiet interval, earliest candidate, then start/end. Continue relative to the chosen boundary; never remove silence. [R1], [R3], [R5], [A3], [C2]

Recora keeps cutting while remaining duration is greater than 1500 s, with no final minimum. RecorAndro's frozen exception fixes the count first: Auto one part at **D<=1620**, otherwise **ceil(D/1620)**; Force **max(2,ceil(D/1620))** at D>=1200, otherwise a valid single part with mode_fulfilled=false; Off one complete part. Each multi-part nominal length is **600–1620 s**. At a cut after p with m remaining parts, **F=[max(p+600,D-m*1620),min(p+1620,D-m*600)]**. Intersect with the normal window; use the p+1500 ideal clamped to that intersection. If empty, search F around **p+(D-p)/(m+1)**. Quiet ranking cannot override feasibility/count/coverage. This is the already frozen tiny-first/last-part improvement. [R3], [A3], [C2]

## Directly measured shared fixtures

Filenames beginning `short-usable` are historical fixture labels, not loudness claims: F01–F03 actually measured slightly below -30 LUFS and correctly received gain. F10 is the separately measured usable-level/Force case. All fourteen fixtures had zero photos.

### Input identity

| Fixture | Input | Bytes | Same input SHA-256 in both projects |
| --- | --- | --- | --- |
| F01 | Short near-gate WAV | 256044 | `1ce02442fb55ddf6e3a9131de94abb68400a8548bf786dc4c9abe6765106a573` |
| F02 | Short near-gate AAC/M4A | 25802 | `394c7c3e669519c581c2edda84877861aa81636089a0a6393c8036132d7484c2` |
| F03 | Short near-gate MP3 | 130220 | `042ae35546651547fd2a490d393b8f7e0efb018b69352638eedd00ea635e9378` |
| F04 | Low-level WAV | 256044 | `5072e5fe2202eeedc4c32425f90a921b5a45572d168fb5dd49fc6c38e229ad5b` |
| F05 | Silent WAV | 256044 | `190415015d40eef0cd797e1b59ffe00846b01873050b12d44b3a216de3faa2a9` |
| F06 | Already usable stereo WAV | 1411244 | `107ec29ea988f9ba175e1f545b189659b10b47f2589518c1352e0e6d8bc0c1e8` |
| F07 | 61-minute quiet-boundary WAV | 58560044 | `a19933b7f51561a23ce2c958ce55da70b033126e25c4d7c6862f00fff8e61241` |
| F08 | 90-minute no-silence WAV | 86992044 | `c4cf041c714eb0788db016c153837c8c398a186fda9a12b2d9c282e708c789bf` |
| F09 | 53-minute tiny-tail WAV | 50880044 | `eb2102025334a8fb8420392f1437403bb6cd9a9d411f001db667ebef06725b6a` |
| F10 | Usable -27.21 LUFS WAV | 256044 | `6bab8f308bce1169f6bb8ec74f0b536b4e82add01588598f44a02a3664c2a20e` |
| F11 | Usable continuous WAV | 256044 | `44f1fcbb13a3620f856c80ab1b1fb7f489672b75407b9a3d3ef62add99f31344` |
| F12 | Compatible original AAC/M4A | 51616 | `a679561e1fdbad3f9f37f12210341cccd3d002ca315ba42c0e1a77687ce41b9f` |
| F13 | Compatible original MP3 | 130220 | `36c3cad0badd7b94504223d43cba22c154b939d0d76cf3ddba4350ab14c9894a` |
| F14 | 12345 Hz stereo WAV | 395084 | `1cdde63f80cb9641c5e4942560c344a39c6cb4abe0c3d2720ff9a35450f5f8c5` |

Each listed hash is the same in the input file and both accepted managed originals. No Android lecture hash is substituted with one of these synthetic hashes. [E1], [E2], [E3], [E5]

### Probe results — actual tools on identical source bytes

| Fixture | Recora summary | RecorAndro summary |
| --- | --- | --- |
| F01 | wav; pcm_s16le; 8.0 s (stream); 16000 Hz/1 ch; index 0, total 1 | wav; pcm_s16le; 8.0 s (stream); 16000 Hz/1 ch; index 0, total 1 |
| F02 | mov,mp4,m4a,3gp,3g2,mj2; aac; 8.0 s (stream); 16000 Hz/1 ch; index 0, total 1 | mov,mp4,m4a,3gp,3g2,mj2; aac; 8.0 s (stream); 16000 Hz/1 ch; index 0, total 1 |
| F03 | mp3; mp3; 8.0 s (stream); 16000 Hz/1 ch; index 0, total 1 | mp3; mp3; 8.0 s (stream); 16000 Hz/1 ch; index 0, total 1 |
| F04 | wav; pcm_s16le; 8.0 s (stream); 16000 Hz/1 ch; index 0, total 1 | wav; pcm_s16le; 8.0 s (stream); 16000 Hz/1 ch; index 0, total 1 |
| F05 | wav; pcm_s16le; 8.0 s (stream); 16000 Hz/1 ch; index 0, total 1 | wav; pcm_s16le; 8.0 s (stream); 16000 Hz/1 ch; index 0, total 1 |
| F06 | wav; pcm_s16le; 8.0 s (stream); 44100 Hz/2 ch; index 0, total 1 | wav; pcm_s16le; 8.0 s (stream); 44100 Hz/2 ch; index 0, total 1 |
| F07 | wav; pcm_s16le; 3660.0 s (stream); 8000 Hz/1 ch; index 0, total 1 | wav; pcm_s16le; 3660.0 s (stream); 8000 Hz/1 ch; index 0, total 1 |
| F08 | wav; pcm_s16le; 5437.0 s (stream); 8000 Hz/1 ch; index 0, total 1 | wav; pcm_s16le; 5437.0 s (stream); 8000 Hz/1 ch; index 0, total 1 |
| F09 | wav; pcm_s16le; 3180.0 s (stream); 8000 Hz/1 ch; index 0, total 1 | wav; pcm_s16le; 3180.0 s (stream); 8000 Hz/1 ch; index 0, total 1 |
| F10 | wav; pcm_s16le; 8.0 s (stream); 16000 Hz/1 ch; index 0, total 1 | wav; pcm_s16le; 8.0 s (stream); 16000 Hz/1 ch; index 0, total 1 |
| F11 | wav; pcm_s16le; 8.0 s (stream); 16000 Hz/1 ch; index 0, total 1 | wav; pcm_s16le; 8.0 s (stream); 16000 Hz/1 ch; index 0, total 1 |
| F12 | mov,mp4,m4a,3gp,3g2,mj2; aac; 8.0 s (stream); 16000 Hz/1 ch; index 0, total 1 | mov,mp4,m4a,3gp,3g2,mj2; aac; 8.0 s (stream); 16000 Hz/1 ch; index 0, total 1 |
| F13 | mp3; mp3; 8.0 s (stream); 16000 Hz/1 ch; index 0, total 1 | mp3; mp3; 8.0 s (stream); 16000 Hz/1 ch; index 0, total 1 |
| F14 | wav; pcm_s16le; 8.0 s (stream); 12345 Hz/2 ch; index 0, total 1 | wav; pcm_s16le; 8.0 s (stream); 12345 Hz/2 ch; index 0, total 1 |

`index` is the selected absolute stream index; `total` includes every stream. Selected-stream duration wins over ticks/time base, then container duration. The table records each actual selected provenance; AAC/MP3 streams were selected from their actual probe results, not suffix guesses. Both cores preserved available estimates and untrusted creation-time treatment. Probe success alone was not used to certify decoding. [R1], [A1], [E1], [E2], [E3]

### Normalization decisions and parameters

Integrated loudness/true peak below are LUFS/dBTP and were equal between projects. Recora's explicit normalization operation is compared with RecorAndro Auto, not with an invented Recora Force mode.

| Fixture | Measured INPUT I / P (both) | Recora decision/gain | RecorAndro Auto decision/gain | Working source R / A | Parameter parity |
| --- | --- | --- | --- | --- | --- |
| F01 | -30.31 / -23.1 | low_level_safe_boost; 3.0 dB | low_level_safe_boost; 3.0 dB | normalized / normalized | P1 identical |
| F02 | -30.32 / -23.08 | low_level_safe_boost; 3.0 dB | low_level_safe_boost; 3.0 dB | normalized / normalized | P1 identical |
| F03 | -30.75 / -23.54 | low_level_safe_boost; 3.0 dB | low_level_safe_boost; 3.0 dB | normalized / normalized | P1 identical |
| F04 | -47.21 / -39.99 | low_level_safe_boost; 3.0 dB | low_level_safe_boost; 3.0 dB | normalized / normalized | P1 identical |
| F05 | below gate (-inf) / below gate (-inf) | below_measurement_gate; 0.0 dB | below_measurement_gate; 0.0 dB | original / original | P1 identical |
| F06 | -11.57 / -10.46 | already_usable_level; 0.0 dB | auto_already_usable_level; 0.0 dB | original / original | P1 identical |
| F07 | -14.05 / -10.29 | already_usable_level; 0.0 dB | auto_already_usable_level; 0.0 dB | original / original | P1 identical |
| F08 | -14.05 / -10.29 | already_usable_level; 0.0 dB | auto_already_usable_level; 0.0 dB | original / original | P1 identical |
| F09 | -14.05 / -10.29 | already_usable_level; 0.0 dB | auto_already_usable_level; 0.0 dB | original / original | P1 identical |
| F10 | -27.21 / -20.0 | already_usable_level; 0.0 dB | auto_already_usable_level; 0.0 dB | original / original | P1 identical |
| F11 | -14.15 / -10.46 | already_usable_level; 0.0 dB | auto_already_usable_level; 0.0 dB | original / original | P1 identical |
| F12 | -14.15 / -9.69 | already_usable_level; 0.0 dB | auto_already_usable_level; 0.0 dB | original / original | P1 identical |
| F13 | -14.65 / -10.9 | already_usable_level; 0.0 dB | auto_already_usable_level; 0.0 dB | original / original | P1 identical |
| F14 | -11.15 / -10.45 | already_usable_level; 0.0 dB | auto_already_usable_level; 0.0 dB | original / original | P1 identical |

**P1, identical for every evaluated Auto comparison:** full selected-stream decoding with discarded `loudnorm=I=-26:TP=-3:LRA=50:print_format=json` output; read INPUT measurements; eligible only below -30 LUFS; target -26 LUFS; positive gain <=3 dB, headroom below -3 dBTP, floor to 0.001 dB, then minimum useful gain 0.5 dB. No attenuation. Applied transform is only `volume=<gain to 3 decimals>dB:precision=double`. No-gain decisions retain original bytes and create no normalized artifact. Requested mono/stereo bitrates are 128000/192000 bit/s; channel/rate, metadata and encoding policies match. [R2], [A2], [T2], [U2]

F01–F04 received +3.000 dB in both cores; their measured encoded true peaks were respectively -20.07, -20.08, -20.53 and -36.94 dBTP in both, with verified duration/start/full decoding. A delivered -26 LUFS or hard -3 dBTP ceiling is not claimed. F05 had valid below-gate input and no boost. [E1]

F10 measured **-27.21 LUFS/-20 dBTP**: Recora's existing operation and RecorAndro Auto both skipped; a separate actual RecorAndro **Force applied +1.210 dB** from the original. Actual Off then succeeded with zero gain, `normalization_off`, no loudness measurement and no derivative. Recora has no equivalent Force/Off enum; those are **contract-defined intentional extensions**, not measured same-mode parity. The frozen behavior contract already authorizes them. [C2], [R2], [A2], [E2]

### Segment counts, boundaries, overlap and source end

Boundaries are internal nominal global timestamps, not overlap-expanded endpoints. All successful sets independently verified no gaps and first start zero. Single-part overlap is zero. Multi-part overlap is five seconds extending the preceding end only; the next nominal start is unchanged. Exact global source-end equality is separate from encoded local duration tolerance.

| Fixture | Count R / A | Internal boundaries R / A (s) | Overlap R / A | Final global end R / A (s) | Classification |
| --- | --- | --- | --- | --- | --- |
| F01 | 1 / 1 | [] / [] | 0 / 0 | 8.0 / 8.0 | PASS (measured semantics) |
| F02 | 1 / 1 | [] / [] | 0 / 0 | 8.0 / 8.0 | PASS (measured semantics) |
| F03 | 1 / 1 | [] / [] | 0 / 0 | 8.0 / 8.0 | PASS (measured semantics) |
| F04 | 1 / 1 | [] / [] | 0 / 0 | 8.0 / 8.0 | PASS (measured semantics) |
| F05 | 1 / 1 | [] / [] | 0 / 0 | 8.0 / 8.0 | PASS (measured semantics) |
| F06 | 1 / 1 | [] / [] | 0 / 0 | 8.0 / 8.0 | PASS (measured semantics) |
| F07 | 3 / 3 | [1500.0000625, 3000.0000625000002] / [1500.0000625, 3000.0000625] | 5 s / 5 s | 3660.0 / 3660.0 | PASS (measured semantics) |
| F08 | 4 / 4 | [1500.0, 3000.0, 4500.0] / [1500.0, 3000.0, 4500.0] | 5 s / 5 s | 5437.0 / 5437.0 | PASS (measured semantics) |
| F09 | 3 / 2 | [1500.0, 3000.0] / [1560.0] | 5 s / 5 s | 3180.0 / 3180.0 | **intentional behavioral divergence** |
| F10 | 1 / 1 | [] / [] | 0 / 0 | 8.0 / 8.0 | PASS (measured semantics) |
| F11 | 1 / 1 | [] / [] | 0 / 0 | 8.0 / 8.0 | PASS (measured semantics) |
| F12 | 1 / 1 | [] / [] | 0 / 0 | 8.0 / 8.0 | PASS (measured semantics) |
| F13 | 1 / 1 | [] / [] | 0 / 0 | 8.0 / 8.0 | PASS (measured semantics) |
| F14 | 1 / 1 | [] / [] | 0 / 0 | 8.0 / 8.0 | PASS (measured semantics) |

### Exported ranges and actual media

Ranges and local durations are **Recora / RecorAndro**. Media listed was independently probed in both and matched; AAC profile was independently read as **LC**. Requested bitrate is 128000 mono/192000 stereo for encodes; measured bitrate and size are not exact-target assertions. An MP3 byte copy preserves its own codec/bitrate/metadata. [R4], [A4], [E5]

| Fixture | Recora global export ranges (s) | RecorAndro global export ranges (s) | Measured local durations R / A (s) | Verified media/method (both) |
| --- | --- | --- | --- | --- |
| F01 | [0.0, 8.0] | [0.0, 8.0] | 8.0 / 8.0 | aac/M4A (LC); 16000 Hz/1 ch; byte_copy |
| F02 | [0.0, 8.0] | [0.0, 8.0] | 8.0 / 8.0 | aac/M4A (LC); 16000 Hz/1 ch; byte_copy |
| F03 | [0.0, 8.0] | [0.0, 8.0] | 8.0 / 8.0 | aac/M4A (LC); 16000 Hz/1 ch; byte_copy |
| F04 | [0.0, 8.0] | [0.0, 8.0] | 8.0 / 8.0 | aac/M4A (LC); 16000 Hz/1 ch; byte_copy |
| F05 | [0.0, 8.0] | [0.0, 8.0] | 8.0 / 8.0 | aac/M4A (LC); 16000 Hz/1 ch; decode_sample_trim_aac |
| F06 | [0.0, 8.0] | [0.0, 8.0] | 8.0 / 8.0 | aac/M4A (LC); 44100 Hz/2 ch; decode_sample_trim_aac |
| F07 | [0.0, 1505.0000625]; [1500.0000625, 3005.0000625000002]; [3000.0000625000002, 3660.0] | [0.0, 1505.0000625]; [1500.0000625, 3005.0000625]; [3000.0000625, 3660.0] | 1505.0/1505.000125/659.999875 / 1505.0/1505.0/660.0 | aac/M4A (LC); 8000 Hz/1 ch; decode_sample_trim_aac |
| F08 | [0.0, 1505.0]; [1500.0, 3005.0]; [3000.0, 4505.0]; [4500.0, 5437.0] | [0.0, 1505.0]; [1500.0, 3005.0]; [3000.0, 4505.0]; [4500.0, 5437.0] | 1505.0/1505.0/1505.0/937.0 / 1505.0/1505.0/1505.0/937.0 | aac/M4A (LC); 8000 Hz/1 ch; decode_sample_trim_aac |
| F09 | [0.0, 1505.0]; [1500.0, 3005.0]; [3000.0, 3180.0] | [0.0, 1565.0]; [1560.0, 3180.0] | 1505.0/1505.0/180.0 / 1565.0/1620.0 | aac/M4A (LC); 8000 Hz/1 ch; decode_sample_trim_aac |
| F10 | [0.0, 8.0] | [0.0, 8.0] | 8.0 / 8.0 | aac/M4A (LC); 16000 Hz/1 ch; decode_sample_trim_aac |
| F11 | [0.0, 8.0] | [0.0, 8.0] | 8.0 / 8.0 | aac/M4A (LC); 16000 Hz/1 ch; decode_sample_trim_aac |
| F12 | [0.0, 8.0] | [0.0, 8.0] | 8.0 / 8.0 | aac/M4A (LC); 16000 Hz/1 ch; byte_copy |
| F13 | [0.0, 8.0] | [0.0, 8.0] | 8.0 / 8.0 | mp3/MP3; 16000 Hz/1 ch; byte_copy |
| F14 | [0.0, 8.0] | [0.0, 8.0] | 8.0 / 8.0 | aac/M4A (LC); 48000 Hz/2 ch; decode_sample_trim_aac |

F01–F04 export independent copies of their verified normalized AAC masters, not a second gain pass. F12/F13 copy their compatible original AAC/M4A or MP3 bytes, matching source SHA-256 and size exactly with zero duration tolerance. F06 preserves 44100 Hz stereo, requesting 192000 bit/s. F14 preserves stereo and converts the admitted 12345 Hz rate to 48000 Hz, requesting 192000 bit/s. WAV single-part outputs are canonical encodes, not references to original storage. [E1], [E2], [E3], [C1]

### 61-minute numerical detail and timeline preservation

The original input and both original hashes were identical for F07. Both detectors reported quiet intervals **[1498,1502.000125]** and **[2998,3002.000125]**; both selected those full-interval midpoints with `quiet_region`, giving three useful nominal parts.

Recora's second midpoint is `3000.0000625000002`; RecorAndro's is `3000.0000625`, a **2.2737367544323206e-13-second** representation difference. At 8000 Hz, multiplication falls on opposite sides of a half-sample tie, so Recora rounds that start/end counter one sample higher. Both use exactly Python `round(global_seconds*source_rate)`; RecorAndro's Decimal feasibility arithmetic avoids binary useful-bound violations. There is no different candidate/interval choice. The report does **not** claim exact boundary-string, sample or output-byte identity. Both follow the same frozen nearest/ties-to-even rule, <=0.5/source_rate endpoint allowance and 0.256 s encoded tolerance. Their overlaps remain five seconds and their source coverage is complete. [R3], [R4], [A3], [A4], [C1], [E1]

Independent exported-audio quiet detection checked all three parts from each project: pauses survived at their expected local positions after subtracting the global start, within the frozen 0.256 s tolerance. These six checks are automated waveform-level pause checks, not manual listening. They support unchanged timeline/silence semantics beyond merely trusting successful process exits. [E5]

### Tiny-tail finding

F09 (3180 s, no qualifying quiet interval) is an **intentional behavioral divergence**:

- Recora: 3 nominal lengths **1500/1500/180**; boundaries 1500 and 3000.
- RecorAndro: 2 nominal lengths **1560/1620**; boundary 1560, `fallback_feasible_target`.
- Counts are fixed before quiet selection in RecorAndro; its two-part feasibility interval forces the first boundary into [1560,1620]. Coverage and the 600–1620 s useful-part structure take priority over the nominal 1500 s target.
- Both delivered full end coverage with the same end-only overlap convention and AAC-LC/M4A policy. RecorAndro's two parts are not missing source content. This is not a parity failure. [R3], [A3], [C2], [T3], [U3], [E1]

## Direct edge fixtures and code-supported comparisons

| Fixture | Input | Bytes | Same SHA-256 | Probed duration |
| --- | --- | --- | --- | --- |
| F15 | raw.aac | 50849 | `5516d46f32f916989cf533b9b4ad594d764c3b0266bf12745bd3fbba4962b149` | 8.075917 s |
| F16 | bad.wav | 41 | `cac6ef4e4b7efc951ab19da6c625c1906b3380812c76ebfaa3671c4a81325ae9` | unavailable |

F15 (raw AAC) directly probed the same bytes in both, with **8.075917 s**, AAC, 16000 Hz mono, index 0/one stream. Recora's actual normalization decoded/measured **-14.16 LUFS/-9.61 dBTP**, then skipped with `already_usable_level`. RecorAndro preserved the raw estimate and `raw_aac_duration_unverified`, then rejected normalization with that code before measurement. Known Android raw AAC heuristic-duration uncertainty is explicitly recorded in the accepted Step 1.1/2.1 evidence; apparently agreeing metadata estimates do not independently establish safe raw timing. This is a **contract-defined intentional duration-safety divergence**, supported by the frozen rule rejecting untrusted processing cases and accepted raw-AAC inspection policy. No duration correction is invented. Segmentation, overlap, source-end export and output codec for F15 are **N: not evaluated**, not fabricated one-part success. [C1], [A1], [A2], [U1], [E4], [STEP_1_1_REPORT.md]

F16 directly failed ffprobe in both projects, retained the accepted original bytes/hash, and produced no media output. Duration, normalization, count, boundaries, overlap, source end and output format are **N/not applicable after failed probe**; this is measured safe-rejection parity, not a successful media fixture. [R1], [A1], [E4]

### Executed pure-function policy checks — S, not audio measurement

Identical validated loudnorm INPUT JSON was passed to both actual gain functions. Auto gain results matched at -30 (0 dB), -30.001 (3 dB), -28 (0 dB), at target -26 (0 dB), 0.49 dB headroom (0 dB), exactly 0.5 dB useful gain, downward 0.001 flooring, possible clipping (0 dB), and below gate (0 dB). Force's -28/-10 example returned +2 dB only in RecorAndro. [R2], [A2], [T2], [U2], [E1] (`policy_cases`)

Both actual parsers also executed on identical **synthetic ffprobe JSON**, skipping a video stream and unknown-codec audio to select absolute index **3 of 3 streams**. Stream, tick/time-base and container duration precedence, untrusted creation_time and a 17-versus-20 s disagreement were exercised. Both reported the disagreement; RecorAndro additionally stored a processing blocker as required. No file/tool probe was run for these JSON cases, so these are S rather than M. [R1], [A1], [T1], [U1], [E4] (`synthetic_probe_cases`)

Both actual planners were called with identical logical durations and region lists:

| Input (not an audio-file fixture) | Recora count / nominal lengths | RecorAndro Auto | Classification |
| --- | --- | --- | --- |
| 1500.1 s, no quiet | 2; 1500/0.1 | 1; 1500.1 | D: intentional behavioral divergence, no tiny tail |
| 1620 s, no quiet | 2; 1500/120 | 1; 1620 | D: exact frozen Auto cutoff |
| 1620.1 s, no quiet | 2; 1500/120.1 | 2; 810.05/810.05 | D: useful-part redistribution |
| 1200 s | 1 | Auto 1; Force 2 x 600 | D: Force extension; no Recora Force equivalent |
| 1199.9 s | 1 | Force 1, mode_fulfilled=false | D: valid useful-part infeasibility result |
| 4000 s, quiet near 1520/3020 | 3; cuts 1520/3020 | Same | S: midpoint/next-relative-target semantics |
| 3660 s, all quiet | 3; cuts 1410/2820 | Same | S: long-interval/window intersection |
| 3660 s, equal-distance/equal-length candidates | First cut 1490 | Same | S: deterministic earliest tie |

No input file/hash exists for these metadata-only cases; their entire input region lists and results are recorded in [E1] (`planning_cases`). They are not substitutes for the measured long fixtures. Quiet ranking retains nearest ideal, longest full quiet region, then earliest timestamp/start/end; RecorAndro restricts search to useful-part feasibility first. Auto `ceil(D/1620)`, Force `max(2,ceil(D/1620))` for D>=1200, and Off one complete part are the frozen deliberate additions. [R3], [R5], [A3], [C2], [T3], [U3]

### Safety/integrity equivalence and known tightening

| Media invariant | Evidence / classification |
| --- | --- |
| Measurement is full selected-stream decode; INPUT values only; delivered transform constant volume | M on shared short/long sources, S from original commands and gain tests. [R2], [A2], [T2], [U2], [E1], [E2], [E3] |
| Planned peak -3; reject encoded peak >-1, warn >-2.9 | Same numeric limits. RecorAndro additionally requires a finite encoded peak; Recora's below-gate null output peak can evade finite comparisons. **Previously frozen intentional safety divergence**, not newly accepted here. Finite successful fixtures were measured; null-peak rejection is S, not an actual altered-audio run. [R2 line 236](C:/loxi/Recora/app/normalization.py:236), [A2 line 308](C:/loxi/ReacorAndro/recorandro/normalization.py:308), [C1], [C2], [U2 line 164](C:/loxi/ReacorAndro/tests/test_normalization.py:164) |
| Codec/container/bitrate/rate/channels | M: AAC-LC/M4A, ipod, faststart, native AAC, mono/stereo and fallback rate cases; same exact rate preservation set in code. Not every admitted rate/conditional codec was cross-measured. [R2], [R4], [A2], [A4], [C1], [E1], [E2], [E3] |
| Timeline/pause preservation | No silence-removal/tempo/denoise/compression filters; global nominal endpoints preserved, only local export PTS rebased. M coverage and six pause checks; S command/test assertions. [R3], [R4], [A3], [A4], [T4], [U4], [E5] |
| Fixed timing, never lecture-percentage tolerance | M for 3660/5437 s exports; S negative duration/start tests. Encodes max(0.05,2048/min(rates)); copies zero. [R2 line 236](C:/loxi/Recora/app/normalization.py:236), [R4], [A2 line 292](C:/loxi/ReacorAndro/recorandro/normalization.py:292), [A4], [C1], [T2 line 164](C:/loxi/Recora/tests/test_normalization.py:164), [U2 line 139](C:/loxi/ReacorAndro/tests/test_normalization.py:139), [U4 line 103](C:/loxi/ReacorAndro/tests/test_exports.py:103) |
| Sources/outputs and incomplete media | M input/original/output hash and size checks; M malformed-media preservation. S tests refuse source tampering, bad timing, empty/undecodable output and incomplete sets. RecorAndro enforces accepted byte size and identity plus SHA-256, including after failures; Recora's normalizer primarily checks original SHA-256. This strengthening is required by the frozen media-integrity contract, not a different audio transform. [R2], [R4], [A1 line 322](C:/loxi/ReacorAndro/recorandro/inspection.py:322), [A4], [C1], [T2 line 192](C:/loxi/Recora/tests/test_normalization.py:192), [T4 line 232](C:/loxi/Recora/tests/test_exports.py:232), [U1], [U4] |
| Reused output qualification | Recora reuse rechecks saved facts/size/hash; RecorAndro also re-probes/full-decodes retained audio. Required original-preservation and complete-set invariants remain; no reuse-only media output differences asserted. S; reuse behavior from current passed tests, not a new shared reuse fixture. [R4 line 127](C:/loxi/Recora/app/exports.py:127), [A4 line 287](C:/loxi/ReacorAndro/recorandro/exports.py:287), [U4 line 340](C:/loxi/ReacorAndro/tests/test_exports.py:340) |
| Untrusted optional metadata / numeric safety | Same semantic required fields, finite positive duration, integer rate/index and first-recognized stream. RecorAndro is stricter about malformed structures/optional diagnostics; optional threshold may be null. No changed gain/duration inference follows from optional tags. Malformed JSON/numbers are S tests, malformed actual bytes are M. [R1], [R2], [A1], [A2], [T1], [U1], [U2] |

The allowed intentional differences above are already documented in the frozen contracts or the previously accepted raw-AAC safety qualification. This report creates no new exception, tolerance, mode or codec policy. No unexplained media-policy mismatch requiring a fix was identified within the measured fixtures and inspected common rules. **Unexecuted comparisons remain S or N.**

## Existing real Android lecture — accepted evidence audit

This is **A**, not M between both projects. Reuse of the previously accepted evidence avoids re-import or expensive processing of the lecture. The real Android original/output bytes, literal digest values and original device result JSON are not available in this local review. Identical real-lecture bytes in both projects are therefore **not established**, and no measured Recora decision is invented for that lecture. In particular, Recora's test named `test_real_lecture_levels_skip_gain_and_reencoding` uses mocked -27.7/-1.39 levels; those are **not** claimed as the Android lecture measurements. [T2 line 138](C:/loxi/Recora/tests/test_normalization.py:138)

| Stage | Accepted evidence | Source |
| --- | --- | --- |
| Baseline / qualification | Redmi Note 10 Pro, Android 12/MIUI V13.0.7.0.SKFTRXM; rooted device but ordinary non-root Termux F-Droid 0.118.3, Python 3.14.6, FFmpeg/ffprobe 8.1.3, arm64; Step 1.1 12 foundation/41 capability checks | [DEVICE_BASELINE.md], [STEP_1_1_REPORT.md] |
| 1.2 immutable import | 47/47 Android tests; source/managed original 44,941,318 bytes, SHA-256 equality, preflight allow, visual_count=0, empty temporary directory | [SESSION_IMPORT.md:326] |
| 2.1 probe | Existing session `d0c39956c17943299dd17e67bf6d1d68`; 84/84 tests; 3691.787029 s, AAC/M4A/MOV, 44100 Hz mono, index 0/1 stream, 96000 bit/s; three estimates agree and user confirmed duration; original integrity before/after; no warnings/errors | [SESSION_INSPECTION.md:158] |
| 2.2 normalization | 125/125 tests/compilation PASS; real Auto completed with auto_already_usable_level, gain 0, original selected, no derivative/encoding/errors/warnings; original size/hash independently unchanged. Separate quiet Auto +3 and usable Force +1.87/Off fixture acceptance | [SESSION_NORMALIZATION.md:250] |
| 2.3 plan | 170/170 tests/compilation PASS; Auto and Force 3 nominal lengths 1500/1500/691.787029; Off one full range; zero qualifying quiet intervals, deterministic fallback_target cuts 1500/3000, repeat identical; complete end coverage | [SESSION_SEGMENTATION.md:175] |
| 2.4 actual exports | 203/203 Android tests/compilation PASS; 3 verified AAC-LC/M4A local durations 1505/1505/691.787007; five-second overlap/no gaps/complete source end; independent size/SHA-256 checks on all three outputs and original | [SESSION_EXPORT.md:214] |

For the accepted plan, exported global ranges are **[0,1505]**, **[1500,3005]**, **[3000,3691.787029]**. Shared contexts are [1500,1505] and [3000,3005]; final logical end stays 3691.787029. The last measured local duration differs by **0.000022 s**, within the frozen 0.05 s tolerance at 44100 Hz. Zero photos is an accepted complete case; no recording start was inferred from tags. [C1], [C2], accepted stage references above

**Manual listening was explicitly waived. It did not PASS.** No numeric lecture INPUT LUFS/true peak, literal original/output SHA-256 strings, measured output bitrate/size values, tested device Git revision, or new device run is invented. Expected/enforced encode settings (44100 Hz mono, requested 128000 bit/s) follow the source and frozen policy; their raw device metadata was not independently inspected here.

Additional user-reported Android integrity checks returned **ALL_PASS=True**. Together with the accepted Steps 1.2–2.4 results for the same lecture, this evidence supports acceptance item 7 PASS. This is accepted user-reported device evidence, not a new independent device execution by this reviewer. Device Git metadata is unavailable because the Android checkout was deployed through ZIP files; no device commit identity is inferred from the host revision.

## PART 1 Final Acceptance Gate — separate audit

Authority: the external **user-defined Step 2.5 checklist supplied in this review**, not a repository file. It does not amend the frozen contracts. PASS below can rely on clearly identified accepted device history plus current code/test evidence; it never means a fresh device run. NOT VERIFIED means this review cannot independently establish the full requirement from the available artifacts. Historical per-step FINAL PASS approvals are preserved.

| # | Requirement | Audit status | Evidence and limits |
| --- | --- | --- | --- |
| 1 | Documented device/versions/root; media core without root | **PASS** | Exact accepted baseline and ordinary-Termux capability/Steps 1.2–2.4 history; no su dependency in the inspected core. [DEVICE_BASELINE.md], [STEP_1_1_REPORT.md], accepted stage table |
| 2 | Actual Recora examined; exact media/mode/tiny-part/overlap contracts frozen | **PASS** | Revision-verified implementation/config/tests; [C1], [C2]; actual measurement/gain/planner/media comparisons above. No contracts changed. |
| 3 | Preflight/conservative capacity/refusal; immutable hash-verified source independent of external URI; zero photos | **PASS** | Accepted 1.2 device evidence and current import/inspection/processing tests; fourteen measured zero-photo fixture pipelines verified managed-original hashes. Capacity estimates remain provisional rather than guarantees. [SESSION_IMPORT.md:326], [I1], [I2], [U1], [E5] |
| 4 | Actual Android probe and correct facts, safe invalid media, original integrity | **PASS** | Accepted real probe/duration confirmation and 84-test device suite; current 203-test suite plus same-byte valid/invalid host probes. Raw AAC duration safety is explicitly qualified, not guessed. [SESSION_INSPECTION.md:158], [U1], [E4] |
| 5 | Auto/Force/Off, safe gain, no needless encode, timeline/media policy | **PASS** | Accepted 125-test device results and actual Auto/Force/Off fixtures; shared Auto comparisons, Force +1.210 measured extension and current safety tests. [SESSION_NORMALIZATION.md:250], [U2], [E1], [E2], [E3] |
| 6 | Modes, deterministic quiet/fallback/useful parts, overlap/no gaps/end | **PASS** | Accepted 170-test device results and real 3-part plan; current tests; measured 61/90/53-minute source comparison and independent geometry/pause checks. Force/Off pure-function extension evidence is S, not a claimed Recora mode. [SESSION_SEGMENTATION.md:175], [U3], [U4], [E5] |
| 7 | One real ~45–70 MB, 1–1.5 h, zero-photo Android lecture completes full local pipeline without PC/server dependencies | **PASS** | Accepted Steps 1.2–2.4 establish this chain for the same 44,941,318-byte (~44.94 MB), 3691.787029-s (~61.53-min), zero-photo lecture session `d0c39956c17943299dd17e67bf6d1d68`. Additional user-reported Android integrity checks returned **ALL_PASS=True**, supporting the original/output integrity acceptance. Device Git metadata is unavailable due to ZIP deployment; no tested device commit is invented. This PASS relies on accepted user-reported Android evidence, not host synthetic runs or a new independent device execution. |
| 8 | This report; no unexplained media divergence; frozen intentional differences only | **PASS** (evaluated scope) | Fourteen same-hash pipelines, measured rejection/raw-AAC edge cases, inspected code/tests and explicitly bounded S/N comparisons. Tiny-tail, modes and safety additions reference pre-existing contracts; no new acceptable divergence invented. |
| 9 | Full Archive Lecture default pending real-device measurement | **OPEN** | Explicitly keep OPEN, not PASS/FAIL. Accepted import selection remains unresolved; later actual-device storage/archive measurement is required. No policy change. [SESSION_IMPORT.md:98], [C2] |

**Separate gate conclusion:** items 1–8 PASS on the evidence identified above, including the additional user-reported Android integrity checks for item 7. Item 9, the Full Archive Lecture default, remains intentionally OPEN pending later actual-device measurement. The accepted Step 2.4 FINAL PASS is preserved; no repeat import or processing is required by this audit.

Additional limits: no fresh Android 90-minute run; no full cross-project conditional-codec/all-rate matrix; no independent device artifact replay, achieved-loudness guarantee, byte-identical-output requirement or manual listening PASS. These are not silently counted as measured successes. No architecture/deployment/UI comparison was made.

## Current automated suite and final classification

Ran `python -m unittest discover -s tests -v` against the unchanged current RecorAndro revision, with TEMP/TMP set to the owned test scratch directory: **203/203 PASS**, **0 failures, 0 errors, 0 skips**, exit **0**, **97.663 s**. [E6] Relevant Recora tests were inspected, not rerun as a suite; their old skips were not converted into passes. Reference core byte hashes and current implementation/contracts/tests are checked unchanged at review completion. Report whitespace is checked with `git diff --check` and the new-file check.

**Media parity classification: PASS WITH INTENTIONAL DIVERGENCE.** The exact measured tiny-tail count/boundary change is the frozen improvement; Force/default-mode, finite-peak and raw-duration safeguards are already authorized differences, not newly excused defects. F07's numerical/sample detail is disclosed and satisfies the same frozen rounding/timing semantics. No unexplained mismatch was found in evaluated media behavior. Unexecuted comparisons are explicitly S/N, and the separate Part 1 acceptance gate remains unclosed as described above.

Stop after this report. No implementation/test/contract edits, Recora writes, commits, pushes or PART 2 work.

## Evidence references

[R1]: C:/loxi/Recora/app/audio.py:72
[R2]: C:/loxi/Recora/app/normalization.py:19
[R3]: C:/loxi/Recora/app/segmentation.py:8
[R4]: C:/loxi/Recora/app/exports.py:111
[R5]: C:/loxi/Recora/app/config.py:13
[A1]: C:/loxi/ReacorAndro/recorandro/inspection.py:83
[A2]: C:/loxi/ReacorAndro/recorandro/normalization.py:71
[A3]: C:/loxi/ReacorAndro/recorandro/segmentation.py:79
[A4]: C:/loxi/ReacorAndro/recorandro/exports.py:323
[T1]: C:/loxi/Recora/tests/test_audio.py:27
[T2]: C:/loxi/Recora/tests/test_normalization.py:58
[T3]: C:/loxi/Recora/tests/test_segmentation.py:55
[T4]: C:/loxi/Recora/tests/test_exports.py:332
[U1]: C:/loxi/ReacorAndro/tests/test_inspection.py:35
[U2]: C:/loxi/ReacorAndro/tests/test_normalization.py:69
[U3]: C:/loxi/ReacorAndro/tests/test_segmentation.py:43
[U4]: C:/loxi/ReacorAndro/tests/test_exports.py:33
[I1]: C:/loxi/ReacorAndro/recorandro/sessions.py:73
[I2]: C:/loxi/ReacorAndro/tests/test_sessions.py
[C1]: C:/loxi/ReacorAndro/docs/MEDIA_CONTRACT.md
[C2]: C:/loxi/ReacorAndro/docs/BEHAVIOR_CONTRACT.md
[E0]: C:/loxi/ReacorAndro/data/part1-recora-reference.json
[E1]: C:/loxi/ReacorAndro/data/part1-parity-evidence.json
[E2]: C:/loxi/ReacorAndro/data/part1-parity-extra-evidence.json
[E3]: C:/loxi/ReacorAndro/data/part1-parity-rate-evidence.json
[E4]: C:/loxi/ReacorAndro/data/part1-parity-edge-evidence.json
[E5]: C:/loxi/ReacorAndro/data/part1-parity-verified.json
[E6]: C:/loxi/ReacorAndro/data/part1-parity-tests.txt
[DEVICE_BASELINE.md]: C:/loxi/ReacorAndro/docs/DEVICE_BASELINE.md
[STEP_1_1_REPORT.md]: C:/loxi/ReacorAndro/docs/STEP_1_1_REPORT.md
[SESSION_IMPORT.md:326]: C:/loxi/ReacorAndro/docs/SESSION_IMPORT.md:326
[SESSION_IMPORT.md:98]: C:/loxi/ReacorAndro/docs/SESSION_IMPORT.md:98
[SESSION_INSPECTION.md:158]: C:/loxi/ReacorAndro/docs/SESSION_INSPECTION.md:158
[SESSION_NORMALIZATION.md:250]: C:/loxi/ReacorAndro/docs/SESSION_NORMALIZATION.md:250
[SESSION_SEGMENTATION.md:175]: C:/loxi/ReacorAndro/docs/SESSION_SEGMENTATION.md:175
[SESSION_EXPORT.md:214]: C:/loxi/ReacorAndro/docs/SESSION_EXPORT.md:214
