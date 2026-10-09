"""User-triggered original-only normalization, with independent verified outputs."""

from contextlib import ExitStack
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import threading
import time
import uuid

from .inspection import (InspectionFailure, MAX_JSON_BYTES, _existing_child, _inspection_lock,
                         _load_json, _number, _read_record, _verify, parse_probe,
                         probe_command, run_probe)
from .sessions import hash_stream, _fingerprint
from .storage import OwnedDirectory, StorageError

MEASUREMENT_FILTER = "loudnorm=I=-26:TP=-3:LRA=50:print_format=json"
AAC_RATES = {7350, 8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100,
             48000, 64000, 88200, 96000}
TAIL_BYTES = 65536
MAX_DIAGNOSTIC_BYTES = 16 * 1024 * 1024


class NormalizationFailure(ValueError):
    def __init__(self, code, message, attempt=None):
        super().__init__(message)
        self.code, self.attempt = code, attempt


def fail(code, message):
    raise NormalizationFailure(code, message)


def parse_loudness(log):
    """Only loudnorm INPUT fields, never its hypothetical output measurements."""
    for match in reversed(list(re.finditer(r"\{[^{}]{0,8192}\}", log))):
        try:
            values = _load_json(match.group())
        except InspectionFailure:
            if '"input_i"' in match.group() or '"input_tp"' in match.group():
                fail("invalid_loudness", "Malformed loudnorm INPUT JSON; original retained.")
            continue
        if not isinstance(values, dict) or "input_i" not in values or "input_tp" not in values:
            continue
        levels = {}
        for key, label in (("input_i", "integrated_lufs"), ("input_tp", "true_peak_dbtp"),
                           ("input_lra", "loudness_range_lu"), ("input_thresh", "threshold_lufs")):
            value = values.get(key)
            if key == "input_thresh" and key not in values:
                levels[label] = None
                continue
            if value == "-inf" and key in ("input_i", "input_tp", "input_thresh"):
                levels[label] = None
                continue
            parsed = _number(value, minimum=0 if key == "input_lra" else -120)
            if parsed is None or parsed > 100:
                fail("invalid_loudness", "Malformed or nonfinite loudnorm input measurements; original retained.")
            levels[label] = parsed
        if levels["integrated_lufs"] is not None and levels["true_peak_dbtp"] is None:
            fail("invalid_loudness", "Finite integrated loudness requires a finite input true peak.")
        return levels
    fail("missing_loudness", "No complete loudnorm INPUT measurement was returned.")


def choose_gain(levels, mode="auto"):
    if mode not in ("auto", "force", "off"):
        fail("invalid_mode", "Mode must be auto, force or off.")
    if mode == "off":
        return {"gain_db": 0.0, "decision": "normalization_off", "warnings": []}
    loudness, peak = levels["integrated_lufs"], levels["true_peak_dbtp"]
    for value in (loudness, peak):
        if value is not None and (type(value) not in (int, float) or
                                  _number(value, minimum=-120) is None or value > 100):
            fail("invalid_loudness", "Gain decisions require finite validated input levels.")
    if loudness is not None and peak is None:
        fail("invalid_loudness", "Finite integrated loudness requires a finite input true peak.")
    warnings = []
    if peak is not None and peak >= 0:
        warnings.append("input_possible_existing_clipping")
    if loudness is None:
        decision = "below_measurement_gate" if mode == "auto" else "force_no_gain_below_measurement_gate"
        warnings.append("loudness_below_measurement_gate")
        return {"gain_db": 0.0, "decision": decision, "warnings": warnings}
    if mode == "auto" and loudness >= -30:
        return {"gain_db": 0.0, "decision": "auto_already_usable_level", "warnings": warnings}
    if mode == "force" and loudness >= -26:
        return {"gain_db": 0.0, "decision": "force_no_gain_at_or_above_target", "warnings": warnings}
    desired = -26 - loudness
    headroom = max(0, -3 - peak)
    gain = math.floor(max(0, min(desired, 3, headroom)) * 1000) / 1000
    if gain < 0.5:
        return {"gain_db": 0.0, "decision": "insufficient_safe_gain" if mode == "auto" else
                "force_no_gain_insufficient_safe_gain", "warnings": warnings + ["insufficient_safe_gain"]}
    if desired > gain + 0.01:
        warnings.append("gain_limited_target_may_remain_unmet")
    return {"gain_db": gain, "decision": "low_level_safe_boost",
            "warnings": warnings + ["constant_gain_raises_background_noise"]}


