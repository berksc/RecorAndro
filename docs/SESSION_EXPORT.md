# Session audio export — Step 2.4

Exports actual audio from the latest completed Step 2.3 plan. This is a reusable
local operation, `recorandro.exports.export_session(config, session_id,
retry=False)`, with a temporary technical CLI:

```sh
python -m recorandro export-session "$session_id"
python -m recorandro export-session "$session_id" --retry
```

The result is JSON: `ok`, `session_id`, and `audio_export` (the attempt record).
Exit 0 means a complete verified export; exit 1 means failure; argument/config
errors retain the existing exit 2 convention. No external input path, mode
override, automatic replanning or re-normalization is accepted. The operation
does not depend on terminal interaction and can be called by a later graphical
app. No UI, ZIP, final delivery manifest or packaging is implemented.

The frozen [media](MEDIA_CONTRACT.md) and [behavior](BEHAVIOR_CONTRACT.md)
contracts govern this operation. The accepted importer, inspector, normalizer,
segmentation planner and owned-directory publication mechanism are unchanged.

## Approved plan and working source

The latest session `segmentation` pointer must have status `planned`, a valid
attempt identifier, the exact managed record path and its SHA-256. Its bounded
record must match the session, attempt, mode/count/decision, source reference,
integrity evidence and nominal geometry. Pending, failed, missing, changed or
inconsistent records fail closed. Earlier plans are never substituted.

The current completed normalization revision must select the same artifact as
the saved plan. Applied gain selects its verified immutable `normalized.m4a`;
Off and successful no-gain Auto/Force select the managed original. A new
normalization evaluation makes an older plan stale even when it selects the
same original bytes. No new gain is applied during export.

The operation uses the existing session lock and `OwnedDirectory` protections.
It opens the managed original and selected source read-only, verifies filesystem
identity, actual size and SHA-256, and freshly probes their selected stream,
codec, demuxer, rate, channels and duration. Processing blockers, unsupported
media and unresolved raw AAC timing uncertainty remain refusals. The freshly
verified working duration must equal the approved plan endpoint exactly.
External upload paths and creation-time tags are never used.

Original and working durations are recorded separately. Normalization's allowed
codec timing delta does not shift global zero. Global ranges remain relative to
the original first decoded sample; measured local output durations do not
replace those ranges or claim exact sample identity after lossy encoding.

## Frozen media and overlap policy

New encodes use native FFmpeg `aac`, AAC-LC (`aac_low`), M4A (`-f ipod`) with
`+faststart`, explicit 128000 bit/s mono or 192000 bit/s stereo. Preserve channels.
Preserve source rates 7350, 8000, 11025, 12000, 16000, 22050, 24000, 32000,
44100, 48000, 64000, 88200 and 96000 Hz; other admitted rates become 48000 Hz
without a speed change. Map only the selected absolute audio stream, strip
metadata/chapters, and exclude video, subtitles and data.

A full-length one-part, exactly one-stream AAC/`.m4a` or MP3/`.mp3` source is
copied into a new independent file. This exception preserves exact bytes,
profile, metadata, size, SHA-256 and duration. It is never a hardlink, alias or
FFmpeg packet stream copy. Other single outputs and every multi-part output
are canonical AAC-LC/M4A encodes. Filenames are `part_01.m4a`, `part_02.m4a`,
etc., padded to at least two digits; the compatible MP3 copy is `part_01.mp3`.

For approved nominal boundaries `b_0=0 < ... < b_N=D`, exported part `i` is:

```text
[b_(i-1), min(D, b_i + 5 seconds)]
```

The next start stays at `b_i`. This is **five seconds total shared context**,
extending the preceding end only. No start is shifted backward. Starts cannot
be negative and ends cannot exceed `D`; first start is zero and final end is
exactly `D`. The accepted useful-part minimum ensures five seconds are available
at every internal boundary. Single-part overlap is zero. Nominal ownership
intervals are half-open except for the final source endpoint. The planner and
its tiny-tail adjustments are consumed unchanged.

Each encoded output decodes independently from the same full working source:

```text
start_sample = round(global_start_seconds * source_rate)
end_sample = round(global_end_seconds * source_rate)
atrim=start_sample=<start_sample>:end_sample=<end_sample>,asetpts=PTS-STARTPTS
```

Python nearest-integer/ties-to-even rounding has a 0.5/source_rate second
allowance per endpoint. Empty rounded ranges fail. No packet seeking, `-ss`,
`-t`, gain, silence deletion, compression, denoising or tempo change occurs.

