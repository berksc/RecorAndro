"""Frozen nominal planning and read-only quiet analysis. No audio export."""

from contextlib import ExitStack
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
import json
import math
import os
import re
import subprocess
import threading
import time
import uuid

from .inspection import (InspectionFailure, _existing_child, _inspection_lock,
                         _number, _read_record, _verify)
from .normalization import (NormalizationFailure, _base, _current_inspection,
                            _eligible, _executable, _fd_path, _fresh_source,
                            _input_args, pass_timeout, verify_output, verify_peak)
from .sessions import hash_stream
from .storage import OwnedDirectory, StorageError

TARGET = 1500
WINDOW_MIN, MAX_PART, MIN_PART = 1200, 1620, 600
MIN_QUIET, QUIET_ALLOWANCE = 1, 0.00001
MAX_REGIONS, MAX_PARTS = 100000, 10000
MAX_LOG_BYTES = 64 * 1024 * 1024
MAX_PLAN_BYTES = 32 * 1024 * 1024
QUIET_FILTER = "asetpts=PTS-STARTPTS,silencedetect=noise=-40dB:duration=1:mono=0"
EVENT = re.compile(r"\[(?:Parsed_)?silencedetect(?:_\d+)? @ [^\]]+\]\s+silence_(start|end):\s*(\S+)")


class PlanningFailure(ValueError):
    def __init__(self, code, message, attempt=None):
        super().__init__(message)
        self.code, self.attempt = code, attempt


def fail(code, message):
    raise PlanningFailure(code, message)


def _duration(value):
    if type(value) not in (int, float) or _number(value, minimum=0.000001) is None:
        fail("invalid_duration", "Planning requires finite source duration >=0.000001 seconds.")
    return value


def part_count(duration, mode="auto"):
    _duration(duration)
    if mode not in ("auto", "force", "off"):
        fail("invalid_mode", "Segmentation mode must be auto, force or off.")
    count = (1 if mode == "off" or (mode == "auto" and duration <= MAX_PART) or
             (mode == "force" and duration < 2 * MIN_PART) else
             max(2, int((Decimal(str(duration)) / MAX_PART).to_integral_value(rounding=ROUND_CEILING))))
    if count > MAX_PARTS:
        fail("too_many_parts", "Nominal plan exceeds the 10000-part validation bound.")
    if count > 1 and not count * MIN_PART <= duration <= count * MAX_PART:
        fail("infeasible_count", "Fixed part count cannot satisfy useful nominal bounds.")
    return count


def _regions(regions, duration):
    if not isinstance(regions, list) or len(regions) > MAX_REGIONS:
        fail("invalid_quiet_regions", "Quiet regions must be a bounded list.")
    valid = []
    for region in regions:
        if not isinstance(region, dict):
            fail("invalid_quiet_regions", "Quiet intervals require source-relative start and end.")
        start, end = region.get("start_seconds"), region.get("end_seconds")
        if (any(type(v) not in (int, float) or _number(v) is None for v in (start, end)) or
                not 0 <= start < end <= duration):
            fail("invalid_quiet_regions", "Quiet intervals must stay on the complete source timeline.")
        if end - start + QUIET_ALLOWANCE >= MIN_QUIET:
            valid.append((start, end))
    return valid


