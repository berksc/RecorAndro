# Step 3.1 — persistent progress and artifact registry

Implementation candidate for independent review and actual Redmi/Termux validation.
No Step 3.1 FINAL PASS, commit or push is authorized yet. PART 1 remains accepted.

Continuity was checked against the clean local `main` and the GitHub connector's
live `main` response: both pointed to
`35eb3688a80b347939d5bd21d5452863d94b5aba` (Step 2.5). The frozen scope, media and
behavior contracts and PART 1 parity report were read before implementation.
No frozen contract or media algorithm changed.

## State model and ownership

Canonical session schema is now **2**, with **state_model_version: 1**. Schema-v1
sessions remain readable by every upgraded pipeline operation. The import field
`state` keeps its existing values (`importing`, `imported`, `failed`); successful
pipeline operations continue to require `state: imported`. Overall progress uses
the separate `current_state` field.

| State | Evidence required in Step 3.1 |
| --- | --- |
| `created` | Persisted allocated import; no accepted original yet |
| `imported` | Accepted original reference and current size/SHA-256 verification |
| `probed` | Current completed probe, media record and matching original integrity before/after; this is not full decode eligibility |
| `normalized_or_skipped` | Current successful normalization outcome, including Off/no-gain, matching probe attempt and media facts, original integrity, full decode, decision/timing evidence, exact attempt report; applied output must match its verified bytes and existing safety rules |
| `segmentation_planned` | Existing approved plan reader validates report hash, attempt, policy/geometry and original/source integrity; selected source matches the current normalization revision |
| `segments_exported` | Current successful export report and pointer match the approved plan/source; every required part matches geometry/source/full-decode/media evidence and current bytes; counts and complete coverage match |
| `manifested`, `packaged`, `archived_or_skipped`, `complete` | Reserved; unreachable in Step 3.1 |
| `failed` | Failed current stage or invalid/unavailable required evidence; protected files are retained |

The normalization decision stays in `normalization.decision`, alongside its
existing result fields. Decision and completion are one operation in the accepted
pipeline, so there is no speculative intermediate decision transition.

`last_successful_state` means the verified frontier of the **current chain**, not a
historical maximum. Explicit new attempts can move it backward. Pending/missing
stages stop advancement. Stale downstream revisions stop at their predecessor
and add a technical warning; they never reuse old success to advance progress.
Failed stages set `failed_stage`, `error_code`, `error_message` and advisory
`retryable`. Pending work has `active_stage`. Historical attempts remain in their
existing owned directories; this step neither discovers nor adopts orphan files.

There is no independent transition setter. `validate_transition` accepts only the
state already established by evidence. Supplied future-state claims are replaced
by the verified projection during canonical writes. Unknown states are refused.

## Schema and compatibility

The new fields are `updated_at`, `state_model_version`, `current_state`,
`last_successful_state`, `failed_stage`, `error_code`, `error_message`, `retryable`,
`active_stage`, `artifact_registry`, `progress_warnings`,
`selected_normalization_mode`, `selected_segmentation_mode`,
`segmentation_plan_identity`, `verified_part_count`, `package_status` and
`archive_status`. Existing session ID, creation time, profile, original audio,
visual count, mode/decision/result and stage pointer records remain authoritative.
Summaries are derived, not competing stage ownership.

`package_status.status` and `archive_status.status` are `not_implemented`.
Archive selection is copied from the accepted storage preflight; an unresolved
Lecture default stays unresolved. No archive default or skip/completion is
invented.

`status` projects legacy v1 metadata in memory without rewriting canonical JSON.
The next existing write upgrades it to v2 under the existing pipeline lock.
Generated attempt reports retain their schema-v1 shapes and bytes. Earlier
schema-v1-only code cannot read a newly written v2 session; validation/deployment
must use the complete upgraded source set.

Session ID must match the owned directory. Canonical updates compare creation
time and accepted original identity against the previous canonical record before
writing. Original filename, imported filename, managed path, source/imported size
and SHA-256 cannot silently change. Imported legacy state cannot be reset.
This is local metadata protection, not authentication against an external actor
replacing the entire JSON and original together.

## Artifact registry

The registry is an object keyed by stable `artifact_id`. Entries have `type`,
session-relative `relative_path`, `status`, `source_artifact_id`, `size_bytes`,
`sha256`, media summary, `created_at`, `verified_at`, `revision_id`,
`classification`, `protected` and `regenerable`. Parts also reference the approved
plan. IDs include attempt identities to distinguish derivatives across revisions.