## Verification, storage and publication

Every new output must be nonempty regular audio, pass an independent ffprobe
and fully decode to null with FFmpeg error-failing options. Require one expected
audio stream, the correct codec/container/rate/channels, and AAC-LC for encodes.
For an encode, both duration error and absolute stream start must be at most:

```text
max(0.05 seconds, 2048 / min(source_rate, output_rate))
```

Copied outputs require exact source hash/size and zero duration error; their
existing start timestamps are preserved. Missing or invalid required metadata
fails. Re-encoded parts require no additional loudness/peak measurement, matching
the frozen contract; export does not promise a delivered -3 dBTP ceiling.

Execution reuses configured executables and bounded process handling: argument
arrays, `shell=False`, disconnected stdin, `-nostdin`, `-n`, file-only protocols,
`mov,mp3,wav,aac` input demuxers, disabled MOV external references/absolute
track paths, `-err_detect explode`, `-xerror` and explicit selected-stream mapping.
Probe timeout is 30 seconds. Each FFmpeg/copy pass uses
`min(21600, max(120, ceil(working_duration*2+60)))` seconds. Private stderr is
bounded to 16 MiB total with only a 64 KiB retained tail; captured JSON is bounded
to the existing 1 MiB limit. Timeout/interruption kills and reaps the tool.
Normal CLI diagnostics contain structured actionable errors, not raw logs or
unrestricted private paths. No installation, root or `su` is used.

Before new audio writes, check current free storage for all remaining outputs.
Encoded estimates use 30000 bytes times each ceil(overlap-expanded duration),
plus 65536 bytes per output. Copies use actual source bytes. Add a 64 MiB
metadata allowance and headroom of max(256 MiB, 20% of subtotal). Reused outputs
do not count as new audio writes. This is conservative provisional admission,
not a capacity reservation; import preflight does not reserve disk. A verified
temporary file moves as the same inode, so publication needs no second full
audio copy. Write/fsync/publication errors still fail safely.

New files live in an exclusive session-owned `temp/export-<attempt_id>` directory.
After probe/decode/hash verification, recheck both sources, flush/fsync the
temporary file, set POSIX read-only mode, and use the accepted no-replace atomic
publication into `generated/exports/<attempt_id>/part_<index>.<ext>`.
Recheck the published inode, size and hash. No final name is accepted from a
partial, empty or invalid output; collisions are never overwritten.

After every required part is published/verified, recheck all part hashes and
the saved plan hash, then prove logical coverage: contiguous nominal ranges,
zero first start, exact source final end, no gaps, capped end-only expansion and
five-second adjacent overlap. Finally recheck original and selected-source
identity/size/hash, including failure paths once those sources have been opened.
A failure before source resolution cannot establish after-source evidence and
does not claim it. Invalid imports or plans cause no media processing.

## Metadata, retries and interrupted publication

Session state remains `imported`. Import, inspection, normalization and planning
records remain intact. `audio_export` is a separate compact latest-attempt
pointer with status `export_pending`, `export_failed` or `export_succeeded`,
`success`, plan/source references, counts, error, record path and SHA-256.

The attempt's `generated/exports/<attempt_id>/session.json` records schema/policy,
timestamps, elapsed time, retry request, plan hash/revision, source identity,
original duration, integrity checks, storage admission, coverage and diagnostics.
Each part records index, deterministic filename, nominal/global starts and ends,
requested and measured local duration, before/after overlap, source artifact
and selected absolute stream, method, sample counters for encodes, requested
encoding, actual probed media, verification, size, SHA-256, managed path,
reuse flag and status. Optional/unavailable fields are null. `silence_removed`
is always false. These are processing records, not final package manifests.

Each invocation creates a new attempt. Completed files remain in their original
attempt directories. Reuse requires matching saved plan hash/revision, working
source, policy, range, filename, method and encoding, then actual size/hash,
fresh probe and **full decoding** again. A retry may therefore reference retained
parts in older export directories while placing new parts in its own directory;
use each part's `managed_path`, not one guessed directory for the whole set.
Unusable prior parts are preserved and replaced by new independent owned files.
Failed/pending attempts require explicit `--retry`; successful reruns can reuse
verified parts. Neither mode accumulates gain or overwrites an earlier artifact.

Pending and failed attempts have `success=false`; failures never retain a
successful coverage claim. Verified individual parts may survive a later failure,
but overall success requires every required part and final source/plan checks.
Temporary files owned by the current attempt are cleaned on handled failures;
unexpected preexisting files are not deleted.