def plan_boundaries(duration, quiet_regions=None, *, mode="auto"):
    """Count first, then constrained deterministic candidates; nominal ranges only."""
    count = part_count(duration, mode)
    regions = _regions([] if quiet_regions is None else quiet_regions, duration)
    boundaries, adjustments = [], []
    # Decimal arithmetic preserves exact useful bounds for fractional quiet
    # midpoints (binary subtraction can turn 1620 into 1620.0000000000002).
    d = Decimal(str(duration))
    regions = [(Decimal(str(start)), Decimal(str(end))) for start, end in regions]
    previous = Decimal(0)
    for index in range(1, count):
        remaining = count - index
        left = max(previous + MIN_PART, d - remaining * MAX_PART)
        right = min(previous + MAX_PART, d - remaining * MIN_PART)
        if left > right:
            fail("infeasible_boundary", "No feasible cut can preserve all remaining useful parts.")
        normal_left = max(left, previous + WINDOW_MIN)
        normal_right = min(right, previous + MAX_PART)
        normal = normal_left <= normal_right
        search_left, search_right = (normal_left, normal_right) if normal else (left, right)
        ideal = previous + TARGET if normal else previous + (d - previous) / (remaining + 1)
        candidates = []
        for start, end in regions:
            candidate = (start + end) / 2
            method = "full_interval_midpoint"
            if not search_left <= candidate <= search_right:
                overlap_left, overlap_right = max(search_left, start), min(search_right, end)
                if overlap_right - overlap_left + Decimal(str(QUIET_ALLOWANCE)) < MIN_QUIET:
                    continue
                candidate = (overlap_left + overlap_right) / 2
                method = "intersection_midpoint"
            candidates.append((abs(candidate - ideal), -(end - start), candidate, start, end, method))
        evidence = None
        if candidates:
            _, _, chosen, start, end, method = min(candidates)
            evidence = {"start_seconds": float(start), "end_seconds": float(end), "candidate_method": method}
            reason = "quiet_region"
        else:
            chosen = min(search_right, max(search_left, ideal))
            reason = ("fallback_target" if chosen == ideal else "fallback_feasible_target") if normal else "fallback_redistributed_balance"
        constrained = not normal or (left, right) != (previous + MIN_PART, previous + MAX_PART)
        if constrained:
            adjustments.append({"boundary_index": index, "reason": "reserve_all_remaining_useful_parts",
                                "normal_preference_relaxed": not normal,
                                "unconstrained_target_seconds": float(previous + TARGET),
                                "chosen_seconds": float(chosen)})
        boundaries.append({"boundary_index": index, "global_timestamp_seconds": float(chosen),
                           "reason": reason, "quiet_interval": evidence,
                           "search_kind": "normal" if normal else "redistribution",
                           "feasible_interval_seconds": [float(left), float(right)],
                           "search_interval_seconds": [float(search_left), float(search_right)],
                           "ideal_seconds": float(ideal), "distance_from_ideal_seconds": float(abs(chosen - ideal))})
        previous = chosen
    points = [0.0, *(b["global_timestamp_seconds"] for b in boundaries), duration]
    fulfilled = mode != "force" or count > 1
    decision = ("force_not_feasible_minimum_duration" if not fulfilled else "segmentation_off" if mode == "off" else
                mode + ("_segmented" if count > 1 else "_single_part"))
    result = {"schema_version": 1, "policy_version": "useful_nominal_plan_v1",
              "mode_requested": mode, "mode_fulfilled": fulfilled, "decision": decision,
              "requested_minimum_count": 2 if mode == "force" else 1,
              "source_duration_seconds": duration, "expected_part_count": count,
              "plan_kind": "segmented" if count > 1 else "single",
              "segmentation_applied": count > 1, "audio_split": False, "audio_exported": False,
              "timeline": "original_media_relative_seconds", "timeline_start_seconds": 0.0,
              "timeline_end_seconds": duration, "target_seconds": TARGET,
              "search_window_seconds": [WINDOW_MIN, MAX_PART],
              "useful_multi_part_seconds": [MIN_PART, MAX_PART], "fixed_count_before_boundaries": True,
              "quiet_summary": {"qualifying_interval_count": len(regions)},
              "boundaries": boundaries, "tiny_part_avoidance_adjustments": adjustments,
              "nominal_parts": [{"part_index": i, "global_start_seconds": start,
                                 "global_end_seconds": end,
                                 "duration_seconds": float(Decimal(str(end)) - Decimal(str(start)))}
                                for i, (start, end) in enumerate(zip(points, points[1:]), 1)],
              "source_end_covered": True, "silence_removed": False}
    validate_plan(result)
    return result


