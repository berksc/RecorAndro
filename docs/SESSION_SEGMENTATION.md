# Step 2.3 — Segmentation decision and nominal planning

Status: **Step 2.3 FINAL PASS approved**, following accepted actual-device
validation on the Redmi Note 10 Pro in ordinary non-root Termux. No audio export,
cuts, overlap-expanded ranges, packaging or subsequent step is implemented.
Step 2.2 remains accepted FINAL PASS.

Started from clean `main`, HEAD and local `origin/main`
`4464da74139f3456659cf4c27e40345b6c402207` (`2.2 - Normalization Auto / Force / Off`).
The frozen behavior/media contracts and accepted import, inspection, normalization
and storage code remain unchanged. Recora was consulted read only; it is not a
runtime dependency. Changes are the new planner/test/guide, CLI and README.

## Frozen decisions

Normalization and segmentation modes are independent. This operation requires
the **current completed normalization outcome**, including Off or evaluated
no-gain. It never runs normalization, falls back to a previous successful attempt,
or accepts an external audio path. Applied normalization selects that attempt's
verified `normalized.m4a`; no-gain/Off selects the verified managed original.
This is an analysis source, not a generated delivery file. A canonical full-length
copy/encode for a single-part plan belongs to a later export step.

| Rule | Exact value |
| --- | --- |
| Auto default | One part for D <=1620 s; otherwise ceil(D/1620) |
| Force | max(2,ceil(D/1620)) for D >=1200 s |
| Force below 1200 s | One full-length part, `mode_fulfilled=false`, `force_not_feasible_minimum_duration` |
| Off | One full-length nominal range for every valid duration |
| Multi-part bounds | Every nominal length 600..1620 s, including first and last |
| Target / normal preference | 1500 s / 1200..1620 s after the preceding boundary |
| Quiet detector | `asetpts=PTS-STARTPTS,silencedetect=noise=-40dB:duration=1:mono=0` |
| Quiet comparison allowance | 0.00001 s, for full/intersection minimum duration |
| Event endpoint allowance | max(0.05 s,2048/source_rate) |
| Retained quiet intervals / parts | At most 100000 / 10000 |

Fix feasible count N **before** quiet selection, requiring N*600 <=D <=N*1620
for multi-part plans. At each internal cut with prior boundary p and m remaining
parts after it:

```text
F = [max(p+600,D-m*1620), min(p+1620,D-m*600)]
S = intersection(F,[p+1200,p+1620])
```

When S is nonempty, including a point, search S around p+1500. Without a quiet
candidate, choose that ideal clamped to S: `fallback_target` if unchanged,
otherwise `fallback_feasible_target`. If S is empty, search F around
`p+(D-p)/(m+1)`; fallback is `fallback_redistributed_balance`.

Use the full quiet interval midpoint when inside the search interval; otherwise
use its intersection midpoint only if the intersection satisfies the 1-second
minimum with the comparison allowance. Rank by distance to ideal ascending,
**full** quiet duration descending, timestamp ascending, quiet start/end ascending.
Input iteration order cannot alter selection. Only qualifying evidence is labeled
`quiet_region`; a fallback never is.

Tiny-part avoidance is global replanning to the fixed count, reserving **all**
remaining useful parts at every cut. No preliminary target-tail plan is accepted.
Coverage and useful structure outrank quiet preference and target proximity.
Decimal arithmetic avoids binary rounding turning an exact 1620-second fractional
span into an apparent bound violation; no cutoff/tolerance fudge is introduced.
The final endpoint is D exactly. Single-part short sources are exempt from the
multi-part minimum; Off is also exempt from its maximum.

## Timeline and representative fallback plans

All nominal ranges use `original_media_relative_seconds`, start at zero, share
exact contiguous boundaries, and end at freshly verified working duration D.
Original and working durations are recorded separately. A normalized duration
delta within its accepted tolerance does not redefine timeline zero or establish
sample identity. Analysis rebases PTS only on the discarded detector stream.
Creation tags, photos and normalization mode cannot shift boundaries.
`silence_removed=false` and `audio_exported=false` always hold.