Audio publication, attempt-record publication and latest-session publication are
separate atomic operations, not a filesystem transaction. A crash can leave a
published orphan, an interrupted temporary directory, or a complete historical
record with a pending/hash-mismatched latest pointer. Such files are never
implicitly complete or automatically adopted. Retry reuses only hash-referenced
verified records; otherwise it creates new owned outputs and preserves old files.
Automatic orphan recovery/pruning is not implemented. Metadata write failures
are actionable errors, even if every media file was already published.

## Host evidence and Recora parity

Host evidence is separate from Android acceptance. The regression suite preserves
all 170 accepted tests and adds 33 export tests: **203/203 host tests PASS**, exit
code 0, zero failures or skips. Python compilation and `git diff --check` PASS.
Full test output is retained in ignored `data/export-all-tests.txt`. Checks cover
export geometry, source/plan tampering, stale
normalization revision, copy/encode policy, full decode, rate/channel/profile,
fixed timing, empty ranges, source-end/no-gap checks, publication collisions,
storage refusal, timeout/interruption, original integrity, metadata failure,
retry/reuse, path/symlink safety and zero-photo tests.

Real host FFmpeg fixtures exercise WAV encoding, independent exact M4A and MP3
copies, a verified normalized working source, stereo/channel preservation,
12345-to-48000 Hz conversion, and a 1200-second mono 8000 Hz source with retained
silence. Force's saved two-part plan exports `[0,605]` and `[600,1200]`, with
five seconds shared context, full decode, AAC-LC and exact logical source-end
coverage. Its fixed codec tolerance is 0.256 seconds, not a duration percentage.
Ignored `data/export-example.json` retains the actual host example, part file
locations and independent original SHA-256 preservation check.

Recora parity is retained for media, copy exception, end-only overlap, nearest
sample rounding, independent source cuts, timing limits and full-decode checks.
Intentional RecorAndro differences already frozen in the planner (Auto's 1620 s
threshold and useful 600–1620 s nominal structure) remain intact. Export reuse
also re-probes/full-decodes retained parts rather than relying only on Recora's
saved verification plus current size/hash. Android does not change output format,
rate, channels or bitrate policy.

## Accepted Android validation — Step 2.4 FINAL PASS

The user approved Step 2.4 **FINAL PASS** based on automated and actual Android
validation, with the following accepted evidence:

- **203/203 Android tests PASS**.
- **Python compilation PASS**.
- The existing **3691.787029-second** lecture session
  `d0c39956c17943299dd17e67bf6d1d68` exported successfully.
- Three verified **AAC-LC/M4A** outputs had measured local durations of
  **1505**, **1505** and **691.787007 seconds**.
- **Five-second overlap, no gaps and complete source-end coverage** were verified.
- Independent **SHA-256 and size checks passed** for all three outputs and
  the original.

The final logical source endpoint remains **3691.787029 seconds**. The third
part's measured local duration, **691.787007 seconds**, does not replace the
global endpoint or nominal geometry; its 0.000022-second difference is within
the frozen encoded timing tolerance.

**Manual listening verification was explicitly waived.** It was not a passed
validation check, and no manual listening PASS is claimed. Accepted Android
evidence is distinct from the host fixtures above.

## Actual-device validation procedure — existing lecture

The procedure below is retained for reproducibility. Accepted actual-device
validation is complete and does not require repeating it.

Transfer only the reviewed Step 2.4 files to the existing Termux checkout:
`recorandro/exports.py`, `recorandro/cli.py`, `tests/test_exports.py`,
`docs/SESSION_EXPORT.md` and `README.md`. Use your existing USB/file transfer
method; retain relative paths. No commit/push is needed and no app installation
or re-import is required. Run from that checkout in ordinary non-root Termux:

```sh
export RECORANDRO_DATA_ROOT="$HOME/recorandro-data"
python -m unittest discover -s tests -v
python -m compileall -q recorandro tests tools
session_id=d0c39956c17943299dd17e67bf6d1d68
python - "$session_id" <<'PY'
import json, os, sys
from pathlib import Path
s = Path(os.environ['RECORANDRO_DATA_ROOT']) / 'sessions' / sys.argv[1]
r = json.loads((s/'session.json').read_text())
p = r['segmentation']
assert r['state'] == 'imported' and p['status'] == 'planned'
assert r['normalization']['status'] == 'normalization_succeeded'
print(json.dumps(p, indent=2))
PY
result="$HOME/recorandro-lecture-export-$(date +%Y%m%d-%H%M%S).json"
python -m recorandro export-session "$session_id" > "$result"
printf 'EXPORT_EXIT=%s\n' "$?"
cat "$result"
# Only after diagnosing a failed/interrupted export:
# python -m recorandro export-session "$session_id" --retry > "$result"
```

