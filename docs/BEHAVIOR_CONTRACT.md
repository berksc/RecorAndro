# RecorAndro v0.1 behavior contract

Status: **frozen design requirements, 2026-10-08**. This freezes decisions and invariants, not Android capability claims or an implementation. Use [MEDIA_CONTRACT.md](C:/loxi/ReacorAndro/docs/MEDIA_CONTRACT.md) for media input/output and verification. Existing [SCOPE.md](C:/loxi/ReacorAndro/docs/SCOPE.md), [DEVICE_BASELINE.md](C:/loxi/ReacorAndro/docs/DEVICE_BASELINE.md) and [RECORA_MEDIA_PARITY.md](C:/loxi/ReacorAndro/docs/RECORA_MEDIA_PARITY.md) were read before this freeze; the parity document stays an unchanged extraction.

The actual Recora reference was accessible and reverified read only at `C:\loxi\Recora`, `main`, commit `9b886519ea623fa8bf0746f96ea512da18413bde`. Working core files matched the committed blobs. Evidence references below use the parity inventory, particularly E03–E07 and E14–E16. Recora's frozen review skipped real-tool integration fixtures; freezing a design does not convert those skips into Android qualification.

> Recora parity means media-processing behavior and invariants only. It does not imply code, filesystem, state-machine, deployment or architecture parity.

## Comparison and intentional divergences

Every proposed default was compared with the actual behavior recorded in the parity extraction. All deviations below are explicit product/safety decisions required by this contract; none assumes a missing Android capability.

| Area | Actual Recora baseline | Frozen RecorAndro decision / reason |
| --- | --- | --- |
| Input/media formats | Supported suffixes/demuxers, first recognized audio, conditional codec decoding; immutable originals. | Retain; exact tables and rejection policy in media contract. No import transcode or unknown-container expansion. |
| Normalized/cut outputs | AAC-LC M4A, native AAC, 128000 mono / 192000 stereo; supported source rate else 48000; preserve channels. | Retain all values, filename basenames and copy exception. No Android format/rate/channel divergence. |
| Normalization default | Recora requires explicit opt-in normalization. | **Auto by default**, an explicit user-approved RecorAndro product decision. Off remains fully supported as a user-selectable mode; Force remains available. |
| Auto normalization | Below -30 LUFS; target -26; positive gain <=3 dB, planned peak -3; useful gain >=0.5, floor 0.001. | Retain exact comparisons, filter and no-gain byte identity. |
| Force normalization | No direct equivalent. | New RecorAndro behavior: intentional measurement and safe gain evaluation without the -30 eligibility gate; all other gain/safety constraints retained. No mandatory gain or re-encoding. |
| Encoded peak validation | Reject finite peak >-1; warn >-2.9; null peak can pass numeric checks. | Same limits; require finite encoded peak for a boosted copy. Small safety tightening: an unavailable measurement cannot verify safe encoded output. |
| Quiet/normal boundaries | -40 dBFS, 1 s; target 1500 s, window 1200–1620 s; midpoint ranking and target fallback. | Retain detector, normal target/window and tie order; constrain candidates to leave feasible useful remaining parts. |
| Auto segmentation threshold | Remaining duration >1500 s can produce a tiny tail; no minimum tail. | **Whole source >1620 s triggers multi-part Auto**. Reuse the existing 27-minute window maximum as the single-part allowance, avoiding needless 0.1 s to 2 min tails above 25 min. |
| Useful durations and part count | No final-tail minimum or merge rule. | New minimum **600 s per nominal part in a multi-part plan**; maximum **1620 s**, fixed feasible count, deterministic merging/replanning/redistribution. Ten minutes prevents 1–3 minute scraps while retaining useful final remainders such as Recora's 11-minute tail. |
| Segmentation modes/default | Separate user-requested planner/export, no Auto/Force/Off enum. | **Auto default** inside a user-triggered processing action; Force seeks at least two useful parts; Off exports exactly one canonical full-length output. No background trigger. |
| Segmentation source prerequisites | Successful normalization check (`success` or `not_needed`) precedes planning. | Applied normalization uses its verified derivative; Off or evaluated no-gain uses verified original directly. Off does not require an unrelated loudness check. |
| Sample export/verification | Independent sample trim and AAC encode; byte-copy compatible one-part source; fixed timing allowance, hashes/decode checks. | Retain; single output for every mode is a generated verified file for packaging, never an alias to original. |
| Overlap/coverage | 5 s added to nominal ends only, capped at source end; no gaps. | Retain exactly, including after redistributed boundaries. |
| Photo/audio relation | Recora implements visual timeline/part mapping. | User-required v0.1 scope: no hard visual-to-audio mapping; photos cannot gate audio or choose boundaries. |
| Full archive | Implemented capability in frozen Recora. | Supported, profile-controlled local capability; Lecture default explicitly pending real-device storage/performance evidence. |
| Tool execution | No shell/remote media, explicit stream, fail-on-error, no overwrite, bounded passes. | Retain platform-neutral behavior and numeric timeouts; root and Windows execution/deployment are excluded. |