def validate_plan(plan):
    """Validate count, shared endpoints and exact logical end, without export ranges."""
    duration = _duration(plan["source_duration_seconds"])
    count = part_count(duration, plan["mode_requested"])
    parts, boundaries = plan["nominal_parts"], plan["boundaries"]
    if (len(parts) != count or len(boundaries) != count - 1 or plan["expected_part_count"] != count or
            plan.get("silence_removed") is not False):
        fail("invalid_plan", "Nominal plan count or silence-preservation invariant is invalid.")
    previous = 0.0
    for index, part in enumerate(parts, 1):
        start, end, length = (part.get(k) for k in ("global_start_seconds", "global_end_seconds", "duration_seconds"))
        if (any(type(v) not in (int, float) or _number(v) is None for v in (start, end, length)) or
                part.get("part_index") != index or start != previous or not 0 <= start < end <= duration or
                abs(length - (end - start)) > 0.000001 or
                (count > 1 and not MIN_PART <= Decimal(str(end)) - Decimal(str(start)) <= MAX_PART)):
            fail("invalid_plan", "Nominal parts must be contiguous and obey useful lengths.")
        if index < count and (boundaries[index - 1]["boundary_index"] != index or
                              boundaries[index - 1]["global_timestamp_seconds"] != end):
            fail("invalid_plan", "Nominal shared endpoints must match chosen boundaries.")
        previous = end
    if previous != duration:
        fail("invalid_plan", "Last nominal part must reach the exact source end.")


def parse_quiet_regions(lines, duration, sample_rate):
    """Complete successful-decode log only; open trailing quiet reaches D."""
    _duration(duration)
    if type(sample_rate) is not int or not 7350 <= sample_rate <= 192000:
        fail("invalid_sample_rate", "Quiet event tolerance requires an admitted sample rate.")
    tolerance = max(0.05, 2048 / sample_rate)
    regions, pending, previous_end = [], None, 0.0
    def retain(start, end):
        if end - start + QUIET_ALLOWANCE >= MIN_QUIET:
            if len(regions) >= MAX_REGIONS:
                fail("too_many_quiet_regions", "Quiet analysis exceeds 100000 retained intervals.")
            regions.append({"start_seconds": start, "end_seconds": end})
    for line in lines:
        if "silence_start:" not in line and "silence_end:" not in line:
            continue
        matches = list(EVENT.finditer(line))
        # Do not ignore malformed detector events or partial/truncated records.
        if len(matches) != line.count("silence_start:") + line.count("silence_end:"):
            fail("invalid_quiet_events", "Malformed quiet event in complete decode log.")
        for match in matches:
            value = _number(match[2], minimum=-tolerance)
            if value is None or value > duration + tolerance:
                fail("invalid_quiet_events", "Quiet timestamp exceeds source endpoint tolerance.")
            value = min(duration, max(0.0, value))
            if match[1] == "start":
                if pending is not None or value < previous_end:
                    fail("invalid_quiet_events", "Duplicate or unordered quiet start.")
                pending = value
            else:
                if pending is None or value <= pending:
                    fail("invalid_quiet_events", "Unmatched or unordered quiet end.")
                retain(pending, value)
                pending, previous_end = None, value
    if pending is not None:
        retain(pending, duration)
    return regions


def _run_detection(args, timeout, log_stream, *, pass_fds=()):
    """Spool ALL diagnostics privately with a hard disk bound; always kill/reap."""
    kwargs = {"pass_fds": tuple(set(pass_fds))} if os.name == "posix" else {"creationflags": subprocess.CREATE_NO_WINDOW}
    try:
        process = subprocess.Popen(args, shell=False, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **kwargs)
    except OSError:
        fail("tool_execution_failed", "Cannot execute configured FFmpeg quiet analysis.")
    excessive, read_error = threading.Event(), threading.Event()
    def kill():
        if process.poll() is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
    def drain():
        total = 0
        try:
            while chunk := os.read(process.stderr.fileno(), 8192):
                total += len(chunk)
                if total > MAX_LOG_BYTES:
                    excessive.set()
                    kill()
                    break
                log_stream.write(chunk)
        except OSError:
            read_error.set()
            kill()
        finally:
            process.stderr.close()
    thread = threading.Thread(target=drain)
    try:
        thread.start()
    except (RuntimeError, KeyboardInterrupt) as exc:
        kill()
        process.wait()
        process.stderr.close()
        if isinstance(exc, KeyboardInterrupt):
            raise
        fail("diagnostic_read_failed", "Cannot start bounded quiet diagnostics; tool stopped.")
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        kill()
        process.wait()
        thread.join()
    if timed_out:
        fail("tool_timeout", "Quiet analysis exceeded its per-pass timeout; retry explicitly.")
    if excessive.is_set() or read_error.is_set():
        fail("diagnostic_read_failed", "Quiet diagnostics exceeded their bound or could not be retained.")
    if process.returncode != 0:
        fail("tool_nonzero_exit", "Selected-stream quiet decoding failed; no plan accepted.")
    log_stream.flush()
    log_stream.seek(0)