Inspect the **latest** saved mode before exporting. Do not regenerate a plan or
normalize merely to run this command. The accepted lecture has D=3691.787029 s,
original size 44,941,318 bytes, AAC, mono, 44100 Hz; its accepted normalization
Auto skip selects the original. If the latest approved plan is Auto/Force with
the accepted fallback boundaries, expect:

| Part | Nominal source range (s) | Exported global range (s) | Requested local duration (s) |
| --- | --- | --- | --- |
| 01 | 0–1500 | 0–1505 | 1505 |
| 02 | 1500–3000 | 1500–3005 | 1505 |
| 03 | 3000–3691.787029 | 3000–3691.787029 | 691.787029 |

New encodes should be AAC-LC/M4A, 44100 Hz mono, requested 128000 bit/s, each
with duration/start tolerance 0.05 s and full decoding verified. Measured bitrate
and file size need not equal requests or original values. If latest mode is Off,
expect one exact independent `part_01.m4a` copy, zero overlap/duration tolerance,
44,941,318 bytes and the original SHA-256. That is a valid completed export.

Independently compare recorded output hashes/sizes and original integrity:

```sh
python - "$result" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
r = json.loads(Path(sys.argv[1]).read_text())
a = r['audio_export']
assert r['ok'] and a['success'] and a['status'] == 'export_succeeded'
s = Path(os.environ['RECORANDRO_DATA_ROOT']) / 'sessions' / r['session_id']
current = json.loads((s/'session.json').read_text())
assert current['state'] == 'imported'
assert current['audio_export']['attempt_id'] == a['attempt_id']
def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while chunk := f.read(1024*1024):
            h.update(chunk)
    return h.hexdigest()
o = current['audio']
assert (s/o['managed_path']).stat().st_size == o['size_bytes'] == 44941318
assert digest(s/o['managed_path']) == o['sha256']
assert current['segmentation']['record_sha256'] == a['plan_reference']['sha256']
assert digest(s/a['plan_reference']['record_path']) == a['plan_reference']['sha256']
assert digest(s/current['audio_export']['record_path']) == current['audio_export']['record_sha256']
for kind in ('original', 'source'):
    assert a['integrity'][kind+'_before']['status'] == 'verified'
    assert a['integrity'][kind+'_after']['status'] == 'verified'
assert len(a['parts']) == a['part_count'] == current['audio_export']['verified_part_count']
assert all(a['coverage'][k] for k in ('verified', 'no_gaps', 'source_end_covered', 'overlap_verified'))
assert not a['silence_removed'] and a['error'] is None
previous = 0
for i, p in enumerate(a['parts']):
    f = s/p['managed_path']
    assert p['status'] == 'verified' and p['verification']['full_decode_passed']
    assert f.stat().st_size == p['size_bytes'] and digest(f) == p['sha256']
    assert p['nominal_start_seconds'] == previous == p['global_start_seconds']
    assert p['global_end_seconds'] == min(a['source']['media']['duration_seconds'], p['nominal_end_seconds']+5)
    if i:
        assert a['parts'][i-1]['global_end_seconds'] == p['global_start_seconds']+5
    previous = p['nominal_end_seconds']
    print(f)
    print(json.dumps({'media': p['media'], 'verification': p['verification']}, indent=2))
assert previous == a['source']['media']['duration_seconds'] == a['parts'][-1]['global_end_seconds']
print('Independent sizes/hashes, source-end and overlap checks PASS')
PY
```

Preserve JSON/test/compilation results for review. Optional future listening of
the printed generated part paths can use an existing player method; never edit
managed files. Playback is supplementary to full-decode/timing/hash evidence.
Manual listening was explicitly waived for the accepted Step 2.4 validation.
Use existing small inspected/normalized/planned fixture sessions to validate
single-output copy versus encode. An intentional failed tool configuration on a
fixture, followed by `--retry` with the correct tool, can demonstrate failure
metadata and retained completed outputs without altering the real lecture.

Step 2.4 has received **FINAL PASS**. No ZIP packaging, final manifests,
subsequent step, commit or push until separately authorized.