The Auto normalization default, 600-second minimum, 1620-second Auto cutoff/nominal cap, constrained planning, Force modes and finite-output-peak check are deliberate RecorAndro contract additions, not extracted Recora behavior. They must be labeled accordingly in later tests and reports.

## D. Normalization modes

Normalization and segmentation modes are independent. Normalization default is **Auto**. Off and Force remain user-selectable. Every run records requested mode, actual outcome and selected working source; the user initiates processing. No media step edits original bytes, deletes source silence, changes speed or uses visual data.

### Shared measurement and safe gain

Each new Auto/Force evaluation starts from the verified accepted original, not a previous normalized copy, so reruns never accumulate gain. Auto and Force fully decode its selected stream for EBU R128 integrated loudness/true peak, using this exact discarded-output measurement filter:

```text
loudnorm=I=-26:TP=-3:LRA=50:print_format=json
```

Use its input measurements, not the transformed measurement output. The sole delivered transform for a selected boost is `volume=<gain to 3 decimals>dB:precision=double`, followed by the media-contract encode. No second dynamic loudness-normalization pipeline.

For eligible finite integrated loudness `I` and true peak `P`:

```text
desired = -26 - I
headroom = max(0, -3 - P)
gain = max(0, min(desired, 3, headroom))
gain = floor(gain * 1000) / 1000
if gain < 0.5: gain = 0
```

Target **-26 LUFS**, positive boost cap **3 dB**, planned true-peak ceiling **-3 dBTP**, minimum useful gain **0.5 dB**, downward precision **0.001 dB**. No negative gain, forced minimum gain, clipping repair, attenuation, limiter or compression. A capped/headroom-limited boost may not reach target. Input peaks at/above 0 dBTP produce an existing-clipping warning and cannot acquire positive peak headroom under this formula.

Below-gate integrated loudness (`-inf`, represented as null) is a valid no-gain decision. Finite integrated loudness without usable true peak, malformed measurement, tool error or failed integrity is a failure, not an ordinary skip. New boosted output must pass the media-contract timing/format/full-decode/finite-peak gates; encoded peak >-1 dBTP fails and >-2.9 dBTP warns. Those encoded limits do not imply a hard delivered -3 dBTP ceiling.

### Auto

Evaluate measured eligibility **`I < -30 LUFS`**; exactly -30 and louder remain unchanged. If eligible, use the shared safe-gain calculation. Gain >=0.5 dB after flooring produces a separate verified normalized master. Otherwise use original bytes unchanged, with an explicit reason: `auto_already_usable_level`, `below_measurement_gate`, or `insufficient_safe_gain`. No zero-gain encode, resampling or metadata stripping is performed for an Auto skip.

### Force — specific to RecorAndro

Force always intentionally runs measurement and gain evaluation even where Auto would skip on its -30 LUFS eligibility cutoff. It **only bypasses that eligibility cutoff**. It retains the target, cap, planned peak, minimum useful gain and all verification rules above.