| Classification | Types |
| --- | --- |
| Protected | `original_audio`, `session_metadata`; reserved `original_photo` |
| Regenerable, implemented registry entries | `normalized_audio`, `audio_part`, `normalization_report`, `segmentation_report`, `export_report` |
| Regenerable, reserved types only | `report`, `manifest`, `zip_package`, `full_archive` |

Artifact statuses are `pending`, `verified`, `failed`, `stale`, `unverified` and
`canonical`. Old derivative entries remain stale when their revision ceases to
be current. Published parts from an incomplete/failed export remain unverified
registry candidates, with `stage_part_status` preserving the export's individual
part result. They cannot advance overall state or verified part count.

Protected canonical metadata uses status `canonical` and **null size/hash**.
It never hashes itself. The independent generated stage reports happen to be
named `session.json` too; they contain no registry and can safely be hashed.
Applied normalized output and canonical parts are independently verified against
their size/hash references. File existence alone never establishes success.
There is no scanning, cleanup, deletion, resume/retry orchestration or packaging.
The types, source links and revisions leave those later steps possible.

`OwnedDirectory.atomic_json` remains the sole metadata writer. Only canonical
import records receive the projection; attempts retain frozen schemas. It checks
identity, writes a new exclusive temporary file, flushes/fsyncs, validates the
complete temporary JSON against the prepared record and the existing 1 MiB
canonical limit, then uses the existing atomic replace and directory sync.
Interrupted, corrupt, differing or oversized temporary metadata cannot replace
the last valid canonical JSON. Unrelated leftover temporary files are ignored.
In-memory stage objects retain their identity so pending/result updates remain
owned by the existing pipeline code.

All existing stages and status use `.inspection.lock`; no new lock owner or daemon
exists. Import still writes its newly allocated private session. Filesystem
access continues through owned directories and existing no-follow verification.

## Optional visuals and technical status

Zero photos is ordinary. No visual field is required beyond the existing count;
absence of visual subsystem data adds no warning. Optional attachment states are
`not_present`, `pending`, `indexed`, `partial_warning`, `failed_nonblocking`.
An optional visual failure never changes audio progress. An unknown optional
visual status may produce a diagnostic but does not block audio.

```sh
python -m recorandro status "$session_id"
# Equivalent installed entry point:
recorandro status "$session_id"
```

The command outputs JSON containing current/last state, active stage, audio
identity/media summary, normalization and segmentation results, verified part
count, registry, package/archive status, errors and warnings. Exit is 0 for a
readable nonfailed state (including pending), 1 for a failed state/access error,
and 2 for invalid configuration/argument parsing. It does not retry or process.
Status takes the existing lock and may create its lock file, but does not rewrite
canonical metadata or media. It freshly hashes current referenced media and reads
approved stage records; it does not run FFmpeg or repeat decode measurement.

The frozen import warnings remain stored. Status suppresses the fulfilled
`media_eligibility_pending` placeholder after current full-decode evidence exists.
Real remaining warnings stay visible, including provisional storage estimates.
Additional integrity reads during publication/status have a device performance
cost; real lecture/device timing remains to be measured.

## Actual host example

[Full example session.json](examples/step-3.1-session.json) and
[actual CLI status output](examples/step-3.1-status.json) are snapshots from a new
host-generated 3-second, 44100 Hz mono WAV sine fixture. Actual FFmpeg/ffprobe
ran import → probe → Auto normalization (+3 dB safe boost) → Auto single-part
plan → verified normalized-source byte-copy export. No tools were mocked in
this example. It is not the accepted Android lecture or new Android evidence.

Selected fields from the actual session JSON:

```json
{
  "schema_version": 2,
  "session_id": "5e038155215b404eb4910ce050399389",
  "state": "imported",
  "visual_count": 0,
  "state_model_version": 1,
  "current_state": "segments_exported",
  "last_successful_state": "segments_exported",
  "failed_stage": null,
  "error_code": null,
  "retryable": false,
  "selected_normalization_mode": "auto",
  "selected_segmentation_mode": "auto",
  "verified_part_count": 1
}
```

Selected fields from the actual technical status output:

