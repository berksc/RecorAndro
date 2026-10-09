# Step 2.2 — Auto / Force / Off normalization

Status: **Step 2.2 FINAL PASS**, accepted after actual-device validation on the
Xiaomi Redmi Note 10 Pro in ordinary non-root Termux. Accepted Android results
are recorded separately from the historical host fixtures below.
No segmentation, quiet-boundary analysis, part export, packaging, photo
processing, UI, server or cloud functionality is added.

## Baseline and preserved work

Started from clean `main` at `13dd400b85ad173bce7007b127bc194e091e2656`
(`2.1 - ffprobe media inspection`), matching local `origin/main` and read-only
live GitHub main. The accepted import, inspection, storage/configuration code,
existing 84 tests and frozen contracts are preserved. Recora normalization code
was read only as a historical reference, never imported at runtime.

Step 2.1 remains FINAL PASS, including the previously imported real lecture
`d0c39956c17943299dd17e67bf6d1d68`: 44941318 bytes, 3691.787029 seconds,
M4A/AAC, 44100 Hz mono, input stream bitrate 96000 bit/s. Those accepted facts
are not Step 2.2 processing evidence.

New files: `recorandro/normalization.py`, `tests/test_normalization.py`,
`tools/make_normalization_fixtures.py`, this guide. Updated: CLI and README.
No commit or push is performed.

## Decisions and Recora comparison

All new evaluations start from the verified managed original. Auto/Force fully
decode the selected stream through the discarded-output measurement filter
`loudnorm=I=-26:TP=-3:LRA=50:print_format=json`. Only **INPUT** measurements are
read: integrated LUFS, true peak dBTP, LRA LU, and threshold when supplied.
Numbers must be finite and within historical Recora limits [-120,100], with
nonnegative LRA. Literal `-inf` is the documented below-gate exception for
integrated loudness, peak and threshold. Finite integrated loudness with an
unknown peak fails. Missing threshold is null; malformed supplied threshold fails.

```python
desired = -26 - I
headroom = max(0, -3 - P)
gain = max(0, min(desired, 3, headroom))
gain = floor(gain * 1000) / 1000
if gain < 0.5:
    gain = 0
```

| Mode / condition | Decision |
| --- | --- |
| Auto (default), I >= -30 | `auto_already_usable_level`, no derivative |
| Auto, I < -30, useful safe gain | `low_level_safe_boost` |
| Auto, insufficient safe/useful gain | `insufficient_safe_gain`, no derivative |
| Auto, below measurement gate | `below_measurement_gate`, no derivative |
| Force, useful safe gain | `low_level_safe_boost`; bypasses only Auto's cutoff |
| Force, I >= -26 | `force_no_gain_at_or_above_target`, no derivative |
| Force, insufficient safe gain | `force_no_gain_insufficient_safe_gain`, no derivative |
| Force, below gate | `force_no_gain_below_measurement_gate`, no derivative |
| Off | `normalization_off`; full decode to null, no loudness filter or derivative |

Off records `evaluation_performed: false`, `evaluation_completed: false` and
successful `full_decode_verified: true`. Auto/Force record both evaluation flags
only as performed/completed. Successful skips have zero gain, no encoding,
`output: null`, `output_source: original` and the original working reference.
Clipped/full-scale input produces `input_possible_existing_clipping`; no repair
or attenuation occurs. Cap/headroom limits and background-noise amplification
are recorded as warning codes.

Retained Recora semantics: INPUT loudnorm measurement, target -26, strict -30
Auto cutoff, +3 cap, -3 planned peak headroom, 0.5 useful minimum, 0.001 downward
floor, constant double-precision volume, immutable skips, AAC/rate/channel rules,
fixed timing and encoded peak comparisons, original hash checks and pass timeout.
Intentional frozen RecorAndro differences: **Auto default**, **Force**, explicit
mode-specific reasons, and **finite encoded peak required**. Historical Recora
could allow a null output peak through its finite comparisons; this engine fails
that verification. No historical server state/layout is adopted.

## Eligibility, subprocess safety and artifacts

