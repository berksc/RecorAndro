# Step 3.2 local recovery and resume

This candidate extends the accepted Step 3.1 JSON records and registry. It uses
the existing stage implementations, owned directories, metadata writer and
session lock. No database, queue, daemon, native background service, manifests,
session packages, archives, visual recovery or final UI is implemented.

## Technical commands

```sh
python -m recorandro --config /path/to/config.json status "$session_id"
python -m recorandro --config /path/to/config.json resume "$session_id"
python -m recorandro --config /path/to/config.json retry "$session_id"
python -m recorandro --config /path/to/config.json retry "$session_id" normalization
```

Retry stage names are `inspection`, `normalization`, `segmentation`,
`audio_export`. Resume and retry without a stage run to the highest implemented
audio milestone. Retry with a stage runs only that required stage; an already
verified stage is a no-op, and a later stage is rejected until its prerequisite
verifies. Existing individual stage commands and their explicit modes remain
available. Recovery preserves recorded normalization/segmentation modes; absent
stage selections use the frozen Auto defaults. Invalid recorded modes are
refused rather than silently replaced.

The response's `classification` is an opening/recovery decision, not a second
persistent state model:

| Classification | Meaning |
| --- | --- |
| `resumable` | A verified prerequisite exists and the next stage is missing/pending. |
| `failed_retryable` | A derived stage failed or its evidence is missing/corrupt; the verified prerequisite is retained. |
| `failed_manual_attention` | Import never completed, original integrity/path failed, or canonical metadata cannot be validated. |
| `complete` | The implemented audio chain is verified through `segments_exported`. |

`completion_scope: implemented_audio_stages` makes the last classification
explicit. `current_state` never advances to future `manifested`, `packaged`,
`archived_or_skipped` or `complete` milestones. Package/archive statuses remain
`not_implemented`. A read-only `status` now includes this recovery classification;
it does not reconcile reports or process media.

## Decision and ownership algorithm

1. Acquire the existing session lock, safely load canonical `session.json`, and
   validate schema/session identity. Atomic metadata replacement preserves the
   last canonical record on interrupted writes. Temporary metadata is ignored.
   A missing/corrupted canonical record is retained for manual attention; no
   arbitrary temporary file is guessed to be a backup.
2. Use the Step 3.1 projection to verify the original's current size/hash and the
   current inspection, normalization, plan and export chain. Registry entries or
   filenames cannot establish success. The last successful state is the current
   verified frontier, not a historical success whose dependencies have changed.
3. For a pending pointer, read only the current attempt's exact owned report
   path. Validate session/attempt/mode identity. Completed reports may repair a
   lost canonical pointer only when the same source/revision/plan/part/coverage
   evidence gates verify the candidate chain. No directory scan adopts orphans.
4. Partial export reports supply reuse candidates to the existing export code.
   It matches source, normalization revision, approved plan hash, policy, modes,
   range geometry and encoding method, then rehashes/probes/fully decodes each
   reusable final file. Missing/corrupt candidates are generated in new owned
   attempts; verified parts retain their existing paths and bytes.
   A dangling completed report with a subsequently damaged part also supplies
   hashed reuse evidence, but its pointer remains pending until a complete set
   verifies. Obsolete source/plan reports are not reconciled. A recovery metadata
   publication error stops processing rather than regenerating already verified
   media merely because its pointer could not be saved.
5. Run the first unverified stage under the same lock. Reproject after every
   success. Source/revision changes deterministically make downstream registry
   entries stale and cause their required stages to rebuild. Old outputs and
   protected originals are retained. A verified complete resume makes no
   metadata writes and allocates no attempts or audio outputs.

Schema-v1 and schema-v2 accepted imports remain readable. Recovery never recopies
an imported original and never modifies its identity. An interrupted import
requires explicit source selection outside these commands; recovery does not
reconstruct an external source path or overwrite an existing managed original.
Zero photos and absent visual status remain ordinary, nonblocking cases.

## Lock and process death

All stages already use `.inspection.lock`; the filename is retained for
compatibility. On Termux/POSIX it uses nonblocking `flock`, and on Windows the
existing byte-range kernel lock remains. The lock stays held throughout the
resume chain. A private token lets stage functions reuse that ownership only for
the same session directory/inode, process, thread and active lifetime.

The kernel, rather than a PID file, owns liveness. Process death closes its lock
descriptor, releasing the lock. A stale filename is harmless and reusable;
recovery never unlinks a lock file, never decides liveness from PID absence, and
never removes another process's active lock. Duplicate acquisition returns the
existing `inspection_busy` error. Children running media tools do not inherit the
lock descriptor. These guarantees assume cooperating application processes on
the owned local filesystem; deleting/replacing a live lock externally is not an
application-supported operation.

## Existing publication and minimal changes

Normalization and part audio already use private temp directories, complete
media verification, fsync and atomic no-replace moves. Planning and attempt
reports already use atomic JSON writes. The canonical metadata writer remains
unchanged, including original/session identity protections and serialization
validation before fsynced atomic replace.