| Duration | Auto nominal lengths (seconds) | Force nominal lengths (seconds) |
| --- | --- | --- |
| Very short / 5 min | Complete single source | Complete single source; request unfulfilled |
| 1619.999999 / 1620 | One full-length part | Two balanced useful parts |
| 1620.1 | 810.05 / 810.05 | Same |
| 26 min | 1560 | 780 / 780 |
| 30 min | 1200 / 600 | Same |
| 49 min | 1500 / 1440 | Same |
| 51 min | 1500 / 1560 | Same |
| 52 min | 1500 / 1620 | Same |
| 53 min | 1560 / 1620 | Same |
| 55 min | 1500 / 1200 / 600 | Same |
| 61 min | 1500 / 1500 / 660 | Same |
| 74 min | 1500 / 1500 / 1440 | Same |
| 76 min | 1500 / 1500 / 1560 | Same |
| 80 min | 1560 / 1620 / 1620 | Same |
| 90 min | 1500 / 1500 / 1500 / 900 | Same |

Off is one [0,D] range for every row. Suitable quiet candidates may change
boundaries, but never these counts or useful bounds.

Retained Recora semantics: combined-channel quiet filter, complete-log parsing,
leading/open-trailing quiet, endpoint allowance, midpoint/intersection candidates,
deterministic ranking, source/global timeline, target-relative subsequent cuts,
and immutable source checks. Intentional frozen RecorAndro improvements are the
1620-second Auto allowance, 600-second minimum for every multi-part part,
mode-dependent fixed counts, Force's unfulfilled safe outcome, and feasible
redistribution. For example historical target-tail splits at 51/53/76 minutes
could produce 1..3-minute leftovers; these plans produce 2/2/3 useful parts.
Recora's 61-minute fallback remains 25/25/11 minutes.

## Source safety and bounded analysis

Uses the accepted `OwnedDirectory` traversal, session validation, shared inspection
lock, file identity/size/SHA-256 verification and atomic JSON writer. It validates
current inspection and completed normalization records, freshly probes the original
and working source, and requires unchanged selected index/codec/demuxer/rate/
channels/stream count/duration. Unknown codecs, invalid media, known duration
contradictions and unresolved raw-AAC duration uncertainty are refused.

The original and selected source are rechecked after analysis, including caught
failure paths. One-part plans need no quiet pass; their completed full-decode
qualification is tied to reverified bytes. Multi-part quiet analysis fully decodes
the selected absolute stream under fail-on-error options. POSIX passes pinned FDs
through `/proc/self/fd`; Windows retains the accepted checked-path limitations.

FFmpeg uses configured executable, argument arrays, `shell=False`, disconnected
stdin, `-nostdin -nostats -n -xerror`, file-only protocol, admitted demuxers,
actual-MOV external-reference restrictions, `-err_detect explode`, explicit map,
`-vn -sn -dn` and null output. There is no encoder, resampler, loudnorm or audio
output path in the analysis command. ffprobe keeps its 30-second timeout;
quiet decoding uses `min(21600,max(120,ceil(D*2+60)))` per pass.

The **complete** private log is spooled in an exclusively allocated owned temp
directory, capped at **64 MiB** while draining. stdout is discarded. Timeout,
interrupt, nonzero exit, excessive output and log-write failure fail and stop/reap
the process. Parse only after successful decode; reject malformed/unordered/
duplicate/unmatched events. Only within-tolerance endpoints are clamped. A valid
open trailing region extends to D. The retained-interval limit includes that final
region. Raw diagnostics are removed after parsing/failure and never enter CLI JSON.
Empty owned temporary directories may remain. Abrupt termination may leave a
private spool; it cannot establish a successful plan. Disk-space/write failures
fail safely; planning does not reserve disk capacity.

## Metadata, retries and recovery

```text
sessions/<session_id>/session.json                  # compact latest pointer
sessions/<session_id>/generated/segmentation/<attempt_id>/session.json
                                                  # full analysis and nominal plan
sessions/<session_id>/temp/plan-<attempt_id>/quiet.log
                                                  # private, removed after pass
```

The latest `segmentation` pointer records status (`planning_pending`, `planned`,
`planning_failed`), request/attempt, record path and SHA-256, selected artifact/
normalization revision and compact outcome. The full record retains source facts,
original duration, before/after integrity, quiet regions and parameters, plan
count/decision/mode fulfillment, each boundary's reason/evidence/ideal/feasible
and search intervals, tiny-part adjustments, contiguous nominal ranges, source-end
coverage, timestamps, elapsed time, warnings and sanitized errors.
Within the plan, `segmentation_applied=true` means multiple nominal parts were
planned; `audio_split=false` and `audio_exported=false` distinguish that decision
from audio cutting/export, which is not implemented.

Full records are bounded at **32 MiB** and kept out of the accepted session
reader's 1 MiB limit. Pending invalidates the latest pointer before probing; a
failure has `plan:null`. Earlier plans and all audio artifacts remain intact.
`--retry` is required after failed/pending planning; successful reruns use a new
attempt directory and the currently selected normalization revision.
No top-level imported/inspection/normalization state is changed.

