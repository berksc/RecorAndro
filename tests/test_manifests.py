"""Documents are derived from verified audio; faults cannot promote partial sets."""

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from recorandro.cli import main
from recorandro.manifests import generate_manifests, ManifestFailure, documents, human
from recorandro.recovery import recover_session
from recorandro.session_state import session_status
from recorandro.storage import OwnedDirectory
from test_exports import ExportFixture
from test_normalization import make_wav
from recorandro.config import Config
from recorandro.sessions import import_audio
from recorandro.inspection import inspect_session, InspectionFailure, _inspection_lock
from recorandro.normalization import normalize_session
from recorandro.segmentation import plan_session
from recorandro.exports import export_session


class ManifestTests(ExportFixture):
    def setUp(self):
        super().setUp()
        self.exported = self.mocked_export()

    def journal(self):
        return json.loads((self.directory / self.record()['manifest_generation']['record_path']).read_bytes())

    def blobs(self):
        return {name: (self.directory / entry['relative_path']).read_bytes() for name, entry in self.journal()['files'].items()}

    def audio_bytes(self):
        return {p['managed_path']: (self.directory / p['managed_path']).read_bytes() for p in self.exported['parts']}

    def test_audio_only_multi_part_registry_determinism_and_nonmutation(self):
        before, audio = self.record(), self.audio_bytes()
        generate_manifests(self.config, self.sid)
        first = self.blobs()
        canonical = (self.directory / 'session.json').read_bytes()
        self.assertTrue(generate_manifests(self.config, self.sid)['reused'])
        self.assertEqual(self.blobs(), first)
        self.assertEqual((self.directory / 'session.json').read_bytes(), canonical)
        self.assertEqual(recover_session(self.config, self.sid, stage='manifest_generation')['performed_stages'], [])
        self.assertEqual(self.audio_bytes(), audio)
        self.assertEqual(self.original.read_bytes(), self.contents)
        for key in ('audio', 'inspection', 'normalization', 'segmentation', 'audio_export', 'state'):
            self.assertEqual(self.record()[key], before[key])
        view = session_status(self.config, self.sid)
        self.assertEqual(view['current_state'], 'manifested')
        entries = [e for e in view['artifacts'].values() if e['type'] in ('manifest', 'report') and e['status'] == 'verified']
        self.assertEqual(len(entries), 10)  # nine documents + journal
        for entry in entries:
            blob = (self.directory / entry['relative_path']).read_bytes()
            self.assertEqual(entry['sha256'], hashlib.sha256(blob).hexdigest())
            self.assertEqual(entry['size_bytes'], len(blob))
            self.assertTrue(entry['regenerable'])
        model = json.loads(first['manifest.json'])
        self.assertEqual(model['visual_count'], 0)
        self.assertEqual(model['visual_status'], 'none')
        self.assertNotIn('## Visuals', first['processing_report.md'].decode())
        self.assertFalse(any('visual' in w or 'photo' in w for w in model['warnings']))
        self.assertEqual(model['timeline']['ownership_duration_seconds'], 3660)
        self.assertEqual(model['parts'][0]['nominal_end_seconds'], 1500)
        self.assertEqual(model['parts'][0]['global_end_seconds'], 1505)
        self.assertEqual(model['parts'][1]['global_start_seconds'], 1500)
        self.assertEqual(model['parts'][-1]['global_end_seconds'], 3660)
        self.assertEqual(model['normalization']['result'], 'skipped')
        self.assertFalse(model['completion']['globally_complete'])

    def test_json_markdown_parity_and_report_shared_model(self):
        generate_manifests(self.config, self.sid)
        blobs = self.blobs()
        model = json.loads(blobs['manifest.json'])
        self.assertEqual(documents(model), blobs)
        for name, blob in blobs.items():
            if name.endswith('manifest.json'):
                md = blobs[name[:-4] + 'md'].decode()
                embedded = md.split('```json\n')[1].split('\n```')[0]
                self.assertEqual(json.loads(blob), json.loads(embedded))

    def test_single_part_tiny_adjustment_and_warning_representation(self):
        for duration, mode in ((30, 'off'), (3180, 'auto'), (4800, 'auto')):
            self.configure_duration(duration)
            self.make_plan(mode)
            self.exported = self.mocked_export()
            record = self.record()
            record['warnings'].append('archive_space_warning')
            record['title'] = 'Title | ```\n# not a heading'
            self.write_record(record)
            generate_manifests(self.config, self.sid)
            blobs = self.blobs()
            model = json.loads(blobs['manifest.json'])
            self.assertIn('archive_space_warning', model['warnings'])
            self.assertEqual(model['errors'], [])
            self.assertEqual(model['segmentation']['part_count'], len(self.ranges))
            self.assertEqual(model['parts'][-1]['global_end_seconds'], duration)
            if duration == 30:
                self.assertEqual(model['parts'][0]['overlap_after_seconds'], 0)
            if duration == 4800:
                self.assertTrue(model['segmentation']['tiny_part_avoidance_adjustments'])
            embedded = blobs['manifest.md'].decode().split('```json\n')[1].split('\n```')[0]
            self.assertEqual(json.loads(embedded), model)

    def test_missing_corrupt_and_stale_audio_rejected_without_documents(self):
        for corruption in ('missing', 'corrupt', 'stale'):
            with self.subTest(corruption=corruption):
                if corruption == 'stale':
                    self.configure_duration(3660)
                    self.make_plan()
                else:
                    target = self.directory / self.exported['parts'][0]['managed_path']
                    target.chmod(0o600)
                    if corruption == 'missing':
                        target.unlink()
                    else:
                        target.write_bytes(b'bad')
                with self.assertRaises(ManifestFailure):
                    generate_manifests(self.config, self.sid)
                self.assertNotIn('manifest_generation', self.record())
                self.assertEqual(self.original.read_bytes(), self.contents)
                if corruption != 'stale':
                    self.exported = self.mocked_export(retry=True)

    def test_corrupt_document_reuses_other_verified_documents_and_never_audio(self):
        generate_manifests(self.config, self.sid)
        before = self.blobs()
        prior = self.journal()
        path = self.directory / prior['files']['manifest.md']['relative_path']
        path.write_bytes(b'corrupt')
        self.assertEqual(session_status(self.config, self.sid)['last_successful_state'], 'segments_exported')
        self.assertEqual(session_status(self.config, self.sid)['current_state'], 'failed')
        self.commands.clear()
        result = recover_session(self.config, self.sid)
        self.assertEqual(result['performed_stages'], ['manifest_generation', 'package_generation'])
        self.assertEqual(result['current_state'], 'packaged')
        self.assertEqual(self.commands, [])
        fresh = self.journal()
        self.assertEqual(self.blobs(), before)
        self.assertNotEqual(fresh['files']['manifest.md']['relative_path'], prior['files']['manifest.md']['relative_path'])
        for name in prior['files']:
            if name != 'manifest.md':
                self.assertEqual(fresh['files'][name]['relative_path'], prior['files'][name]['relative_path'])

    def test_missing_document_and_forged_journal_cannot_advance_state(self):
        generate_manifests(self.config, self.sid)
        prior = self.journal()
        (self.directory / prior['files']['processing_report.md']['relative_path']).unlink()
        self.assertEqual(session_status(self.config, self.sid)['last_successful_state'], 'segments_exported')
        generate_manifests(self.config, self.sid)
        record = self.record()
        prior = self.journal()
        prior['source_revision'] = '0' * 64
        path = self.directory / record['manifest_generation']['record_path']
        with OwnedDirectory.root(path.parent) as folder:
            folder.atomic_json(prior)
        record['manifest_generation'].update(source_revision='0' * 64, record_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.write_record(record)
        self.assertEqual(session_status(self.config, self.sid)['last_successful_state'], 'segments_exported')
        self.assertEqual(session_status(self.config, self.sid)['errors'][0]['code'], 'invalid_manifest_evidence')
        generate_manifests(self.config, self.sid)
        self.assertEqual(session_status(self.config, self.sid)['current_state'], 'manifested')

    def test_metadata_change_invalidates_revision(self):
        generate_manifests(self.config, self.sid)
        record = self.record()
        record['title'] = 'Supplied later'
        self.write_record(record)
        self.assertEqual(session_status(self.config, self.sid)['last_successful_state'], 'segments_exported')
        generate_manifests(self.config, self.sid)
        self.assertEqual(json.loads(self.blobs()['manifest.json'])['title'], 'Supplied later')

    def test_partial_publication_never_advances_and_resume_reuses_member(self):
        class Crash(BaseException):
            pass
        publish = OwnedDirectory.publish
        def die(folder, temporary, final, destination=None):
            publish(folder, temporary, final, destination)
            if final == 'manifest.json':
                raise Crash()
        with patch.object(OwnedDirectory, 'publish', die), self.assertRaises(Crash):
            generate_manifests(self.config, self.sid)
        prior = self.journal()
        self.assertEqual(session_status(self.config, self.sid)['current_state'], 'segments_exported')
        # A partial staging file is unrelated to final member evidence.
        (self.directory / 'temp' / 'partial.tmp').write_bytes(b'{')
        result = recover_session(self.config, self.sid)
        self.assertEqual(result['current_state'], 'packaged')
        self.assertEqual(self.journal()['files']['manifest.json']['relative_path'], prior['files']['manifest.json']['relative_path'])

    def test_crash_after_complete_publication_adopts_without_new_attempt(self):
        class Crash(BaseException):
            pass
        atomic = OwnedDirectory.atomic_json
        def die(folder, record):
            if folder.path == self.directory and record.get('manifest_generation', {}).get('status') == 'manifest_succeeded':
                raise Crash()
            return atomic(folder, record)
        with patch.object(OwnedDirectory, 'atomic_json', die), self.assertRaises(Crash):
            generate_manifests(self.config, self.sid)
        prior = self.journal()
        self.assertEqual(session_status(self.config, self.sid)['current_state'], 'segments_exported')
        generate_manifests(self.config, self.sid)
        self.assertEqual(self.journal()['attempt_id'], prior['attempt_id'])
        self.assertEqual(self.journal()['files'], prior['files'])

    def test_cli_isolated_from_external_environment(self):
        config = self.base / 'config.json'
        config.write_text(json.dumps({'data_root': str(self.config.data_root)}))
        with patch.dict(os.environ, {'RECORANDRO_DATA_ROOT': str(self.config.data_root)}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['--config', str(config), 'manifest-session', self.sid]), 0)
        self.assertTrue(json.loads(output.getvalue())['ok'])

    def test_human_precision(self):
        self.assertEqual(human(3691.787029), '01:01:31.787')
        self.assertEqual(human(59.9999), '00:01:00.000')

    def test_active_lock_rejects_generation(self):
        with OwnedDirectory.root(self.directory) as directory, _inspection_lock(directory):
            with self.assertRaises(InspectionFailure):
                generate_manifests(self.config, self.sid)
        self.assertNotIn('manifest_generation', self.record())

    def test_legacy_metadata_without_registry_does_not_reprocess_audio(self):
        record = self.record()
        record['schema_version'] = 1
        record.pop('artifact_registry')
        (self.directory / 'session.json').write_text(json.dumps(record))
        audio = self.audio_bytes()
        generate_manifests(self.config, self.sid)
        self.assertEqual(self.audio_bytes(), audio)
        self.assertEqual(session_status(self.config, self.sid)['current_state'], 'manifested')

    def test_controlled_child_death_after_publication(self):
        ready = self.base / 'manifest-ready'
        code = '''
import sys, time
from pathlib import Path
from recorandro.config import Config
from recorandro.manifests import generate_manifests
from recorandro.storage import OwnedDirectory
publish = OwnedDirectory.publish
def pause(self, temporary, final, destination=None):
    publish(self, temporary, final, destination)
    if final == 'manifest.json':
        Path(sys.argv[3]).write_text('ready')
        while True: time.sleep(0.1)
OwnedDirectory.publish = pause
generate_manifests(Config(Path(sys.argv[1])), sys.argv[2])
'''
        child = subprocess.Popen([sys.executable, '-c', code, str(self.config.data_root), self.sid, str(ready)],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 30
            while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(ready.exists(), child.poll())
            child.kill()
            child.communicate(timeout=10)
            self.assertEqual(session_status(self.config, self.sid)['current_state'], 'segments_exported')
            self.assertEqual(recover_session(self.config, self.sid)['current_state'], 'packaged')
            self.assertEqual(self.original.read_bytes(), self.contents)
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=10)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'actual tools required')
class RealManifestTests(unittest.TestCase):
    def test_applied_and_skipped_actual_single_part(self):
        for mode in ('auto', 'off'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                config = Config(base / 'data')
                source = base / 'small.wav'
                make_wav(source, seconds=3)
                with patch.object(OwnedDirectory, 'free_bytes', return_value=10**12):
                    imported = import_audio(config, source, provision_seconds=3)
                    sid = imported['session_id']
                    inspect_session(config, sid)
                    normalize_session(config, sid, mode=mode)
                    plan_session(config, sid)
                    exported = export_session(config, sid)
                directory = config.data_root / 'sessions' / sid
                before = {p['managed_path']: (directory / p['managed_path']).read_bytes() for p in exported['parts']}
                result = generate_manifests(config, sid)
                journal = json.loads((directory / result['record_path']).read_bytes())
                model = json.loads((directory / journal['files']['manifest.json']['relative_path']).read_bytes())
                self.assertEqual(model['normalization']['result'], 'applied' if mode == 'auto' else 'skipped')
                self.assertEqual(model['segmentation']['part_count'], 1)
                self.assertEqual(model['parts'][0]['overlap_after_seconds'], 0)
                self.assertEqual(model['probe']['container'], 'wav')
                self.assertEqual({p: (directory / p).read_bytes() for p in before}, before)
