"""Versioned progress/registry projection; no processing, recovery or new writer.

The legacy import ``state`` and stage records remain authoritative. A current
verified chain may regress when an explicit new attempt invalidates a revision.
Canonical metadata is protected but deliberately never hashes itself.
"""

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import PurePosixPath
import re
import stat

from .storage import OwnedDirectory, StorageError

SCHEMA_VERSION = 2
STATE_MODEL_VERSION = 1
STATES = ("created", "imported", "probed", "normalized_or_skipped",
          "segmentation_planned", "segments_exported", "manifested", "packaged",
          "archived_or_skipped", "complete", "failed")
PROTECTED_TYPES = {"original_audio", "original_photo", "session_metadata"}
REGENERABLE_TYPES = {"normalized_audio", "audio_part", "normalization_report",
                     "segmentation_report", "export_report", "report", "manifest",
                     "zip_package", "full_archive"}
ARTIFACT_STATUSES = {"pending", "verified", "failed", "stale", "unverified", "canonical"}
VISUAL_STATUSES = {"not_present", "pending", "indexed", "partial_warning", "failed_nonblocking"}
IDENTITY_KEYS = ("managed_path", "size_bytes", "sha256", "imported_filename", "original_filename", "source_bytes")
UUID = re.compile(r"[0-9a-f]{32}")
HASH = re.compile(r"[0-9a-f]{64}")
PROJECTION_KEYS = ("schema_version", "state_model_version", "updated_at", "current_state",
                   "last_successful_state", "failed_stage", "error_code", "error_message",
                   "retryable", "active_stage", "artifact_registry", "progress_warnings",
                   "selected_normalization_mode", "selected_segmentation_mode",
                   "segmentation_plan_identity", "verified_part_count", "package_status", "archive_status")


def _require(condition, message):
    if not condition:
        raise StorageError(message)


def _object(value):
    return value if isinstance(value, dict) else {}


def _read(directory):
    from .inspection import MAX_JSON_BYTES, _load_json
    with os.fdopen(directory.open("session.json", os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)), "rb") as stream:
        _require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Metadata must be regular")
        return _load_json(stream.read(MAX_JSON_BYTES + 1))


def _validate(record, session_id):
    _require(isinstance(record, dict) and type(record.get("schema_version")) is int and
             record["schema_version"] in (1, 2), "Unsupported session schema")
    _require(isinstance(session_id, str) and UUID.fullmatch(session_id) and
             record.get("session_id") == session_id, "Session ID is immutable and must match its directory")
    _require(record.get("state") in ("importing", "imported", "failed") and
             isinstance(record.get("audio"), dict), "Invalid legacy import record")
    _require(type(record.get("visual_count")) is int and record["visual_count"] >= 0,
             "visual_count must be a nonnegative integer")
    _require(type(record.get("state_model_version", 1)) is int and
             record.get("state_model_version", 1) == STATE_MODEL_VERSION, "Unsupported state model")


def _folder(stack, directory, path):
    from .inspection import _existing_child
    _require(isinstance(path, str) and path and "\\" not in path and ":" not in path and
             not path.startswith("/") and all(p not in ("", ".", "..") for p in path.split("/")),
             "Artifact path must be a safe session-relative path")
    parts = PurePosixPath(path).parts
    for part in parts[:-1]:
        directory = _existing_child(stack, directory, part)
    return directory, parts[-1]


def _check_file(stack, directory, artifact):
    from .inspection import _verify
    folder, leaf = _folder(stack, directory, artifact["relative_path"])
    with os.fdopen(folder.open(leaf, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)), "rb") as stream:
        _verify(stream, folder, leaf, artifact)