- Source below target with sufficient safe headroom: apply the formula. For example, -28 LUFS / -10 dBTP produces +2 dB in Force while Auto skips.
- Source at or above **-26 LUFS**: valid `force_no_gain_at_or_above_target`; preserve it without attenuation or re-encoding.
- Below-gate loudness: valid `force_no_gain_below_measurement_gate`.
- Safe candidate gain below 0.5 dB or no peak headroom: valid `force_no_gain_insufficient_safe_gain`. For example, -27.7 LUFS / -1.39 dBTP cannot be boosted safely; Force preserves the original.

Force evaluation does not promise mandatory gain or mandatory encoding. On a valid safe no-gain result record `mode_requested: force`, `evaluation_performed: true`, `evaluation_completed: true`, `decision: <explicit force reason>`, `gain_db: 0`, `normalization_applied: false`, `encoding_applied: false`, `output_source: original`, original size/hash/duration, and input levels/warnings. Normalization has completed its requested safety evaluation; it must not be mislabeled as an applied normalization. A failed measurement/verification uses a failed outcome rather than this success metadata. These are semantic facts, not a prescribed database or state machine.

### Off

No loudness measurement or gain is requested. Record `mode_requested: off`, `evaluation_performed: false`, `decision: normalization_off`, `gain_db: 0`, `normalization_applied: false`, `encoding_applied: false`, and verified original as working source. Probe/integrity/decoder checks remain required; Off does not bypass media validation.

Segmentation/delivery uses that original directly; it does not wait for a fake normalization run or create `normalized.m4a`. Canonical delivery may later encode/copy a part under the media contract. Report that encoding as delivery/export, not normalization. No-gain Auto/Force follows the same working-source rule; successful applied normalization uses its verified derivative.

## E. Segmentation modes

Segmentation default is **Auto** within an explicit user-triggered processing action. Let `D` be the verified working-source duration, `L = 600 s` the minimum useful multi-part nominal duration, and `U = 1620 s` the nominal maximum. Target remains **1500 s**. Apply thresholds to logical source duration, not padded part file durations; timing tolerance is not a threshold fudge factor.

### Auto

For **`D <= 1620 s`**, generate one full-length canonical part. For **`D > 1620 s`**, create exactly **`N = ceil(D / 1620)`** nominal parts using F below. This is the minimum count able to respect the maximum; quiet regions do not increase/decrease it. Every part must be at least 600 seconds. An inherently short one-part source is valid even if under 600 seconds.

A source just above the 25-minute target, such as 1500.1 seconds, remains one part. The 27-minute cutoff is intentional tiny-tail avoidance, not a changed loudness threshold, FFmpeg capability workaround or lost interval. Exactly 1620 seconds stays one; 1620.1 seconds creates two useful parts.

### Force

Intentionally request segmentation even when Auto would retain one part. If **`D >= 1200 s`** (two times the useful minimum), set **`N = max(2, ceil(D / 1620))`**. Thus a 26-minute source has two useful 13-minute fallback parts even though Auto retains one. For longer sources already split by Auto, Force uses the same count/planning; it does not add arbitrary extra parts.

If **`D < 1200 s`**, two useful parts cannot fit. Generate one verified full-length output, and record `mode_requested: force`, `mode_fulfilled: false`, `segmentation_applied: false`, `decision: force_not_feasible_minimum_duration`, the 600-second minimum, requested minimum count 2 and actual count 1. This is a valid complete session with an unmet segmentation request, not a silent claim that Force produced multiple parts. No gap, shortened source or tiny fragment is allowed to satisfy Force cosmetically. At exactly 1200 seconds Force produces two 600-second nominal parts.

### Off

Exactly one verified generated full-length canonical audio file, regardless of duration. No quiet-boundary analysis or multi-part plan is needed. Its nominal and exported logical range is `[0,D]`, overlap 0. Source is whichever normalization outcome selected. Packaging references this safe generated file: a byte copy for the media-contract compatible source, otherwise a canonical AAC/M4A encode. It never aliases the immutable original. The multi-part minimum/maximum and Auto threshold do not truncate or reject a full-length Off output.

## F. Deterministic useful-part policy

> Segmentation may deviate from the nominal target duration to avoid nonsensical tiny first or last parts.

