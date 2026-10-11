"""Actual ZIP content, current revisions, set publication and optional archive safety."""
import contextlib
import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
import subprocess
import sys
import time
import zipfile
from unittest.mock import patch

from recorandro.cli import main
from recorandro.manifests import generate_manifests
from recorandro.packages import (package_session, archive_session, PackageFailure, safe_member,
                                verify_zip, zip_info, storage_check, inline)
from recorandro.recovery import recover_session
from recorandro.session_state import session_status
from recorandro.storage import OwnedDirectory
from test_exports import ExportFixture
from test_normalization import make_wav


class PackageTests(ExportFixture):
    def setUp(self):
        super().setUp()
        self.exported = self.mocked_export()
        generate_manifests(self.config, self.sid)

    def package(self):
        with patch.object(OwnedDirectory, 'free_bytes', return_value=10**12):
            return package_session(self.config, self.sid)

    def archive(self, decision='on'):
        with patch.object(OwnedDirectory, 'free_bytes', return_value=10**12):
            return archive_session(self.config, self.sid, decision=decision)

    def journal(self, kind='package_generation'):
        return json.loads((self.directory / self.record()[kind]['record_path']).read_bytes())

    def outputs(self, kind='package_generation'):
        return {n: (self.directory / e['relative_path']).read_bytes() for n, e in self.journal(kind)['files'].items()}

    def protected_bytes(self):
        record = self.record()
        result = {'original': self.original.read_bytes()}
        for key in ('normalization', 'segmentation', 'audio_export', 'manifest_generation'):
            pointer = record[key]
            path = pointer.get('record_path') or f"generated/normalization/{pointer['attempt_id']}/session.json"
            result[path] = (self.directory / path).read_bytes()
        for entry in session_status(self.config, self.sid)['artifacts'].values():
            if entry['status'] == 'verified' and entry['type'] not in ('zip_package', 'full_archive'):
                result[entry['relative_path']] = (self.directory / entry['relative_path']).read_bytes()
        return result

    def test_audio_only_multipart_exact_contents_registry_and_noop(self):
        before = self.protected_bytes()
        self.package()
        for name, blob in self.outputs().items():
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                audio = name[:-4] + '.m4a'
                self.assertEqual(archive.namelist(), ['manifest.json', 'manifest.md', audio])
                part = json.loads(archive.read('manifest.json'))
                self.assertEqual(hashlib.sha256(archive.read(audio)).hexdigest(), part['sha256'])
                self.assertIsNone(archive.testzip())
        view = session_status(self.config, self.sid)
        self.assertEqual(view['current_state'], 'packaged')
        self.assertEqual(view['archive_status']['status'], 'unresolved')
        entries = [e for e in view['artifacts'].values() if e['type'] == 'zip_package' and e['status'] == 'verified']
        self.assertEqual(len(entries), 3)
        self.assertTrue(all(e['regenerable'] and not e['protected'] for e in entries))
        metadata = (self.directory / 'session.json').read_bytes()
        self.assertTrue(self.package()['reused'])
        self.assertEqual(recover_session(self.config, self.sid)['performed_stages'], [])
        self.assertEqual((self.directory / 'session.json').read_bytes(), metadata)
        self.assertEqual(self.protected_bytes(), before)

    def test_single_part_package(self):
        self.configure_duration(30)
        self.make_plan('off')
        self.exported = self.mocked_export()
        generate_manifests(self.config, self.sid)
        self.package()
        self.assertEqual(list(self.outputs()), ['part_01.zip'])
        self.assertEqual(session_status(self.config, self.sid)['package_status']['required_count'], 1)

    def test_corrupt_or_missing_zip_selective_byte_identical_regeneration(self):
        self.package()
        before = self.outputs()
        for missing in (False, True):
            old = self.journal()
            path = self.directory / old['files']['part_02.zip']['relative_path']
            path.unlink() if missing else path.write_bytes(b'bad ZIP')
            view = session_status(self.config, self.sid)
            self.assertEqual(view['last_successful_state'], 'manifested')
            self.assertEqual(view['package_status']['verified_count'], 2)
            self.commands.clear()
            with patch.object(OwnedDirectory, 'free_bytes', return_value=10**12):
                result = recover_session(self.config, self.sid)
            self.assertEqual(result['performed_stages'], ['package_generation'])
            self.assertEqual(self.commands, [])
            self.assertEqual(self.outputs(), before)
            fresh = self.journal()
            for name in ('part_01.zip', 'part_03.zip'):
                self.assertEqual(fresh['files'][name]['relative_path'], old['files'][name]['relative_path'])

    def test_manifest_revision_change_rejects_old_packages(self):
        self.package()
        old = self.journal()
        record = self.record()
        record['title'] = 'Explicitly supplied'
        self.write_record(record)
        self.assertNotEqual(session_status(self.config, self.sid)['last_successful_state'], 'packaged')
        with self.assertRaises(PackageFailure):
            self.package()
        generate_manifests(self.config, self.sid)
        self.package()
        self.assertNotEqual(self.journal()['source_revision'], old['source_revision'])

    def test_partial_package_publication_not_complete_and_reuses_final(self):
        class Crash(BaseException):
            pass
        actual = OwnedDirectory.publish
        def die(folder, temporary, final, destination=None):
            actual(folder, temporary, final, destination)
            if final == 'part_01.zip':
                raise Crash()
        with patch.object(OwnedDirectory, 'publish', die), self.assertRaises(Crash):
            self.package()
        old = self.journal()
        self.assertEqual(session_status(self.config, self.sid)['current_state'], 'manifested')
        self.package()
        self.assertEqual(self.journal()['files']['part_01.zip']['relative_path'], old['files']['part_01.zip']['relative_path'])
        self.assertEqual(session_status(self.config, self.sid)['current_state'], 'packaged')

    def test_complete_publication_before_canonical_update_adopted(self):
        class Crash(BaseException):
            pass
        actual = OwnedDirectory.atomic_json
        def die(folder, record):
            if folder.path == self.directory and record.get('package_generation', {}).get('status') == 'succeeded':
                raise Crash()
            return actual(folder, record)
        with patch.object(OwnedDirectory, 'atomic_json', die), self.assertRaises(Crash):
            self.package()
        old = self.journal()
        view = session_status(self.config, self.sid)
        self.assertEqual(view['last_successful_state'], 'manifested')
        self.assertNotEqual(view['current_state'], 'packaged')
        self.package()
        self.assertEqual(self.journal()['attempt_id'], old['attempt_id'])

    def test_packaging_failure_retains_audio_and_manifest_frontier(self):
        before = self.protected_bytes()
        with patch('recorandro.packages.write_zip', side_effect=OSError('controlled disk failure')), self.assertRaises(PackageFailure):
            self.package()
        self.assertEqual(session_status(self.config, self.sid)['last_successful_state'], 'manifested')
        self.assertEqual(self.protected_bytes(), before)
        self.assertEqual(list(self.directory.glob('generated/package_generation/*/*.zip')), [])
        self.package()

    def test_optional_unresolved_and_explicit_off_never_generate(self):
        self.package()
        metadata = (self.directory / 'session.json').read_bytes()
        self.assertEqual(archive_session(self.config, self.sid)['status'], 'unresolved')
        self.assertEqual((self.directory / 'session.json').read_bytes(), metadata)
        self.assertEqual(self.archive('off')['status'], 'explicit_off')
        self.assertEqual(list(self.directory.glob('generated/full_archive/*/*.zip')), [])
        self.assertEqual(session_status(self.config, self.sid)['current_state'], 'packaged')

    def test_archive_actual_content_snapshot_compact_and_idempotent(self):
        self.package()
        before = self.protected_bytes()
        self.archive()
        blob = self.outputs('full_archive')['full_archive.zip']
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            names = archive.namelist()
            self.assertEqual(names, sorted(names))
            self.assertFalse(any(n.endswith('.zip') or '/temp/' in n for n in names))
            self.assertIn(self.record()['audio']['managed_path'], names)
            self.assertTrue(any(n.endswith('processing_report.md') for n in names))
            self.assertIsNone(archive.testzip())
            snapshot = json.loads(archive.read('session.json'))
            self.assertEqual(snapshot['current_state'], 'manifested')
            self.assertEqual(snapshot['archive_status']['status'], 'snapshot_before_archive')
            self.assertNotIn('full_archive', snapshot)
            self.assertNotIn('package_generation', snapshot)
            for name in names:
                if name != 'session.json':
                    self.assertEqual(archive.read(name), (self.directory / name).read_bytes())
            restored = self.base / 'restored' / 'sessions' / self.sid
            for name in names:
                safe_member(name)
                target = restored / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
            from recorandro.config import Config
            self.assertEqual(session_status(Config(self.base / 'restored'), self.sid)['last_successful_state'], 'manifested')
        view = session_status(self.config, self.sid)
        self.assertEqual(view['archive_status']['status'], 'archived')
        self.assertEqual(view['current_state'], 'packaged')
        self.assertEqual(self.protected_bytes(), before)
        metadata = (self.directory / 'session.json').read_bytes()
        self.assertTrue(self.archive()['reused'])
        self.assertEqual(recover_session(self.config, self.sid)['performed_stages'], [])
        self.assertEqual((self.directory / 'session.json').read_bytes(), metadata)

    def test_archive_insufficient_storage_nonfatal_and_explicit_retry(self):
        self.package()
        before = self.protected_bytes()
        with patch.object(OwnedDirectory, 'free_bytes', return_value=1):
            denied = archive_session(self.config, self.sid, decision='on')
        self.assertEqual(denied['status'], 'skipped_due_to_storage')
        self.assertEqual(denied['preflight']['free_bytes'], 1)
        self.assertGreater(denied['preflight']['required_free_bytes'], 256 * 1024**2)
        self.assertEqual(list(self.directory.glob('generated/full_archive/*/*.zip')), [])
        self.assertEqual(session_status(self.config, self.sid)['current_state'], 'packaged')
        metadata = (self.directory / 'session.json').read_bytes()
        self.assertEqual(recover_session(self.config, self.sid)['performed_stages'], [])
        self.assertEqual((self.directory / 'session.json').read_bytes(), metadata)
        self.assertEqual(self.protected_bytes(), before)
        self.archive()
        self.assertEqual(session_status(self.config, self.sid)['archive_status']['status'], 'archived')

    def test_archive_failure_or_corruption_does_not_invalidate_packages(self):
        self.package()
        with patch('recorandro.packages.write_zip', side_effect=OSError('controlled disk failure')):
            self.assertEqual(self.archive()['status'], 'failed')
        self.assertEqual(session_status(self.config, self.sid)['current_state'], 'packaged')
        self.archive()
        before = self.outputs('full_archive')
        entry = self.journal('full_archive')['files']['full_archive.zip']
        (self.directory / entry['relative_path']).write_bytes(b'bad')
        self.assertEqual(session_status(self.config, self.sid)['archive_status']['status'], 'failed_nonblocking')
        self.assertEqual(session_status(self.config, self.sid)['current_state'], 'packaged')
        self.archive()
        self.assertEqual(self.outputs('full_archive'), before)

    def test_member_safety_and_metadata_and_content_validation(self):
        for name in ('/absolute', '../escape', 'a/../b', 'a//b', 'C:/bad', 'a\\b', 'a\x00b', 'a/', './a'):
            with self.assertRaises(PackageFailure):
                safe_member(name)
        expected = {'part_01.m4a': inline(b'audio')}
        for variant in ('duplicate', 'unexpected', 'symlink', 'content', 'timestamp'):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w') as archive:
                info = zip_info('part_01.m4a')
                if variant == 'symlink':
                    info.external_attr = 0o120777 << 16
                if variant == 'timestamp':
                    info.date_time = (2020, 1, 1, 0, 0, 0)
                archive.writestr(info, b'wrong' if variant == 'content' else b'audio')
                if variant in ('duplicate', 'unexpected'):
                    with contextlib.suppress(UserWarning):
                        archive.writestr(zip_info('part_01.m4a' if variant == 'duplicate' else 'unexpected'), b'audio')
            with self.assertRaises(PackageFailure):
                verify_zip(buffer, expected)

    def test_actual_size_storage_bound(self):
        spec = {'part_01.zip': {'part_01.m4a': inline(b'audio')}}
        check = storage_check(spec, 1, existing_artifact_bytes=10)
        self.assertEqual(check['member_payload_bytes'], 5)
        self.assertEqual(check['existing_artifact_bytes'], 10)
        self.assertEqual(check['publication_extra_copy_bytes'], 0)
        self.assertEqual(check['decision'], 'deny')

    def test_part_zip_storage_denial_and_recovery_preserve_inputs(self):
        before = self.protected_bytes()
        with patch.object(OwnedDirectory, 'free_bytes', return_value=0), self.assertRaises(PackageFailure):
            package_session(self.config, self.sid)
        self.assertEqual(session_status(self.config, self.sid)['last_successful_state'], 'manifested')
        self.assertEqual(self.protected_bytes(), before)
        self.package()

    def test_resume_honors_recorded_on_and_failed_archive_is_nonblocking(self):
        self.package()
        record = self.record()
        record['archive_request'] = {'decision': 'explicit_on', 'provenance': 'explicit_archive_command'}
        self.write_record(record)
        with patch('recorandro.packages.write_zip', side_effect=OSError('controlled')):
            result = recover_session(self.config, self.sid)
        self.assertEqual(result['classification'], 'complete')
        self.assertEqual(result['performed_stages'], ['full_archive'])
        self.assertEqual(result['archive_status']['status'], 'failed_nonblocking')
        with patch.object(OwnedDirectory, 'free_bytes', return_value=10**12):
            result = recover_session(self.config, self.sid, stage='full_archive')
        self.assertEqual(result['archive_status']['status'], 'archived')

    def test_full_archive_publication_crash_and_reuse(self):
        self.package()
        class Crash(BaseException):
            pass
        actual = OwnedDirectory.publish
        def die(folder, temporary, final, destination=None):
            actual(folder, temporary, final, destination)
            if final == 'full_archive.zip':
                raise Crash()
        with patch.object(OwnedDirectory, 'publish', die), self.assertRaises(Crash):
            self.archive()
        old = self.journal('full_archive')
        self.assertEqual(session_status(self.config, self.sid)['current_state'], 'packaged')
        self.archive()
        self.assertEqual(self.journal('full_archive')['attempt_id'], old['attempt_id'])
        self.assertEqual(session_status(self.config, self.sid)['archive_status']['status'], 'archived')

    def test_cli_and_external_env_isolation(self):
        with patch('recorandro.cli.load_config', return_value=self.config), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['package-session', self.sid]), 0)
        self.assertTrue(json.loads(output.getvalue())['ok'])

    def test_live_lock_rejects_duplicate_run(self):
        from recorandro.inspection import _inspection_lock, InspectionFailure
        with OwnedDirectory.root(self.directory) as directory, _inspection_lock(directory):
            with self.assertRaises(InspectionFailure):
                self.package()

    def test_controlled_child_death_after_part_zip_publication(self):
        marker = self.base / 'zip-ready'
        code = '''
import sys, time
from pathlib import Path
from recorandro.config import Config
from recorandro.packages import package_session
from recorandro.storage import OwnedDirectory
publish = OwnedDirectory.publish
def pause(self, temporary, final, destination=None):
    publish(self, temporary, final, destination)
    if final == 'part_01.zip':
        Path(sys.argv[3]).write_text('ready')
        while True: time.sleep(0.1)
OwnedDirectory.publish = pause
package_session(Config(Path(sys.argv[1])), sys.argv[2])
'''
        child = subprocess.Popen([sys.executable, '-c', code, str(self.config.data_root), self.sid, str(marker)],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 30
            while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertTrue(marker.exists(), child.poll())
            from recorandro.inspection import InspectionFailure
            with self.assertRaises(InspectionFailure):
                self.package()
            child.kill()
            child.communicate(timeout=10)
            self.assertEqual(session_status(self.config, self.sid)['current_state'], 'manifested')
            self.package()
            self.assertEqual(session_status(self.config, self.sid)['current_state'], 'packaged')
            self.assertEqual(self.original.read_bytes(), self.contents)
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=10)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'actual tools required')
class RealPackageTests(unittest.TestCase):
    def test_actual_normalized_and_mp3_packages_and_archives(self):
        from recorandro.config import Config
        from recorandro.sessions import import_audio
        from recorandro.inspection import inspect_session
        from recorandro.normalization import normalize_session
        from recorandro.segmentation import plan_session
        from recorandro.exports import export_session
        for mode, suffix in (('auto', '.wav'), ('off', '.wav'), ('off', '.mp3')):
            with self.subTest(mode=mode, suffix=suffix), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                wave = base / 'small.wav'
                make_wav(wave, seconds=3)
                source = base / ('small' + suffix)
                if suffix == '.mp3':
                    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-n', '-i', str(wave), str(source)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True, timeout=30)
                config = Config(base / 'data')
                with patch.object(OwnedDirectory, 'free_bytes', return_value=10**12):
                    imported = import_audio(config, source, provision_seconds=3, archive='not_requested')
                    sid = imported['session_id']
                    inspect_session(config, sid)
                    normalized = normalize_session(config, sid, mode=mode)
                    plan_session(config, sid, mode='off')
                    exported = export_session(config, sid)
                    generate_manifests(config, sid)
                    directory = config.data_root / 'sessions' / sid
                    # ZIP generation/verification must invoke no media child.
                    with patch('subprocess.Popen', side_effect=AssertionError('No media processing while packaging')):
                        package = package_session(config, sid)
                        full = archive_session(config, sid, decision='on')
                journal = json.loads((directory / package['record_path']).read_bytes())
                with zipfile.ZipFile(directory / journal['files']['part_01.zip']['relative_path']) as archive:
                    self.assertIn('part_01.mp3' if suffix == '.mp3' else 'part_01.m4a', archive.namelist())
                    self.assertIsNone(archive.testzip())
                journal = json.loads((directory / full['record_path']).read_bytes())
                with zipfile.ZipFile(directory / journal['files']['full_archive.zip']['relative_path']) as archive:
                    self.assertIsNone(archive.testzip())
                    if mode == 'auto':
                        self.assertIn(normalized['working_source']['managed_path'], archive.namelist())
                    self.assertEqual(hashlib.sha256(archive.read(imported['audio']['managed_path'])).hexdigest(), imported['audio']['sha256'])
                self.assertEqual(session_status(config, sid)['archive_status']['status'], 'archived')
