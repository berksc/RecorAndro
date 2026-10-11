"""Step 3.1 evidence gates, compatibility, ownership and atomic publication."""

import contextlib
import copy
import hashlib
import io
import json
import os
import uuid
from unittest.mock import patch

from recorandro.cli import main
from recorandro.inspection import inspect_session, _read_record, InspectionFailure
from recorandro.normalization import normalize_session
from recorandro.exports import ExportFailure
from recorandro.session_state import (PROJECTION_KEYS, STATES, artifact_entry,
                                      session_status, validate_transition)
from recorandro.storage import OwnedDirectory, StorageError
from test_exports import ExportFixture


class StateTests(ExportFixture):
    def status(self):
        return session_status(self.config, self.sid)

    def test_normal_progression_legacy_state_and_stage_reference_ownership(self):
        observed = []
        baseline = self.record()
        for remove, expected in ((('inspection', 'normalization', 'segmentation'), 'imported'),
                                 (('normalization', 'segmentation'), 'probed'),
                                 (('segmentation',), 'normalized_or_skipped'), ((), 'segmentation_planned')):
            record = copy.deepcopy(baseline)
            for key in remove:
                record.pop(key, None)
            self.write_record(record)
            observed.append(self.status()['current_state'])
            self.assertEqual(observed[-1], expected)
            self.assertEqual(record['state'], 'imported')
        result = self.mocked_export()
        self.assertTrue(result['success'])
        view = self.status()
        self.assertEqual(view['current_state'], 'segments_exported')
        self.assertEqual(view['last_successful_state'], 'segments_exported')
        self.assertEqual(view['part_count'], 3)
        self.assertEqual(self.record()['current_state'], 'segments_exported')
        self.assertEqual(self.original.read_bytes(), self.contents)

    def test_invalid_transition_and_forged_future_state_cannot_advance(self):
        record = self.record()
        validate_transition(record, 'segmentation_planned')
        for state in ('packaged', 'complete', 'unknown', 'segments_exported'):
            with self.subTest(state=state), self.assertRaises(StorageError):
                validate_transition(record, state)
        record.update(current_state='complete', last_successful_state='packaged')
        self.write_record(record)
        self.assertEqual(self.record()['current_state'], 'segmentation_planned')
        self.assertEqual(len(STATES), len(set(STATES)))

    def test_atomic_replace_failure_retains_old_canonical_and_caller(self):
        path = self.directory / 'session.json'
        before = path.read_bytes()
        record = self.record()
        old_timestamp = record['updated_at']
        record['title'] = 'New title'
        with patch('recorandro.storage.os.replace', side_effect=OSError('controlled')), self.assertRaises(OSError):
            self.write_record(record)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(record['updated_at'], old_timestamp)
        self.assertEqual(list(self.directory.glob('.metadata-*.tmp')), [])

    def test_partial_serialization_and_corrupt_leftover_temp_do_not_replace_canonical(self):
        path = self.directory / 'session.json'
        before = path.read_bytes()
        def partial(record, output, **kwargs):
            output.write('{"schema_version":')
            raise OSError('controlled partial write')
        with patch('recorandro.storage.json.dump', side_effect=partial), self.assertRaises(OSError):
            self.write_record(self.record())
        self.assertEqual(path.read_bytes(), before)
        orphan = self.directory / '.metadata-interrupted.tmp'
        orphan.write_text('{corrupt')
        self.assertEqual(self.status()['current_state'], 'segmentation_planned')
        self.assertEqual(path.read_bytes(), before)
        self.write_record(self.record())
        self.assertEqual(self.status()['current_state'], 'segmentation_planned')
        self.assertEqual(orphan.read_text(), '{corrupt')

    def test_silent_corrupt_serialization_and_oversized_candidate_refused(self):
        path = self.directory / 'session.json'
        before = path.read_bytes()
        for payload in ('{"schema_version":', '{"wrong": true}'):
            def corrupt(record, output, **kwargs):
                output.write(payload)
            with patch('recorandro.storage.json.dump', side_effect=corrupt), self.assertRaises(StorageError):
                self.write_record(self.record())
            self.assertEqual(path.read_bytes(), before)
        record = self.record()
        record['oversized'] = 'x' * (1024 * 1024)
        with self.assertRaises(StorageError):
            self.write_record(record)
        self.assertEqual(path.read_bytes(), before)

    def test_created_and_failed_import_status_round_trip(self):
        record = copy.deepcopy(self.imported)
        record['session_id'] = uuid.uuid4().hex
        for key in PROJECTION_KEYS:
            record.pop(key, None)
        record['schema_version'] = 1
        record['state'] = 'importing'
        for key in ('managed_path', 'imported_filename', 'size_bytes', 'sha256'):
            record['audio'][key] = None
        path = self.config.data_root / 'sessions' / record['session_id']
        with OwnedDirectory.root(path) as directory:
            directory.atomic_json(record)
            self.assertEqual(record['current_state'], 'created')
            record['state'] = 'failed'
            record['errors'] = [{'code': 'audio_import_failed', 'message': 'controlled'}]
            directory.atomic_json(record)
        view = session_status(self.config, record['session_id'])
        self.assertEqual(view['current_state'], 'failed')
        self.assertEqual(view['last_successful_state'], 'created')
        self.assertEqual(view['errors'][0]['stage'], 'import')
        self.assertNotIn('original_audio', view['artifacts'])

    def test_original_and_session_identity_invariants_refuse_atomic_update(self):
        path = self.directory / 'session.json'
        before = path.read_bytes()
        for key, value in (('sha256', '0' * 64), ('size_bytes', 42), ('managed_path', 'originals/audio/new.wav')):
            record = self.record()
            record['audio'][key] = value
            with self.subTest(key=key), self.assertRaises(StorageError):
                self.write_record(record)
            self.assertEqual(path.read_bytes(), before)
        for key, value in (('session_id', '0' * 32), ('created_at', 'new'), ('state', 'failed')):
            record = self.record()
            record[key] = value
            with self.subTest(key=key), self.assertRaises(StorageError):
                self.write_record(record)
            self.assertEqual(path.read_bytes(), before)

    def test_regenerable_registry_original_protection_and_no_recursive_hash(self):
        self.mocked_export()
        registry = self.status()['artifacts']
        self.assertTrue(registry['original_audio']['protected'])
        self.assertFalse(registry['original_audio']['regenerable'])
        metadata = registry['session_metadata']
        self.assertIsNone(metadata['sha256'])
        self.assertIsNone(metadata['size_bytes'])
        self.assertEqual(metadata['status'], 'canonical')
        parts = [a for a in registry.values() if a['type'] == 'audio_part']
        self.assertEqual(len(parts), 3)
        for part in parts:
            self.assertEqual(part['classification'], 'regenerable')
            self.assertEqual(part['status'], 'verified')
            self.assertEqual(part['source_artifact_id'], 'original_audio')
            self.assertEqual(hashlib.sha256((self.directory / part['relative_path']).read_bytes()).hexdigest(), part['sha256'])
        for kind in ('zip_package', 'full_archive', 'normalized_audio', 'report'):
            entry = artifact_entry('future', kind, 'generated/future', source='original_audio')
            self.assertTrue(entry['regenerable'])
        with self.assertRaises(StorageError):
            artifact_entry('metadata', 'session_metadata', 'session.json', sha256='0' * 64)
        with self.assertRaises(StorageError):
            artifact_entry('part', 'audio_part', 'generated/part.m4a', status='verified')

    def test_zero_photos_visual_absence_and_nonblocking_failure(self):
        self.mocked_export()
        record = self.record()
        self.assertEqual(record['visual_count'], 0)
        self.assertNotIn('visual_status', record)
        self.assertFalse(any('visual' in warning or 'photo' in warning for warning in self.status()['warnings']))
        for visual_status in ('failed_nonblocking', {'malformed': True}):
            record.update(visual_count=2, visual_status=visual_status)
            self.write_record(record)
            self.assertEqual(self.status()['current_state'], 'segments_exported')
        self.assertEqual(self.original.read_bytes(), self.contents)

    def test_session_round_trip_and_status_read_only(self):
        before = self.record()
        self.write_record(before)
        loaded = self.record()
        for key in PROJECTION_KEYS:
            self.assertEqual(loaded[key], before[key])
        path = self.directory / 'session.json'
        content = path.read_bytes()
        self.assertEqual(self.status(), self.status())
        self.assertEqual(path.read_bytes(), content)
        with OwnedDirectory.root(self.directory) as directory:
            self.assertEqual(_read_record(directory, self.sid), loaded)

    def test_legacy_v1_complete_chain_read_only_then_migrated_on_existing_action(self):
        self.mocked_export()
        path = self.directory / 'session.json'
        legacy = self.record()
        for key in PROJECTION_KEYS:
            legacy.pop(key, None)
        legacy['schema_version'] = 1
        path.write_text(json.dumps(legacy), encoding='utf-8')
        before = path.read_bytes()
        status = self.status()
        self.assertEqual(status['stored_schema_version'], 1)
        self.assertEqual(status['current_state'], 'segments_exported')
        self.assertEqual(path.read_bytes(), before)
        self.mocked_export()
        self.assertEqual(self.record()['schema_version'], 2)
        for key in ('audio', 'created_at', 'state', 'inspection', 'normalization', 'segmentation'):
            self.assertEqual(self.record()[key], legacy[key])

    def test_pending_failed_missing_downstream_never_advance(self):
        self.mocked_export()
        baseline = self.record()
        for stage, pending, failed, expected in (
                ('inspection', 'probe_pending', 'probe_failed', 'imported'),
                ('normalization', 'normalization_pending', 'normalization_failed', 'probed'),
                ('segmentation', 'planning_pending', 'planning_failed', 'normalized_or_skipped'),
                ('audio_export', 'export_pending', 'export_failed', 'segmentation_planned')):
            for status in (pending, failed, None):
                record = copy.deepcopy(baseline)
                if status is None:
                    record.pop(stage)
                else:
                    record[stage]['status'] = status
                    if status == failed:
                        record[stage]['error'] = {'code': 'controlled_failure', 'message': 'controlled'}
                    # Inject inconsistent report bytes deliberately; cannot
                    # establish success even if old downstream files remain.
                (self.directory / 'session.json').write_text(json.dumps(record), encoding='utf-8')
                view = self.status()
                self.assertEqual(view['last_successful_state'], expected)
                self.assertNotEqual(view['current_state'], 'segments_exported')
                self.assertEqual(view['part_count'], 0)

    def test_new_probe_revision_invalidates_normalization_and_all_downstream(self):
        self.mocked_export()
        with patch('recorandro.inspection.run_probe', return_value=self.payload):
            inspect_session(self.config, self.sid)
        view = self.status()
        self.assertEqual(view['current_state'], 'probed')
        self.assertIn('stale_normalization_revision', view['warnings'])
        self.assertEqual(view['part_count'], 0)
        self.assertTrue(all(a['status'] == 'stale' for a in view['artifacts'].values() if a['regenerable']))

    def test_new_normalization_revision_invalidates_existing_plan_and_exports(self):
        self.mocked_export()
        with patch('recorandro.normalization.run_probe', return_value=self.payload), \
                patch('recorandro.normalization._execute', return_value=''), \
                patch('recorandro.normalization._executable', return_value='ffmpeg'):
            normalize_session(self.config, self.sid, mode='off')
        view = self.status()
        self.assertEqual(view['current_state'], 'normalized_or_skipped')
        self.assertIn('stale_segmentation_revision', view['warnings'])
        self.assertEqual(view['part_count'], 0)

    def test_new_plan_revision_invalidates_old_export(self):
        self.mocked_export()
        self.make_plan()
        view = self.status()
        self.assertEqual(view['current_state'], 'segmentation_planned')
        self.assertIn('stale_export_revision', view['warnings'])
        self.assertEqual(view['part_count'], 0)

    def test_corrupt_part_preserves_original_and_blocks_export_milestone(self):
        exported = self.mocked_export()
        target = self.directory / exported['parts'][0]['managed_path']
        target.chmod(0o600)
        target.write_bytes(b'corrupt')
        view = self.status()
        self.assertEqual(view['current_state'], 'failed')
        self.assertEqual(view['last_successful_state'], 'segmentation_planned')
        self.assertEqual(view['part_count'], 0)
        self.assertTrue(view['errors'][0]['retryable'])
        self.assertEqual(self.original.read_bytes(), self.contents)
        self.assertTrue(any(a['status'] == 'unverified' for a in view['artifacts'].values()))

    def test_report_hash_and_missing_semantic_evidence_block_success(self):
        exported = self.mocked_export()
        record = self.record()
        path = self.directory / record['audio_export']['record_path']
        original = path.read_bytes()
        path.write_bytes(original + b' ')
        self.assertEqual(self.status()['current_state'], 'failed')
        path.write_bytes(original)
        for change in ('decode', 'coverage', 'source'):
            bad = copy.deepcopy(exported)
            if change == 'decode':
                bad['parts'][0]['verification']['full_decode_passed'] = False
            elif change == 'coverage':
                bad['coverage']['no_gaps'] = False
            else:
                bad['parts'][0]['source_artifact']['sha256'] = '0' * 64
            path.write_text(json.dumps(bad), encoding='utf-8')
            candidate = copy.deepcopy(record)
            candidate['audio_export']['record_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            (self.directory / 'session.json').write_text(json.dumps(candidate), encoding='utf-8')
            view = self.status()
            self.assertEqual(view['current_state'], 'failed')
            self.assertEqual(view['last_successful_state'], 'segmentation_planned')
            self.assertEqual(self.original.read_bytes(), self.contents)

    def test_incomplete_probe_and_original_tamper_do_not_claim_probed(self):
        record = self.record()
        record['inspection']['integrity']['after']['status'] = 'not_checked'
        self.write_record(record)
        self.assertEqual(self.status()['last_successful_state'], 'imported')
        self.original.chmod(0o600)
        self.original.write_bytes(b'corrupt original')
        self.assertEqual(self.status()['last_successful_state'], 'created')
        self.assertFalse(self.status()['errors'][0]['retryable'])

    def test_cli_machine_status_and_invalid_id(self):
        config = self.base / 'status-config.json'
        config.write_text(json.dumps({'data_root': str(self.config.data_root)}))
        for external_root in (None, str(self.base / 'unrelated-data')):
            with self.subTest(external_root=external_root), patch.dict(os.environ):
                if external_root is None:
                    os.environ.pop('RECORANDRO_DATA_ROOT', None)
                else:
                    os.environ['RECORANDRO_DATA_ROOT'] = external_root
                # Exercise the temporary config without inheriting the user's
                # higher-precedence data root; restore their environment afterward.
                with patch.dict(os.environ):
                    os.environ.pop('RECORANDRO_DATA_ROOT', None)
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        code = main(['--config', str(config), 'status', self.sid])
                    self.assertEqual(code, 0)
                    self.assertEqual(json.loads(output.getvalue())['current_state'], 'segmentation_planned')
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(main(['--config', str(config), 'status', '../invalid']), 1)
                self.assertEqual(os.environ.get('RECORANDRO_DATA_ROOT'), external_root)

    def test_status_uses_existing_lock(self):
        from recorandro.inspection import _inspection_lock
        with OwnedDirectory.root(self.directory) as directory, _inspection_lock(directory), \
                self.assertRaises(InspectionFailure) as failure:
            self.status()
        self.assertEqual(failure.exception.code, 'inspection_busy')

    def test_partial_export_registry_keeps_candidates_without_claiming_success(self):
        def broken(args, timeout, phase, **kwargs):
            result = ExportFixture.fake_execute(self, args, timeout, phase, **kwargs)
            if phase == 'part_encode' and 'part_02' in str(args[-1]):
                raise ExportFailure('tool_nonzero_exit', 'Controlled failure')
            return result
        with patch.object(self, 'fake_execute', side_effect=broken), self.assertRaises(ExportFailure):
            self.mocked_export()
        view = self.status()
        self.assertEqual(view['current_state'], 'failed')
        self.assertEqual(view['last_successful_state'], 'segmentation_planned')
        parts = [a for a in view['artifacts'].values() if a['type'] == 'audio_part']
        self.assertEqual([a['status'] for a in parts], ['unverified', 'failed', 'pending'])
        self.assertEqual(parts[0]['stage_part_status'], 'verified')
        self.assertEqual(view['part_count'], 0)
        self.assertEqual(self.original.read_bytes(), self.contents)

    def test_real_normalized_artifact_registration_and_tamper_gate(self):
        import shutil
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            self.skipTest('Real media tools unavailable')
        inspect_session(self.config, self.sid)
        normalize_session(self.config, self.sid, mode='auto')
        view = self.status()
        self.assertEqual(view['current_state'], 'normalized_or_skipped')
        normalized = [a for a in view['artifacts'].values() if a['type'] == 'normalized_audio' and a['status'] == 'verified']
        self.assertEqual(len(normalized), 1)
        entry = normalized[0]
        self.assertEqual(entry['source_artifact_id'], 'original_audio')
        path = self.directory / entry['relative_path']
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry['sha256'])
        path.chmod(0o600)
        path.write_bytes(b'corrupt')
        self.assertEqual(self.status()['last_successful_state'], 'probed')
        self.assertEqual(self.status()['current_state'], 'failed')
        self.assertTrue(self.status()['errors'][0]['retryable'])
        self.assertEqual(self.original.read_bytes(), self.contents)
