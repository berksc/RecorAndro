"""Verified audio-only export from a saved nominal plan. No manifest/package."""

from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time
import uuid

from .inspection import (InspectionFailure, _existing_child, _inspection_lock,
                         _load_json, _number, _read_record, _verify, parse_probe, probe_command)
from .normalization import (AAC_RATES, NormalizationFailure, _base, _current_inspection,
                            _eligible, _execute, _executable, _fd_path, _fresh_source,
                            _input_args, pass_timeout)
from .segmentation import MAX_PLAN_BYTES, PlanningFailure, _completed_source, validate_plan
from .sessions import _fingerprint, hash_stream
from .storage import OwnedDirectory, StorageError

POLICY = "aac_m4a_sample_trim_v1"
OVERLAP = 5
MAX_EXPORT_BYTES = 64 * 1024 * 1024
UUID = re.compile(r"[0-9a-f]{32}")
HASH = re.compile(r"[0-9a-f]{64}")


class ExportFailure(ValueError):
    def __init__(self, code, message, attempt=None):
        super().__init__(message)
        self.code, self.attempt = code, attempt


def fail(code, message):
    raise ExportFailure(code, message)


def _json_blob(folder, limit):
    """Read a pinned bounded metadata file with duplicate/nonfinite rejection."""
    fd = folder.open("session.json", os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            fail("invalid_saved_record", "Saved processing record is not a bounded regular file.")
        payload = stream.read(limit + 1)
        if (len(payload) > limit or _fingerprint(os.fstat(fd)) != _fingerprint(info) or
                _fingerprint(folder.info("session.json")) != _fingerprint(info)):
            fail("saved_record_changed", "Saved processing record changed while reading.")
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError
            value[key] = item
        return value
    try:
        value = json.loads(payload, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        fail("invalid_saved_record", "Saved processing JSON is malformed or inconsistent.")
    if not isinstance(value, dict):
        fail("invalid_saved_record", "Saved processing record must be an object.")
    return value, hashlib.sha256(payload).hexdigest()


def export_ranges(plan):
    """Validate the approved nominal geometry; expand ends, never replan."""
    try:
        if (not isinstance(plan, dict) or type(plan.get("schema_version")) is not int or
                plan["schema_version"] != 1 or plan.get("policy_version") != "useful_nominal_plan_v1" or
                plan.get("timeline") != "original_media_relative_seconds" or
                type(plan.get("timeline_start_seconds")) not in (int, float) or
                type(plan.get("timeline_end_seconds")) not in (int, float) or
                plan.get("timeline_start_seconds") != 0 or
                plan.get("timeline_end_seconds") != plan.get("source_duration_seconds") or
                plan.get("source_end_covered") is not True or plan.get("fixed_count_before_boundaries") is not True or
                type(plan.get("expected_part_count")) is not int or type(plan.get("mode_fulfilled")) is not bool or
                not isinstance(plan.get("nominal_parts"), list) or not isinstance(plan.get("boundaries"), list) or
                any(not isinstance(p, dict) for p in plan["nominal_parts"]) or
                any(not isinstance(b, dict) or type(b.get("boundary_index")) is not int for b in plan["boundaries"])):
            fail("invalid_plan", "Requires the exact approved global nominal plan.")
        validate_plan(plan)
        if (plan["mode_fulfilled"] != (plan["mode_requested"] != "force" or plan["expected_part_count"] > 1) or
                plan.get("segmentation_applied") is not (plan["expected_part_count"] > 1) or
                plan.get("plan_kind") != ("segmented" if plan["expected_part_count"] > 1 else "single")):
            fail("invalid_plan", "Saved plan fulfillment/kind differs from its validated count.")
        duration = plan["source_duration_seconds"]
        ranges = []
        for index, nominal in enumerate(plan["nominal_parts"], 1):
            if type(nominal.get("part_index")) is not int or nominal["part_index"] != index:
                fail("invalid_plan", "Nominal part indices must be ordered integers.")
            start, end = nominal["global_start_seconds"], nominal["global_end_seconds"]
            ranges.append({"part_index": index, "nominal_start_seconds": start, "nominal_end_seconds": end,
                           "global_start_seconds": start, "global_end_seconds": min(duration, end + OVERLAP),
                           "requested_duration_seconds": min(duration, end + OVERLAP) - start})
        for index, part in enumerate(ranges):
            # Logical overlap is exact; subtracting two binary floats near an
            # exponent boundary can turn 5 into 5.000000000000114.
            part["overlap_before_seconds"] = OVERLAP if index else 0
            part["overlap_after_seconds"] = OVERLAP if index + 1 < len(ranges) else 0
        coverage(ranges, duration)
        return ranges
    except (KeyError, TypeError, IndexError, PlanningFailure, OverflowError):
        fail("invalid_plan", "Saved nominal ranges/count/boundaries are invalid; export refused.")


def coverage(parts, duration):
    if not parts or parts[0]["global_start_seconds"] != 0 or parts[-1]["global_end_seconds"] != duration:
        fail("invalid_coverage", "Export must cover zero through exact source end.")
    previous = 0
    for index, part in enumerate(parts):
        start, end = part["global_start_seconds"], part["global_end_seconds"]
        if (start != part["nominal_start_seconds"] or part["nominal_start_seconds"] != previous or
                not 0 <= start < end <= duration or
                end != min(duration, part["nominal_end_seconds"] + OVERLAP)):
            fail("invalid_coverage", "Exported ranges must follow contiguous nominal boundaries and capped end-only overlap.")
        before = OVERLAP if index else 0
        after = OVERLAP if index + 1 < len(parts) else 0
        if (part["overlap_before_seconds"] != before or part["overlap_after_seconds"] != after or
                (index and parts[index - 1]["global_end_seconds"] != start + OVERLAP) or
                (index + 1 < len(parts) and end != parts[index + 1]["global_start_seconds"] + OVERLAP)):
            fail("invalid_coverage", "Required adjacent 5-second overlap or no-gap invariant failed.")
        previous = part["nominal_end_seconds"]
    if previous != duration:
        fail("invalid_coverage", "Final nominal end must reach the source endpoint.")
    return {"verified": True, "source_start_seconds": 0, "source_end_seconds": duration,
            "no_gaps": True, "source_end_covered": True, "overlap_verified": True,
            "overlap_seconds": OVERLAP if len(parts) > 1 else 0, "part_count": len(parts)}


def _read_plan(stack, generated, record):
    pointer = record.get("segmentation")
    if (not isinstance(pointer, dict) or pointer.get("status") != "planned" or
            not isinstance(pointer.get("attempt_id"), str) or not UUID.fullmatch(pointer["attempt_id"]) or
            not isinstance(pointer.get("record_sha256"), str) or not HASH.fullmatch(pointer["record_sha256"]) or
            pointer.get("record_path") != f"generated/segmentation/{pointer['attempt_id']}/session.json"):
        fail("approved_plan_required", "Latest segmentation plan must be successfully completed and hash-referenced.")
    parent = _existing_child(stack, generated, "segmentation")
    folder = _existing_child(stack, parent, pointer["attempt_id"])
    analysis, digest = _json_blob(folder, MAX_PLAN_BYTES)
    if digest != pointer["record_sha256"]:
        fail("plan_hash_mismatch", "Saved plan SHA-256 differs from its accepted session pointer.")
    if (type(analysis.get("schema_version")) is not int or analysis["schema_version"] != 1 or analysis.get("session_id") != record["session_id"] or
            analysis.get("attempt_id") != pointer["attempt_id"] or analysis.get("status") != "planned" or
            analysis.get("error") is not None or not isinstance(analysis.get("source"), dict) or
            analysis["source"] != pointer.get("source") or not isinstance(analysis.get("plan"), dict) or
            not isinstance(analysis.get("integrity"), dict) or not isinstance(analysis["source"].get("media"), dict)):
        fail("invalid_plan_record", "Saved plan record is not the latest successful analysis.")
    plan = analysis["plan"]
    ranges = export_ranges(plan)
    if (analysis.get("mode_requested") != pointer.get("mode_requested") or
            plan.get("mode_requested") != analysis["mode_requested"] or
            any(pointer.get(key) != plan.get(key) for key in ("expected_part_count", "mode_fulfilled", "decision")) or
            analysis["source"].get("media", {}).get("duration_seconds") != plan["source_duration_seconds"]):
        fail("invalid_plan_record", "Plan mode/count/working duration differs from its approved record.")
    for kind, expected in (("original", record["audio"]), ("source", analysis["source"])):
        for phase in ("before", "after"):
            check = analysis.get("integrity", {}).get(kind + "_" + phase, {})
            if (not isinstance(check, dict) or check.get("status") != "verified" or
                    check.get("sha256") != expected.get("sha256") or check.get("actual_size_bytes") != expected.get("size_bytes")):
                fail("invalid_plan_record", "Approved analysis lacks source/original integrity evidence.")
    return folder, analysis, ranges, {"attempt_id": pointer["attempt_id"],
                                    "record_path": pointer["record_path"], "sha256": digest}


def copy_suffix(source, count):
    if count != 1 or source["media"]["stream_count"] != 1:
        return None
    suffix = Path(source["managed_path"]).suffix.lower()
    codec = source["media"]["audio_codec"]
    return suffix if (suffix, codec) in ((".m4a", "aac"), (".mp3", "mp3")) else None


def storage_budget(parts, method, source_bytes, free):
    required_audio = sum(source_bytes if method == "byte_copy" else
                         30000 * math.ceil(p["requested_duration_seconds"]) + 65536 for p in parts)
    metadata = MAX_EXPORT_BYTES
    subtotal = required_audio + metadata
    headroom = max(256 * 1024 * 1024, (subtotal + 4) // 5)
    return {"decision": "allow" if free >= subtotal + headroom else "deny", "free_bytes": free,
            "remaining_audio_bytes": required_audio, "metadata_allowance_bytes": metadata,
            "headroom_bytes": headroom, "estimated_required_bytes": subtotal + headroom,
            "reservation": False, "temporary_publication": "same_inode_move_no_full_copy_duplication"}


def _probe_part(config, stream, folder, leaf):
    args = probe_command(_executable(config.ffprobe, "ffprobe"), _fd_path(stream, folder, leaf))
    entry = args.index("-show_entries") + 1
    args[entry] = args[entry].replace("codec_name,", "codec_name,profile,")
    data = _execute(args, 30, "part_probe", pass_fds=(stream.fileno(),), capture_stdout=True)
    media = parse_probe(data, Path(leaf).suffix)
    selected = next(s for s in _load_json(data)["streams"] if s["index"] == media["selected_audio_stream_index"])
    media["codec_profile"] = selected.get("profile")
    return media


def verify_part(media, source_media, part, method):
    _eligible(media)
    copied = method == "byte_copy"
    rate = source_media["sample_rate"] if copied or source_media["sample_rate"] in AAC_RATES else 48000
    tolerance = 0 if copied else max(0.05, 2048 / min(source_media["sample_rate"], rate))
    expected_codec = source_media["audio_codec"] if copied else "aac"
    expected_family = source_media["demuxer_family"] if copied else "mov"
    if (media["stream_count"] != 1 or media["audio_codec"] != expected_codec or
            media["demuxer_family"] != expected_family or media["sample_rate"] != rate or
            media["channels"] != source_media["channels"] or (not copied and media.get("codec_profile") != "LC")):
        fail("invalid_part_format", "Part stream/codec/profile/rate/channels do not satisfy its copy/encode policy.")
    delta = abs(media["duration_seconds"] - part["requested_duration_seconds"])
    start = _number(media.get("stream_start_seconds"), minimum=-2**53)
    if delta > tolerance or (not copied and (start is None or abs(start) > tolerance)):
        fail("invalid_part_timing", "Part duration/start exceeds the frozen fixed tolerance.")
    return {"passed": True, "duration_delta_seconds": delta, "tolerance_seconds": tolerance,
            "stream_start_seconds": media.get("stream_start_seconds"), "full_decode_passed": False,
            "sample_rounding_max_seconds": 0 if copied else 0.5 / source_media["sample_rate"]}


def _copy(stream, temp, leaf, timeout):
    start = time.monotonic()
    stream.seek(0)
    fd = temp.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    try:
        with os.fdopen(fd, "wb") as output:
            while chunk := stream.read(1024 * 1024):
                if time.monotonic() - start > timeout:
                    fail("copy_timeout", "Independent full-length copy exceeded its per-pass deadline.")
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        # This function owns the file only after successful exclusive open.
        temp.unlink(leaf)
        raise


def _verify_file(config, folder, leaf, part, source, executable, timeout, expected=None):
    # Read-only published files; Windows fsync is performed on temporary RW handles.
    fd = folder.open(leaf, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
            fail("empty_part", "Exported part must be nonempty regular audio.")
        size, digest = hash_stream(stream)
        actual = {"size_bytes": size, "sha256": digest}
        if expected is not None and actual != {k: expected[k] for k in actual}:
            fail("part_integrity_mismatch", "Previously verified part changed; no complete export accepted.")
        _verify(stream, folder, leaf, actual, info)
        media = _probe_part(config, stream, folder, leaf)
        verification = verify_part(media, source["media"], part, part["method"])
        _execute(_base(executable) + _input_args(_fd_path(stream, folder, leaf), media) + ["-f", "null", "-"],
                 timeout, "part_decode", pass_fds=(fd,))
        _verify(stream, folder, leaf, actual, info)
        if part["method"] == "byte_copy" and actual != {k: source[k] for k in actual}:
            fail("copy_integrity_mismatch", "Full-length independent copy must match exact source bytes and SHA-256.")
        verification["full_decode_passed"] = True
        return actual, media, verification, info


def _failure(exc):
    if isinstance(exc, ExportFailure):
        return exc
    if isinstance(exc, (InspectionFailure, NormalizationFailure, PlanningFailure)):
        return ExportFailure(exc.code, str(exc))
    if isinstance(exc, KeyboardInterrupt):
        return ExportFailure("export_interrupted", "Export interrupted; sources and verified parts retained. Retry explicitly.")
    return ExportFailure("export_access_failed", "Cannot safely read/write owned export files; sources and verified parts retained.")


def _persist(owned, directory, result, pointer, record):
    if len(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")) > MAX_EXPORT_BYTES:
        fail("export_record_too_large", "Export record exceeds its bounded metadata allowance.")
    try:
        owned.atomic_json(result)
        fd = owned.open("session.json", os.O_RDONLY)
        with os.fdopen(fd, "rb") as stream:
            _, digest = hash_stream(stream)
        pointer.update(status=result["status"], success=result["success"], record_sha256=digest,
                       verified_part_count=sum(p["status"] == "verified" for p in result["parts"]),
                       error=result["error"], completed_at=result["completed_at"])
        directory.atomic_json(record)
    except (OSError, StorageError):
        fail("metadata_persistence_failed", "Export metadata publication failed; persisted pending/partial is incomplete. Preserve owned files.")


def _reuse_candidates(stack, generated, previous, reference, source):
    if not isinstance(previous, dict) or not isinstance(previous.get("attempt_id"), str) or not UUID.fullmatch(previous["attempt_id"]):
        return {}, False
    try:
        if previous.get("record_path") != f"generated/exports/{previous['attempt_id']}/session.json":
            return {}, True
        parent = _existing_child(stack, generated, "exports")
        folder = _existing_child(stack, parent, previous["attempt_id"])
        saved, digest = _json_blob(folder, MAX_EXPORT_BYTES)
        if (digest != previous.get("record_sha256") or saved.get("policy") != POLICY or
                saved.get("overlap_seconds") != OVERLAP or saved.get("plan_reference") != reference or
                saved.get("source") != source or not isinstance(saved.get("parts"), list)):
            return {}, True
        candidates = {}
        for part in saved["parts"]:
            if isinstance(part, dict) and type(part.get("part_index")) is int and part.get("status") == "verified":
                if part["part_index"] in candidates:
                    return {}, True
                candidates[part["part_index"]] = part
        return candidates, False
    except (ExportFailure, InspectionFailure, OSError, StorageError):
        return {}, True


def _part_folder(stack, exports, part):
    path = part.get("managed_path")
    filename = part.get("filename")
    if not isinstance(path, str) or not isinstance(filename, str):
        fail("invalid_part_reference", "Reusable part lacks an owned generated reference.")
    pieces = path.split("/")
    if (len(pieces) != 4 or pieces[:2] != ["generated", "exports"] or
            not UUID.fullmatch(pieces[2]) or pieces[3] != filename):
        fail("invalid_part_reference", "Part reference must stay in its immutable export directory.")
    return _existing_child(stack, exports, pieces[2])


def export_session(config, session_id, *, retry=False):
    """Reusable blocking operation; CLI/UI callers receive identical structured facts."""
    if not isinstance(session_id, str) or not UUID.fullmatch(session_id):
        fail("invalid_session_id", "Export requires an existing imported session identifier.")
    started = time.monotonic()
    with ExitStack() as stack:
        if not config.data_root.is_dir():
            fail("session_unavailable", "Configured session data root is unavailable.")
        root = stack.enter_context(OwnedDirectory.root(config.data_root))
        sessions = _existing_child(stack, root, "sessions")
        directory = _existing_child(stack, sessions, session_id)
        stack.enter_context(_inspection_lock(directory))
        record = _read_record(directory, session_id)
        previous = record.get("audio_export")
        if previous is not None and (not isinstance(previous, dict) or previous.get("status") not in
                                    ("export_pending", "export_failed", "export_succeeded")):
            fail("invalid_export_record", "Latest export status is invalid.")
        if previous and previous["status"] != "export_succeeded" and not retry:
            fail("retry_required", "Previous export failed/interrupted; pass --retry after diagnosis.")
        generated = _existing_child(stack, directory, "generated")
        exports = stack.enter_context(generated.child("exports"))
        attempt_id = uuid.uuid4().hex
        owned = stack.enter_context(exports.child(attempt_id, exclusive=True))
        result = {"schema_version": 1, "session_id": session_id, "attempt_id": attempt_id,
                  "policy": POLICY, "status": "export_pending", "success": False, "retry_requested": retry,
                  "created_at": datetime.now(timezone.utc).isoformat(), "completed_at": None, "elapsed_seconds": None,
                  "plan_reference": None, "source": None, "original_duration_seconds": None,
                  "overlap_seconds": OVERLAP, "parts": [], "part_count": None,
                  "coverage": None, "integrity": {}, "storage_preflight": None, "warnings": [],
                  "silence_removed": False, "error": None}
        pointer = {"schema_version": 1, "attempt_id": attempt_id, "status": "export_pending", "success": False,
                   "record_path": f"generated/exports/{attempt_id}/session.json", "record_sha256": None}
        record["audio_export"] = pointer
        _persist(owned, directory, result, pointer, record)
        original_stream = source_stream = original_dir = source_dir = None
        original_initial = source_initial = source = leaf = active = temp = None
        original_leaf = record["audio"]["imported_filename"]
        failure = None
        try:
            plan_folder, analysis, ranges, reference = _read_plan(stack, generated, record)
            n, selected = _completed_source(record)
            source = analysis["source"]
            if (source.get("normalization_attempt_id") != n["attempt_id"] or source.get("kind") != n["output_source"] or
                    any(source.get(k) != selected.get(k) for k in ("managed_path", "size_bytes", "sha256"))):
                fail("stale_plan_source", "Latest plan no longer selects the current normalization artifact/revision.")
            accepted = _current_inspection(record)
            originals = _existing_child(stack, directory, "originals")
            original_dir = _existing_child(stack, originals, "audio")
            original_stream = stack.enter_context(os.fdopen(original_dir.open(original_leaf, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)), "rb"))
            original_initial, check = _verify(original_stream, original_dir, original_leaf, record["audio"])
            result["integrity"]["original_before"] = check
            original_media = _fresh_source(config, original_stream, original_dir, original_leaf, accepted)
            _compare_media(original_media, n["input"]["media"])
            if source["kind"] == "normalized":
                parent = _existing_child(stack, generated, "normalization")
                source_dir = _existing_child(stack, parent, n["attempt_id"])
                leaf = "normalized.m4a"
                source_stream = stack.enter_context(os.fdopen(source_dir.open(leaf, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)), "rb"))
                source_initial, check = _verify(source_stream, source_dir, leaf, selected)
                media = _fresh_source(config, source_stream, source_dir, leaf, selected["media"])
            else:
                source_stream, source_dir, leaf = original_stream, original_dir, original_leaf
                source_initial, media = original_initial, original_media
            _compare_media(media, source["media"])
            if media["duration_seconds"] != analysis["plan"]["source_duration_seconds"]:
                fail("stale_plan_duration", "Fresh working duration differs from the exact approved plan endpoint.")
            result["integrity"]["source_before"] = check
            result.update(plan_reference=reference, source=source, part_count=len(ranges),
                          original_duration_seconds=original_media["duration_seconds"])
            pointer.update(plan_reference=reference, source=source, part_count=len(ranges))
            executable = _executable(config.ffmpeg, "ffmpeg")
            timeout = pass_timeout(media["duration_seconds"])
            suffix = copy_suffix(source, len(ranges))
            method = "byte_copy" if suffix else "decode_sample_trim_aac"
            rate = media["sample_rate"] if suffix or media["sample_rate"] in AAC_RATES else 48000
            bitrate = None if suffix else 128000 if media["channels"] == 1 else 192000
            artifact = {k: source[k] for k in ("kind", "normalization_attempt_id", "managed_path", "sha256", "size_bytes")}
            for interval in ranges:
                filename = f"part_{interval['part_index']:02d}{suffix or '.m4a'}"
                result["parts"].append(dict(interval, filename=filename, method=method,
                     source_artifact=artifact, selected_audio_stream_index=media["selected_audio_stream_index"],
                     requested_encoding=None if suffix else {"codec": "aac", "profile": "aac_low", "muxer": "ipod",
                         "container": "m4a", "sample_rate": rate, "channels": media["channels"], "bitrate": bitrate},
                     status="pending", managed_path=None, size_bytes=None, sha256=None,
                     duration_seconds=None, media=None, verification=None, reused=False))
                if not suffix:
                    result["parts"][-1].update(
                        source_start_sample=round(interval["global_start_seconds"] * media["sample_rate"]),
                        source_end_sample=round(interval["global_end_seconds"] * media["sample_rate"]))
            candidates, unavailable = _reuse_candidates(stack, generated, previous, reference, source)
            if unavailable:
                result["warnings"].append("previous_export_not_reusable")
            # Revalidate reuse before budgeting new output; failures get new owned files.
            for part in result["parts"]:
                old = candidates.get(part["part_index"])
                if old is None:
                    continue
                try:
                    keys = (*ranges[0].keys(), "filename", "method", "source_artifact", "selected_audio_stream_index", "requested_encoding")
                    if not suffix:
                        keys += ("source_start_sample", "source_end_sample")
                    if any(old.get(k) != part[k] for k in keys):
                        fail("stale_part_record", "Earlier part geometry/source/policy does not match this plan.")
                    folder = _part_folder(stack, exports, old)
                    actual, out_media, verified, _ = _verify_file(config, folder, old["filename"], part, source, executable, timeout, old)
                    part.update(status="verified", managed_path=old["managed_path"], reused=True,
                                duration_seconds=out_media["duration_seconds"], media=out_media, verification=verified, **actual)
                except (ExportFailure, InspectionFailure, NormalizationFailure, OSError, StorageError, KeyError, TypeError):
                    result["warnings"].append("previous_part_not_reusable")
            pending = [p for p in result["parts"] if p["status"] != "verified"]
            result["storage_preflight"] = storage_budget(pending, method, source["size_bytes"], root.free_bytes()) if pending else None
            if pending and result["storage_preflight"]["decision"] != "allow":
                fail("insufficient_storage", "Current storage is below the remaining-output/headroom budget; verified parts retained.")
            _persist(owned, directory, result, pointer, record)
            if pending:
                parent = _existing_child(stack, directory, "temp")
                temp = stack.enter_context(parent.child("export-" + attempt_id, exclusive=True))
            for part in pending:
                active = part
                pending_leaf = "pending-" + part["filename"]
                try:
                    temp.info(pending_leaf)
                except FileNotFoundError:
                    pass
                else:
                    fail("temporary_output_exists", "Refusing an unexpected existing temporary part.")
                created = False
                try:
                    if suffix:
                        _copy(source_stream, temp, pending_leaf, timeout)
                        created = True
                    else:
                        start_sample = part["source_start_sample"]
                        end_sample = part["source_end_sample"]
                        if end_sample <= start_sample:
                            fail("empty_sample_range", "Nominal export has no samples at its source rate.")
                        target = f"/proc/self/fd/{temp.fd}/{pending_leaf}" if os.name == "posix" else temp.path / pending_leaf
                        args = _base(executable) + _input_args(_fd_path(source_stream, source_dir, leaf), media)
                        args += ["-map_metadata", "-1", "-map_chapters", "-1", "-af",
                                 f"atrim=start_sample={start_sample}:end_sample={end_sample},asetpts=PTS-STARTPTS",
                                 "-c:a", "aac", "-profile:a", "aac_low", "-b:a", str(bitrate), "-ar", str(rate),
                                 "-movflags", "+faststart", "-f", "ipod", str(target)]
                        created = True
                        _execute(args, timeout, "part_encode", pass_fds=(source_stream.fileno(),) + ((temp.fd,) if os.name == "posix" else ()))
                    actual, out_media, verified, info = _verify_file(config, temp, pending_leaf, part, source, executable, timeout)
                    _verify(source_stream, source_dir, leaf, source, source_initial)
                    _verify(original_stream, original_dir, original_leaf, record["audio"], original_initial)
                    fd = temp.open(pending_leaf, os.O_RDWR)
                    with os.fdopen(fd, "rb") as flushed:
                        _verify(flushed, temp, pending_leaf, actual, info)
                        os.fsync(fd)
                        if os.name == "posix":
                            os.fchmod(fd, 0o400)
                    temp.publish(pending_leaf, part["filename"], owned)
                    fd = owned.open(part["filename"], os.O_RDONLY)
                    with os.fdopen(fd, "rb") as final:
                        after = os.fstat(fd)
                        if (after.st_dev, after.st_ino) != (info.st_dev, info.st_ino):
                            fail("part_identity_changed", "Published part differs from the verified temporary inode.")
                        _verify(final, owned, part["filename"], actual)
                    part.update(status="verified", managed_path=f"generated/exports/{attempt_id}/{part['filename']}",
                                duration_seconds=out_media["duration_seconds"], media=out_media, verification=verified, **actual)
                    _persist(owned, directory, result, pointer, record)
                finally:
                    if created:
                        try:
                            temp.unlink(pending_leaf)
                        except FileNotFoundError:
                            pass
                        except (OSError, StorageError):
                            result["warnings"].append("temporary_cleanup_failed")
            # Recheck every published/reused part and approved plan, not merely list length.
            for part in result["parts"]:
                if part["status"] != "verified":
                    fail("incomplete_export", "A required part remains unverified or unpublished.")
                folder = _part_folder(stack, exports, part)
                with os.fdopen(folder.open(part["filename"], os.O_RDONLY), "rb") as stream:
                    _verify(stream, folder, part["filename"], part)
            _, plan_digest = _json_blob(plan_folder, MAX_PLAN_BYTES)
            if plan_digest != reference["sha256"]:
                fail("plan_changed", "Approved plan changed during export; no complete export accepted.")
            result["coverage"] = coverage(result["parts"], media["duration_seconds"])
        except (ExportFailure, InspectionFailure, NormalizationFailure, PlanningFailure,
                OSError, StorageError, KeyboardInterrupt, KeyError, TypeError, IndexError) as exc:
            failure = _failure(exc)
            if active is not None and active["status"] != "verified":
                active["status"] = "failed"
                active["error"] = {"code": failure.code, "message": str(failure)}
        finally:
            for kind, stream, folder, name, expected, initial in (
                    ("original", original_stream, original_dir, original_leaf, record["audio"], original_initial),
                    ("source", source_stream, source_dir, leaf, source, source_initial)):
                if stream is not None:
                    try:
                        _, check = _verify(stream, folder, name, expected, initial)
                        result["integrity"][kind + "_after"] = check
                    except (InspectionFailure, OSError, StorageError) as exc:
                        failure = _failure(exc)
                        result["integrity"][kind + "_after"] = {"status": "failed", "code": failure.code}
        result.update(completed_at=datetime.now(timezone.utc).isoformat(), elapsed_seconds=round(time.monotonic() - started, 6))
        if failure:
            result.update(status="export_failed", success=False, coverage=None,
                          error={"code": failure.code, "message": str(failure)})
        else:
            result.update(status="export_succeeded", success=True)
        _persist(owned, directory, result, pointer, record)
        if failure:
            raise ExportFailure(failure.code, str(failure), result)
        return result


def _compare_media(actual, saved):
    _eligible(saved)
    keys = ("audio_codec", "demuxer_family", "sample_rate", "channels", "stream_count", "selected_audio_stream_index")
    if (any(actual[k] != saved[k] for k in keys) or abs(actual["duration_seconds"] - saved["duration_seconds"]) > 0.000001):
        fail("stale_source_media", "Fresh source facts differ from approved processing metadata.")