Requires a valid imported UUID session and current successful inspection whose
source/integrity records match the import. Uses the accepted managed path and
`OwnedDirectory` chain. Rehashes original bytes and checks pinned pathname/FD
identity, size/mtime (ctime on POSIX). A fresh restricted probe must match the
inspection's codec, demuxer, selected index, stream count, rate, channels and
duration (within 0.000001 seconds). Require positive finite duration >=0.000001,
7350–192000 Hz, mono/stereo, recognized selected stream, no known duration
contradictions or processing blockers. **Unresolved raw AAC duration uncertainty
is refused**, including Off. No filename, timestamp, byte size or creation tag
establishes duration. Full decode must succeed with the installed selected decoder.

The existing inspection lock serializes inspection and normalization in a session.
POSIX uses passed original/output file FDs and pinned temporary directory FDs via
`/proc/self/fd`, as in accepted inspection. Windows retains checked directories
and handles; it does not gain equivalent malicious same-user path-race guarantees.
No external Android source path is accepted or used after import.

Every FFmpeg pass uses argument arrays, `shell=False`, disconnected stdin,
`-nostdin -nostats -n -xerror`, file-only protocol, `mov,mp3,wav,aac` input
demuxers, `-err_detect explode`, explicit `-map 0:<absolute_index>`, and
`-vn -sn -dn`. MOV private options `-enable_drefs 0 -use_absolute_path 0` are
scoped by freshly probed **actual MOV family**, not suffix. This preserves the
documented host/Android capability behavior and protects permitted-family
mismatches. No shell, root, network input, auto-installation or option fallback.

Each measurement/decode/encode pass gets its own frozen timeout:
`min(21600, max(120, ceil(source_duration * 2 + 60)))` seconds. ffprobe remains
30 seconds. The real lecture gives **7444 seconds per FFmpeg pass**, not a total
run-time promise. stdout is discarded for FFmpeg; probe stdout is capped at
1 MiB. stderr drains concurrently into a private **64 KiB tail**, with a
**16 MiB total diagnostic limit per pass**; exceeding it fails safely. No raw
logs or unrestricted tool/media paths enter CLI/session error messages. No disk
spooling. Timeout/Ctrl-C kills and reaps the subprocess before returning failure.

For a useful boost, the only delivered filter is
`volume=<gain with exactly 3 decimals>dB:precision=double`. The encode uses
`-c:a aac -profile:a aac_low -b:a <128000 mono / 192000 stereo>`,
`-map_metadata -1 -map_chapters -1`, explicit output rate,
`-movflags +faststart -f ipod`. No `-ac` upmix/downmix and no quality-scale mode.
Preserve rates in `{7350,8000,11025,12000,16000,22050,24000,32000,44100,48000,
64000,88200,96000}`; other admitted rates convert to 48000 without speed change.
Effective bitrate is separately probed; differences warn and are not failure
merely because a requested bitrate is not exact.

```text
<data_root>/sessions/<session_id>/
  session.json                         # latest normalization attempt
  originals/audio/<accepted_original>  # unchanged
  generated/normalization/<attempt_id>/
    session.json                       # this attempt's atomic history record
    normalized.m4a                     # only after a verified useful boost
  temp/normalize-<attempt_id>/
    pending.m4a                        # temporary encoder output only
```

Each output/history directory is exclusively allocated by UUID. The temporary
directory is exclusive and FFmpeg creates an absent leaf with `-n`; preexisting
temporary leaves are refused and preserved. No skip creates an audio file.
Temporary audio is removed on caught encoding/verification failure. Empty owned
temporary directories and attempt metadata remain; abrupt process/device death
may leave a partial temporary file. No general recovery engine is introduced.

After successful encode: require nonempty regular output, pin/hash it, independently
probe profile and media, require one AAC-LC MOV-family stream at expected rate/
channels, check duration/start, then fully decode/measure its INPUT levels. Require
finite encoded true peak; **>-1 dBTP fails**, **>-2.9 dBTP warns**. Check output
identity/hash around verification, recheck original, flush generated bytes, make
the temporary read-only on POSIX, and publish `normalized.m4a` using the unchanged
`OwnedDirectory.publish` no-replace move. Android uses the accepted
`renameat2(RENAME_NOREPLACE)`; Windows uses its existing no-replace rename path.
Recheck the published inode/size/hash and original before accepting success.

Timing is **fixed**, never a percentage of lecture length:
`max(0.05, 2048/min(source_rate, output_rate))`. Require absolute duration delta
and output-stream start within this bound. The 44100 Hz lecture uses **0.05 s**.
No achieved -26 LUFS guarantee or universal delivered -3 dBTP sample ceiling is
claimed. Every source timeline interval, including silence, remains present.