def artifact_entry(artifact_id, kind, path, *, status="pending", source=None,
                   size=None, sha256=None, media=None, created_at=None, verified_at=None,
                   revision=None):
    """Construct a classified entry; verification is established by stage readers."""
    _require(kind in PROTECTED_TYPES | REGENERABLE_TYPES and status in ARTIFACT_STATUSES,
             "Unknown artifact type/status")
    if kind == "session_metadata":
        _require(path == "session.json" and sha256 is None and size is None,
                 "Canonical session metadata must not hash itself")
    if status == "verified":
        _require(type(size) is int and size > 0 and isinstance(sha256, str) and HASH.fullmatch(sha256)
                 and verified_at is not None, "Verified artifact requires size/hash/time evidence")
    protected = kind in PROTECTED_TYPES
    return {"artifact_id": artifact_id, "type": kind, "relative_path": path,
            "status": status, "source_artifact_id": source, "size_bytes": size,
            "sha256": sha256, "media": media, "created_at": created_at,
            "verified_at": verified_at, "revision_id": revision,
            "classification": "protected" if protected else "regenerable",
            "protected": protected, "regenerable": not protected}


def project_session(directory, record, *, _normalization_intent=False, _audio_only=False,
                    _documents_only=False, _packages_only=False):
    """Read evidence under the caller's existing session lock; never write files.

    Hashes verify referenced bytes, not paths or directory scans. No orphan is
    adopted. Current stage evidence gates progression; older entries stay stale.
    """
    from .inspection import _existing_child
    from .normalization import _current_inspection
    from .segmentation import _completed_source
    from .exports import (MAX_EXPORT_BYTES, POLICY, _json_blob, _read_plan,
                          _part_folder, _compare_media, coverage, verify_part)

    _validate(record, directory.path.name)
    result = deepcopy(record)
    registry = deepcopy(record.get("artifact_registry", {}))
    _require(isinstance(registry, dict), "Artifact registry must be an object")
    for artifact_id, entry in registry.items():
        _require(isinstance(entry, dict), "Invalid artifact entry")
        _require(entry.get("artifact_id") == artifact_id and entry.get("type") in PROTECTED_TYPES | REGENERABLE_TYPES and
                 entry.get("status") in ARTIFACT_STATUSES, "Invalid artifact identity/type/status")
        protected = entry["type"] in PROTECTED_TYPES
        _require(entry.get("protected") is protected and entry.get("regenerable") is (not protected) and
                 entry.get("classification") == ("protected" if protected else "regenerable"),
                 "Artifact protection classification cannot change")
        if entry.get("type") in REGENERABLE_TYPES:
            entry["status"] = "stale"
    created = record.get("created_at")
    registry["session_metadata"] = artifact_entry("session_metadata", "session_metadata", "session.json",
                                                  status="canonical", created_at=created)
    frontier, failure, active, warnings = "created", None, None, []
    if "visual_status" in record and (not isinstance(record["visual_status"], str) or
                                      record["visual_status"] not in VISUAL_STATUSES):
        warnings.append("invalid_optional_visual_status")
    stage = "import"
    part_count = 0
    plan_identity = None

    def error(code, message):
        return {"code": code, "message": message}

    def report(kind, pointer, status):
        attempt = pointer.get("attempt_id")
        _require(isinstance(attempt, str) and UUID.fullmatch(attempt), "Invalid stage revision")
        path = pointer.get("record_path") or f"generated/normalization/{attempt}/session.json"
        expected_path = f"generated/{kind}/{attempt}/session.json"
        _require(path == expected_path, "Stage report path differs from revision")
        folder, leaf = _folder(stack, directory, path)
        limit = MAX_EXPORT_BYTES if kind == "exports" else 32 * 1024 * 1024
        # Existing bounded report reader also rejects duplicate keys and NaN.
        saved, digest = _json_blob(folder, limit)
        size = folder.info(leaf).st_size
        if kind == "normalization":
            # Recovery may validate a ready result against its still-pending
            # report. All original/revision/final-file gates remain required.
            # Normal projection/writes never promote publication intent.
            if (_normalization_intent and saved.get("status") == "normalization_pending" and
                    isinstance(saved.get("publication_intent"), dict)):
                saved = saved["publication_intent"]
            _require(saved == pointer, "Normalization report differs from latest stage record")
        else:
            _require(digest == pointer.get("record_sha256") and saved.get("attempt_id") == attempt and
                     saved.get("session_id") == record["session_id"] and
                     saved.get("status") == pointer.get("status"), "Report identity/hash/status mismatch")
        entry = artifact_entry(f"{kind}_report:{attempt}",
                               {"normalization": "normalization_report", "segmentation": "segmentation_report",
                                "exports": "export_report"}[kind], path, status=status,
                               source=source_id, size=size, sha256=digest, created_at=saved.get("created_at"),
                               verified_at=saved.get("completed_at") if status == "verified" else None,
                               revision=attempt)
        registry[entry["artifact_id"]] = entry
        return saved

    def artifact(identity, kind, artifact_id, revision, timestamp):
        entry = artifact_entry(artifact_id, kind, identity.get("managed_path"), status="verified",
                               source=source_id if kind != "original_audio" else None,
                               size=identity.get("size_bytes"), sha256=identity.get("sha256"),
                               media=identity.get("media"), created_at=timestamp,
                               verified_at=timestamp, revision=revision)
        # Add before checking so a failed check remains visible in the registry.
        registry[artifact_id] = entry
        try:
            _check_file(stack, directory, entry)
        except (ValueError, OSError):
            entry.update(status="unverified", verified_at=None)
            raise

    source_id = "original_audio"
    with ExitStack() as stack:
        try:
            if record["state"] == "failed":
                errors = record.get("errors", [])
                failure = errors[-1] if errors else error("audio_import_failed", "Import did not complete")
            elif record["state"] == "imported":
                # Reuse the frozen original-reference validation, accepting v1/v2.
                # Validate supplied candidate without reading old stage data.
                audio = record["audio"]
                from .storage import safe_leaf
                leaf = audio.get("imported_filename")
                _require(isinstance(leaf, str) and safe_leaf(leaf) == leaf and
                         audio.get("managed_path") == f"originals/audio/{leaf}", "Invalid original reference")
                artifact(audio, "original_audio", "original_audio", None, created)
                frontier = "imported"
                stages = (("inspection", "probed", "probe_pending", "probe_failed"),
                          ("normalization", "normalization_succeeded", "normalization_pending", "normalization_failed"),
                          ("segmentation", "planned", "planning_pending", "planning_failed"),
                          ("audio_export", "export_succeeded", "export_pending", "export_failed"))
                for stage, succeeded, pending, failed in stages:
                    pointer = record.get(stage)
                    if pointer is None:
                        break
                    _require(isinstance(pointer, dict), "Stage record must be an object")
                    active = stage
                    status = pointer.get("status")
                    if status in (pending, failed):
                        if status == failed:
                            failure = pointer.get("error") or error(stage + "_failed", "Stage failed")
                        # Reports from incomplete attempts cannot establish success.
                        if stage == "normalization" or (stage in ("segmentation", "audio_export") and pointer.get("record_sha256")):
                            incomplete = report({"normalization": "normalization", "segmentation": "segmentation", "audio_export": "exports"}[stage], pointer,
                                                "pending" if status == pending else "failed")
                            if stage == "audio_export":
                                for part in incomplete.get("parts", []):
                                    part_id = f"audio_part:{pointer['attempt_id']}:{part['part_index']}"
                                    # Retain salvage candidates without claiming
                                    # a completed source/coverage verification.
                                    part_status = part.get("status")
                                    entry = artifact_entry(part_id, "audio_part", part.get("managed_path"),
                                                           status=part_status if part_status in ("pending", "failed") else "unverified",
                                                           source=source_id, size=part.get("size_bytes"), sha256=part.get("sha256"),
                                                           media=part.get("media"), created_at=incomplete.get("created_at"),
                                                           revision=pointer["attempt_id"])
                                    entry["stage_part_status"] = part_status
                                    entry["plan_reference"] = incomplete.get("plan_reference")
                                    registry[part_id] = entry
                        break
                    _require(status == succeeded, "Unknown stage status")
                    _require(pointer.get("completed_at") and pointer.get("error") is None,
                             "Completed stage lacks completion/error evidence")
                    if stage == "inspection":
                        _require(pointer.get("probe_status") == "succeeded" and
                                 isinstance(pointer.get("media"), dict) and
                                 isinstance(pointer.get("attempt_id"), str) and UUID.fullmatch(pointer["attempt_id"]),
                                 "Probe result is incomplete")
                        _require(pointer.get("source", {}).get("imported_sha256") == audio["sha256"] and
                                 pointer["source"].get("expected_size_bytes") == audio["size_bytes"], "Probe source is stale")
                        for phase in ("before", "after"):
                            check = pointer.get("integrity", {}).get(phase, {})
                            _require(check.get("status") == "verified" and check.get("sha256") == audio["sha256"] and
                                     check.get("actual_size_bytes") == audio["size_bytes"], "Probe integrity is incomplete")
                        registry["original_audio"]["media"] = pointer["media"]
                        frontier = "probed"
                    elif stage == "normalization":
                        inspected_media = _current_inspection(record)
                        n, source = _completed_source(record)
                        if n["input"].get("inspection_attempt_id") != record["inspection"]["attempt_id"]:
                            warnings.append("stale_normalization_revision")
                            break
                        _compare_media(n["input"]["media"], inspected_media)
                        _require(n.get("decision") and n.get("duration_integrity", {}).get("passed") is True,
                                 "Normalization decision/result is incomplete")
                        report("normalization", n, "verified")
                        if n["output_source"] == "normalized":
                            source_id = "original_audio"
                            artifact(source, "normalized_audio", "normalized_audio:" + n["attempt_id"],
                                     n["attempt_id"], n["completed_at"])
                            source_id = "normalized_audio:" + n["attempt_id"]
                        frontier = "normalized_or_skipped"
                    elif stage == "segmentation":
                        generated = _existing_child(stack, directory, "generated")
                        _, analysis, ranges, reference = _read_plan(stack, generated, record)
                        selected = analysis["source"]
                        if (selected.get("normalization_attempt_id") != n["attempt_id"] or
                                selected.get("kind") != n["output_source"] or
                                any(selected.get(k) != source.get(k) for k in ("managed_path", "size_bytes", "sha256"))):
                            warnings.append("stale_segmentation_revision")
                            break
                        report("segmentation", pointer, "verified")
                        warnings.extend(analysis.get("warnings", []))
                        plan_identity = dict(reference, policy_version=analysis["plan"].get("policy_version"))
                        frontier = "segmentation_planned"
                    else:
                        saved = report("exports", pointer, "verified")
                        if saved.get("plan_reference") != reference or saved.get("source") != selected:
                            registry["exports_report:" + pointer["attempt_id"]]["status"] = "stale"
                            warnings.append("stale_export_revision")
                            break
                        warnings.extend(saved.get("warnings", []))
                        _require(saved.get("schema_version") == 1 and saved.get("policy") == POLICY and
                                 saved.get("success") is True and pointer.get("success") is True and
                                 pointer.get("plan_reference") == reference and pointer.get("source") == selected and
                                 saved.get("completed_at") and saved.get("error") is None,
                                 "Export completion evidence is incomplete")
                        parts = saved.get("parts")
                        _require(isinstance(parts, list) and len(parts) == len(ranges) and
                                 saved.get("part_count") == len(parts) and pointer.get("part_count") == len(parts) and
                                 pointer.get("verified_part_count") == len(parts), "Export part count is incomplete")
                        for kind, expected in (("original", audio), ("source", selected)):
                            for phase in ("before", "after"):
                                check = saved.get("integrity", {}).get(kind + "_" + phase, {})
                                _require(check.get("status") == "verified" and check.get("sha256") == expected["sha256"] and
                                         check.get("actual_size_bytes") == expected["size_bytes"], "Export integrity is incomplete")
                        exports = stack.enter_context(generated.child("exports"))
                        expected_source = {k: selected[k] for k in ("kind", "normalization_attempt_id", "managed_path", "sha256", "size_bytes")}
                        for part, geometry in zip(parts, ranges):
                            _require(part.get("status") == "verified" and part.get("source_artifact") == expected_source and
                                     all(part.get(k) == v for k, v in geometry.items()) and
                                     part.get("method") in ("byte_copy", "decode_sample_trim_aac") and
                                     part.get("verification", {}).get("full_decode_passed") is True,
                                     "Required part lacks current source/geometry/decode verification")
                            _part_folder(stack, exports, part)
                            verify_part(part.get("media"), selected["media"], part, part.get("method"))
                            if part["method"] == "byte_copy":
                                _require(all(part.get(k) == selected[k] for k in ("sha256", "size_bytes")),
                                         "Full-length copy identity differs from its verified source")
                            artifact(part, "audio_part", f"audio_part:{pointer['attempt_id']}:{part['part_index']}",
                                     pointer["attempt_id"], saved["completed_at"])
                            registry[f"audio_part:{pointer['attempt_id']}:{part['part_index']}"]["plan_reference"] = reference
                        _require(saved.get("coverage") == coverage(parts, selected["media"]["duration_seconds"]),
                                 "Export coverage is incomplete")
                        part_count = len(parts)
                        frontier = "segments_exported"
                    active = None
        except (ValueError, OSError, KeyError, TypeError, IndexError, AttributeError) as exc:
            failure = error(getattr(exc, "code", "invalid_stage_evidence"),
                            str(exc) if isinstance(exc, ValueError) else "Cannot verify current owned stage evidence")
            # Any report added before its semantic validation is not verified.
            for entry in registry.values():
                if entry.get("type") == {"normalization": "normalization_report", "segmentation": "segmentation_report",
                                         "audio_export": "export_report"}.get(stage):
                    entry.update(status="unverified", verified_at=None)

    if failure and not isinstance(failure, dict):
        failure = error("invalid_stage_evidence", "Stage error record is malformed")
    code = failure.get("code") if failure else None
    result.update(schema_version=SCHEMA_VERSION, state_model_version=STATE_MODEL_VERSION,
                  current_state="failed" if failure else frontier, last_successful_state=frontier,
                  failed_stage=stage if failure else None, error_code=code,
                  error_message=failure.get("message") if failure else None,
                  retryable=bool(failure) and code != "invalid_stage_evidence" and not
                  (stage == "import" and code in {"original_hash_mismatch", "original_size_mismatch",
                                                 "original_identity_changed"}),
                  active_stage=active, artifact_registry=registry, progress_warnings=warnings,
                  selected_normalization_mode=_object(record.get("normalization")).get("mode_requested"),
                  selected_segmentation_mode=_object(record.get("segmentation")).get("mode_requested"),
                  segmentation_plan_identity=plan_identity, verified_part_count=part_count,
                  package_status={"status": "not_implemented"},
                  archive_status={"status": "not_implemented",
                                  "selection": record.get("storage_preflight", {}).get("archive")})
    if not _audio_only and frontier == "segments_exported" and record.get("manifest_generation") is not None:
        from .manifests import verify_stage
        pointer = record["manifest_generation"]
        result["active_stage"] = "manifest_generation"
        try:
            _require(isinstance(pointer, dict) and pointer.get("status") in
                     ("manifest_pending", "manifest_succeeded", "manifest_failed"), "Invalid manifest status")
            _require(pointer["status"] != "manifest_failed", "Manifest generation failed")
            if pointer["status"] == "manifest_succeeded":
                registry.update(verify_stage(directory, record, result))
                result.update(current_state="manifested", last_successful_state="manifested", active_stage=None)
        except (ValueError, OSError, KeyError, TypeError, AttributeError):
            result.update(current_state="failed", failed_stage="manifest_generation",
                          error_code="invalid_manifest_evidence", error_message="Manifest set is stale, incomplete or invalid.",
                          retryable=True)
    if not _audio_only and not _documents_only and result['last_successful_state'] == 'manifested':
        from .packages import project_packages
        project_packages(directory, record, result, packages_only=_packages_only)
    return result