```json
{
  "current_state": "segments_exported",
  "last_successful_state": "segments_exported",
  "normalization": {
    "status": "normalization_succeeded",
    "mode_requested": "auto",
    "decision": "low_level_safe_boost",
    "gain_db": 3.0,
    "output_source": "normalized",
    "normalization_applied": true
  },
  "part_count": 1,
  "errors": [],
  "warnings": [
    "storage_estimate_unverified",
    "gain_limited_target_may_remain_unmet",
    "constant_gain_raises_background_noise",
    "effective_bitrate_differs_from_requested"
  ]
}
```

The working fixture, config, media and full evidence also reside in ignored
`data/step-3.1-example/`. The source-review examples contain relative managed
references; they are snapshots, not an independently runnable media session.

## Verification and independent review handoff

Tests cover normal progression, unsupported transitions/forged claims, atomic
replace faults, interrupted and silently corrupt serialization, canonical size
limit, immutable original/session identity, registry classification, zero photos,
absent/nonblocking visual status, reload, read-only status, legacy v1 upgrade,
upstream revision invalidation, pending/failed/missing stages, corrupt media/report
evidence, partial exports, lock reuse and a real normalized derivative.

Two existing security tests now inject deliberately corrupt JSON directly rather
than asking the protected writer to change original/session identity. Their
original downstream rejection assertions remain. No accepted media expectation
was weakened or changed.

Final host run: **225/225 PASS**, zero failures, errors or skips, exit **0**,
**216.409 s** (`python -m unittest discover -s tests -v`). Python compilation
(`python -m compileall -q recorandro tests`) and `git diff --check` also PASS.
Host tools: **Windows, Python 3.12.10, FFmpeg/ffprobe 9.0.2-full_build-www.gyan.dev**.
Logs are in ignored `data/step-3.1-tests-confirmed.txt`. The real example's current
artifact sizes/hashes, saved status and unchanged canonical JSON after status
were also checked: **ALL_PASS**. Host evidence does not satisfy the
actual-device acceptance gate. Independent review should inspect all changed
files, the source/registry evidence gates, atomic publication and retained object
ownership before Android validation. No commit/push before both reviews and
explicit **FINAL PASS** authorization.

A candidate source-transfer ZIP is prepared in ignored
`data/step-3.1-review/recorandro-step-3.1-candidate.zip`, alongside its SHA-256.
It contains the complete 45-file source/documentation candidate, a review-info
record with every source file's SHA-256 and the 11 changed-file names, and the
final host test log. It excludes `.git`, local config, runtime media and session
data. This is a code-review/deployment transfer artifact; session ZIP packaging
remains unimplemented. Review it before deployment. No independent review or
actual Redmi/Termux Step 3.1 run is claimed.

## Redmi / ordinary Termux validation procedure — pending

Use a separate candidate source directory transferred as a reviewed source ZIP,
without `.git`, runtime config or managed media. Preserve the accepted source
directory and session data. Test in ordinary Termux without root:

```sh
python -m compileall -q recorandro tests
python -m unittest discover -s tests -v
```

Using the existing local config/data root, first inspect the accepted legacy
lecture **without reimporting, renormalizing, replanning or re-exporting it**:

```sh
python -m recorandro --config /path/to/existing/config.json status d0c39956c17943299dd17e67bf6d1d68
```

Expect legacy `state: imported`, derived `segments_exported`, last successful
`segments_exported`, three verified parts, Auto no-gain result, zero photos and no
visual warnings. Original duration must remain **3691.787029 s**, original hash
**9a3843145f2978defbf6a1afcb2b272abf77cbc520598573861b84682e5294ab**.
Compare canonical JSON SHA-256 before/after `status` to prove no rewrite; existing
source/part SHA-256 must remain unchanged. Capture the full status output and
elapsed time. Any disagreement needs investigation, not forced state advancement.

Then use a separate small fixture/session to run the existing import → inspect →
normalize → plan → export commands. Verify persisted v2 progress, registry entries,
reload and original identity on the device. Reuse the automated fault tests for
pending/failed/stale/corrupt cases; do not inject corruption into the accepted
lecture. Optional visual failure is covered by synthetic metadata tests only;
there is no visual subsystem in this step.

Report actual test counts, compilation, lecture status/integrity, fixture progression
and any additional I/O/performance observations for independent review. Manual
listening remains waived under PART 1; it is not counted as PASS here. Full Archive
Lecture default remains **OPEN**. Stop before recovery/retry design, manifests,
package creation, visuals or UI.