## Current storage check

Import preflight is not a reservation. Before positive-gain encoding, measure
current free space again and budget this step's remaining writes:

```text
E = 30000 * ceil(actual_duration_seconds) + 65536
H = max(268435456, ceil(E / 5))
required = E + H
allow iff current_free >= required
```

Uses Step 1.2's conservative stereo requested-bitrate +25% allowance, container
allowance and headroom. Existing original/prior-output bytes are already reflected
in free space. Temporary and final derivative are the same inode after atomic
move, so they are not simultaneously full copies. No segmentation/archive budget
is spent or archive selection resolved here. This is provisional provisioning,
not reserved capacity or a disk-space guarantee; ENOSPC/flush failure still fails
the attempt safely. Off/no-gain does not reserve a nonexistent derivative.

## State, metadata and retry

Session `state: imported`, `audio`, successful `inspection`, preflight and archive
selection are preserved. `normalization` holds the latest attempt and separately
persisted attempt records preserve earlier outcomes/artifacts. Each new evaluation
uses the original, never a previous derivative; gain cannot accumulate on rerun.

| Field | Meaning |
| --- | --- |
| `schema_version`, `policy_version`, `attempt_id`, `mode_requested`, `retry_requested` | Versioned attempt identity and user request |
| `status` | `normalization_pending`, `normalization_succeeded`, or `normalization_failed` |
| `created_at`, `completed_at`, `elapsed_seconds` | UTC timestamps and monotonic processing elapsed time |
| `decision`, `gain_db`, `applied_gain_db` | Exact reason, planned gain, accepted applied gain |
| `evaluation_performed/completed`, `full_decode_verified` | Measurement evaluation and selected-source full-decode outcome |
| `encoding_performed` | Encode was attempted; it may have failed |
| `normalization_applied`, `encoding_applied` | A verified independent derivative was accepted |
| `input`, `input_levels` | Accepted original path/size/SHA-256, fresh media facts, inspection attempt and measured INPUT levels |
| `output`, `output_levels` | Null on skip/failure; accepted normalized path/size/hash/media/full-decode verification and measured encoded INPUT levels |
| `input_duration_seconds`, `output_duration_seconds` | Original/selected working durations, separately retained |
| `output_source`, `working_source` | Original or normalized on success; null on failure |
| `parameters` | Frozen constants, selected index, filter, timeout and requested encode properties |
| `duration_integrity`, `encoded_peak_safety`, `integrity.before/after` | Timing, finite encoded peak and original byte verification |
| `storage_preflight`, `warnings`, `error` | Current budget, warning codes, sanitized actionable error |

Probe `media.processing_eligibility.decoder` remains an inspection-only fact;
the enclosing artifact/attempt `full_decode_verified` records the subsequent
actual selected-stream decode. Missing optional values remain null. Failures do
not revoke immutable import or erase historical successful inspection facts;
normalization never treats those facts as current proof without its fresh checks.

Pending is atomically written before processing, replacing the latest pointer
without exposing partial successful metadata. Failed/pending attempts require
`--retry`. Exit codes: success **0**, session/processing failure **1**, argument/
configuration error **2**. Success includes valid skips. Prior outputs remain
accessible through their own attempt records when the latest attempt fails.

Recovery boundary: artifact move, attempt JSON and session JSON are **separate
atomic publications**, not a transaction. Failure after move may leave a verified
orphan; retain it and report failure rather than deleting/overwriting it. Attempt
success metadata can exist while the session's latest attempt is still pending
if session publication fails. Use the session latest status as the current result;
do not infer completed processing from file existence alone. Explicit retry gets
a new attempt directory. Directory-fsync failure after replace can leave a
complete record whose durability is uncertain; CLI still fails. Abrupt kill can
leave pending/partial files; kernel locks release automatically. Automatic orphan
reuse/recovery/pruning is deferred.

## Host results and examples

Windows Python 3.12.10, FFmpeg/ffprobe 9.0.2. **125 full host tests PASS, no
failures or skips** (84 existing + 41 Step 2.2), including guarded real WAV/M4A/MP3 fixtures, silence, stereo and rate
conversion. Policy/session faults use deterministic mocks; real helper processes
exercise bounded diagnostics and kill/reap cleanup. Timeout is injected into
wait for those helpers; this is not measured Android timeout behavior. All 84
accepted existing tests are retained. Full-suite evidence and checks are reported
in the final implementation response and ignored `data/step-2.2-tests.txt`.

