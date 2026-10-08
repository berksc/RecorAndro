"""One-audio immutable import; no probing or processing orchestration."""

from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import stat
import uuid

from .storage import OwnedDirectory, StorageError, archive_selection, preflight, safe_leaf, _is_redirect

AUDIO_SUFFIXES = {".m4a", ".mp3", ".wav", ".aac"}
CHUNK_BYTES = 1024 * 1024


class ImportFailure(ValueError):
    def __init__(self, message, record=None):
        super().__init__(message)
        self.record = record


class PreflightDenied(ImportFailure):
    def __init__(self, report):
        self.preflight = report
        super().__init__(f"Insufficient storage: required {report['estimated_required_bytes']} bytes; "
                         f"free {report['free_bytes']} bytes. No original copied; no session created.")


def _fingerprint(info):
    # Windows Python 3.12 path-stat and fd-stat can disagree on ctime semantics.
    # POSIX ctime is a change timestamp; identity, mtime and re-hashing work on both.
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns if os.name == "posix" else None)


def hash_stream(stream):
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(CHUNK_BYTES):
        digest.update(chunk)
        size += len(chunk)
    return size, digest.hexdigest()


def copy_stream(source, output):
    digest = hashlib.sha256()
    size = 0
    while chunk := source.read(CHUNK_BYTES):
        output.write(chunk)
        digest.update(chunk)
        size += len(chunk)
    return size, digest.hexdigest()


def _source(path):
    info = path.lstat()
    if _is_redirect(info) or not stat.S_ISREG(info.st_mode):
        raise ImportFailure("Source must be a regular non-symlink file")
    if path.suffix.lower() not in AUDIO_SUFFIXES:
        raise ImportFailure("Supported audio suffixes: .m4a, .mp3, .wav, .aac (case insensitive)")
    if info.st_size == 0:
        raise ImportFailure("Empty audio source refused")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags)
    opened = os.fstat(fd)
    if not stat.S_ISREG(opened.st_mode) or _fingerprint(opened) != _fingerprint(info):
        os.close(fd)
        raise ImportFailure("Source changed while opening")
    return os.fdopen(fd, "rb"), info


def import_audio(config, path, *, profile="lecture", provision_seconds,
                 archive="profile", title=None, course=None):
    if not isinstance(profile, str) or not profile or len(profile) > 64 or not all(
            c.isascii() and (c.isalnum() or c in "_-") for c in profile):
        raise ImportFailure("Profile must be 1..64 ASCII letters, digits, underscores or hyphens")
    for name, value in (("title", title), ("course", course)):
        if value is not None and (not isinstance(value, str) or len(value) > 1024):
            raise ImportFailure(f"{name} must be text of at most 1024 characters")
    selection = archive_selection(profile, archive, config.profile_archives)
    # Validate provisioning input before source/storage mutation.
    preflight(1, provision_seconds, 0, selection)
    source_path = Path(path).expanduser().absolute()
    record = None
    with ExitStack() as stack:
        source, initial = _source(source_path)
        stack.enter_context(source)
        root = stack.enter_context(OwnedDirectory.root(config.data_root))
        report = preflight(initial.st_size, provision_seconds, root.free_bytes(), selection)
        if report["decision"] == "deny":
            raise PreflightDenied(report)
        sessions = stack.enter_context(root.child("sessions"))
        for attempt in range(10):
            session_id = uuid.uuid4().hex
            try:
                directory = stack.enter_context(sessions.child(session_id, exclusive=True))
                break
            except FileExistsError:
                continue
        else:
            raise ImportFailure("Unable to allocate a unique session directory")
        record = {"schema_version": 1, "session_id": session_id,
                  "created_at": datetime.now(timezone.utc).isoformat(), "profile": profile,
                  "title": title, "course": course, "state": "importing", "visual_count": 0,
                  "audio": {"original_filename": source_path.name, "source_bytes": initial.st_size,
                            "imported_filename": None, "managed_path": None,
                            "size_bytes": None, "sha256": None},
                  "errors": [], "warnings": ["media_eligibility_pending", "storage_estimate_unverified"],
                  "storage_preflight": report, "media_eligibility": "not_inspected"}
        if selection["resolved"] == "unresolved":
            record["warnings"].append("full_archive_profile_default_unresolved")
        temp = None
        temporary_name = f"import-{uuid.uuid4().hex}.partial"
        try:
            directory.atomic_json(record)
            originals = stack.enter_context(directory.child("originals", exclusive=True))
            audio = stack.enter_context(originals.child("audio", exclusive=True))
            stack.enter_context(directory.child("generated", exclusive=True))
            temp = stack.enter_context(directory.child("temp", exclusive=True))
            fd = temp.open(temporary_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            with os.fdopen(fd, "wb") as output:
                copied_size, copied_hash = copy_stream(source, output)
                output.flush()
                os.fsync(output.fileno())
            source.seek(0)
            source_size, source_hash = hash_stream(source)
            if (_fingerprint(os.fstat(source.fileno())) != _fingerprint(initial) or
                    _fingerprint(source_path.lstat()) != _fingerprint(initial)):
                raise ImportFailure("Source changed during import")
            fd = temp.open(temporary_name, os.O_RDONLY)
            with os.fdopen(fd, "rb") as imported:
                imported_size, imported_hash = hash_stream(imported)
                if os.fstat(imported.fileno()).st_size != initial.st_size:
                    raise ImportFailure("Imported size mismatch")
            if not copied_size == source_size == imported_size == initial.st_size:
                raise ImportFailure("Source/import size mismatch")
            if not copied_hash == source_hash == imported_hash:
                raise ImportFailure("Source/import SHA-256 mismatch")
            if (_fingerprint(os.fstat(source.fileno())) != _fingerprint(initial) or
                    _fingerprint(source_path.lstat()) != _fingerprint(initial)):
                raise ImportFailure("Source changed before publication")
            stored_name = safe_leaf(source_path.name)
            # Permissions reinforce immutability; hashes remain authoritative.
            fd = temp.open(temporary_name, os.O_RDONLY)
            try:
                if os.name == "posix":
                    os.fchmod(fd, 0o400)
            finally:
                os.close(fd)
            temp.publish(temporary_name, stored_name, audio)
            record["audio"].update(imported_filename=stored_name,
                                   managed_path=f"originals/audio/{stored_name}",
                                   size_bytes=imported_size, sha256=imported_hash)
            record["state"] = "imported"
            directory.atomic_json(record)
            return record
        except (Exception, KeyboardInterrupt) as exc:
            # An unpublished partial is removed only from this session's temp dir.
            # If publication succeeded but metadata failed, the verified orphan
            # is retained; failed metadata must never reference it as valid.
            record["state"] = "failed"
            record["audio"].update(imported_filename=None, managed_path=None, size_bytes=None, sha256=None)
            record["errors"].append({"code": "audio_import_failed", "message": str(exc) or type(exc).__name__})
            if temp is not None:
                try:
                    temp.unlink(temporary_name)
                except FileNotFoundError:
                    pass
                except (OSError, StorageError) as cleanup_error:
                    record["warnings"].append(f"temporary_cleanup_failed: {cleanup_error}")
            try:
                directory.atomic_json(record)
            except (OSError, StorageError) as metadata_error:
                raise ImportFailure(f"Import failed: {exc}; failed-state persistence unavailable: {metadata_error}; "
                                    "existing importing state is incomplete", record) from exc
            raise ImportFailure(f"Import failed in session {session_id}: {exc}", record) from exc
