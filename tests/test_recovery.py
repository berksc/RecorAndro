"""Recovery evidence gates, reuse, kernel lock and real child-process death."""

import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from recorandro.cli import main
from recorandro.config import Config
from recorandro.inspection import InspectionFailure, _inspection_lock, inspect_session
from recorandro.normalization import normalize_session
from recorandro.segmentation import plan_session
from recorandro.recovery import recover_session, RecoveryFailure
from recorandro.session_state import session_status
from recorandro.sessions import import_audio
from recorandro.storage import OwnedDirectory
from test_exports import ExportFixture
from test_normalization import make_wav


class RecoveryTests(ExportFixture):
    def resume(self, **kwargs):
        with patch('recorandro.normalization.run_probe', return_value=self.payload), \
                patch('recorandro.segmentation.detect_quiet_regions', return_value=[]), \
                patch('recorandro.exports._probe_part', side_effect=self.fake_probe), \
                patch('recorandro.exports._execute', side_effect=self.fake_execute), \
                patch('recorandro.exports._executable', return_value='ffmpeg'), \
                patch.object(OwnedDirectory, 'free_bytes', return_value=10**12):
            return recover_session(self.config, self.sid, **kwargs)

    def test_resume_and_complete_idempotence_without_original_source(self):
        self.external.unlink()
        result = self.resume()
        self.assertEqual(result['classification'], 'complete')
        self.assertEqual(result['current_state'], 'segments_exported')
        before = (self.directory / 'session.json').read_bytes()
        self.commands.clear()
        self.assertEqual(self.resume()['performed_stages'], [])
        self.assertEqual((self.directory / 'session.json').read_bytes(), before)
        self.assertEqual(self.commands, [])
        self.assertEqual(self.original.read_bytes(), self.contents)

    def test_missing_and_corrupt_part_regenerate_only_that_part(self):
        for missing in (True, False):
            with self.subTest(missing=missing):
                self.resume()
                old = self.record()['audio_export']
                report = json.loads((self.directory / old['record_path']).read_text())
                broken = self.directory / report['parts'][1]['managed_path']
                if missing:
                    broken.unlink()
                else:
                    broken.chmod(0o600)
                    broken.write_bytes(b'corrupt')
                self.assertEqual(self.resume(inspect_only=True)['classification'], 'failed_retryable')
                self.commands.clear()
                result = self.resume()
                self.assertEqual(result['classification'], 'complete')
                self.assertEqual(sum(phase == 'part_encode' for _, _, phase, _ in self.commands), 1)
                fresh = json.loads((self.directory / self.record()['audio_export']['record_path']).read_text())
                self.assertEqual([p['reused'] for p in fresh['parts']], [True, False, True])
                self.assertEqual(self.original.read_bytes(), self.contents)

    def test_failed_partial_export_reuses_verified_previous_parts(self):
        actual = self.fake_execute
        def fail_second(args, timeout, phase, **kwargs):
            if phase == 'part_encode' and 'part_02' in str(args[-1]):
                raise KeyboardInterrupt()
            return actual(args, timeout, phase, **kwargs)
        with patch.object(self, 'fake_execute', side_effect=fail_second):
            self.assertEqual(self.resume()['classification'], 'failed_retryable')
        self.commands.clear()
        result = self.resume()
        self.assertEqual(result['classification'], 'complete')
        self.assertEqual(sum(phase == 'part_encode' for _, _, phase, _ in self.commands), 2)

    def test_crash_after_first_of_three_parts_never_completes_partial_set(self):
        class Crash(BaseException):
            pass
        publish = OwnedDirectory.publish
        def die(folder, temporary, final, destination=None):
            publish(folder, temporary, final, destination)
            if final == 'part_01.m4a':
                raise Crash()
        with patch.object(OwnedDirectory, 'publish', die), self.assertRaises(Crash):
            self.resume()
        self.assertNotEqual(session_status(self.config, self.sid)['current_state'], 'segments_exported')
        self.commands.clear()
        result = self.resume()
        self.assertEqual(result['classification'], 'complete')
        self.assertEqual(result['part_count'], 3)
        self.assertEqual(sum(phase == 'part_encode' for _, _, phase, _ in self.commands), 2)
        self.assertEqual(self.original.read_bytes(), self.contents)

    def pending_completed_report(self):
        self.resume()
        record = self.record()
        pointer = record['audio_export']
        pointer.update(status='export_pending', success=False, record_sha256=None,
                       completed_at=None, verified_part_count=0)
        self.write_record(record)
        return pointer

    def test_dangling_completed_report_with_one_missing_part_reuses_other_parts(self):
        pointer = self.pending_completed_report()
        report = json.loads((self.directory / pointer['record_path']).read_text())
        (self.directory / report['parts'][1]['managed_path']).unlink()
        self.commands.clear()
        result = self.resume()
        self.assertEqual(result['classification'], 'complete')
        self.assertEqual(sum(phase == 'part_encode' for _, _, phase, _ in self.commands), 1)
        self.assertEqual(self.original.read_bytes(), self.contents)

    def test_reconciliation_metadata_failure_stops_without_regenerating_verified_parts(self):
        self.pending_completed_report()
        before = (self.directory / 'session.json').read_bytes()
        atomic = OwnedDirectory.atomic_json
        def fail(folder, record):
            if folder.path == self.directory:
                raise OSError('controlled canonical persistence failure')
            return atomic(folder, record)
        self.commands.clear()
        with patch.object(OwnedDirectory, 'atomic_json', fail):
            result = self.resume()
        self.assertEqual(result['classification'], 'failed_retryable')
        self.assertEqual(result['error_code'], 'metadata_persistence_failed')
        self.assertEqual(self.commands, [])
        self.assertEqual((self.directory / 'session.json').read_bytes(), before)
        self.assertEqual(self.resume()['classification'], 'complete')

    def test_obsolete_pending_export_report_is_not_reconciled_or_reused(self):
        self.pending_completed_report()
        self.configure_duration(3660)
        self.make_plan()
        self.commands.clear()
        result = self.resume()
        self.assertEqual(result['classification'], 'complete')
        self.assertNotIn('audio_export', result['reconciled_stages'])
        self.assertEqual(sum(phase == 'part_encode' for _, _, phase, _ in self.commands), 3)

    def test_failed_planning_retries_recorded_mode(self):
        record = self.record()
        record.pop('segmentation')
        self.write_record(record)
        with patch('recorandro.segmentation.plan_boundaries', side_effect=KeyboardInterrupt()):
            self.assertEqual(self.resume()['classification'], 'failed_retryable')
        self.assertEqual(self.resume()['performed_stages'], ['segmentation', 'audio_export'])

    def test_incomplete_import_requires_source_selection(self):
        record = self.record()
        # Direct corruption injection is not permitted through the safe writer.
        record['state'] = 'importing'
        for key in ('managed_path', 'size_bytes', 'sha256', 'imported_filename'):
            record['audio'][key] = None
        (self.directory / 'session.json').write_text(json.dumps(record))
        result = self.resume()
        self.assertEqual(result['classification'], 'failed_manual_attention')
        self.assertEqual(result['performed_stages'], [])
        self.assertEqual(self.original.read_bytes(), self.contents)

    def test_stale_plan_revision_rebuilds_downstream_and_keeps_old_files(self):
        self.resume()
        old = self.record()['audio_export']
        files = list((self.directory / 'generated/exports' / old['attempt_id']).glob('part_*'))
        self.configure_duration(3660)  # new inspection/normalization revision, same bytes
        result = self.resume()
        self.assertEqual(result['performed_stages'], ['segmentation', 'audio_export'])
        self.assertTrue(all(p.exists() for p in files))
        self.assertEqual(self.original.read_bytes(), self.contents)

    def test_corrupt_plan_regenerated_and_original_mismatch_manual(self):
        pointer = self.record()['segmentation']
        (self.directory / pointer['record_path']).write_text('{partial')
        self.assertEqual(self.resume()['performed_stages'], ['segmentation', 'audio_export'])
        self.original.chmod(0o600)
        self.original.write_bytes(b'original changed externally')
        before = (self.directory / 'session.json').read_bytes()
        result = self.resume()
        self.assertEqual(result['classification'], 'failed_manual_attention')
        self.assertEqual((self.directory / 'session.json').read_bytes(), before)

    def test_active_lock_blocks_and_leftover_lock_recovers(self):
        with OwnedDirectory.root(self.directory) as directory, _inspection_lock(directory) as token:
            with self.assertRaises(InspectionFailure) as error:
                self.resume()
            self.assertEqual(error.exception.code, 'inspection_busy')
        self.assertTrue((self.directory / '.inspection.lock').exists())
        with OwnedDirectory.root(self.directory) as directory:
            with self.assertRaises(InspectionFailure):
                with _inspection_lock(directory, token):
                    pass
        self.assertEqual(self.resume()['classification'], 'complete')

    def test_retry_verified_stage_noop_and_later_prerequisite_rejected(self):
        before = (self.directory / 'session.json').read_bytes()
        self.assertEqual(self.resume(stage='normalization')['performed_stages'], [])
        self.assertEqual((self.directory / 'session.json').read_bytes(), before)
        self.assertEqual(self.resume(stage='audio_export')['classification'], 'complete')
        record = self.record()
        record.pop('segmentation')
        self.write_record(record)
        with self.assertRaises(RecoveryFailure):
            self.resume(stage='audio_export')

    def test_partial_temps_and_corrupt_canonical_never_adopted(self):
        temp = self.directory / 'temp/unreferenced'
        temp.mkdir()
        (temp / 'normalized.m4a').write_bytes(b'partial')
        (self.directory / '.metadata-crash.tmp').write_text('{broken')
        self.assertEqual(self.resume()['classification'], 'complete')
        self.assertEqual((temp / 'normalized.m4a').read_bytes(), b'partial')
        path = self.directory / 'session.json'
        path.write_text('{broken')
        self.assertEqual(self.resume()['classification'], 'failed_manual_attention')
        self.assertEqual(path.read_text(), '{broken')

    def test_malformed_stage_and_invalid_modes_are_manual_without_writes(self):
        baseline = self.record()
        for stage, replacement in (('normalization', []),
                ('normalization', dict(baseline['normalization'], status='unknown')),
                ('normalization', dict(baseline['normalization'], mode_requested='unknown')),
                ('segmentation', dict(baseline['segmentation'], mode_requested='unknown'))):
            with self.subTest(stage=stage, replacement=replacement):
                record = copy.deepcopy(baseline)
                record[stage] = replacement
                path = self.directory / 'session.json'
                path.write_text(json.dumps(record))
                before = path.read_bytes()
                result = self.resume()
                self.assertEqual(result['classification'], 'failed_manual_attention')
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(self.original.read_bytes(), self.contents)

    def test_legacy_v1_verified_exports_resume_without_migration_or_encoding(self):
        self.resume()
        record = self.record()
        from recorandro.session_state import PROJECTION_KEYS
        for key in PROJECTION_KEYS:
            record.pop(key, None)
        record['schema_version'] = 1
        path = self.directory / 'session.json'
        path.write_text(json.dumps(record))
        before = path.read_bytes()
        self.commands.clear()
        result = self.resume()
        self.assertEqual(result['classification'], 'complete')
        self.assertEqual(result['performed_stages'], [])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.commands, [])

    def test_cli_resume_and_status_classification_external_env_isolated(self):
        self.resume()
        config = self.base / 'config.json'
        config.write_text(json.dumps({'data_root': str(self.config.data_root)}))
        with patch.dict(os.environ):
            os.environ.pop('RECORANDRO_DATA_ROOT', None)
            for command in ('resume', 'retry'):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(['--config', str(config), command, self.sid]), 0)
                self.assertEqual(json.loads(output.getvalue())['classification'], 'complete')
        self.assertEqual(session_status(self.config, self.sid)['recovery']['classification'], 'complete')


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'actual tools required')
class ControlledInterruptionTests(unittest.TestCase):
    def test_missing_or_corrupt_normalized_source_invalidates_dependents(self):
        for missing in (True, False):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                config = Config(base / 'data')
                source = base / 'source.wav'
                make_wav(source, seconds=3)
                with patch.object(OwnedDirectory, 'free_bytes', return_value=10**12):
                    imported = import_audio(config, source, provision_seconds=3)
                    sid = imported['session_id']
                    self.assertEqual(recover_session(config, sid)['classification'], 'complete')
                    directory = config.data_root / 'sessions' / sid
                    record = json.loads((directory / 'session.json').read_text())
                    normalized = directory / record['normalization']['working_source']['managed_path']
                    self.assertEqual(record['normalization']['output_source'], 'normalized')
                    old_part_report = json.loads((directory / record['audio_export']['record_path']).read_text())
                    old_part = directory / old_part_report['parts'][0]['managed_path']
                    if missing:
                        normalized.unlink()
                    else:
                        normalized.chmod(0o600)
                        normalized.write_bytes(b'corrupt')
                    self.assertEqual(recover_session(config, sid, inspect_only=True)['last_successful_state'], 'probed')
                    result = recover_session(config, sid)
                self.assertEqual(result['performed_stages'], ['normalization', 'segmentation', 'audio_export'])
                self.assertEqual(result['classification'], 'complete')
                self.assertTrue(old_part.exists())
                original = directory / imported['audio']['managed_path']
                self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), imported['audio']['sha256'])

    def exercise(self, checkpoint):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            config = Config(base / 'data')
            source = base / 'source.wav'
            make_wav(source, seconds=3)
            with patch.object(OwnedDirectory, 'free_bytes', return_value=10**12):
                imported = import_audio(config, source, provision_seconds=3)
                sid = imported['session_id']
                inspect_session(config, sid)
                if checkpoint.startswith(('plan_', 'export_')):
                    normalize_session(config, sid)
                if checkpoint.startswith('export_'):
                    plan_session(config, sid)
            directory = config.data_root / 'sessions' / sid
            original = directory / imported['audio']['managed_path']
            original_bytes = original.read_bytes()
            marker = base / 'ready'
            helper = Path(__file__).with_name('recovery_child.py')
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
            kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
            with (base / 'child.log').open('wb') as log:
                child = subprocess.Popen([sys.executable, str(helper), str(config.data_root), sid,
                                          checkpoint, str(marker)], env=env, stdout=log, stderr=log, **kwargs)
                try:
                    deadline = time.monotonic() + 45
                    while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.05)
                    self.assertTrue(marker.exists(), (base / 'child.log').read_text())
                    with self.assertRaises(InspectionFailure) as duplicate:
                        recover_session(config, sid)
                    self.assertEqual(duplicate.exception.code, 'inspection_busy')
                finally:
                    if child.poll() is None:
                        child.kill()
                    child.wait(timeout=10)
            pending = json.loads((directory / 'session.json').read_text())
            self.assertNotEqual(pending['current_state'], 'segments_exported')
            if checkpoint == 'normalization_publish':
                attempt = pending['normalization']['attempt_id']
                report = json.loads((directory / 'generated/normalization' / attempt / 'session.json').read_text())
                self.assertEqual(report['status'], 'normalization_pending')
                self.assertIn('publication_intent', report)
            if checkpoint == 'export_publish':
                report = json.loads((directory / pending['audio_export']['record_path']).read_text())
                self.assertEqual(report['status'], 'export_pending')
                self.assertEqual(report['parts'][0]['status'], 'publication_ready')
            with patch.object(OwnedDirectory, 'free_bytes', return_value=10**12):
                result = recover_session(config, sid)
            self.assertEqual(result['classification'], 'complete', result)
            self.assertEqual(original.read_bytes(), original_bytes)
            self.assertEqual(hashlib.sha256(original_bytes).hexdigest(), imported['audio']['sha256'])
            if checkpoint == 'normalization_publish':
                self.assertIn('normalization', result['reconciled_stages'])
                self.assertNotIn('normalization', result['performed_stages'])
            if checkpoint == 'plan_report':
                self.assertIn('segmentation', result['reconciled_stages'])
                self.assertNotIn('segmentation', result['performed_stages'])
            if checkpoint == 'export_report':
                self.assertEqual(result['performed_stages'], [])
            if checkpoint == 'export_publish':
                pointer = json.loads((directory / 'session.json').read_text())['audio_export']
                report = json.loads((directory / pointer['record_path']).read_text())
                self.assertTrue(report['parts'][0]['reused'])
            before = (directory / 'session.json').read_bytes()
            self.assertEqual(recover_session(config, sid)['performed_stages'], [])
            self.assertEqual((directory / 'session.json').read_bytes(), before)

    def test_kill_during_normalization_generation(self):
        self.exercise('normalization_generate')

    def test_kill_after_normalized_publication_before_metadata(self):
        self.exercise('normalization_publish')

    def test_kill_during_planning(self):
        self.exercise('plan_generate')

    def test_kill_after_plan_report_before_metadata(self):
        self.exercise('plan_report')

    def test_kill_during_part_generation(self):
        self.exercise('export_generate')

    def test_kill_after_part_publication_before_metadata(self):
        self.exercise('export_publish')

    def test_kill_after_export_report_before_metadata(self):
        self.exercise('export_report')