Actual synthetic host examples (8-second 44100 Hz mono WAVs, not the lecture):

| Example | Input I / TP | Decision / gain | Encoded TP |
| --- | --- | --- | --- |
| Auto usable | -27.87 / -23.74 | `auto_already_usable_level`, 0 dB | No derivative |
| Auto quiet | -44.17 / -39.98 | `low_level_safe_boost`, +3 dB | -36.66 dBTP |
| Force usable | -27.87 / -23.74 | `low_level_safe_boost`, +1.87 dB | -21.77 dBTP |
| Force loud | -14.57 / -10.46 | `force_no_gain_at_or_above_target`, 0 dB | No derivative |
| Off quiet | Not measured | `normalization_off`, 0 dB | No derivative |
| Auto silent | Below gate | `below_measurement_gate`, 0 dB | No derivative |

Applied outputs: AAC-LC/M4A, 44100 Hz mono, 128000 bit/s requested, one stream,
8.0-second duration, zero start, 0.05-second timing tolerance, finite safe peaks.
Actual bitrate differences are recorded, not forced to the request. Original
705644-byte WAVs were independently hashed unchanged after each example. Full
JSON is in ignored `data/step-2.2-example/{auto-skip,auto-applied,force-applied,
force-no-gain,off,silent-auto}.json`; `cli-off.json` exercises the actual CLI.

## Accepted Android validation — FINAL PASS

The user accepted Step 2.2 FINAL PASS after validation on the Xiaomi Redmi
Note 10 Pro using ordinary non-root Termux:

- **125/125 Android tests PASS**, exit code **0**.
- **Python compilation PASS**.
- Successful normalization metadata was persisted and verified.
- Top-level session state remains **`imported`**.

| Android case | Accepted result | Gain | Derivative |
| --- | --- | --- | --- |
| Small quiet WAV, Auto | Gain applied successfully; verified AAC-LC/M4A, 44100 Hz mono, 8-second duration, full decode verified | +3.000 dB | Verified output |
| Small usable WAV, Auto | `auto_already_usable_level`, successful skip | 0 dB | None |
| Same usable session, Force | Gain applied successfully | +1.87 dB | Verified output |
| Quiet WAV, Off | `normalization_off`, successful no-gain result | 0 dB | None |
| Existing real lecture, Auto | `auto_already_usable_level`, successful skip; no errors or warnings | 0 dB | None |

The existing real lecture session
`d0c39956c17943299dd17e67bf6d1d68` completed without re-import. Its
**44,941,318-byte original and SHA-256 were independently verified unchanged**.
The successful normalization result was persisted and verified while preserving
the top-level imported state.

**Successful Auto Skip is a completed normalization evaluation, not applied
normalization.** The real lecture retained the original as its working source,
with zero gain, no encoding and no normalized derivative. Applied-normalization
evidence comes from the quiet Auto and usable Force fixtures.

Actual input loudness fields reside under **`normalization.input_levels`** in
CLI JSON (or `input_levels` within the normalization attempt), **not
`measurement`**. No numeric lecture loudness values or encoded lecture output
properties are inferred from the successful skip. The host example measurements
above remain host-only evidence.

The procedures below are retained for reproducibility; Android acceptance is
completed and does not require repeating validation or re-importing the lecture.

## Transfer reviewed changes without commit/push

From PowerShell in `C:\loxi\ReacorAndro`, package only this step's files:

```powershell
@'
from pathlib import Path
from zipfile import ZipFile
files = ['recorandro/normalization.py', 'recorandro/cli.py',
         'tests/test_normalization.py', 'tools/make_normalization_fixtures.py',
         'docs/SESSION_NORMALIZATION.md', 'README.md']
Path('data').mkdir(exist_ok=True)
with ZipFile('data/recorandro-step-2.2.zip', 'w') as archive:
    for name in files:
        archive.write(name, name)
'@ | python -
```

Transfer that ZIP through your existing file-transfer method to the phone's
Download directory. In ordinary Termux, from the existing `~/RecorAndro` checkout
(already containing accepted Step 2.1), extract only the expected files:

