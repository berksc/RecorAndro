# RecorAndro

Android-first, local-only project. Step 1.1 provides Python configuration and
environment diagnostics. Step 1.2 adds conservative storage preflight and verified
immutable audio import; media probing/processing is not implemented.

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
This validates immutable import; media eligibility and processing remain deferred.

Temporary technical import CLI (from the repository root):

```sh
python -m recorandro import-audio "$HOME/lecture-audio.m4a" --profile lecture --provision-seconds 7200 --archive profile
```

`--provision-seconds` is a required user-supplied duration budget, not measured
media duration. No default Lecture archive choice is made. See
[session import, storage formula and Termux validation](docs/SESSION_IMPORT.md).
