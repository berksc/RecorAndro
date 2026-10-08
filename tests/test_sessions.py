import contextlib
import ctypes
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch

from recorandro.cli import main
from recorandro.config import Config, ConfigError, load_config
from recorandro.sessions import ImportFailure, PreflightDenied, import_audio, copy_stream
from recorandro.storage import OwnedDirectory, StorageError, archive_selection, preflight, safe_leaf, _native_renameat2

FREE = 10 * 1024 ** 3


@contextlib.contextmanager
def native_publication_transport():
    """Real native branch on POSIX; mocked syscall with real Windows moves on host.

    Windows os.rename refuses replacement atomically; this is only test transport,
    never a production Linux/Android fallback or native syscall validation.
    """
    if os.name == "posix":
        with patch.object(OwnedDirectory, "_publish_original", OwnedDirectory._publish_noreplace):
            yield
    else:
        move = os.rename
        def dispatch(directory, temporary, final, destination, pending):
            def native_move(source_fd, source_leaf, destination_fd, destination_leaf):
                move(directory.path / source_leaf, destination.path / destination_leaf)
            with patch("recorandro.storage._native_renameat2", side_effect=native_move):
                directory._publish_noreplace(temporary, final, destination, pending)
        with patch.object(OwnedDirectory, "_publish_original", dispatch):
            yield


class PreflightTests(unittest.TestCase):
    def test_formula_boundary_and_components(self):
        # Six-second provision, 3 source bytes: hand-calculated independent values.
        archive = archive_selection("lecture", "not_requested")
        result = preflight(3, 6, FREE, archive)
        self.assertEqual(result["part_count_allowance"], 2)
        self.assertEqual(result["components"], {
            "immutable_original": 3, "possible_normalized": 245536,
            "generated_audio": 611072, "package_zip_duplication": 611072,
            "temporary_work": 611072, "optional_full_archive": 0})
        required = 270514211
        self.assertEqual(result["estimated_required_bytes"], required)
        self.assertEqual(preflight(3, 6, required, archive)["decision"], "allow")
        self.assertEqual(preflight(3, 6, required - 1, archive)["decision"], "deny")

    def test_archive_requested_unresolved_and_profile_resolution(self):
        unresolved = archive_selection("lecture")
        self.assertEqual(unresolved["resolved"], "unresolved")
        requested = archive_selection("lecture", "requested")
        off = archive_selection("lecture", "not_requested")
        self.assertEqual(preflight(100, 3600, FREE, unresolved)["estimated_required_bytes"],
                         preflight(100, 3600, FREE, requested)["estimated_required_bytes"])
        self.assertGreater(preflight(100, 3600, FREE, requested)["estimated_required_bytes"],
                           preflight(100, 3600, FREE, off)["estimated_required_bytes"])
        self.assertEqual(archive_selection("lecture", defaults={"lecture": False})["resolved"], "not_requested")
        self.assertEqual(archive_selection("lecture", defaults={"lecture": True})["provenance"], "local_profile_setting")
        self.assertEqual(archive_selection("lecture", "requested", {"lecture": False})["resolved"], "requested")

    def test_large_source_copy_and_percentage_headroom(self):
        report = preflight(2 * 1024 ** 3, 1, FREE, archive_selection("lecture", "not_requested"))
        self.assertEqual(report["components"]["generated_audio"], 2 * 1024 ** 3)
        self.assertGreater(report["headroom_policy"]["reserved_bytes"], 256 * 1024 ** 2)
        self.assertFalse(report["provisioning_bound"]["verified_media_duration"])

    def test_invalid_bounds(self):
        for bound in (None, 0, -1, 604801, 1.5, float("inf"), True):
            with self.subTest(bound=bound), self.assertRaises(StorageError):
                preflight(1, bound, FREE, archive_selection("lecture"))
        for size, free in ((0, FREE), (1, -1), (True, FREE), (1, False)):
            with self.subTest(size=size, free=free), self.assertRaises(StorageError):
                preflight(size, 1, free, archive_selection("lecture"))