```sh
python - <<'PY'
from pathlib import Path
from zipfile import ZipFile
expected = {'recorandro/normalization.py', 'recorandro/cli.py',
            'tests/test_normalization.py', 'tools/make_normalization_fixtures.py',
            'docs/SESSION_NORMALIZATION.md', 'README.md'}
with ZipFile('/sdcard/Download/recorandro-step-2.2.zip') as archive:
    assert set(archive.namelist()) == expected
    for name in expected:
        destination = Path(name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(archive.read(name))
PY
python -m unittest discover -s tests -v
python -m compileall -q recorandro tools tests
```

Use existing Termux storage access; no new permissions, root, package installation
or overwrite/reset of the repository/session data is required. The ZIP replaces
only reviewed development files, including the CLI integration.

## Existing real lecture: Android validation

No re-import. In ordinary Termux from the repository root:

```sh
export RECORANDRO_DATA_ROOT="$HOME/recorandro-data"
session_id=d0c39956c17943299dd17e67bf6d1d68
stamp=$(date +%Y%m%d-%H%M%S)
normalization_result="$HOME/recorandro-lecture-auto-$stamp.json"
python -m recorandro normalize-session "$session_id" > "$normalization_result"
normalize_exit=$?
printf 'NORMALIZE_EXIT=%s\n' "$normalize_exit"
cat "$normalization_result"
```

Default Auto may validly skip or apply gain. Do not invent expected loudness from
the previous inspection's codec/bitrate or historical Recora mock lecture levels.
If applied, expected request is AAC-LC/M4A, 44100 Hz mono, **128000 bit/s**;
duration delta/start tolerance **0.05 s**. Exact measured bitrate/file size need
not match original/request. Check `input_levels`, reason, planned/applied gain,
peak verification, warnings, and elapsed time. Record Android suite counts and
command exits. Inspect any failure before retrying:

```sh
python -m recorandro normalize-session "$session_id" --mode auto --retry \
  > "$HOME/recorandro-lecture-auto-retry-$(date +%Y%m%d-%H%M%S).json"
printf 'RETRY_EXIT=%s\n' "$?"
```

Independent integrity/result check, using the successful result file:

```sh
python - "$normalization_result" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
r = json.loads(Path(sys.argv[1]).read_text())
assert r['ok'] and r['session_id'] == 'd0c39956c17943299dd17e67bf6d1d68'
n = r['normalization']
d = Path(os.environ['RECORANDRO_DATA_ROOT']) / 'sessions' / r['session_id']
s = json.loads((d / 'session.json').read_text())
assert s['state'] == 'imported' and s['visual_count'] == 0
assert s['normalization'] == n and n['status'] == 'normalization_succeeded'
assert s['inspection']['status'] == 'probed'
original = d / s['audio']['managed_path']
with original.open('rb') as stream:
    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
assert original.stat().st_size == s['audio']['size_bytes'] == 44941318
assert digest == s['audio']['sha256'] == n['input']['sha256']
for phase in ('before', 'after'):
    assert n['integrity'][phase]['status'] == 'verified'
    assert n['integrity'][phase]['sha256'] == digest
print('ORIGINAL_SIZE_HASH_PASS:', True)
print('DECISION:', n['decision'], 'GAIN:', n['gain_db'])
print('INPUT_LEVELS:', n['input_levels'])
print('WARNINGS:', n['warnings'])
if n['output']:
    out = d / n['output']['managed_path']
    with out.open('rb') as stream:
        output_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    assert output_hash == n['output']['sha256']
    assert out.stat().st_size == n['output']['size_bytes'] > 0
    m = n['output']['media']
    assert m['audio_codec'] == 'aac' and m['codec_profile'] == 'LC'
    assert m['sample_rate'] == 44100 and m['channels'] == 1 and m['stream_count'] == 1
    assert n['duration_integrity']['passed'] and n['duration_integrity']['tolerance_seconds'] == 0.05
    assert n['encoded_peak_safety']['passed'] and n['encoded_peak_safety']['true_peak_dbtp'] <= -1
    print('DERIVATIVE_HASH_PASS:', True)
    print('DERIVATIVE:', out)
    print('OUTPUT_MEDIA:', m)
    print('OUTPUT_LEVELS:', n['output_levels'])
else:
    assert not n['encoding_applied'] and not n['normalization_applied']
    assert n['output_source'] == 'original' and n['gain_db'] == 0
    print('VALID_NO_GAIN_ORIGINAL_SOURCE:', True)
PY
```

