# Step 2.1 — managed-original media inspection

Status: **Step 2.1 FINAL PASS — actual-device validation completed and accepted**.
Host evidence and accepted Android evidence are recorded separately below. No normalization,
segmentation, full decoding, conversion, photos or packaging is implemented.

## Verified baseline and scope

Started from clean `C:\loxi\ReacorAndro`, branch `main`, HEAD and local
`origin/main` `73167b1af9b90bd393c91ecc53a4a2e3343b88b0` (finalized Step 1.2).
Read-only live `git ls-remote origin refs/heads/main` also matched this commit.
The initial sandbox network call could not resolve GitHub; the permitted
read-only call subsequently verified it. No commit, push or reset was performed.

The authoritative scope/media/behavior/parity/device/Step 1.1/import documents,
README, implementation and tests were inspected. Frozen contracts take precedence.
Recora `app/audio.py` was read only for exact probe fields and numeric semantics;
RecorAndro has no runtime dependency on that repository.

Changed files: `recorandro/inspection.py`, `recorandro/cli.py`,
`tests/test_inspection.py`, this guide and README. Import, storage/publication,
configuration and frozen contracts are unchanged.

## Technical interface and state

```sh
python -m recorandro inspect-session "$session_id"
python -m recorandro inspect-session "$session_id" --retry
```

Uses existing configuration, including `RECORANDRO_DATA_ROOT`,
`RECORANDRO_FFPROBE`, and global `--config`. No external source argument exists.
Exit 0 means a complete, persisted inspection; exit 1 means inspection/session
failure; configuration/argument errors retain exit 2. Exit 0 does not certify
decodability or processing readiness. Warnings and blockers are explicit JSON.

The top-level session schema remains v1 and `state: imported` remains the
accepted byte-import fact. The `audio` record, import warnings, preflight and
archive selection are preserved. The legacy `media_eligibility: not_inspected`
field remains an import-time placeholder; technical inspection facts now live
in `inspection`. Neither field can certify processing readiness.

| Inspection representation | Meaning |
| --- | --- |
| Absent | Existing Step 1.2 original has not been inspected. |
| `status: probe_pending` | New attempt atomically recorded, with `media: null`; older success invalidated. An interrupted attempt is incomplete. |
| `status: probed` | Tool output parsed and original integrity passed before/after; warnings may still block processing. |
| `status: probe_failed` | Current attempt failed; imported-original identity remains recorded; previous success cannot be reused. |
| `retry_requested: true` | Caller explicitly supplied `--retry`, recorded on the new attempt. |

Failed/pending attempts require `--retry`. Calling inspection again on a probed
session starts a fresh attempt; it never returns a cached success without
rechecking. Each attempt gets a UUID. No attempt history/workflow engine exists.
An owned `.inspection.lock` uses kernel advisory locking (POSIX flock; Windows
byte lock) to reject concurrent inspections. The empty lock file stays owned;
the kernel releases the lock on normal close or process death.

Pending and final records use the unchanged `OwnedDirectory.atomic_json` writer.
If pending publication fails, no original access/tool execution occurs and the
previous record remains. If final publication fails, pending remains incomplete
and the CLI fails. Filesystem directory-sync failure after replace can leave a
complete replaced record with uncertain durability; the CLI still reports failure.

## Schema v1

Missing optional values are JSON null. Only whitelisted fields are persisted;
unknown ffprobe fields, arbitrary tags and raw stderr are excluded.

| Inspection fields | Content |
| --- | --- |
| `schema_version`, `implementation_version` | `1`, `step_2_1_v1` |
| `status`, `probe_status` | Inspection status above; tool status `not_run`, `running`, `succeeded`, or `failed`. Tool success can accompany parser/integrity failure. |
| `attempt_id`, `retry_requested`, `inspected_at`, `completed_at` | Attempt identity, explicit retry, UTC ISO timestamps (start/completion). |
| `source.actual_size_bytes`, `expected_size_bytes`, `imported_sha256` | Opened regular-file filesystem size and accepted import size/hash. |
| `integrity.before`, `integrity.after` | `verified` with actual read bytes/hash, `failed` with code, or `not_checked` if safe access was unavailable. |
| `media` | Parsed facts from this attempt, or null. On failure, any retained current facts are diagnostic only. |
| `warnings`, `error` | Warning codes; null or sanitized actionable `{code, message}`. |
| `processing_eligibility` | `unverified` or `blocked`, blocker list, always `decoder: unverified`. Never `ready`. |