Plan-record publication and latest-session publication are separate atomic writes,
not a transaction. A crash/write failure may leave a complete historical record
while the latest session remains pending. Treat the latest pointer as authoritative,
not file existence; no automatic recovery or pruning is implemented. A changed
normalization outcome makes a saved plan stale by revision/source identity; no
future export may silently reuse it. Export validation remains a later step.

## Accepted Android validation — Step 2.3 FINAL PASS

The user approved Step 2.3 FINAL PASS with the following actual-device evidence:

- Redmi Note 10 Pro, ordinary non-root Termux.
- **170/170 Android tests PASS**, zero failures or skips.
- **Python compilation PASS**.
- Existing lecture session: `d0c39956c17943299dd17e67bf6d1d68`.
- Verified source duration: **3691.787029 seconds**.
- Selected source: **verified managed original**, because normalization Auto
  completed with no gain. Planning did not run normalization again.

| Mode | Nominal part count | Nominal lengths (seconds) | Source-end coverage |
| --- | --- | --- | --- |
| Auto | 3 | 1500 / 1500 / 691.787029 | true |
| Force | 3 | 1500 / 1500 / 691.787029 | true |
| Off | 1 | 3691.787029 | true |

The real lecture had **0 qualifying quiet intervals**. Both Auto boundaries
used deterministic **`fallback_target`**, at global timestamps **1500** and
**3000** seconds. Repeated Auto planning produced identical nominal boundaries.
The final nominal endpoint was **3691.787029 seconds** in all three modes.

There were **no errors**, silence removal, audio export, cutting or
re-normalization. These accepted results validate decisions and nominal planning;
they do not claim part audio was generated or exported. Host fixture evidence
below remains distinct from these actual Android results.

## Host verification and reproducible Android procedure

**170/170 host tests PASS**, exit code 0, no failures or skips: the unchanged
125 existing tests plus 45 planning tests. Python compilation and `git diff
--check` PASS; new-file whitespace checks are clean. Full test evidence is in
ignored `data/segmentation-all-tests.txt`; representative Auto/Force/Off plans
are in `data/segmentation-plans.json`, explicitly labeled pure arithmetic rather
than media/device results. Android FINAL PASS is established by the accepted
actual-device evidence above, independently of these host checks.

Tests cover every frozen fallback example and threshold, duration grids, dense
candidate ranking/order, long interval intersections, parser endpoint/error/limit
cases, full diagnostic spooling and kill/reap behavior, Off/no-gain/applied source
selection, timeline delta, path/hash failures, retries, metadata publication and
zero-photo sessions. Real host FFmpeg fixtures include WAV, M4A, MP3, stereo
combined-channel behavior, an applied normalized source, and a 1621-second WAV
with a 809..813-second quiet interval yielding a boundary near 811 seconds.
Those fixtures are host evidence, not Redmi results or audio export validation.

The following procedure is retained for reproducibility; accepted validation is
complete and does not require repeating it. After transferring the reviewed
planner, CLI, new test, guide and README to the
existing Termux checkout, use ordinary Termux with its existing data root:

```sh
export RECORANDRO_DATA_ROOT="$HOME/recorandro-data"
python -m unittest discover -s tests -v
python -m compileall -q recorandro tests tools
session_id=d0c39956c17943299dd17e67bf6d1d68
result="$HOME/recorandro-lecture-plan-$(date +%Y%m%d-%H%M%S).json"
python -m recorandro plan-session "$session_id" --mode auto > "$result"
printf 'PLAN_EXIT=%s\n' "$?"
cat "$result"
# Separate segmentation modes; these never invoke normalization:
python -m recorandro plan-session "$session_id" --mode force
python -m recorandro plan-session "$session_id" --mode off
# Only after diagnosing a failed/interrupted plan:
python -m recorandro plan-session "$session_id" --mode auto --retry
```

The accepted lecture's completed Auto skip selects its original. Do not re-import
or normalize again. At its accepted duration 3691.787029 s, Auto/Force count is
**3**; without suitable quiet candidates nominal lengths would be
1500/1500/691.787029 s. Actual detected quiet may move boundaries. Off is one full
range. Verify plan source hash/size against the unchanged 44,941,318-byte import,
normalization revision, before/after hashes, source-end coverage, 600..1620 useful
lengths, no gaps, no audio output files and `silence_removed=false`.

Step 2.3 has received **FINAL PASS**. No commit, push or Step 2.4 work without
separate authorization.