class NativePublicationTests(unittest.TestCase):
    def test_no_os_link_uses_typed_directory_relative_libc_call(self):
        native = Mock(return_value=0)
        library = Mock(renameat2=native)
        with patch.dict(os.__dict__), patch("ctypes.CDLL", return_value=library) as load, \
             patch("os.rename", side_effect=AssertionError("No rename fallback")):
            os.__dict__.pop("link", None)
            self.assertFalse(hasattr(os, "link"))
            _native_renameat2(11, "İstanbul 🎧.partial", 12, "ders.wav")
        load.assert_called_once_with(None, use_errno=True)
        native.assert_called_once_with(11, os.fsencode("İstanbul 🎧.partial"), 12, b"ders.wav", 1)
        self.assertEqual(native.argtypes, [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                                          ctypes.c_char_p, ctypes.c_uint])
        self.assertIs(native.restype, ctypes.c_int)

    def test_collision_and_native_errors_fail_without_fallback(self):
        for code in (errno.EEXIST, errno.EINVAL, errno.EACCES, errno.EPERM, errno.EXDEV, errno.ENOSYS, errno.EOPNOTSUPP):
            def failed(*args):
                ctypes.set_errno(code)
                return -1
            library = Mock(renameat2=Mock(side_effect=failed))
            with self.subTest(errno=code), patch.dict(os.__dict__), \
                 patch("ctypes.CDLL", return_value=library), \
                 patch("os.rename", side_effect=AssertionError("No rename fallback")), \
                 self.assertRaises(OSError) as error:
                os.__dict__.pop("link", None)
                _native_renameat2(11, "verified.partial", 12, "audio.wav")
            self.assertEqual(error.exception.errno, code)
            if code == errno.EEXIST:
                self.assertIsInstance(error.exception, FileExistsError)

    def test_unavailable_ctypes_libc_or_symbol_fails_closed(self):
        for load in (patch("ctypes.CDLL", side_effect=OSError("libc unavailable")),
                     patch("ctypes.CDLL", return_value=object()),
                     patch.dict("sys.modules", {"ctypes": None})):
            with load, patch("os.rename", side_effect=AssertionError("No rename fallback")), \
                 self.assertRaises(StorageError):
                _native_renameat2(11, "verified.partial", 12, "audio.wav")

    def test_unconfined_descriptors_or_leaf_paths_rejected_before_native_call(self):
        for args in ((-100, "owned.partial", 12, "audio.wav"),
                     (None, "owned.partial", 12, "audio.wav"),
                     (11, "../escape", 12, "audio.wav"),
                     (11, "owned.partial", 12, "/outside")):
            with self.subTest(args=args), patch("ctypes.CDLL") as load, self.assertRaises(StorageError):
                _native_renameat2(*args)
            load.assert_not_called()

    def test_native_rename_sync_order_without_temporary_unlink(self):
        from types import SimpleNamespace
        inode = SimpleNamespace(st_mode=stat.S_IFREG | 0o400, st_dev=1, st_ino=99, st_size=123)
        for sync_failure in (False, True):
            events = []
            def renamed(*args):
                events.append("renameat2")
                return 0
            def sync_destination():
                events.append("sync_destination")
                if sync_failure:
                    raise OSError("simulated sync failure")
            temporary = Mock(fd=11, unlink=Mock(side_effect=AssertionError("Moved temp must not be unlinked")),
                             sync=Mock(side_effect=lambda: events.append("sync_temporary_directory")))
            destination = Mock(fd=12, info=Mock(return_value=inode), sync=Mock(side_effect=sync_destination))
            library = Mock(renameat2=Mock(side_effect=renamed))
            expected_error = self.assertRaises(OSError) if sync_failure else contextlib.nullcontext()
            with self.subTest(sync_failure=sync_failure), patch.dict(os.__dict__), \
                 patch("ctypes.CDLL", return_value=library), expected_error:
                os.__dict__.pop("link", None)
                OwnedDirectory._publish_noreplace(temporary, "verified.partial", "audio.wav", destination, inode)
            self.assertEqual(events, ["renameat2", "sync_destination"] +
                             ([] if sync_failure else ["sync_temporary_directory"]))
            temporary.unlink.assert_not_called()


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.base = Path(self.folder.name)
        self.config = Config(self.base / "managed")
        self.source = self.base / "source.wav"
        # Admission is suffix-only: deliberately not a media decode fixture.
        self.contents = bytes(range(256)) * 20
        self.source.write_bytes(self.contents)
        self.free = patch.object(OwnedDirectory, "free_bytes", return_value=FREE)
        self.free.start()
        self.addCleanup(self.free.stop)
        # POSIX imported originals are read-only; cleanup only this test's files.
        self.addCleanup(self.make_owned_writable)

    def make_owned_writable(self):
        for path in self.config.data_root.glob("sessions/*/originals/audio/*"):
            if path.is_file() and not path.is_symlink():
                path.chmod(0o600)

    def ingest(self, source=None, **kwargs):
        return import_audio(self.config, source or self.source, provision_seconds=6, **kwargs)

    def metadata(self):
        return [json.loads(path.read_text(encoding="utf-8"))
                for path in self.config.data_root.glob("sessions/*/session.json")]

    def test_normal_import_immutable_source_zero_photos_and_independent_copy(self):
        before = self.source.stat()
        result = self.ingest(title="Ders", course="Fizik", archive="not_requested")
        after = self.source.stat()
        self.assertEqual((before.st_size, before.st_mtime_ns), (after.st_size, after.st_mtime_ns))
        self.assertEqual(self.source.read_bytes(), self.contents)
        managed = self.config.data_root / "sessions" / result["session_id"] / result["audio"]["managed_path"]
        self.assertEqual(managed.read_bytes(), self.contents)
        self.assertNotEqual(managed.stat().st_ino, self.source.stat().st_ino)
        self.assertEqual(result["audio"]["sha256"], hashlib.sha256(self.contents).hexdigest())
        self.assertEqual(result["state"], "imported")
        self.assertEqual(result["visual_count"], 0)
        self.assertEqual(result["media_eligibility"], "not_inspected")
        self.assertEqual(self.metadata(), [result])
        self.assertEqual(result["title"], "Ders")
        self.source.unlink()
        self.assertEqual(managed.read_bytes(), self.contents)
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(managed.stat().st_mode), 0o400)

    def test_insufficient_storage_never_copies_or_allocates_session(self):
        with patch.object(OwnedDirectory, "free_bytes", return_value=0), \
             patch("recorandro.sessions.copy_stream") as copier, \
             self.assertRaises(PreflightDenied) as error:
            self.ingest()
        copier.assert_not_called()
        self.assertIn("required", str(error.exception))
        self.assertIn("free 0 bytes", str(error.exception))
        self.assertEqual(error.exception.preflight["decision"], "deny")
        self.assertFalse((self.config.data_root / "sessions").exists())

    def test_empty_missing_directory_unsupported_and_unreadable_sources(self):
        empty = self.base / "empty.wav"
        empty.touch()
        other = self.base / "other.flac"
        other.write_bytes(b"x")
        for path in (empty, self.base / "missing.wav", self.base, other):
            with self.subTest(path=path), self.assertRaises((ImportFailure, OSError)):
                self.ingest(path)
        real_open = os.open
        def denied(path, *args, **kwargs):
            if Path(path) == self.source:
                raise PermissionError("unreadable fixture")
            return real_open(path, *args, **kwargs)
        with patch("recorandro.sessions.os.open", side_effect=denied), self.assertRaises(PermissionError):
            self.ingest()
        self.assertFalse(self.config.data_root.exists())

    def test_unicode_and_long_stored_names(self):
        for name in ("İstanbul_öğrenci_şğı.M4A", "Ders 🎧📚.mp3", "ğ" * 110 + ".aac"):
            path = self.base / name
            path.write_bytes(self.contents)
            result = self.ingest(path)
            self.assertEqual(result["audio"]["original_filename"], name)
            stored = result["audio"]["imported_filename"]
            self.assertLessEqual(len(stored.encode("utf-8")), 160)
            self.assertEqual(Path(stored).suffix, Path(name).suffix)
            self.assertEqual(result["audio"]["sha256"], hashlib.sha256(self.contents).hexdigest())

    def test_identical_reimport_creates_separate_sessions(self):
        first, second = self.ingest(), self.ingest()
        self.assertNotEqual(first["session_id"], second["session_id"])
        self.assertEqual(first["audio"]["sha256"], second["audio"]["sha256"])
        self.assertEqual(len(self.metadata()), 2)

    def test_interruption_failure_not_complete(self):
        def interrupted(source, output):
            output.write(source.read(128))
            raise KeyboardInterrupt("simulated interruption")
        with patch("recorandro.sessions.copy_stream", side_effect=interrupted), \
             self.assertRaises(ImportFailure):
            self.ingest()
        self.assert_failed_session()

    def assert_failed_session(self):
        records = self.metadata()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["state"], "failed")
        self.assertIsNone(records[0]["audio"]["managed_path"])
        self.assertIsNone(records[0]["audio"]["sha256"])
        self.assertTrue(records[0]["errors"])
        directory = self.config.data_root / "sessions" / records[0]["session_id"]
        self.assertEqual(list((directory / "temp").iterdir()), [])
        self.assertEqual(list((directory / "originals/audio").iterdir()), [])
        self.assertEqual(self.source.read_bytes(), self.contents)

    def test_hash_mismatch_failure(self):
        def corrupt(source, output):
            size, digest = copy_stream(source, output)
            output.seek(0)
            output.write(b"corrupt")
            return size, digest
        with patch("recorandro.sessions.copy_stream", side_effect=corrupt), \
             self.assertRaises(ImportFailure) as error:
            self.ingest()
        self.assertIn("SHA-256 mismatch", str(error.exception))
        self.assert_failed_session()

    def test_same_size_source_change_during_copy(self):
        def changing(source, output):
            result = copy_stream(source, output)
            self.source.write_bytes(b"x" * len(self.contents))
            return result
        with patch("recorandro.sessions.copy_stream", side_effect=changing), self.assertRaises(ImportFailure):
            self.ingest()
        record = self.metadata()[0]
        self.assertEqual(record["state"], "failed")
        self.assertIn("Source changed", record["errors"][0]["message"])
        self.assertIsNone(record["audio"]["managed_path"])

    def test_failed_final_metadata_never_records_imported(self):
        original = OwnedDirectory.atomic_json
        def fail_imported(directory, record):
            if record["state"] == "imported":
                raise OSError("simulated final metadata failure")
            return original(directory, record)
        with patch.object(OwnedDirectory, "atomic_json", fail_imported), self.assertRaises(ImportFailure):
            self.ingest()
        result = self.metadata()[0]
        self.assertEqual(result["state"], "failed")
        self.assertIsNone(result["audio"]["managed_path"])
        self.assertEqual(len(list(self.config.data_root.glob("sessions/*/originals/audio/*"))), 1)

    def test_collision_does_not_overwrite_existing_session(self):
        first = self.ingest()
        import uuid
        sequence = [uuid.UUID(first["session_id"])] + [uuid.uuid4() for _ in range(8)]
        with patch("recorandro.sessions.uuid.uuid4", side_effect=sequence):
            second = self.ingest()
        self.assertNotEqual(first["session_id"], second["session_id"])
        self.assertIn(first, self.metadata())

    def test_import_cli_does_not_invoke_tools(self):
        with patch("recorandro.cli.load_config", return_value=self.config), \
             patch("subprocess.run", side_effect=AssertionError("No tools allowed")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            status = main(["import-audio", str(self.source), "--profile", "lecture", "--provision-seconds", "6"])
        self.assertEqual(status, 0)
        self.assertTrue(json.loads(output.getvalue())["ok"])
        with patch("recorandro.cli.load_config", return_value=self.config), \
             patch.object(OwnedDirectory, "free_bytes", return_value=0), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["import-audio", str(self.source), "--provision-seconds", "6"]), 1)
        self.assertIn("storage_preflight", json.loads(output.getvalue()))

    def test_publication_race_never_overwrites_or_completes_import(self):
        # Execute native dispatch and, on Windows, the Linux rename sequence via
        # a test-only Windows no-replace transport. Actual Linux/Android exercises dir_fd natively.
        for mode in ("native", "rename_sequence"):
            with self.subTest(mode=mode):
                self.config = Config(self.base / mode)
                original_info = OwnedDirectory.info
                injected = []
                def racing_info(directory, name):
                    try:
                        return original_info(directory, name)
                    except FileNotFoundError:
                        if name == self.source.name and directory.path.name == "audio" and not injected:
                            # The existence check observed absence; a competitor
                            # creates the final leaf before publication executes.
                            final = directory.path / name
                            final.write_bytes(b"competing original; must survive")
                            injected.append(final)
                        raise
                dispatch = (native_publication_transport()
                            if mode == "rename_sequence" else contextlib.nullcontext())
                with patch.object(OwnedDirectory, "info", racing_info), dispatch, \
                     self.assertRaises(ImportFailure):
                    self.ingest()
                self.assertEqual(len(injected), 1)
                self.assertEqual(injected[0].read_bytes(), b"competing original; must survive")
                result = self.metadata()[0]
                self.assertEqual(result["state"], "failed")
                self.assertIsNone(result["audio"]["managed_path"])
                self.assertIsNone(result["audio"]["sha256"])
                self.assertTrue(result["errors"])
                self.assertEqual(list(injected[0].parents[2].joinpath("temp").iterdir()), [])
                self.assertEqual(self.source.read_bytes(), self.contents)

    def test_renamed_temporary_absence_is_success_not_cleanup_failure(self):
        original_unlink = OwnedDirectory.unlink
        def reject_partial_unlink(directory, name):
            if name.endswith(".partial"):
                raise AssertionError("Successfully moved temp must not be unlinked")
            return original_unlink(directory, name)
        with native_publication_transport(), patch.object(OwnedDirectory, "unlink", reject_partial_unlink):
            result = self.ingest()
        self.assertEqual(result["state"], "imported")
        self.assertEqual(list(self.config.data_root.glob("sessions/*/temp/*.partial")), [])
        final = next(self.config.data_root.glob("sessions/*/originals/audio/*"))
        self.assertEqual(hashlib.sha256(final.read_bytes()).hexdigest(), result["audio"]["sha256"])

    def test_post_rename_sync_failure_preserves_orphan_and_failed_metadata(self):
        original_sync = OwnedDirectory.sync
        def fail_after_move(directory):
            if directory.path.name == "audio":
                raise OSError("simulated destination sync failure")
            return original_sync(directory)
        with native_publication_transport(), patch.object(OwnedDirectory, "sync", fail_after_move), \
             self.assertRaises(ImportFailure):
            self.ingest()
        result = self.metadata()[0]
        self.assertEqual(result["state"], "failed")
        self.assertIsNone(result["audio"]["managed_path"])
        final = next(self.config.data_root.glob("sessions/*/originals/audio/*"))
        self.assertEqual(final.read_bytes(), self.contents)
        self.assertEqual(list(self.config.data_root.glob("sessions/*/temp/*.partial")), [])

    def test_post_rename_metadata_failure_preserves_unreferenced_orphan(self):
        original_json = OwnedDirectory.atomic_json
        def fail_imported(directory, record):
            if record["state"] == "imported":
                raise OSError("simulated final metadata failure")
            return original_json(directory, record)
        with native_publication_transport(), patch.object(OwnedDirectory, "atomic_json", fail_imported), \
             self.assertRaises(ImportFailure):
            self.ingest()
        result = self.metadata()[0]
        self.assertEqual(result["state"], "failed")
        self.assertIsNone(result["audio"]["managed_path"])
        self.assertIsNone(result["audio"]["sha256"])
        final = next(self.config.data_root.glob("sessions/*/originals/audio/*"))
        self.assertEqual(final.read_bytes(), self.contents)
        self.assertEqual(list(self.config.data_root.glob("sessions/*/temp/*.partial")), [])

    def test_unavailable_native_publication_cannot_complete_session(self):
        def native_dispatch(directory, temporary, final, destination, pending):
            # Fake descriptor values only reach the mocked missing-symbol load.
            _native_renameat2(11, temporary, 12, final)
        with patch.object(OwnedDirectory, "_publish_original", native_dispatch), \
             patch("ctypes.CDLL", return_value=object()), patch.dict(os.__dict__), \
             self.assertRaises(ImportFailure):
            os.__dict__.pop("link", None)
            self.ingest()
        self.assert_failed_session()


class FilesystemTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.base = Path(self.folder.name)

    def test_safe_leaf_traversal_absolute_emoji_turkish_and_extreme_names(self):
        for name in ("../../escape.wav", r"C:\escape\file.mp3", "/tmp/escape.aac",
                     "CON.wav", "...", "ğ" * 500 + ".m4a", "İ 🎧.wav"):
            stored = safe_leaf(name)
            self.assertFalse(any(c in stored for c in '/\\:'))
            self.assertNotIn(stored, ("", ".", ".."))
            self.assertLessEqual(len(stored.encode("utf-8")), 160)

    def test_atomic_metadata_old_or_new_not_partial(self):
        with OwnedDirectory.root(self.base / "owned") as directory:
            directory.atomic_json({"state": "importing"})
            replace = os.replace
            snapshots = []
            def observed(src, dst, **kwargs):
                snapshots.append(json.loads((directory.path / "session.json").read_text()))
                temporary = directory.path / Path(src).name
                self.assertEqual(json.loads(temporary.read_text()), {"state": "failed"})
                return replace(src, dst, **kwargs)
            with patch("recorandro.storage.os.replace", side_effect=observed):
                directory.atomic_json({"state": "failed"})
            self.assertEqual(snapshots, [{"state": "importing"}])
            self.assertEqual(json.loads((directory.path / "session.json").read_text()), {"state": "failed"})
            with patch("recorandro.storage.os.replace", side_effect=OSError("interrupted publication")), \
                 self.assertRaises(OSError):
                directory.atomic_json({"state": "imported"})
            self.assertEqual(json.loads((directory.path / "session.json").read_text()), {"state": "failed"})
            self.assertEqual([p.name for p in directory.path.iterdir()], ["session.json"])

    def test_managed_path_injection_refused(self):
        with OwnedDirectory.root(self.base / "owned") as directory:
            for name in ("../outside", "/tmp/outside", r"..\outside", "C:outside"):
                with self.subTest(name=name), self.assertRaises(StorageError):
                    directory.child(name)

    def symlink(self, target, link, directory=False):
        try:
            os.symlink(target, link, target_is_directory=directory)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Host cannot create symlink: {exc}")

    def test_managed_symlink_redirection_refused(self):
        outside = self.base / "outside"
        outside.mkdir()
        root = self.base / "owned"
        root.mkdir()
        self.symlink(outside, root / "sessions", True)
        with OwnedDirectory.root(root) as directory, self.assertRaises((StorageError, OSError)):
            directory.child("sessions")
        self.assertEqual(list(outside.iterdir()), [])

    def test_config_does_not_resolve_away_root_symlink(self):
        outside = self.base / "outside"
        outside.mkdir()
        alias = self.base / "alias"
        self.symlink(outside, alias, True)
        config = load_config(env={"RECORANDRO_DATA_ROOT": str(alias)})
        self.assertEqual(config.data_root, alias)
        with self.assertRaises((StorageError, OSError)):
            OwnedDirectory.root(config.data_root)

    def test_source_symlink_refused(self):
        source = self.base / "source.wav"
        source.write_bytes(b"fixture")
        alias = self.base / "alias.wav"
        self.symlink(source, alias)
        with self.assertRaises(ImportFailure):
            import_audio(Config(self.base / "owned"), alias, provision_seconds=6)

    def test_metadata_symlink_refused_without_touching_target(self):
        outside = self.base / "outside.json"
        outside.write_text("untouched")
        with OwnedDirectory.root(self.base / "owned") as directory:
            self.symlink(outside, directory.path / "session.json")
            with self.assertRaises(StorageError):
                directory.atomic_json({"state": "imported"})
        self.assertEqual(outside.read_text(), "untouched")

    def test_publication_refuses_symlink_or_existing_original(self):
        outside = self.base / "outside.wav"
        outside.write_bytes(b"untouched")
        with OwnedDirectory.root(self.base / "owned") as directory:
            self.symlink(outside, directory.path / "pending.partial")
            with self.assertRaises(StorageError):
                directory.publish("pending.partial", "audio.wav")
            (directory.path / "another.partial").write_bytes(b"new")
            (directory.path / "audio.wav").write_bytes(b"previous")
            with self.assertRaises(StorageError):
                directory.publish("another.partial", "audio.wav")
            self.assertEqual((directory.path / "audio.wav").read_bytes(), b"previous")
        self.assertEqual(outside.read_bytes(), b"untouched")

    def test_rename_publication_preserves_verified_inode_and_attributes(self):
        with OwnedDirectory.root(self.base / "owned") as directory:
            with directory.child("temp") as temporary, directory.child("audio") as destination:
                source = temporary.path / "verified.partial"
                source.write_bytes(b"verified fixture bytes")
                before = source.stat()
                expected_hash = hashlib.sha256(source.read_bytes()).hexdigest()
                with native_publication_transport():
                    temporary.publish("verified.partial", "audio.wav", destination)
                final = destination.path / "audio.wav"
                after = final.stat()
                self.assertEqual((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
                                  stat.S_IMODE(after.st_mode)),
                                 (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                                  stat.S_IMODE(before.st_mode)))
                self.assertEqual(hashlib.sha256(final.read_bytes()).hexdigest(), expected_hash)
                self.assertFalse(source.exists())

    def test_local_profile_config_validation(self):
        path = self.base / "config.json"
        path.write_text('{"data_root":"owned","profile_archives":{"lecture":null,"custom":false}}')
        self.assertIsNone(load_config(str(path), {}).profile_archives["lecture"])
        for profiles in ({"lecture": 1}, {"../escape": False}, [], {"lecture": "off"}):
            path.write_text(json.dumps({"data_root": "owned", "profile_archives": profiles}))
            with self.assertRaises(ConfigError):
                load_config(str(path), {})


if __name__ == "__main__":
    unittest.main()