`media` contains `container_format`, `demuxer_family`,
`selected_audio_stream_index` (absolute index), `stream_count` (all streams),
`audio_codec`, `sample_rate`, `channels`, `channel_layout`, `stream_bitrate`,
`container_bitrate`, `duration_seconds`, `duration_human`, `duration_source`,
`duration_estimates_seconds` (`stream`, `stream_time_base`, `container`),
`duration_ts`, `time_base`, `duration_consistency` (comparison tolerance and
disagreements), separate stream/container start seconds,
`container_reported_size_bytes`, `creation_time`, warnings and metadata blockers.
The inspection-level eligibility also accounts for tool/integrity failures.

Creation tags are retained as strings with `trusted: false` and
`informational_only: true`. They never establish recording start or modify
audio-relative zero. Container-reported size is only diagnostic; it is compared
to filesystem size and is never used to validate the import.

## Preserved semantics and safeguards

- Resolve only exact `originals/audio/<imported_filename>` from a matching
  schema-v1 imported UUID session. Validate safe leaf, suffix, accepted size/hash,
  regular file and owned directory chain; reject traversal, symlinks/reparse
  points, malformed session metadata and invalid stream indices.
- Before probing, compare opened inode/device/size/mtime (also ctime on POSIX)
  to the pinned managed pathname. Hash in 1 MiB chunks and require accepted
  size/SHA-256. Repeat identity/size/hash verification after probing in `finally`,
  including missing-tool, timeout, parser failure and caught interruption paths
  where an original was safely opened. Changed identity fails closed even when
  rehashing the replacement cannot establish the original's identity.
- On POSIX, pass the verified read-only file descriptor to ffprobe with
  `pass_fds` and `/proc/self/fd/<fd>`. It reads the verified inode rather than a
  replaceable session pathname. This is an internal kernel FD reference, never
  a supplied path/URL or an arbitrary managed symlink. Require its availability
  on ordinary Termux; there is no weaker fallback. Windows uses the existing
  checked-path approach and a retained read handle, without claiming POSIX
  descriptor guarantees against malicious same-user replacement.
- Exact Recora `-show_entries` selection; arguments as an array, `shell=False`,
  disconnected stdin, `-v error`, `-protocol_whitelist file`,
  `-format_whitelist mov,mp3,wav,aac`, `-enable_drefs 0`,
  `-use_absolute_path 0`, `-of json`, and **30-second tool timeout**.
  MOV options apply regardless of suffix, protecting permitted-family mismatches.
  All these options passed real Windows fixtures; Step 1.1 established Android
  restrictions, and Step 2.1's full invocation with a passed FD successfully
  inspected the existing real lecture in ordinary Termux on Redmi. No option
  fallback, auto-installation, shell, root or network input.
- Stdout and stderr drain concurrently: retain at most **1 MiB stdout** and
  **64 KiB stderr**, kill on excess, reject truncated output. No disk spooling;
  stderr is private and discarded, never added to CLI JSON/logs. Nonzero exits,
  missing tools, timeouts, malformed/duplicate-key/oversized JSON and bad
  metadata structures fail. A zero exit alone does not validate media.
- First recognized audio stream in output order; skip non-audio and missing/
  `unknown` codecs. Do not select by bitrate/disposition or silently advance past
  a recognized stream with invalid metadata. Save absolute index and all-stream
  count. Naming another recognized codec never certifies its installed decoder.
- Suffix admission and actual allowed demuxer remain separate. MOV aliases
  (`mov,mp4,m4a,3gp,3g2,mj2`) identify one permitted family. Permitted-family
  mismatch warns; unsupported demuxer fails.
- Positive finite duration minimum **0.000001 s**; precedence is stream duration,
  ticks times rational time base, container duration. Preserve all available
  accepted estimates and their provenance. Invalid supplied numbers are excluded
  with `invalid_<stream/container>_<field>` warnings. Booleans, nonfinite numbers,
  fractional integer fields, malformed/nonpositive rationals and magnitudes
  beyond Recora's `2**53` limit never become accepted numeric facts.
- Preserve `duration_no_independent_cross_check` when fewer than two estimates
  exist. If only direct/tick estimates from the same stream exist, additionally
  warn `duration_cross_check_same_stream_only`. Any positive estimate differing
  by **more than** `max(1 s, selected_duration * 0.01)` records
  `duration_disagreement` and blocks later processing; no guessed replacement.
