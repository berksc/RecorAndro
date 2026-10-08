# RecorAndro

Android-first, local-only project. Step 1.1 provides Python configuration and
environment diagnostics; media processing is not implemented.

From the repository root (Python >=3.10), set an explicit owned data directory:

```sh
export RECORANDRO_DATA_ROOT="$HOME/recorandro-data"
python -m recorandro doctor --json
python -m unittest discover -s tests -v
python tools/check_media_capabilities.py
```

See [Termux installation and actual-device capability verification](docs/TERMUX_ENVIRONMENT.md).
**Redmi/Termux validation is PENDING.** Host tests do not establish Android support.