The saved Step 1.2 import SHA-256 can also be compared via
`$HOME/recorandro-lecture-import.json`; no external audio file is read.
Keep that baseline/result and the new result for independent review. After retry,
point `normalization_result` at the actual successful retry file.

## Safe short Force / Off fixtures on Android

Generate synthetic fixtures in a new directory; this never changes lecture data:

```sh
fixture_root="$HOME/recorandro-normalization-fixtures-$(date +%Y%m%d-%H%M%S)"
python tools/make_normalization_fixtures.py "$fixture_root" \
  > "$HOME/recorandro-normalization-fixtures.json"
python - "$fixture_root" <<'PY'
import json, sys
from pathlib import Path
from recorandro.config import load_config
from recorandro.sessions import import_audio
from recorandro.inspection import inspect_session
from recorandro.normalization import normalize_session
config = load_config()
for fixture, modes in [('usable', ('auto','force')), ('quiet', ('auto','off')),
                       ('loud', ('force',)), ('silent', ('auto','force'))]:
    s = import_audio(config, Path(sys.argv[1]) / (fixture + '.wav'),
                     provision_seconds=60, archive='not_requested', title='Synthetic '+fixture)
    inspect_session(config, s['session_id'])
    for mode in modes:
        n = normalize_session(config, s['session_id'], mode=mode)
        path = Path.home() / ('recorandro-fixture-'+fixture+'-'+mode+'-'+n['attempt_id']+'.json')
        path.write_text(json.dumps({'ok': True, 'session_id': s['session_id'],
                                    'normalization': n}, indent=2))
        print(fixture, mode, n['decision'], n['gain_db'], path)
PY
```

Check usable Auto skip vs Force useful boost, loud Force no-gain, silent no-gain,
quiet Auto boost and Off no measurement/no derivative. Device measurements can
vary slightly; assert frozen decisions using actual measured values, not exact
host loudness numbers. Fixture imports are new synthetic sessions only, not
re-imports of the real lecture.

## Listen to beginning / middle / end of an accepted derivative

Use a successful applied result, either the lecture's or a short fixture's.
If Auto skipped the lecture, there is no normalized lecture file to listen to;
use the verified quiet/Force fixture derivative instead. Locate it from result
metadata and create disposable **listening previews outside managed storage**:

```sh
python - "$normalization_result" <<'PY'
import json, os, subprocess, sys, time
from pathlib import Path
r = json.loads(Path(sys.argv[1]).read_text())
n = r['normalization']
assert r['ok'] and n['status'] == 'normalization_succeeded' and n['output']
source = Path(os.environ['RECORANDRO_DATA_ROOT']) / 'sessions' / r['session_id'] / n['output']['managed_path']
duration = n['output_duration_seconds']
length = min(12.0, duration)
previews = Path.home() / ('recorandro-listening-'+str(time.time_ns()))
previews.mkdir(exist_ok=False)
for name, start in [('beginning', 0), ('middle', max(0, (duration-length)/2)),
                    ('end', max(0, duration-length))]:
    target = previews / (name+'.wav')
    subprocess.run([os.environ.get('RECORANDRO_FFMPEG','ffmpeg'), '-hide_banner', '-nostdin',
                    '-n', '-v', 'error', '-xerror', '-protocol_whitelist', 'file',
                    '-format_whitelist', 'mov,mp3,wav,aac', '-enable_drefs', '0',
                    '-use_absolute_path', '0', '-err_detect', 'explode', '-ss', str(start),
                    '-i', str(source), '-map', '0:0', '-vn', '-sn', '-dn', '-t', str(length),
                    '-c:a', 'pcm_s16le', str(target)], shell=False,
                   stdin=subprocess.DEVNULL, timeout=120, check=True)
    print(target)
PY
```

These bounded excerpts are optional listening diagnostics, not a segmentation/
part-export implementation or processing artifacts. They only read an accepted
derivative; they never write the managed original/derivative. Listen for audible
content, retained pauses, clipping and beginning/end coverage using your existing
player method. If `termux-media-player` is already available, run
`termux-media-player play "<printed preview path>"`; no installation is required
by the engine. Listening is supplementary, not a replacement for timing/hash/
full-decode/peak checks. Preserve device results for independent review.

Step 2.2 has received **FINAL PASS** with the accepted Android evidence above.
**No segmentation or commit/push until separately authorized.**