The added publication evidence closes the gap between those existing writes:

| Interrupted boundary | Recovery |
| --- | --- |
| Normalization generation/partial temp | Ignore temp bytes; retry normalization with the recorded mode. |
| Normalized final moved, canonical pointer pending | The existing attempt report carries a pending `publication_intent` result. Validate it using the same Step 3.1 source/media/final-file gates; only then publish a completed report and canonical pointer. |
| Planning generation | Retry planning from the verified working source. |
| Completed plan report, canonical pointer pending | Validate the referenced completed plan, repair its pointer, and retain the plan revision. |
| Part generation/partial temp | Ignore temp bytes; regenerate only unavailable parts. |
| Part final moved, report/canonical update incomplete | The existing pending report carries a `publication_ready` candidate with exact final path/hash/size/media/source/range evidence. The exporter independently verifies final bytes before reuse. |
| Entire export report completed, canonical pointer pending | Verify every required part and source/plan/coverage chain before repairing the completed pointer. |

Pending publication evidence is not a completed artifact registry entry.
Individual final parts never establish set success. Only the existing complete
export verification permits `segments_exported`. Legacy unjournaled or orphan
final files without sufficient evidence are retained but cannot be adopted;
recovery may need a new derivative in that case.

## Automated Redmi/Termux controlled interruption

Transfer the reviewed candidate source into a separate source directory. Preserve
the accepted deployment and lecture session. Run ordinary Termux without root:

```sh
python -m compileall -q recorandro tests
PYTHONPATH=tests python -m unittest test_recovery.ControlledInterruptionTests -v
env -u RECORANDRO_DATA_ROOT python -m unittest discover -s tests -v
RECORANDRO_DATA_ROOT="$TMPDIR/recorandro-unrelated-test-root" python -m unittest discover -s tests -v
```

The interruption tests create dedicated disposable three-second WAV sessions,
run real installed FFmpeg/ffprobe, and launch `tests/recovery_child.py`. Test-only
hooks pause at deterministic stage/publication boundaries (and write controlled
partial bytes for generation interruption). The parent waits for a marker,
attempts a duplicate resume, then kills/reaps only that Python child. It never
kills Termux or accesses the accepted lecture. Recovery reuses published verified
artifacts, finishes audio export, checks original SHA-256 and repeats resume to
prove canonical metadata remains byte-for-byte unchanged. Seven death boundaries
plus normalized-source corruption are covered. A multipart simulated crash also
checks that one published file out of three cannot be classified complete.

For the accepted lecture, `status` and an already-complete `resume` should retain
all original/stage/output hashes and attempt IDs. **Inspect its status first**;
if it reports damaged/unverified evidence, use a disposable copy for fault
investigation. Do not intentionally corrupt or interrupt the accepted session.
Expected accepted audio state remains `segments_exported`, three parts, original
duration 3691.787029 seconds, zero photos, and original SHA-256
`9a3843145f2978defbf6a1afcb2b272abf77cbc520598573861b84682e5294ab`.

## Evidence, limitations and review gate

Host results and an actual controlled-interruption transcript are recorded in the
Step 3.2 review evidence. The final Windows host run passed **250/250 tests**,
zero failures/errors/skips, exit 0, **338.053 seconds**, with an unrelated
`RECORANDRO_DATA_ROOT` exported. Compilation and tracked/new-file whitespace
checks passed. The 25 new tests include seven controlled child-death boundaries,
normalized-source damage, multipart partial publication, selective part rebuild,
stale source/plan rejection, metadata persistence failure, manual-attention
records, legacy v1 reuse, CLI classification and idempotence. Six focused tests
also passed with the data-root variable unset (two runs of three tests).

Actual disposable demonstration session `49ea695bd80a4b15b66a5593fed5c03c` was
interrupted after final part publication. The duplicate attempt returned
`inspection_busy`. Its verified frontier was `segmentation_planned` and its
classification `failed_retryable`. Resume reconciled the pending export report,
reused the published part and finished at `segments_exported`, one verified
part, `classification: complete`. Original SHA-256 was unchanged; repeated resume
performed no stages and left canonical JSON byte-for-byte unchanged. The
candidate source-transfer ZIP includes the full JSON transcript, final test log,
diff and source hashes under `review-info/`; it contains no managed session data
or `.git`. This ZIP transfers source for review/deployment, not session packaging.

Full device validation and independent review remain
pending. Kernel process-death tests do not prove durability under device power
loss, filesystem damage or arbitrary external edits. Hash/probe/decode checks
have I/O cost; real lecture performance remains to be measured. Orphan/temp
garbage collection and interrupted-import source reselection are intentionally
manual. Full Archive Lecture default remains OPEN. Manual listening remains
waived, not passed.

Stop before manifests, session packaging, archive processing, visuals or UI.
No commit/push or Step 3.3 without independent review, actual Redmi validation and
explicit FINAL PASS authorization.
