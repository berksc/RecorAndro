# RecorAndro

Android-first, local-only project. Step 1.1 provides Python configuration and
environment diagnostics. Step 1.2 adds conservative storage preflight and verified
immutable audio import. Step 2.1 adds managed-original ffprobe inspection.
Step 2.2 adds Auto/Force/Off normalization with full selected-stream decoding
and verified independent AAC/M4A artifacts for useful gain. Step 2.2 actual
Redmi validation is completed and accepted: **FINAL PASS**, with 125/125 Android
tests (exit code 0) and Python compilation PASS. Quiet Auto and usable Force
fixtures applied gain; usable Auto and quiet Off fixtures succeeded without a
derivative. The existing real lecture completed with `auto_already_usable_level`,
gain 0 and no normalized derivative, errors or warnings. Its original size and
SHA-256 were independently verified unchanged; session state remains `imported`
and successful normalization metadata was persisted and verified. See
[accepted Android normalization evidence](docs/SESSION_NORMALIZATION.md#accepted-android-validation--final-pass).

From the repository root (Python >=3.10), set an explicit owned data directory:

```sh
export RECORANDRO_DATA_ROOT="$HOME/recorandro-data"
python -m recorandro doctor --json
python -m unittest discover -s tests -v
python tools/check_media_capabilities.py
```

See [Termux installation and actual-device capability verification](docs/TERMUX_ENVIRONMENT.md).
Step 1.1 actual Redmi/Termux capability validation is accepted in
[its report](docs/STEP_1_1_REPORT.md). Step 1.2 actual-device validation is completed:
47/47 Android tests and small Unicode WAV / real lecture M4A imports passed.
This validates immutable import. Step 2.1 actual-device validation is completed
and accepted: **FINAL PASS**, with 84/84 Android tests and successful inspection
of the existing real lecture session without re-import. Duration was independently
confirmed and original integrity verified before/after; decoder eligibility
remains unverified. See [accepted inspection evidence](docs/SESSION_INSPECTION.md).

Temporary technical import CLI (from the repository root):

```sh
python -m recorandro import-audio "$HOME/lecture-audio.m4a" --profile lecture --provision-seconds 7200 --archive profile
```

`--provision-seconds` is a required user-supplied duration budget, not measured
media duration. No default Lecture archive choice is made. See
[session import, storage formula and Termux validation](docs/SESSION_IMPORT.md).

Inspect an existing imported session using its stored session identifier:

```sh
python -m recorandro inspect-session "$session_id"
# Explicit retry after a failed/interrupted inspection:
python -m recorandro inspect-session "$session_id" --retry
```

This probes only the verified managed original, preserves imported bytes, and
returns JSON metadata, integrity outcomes, warnings and processing blockers.
Probe success does not certify full decoding or normalization readiness. See
[inspection schema, safeguards and existing real-lecture Termux validation](docs/SESSION_INSPECTION.md).

Evaluate normalization for an already inspected session (Auto is the default):

```sh
python -m recorandro normalize-session "$session_id"
python -m recorandro normalize-session "$session_id" --mode force
python -m recorandro normalize-session "$session_id" --mode off
# Explicit retry after failed/interrupted normalization:
python -m recorandro normalize-session "$session_id" --mode auto --retry
```

Successful no-gain decisions retain the original and create no normalized audio.
New boosts receive attempt-owned verified outputs; prior outputs are preserved.
Input loudness fields are under `normalization.input_levels`, not `measurement`.
See [normalization policy, host and accepted Android evidence, transfer and existing-lecture validation](docs/SESSION_NORMALIZATION.md).
Segmentation and packaging remain unimplemented.