Minimum useful nominal duration is **600 seconds (10 minutes)** for **every part of a multi-part plan**, including first and last. Overlap does not count toward this minimum. Maximum nominal duration is **1620 seconds (27 minutes)** for every multi-part part. The **1200-second search minimum is a preference for normal cuts**, not a hard lower bound when redistribution is required. A short complete single-source output is not a leftover and is exempt.

### Merging and redistribution rules

1. Select mode/count using E before selecting quiet boundaries. Require `N*L <= D <= N*U` for a multi-part plan. Off and single-part Auto bypass this multi-part test; Force's too-short safe outcome is specified above.
2. A preliminary target-based plan with redundant boundaries/tiny tails is not exportable. **Merge and replan globally to the mode's fixed `N`**: remove excess tentative boundaries, then compute the complete plan from the same source/quiet regions. Do not merely drop the final tail, keep an invalid first part or vary count with quiet-detector order. For Auto, `ceil(D/U)` is the canonical merge count: e.g. 51/53/76-minute target-tail cases become 2/2/3 parts, respectively.
3. If a tail cannot be merged into its neighbor within `U`, redistribute by moving earlier boundaries as far back as necessary to satisfy the selected count. Reserve feasible duration for **all** remaining parts at every cut, not only the immediate tail. Replanning is the deterministic redistribution operation; no ad hoc later append or arbitrary part-count target is allowed.
4. Coverage and useful-duration feasibility have priority over quiet preference, target proximity and preserving a preliminary boundary. Force cannot merge its requested two feasible parts down to one. Never sacrifice zero/end coverage or the fixed overlap geometry.

### Exact boundary-selection algorithm

For each internal boundary, let `p` be the previous chosen boundary and `m` the number of nominal parts that must remain **after** this cut. Define the closed feasible interval:

```text
F = [max(p + 600, D - m*1620), min(p + 1620, D - m*600)]
normal_window = [p + 1200, p + 1620]
S = intersection(F, normal_window)
```

`F` reserves enough source duration for every remaining part and prevents tiny first/last parts. Feasibility interval endpoints, not encoded padding, control the rule. An empty `F` is an invalid plan and must fail without export.

- If `S` is nonempty (even a single point), search in `S` around ideal **`p + 1500`**. With no qualifying quiet candidate, choose that ideal clamped to `S`: exact nominal target when feasible, otherwise the nearest feasible endpoint. Reason is `fallback_target` when unclamped, or `fallback_feasible_target` when clamped.
- If `S` is empty, useful redistribution requires a cut outside the normal 20–27 minute preference. Search in `F` around balanced remaining ideal **`p + (D-p)/(m+1)`**. That ideal is feasible; with no candidate, choose it exactly and record `fallback_redistributed_balance`. This is an explicit exception to target/window preference, not to the useful bounds. It permits two useful ~13.5-minute parts just above the Auto cutoff and feasible shorter Force splits.
- For the selected search interval and ideal, use a full quiet interval's midpoint if inside the search interval. Otherwise use the midpoint of its intersection if the intersection meets the 1-second quiet minimum. Full qualifying interval minimum and intersection checks retain Recora's **0.00001 s comparison allowance**.
- Rank candidate tuples by **distance from this cut's ideal ascending**, **full quiet-interval duration descending**, **candidate timestamp ascending**, then quiet start/end ascending. Rank is independent of input iteration order. Search-feasibility and chosen count cannot be overridden by a nearer infeasible silence. Record quiet evidence and whether selection used the normal or redistribution window; never label a fallback as quiet.
- Continue relative to the actual chosen boundary. Set final endpoint to `D` exactly; verify all nominal lengths are in `[600,1620]`. The final part has no added boundary chosen beyond source end.

There is no gap or silence removal, no source-time clamping to a target multiple, and no dropped final remainder. The fixed count ensures duration-only examples have exact counts even if valid quiet regions move their boundaries.

### Quiet analysis and overlap

Retain Recora's full decoded, combined-channel detector:

```text
asetpts=PTS-STARTPTS,silencedetect=noise=-40dB:duration=1:mono=0
```