def pass_timeout(duration):
    return min(21600, max(120, math.ceil(duration * 2 + 60)))


def storage_budget(duration, free_bytes):
    # Same provisional 30000 bytes/s + container allowance and headroom as import.
    # Atomic move reuses temporary bytes; no additional full derivative copy.
    artifact = 30000 * math.ceil(duration) + 65536
    headroom = max(268435456, (artifact + 4) // 5)
    required = artifact + headroom
    return {"policy_version": 1, "measured_duration_seconds": duration,
            "derivative_temporary_bytes": artifact, "headroom_bytes": headroom,
            "estimated_required_bytes": required, "free_bytes": free_bytes,
            "decision": "allow" if free_bytes >= required else "deny",
            "reservation": False, "scope": "normalization_only_atomic_move_no_copy"}


def _executable(configured, name):
    path = shutil.which(configured)
    if path is None:
        fail(name + "_missing", f"Configured {name} is missing; check installation/configuration.")
    if os.name == "nt" and Path(path).suffix.lower() != ".exe":
        fail("unsafe_executable", "Configure native media tool executables.")
    return path


def _execute(args, timeout, phase, *, pass_fds=(), capture_stdout=False):
    """Private bounded tail, bounded total diagnostics, kill/reap on all exits."""
    kwargs = {"pass_fds": tuple(set(pass_fds))} if os.name == "posix" else {
        "creationflags": subprocess.CREATE_NO_WINDOW}
    try:
        process = subprocess.Popen(args, shell=False, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
                                   stderr=subprocess.PIPE, **kwargs)
    except OSError:
        fail("tool_execution_failed", f"Cannot execute media tool for {phase}; check permissions/configuration.")
    stdout, tail = bytearray(), bytearray()
    excessive, read_error = threading.Event(), threading.Event()
    def kill():
        if process.poll() is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
    def read(pipe, output, limit, retain_tail):
        total = 0
        try:
            while chunk := os.read(pipe.fileno(), 8192):
                total += len(chunk)
                if total > limit:
                    excessive.set()
                    kill()
                    break
                output.extend(chunk)
                if retain_tail and len(output) > TAIL_BYTES:
                    del output[:-TAIL_BYTES]
        except OSError:
            read_error.set()
            kill()
        finally:
            pipe.close()
    threads = [threading.Thread(target=read, args=(process.stderr, tail, MAX_DIAGNOSTIC_BYTES, True))]
    if capture_stdout:
        threads.append(threading.Thread(target=read, args=(process.stdout, stdout, MAX_JSON_BYTES, False)))
    started_threads = []
    try:
        for thread in threads:
            thread.start()
            started_threads.append(thread)
    except (RuntimeError, KeyboardInterrupt) as exc:
        kill()
        process.wait()
        for thread in started_threads:
            thread.join()
        for pipe in (process.stderr, process.stdout):
            if pipe is not None:
                pipe.close()
        if isinstance(exc, KeyboardInterrupt):
            raise
        fail("tool_output_failed", f"Cannot start bounded diagnostics for {phase}; tool stopped safely.")
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        kill()
        process.wait()
        for thread in threads:
            thread.join()
    if timed_out:
        fail("tool_timeout", f"{phase} exceeded its {timeout}-second limit; original retained. Retry explicitly.")
    if excessive.is_set() or read_error.is_set():
        fail("tool_output_failed", f"{phase} diagnostics were excessive or unreadable; no result accepted.")
    if process.returncode != 0:
        fail("tool_nonzero_exit", f"{phase} failed; check selected decoder/media compatibility. Original retained.")
    return bytes(stdout) if capture_stdout else tail.decode("utf-8", errors="replace")


def _input_args(path, media):
    options = ["-protocol_whitelist", "file", "-format_whitelist", "mov,mp3,wav,aac"]
    if media["demuxer_family"] == "mov":
        options += ["-enable_drefs", "0", "-use_absolute_path", "0"]
    return options + ["-err_detect", "explode", "-i", str(path), "-map",
                      f"0:{media['selected_audio_stream_index']}", "-vn", "-sn", "-dn"]


def _base(executable):
    return [executable, "-hide_banner", "-nostdin", "-nostats", "-n", "-v", "info", "-xerror"]


def _fd_path(stream, directory, leaf):
    return f"/proc/self/fd/{stream.fileno()}" if os.name == "posix" else directory.path / leaf


def _eligible(media):
    if not isinstance(media, dict):
        fail("invalid_inspection", "Successful inspection media facts are required.")
    if (not isinstance(media.get("processing_eligibility"), dict) or
            not isinstance(media["processing_eligibility"].get("blockers"), list) or
            not isinstance(media.get("warnings"), list) or
            not isinstance(media.get("duration_consistency"), dict) or
            not isinstance(media["duration_consistency"].get("disagreements"), list) or
            any(type(media.get(key)) is not int for key in
                ("sample_rate", "channels", "selected_audio_stream_index", "stream_count")) or
            media["stream_count"] < 1):
        fail("invalid_inspection", "Inspection numeric fields, blockers and duration diagnostics must be valid.")
    duration = _number(media.get("duration_seconds"), minimum=0.000001)
    rate = _number(media.get("sample_rate"), integer=True, minimum=7350)
    channels = _number(media.get("channels"), integer=True, minimum=1)
    index = _number(media.get("selected_audio_stream_index"), integer=True)
    if (duration is None or rate is None or rate > 192000 or channels not in (1, 2) or
            index is None or media.get("demuxer_family") not in ("mov", "mp3", "wav", "aac") or
            not isinstance(media.get("audio_codec"), str) or media["audio_codec"] in ("", "unknown")):
        fail("ineligible_media", "Need valid duration, selected stream/codec, admitted demuxer, 7350–192000 Hz and mono/stereo.")
    if media.get("demuxer_family") == "aac":
        fail("raw_aac_duration_unverified", "Raw AAC duration remains unverified; safe normalization timing is not established.")
    if (media.get("processing_eligibility", {}).get("blockers") or
            "duration_disagreement" in media.get("warnings", []) or
            media.get("duration_consistency", {}).get("disagreements")):
        fail("ineligible_media", "Inspection contains processing blockers or duration disagreement; verify media first.")


def _current_inspection(record):
    inspected = record.get("inspection")
    if (not isinstance(inspected, dict) or inspected.get("status") != "probed" or
            inspected.get("probe_status") != "succeeded" or
            not isinstance(inspected.get("source"), dict) or
            not isinstance(inspected.get("integrity"), dict) or
            inspected.get("source", {}).get("imported_sha256") != record["audio"]["sha256"] or
            inspected.get("source", {}).get("expected_size_bytes") != record["audio"]["size_bytes"]):
        fail("inspection_required", "Current successful inspection matching the import is required; run inspect-session.")
    for phase in ("before", "after"):
        check = inspected.get("integrity", {}).get(phase, {})
        if (not isinstance(check, dict) or check.get("status") != "verified" or
                check.get("sha256") != record["audio"]["sha256"] or
                check.get("actual_size_bytes") != record["audio"]["size_bytes"]):
            fail("inspection_required", "Inspection integrity evidence is unavailable; run inspect-session.")
    _eligible(inspected.get("media"))
    return inspected["media"]


def _fresh_source(config, stream, directory, leaf, accepted):
    path = _fd_path(stream, directory, leaf)
    fds = (stream.fileno(),) if os.name == "posix" else ()
    media = parse_probe(run_probe(config.ffprobe, path, pass_fds=fds), Path(leaf).suffix)
    _eligible(media)
    keys = ("selected_audio_stream_index", "audio_codec", "sample_rate", "channels", "stream_count", "demuxer_family")
    if (any(media[key] != accepted.get(key) for key in keys) or
            abs(media["duration_seconds"] - accepted["duration_seconds"]) > 0.000001):
        fail("inspection_stale", "Fresh source facts differ from accepted inspection; inspect-session again.")
    return media


def _probe_output(config, stream, directory):
    command = probe_command(_executable(config.ffprobe, "ffprobe"), _fd_path(stream, directory, "pending.m4a"))
    entry = command.index("-show_entries") + 1
    command[entry] = command[entry].replace("codec_name,", "codec_name,profile,")
    payload = _execute(command, 30, "output_probe", pass_fds=(stream.fileno(),), capture_stdout=True)
    media = parse_probe(payload, ".m4a")
    raw = _load_json(payload)
    selected = next(s for s in raw["streams"] if s["index"] == media["selected_audio_stream_index"])
    media["codec_profile"] = selected.get("profile")
    return media


def verify_output(media, source):
    _eligible(media)
    rate = source["sample_rate"] if source["sample_rate"] in AAC_RATES else 48000
    if (media["demuxer_family"] != "mov" or media["audio_codec"] != "aac" or
            media.get("codec_profile") != "LC" or media["stream_count"] != 1 or
            media["sample_rate"] != rate or media["channels"] != source["channels"]):
        fail("invalid_derivative_format", "Derivative must be single-stream AAC-LC/M4A at expected rate/channels.")
    tolerance = max(0.05, 2048 / min(source["sample_rate"], rate))
    start = _number(media.get("stream_start_seconds"), minimum=-2**53)
    delta = abs(media["duration_seconds"] - source["duration_seconds"])
    if start is None or delta > tolerance or abs(start) > tolerance:
        fail("invalid_derivative_timing", "Derivative duration/start exceeds fixed codec/sample-rate tolerance.")
    return {"passed": True, "delta_seconds": delta, "tolerance_seconds": tolerance,
            "output_start_seconds": start}


def verify_peak(levels):
    peak = _number(levels.get("true_peak_dbtp"), minimum=-120)
    if peak is None or peak > 100:
        fail("encoded_peak_unverified", "Encoded true peak must be finite; derivative not accepted.")
    if peak > -1:
        fail("encoded_peak_unsafe", "Encoded true peak exceeds -1 dBTP; derivative not accepted.")
    return {"passed": True, "true_peak_dbtp": peak, "reject_above_dbtp": -1,
            "warn_above_dbtp": -2.9, "overshoot_warning": peak > -2.9}


def _new_attempt(session_id, mode, retry):
    return {"schema_version": 1, "policy_version": "normalization_v1", "session_id": session_id,
            "attempt_id": uuid.uuid4().hex, "status": "normalization_pending", "mode_requested": mode,
            "retry_requested": retry, "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None, "elapsed_seconds": None, "decision": None,
            "evaluation_performed": False, "evaluation_completed": False,
            "full_decode_verified": False, "gain_db": None, "applied_gain_db": 0.0,
            "normalization_applied": False, "encoding_applied": False, "encoding_performed": False,
            "input": None, "input_levels": None, "output": None, "output_levels": None,
            "input_duration_seconds": None, "output_duration_seconds": None,
            "output_source": None, "working_source": None, "parameters": None,
            "encoded_peak_safety": None, "duration_integrity": None, "storage_preflight": None,
            "integrity": {"before": {"status": "not_checked"}, "after": {"status": "not_checked"}},
            "warnings": [], "error": None}


def normalize_session(config, session_id, *, mode="auto", retry=False):
    if mode not in ("auto", "force", "off"):
        fail("invalid_mode", "Mode must be auto, force or off.")
    if not isinstance(session_id, str) or not re.fullmatch(r"[0-9a-f]{32}", session_id):
        fail("invalid_session_id", "Use the existing import's 32-character session ID.")
    started = time.monotonic()
    with ExitStack() as stack:
        if not config.data_root.is_dir():
            fail("session_unavailable", "Configured data root/session is unavailable.")
        root = stack.enter_context(OwnedDirectory.root(config.data_root))
        sessions = _existing_child(stack, root, "sessions")
        directory = _existing_child(stack, sessions, session_id)
        stack.enter_context(_inspection_lock(directory))
        record = _read_record(directory, session_id)
        previous = record.get("normalization")
        if previous is not None and (not isinstance(previous, dict) or previous.get("status") not in
                                    ("normalization_pending", "normalization_failed", "normalization_succeeded")):
            fail("invalid_normalization_record", "Existing normalization status is invalid.")
        if previous and previous["status"] != "normalization_succeeded" and not retry:
            fail("retry_required", "Previous normalization failed/interrupted; pass --retry.")
        generated = _existing_child(stack, directory, "generated")
        attempts = stack.enter_context(generated.child("normalization"))
        attempt = _new_attempt(session_id, mode, retry)
        owned = stack.enter_context(attempts.child(attempt["attempt_id"], exclusive=True))
        record["normalization"] = attempt
        try:
            owned.atomic_json(attempt)
            directory.atomic_json(record)
        except (OSError, StorageError):
            fail("metadata_persistence_failed", "Cannot publish pending normalization; no processing was run.")
        source_stream = audio_dir = initial = temp = None
        failure = None
        candidate = None
        leaf = record["audio"]["imported_filename"]
        try:
            accepted = _current_inspection(record)
            originals = _existing_child(stack, directory, "originals")
            audio_dir = _existing_child(stack, originals, "audio")
            fd = audio_dir.open(leaf, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
            source_stream = stack.enter_context(os.fdopen(fd, "rb"))
            initial, attempt["integrity"]["before"] = _verify(source_stream, audio_dir, leaf, record["audio"])
            media = _fresh_source(config, source_stream, audio_dir, leaf, accepted)
            attempt["input"] = dict(record["audio"], media=media, inspection_attempt_id=record["inspection"]["attempt_id"])
            duration, rate, channels = media["duration_seconds"], media["sample_rate"], media["channels"]
            attempt["input_duration_seconds"] = duration
            attempt["warnings"].extend(media["warnings"])
            executable = _executable(config.ffmpeg, "ffmpeg")
            path = _fd_path(source_stream, audio_dir, leaf)
            fds = (fd,) if os.name == "posix" else ()
            base = _base(executable) + _input_args(path, media)
            timeout = pass_timeout(duration)
            if mode == "off":
                _execute(base + ["-f", "null", "-"], timeout, "input_decode", pass_fds=fds)
                decision = choose_gain(None, mode)
            else:
                attempt["evaluation_performed"] = True
                log = _execute(base + ["-af", MEASUREMENT_FILTER, "-f", "null", "-"],
                               timeout, "input_measurement", pass_fds=fds)
                attempt["input_levels"] = parse_loudness(log)
                attempt["evaluation_completed"] = True
                decision = choose_gain(attempt["input_levels"], mode)
            attempt["full_decode_verified"] = True
            attempt["input"]["full_decode_verified"] = True
            gain = decision["gain_db"]
            attempt.update(gain_db=gain, decision=decision["decision"])
            attempt["warnings"].extend(decision["warnings"])
            output_rate = rate if rate in AAC_RATES else 48000
            attempt["parameters"] = {"measurement_filter": MEASUREMENT_FILTER if mode != "off" else None,
                                     "timeout_seconds_per_pass": timeout, "selected_audio_stream_index": media["selected_audio_stream_index"],
                                     "target_lufs": -26, "auto_cutoff_lufs": -30, "positive_gain_cap_db": 3,
                                     "planned_peak_dbtp": -3, "minimum_useful_gain_db": 0.5,
                                     "gain_floor_precision_db": 0.001, "gain_filter": None,
                                     "requested_encoding": None}
            if gain > 0:
                budget = storage_budget(duration, root.free_bytes())
                attempt["storage_preflight"] = budget
                if budget["decision"] != "allow":
                    fail("insufficient_storage", "Current free space is below normalization temporary-output/headroom budget.")
                parent = _existing_child(stack, directory, "temp")
                temp = stack.enter_context(parent.child("normalize-" + attempt["attempt_id"], exclusive=True))
                # Exclusive owned directory + -n: FFmpeg creates its own new leaf.
                temp._leaf("pending.m4a")
                try:
                    temp.info("pending.m4a")
                except FileNotFoundError:
                    pass
                else:
                    fail("temporary_output_exists", "Refusing an existing temporary encoder output.")
                target = f"/proc/self/fd/{temp.fd}/pending.m4a" if os.name == "posix" else temp.path / "pending.m4a"
                filter_text = f"volume={gain:.3f}dB:precision=double"
                encoding = {"codec": "aac", "profile": "aac_low", "container": "m4a", "muxer": "ipod",
                            "sample_rate": output_rate, "channels": channels,
                            "bitrate": 128000 if channels == 1 else 192000, "movflags": "+faststart"}
                attempt["parameters"].update(gain_filter=filter_text, requested_encoding=encoding)
                if output_rate != rate:
                    attempt["warnings"].append("resampled_to_48000")
                attempt["encoding_performed"] = True
                _execute(base + ["-map_metadata", "-1", "-map_chapters", "-1", "-af", filter_text,
                                 "-c:a", "aac", "-profile:a", "aac_low", "-b:a", str(encoding["bitrate"]),
                                 "-ar", str(output_rate), "-movflags", "+faststart", "-f", "ipod", str(target)],
                         timeout, "encode", pass_fds=fds + ((temp.fd,) if os.name == "posix" else ()))
                # Owned temporary only: Windows needs write access for fsync.
                # No audio bytes are written through this verification handle.
                out_fd = temp.open("pending.m4a", os.O_RDWR | getattr(os, "O_NONBLOCK", 0))
                with os.fdopen(out_fd, "rb") as output_stream:
                    info = os.fstat(out_fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
                        fail("empty_derivative", "Encoder did not produce nonempty regular output.")
                    # Pin, hash and check identity around probe/full-decode verification.
                    size, digest = hash_stream(output_stream)
                    expected = {"size_bytes": size, "sha256": digest}
                    before, _ = _verify(output_stream, temp, "pending.m4a", expected, info)
                    output_media = _probe_output(config, output_stream, temp)
                    attempt["duration_integrity"] = verify_output(output_media, media)
                    if output_media["stream_bitrate"] is not None and output_media["stream_bitrate"] != encoding["bitrate"]:
                        attempt["warnings"].append("effective_bitrate_differs_from_requested")
                    output_path = _fd_path(output_stream, temp, "pending.m4a")
                    log = _execute(_base(executable) + _input_args(output_path, output_media) +
                                   ["-af", MEASUREMENT_FILTER, "-f", "null", "-"],
                                   timeout, "output_measurement", pass_fds=(out_fd,))
                    attempt["output_levels"] = parse_loudness(log)
                    peak = verify_peak(attempt["output_levels"])
                    attempt["encoded_peak_safety"] = peak
                    if peak["overshoot_warning"]:
                        attempt["warnings"].append("encoded_peak_overshoot")
                    _verify(output_stream, temp, "pending.m4a", expected, before)
                    _, attempt["integrity"]["after"] = _verify(source_stream, audio_dir, leaf, record["audio"], initial)
                    os.fsync(out_fd)
                    if os.name == "posix":
                        os.fchmod(out_fd, 0o400)
                # Close the verified read handle before the existing Windows
                # no-replace move; Android retains pinned directory descriptors.
                temp.publish("pending.m4a", "normalized.m4a", owned)
                # Native rename changes ctime, but inode/bytes must remain identical.
                final_fd = owned.open("normalized.m4a", os.O_RDONLY)
                with os.fdopen(final_fd, "rb") as published:
                    final_info = os.fstat(final_fd)
                    if (final_info.st_dev, final_info.st_ino) != (info.st_dev, info.st_ino):
                        fail("derivative_identity_changed", "Published derivative identity differs from verified output.")
                    _verify(published, owned, "normalized.m4a", expected)
                candidate = {"managed_path": f"generated/normalization/{attempt['attempt_id']}/normalized.m4a",
                             "size_bytes": size, "sha256": digest, "media": output_media,
                             "full_decode_verified": True}
            else:
                attempt["duration_integrity"] = {"passed": True, "delta_seconds": 0,
                                                  "tolerance_seconds": 0, "verification": "original_bytes_unchanged"}
        except (NormalizationFailure, InspectionFailure, OSError, StorageError, KeyboardInterrupt) as exc:
            failure = _error(exc)
        finally:
            if source_stream is not None:
                try:
                    _, attempt["integrity"]["after"] = _verify(source_stream, audio_dir, leaf, record["audio"], initial)
                except (InspectionFailure, OSError, StorageError) as exc:
                    failure = _error(exc)
                    attempt["integrity"]["after"] = {"status": "failed", "code": failure.code}
            if temp is not None and attempt["encoding_performed"]:
                try:
                    temp.unlink("pending.m4a")
                except FileNotFoundError:
                    pass  # Successful publication moved the temporary name.
                except (OSError, StorageError):
                    attempt["warnings"].append("temporary_cleanup_failed")
        attempt["completed_at"] = datetime.now(timezone.utc).isoformat()
        attempt["elapsed_seconds"] = round(time.monotonic() - started, 6)
        if failure:
            attempt.update(status="normalization_failed", error={"code": failure.code, "message": str(failure)})
        else:
            attempt.update(status="normalization_succeeded", output=candidate,
                           normalization_applied=candidate is not None, encoding_applied=candidate is not None,
                           applied_gain_db=attempt["gain_db"] if candidate else 0,
                           output_source="normalized" if candidate else "original",
                           working_source=candidate if candidate else attempt["input"],
                           output_duration_seconds=candidate["media"]["duration_seconds"] if candidate else
                           attempt["input_duration_seconds"])
        try:
            # Per-attempt history first, then latest-session pointer. They are not
            # a multi-file transaction; the session must report failure if it fails.
            owned.atomic_json(attempt)
            directory.atomic_json(record)
        except (OSError, StorageError):
            fail("metadata_persistence_failed", "Result metadata publication failed; session pending is incomplete. Preserve owned artifacts.")
        if failure:
            raise NormalizationFailure(failure.code, str(failure), attempt)
        return attempt


def _error(exc):
    if isinstance(exc, NormalizationFailure):
        return exc
    if isinstance(exc, InspectionFailure):
        return NormalizationFailure(exc.code, str(exc))
    if isinstance(exc, KeyboardInterrupt):
        return NormalizationFailure("normalization_interrupted", "Normalization interrupted; original retained. Retry explicitly.")
    return NormalizationFailure("managed_access_failed", "Cannot safely access/publish owned normalization files; original retained.")
