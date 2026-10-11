# Manifest schema 1 — Step 4.1

This candidate adds operational documents only. No transcript, lecture interpretation,
ZIP, archive, photo processing or final UI is generated. Phase 3's accepted commit
`455db0b` was HEAD and the working tree was clean before implementation.

## Canonical data and display

`manifest.json` is the session model. Its fields are:

| Field | Meaning |
| --- | --- |
| schema_version | Integer 1, independent of session schema 2/state model 1 |
| session_id, profile, created_at | Existing canonical import values |
| title, course | Present only when supplied |
| original | Original filename, byte size and immutable SHA-256 |
| probe | Container, audio codec, sample rate, channels and original duration |
| normalization | Requested mode, applied/skipped, canonical decision reason, gain and source identities |
| segmentation | Mode/fulfillment/decision, policy version, single/segmented, target/window/useful-part limits, part count, overlap and tiny-part adjustments |
| source_revisions | Current inspection/normalization attempts, hashed plan identity and hashed export identity |
| timeline | Immutable original origin/duration, verified working-source endpoint, ownership duration and interpretation note |
| visual_count, visual_status | Zero and `none` are normal; later attachment metadata is optional and nonblocking |
| artifacts | Only current verified audio and stage report identities; never document hashes or session.json's hash |
| parts | Complete ordered array of canonical part models |
| storage_preflight | Recorded import, normalization and export estimates/decisions |
| integrity | Verified original/source/full set and canonical export coverage |
| completion | Audio verified, documents manifested; packaging/archive unimplemented, globally_complete false |
| warnings, errors | Sorted unique legitimate warnings; no errors in successfully verified audio documents |

Each part model has schema/session/index, filename/size/SHA-256, media summary,
source artifact identity, nominal start/end, global export start/end (numeric and
human forms), local start/end/duration, overlap before/after and a timeline note.
`media.duration_seconds` and `local_duration_seconds` preserve measured encoded
duration; they do not redefine global boundaries.

GLOBAL is relative to the immutable original lecture origin. Nominal intervals
partition the planned working source once, with no overlap or gaps. Export
intervals extend the **preceding** part's end by five seconds. The next nominal
start does not move. The final export ends at the exact verified source endpoint.
LOCAL playback starts at zero in each part. Overlap adds no lecture content.
`segmentation.overlap_seconds` records the frozen five-second policy for adjacent
parts; a single part's actual before/after overlap is zero, as its part model shows.
Normalization's permitted encoded-duration tolerance is represented by separate
original duration and working-source endpoint, never hidden by rounded display.

`manifest.md` embeds the same canonical JSON and displays its part table.
Per-part Markdown embeds its exact part model. `processing_report.md` renders
the same model's input, storage estimates, probe, decisions, part table,
integrity and warnings/errors. Its visual section is absent for zero photos.
Audio failure is rejected with an explicit technical error; no successful
manifest/report is published from a failed or incomplete audio chain. Existing
storage/archive warnings remain visible and are not presented as visual problems.

## Determinism

JSON is UTF-8, sorted keys, two-space indentation, finite numbers, final LF and
escaped backticks (JSON `\u0060`) for safe Markdown embedding. Source numeric
values retain their existing JSON precision. Human timestamps are HH:MM:SS.mmm,
decimal round-half-up; these display values never drive geometry. Markdown uses
UTF-8/LF and deterministic ordering/escaping. There are no generation timestamps
in documents. Canonical import `created_at` remains present. Attempt-journal
creation/verification timestamps are operational registry evidence only.

The SHA-256 of canonical session-model bytes is the source revision. It includes
accepted audio revisions and supplied metadata, excludes mutable `updated_at`,
document attempts, historical stale registry entries and document self-hashes.
Unchanged verified generation does not write any files or session metadata.

## Storage, publication, registry and recovery

The existing session kernel lock, `OwnedDirectory`, bounded JSON readers,
`atomic_json`, staged-file verification and no-replace `publish` remain owners of
safety. No additional lock, writer, registry or database is introduced.

The current `manifest_generation` pointer references
`generated/manifests/<attempt>/session.json`. This journal records schema/session/
attempt, status, source revision, operational times and a `files` mapping from
logical document names to relative paths, size, SHA-256 and verification status.
Logical names are `manifest.json`, `manifest.md`, `processing_report.md` and
`parts/part_NN/manifest.json` / `manifest.md` for every verified part.

The full-set pending journal is atomically saved before publishing the first
member. Members are written/fsynced under `temp/manifests-<id>/`, size/hash
verified, no-replace published and checked again. Only a succeeded journal,
matching canonical source revision, exact required member set and verified
canonical document bytes advance `segments_exported` to `manifested`.
All documents and their journal are regenerable registry artifacts, carrying
hash/size/times, export source artifact ID and model revision. Protected originals
and canonical session metadata retain their existing protection.

A partial attempt stays pending, with last success `segments_exported`. A damaged
previously successful document set becomes retryable; audio remains verified.
Resume/retry and `manifest-session` reuse individually verified model-matching
members, generate missing/invalid members under a new attempt and preserve old
files. The journal is the authoritative logical-name/path mapping: reused members
may live in earlier attempts. No directory scan or filename proves completion.
After all finals publish but before canonical metadata updates, generation adopts
the referenced journal's exact complete set without creating a new attempt.
Metadata persistence errors leave pending state; later resume revalidates bytes.
`manifested` is now the highest implemented frontier. Recovery `complete` means
only `implemented_audio_and_manifest_stages`, never global completion or packaging.

## Redmi/Termux validation

Transfer the reviewed changed source/tests/docs without `.git`; overlay the
existing development checkout, preserving its configured data root and sessions.
Do not re-import or run normalization, planning, export or general resume on the
accepted lecture for this validation. From the repository root:

```sh
python -m compileall -q recorandro tests scripts
python -m unittest discover -s tests -v > step4.1-tests.txt 2>&1
python scripts/validate_manifests.py \
  --session-id d0c39956c17943299dd17e67bf6d1d68 \
  --expected-parts 3 \
  --expected-original-sha256 9a3843145f2978defbf6a1afcb2b272abf77cbc520598573861b84682e5294ab \
  > step4.1-lecture-validation.json
python -m recorandro status d0c39956c17943299dd17e67bf6d1d68 > step4.1-lecture-status.json
```

The script honors normal config/environment precedence (`--config` is optional),
requires already verified audio, runs only manifest generation, compares original/
normalized/part/stage-report hashes before/after, checks registry integrity,
zero-photo/timeline semantics, and asserts a second generation preserves both
document hashes and session.json bytes. Expect `ALL_PASS: true`, state `manifested`,
three parts and preserved legitimate warnings. Initial canonical metadata changes
to register documents; repeated generation must not change it. Validation failure
raises an assertion and exits nonzero rather than inventing success.

To run the disposable controlled child-process interruption separately:

```sh
PYTHONPATH=tests python -m unittest \
  test_manifests.ManifestTests.test_controlled_child_death_after_publication -v
```

This creates its own disposable session with fixture audio evidence, pauses a
child after its first document publication, kills only that child, verifies audio
frontier, resumes documents and checks original safety. It does not touch the
accepted lecture or kill Termux. The full suite also retains all eight Phase 3
controlled real-audio interruption checks and tests actual applied/skipped
normalization with host/Android FFmpeg when available.

Independent review, actual Redmi validation and explicit FINAL PASS remain
required. Do not commit/push or proceed to ZIP packaging.