def detect_quiet_regions(config, stream, source_dir, leaf, media, temp):
    args = _base(_executable(config.ffmpeg, "ffmpeg")) + _input_args(_fd_path(stream, source_dir, leaf), media)
    args += ["-af", QUIET_FILTER, "-f", "null", "-"]
    fd = temp.open("quiet.log", os.O_RDWR | os.O_CREAT | os.O_EXCL)
    try:
        with os.fdopen(fd, "w+b") as log:
            _run_detection(args, pass_timeout(media["duration_seconds"]), log,
                           pass_fds=(stream.fileno(),) if os.name == "posix" else ())
            return parse_quiet_regions((line.decode("utf-8", errors="replace") for line in log),
                                       media["duration_seconds"], media["sample_rate"])
    finally:
        temp.unlink("quiet.log")


def _completed_source(record):
    """No re-normalization or fallback to an older successful evaluation."""
    n = record.get("normalization")
    if (not isinstance(n, dict) or n.get("status") != "normalization_succeeded" or
            n.get("schema_version") != 1 or n.get("policy_version") != "normalization_v1" or
            n.get("session_id") != record["session_id"] or
            not isinstance(n.get("attempt_id"), str) or not re.fullmatch(r"[0-9a-f]{32}", n["attempt_id"]) or
            n.get("full_decode_verified") is not True or n.get("mode_requested") not in ("auto", "force", "off") or
            not isinstance(n.get("input"), dict) or not isinstance(n.get("working_source"), dict) or
            not isinstance(n.get("integrity"), dict) or n.get("error") is not None):
        fail("normalization_required", "Need a current completed normalization outcome (including Off/no-gain); no automatic normalization.")
    original = record["audio"]
    for key in ("managed_path", "size_bytes", "sha256"):
        if n["input"].get(key) != original[key]:
            fail("invalid_working_source", "Normalization input does not match the accepted original.")
    for phase in ("before", "after"):
        check = n["integrity"].get(phase)
        if (not isinstance(check, dict) or check.get("status") != "verified" or
                check.get("sha256") != original["sha256"] or check.get("actual_size_bytes") != original["size_bytes"]):
            fail("invalid_working_source", "Completed normalization lacks original integrity evidence.")
    source = n["working_source"]
    if (source.get("full_decode_verified") is not True or type(source.get("size_bytes")) is not int or
            source["size_bytes"] <= 0 or not isinstance(source.get("sha256"), str) or
            not re.fullmatch(r"[0-9a-f]{64}", source["sha256"])):
        fail("invalid_working_source", "Working artifact size/hash/full-decode record is invalid.")
    _eligible(source.get("media"))
    _eligible(n["input"].get("media"))
    if (n["input"].get("full_decode_verified") is not True or
            n.get("input_duration_seconds") != n["input"]["media"]["duration_seconds"]):
        fail("invalid_working_source", "Completed normalization input decoder/duration record is inconsistent.")
    if n.get("output_source") == "normalized":
        gain = _number(n.get("gain_db"), minimum=0.5)
        if (n.get("normalization_applied") is not True or n.get("encoding_applied") is not True or
                n.get("encoding_performed") is not True or type(n.get("gain_db")) not in (int, float) or
                gain is None or gain > 3 or
                n.get("applied_gain_db") != n["gain_db"] or
                n.get("output") != source or source.get("managed_path") !=
                f"generated/normalization/{n['attempt_id']}/normalized.m4a" or n["mode_requested"] == "off"):
            fail("invalid_working_source", "Applied normalization requires its exact immutable output reference.")
        verify_output(source["media"], n["input"]["media"])
        peak = n.get("encoded_peak_safety")
        if not isinstance(peak, dict) or peak.get("passed") is not True:
            fail("invalid_working_source", "Applied source lacks successful encoded peak verification.")
        verify_peak(peak)
    elif n.get("output_source") == "original":
        if (n.get("normalization_applied") is not False or n.get("encoding_applied") is not False or
                n.get("output") is not None or source != n["input"] or n.get("gain_db") != 0):
            fail("invalid_working_source", "No-gain normalization must select the accepted original without an artifact.")
    else:
        fail("invalid_working_source", "Unknown working-source kind.")
    if n.get("output_duration_seconds") != source["media"]["duration_seconds"]:
        fail("invalid_working_source", "Working duration differs from completed normalization.")
    return n, source


