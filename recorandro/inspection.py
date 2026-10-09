"""Bounded technical inspection of a verified session-owned original only."""

from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import threading
import uuid

from .sessions import AUDIO_SUFFIXES, _fingerprint, hash_stream
from .storage import OwnedDirectory, StorageError, _is_redirect, safe_leaf

PROBE_TIMEOUT_SECONDS = 30
MAX_JSON_BYTES = 1024 * 1024
MAX_STDERR_BYTES = 65536
ENTRIES = ("format=format_name,duration,size,bit_rate,start_time:format_tags=creation_time:"
           "stream=index,codec_type,codec_name,sample_rate,channels,channel_layout,bit_rate,"
           "duration,duration_ts,time_base,start_time:stream_tags=creation_time")
FORMAT_FAMILIES = {"mov": {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"},
                   "mp3": {"mp3"}, "wav": {"wav"}, "aac": {"aac"}}
SUFFIX_FAMILIES = {".m4a": "mov", ".mp3": "mp3", ".wav": "wav", ".aac": "aac"}


class InspectionFailure(ValueError):
    def __init__(self, code, message, inspection=None):
        super().__init__(message)
        self.code = code
        self.inspection = inspection


def _fail(code, message):
    raise InspectionFailure(code, message)


def _text(value):
    if (isinstance(value, str) and 0 < len(value) <= 200 and
            all(ord(c) >= 32 and ord(c) != 127 for c in value)):
        return value
    return None


def _number(value, *, integer=False, minimum=0, warnings=None, field="number"):
    if value is None or value == "N/A":
        return None
    try:
        if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
            raise ValueError
        result = Decimal(str(value))
        if not result.is_finite() or not Decimal(str(minimum)) <= result <= 2**53:
            raise ValueError
        if integer and result != result.to_integral_value():
            raise ValueError
        return int(result) if integer else float(result)
    except (ValueError, InvalidOperation, OverflowError):
        if warnings is not None:
            warnings.append("invalid_" + field)
        return None


def _load_json(payload):
    if len(payload) > MAX_JSON_BYTES:
        _fail("excessive_json", "Metadata exceeds the 1 MiB limit.")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    try:
        return json.loads(payload, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        _fail("malformed_json", "Tool/session JSON is malformed; verify the tool or metadata.")


def parse_probe(payload, suffix):
    """Whitelist facts; invalid numeric values are excluded and diagnosed.

    A readable inspection may lack processing prerequisites. It never certifies
    decoding. Stream and ticks estimates are preserved even when contradictory.
    """
    data = _load_json(payload)
    if (not isinstance(data, dict) or not isinstance(data.get("streams"), list) or
            any(not isinstance(s, dict) for s in data["streams"]) or
            not isinstance(data.get("format"), dict)):
        _fail("invalid_metadata_structure", "Expected stream objects and a format object.")
    streams, container = data["streams"], data["format"]
    audio = next((s for s in streams if s.get("codec_type") == "audio" and
                  _text(s.get("codec_name")) not in (None, "unknown")), None)
    if audio is None:
        _fail("no_recognized_audio", "No recognized audio stream; original retained.")
    warnings = []
    def number(section, key, **kwargs):
        label = "stream" if section is audio else "container"
        return _number(section.get(key), warnings=warnings, field=label + "_" + key, **kwargs)
    index = number(audio, "index", integer=True)
    if index is None:
        _fail("invalid_stream_index", "Selected audio needs a nonnegative absolute integer index.")
    indices = [_number(s.get("index"), integer=True) for s in streams]
    if any(i is None for i in indices) or len(set(indices)) != len(indices):
        _fail("invalid_stream_index", "Stream indices must be unique nonnegative integers.")
    name = _text(container.get("format_name"))
    names = set(name.split(",")) if name else set()
    families = [key for key, aliases in FORMAT_FAMILIES.items() if names and names <= aliases]
    if len(families) != 1:
        _fail("unsupported_demuxer", "Actual demuxer must be mov, mp3, wav or aac.")
    family = families[0]
    if suffix.lower() not in AUDIO_SUFFIXES:
        _fail("unsupported_suffix", "Managed original has an unsupported suffix.")
    if SUFFIX_FAMILIES[suffix.lower()] != family:
        warnings.append("suffix_demuxer_mismatch")
    estimates = {"stream": number(audio, "duration", minimum=0.000001),
                 "stream_time_base": None,
                 "container": number(container, "duration", minimum=0.000001)}
    ticks = number(audio, "duration_ts", integer=True, minimum=1)
    time_base = _text(audio.get("time_base"))
    rational = None
    if time_base is not None and re.fullmatch(r"[0-9]+/[0-9]+", time_base):
        numerator, denominator = time_base.split("/")
        numerator = _number(numerator, integer=True, minimum=1)
        denominator = _number(denominator, integer=True, minimum=1)
        if numerator is not None and denominator is not None:
            rational = (numerator, denominator)
    if audio.get("time_base") not in (None, "N/A") and rational is None:
        warnings.append("invalid_stream_time_base")
    if ticks is not None and rational is not None:
        with localcontext() as context:
            # Preserve the bound comparison before converting a rational to
            # float; 64 digits cover products/ratios of these <=2**53 integers.
            context.prec = 64
            estimates["stream_time_base"] = _number(Decimal(ticks) * rational[0] / rational[1],
                                                   minimum=0.000001, warnings=warnings,
                                                   field="stream_time_base_duration")
    provenance = next((key for key, value in estimates.items() if value is not None), None)
    duration = estimates[provenance] if provenance else None
    tolerance = max(1.0, duration * 0.01) if duration is not None else None
    disagreements = [{"estimate": key, "seconds": value, "delta_seconds": abs(value - duration)}
                     for key, value in estimates.items() if value is not None and
                     duration is not None and abs(value - duration) > tolerance]
    blockers = []
    if duration is None:
        warnings.append("duration_unavailable")
        blockers.append("duration_unavailable")
    if sum(value is not None for value in estimates.values()) < 2:
        warnings.append("duration_no_independent_cross_check")
    elif estimates["container"] is None:
        warnings.append("duration_cross_check_same_stream_only")
    if disagreements:
        warnings.append("duration_disagreement")
        blockers.append("duration_disagreement")
    if family == "aac":
        warnings.append("raw_aac_duration_unverified")
        blockers.append("raw_aac_duration_verification_required")
    rate = number(audio, "sample_rate", integer=True, minimum=1)
    channels = number(audio, "channels", integer=True, minimum=1)
    if rate is None or not 7350 <= rate <= 192000:
        blockers.append("sample_rate_outside_contract")
    if channels not in (1, 2):
        blockers.append("channels_outside_contract")
    human = None
    if duration is not None:
        hours, remainder = divmod(round(duration * 100), 360000)
        minutes, remainder = divmod(remainder, 6000)
        seconds, fraction = divmod(remainder, 100)
        human = f"{hours:02}:{minutes:02}:{seconds:02}.{fraction:02}"
    def creation(section):
        tags = section.get("tags")
        if tags is not None and not isinstance(tags, dict):
            _fail("invalid_metadata_structure", "Creation tags must be objects.")
        return _text(tags.get("creation_time")) if tags else None
    media = {"container_format": name, "demuxer_family": family,
             "selected_audio_stream_index": index, "stream_count": len(streams),
             "audio_codec": _text(audio.get("codec_name")), "sample_rate": rate,
             "channels": channels, "channel_layout": _text(audio.get("channel_layout")),
             "stream_bitrate": number(audio, "bit_rate", integer=True, minimum=1),
             "container_bitrate": number(container, "bit_rate", integer=True, minimum=1),
             "duration_seconds": duration, "duration_human": human, "duration_source": provenance,
             "duration_estimates_seconds": estimates, "duration_ts": ticks, "time_base": time_base,
             "duration_consistency": {"tolerance_seconds": tolerance, "disagreements": disagreements},
             "stream_start_seconds": number(audio, "start_time", minimum=-2**53),
             "container_start_seconds": number(container, "start_time", minimum=-2**53),
             "container_reported_size_bytes": number(container, "size", integer=True),
             "creation_time": {"container": creation(container), "audio_stream": creation(audio),
                               "trusted": False, "informational_only": True},
             "warnings": warnings,
             "processing_eligibility": {"status": "blocked" if blockers else "unverified",
                                        "blockers": blockers, "decoder": "unverified"}}
    return media


def probe_command(executable, path):
    # Apply MOV protections regardless of suffix: permitted-family mismatch is
    # allowed, so a MOV renamed .wav must receive the same restrictions.
    return [executable, "-v", "error", "-protocol_whitelist", "file",
            "-format_whitelist", "mov,mp3,wav,aac", "-enable_drefs", "0",
            "-use_absolute_path", "0", "-show_entries", ENTRIES, "-of", "json", "-i", str(path)]


def run_probe(executable, path, *, pass_fds=()):
    """Drain both pipes with hard retained-byte caps; kill on overflow/timeout.

    No raw stderr, executable path, command or media path escapes this function.
    Diagnostics are private, bounded and discarded after status classification.
    """
    resolved = shutil.which(executable)
    if resolved is None:
        _fail("ffprobe_missing", "Configured ffprobe is missing; check its installation or configuration.")
    if os.name == "nt" and Path(resolved).suffix.lower() != ".exe":
        _fail("unsafe_executable", "Configure a native ffprobe executable.")
    kwargs = {"pass_fds": pass_fds} if os.name == "posix" else {"creationflags": subprocess.CREATE_NO_WINDOW}
    try:
        process = subprocess.Popen(probe_command(resolved, path), shell=False,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, **kwargs)
    except OSError:
        _fail("ffprobe_execution_failed", "Cannot execute configured ffprobe; check availability and permissions.")
    output, diagnostic = bytearray(), bytearray()
    excessive = threading.Event()
    read_failed = threading.Event()
    def drain(pipe, target, limit):
        try:
            while chunk := os.read(pipe.fileno(), 8192):
                remaining = limit - len(target)
                target.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    excessive.set()
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    break
        except OSError:
            read_failed.set()
        finally:
            pipe.close()
    threads = [threading.Thread(target=drain, args=(process.stdout, output, MAX_JSON_BYTES)),
               threading.Thread(target=drain, args=(process.stderr, diagnostic, MAX_STDERR_BYTES))]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        process.wait(timeout=PROBE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        for thread in threads:
            thread.join()
    if timed_out:
        _fail("ffprobe_timeout", "ffprobe exceeded 30 seconds; original retained. Retry explicitly.")
    if excessive.is_set():
        _fail("excessive_output", "ffprobe output exceeded the stdout/stderr limit; inspect tool configuration.")
    if read_failed.is_set():
        _fail("ffprobe_output_failed", "Cannot read complete ffprobe output; retry explicitly.")
    if process.returncode != 0:
        _fail("ffprobe_nonzero_exit", "ffprobe could not inspect the media; original retained. Check media/tool compatibility.")
    return bytes(output)


def _existing_child(stack, directory, name):
    info = directory.info(name)
    if _is_redirect(info) or not stat.S_ISDIR(info.st_mode):
        _fail("unsafe_managed_path", "Managed directory redirection or invalid directory refused.")
    return stack.enter_context(directory.child(name))


@contextmanager
def _inspection_lock(directory):
    """Kernel-released advisory lock; no stale lock after interruption/kill."""
    fd = directory.open(".inspection.lock", os.O_RDWR | os.O_CREAT | getattr(os, "O_NONBLOCK", 0))
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            _fail("unsafe_managed_path", "Inspection lock must be a regular owned file.")
        try:
            if os.name == "posix":
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                import msvcrt
                # msvcrt permits locking a byte beyond EOF; no writes needed.
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            _fail("inspection_busy", "Another inspection is active for this session; wait for it to finish.")
        yield
    finally:
        os.close(fd)


def _read_record(directory, session_id):
    fd = directory.open("session.json", os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            _fail("invalid_session", "Session metadata must be a regular file.")
        record = _load_json(stream.read(MAX_JSON_BYTES + 1))
    if (not isinstance(record, dict) or type(record.get("schema_version")) is not int or
            record["schema_version"] != 1 or record.get("session_id") != session_id or
            record.get("state") != "imported" or not isinstance(record.get("audio"), dict) or
            type(record.get("visual_count")) is not int or record["visual_count"] < 0):
        _fail("invalid_session", "Requires a matching schema-v1 imported session with an audio record.")
    audio = record["audio"]
    leaf = audio.get("imported_filename")
    if (not isinstance(leaf, str) or not leaf or safe_leaf(leaf) != leaf or
            audio.get("managed_path") != f"originals/audio/{leaf}" or
            Path(leaf).suffix.lower() not in AUDIO_SUFFIXES or
            type(audio.get("size_bytes")) is not int or audio["size_bytes"] <= 0 or
            not isinstance(audio.get("sha256"), str) or
            not re.fullmatch(r"[0-9a-f]{64}", audio["sha256"])):
        _fail("invalid_original_record", "Managed original reference, imported size or SHA-256 is invalid.")
    return record


def _verify(stream, directory, leaf, expected, initial=None):
    before = os.fstat(stream.fileno())
    path_info = directory.info(leaf)
    if (_is_redirect(path_info) or not stat.S_ISREG(before.st_mode) or
            not stat.S_ISREG(path_info.st_mode) or _fingerprint(before) != _fingerprint(path_info) or
            (initial is not None and _fingerprint(before) != _fingerprint(initial))):
        _fail("original_identity_changed", "Managed original identity changed; check session storage.")
    stream.seek(0)
    size, digest = hash_stream(stream)
    if (_fingerprint(os.fstat(stream.fileno())) != _fingerprint(before) or
            _fingerprint(directory.info(leaf)) != _fingerprint(before)):
        _fail("original_identity_changed", "Managed original changed during integrity verification.")
    if size != expected["size_bytes"] or before.st_size != expected["size_bytes"]:
        _fail("original_size_mismatch", "Managed original size differs from accepted import; check storage.")
    if digest != expected["sha256"]:
        _fail("original_hash_mismatch", "Managed original SHA-256 differs from accepted import; check storage.")
    return before, {"status": "verified", "actual_size_bytes": size, "sha256": digest}


def inspect_session(config, session_id, *, retry=False):
    """Inspect an existing import, persisting pending before any original access."""
    if not isinstance(session_id, str) or not re.fullmatch(r"[0-9a-f]{32}", session_id):
        _fail("invalid_session_id", "Session ID must be the 32 lowercase hex characters from import JSON.")
    with ExitStack() as stack:
        # root() supports allocation for import; inspection requires it to exist.
        if not config.data_root.is_dir():
            _fail("session_unavailable", "Configured data root/session is unavailable.")
        root = stack.enter_context(OwnedDirectory.root(config.data_root))
        sessions = _existing_child(stack, root, "sessions")
        directory = _existing_child(stack, sessions, session_id)
        stack.enter_context(_inspection_lock(directory))
        record = _read_record(directory, session_id)
        prior = record.get("inspection")
        if prior is not None and (not isinstance(prior, dict) or
                                  prior.get("status") not in ("probed", "probe_failed", "probe_pending")):
            _fail("invalid_inspection_record", "Existing inspection status is invalid.")
        if prior and prior["status"] in ("probe_failed", "probe_pending") and not retry:
            _fail("retry_required", "Previous inspection failed or was interrupted; pass --retry.")
        inspection = {"schema_version": 1, "implementation_version": "step_2_1_v1",
                      "status": "probe_pending", "probe_status": "not_run",
                      "attempt_id": uuid.uuid4().hex, "retry_requested": bool(retry),
                      "inspected_at": datetime.now(timezone.utc).isoformat(), "completed_at": None,
                      "source": {"actual_size_bytes": None,
                                 "expected_size_bytes": record["audio"]["size_bytes"],
                                 "imported_sha256": record["audio"]["sha256"]},
                      "integrity": {"before": {"status": "not_checked"}, "after": {"status": "not_checked"}},
                      "media": None, "warnings": [], "error": None,
                      "processing_eligibility": {"status": "unverified", "decoder": "unverified", "blockers": []}}
        record["inspection"] = inspection
        # Preserve Step 1.2 import semantics; no decoder eligibility assertion.
        try:
            directory.atomic_json(record)
        except (OSError, StorageError):
            _fail("metadata_persistence_failed", "Cannot invalidate old inspection atomically; no probe was run.")
        failure = None
        stream = audio_dir = initial = None
        leaf = record["audio"]["imported_filename"]
        try:
            originals = _existing_child(stack, directory, "originals")
            audio_dir = _existing_child(stack, originals, "audio")
            fd = audio_dir.open(leaf, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
            stream = stack.enter_context(os.fdopen(fd, "rb"))
            opened = os.fstat(fd)
            if stat.S_ISREG(opened.st_mode):
                inspection["source"]["actual_size_bytes"] = opened.st_size
            initial, inspection["integrity"]["before"] = _verify(stream, audio_dir, leaf, record["audio"])
            # POSIX: ffprobe opens the already verified inode through a passed FD,
            # never a replaceable pathname. Android exposes /proc/self/fd.
            path = f"/proc/self/fd/{fd}" if os.name == "posix" else audio_dir.path / leaf
            inspection["probe_status"] = "running"
            payload = run_probe(config.ffprobe, path, pass_fds=(fd,) if os.name == "posix" else ())
            inspection["probe_status"] = "succeeded"
            media = parse_probe(payload, Path(leaf).suffix)
            inspection["media"] = media
            inspection["warnings"] = list(media["warnings"])
            if media["container_reported_size_bytes"] not in (None, initial.st_size):
                inspection["warnings"].append("container_reported_size_mismatch")
            inspection["processing_eligibility"] = media["processing_eligibility"]
        except (InspectionFailure, OSError, StorageError, KeyboardInterrupt) as exc:
            failure = exc if isinstance(exc, InspectionFailure) else InspectionFailure(
                "inspection_interrupted" if isinstance(exc, KeyboardInterrupt) else "managed_access_failed",
                "Inspection interrupted; retry explicitly." if isinstance(exc, KeyboardInterrupt) else
                "Cannot safely read managed original; check session storage and permissions.")
            if inspection["integrity"]["before"]["status"] == "not_checked":
                inspection["integrity"]["before"] = {"status": "failed", "code": failure.code}
        finally:
            if stream is not None and audio_dir is not None:
                try:
                    _, inspection["integrity"]["after"] = _verify(stream, audio_dir, leaf, record["audio"], initial)
                except (InspectionFailure, OSError, StorageError) as exc:
                    integrity_error = exc if isinstance(exc, InspectionFailure) else InspectionFailure(
                        "original_recheck_failed", "Cannot recheck managed original after inspection.")
                    inspection["integrity"]["after"] = {"status": "failed", "code": integrity_error.code}
                    failure = integrity_error
        inspection["completed_at"] = datetime.now(timezone.utc).isoformat()
        if failure is not None:
            inspection.update(status="probe_failed", error={"code": failure.code, "message": str(failure)})
            if inspection["probe_status"] == "running":
                inspection["probe_status"] = "failed"
            inspection["processing_eligibility"] = {"status": "blocked", "decoder": "unverified",
                                                     "blockers": [failure.code]}
        else:
            inspection["status"] = "probed"
        try:
            directory.atomic_json(record)
        except (OSError, StorageError):
            _fail("metadata_persistence_failed", "Inspection result could not be published; persisted pending is incomplete.")
        if failure:
            raise InspectionFailure(failure.code, str(failure), inspection)
        return inspection