Quiet threshold **-40 dBFS**, minimum quiet duration **1 s**. Parse the complete event log only after successful decode; leading/trailing regions are valid. Event tolerance is **`max(0.05 s, 2048/source_rate)`**, with only within-tolerance events clamped to source endpoints. Invalid/unordered/unmatched events fail; more than **100000 retained quiet intervals** fails, following Recora. Analysis rebases discarded PTS only and never edits the source. One-part outputs do not require unnecessary quiet analysis.

After the final nominal plan is fixed, every exported range is:

```text
[nominal_start, min(D, nominal_end + 5 s)]
```

Following starts stay at nominal boundaries. Internal logical ranges are half-open; final logical end is source end. This is **5 seconds total shared context per adjacent boundary**, not a symmetric +/-5-second expansion. First start is zero, final end is `D`, overlap is capped by available source. Useful multi-part minimums make full 5-second adjacency overlap available; a single-part output has none. No gap is permitted. Round shared boundaries consistently for sample cuts under the media contract; codec duration allowance does not change logical geometry.

### Required example outcomes

The following ranges are **nominal source ranges without overlap**, for no suitable quiet candidate. Seconds govern exact decisions; minute notation is approximate for fractional seconds. With eligible quiet candidates, boundaries may move inside feasibility/search intervals but **the listed counts remain exact**. Off is always one full-length generated output.

| Source duration | Auto count and fallback nominal ranges | Force count and fallback nominal ranges | Off count |
| --- | --- | --- | --- |
| **1500.1 s** (~25:00.1) | **1**: 0–1500.1 s | **2**: 0–750.05–1500.1 s (~12:30.05 each) | **1** |
| **26 min** (1560 s) | **1**: 0–26 min | **2**: 0–13–26 min | **1** |
| Exactly **27 min** (1620 s) | **1**: 0–27 min | **2**: 0–13.5–27 min | **1** |
| **1620.1 s** (~27:00.1) | **2**: 0–810.05–1620.1 s (~13:30.05 each) | **2**: same | **1** |
| **30 min** (1800 s) | **2**: 0–20–30 min (20/10) | **2**: same | **1** |
| **49 min** (2940 s) | **2**: 0–25–49 min (25/24) | **2**: same | **1** |
| **51 min** (3060 s) | **2**: 0–25–51 min (25/26) | **2**: same | **1** |
| **53 min** (3180 s) | **2**: 0–26–53 min (26/27) | **2**: same | **1** |
| **55 min** (3300 s) | **3**: 0–25–45–55 min (25/20/10) | **3**: same | **1** |
| **61 min** (3660 s) | **3**: 0–25–50–61 min (25/25/11) | **3**: same | **1** |
| **74 min** (4440 s) | **3**: 0–25–50–74 min (25/25/24) | **3**: same | **1** |
| **76 min** (4560 s) | **3**: 0–25–50–76 min (25/25/26) | **3**: same | **1** |
| **80 min** (4800 s) | **3**: 0–26–53–80 min (26/27/27) | **3**: same | **1** |
| **90 min** (5400 s) | **4**: 0–25–50–75–90 min (25/25/25/15) | **4**: same | **1** |

Thus 26 minutes does not become 25+1; 51–53 minutes do not become 25+25+1..3; 76 minutes does not become 25+25+25+1. For example, the 53-minute fallback exported ranges are `[0,1565]` and `[1560,3180]` seconds: five seconds repeat after the redistributed 26-minute boundary, with no missing source. At 61 minutes they are `[0,1505]`, `[1500,3005]`, `[3000,3660]`, preserving Recora's established example. A 30-minute recording uses 20/10 rather than 25/5 because useful-part feasibility wins over target proximity.

## G. Full archive policy

Full archive is a **supported local capability**, independently controlled by profile. Its exact **Lecture default remains pending** real-device peak-storage, elapsed-time and thermal/performance measurements. Do not encode a Lecture ON default in metadata, examples, profile fallback or implementation. Other profile archive choices and archive storage budgets remain unfrozen.

A session with no full archive is still complete when its required canonical audio outputs pass verification. Archive selection cannot change input shape, normalization/split decisions, source ranges or original immutability. Capability support is frozen; archive-default tuning is not.

## H. Visual non-dependency and operating scope

