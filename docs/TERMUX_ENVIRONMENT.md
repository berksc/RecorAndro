# Step 1.1 — Android local foundation

Status: **Android validation PENDING**. No physical Redmi/Termux access is established
in this Codex environment. Windows unit tests or synthetic FFmpeg runs do not grant
`MEDIA_CONTRACT Android-capability-validated` or Step 1.1 FINAL PASS.

This step adds configuration, environment diagnostics and an isolated synthetic
capability harness. It implements no session import, normalization decision engine,
segmentation planner, ZIP/archive packaging or final Android UI. No empty media or
session packages are needed yet. All frozen contracts remain authoritative.

## Manual installation on the Redmi Note 10 Pro

Use ordinary Termux, without `su`. Install Termux from
[F-Droid](https://f-droid.org/packages/com.termux/) or its
[official GitHub releases](https://github.com/termux/termux-app/releases).
Record the source and installed version. Follow the
[Termux installation guidance](https://github.com/termux/termux-app#installation);
do not mix app/add-on signing sources. If Termux is already installed, inspect it
first; this procedure does not authorize uninstalling or replacing existing data.
No Magisk grants, Android security changes or shared-storage permission is needed.

Run these commands manually, reviewing package-manager prompts:

```sh
pkg update
pkg install python ffmpeg git
python --version
ffmpeg -version
ffprobe -version
termux-info
id
uname -m
getprop ro.product.manufacturer
getprop ro.product.model
getprop ro.build.version.release
getprop ro.build.display.id
getprop ro.build.version.incremental
getprop ro.product.cpu.abi
```

Expected identity: Xiaomi Redmi Note 10 Pro, Android 12, accepted MIUI
13.0.7.0(SKFTRXM). Report a discrepancy instead of changing the baseline. `id`
must show an ordinary app UID, not UID 0. Record actual ABI; do not infer it.
Python must be >=3.10; no runtime Python dependencies are required.

Step 1.1 files are initially **uncommitted on Windows**. A clone from GitHub will
only include them after the user reviews and commits/pushes this numbered step.
Alternatively, transfer the reviewed source files into a fresh owned Termux
directory before device testing. Do not claim that the current GitHub HEAD already
contains this scaffold. No commit/push is performed by these instructions.

For a new checkout after the reviewed files become available on `main`:

```sh
mkdir -p "$HOME/projects"
cd "$HOME/projects"
git clone https://github.com/berksc/RecorAndro.git
cd RecorAndro
git remote -v
git status --short --branch
git rev-parse HEAD
git log -5 --oneline
```

For an existing checkout, use `cd` to it and run the four inspection commands
instead. Do not clone over it or reset it. Authentication, if needed, is separate
from application configuration; do not put GitHub credentials in the config.
Network is used for installation/source acquisition only. Runtime diagnostics and
fixture checks process local files without a service.

## Explicit configuration and execution

From the reviewed repository directory:

```sh
export RECORANDRO_DATA_ROOT="$HOME/recorandro-data"
python -m recorandro doctor
python -m recorandro doctor --json
python -m unittest discover -s tests -v
```

This data root is in Termux's app-private home. No `/sdcard` assumption,
`termux-setup-storage`, Android-wide scan or root access is involved. `doctor`
creates only the explicitly configured root, briefly writes/reads/removes an owned
probe, measures free bytes on that filesystem and appends status-only rotating
logs (`recorandro.log`, 64 KiB, two backups). The data root remains after checking.
Actual usable storage can differ from the baseline estimate of 96.7 GB.

Expected JSON: `ok: true`, nonempty FFmpeg/ffprobe paths and versions,
`environment.android_detected: true`, `environment.termux_detected: true`,
`environment.running_as_root: false`, `data_root.writable: true`, and a nonnegative
integer `data_root.available_bytes`. `su_on_path` only reports executable presence;
it does not test root permission or prove Magisk availability. Version/getprop
commands have bounded timeouts and disconnected stdin. Unknown fields stay unknown.
`android_capability_validation` deliberately stays PENDING.

Exit codes: 0 = environment diagnostics succeeded; 1 = a required check/log write
failed; 2 = configuration/CLI error. A zero doctor exit does not pass the media gate.

Optional local JSON configuration instead of the environment-only method:

```sh
cp -n config.example.json config.local.json
unset RECORANDRO_DATA_ROOT
python -m recorandro --config config.local.json doctor --json
```

Edit `config.local.json` if you want a different owned location. Example:

```json
{"data_root":"~/recorandro-data","ffmpeg":"ffmpeg","ffprobe":"ffprobe"}
```

Only `data_root`, `ffmpeg`, `ffprobe` are accepted; no secrets. A file-relative
data root resolves relative to the JSON file. Environment data roots must be
absolute (or `~/...`). No implicit data root is selected; filesystem roots and
empty values are rejected. Executables are names/paths, never command strings.
Precedence: `--config` selects the file before `RECORANDRO_CONFIG`; then
`RECORANDRO_DATA_ROOT`, `RECORANDRO_FFMPEG`, `RECORANDRO_FFPROBE` override file values.
No config file is auto-discovered in the current directory.

The module invocation needs no pip installation or virtual environment. If a
console entry point is wanted, optionally use `python -m venv .venv`,
`. .venv/bin/activate`, `python -m pip install --no-deps --no-build-isolation -e .`,
then `recorandro doctor --json`. This optional packaging path requires setuptools
>=61 in the virtual environment and is not necessary for acceptance.

## Actual-device capability commands

In ordinary Termux at the repository root, with the environment-only configuration:

```sh
export RECORANDRO_DATA_ROOT="$HOME/recorandro-data"
mkdir -p evidence
stamp=$(date +%Y%m%d-%H%M%S)
termux-info > "evidence/termux-$stamp.txt" 2>&1
id > "evidence/identity-$stamp.txt"
git rev-parse HEAD > "evidence/revision-$stamp.txt"
git status --short >> "evidence/revision-$stamp.txt"
python -m recorandro doctor --json > "evidence/doctor-$stamp.json"
echo "doctor exit: $?"
python -m unittest discover -s tests -v > "evidence/tests-$stamp.txt" 2>&1
echo "tests exit: $?"
python tools/check_media_capabilities.py > "evidence/capabilities-$stamp.json"
echo "capabilities exit: $?"
```

For file configuration, supply `--config config.local.json` to both module and
checker commands. Keep all evidence together with the tested source revision;
for transferred uncommitted code, also identify the exact reviewed transfer.
Share these files back for independent review. No lecture/photo contents are read.

The checker uses stdlib-generated six-second PCM fixtures in a fresh temporary
directory inside the configured root. Only its own fixtures are removed. It
records argv arrays, return codes, tool identity, complete small-fixture logs and
assertion failures in JSON (per-command retained output <=64 KiB; truncation fails).
Captured output is spooled to temporary files rather than unbounded memory. Each
ffprobe pass uses 30 seconds; each short FFmpeg pass uses the contract's 120-second
minimum. Evidence commands are recorded, not replayed from JSON. Fixture paths
cease to exist after the run; reproduce failures by rerunning the harness.

Expected: exit 0, `fixture_checks: PASS`, and **all 41 check rows PASS**. Expected
negative tests show nonzero media/allowlist failures; they are passes only if the
intended rejection occurs. FFmpeg versions may return zero when `-n` refuses
overwrite; that test checks the refusal diagnostic and unchanged hash directly.
No overwrite success is accepted. A checker PASS still needs confirmed actual
Redmi identity, ordinary UID, Termux source/version and user review; the checker
never automatically emits Android-capability-validated.

| Group | Executed fixture checks and expected evidence |
| --- | --- |
| 1. Demuxers/local protocol | WAV, MOV/M4A, raw AAC and MP3 successfully probed/decoded. Both tools reject HTTP before connection and reject WAV under an MP3-only whitelist. |
| 2. Required decoding | PCM S16LE WAV, AAC-LC M4A, ADTS raw AAC, MP3; selected index, codec, duration, start/rate/channels and requested JSON fields captured; malformed input rejected. |
| 3. M4A muxer/faststart | Explicit `-f ipod -movflags +faststart`; MP4 atom check confirms moov precedes mdat; nonempty output and full decode. |
| 4. Native AAC/bitrate | `-c:a aac -profile:a aac_low`; ffprobe profile LC; requested `-b:a 128000` mono / `192000` stereo. Measured bitrate need not equal target. |
| 5. Measurement | `loudnorm=I=-26:TP=-3:LRA=50:print_format=json`; input_i/input_tp/input_lra/input_thresh finite for the tone fixture; discarded null output. |
| 6. Gain | Fixture-only fixed `volume=1.000dB:precision=double`, AAC encode and finite output measurement. No Auto/Force decision or normalization pipeline. |
| 7. Silence | Frozen `asetpts=PTS-STARTPTS,silencedetect=noise=-40dB:duration=1:mono=0`; all leading/middle/trailing pauses at expected positions; an active right channel prevents combined silence. |
| 8. Timeline | `atrim=start_sample=72000:end_sample=168000,asetpts=PTS-STARTPTS`; exact two-second PCM sample slice, retained silent samples, encoded duration/start verified. No segmentation planner. |
| 9. Rate/channel | All 13 frozen AAC rates in mono and stereo; 12345 and 192000 Hz sources converted to 48000 Hz; channels preserved; six-second duration and start within `max(0.05,2048/min(source_rate,output_rate))`. |
| 10. Safety/verification | Shell-free args, disconnected stdin, explicit map, stream exclusions, metadata/chapter stripping, explode/xerror, no-overwrite, full decoding, exact independent-copy hash/size/duration, source hashes unchanged, external reference restrictions below. |

MOV-private `-enable_drefs 0 -use_absolute_path 0` are applied to known synthetic
MOV fixtures; some tool builds reject these private options for WAV/MP3. This
diagnostic routing is not a suffix-based production import implementation or a
change to the admitted actual-demuxer policy.

The harness constructs an owned QuickTime `alis` reference fixture from its
synthetic M4A, pointing only to that owned source. With `enable_drefs=0`, both
tools must report `Skipped opening external track` and ffprobe must return no
packets. A separate **negative fixture control** uses `enable_drefs=1` with
`use_absolute_path=0` to isolate absolute-path refusal; both tools must report
`not tried for security reasons`, and ffprobe again returns no packets. This
control never opens a reference or changes Android settings. Ordinary fixture
processing retains both restrictions. Fixture construction follows the
[FFmpeg MOV demuxer source](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/mov.c).

The harness currently uses `libmp3lame` only to *generate* its MP3 input fixture.
It is not an added frozen delivery-encoder requirement. If that generator is
unavailable, the row fails to establish MP3 decode capability; report this as a
fixture-generation limitation. A reviewed pre-generated MP3 fixture is an
available alternative for a later diagnostic adjustment, without installing an
alternate FFmpeg distribution or relaxing MP3 decoding. Similarly, no synthetic
fixture proves every conditional codec or malicious container variant is safe.

## Failure gate and FINAL PASS evidence

If a row fails, preserve the JSON and report its check name, exact `commands`
entries, return code, tool versions and error text. Check rows identify a
zero-based, half-open range into `commands`. Distinguish a missing required
capability from a broken fixture/harness or missing evidence. Available next
actions are correcting a demonstrated harness issue, rerunning the installed
ordinary Termux tools, or proposing the smallest evidence-backed contract
revision for approval. No codec/filter/bitrate/rate/threshold substitution,
alternate distribution installation, root workaround or automatic contract edit.
Stop before engine implementation.

Step 1.1 FINAL PASS needs all of:

- Confirmed Redmi Note 10 Pro / accepted Android-MIUI identity, actual ABI,
  Termux source/version, tested source identity, and non-root app UID.
- Actual doctor success: supported Python, FFmpeg/ffprobe identity, explicit
  app-private root, successful write/read check, free storage bytes and local log.
- Unit tests passing on that device and all capability rows passing with complete
  command/fixture/error evidence reviewed, including external-reference controls.
- User/ChatGPT acceptance of the evidence. Only then record
  `MEDIA_CONTRACT Android-capability-validated` as actual-device evidence in a
  follow-up Step 1.1 validation record; do not infer it from this scaffold.

Unavailable here: actual Termux installation/source/version, Redmi execution/ABI,
Android storage/access checks and the Android FFmpeg capability run. Long-media,
thermal, background/screen-off and hotspot coexistence qualification remain later
work, not simulated Step 1.1 results. Do not begin Step 1.2 at this boundary.