- Missing duration, sample rate outside 7350–192000 Hz, or channels other than
  one/two are faithfully reported with processing blockers. Inspection success
  is separate from eligibility. Raw AAC always records
  `raw_aac_duration_unverified` and `raw_aac_duration_verification_required`;
  even agreeing metadata cannot overcome the accepted six-second/63.67-second
  observation. No duration correction or full-decode claim is made here.

Other warnings: `suffix_demuxer_mismatch`, `container_reported_size_mismatch`,
`duration_unavailable`. Decoder verification, current storage checks, unresolved
archive choice and all later processing gates remain future requirements.
Zero photos remains complete; no photo metadata is accessed.

## Accepted actual-device Step 2.1 evidence

The user supplied the following verified evidence from the **Xiaomi Redmi Note
10 Pro**, running ordinary **non-root Termux**, and confirmed **Step 2.1 FINAL
PASS** after actual-device validation. This is accepted device evidence, not
inferred from Windows fixtures or a device run performed by Codex.

| Check / property | Accepted result |
| --- | --- |
| Android test suite | **84/84 PASS**, exit code **0** |
| Existing real lecture session | `d0c39956c17943299dd17e67bf6d1d68`; previously imported M4A inspected successfully **without re-import** |
| Original / managed size | **44,941,318 bytes** each |
| Inspection / probe status | `probed` / `succeeded` |
| Container / codec | M4A/MOV / AAC |
| Sample rate / channels | **44100 Hz** / **1 (mono)** |
| Selected absolute audio index / total streams | **0** / **1** |
| Stream bitrate | **96000 bit/s** |
| Duration | **3691.787029 seconds** (`01:01:31.79`) |
| Duration consistency | All three available estimates agree; user independently confirmed duration matches the original recording |
| Original integrity | Verified before and after probing; SHA-256 matched the accepted import record |
| Inspection warnings / errors | None |
| Decoder eligibility | **Unverified**, as expected for inspection only |

This accepts the managed-original inspection step, including the ordinary-Termux
FD handoff and successful real-lecture inspection. It does not certify full
decoding or authorize normalization/segmentation. No SHA-256 value or additional
device measurements are invented; the supplied evidence establishes equality.
Frozen contracts, accepted import/publication semantics and implementation remain
unchanged. The documentation-only finalization updates this guide and README.

## Repeatable actual lecture validation in ordinary Termux

Transfer the reviewed changed files to the existing Termux checkout through your
normal development transfer method. No commit/push or re-import is needed.
The preceding Android validation chat recorded the successful lecture result at
**`$HOME/recorandro-lecture-import.json`**. The accepted Step 2.1 session ID is
`d0c39956c17943299dd17e67bf6d1d68`; the procedure still reads the existing result
to identify the managed original. Never substitute a host fixture ID. These
commands remain available for repeat checks; validation is already accepted.
Run from the existing Termux repository root:

```sh
export RECORANDRO_DATA_ROOT="$HOME/recorandro-data"
python -m unittest discover -s tests -v
python -m compileall -q recorandro tools tests

result="$HOME/recorandro-lecture-import.json"
session_id=$(python - "$result" <<'PY'
import json, re, sys
from pathlib import Path
r = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
s = r['session']
assert r['ok'] and s['state'] == 'imported'
assert s['audio']['size_bytes'] == 44941318
assert re.fullmatch(r'[0-9a-f]{32}', s['session_id'])
print(s['session_id'])
PY
) || exit 1
printf 'Existing Android lecture session: %s\n' "$session_id"

stamp=$(date +%Y%m%d-%H%M%S)
inspection_result="$HOME/recorandro-lecture-inspection-$stamp.json"
python -m recorandro inspect-session "$session_id" > "$inspection_result"
inspect_exit=$?
printf 'INSPECT_EXIT=%s\n' "$inspect_exit"
cat "$inspection_result"
```

If failed, review the sanitized error. After the cause is resolved, explicitly
retry the same session (retain the initial evidence):

```sh
retry_result="$HOME/recorandro-lecture-inspection-retry-$(date +%Y%m%d-%H%M%S).json"
python -m recorandro inspect-session "$session_id" --retry > "$retry_result"
printf 'RETRY_EXIT=%s\n' "$?"
cat "$retry_result"
```

