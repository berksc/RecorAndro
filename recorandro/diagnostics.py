"""Small write probe and informational environment diagnostics; never invokes su."""

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .config import Config


def run_tool(args: list[str], timeout: int = 30) -> dict:
    """Spool output, retaining a bounded tail; always disconnect stdin."""
    try:
        with tempfile.TemporaryFile() as output:
            result = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=output,
                                    stderr=subprocess.STDOUT, shell=False, timeout=timeout)
            size = output.tell()
            output.seek(max(0, size - 65536))
            return {"command": args, "returncode": result.returncode,
                    "output": output.read().decode("utf-8", errors="replace"),
                    "truncated": size > 65536}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"command": args, "returncode": None, "output": str(exc), "truncated": False}


def tool_version(executable: str) -> dict:
    path = shutil.which(executable)
    if path is None:
        return {"path": None, "version": None, "ok": False, "error": "Executable not found"}
    result = run_tool([path, "-version"])
    lines = result["output"].splitlines()
    return {"path": path, "version": lines[0] if lines else None,
            "ok": result["returncode"] == 0,
            "error": None if result["returncode"] == 0 else result["output"][-4096:]}


def environment() -> dict:
    prefix = os.environ.get("PREFIX", "")
    termux = bool(os.environ.get("TERMUX_VERSION") or
                  "/com.termux/" in prefix or "/com.termux/" in sys.executable)
    android = hasattr(sys, "getandroidapilevel") or Path("/system/build.prop").is_file()
    properties = {}
    getprop = shutil.which("getprop") if android else None
    if getprop:
        for key in ("ro.product.manufacturer", "ro.product.model", "ro.build.version.release",
                    "ro.build.display.id", "ro.build.version.incremental", "ro.product.cpu.abi"):
            result = run_tool([getprop, key], timeout=5)
            properties[key] = result["output"].strip() if result["returncode"] == 0 else None
    uid = os.geteuid() if hasattr(os, "geteuid") else None
    return {"python": sys.version, "python_executable": sys.executable,
            "platform": platform.platform(), "machine": platform.machine(),
            "android_detected": android, "android_properties": properties,
            "termux_detected": termux, "termux_version": os.environ.get("TERMUX_VERSION"),
            "termux_prefix": prefix or None, "effective_uid": uid,
            "running_as_root": uid == 0 if uid is not None else None,
            "su_on_path": shutil.which("su") is not None,
            "root_note": "Informational only; su was not invoked. Magisk authorization is unknown."}


def check_data_root(root: Path) -> dict:
    result = {"path": str(root), "writable": False, "available_bytes": None, "error": None}
    try:
        root.mkdir(parents=True, exist_ok=True)
        # Actual create/write/read/unlink in the configured location, not os.access alone.
        with tempfile.TemporaryFile(dir=root) as probe:
            probe.write(b"recorandro-doctor\n")
            probe.flush()
            probe.seek(0)
            if probe.read() != b"recorandro-doctor\n":
                raise OSError("Write probe readback differs")
        result["writable"] = True
        result["available_bytes"] = shutil.disk_usage(root).free
    except OSError as exc:
        result["error"] = str(exc)
    return result


def doctor(config: Config) -> dict:
    report = {"environment": environment(), "ffmpeg": tool_version(config.ffmpeg),
              "ffprobe": tool_version(config.ffprobe), "data_root": check_data_root(config.data_root),
              "android_capability_validation": "PENDING: requires actual Redmi/Termux evidence"}
    report["ok"] = (sys.version_info >= (3, 10) and report["ffmpeg"]["ok"] and
                    report["ffprobe"]["ok"] and report["data_root"]["writable"] and
                    report["data_root"]["available_bytes"] is not None)
    return report