Zero-photo sessions are fully complete and valid. No normalization, source selection, duration inspection, segmentation, encoding, integrity verification, packaging readiness or archive-capability decision requires visual data or valid photo timing. No hard visual-to-audio mapping in v0.1: audio succeeds without photo timestamp alignment, primary part ownership or inferred associations. Audio source-range metadata remains required for audio's own coverage; it does not impose photo mapping.

Android-first, local-first, user-triggered and audio-first; no PC, server, Cloudflare, database, OpenAI API, Notion API, transcription, OCR or cloud sync. Normal processing uses ordinary Termux context; current Magisk/root status does not create a dependency. No Android background workaround or deployment architecture is selected here.

## Pending after real-device measurement

- **Blocking before engine implementation:** the step 1.1 capability gate in the media contract: installed Termux/Python/tools/ABI, required input demuxers/decoders, M4A muxer/AAC encoder, loudness/quiet/sample/gain filters, rate/channel operations and verification/safety options, all demonstrated without root. Missing capability requires recorded evidence and the smallest proposed explicit revision; version differences alone do not justify divergence.
- **Intentionally unfrozen after measurement:** Lecture full-archive default; other profile archive defaults; storage reserve/budget/admission limits, real peak storage, execution/thermal budgets and performance expectations; any specific Android integration/background mitigation warranted by actual device failures. Mode defaults and media constants above are already frozen, not auto-tuned by those measurements.
- **Qualification work, not undecided policy:** real 61-/90-minute runs, raw AAC and other conditional codec variants, rate/channel preservation and resampling, gap/overlap/sample accuracy, encoded safety checks, and Xiaomi/MIUI screen-off/background plus hotspot coexistence. No benchmark result or required workaround is invented now.
- **Separate later design:** complete on-device filesystem layout, action/state orchestration, reports/package/archive layout and daily UI. These are not Recora architecture parity and are not audio-engine implementation in this step.

## Canonical behavior constants and decision table

| Constant / decision | Frozen value |
| --- | --- |
| Default modes | Normalization **Auto**; segmentation **Auto**; processing remains user-triggered |
| Auto normalization eligibility | Integrated loudness **strictly below -30 LUFS** |
| Gain target / maximum / minimum | **-26 LUFS** / **+3 dB** / **0.5 dB** useful positive gain |
| Planned / encoded peak | **-3 dBTP** gain headroom; reject encoded **>-1 dBTP**; warn **>-2.9 dBTP**; boosted output peak must be finite |
| Measurement / gain precision | `loudnorm=I=-26:TP=-3:LRA=50:print_format=json`, output discarded; gain floored to **0.001 dB**, `volume` double precision |
| Force normalization | Bypass only Auto's -30 LUFS eligibility; same target/cap/peak/minimum; safe explicit no-gain is valid, without mandatory encode |
| Off / no-gain source | Verified original; no normalized file; canonical export copy/encode is a separate step |
| Auto one-part cutoff | **D <=1620 s** one part; **D >1620 s** split |
| Normal target / search window | **1500 s** / **1200–1620 s** after previous boundary, intersected with useful-duration feasibility |
| Useful multi-part duration | **600–1620 s** nominal duration for every part; overlap excluded; no short-tail exception |
| Auto count | `ceil(D/1620)` above cutoff; otherwise 1 |
| Force count / feasibility | `max(2,ceil(D/1620))` when **D >=1200 s**; otherwise one full-length output with unmet-request metadata |
| Off count | 1 full-length canonical generated output, all durations |
| Quiet detector / minimum | **-40 dBFS**, **1 s**, combined channels; minimum/intersection comparison allowance **0.00001 s** |
| Quiet parser tolerance / bound | `max(0.05 s,2048/source_rate)` / **100000 retained intervals** |
| Boundary priority / fallback | Coverage/useful count first; normal window then feasible redistribution; quiet nearest ideal, longest full interval, earliest; clamped target or balanced remaining ideal |
| Overlap / endpoints | **5 s**, extend nominal ends only, cap at `D`; first 0, final `D`, no gaps |
| Original / visual invariants | Immutable original; preserve source time/silence; no required photos or hard visual-to-audio mapping |
| Full archive | Supported, profile-controlled; **Lecture default pending measurements** |
