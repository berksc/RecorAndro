import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import sys

from .config import ConfigError, load_config
from .diagnostics import doctor
from .sessions import ImportFailure, PreflightDenied, import_audio
from .storage import StorageError


def log_result(root, ok: bool) -> None:
    """Only status, no media contents, subprocess logs or environment dumps."""
    logger = logging.getLogger("recorandro")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = RotatingFileHandler(root / "recorandro.log", maxBytes=65536,
                                  backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    try:
        logger.info("doctor completed: %s", "ok" if ok else "failed")
    finally:
        logger.removeHandler(handler)
        handler.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="recorandro")
    parser.add_argument("--config", help="Local JSON config path")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("doctor", help="Check environment and configured data root")
    check.add_argument("--json", action="store_true", help="Print machine-readable evidence")
    ingest = commands.add_parser("import-audio", help="Import one immutable audio; media inspection deferred")
    ingest.add_argument("path")
    ingest.add_argument("--profile", default="lecture")
    ingest.add_argument("--provision-seconds", required=True, type=int,
                        help="User-supplied duration provisioning bound (1..604800), not measured duration")
    ingest.add_argument("--archive", choices=("profile", "requested", "not_requested"), default="profile")
    ingest.add_argument("--title")
    ingest.add_argument("--course")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    if args.command == "import-audio":
        try:
            record = import_audio(config, args.path, profile=args.profile,
                                  provision_seconds=args.provision_seconds, archive=args.archive,
                                  title=args.title, course=args.course)
        except (ImportFailure, StorageError, OSError, ValueError) as exc:
            result = {"ok": False, "error": str(exc)}
            if isinstance(exc, PreflightDenied):
                result["storage_preflight"] = exc.preflight
            elif isinstance(exc, ImportFailure) and exc.record is not None:
                result["session"] = exc.record
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1
        print(json.dumps({"ok": True, "session": record}, ensure_ascii=False, indent=2))
        return 0
    report = doctor(config)
    if report["data_root"]["writable"]:
        try:
            log_result(config.data_root, report["ok"])
        except OSError as exc:
            report["logging_error"] = str(exc)
            report["ok"] = False
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for key, value in report.items():
            print(f"{key}: {json.dumps(value)}")
    return 0 if report["ok"] else 1