No command reads `/sdcard/Download/lecture-test.m4a`, requests storage permission,
invokes `su`, changes the archive selection, or deletes/re-imports the lecture.
Do not run controlled failure experiments against the real lecture; host tests
already exercise those. If the saved result is unavailable, locate the existing
result rather than inventing a UUID or importing again.

## Comparison procedure

Use the success result (set `inspection_result="$retry_result"` if retry succeeded).
Read the current persisted inspection, independently rehash the managed original
and compare to the historical accepted import JSON:

```sh
python - "$result" "$inspection_result" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
accepted = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))['session']
r = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
assert r['ok'] and r['session_id'] == accepted['session_id']
root = Path(os.environ['RECORANDRO_DATA_ROOT'])
directory = root / 'sessions' / accepted['session_id']
current = json.loads((directory / 'session.json').read_text(encoding='utf-8'))
assert current['state'] == 'imported' and current['audio'] == accepted['audio']
assert current['visual_count'] == 0
assert current['storage_preflight'] == accepted['storage_preflight']
i = r['inspection']
assert i == current['inspection'] and i['status'] == 'probed'
path = directory / current['audio']['managed_path']
with path.open('rb') as stream:
    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
assert path.stat().st_size == accepted['audio']['size_bytes'] == 44941318
assert digest == accepted['audio']['sha256'] == i['source']['imported_sha256']
for phase in ('before', 'after'):
    check = i['integrity'][phase]
    assert check['status'] == 'verified'
    assert check['actual_size_bytes'] == 44941318 and check['sha256'] == digest
print('Size/hash before, after and independent recheck: PASS')
print('Recorded SHA-256:', digest)
m = i['media']
for key in ('container_format', 'selected_audio_stream_index', 'stream_count',
            'audio_codec', 'sample_rate', 'channels', 'channel_layout',
            'duration_seconds', 'duration_human', 'duration_source',
            'duration_estimates_seconds', 'duration_consistency',
            'stream_bitrate', 'container_bitrate', 'container_reported_size_bytes'):
    print(key + ':', m[key])
print('Warnings:', i['warnings'])
print('Processing/decoder eligibility:', i['processing_eligibility'])
print('Archive selection:', current['storage_preflight']['archive']['resolved'])
PY
```

Compare `duration_human` and the individual estimates to the recorder's displayed
duration, allowing for its display rounding. A larger unexplained discrepancy
requires evidence/review; do not alter metadata to match the UI. Compare codec,
sample rate and channels to the recorder/export technical properties where
available; M4A suffix alone is not proof of AAC/rate/channel values. Preserve
the reported stream index/count and all warnings for independent review.
Container size differences are diagnostic; the **44941318 actual/imported bytes
and SHA-256 equality** are authoritative. If recorder details are unavailable,
state that limitation rather than claiming an independent comparison passed.

## Host evidence and acceptance boundary

Windows Python 3.12.10, ffprobe/FFmpeg 9.0.2: **84 tests PASS, no skips**
(47 existing + 37 Step 2.1); `python -m compileall -q recorandro tools tests`
and `git diff --check` pass. New-file trailing whitespace was checked separately.
Ignored full test output is `data/step-2.1-tests.txt`.
Real executable fixtures exercise PCM/WAV, AAC/M4A, MP3, raw AAC, malformed media
and MOV under a WAV suffix. Other cases use deterministic parser/session mocks;
helper processes exercise hard output caps and cleanup. The 30-second timeout
failure is injected into the wait call with real helper-process cleanup, not
a measured 30-second Android timeout. Windows replacement identity is injected
because its open read handle rejects the real replacement; POSIX tests perform
the real owned pathname replacement when run on that platform.

Ignored local host examples: `data/step-2.1-example/success.json`,
`controlled-failure.json` (configured missing ffprobe; exit 1, before/after
integrity verified, original retained), and `retry-success.json` (exit 0).
These are synthetic one-second WAV results, not the real Android lecture.

The POSIX FD handoff/locking/directory branch has not run on this Windows host.
Actual ordinary-Termux execution, the real lecture metadata and the user's
independent duration comparison are accepted separately in the device evidence
above. **Step 2.1 FINAL PASS** is based on that actual-device validation, not host
simulation. Decoder eligibility remains unverified. Stop here; normalization
and segmentation remain unimplemented.