def prepare_session(directory, record):
    """Called only by OwnedDirectory.atomic_json for canonical import records."""
    _validate(record, directory.path.name)
    try:
        previous = _read(directory)
    except FileNotFoundError:
        previous = None
    if previous is not None:
        _validate(previous, directory.path.name)
        _require(previous["created_at"] == record.get("created_at"), "Session creation time is immutable")
        if previous["audio"].get("sha256") is not None:
            _require(all(previous["audio"].get(k) == record["audio"].get(k) for k in IDENTITY_KEYS),
                     "Original audio identity is immutable after import")
            _require(record["state"] == "imported", "Legacy imported state is immutable")
    result = project_session(directory, record)
    result["updated_at"] = datetime.now(timezone.utc).isoformat()
    return result


def validate_transition(record, requested):
    """No setter can claim a milestone beyond the verified evidence projection."""
    _require(requested in STATES, "Unknown processing state")
    _require(requested == record.get("current_state"), "Transition requires current verified stage evidence")


def session_status(config, session_id):
    """Read-only technical view, including legacy imports and interrupted imports."""
    from .inspection import _existing_child, _inspection_lock
    _require(isinstance(session_id, str) and UUID.fullmatch(session_id), "Invalid session ID")
    _require(config.data_root.is_dir(), "Session data root unavailable")
    with ExitStack() as stack:
        root = stack.enter_context(OwnedDirectory.root(config.data_root))
        sessions = _existing_child(stack, root, "sessions")
        directory = _existing_child(stack, sessions, session_id)
        stack.enter_context(_inspection_lock(directory))
        record = _read(directory)
        view = project_session(directory, record)
    warnings = list(record.get("warnings", [])) + view["progress_warnings"]
    for name in ("inspection", "normalization"):
        warnings.extend(_object(record.get(name)).get("warnings", []))
    if STATES.index(view["last_successful_state"]) >= STATES.index("normalized_or_skipped"):
        # Preserve the import record but suppress its fulfilled prerequisite in
        # the technical view after full decoding has actually been verified.
        warnings = [w for w in warnings if w != "media_eligibility_pending"]
    from .recovery import _decision
    return {"session_id": session_id, "recovery": _decision(view), "stored_schema_version": record["schema_version"],
            "state_model_version": STATE_MODEL_VERSION, "legacy_import_state": record["state"],
            "current_state": view["current_state"], "last_successful_state": view["last_successful_state"],
            "active_stage": view["active_stage"], "audio": record["audio"],
            "audio_summary": _object(record.get("inspection")).get("media"),
            "normalization": {k: _object(record.get("normalization")).get(k) for k in
                              ("status", "mode_requested", "decision", "gain_db", "output_source", "normalization_applied")},
            "segmentation": record.get("segmentation"), "part_count": view["verified_part_count"],
            "artifacts": view["artifact_registry"], "visual_count": record["visual_count"],
            "package_status": view["package_status"], "archive_status": view["archive_status"],
            "errors": [] if view["error_code"] is None else [{"stage": view["failed_stage"],
                       "code": view["error_code"], "message": view["error_message"], "retryable": view["retryable"]}],
            "warnings": list(dict.fromkeys(warnings))}