def _failure(exc):
    if isinstance(exc, PlanningFailure):
        return exc
    if isinstance(exc, (InspectionFailure, NormalizationFailure)):
        return PlanningFailure(exc.code, str(exc))
    if isinstance(exc, KeyboardInterrupt):
        return PlanningFailure("planning_interrupted", "Quiet planning interrupted; audio retained. Retry explicitly.")
    return PlanningFailure("managed_access_failed", "Cannot safely access/persist managed planning files; audio retained.")


def plan_session(config, session_id, *, mode="auto", retry=False):
    if not isinstance(session_id, str) or not re.fullmatch(r"[0-9a-f]{32}", session_id):
        fail("invalid_session_id", "Use an existing imported session identifier.")
    if mode not in ("auto", "force", "off"):
        fail("invalid_mode", "Segmentation mode must be auto, force or off.")
    started = time.monotonic()
    with ExitStack() as stack:
        if not config.data_root.is_dir():
            fail("session_unavailable", "Configured data root/session is unavailable.")
        root = stack.enter_context(OwnedDirectory.root(config.data_root))
        sessions = _existing_child(stack, root, "sessions")
        directory = _existing_child(stack, sessions, session_id)
        stack.enter_context(_inspection_lock(directory))
        record = _read_record(directory, session_id)
        previous = record.get("segmentation")
        if previous is not None and (not isinstance(previous, dict) or previous.get("status") not in
                                    ("planning_pending", "planned", "planning_failed")):
            fail("invalid_planning_record", "Existing planning status is invalid.")
        if previous and previous["status"] != "planned" and not retry:
            fail("retry_required", "Previous plan failed/interrupted; pass --retry.")
        parent = _existing_child(stack, directory, "generated")
        plans = stack.enter_context(parent.child("segmentation"))
        attempt_id = uuid.uuid4().hex
        owned = stack.enter_context(plans.child(attempt_id, exclusive=True))
        relative = f"generated/segmentation/{attempt_id}/session.json"
        result = {"schema_version": 1, "session_id": session_id, "attempt_id": attempt_id,
                  "status": "planning_pending", "mode_requested": mode, "retry_requested": retry,
                  "created_at": datetime.now(timezone.utc).isoformat(), "completed_at": None,
                  "elapsed_seconds": None, "source": None, "original_duration_seconds": None,
                  "quiet_analysis": {"performed": False, "completed": False, "filter": QUIET_FILTER,
                                     "quiet_threshold_dbfs": -40, "minimum_quiet_seconds": MIN_QUIET,
                                     "channels": "combined", "regions": []},
                  "plan": None, "integrity": {}, "warnings": [], "error": None}
        pointer = {"schema_version": 1, "attempt_id": attempt_id, "status": "planning_pending",
                   "mode_requested": mode, "record_path": relative, "record_sha256": None}
        record["segmentation"] = pointer
        try:
            owned.atomic_json(result)
            directory.atomic_json(record)
        except (OSError, StorageError):
            fail("metadata_persistence_failed", "Cannot publish pending plan; no analysis was run.")
        original_stream = source_stream = original_dir = source_dir = None
        original_initial = source_initial = None
        source = leaf = None
        failure = None
        try:
            accepted_original = _current_inspection(record)
            n, source = _completed_source(record)
            originals = _existing_child(stack, directory, "originals")
            original_dir = _existing_child(stack, originals, "audio")
            original_leaf = record["audio"]["imported_filename"]
            original_stream = stack.enter_context(os.fdopen(original_dir.open(original_leaf, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)), "rb"))
            original_initial, before = _verify(original_stream, original_dir, original_leaf, record["audio"])
            result["integrity"]["original_before"] = before
            original_media = _fresh_source(config, original_stream, original_dir, original_leaf, accepted_original)
            original_keys = ("audio_codec", "sample_rate", "channels",
                             "selected_audio_stream_index", "stream_count", "demuxer_family")
            if (any(original_media[key] != n["input"]["media"].get(key) for key in original_keys) or
                    abs(original_media["duration_seconds"] - n["input"]["media"]["duration_seconds"]) > 0.000001):
                fail("normalization_stale", "Fresh original facts differ from the completed normalization input; do not reuse this outcome.")
            result["original_duration_seconds"] = original_media["duration_seconds"]
            if n["output_source"] == "normalized":
                normalizations = _existing_child(stack, parent, "normalization")
                source_dir = _existing_child(stack, normalizations, n["attempt_id"])
                leaf = "normalized.m4a"
                source_stream = stack.enter_context(os.fdopen(source_dir.open(leaf, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)), "rb"))
                source_initial, before = _verify(source_stream, source_dir, leaf, source)
                media = _fresh_source(config, source_stream, source_dir, leaf, source["media"])
            else:
                source_stream, source_dir, leaf = original_stream, original_dir, original_leaf
                source_initial, before, media = original_initial, before, original_media
            result["integrity"]["source_before"] = before
            result["source"] = {"kind": n["output_source"], "normalization_attempt_id": n["attempt_id"],
                                "managed_path": source["managed_path"], "sha256": source["sha256"],
                                "size_bytes": source["size_bytes"], "media": media,
                                "full_decode_verified": True}
            result["warnings"] = list(media["warnings"])
            duration = media["duration_seconds"]
            count = part_count(duration, mode)
            regions = []
            if count > 1:
                temp_parent = _existing_child(stack, directory, "temp")
                temp = stack.enter_context(temp_parent.child("plan-" + attempt_id, exclusive=True))
                result["quiet_analysis"]["performed"] = True
                regions = detect_quiet_regions(config, source_stream, source_dir, leaf, media, temp)
                result["quiet_analysis"]["completed"] = True
            result["quiet_analysis"].update(regions=regions, retained_interval_count=len(regions),
                                            event_tolerance_seconds=max(0.05, 2048 / media["sample_rate"]))
            result["plan"] = plan_boundaries(duration, regions, mode=mode)
        except (PlanningFailure, InspectionFailure, NormalizationFailure, OSError, StorageError, KeyboardInterrupt) as exc:
            failure = _failure(exc)
        finally:
            for kind, stream, folder, leaf_name, expected, initial in (
                    ("original", original_stream, original_dir, record["audio"]["imported_filename"], record["audio"], original_initial),
                    ("source", source_stream, source_dir, leaf, source, source_initial)):
                if stream is not None:
                    try:
                        _, check = _verify(stream, folder, leaf_name, expected, initial)
                        result["integrity"][kind + "_after"] = check
                    except (InspectionFailure, OSError, StorageError) as exc:
                        failure = _failure(exc)
                        result["integrity"][kind + "_after"] = {"status": "failed", "code": failure.code}
        result.update(completed_at=datetime.now(timezone.utc).isoformat(), elapsed_seconds=round(time.monotonic() - started, 6))
        if failure:
            result.update(status="planning_failed", plan=None, error={"code": failure.code, "message": str(failure)})
        else:
            result["status"] = "planned"
        try:
            if len(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")) > MAX_PLAN_BYTES:
                fail("plan_metadata_too_large", "Plan record exceeds its private metadata bound.")
            owned.atomic_json(result)
            fd = owned.open("session.json", os.O_RDONLY)
            with os.fdopen(fd, "rb") as published:
                _, digest = hash_stream(published)
            pointer.update(status=result["status"], record_sha256=digest,
                           source=result["source"], error=result["error"], completed_at=result["completed_at"])
            if result["plan"]:
                pointer.update(expected_part_count=result["plan"]["expected_part_count"],
                               mode_fulfilled=result["plan"]["mode_fulfilled"], decision=result["plan"]["decision"])
            directory.atomic_json(record)
        except (OSError, StorageError):
            fail("metadata_persistence_failed", "Plan publication failed; session pending is incomplete. Preserve history.")
        if failure:
            raise PlanningFailure(failure.code, str(failure), result)
        return result
