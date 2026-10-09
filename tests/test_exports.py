"""Frozen export geometry, publication/retry faults and actual host media checks."""

from array import array
import contextlib
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
import wave

from recorandro.cli import main
from recorandro.exports import (ExportFailure, copy_suffix, coverage, export_ranges,
                               export_session, storage_budget, verify_part)
from recorandro.inspection import inspect_session
from recorandro.normalization import normalize_session
from recorandro.segmentation import plan_boundaries, plan_session
from recorandro.sessions import import_audio
from recorandro.storage import OwnedDirectory
from test_normalization import make_wav, output_media
from test_segmentation import SessionFixture


class GeometryTests(unittest.TestCase):
    def test_fractional_quiet_boundary_keeps_exact_logical_overlap(self):
        boundary = 1023.9999999999999
        plan = plan_boundaries(1700, mode='force', quiet_regions=[{
            'start_seconds': 1023.4999999999998, 'end_seconds': 1024.5}])
        parts = export_ranges(plan)
        self.assertEqual(parts[0]['nominal_end_seconds'], boundary)
        self.assertEqual(parts[0]['overlap_after_seconds'], 5)
        self.assertEqual(parts[1]['overlap_before_seconds'], 5)
        self.assertTrue(coverage(parts, 1700)['overlap_verified'])

    def test_61_minute_ranges_first_last_overlap_and_no_gap(self):
        parts = export_ranges(plan_boundaries(3660))
        self.assertEqual([(p['global_start_seconds'], p['global_end_seconds']) for p in parts],
                         [(0, 1505), (1500, 3005), (3000, 3660)])
        self.assertEqual([p['requested_duration_seconds'] for p in parts], [1505, 1505, 660])
        self.assertEqual([p['overlap_before_seconds'] for p in parts], [0, 5, 5])
        self.assertEqual([p['overlap_after_seconds'] for p in parts], [5, 5, 0])
        self.assertTrue(coverage(parts, 3660)['no_gaps'])

    def test_53_minute_tiny_tail_adjustment_preserved(self):
        parts = export_ranges(plan_boundaries(3180))
        self.assertEqual([(p['nominal_start_seconds'], p['nominal_end_seconds']) for p in parts], [(0, 1560), (1560, 3180)])
        self.assertEqual([(p['global_start_seconds'], p['global_end_seconds']) for p in parts], [(0, 1565), (1560, 3180)])
        self.assertTrue(coverage(parts, 3180)['source_end_covered'])

    def test_single_off_short_and_long_no_overlap_beyond_end(self):
        for duration in (0.02, 8, 300, 3660):
            parts = export_ranges(plan_boundaries(duration, mode='off'))
            self.assertEqual(parts[0]['global_start_seconds'], 0)
            self.assertEqual(parts[0]['global_end_seconds'], duration)
            self.assertEqual(parts[0]['overlap_before_seconds'], 0)
            self.assertEqual(parts[0]['overlap_after_seconds'], 0)

    def test_invalid_plan_endpoint_gap_index_duration_refused(self):
        baseline = plan_boundaries(3660)
        for mutation in (lambda p: p['nominal_parts'][1].update(global_start_seconds=1501),
                         lambda p: p['nominal_parts'][-1].update(global_end_seconds=3659),
                         lambda p: p.update(timeline_start_seconds=1),
                         lambda p: p['nominal_parts'][0].update(part_index=True),
                         lambda p: p['nominal_parts'].__setitem__(0, None),
                         lambda p: p['boundaries'].__setitem__(0, None),
                         lambda p: p['boundaries'][0].update(boundary_index=True),
                         lambda p: p.update(mode_fulfilled=False),
                         lambda p: p.update(plan_kind='single'),
                         lambda p: p.update(silence_removed=True)):
            plan = copy.deepcopy(baseline)
            mutation(plan)
            with self.assertRaises(ExportFailure):
                export_ranges(plan)
        single = plan_boundaries(8)
        single['expected_part_count'] = True
        with self.assertRaises(ExportFailure):
            export_ranges(single)
        for field in ('global_start_seconds', 'global_end_seconds', 'overlap_after_seconds'):
            parts = export_ranges(baseline)
            parts[0][field] += 1
            with self.assertRaises(ExportFailure):
                coverage(parts, 3660)

    def test_copy_exception_exact_suffix_codec_full_single_stream(self):
        for suffix, codec, expected in (('.m4a', 'aac', '.m4a'), ('.mp3', 'mp3', '.mp3'),
                                         ('.wav', 'pcm_s16le', None), ('.aac', 'aac', None),
                                         ('.m4a', 'mp3', None)):
            source = {'managed_path': 'originals/audio/source'+suffix,
                      'media': {'audio_codec': codec, 'stream_count': 1}}
            self.assertEqual(copy_suffix(source, 1), expected)
            self.assertIsNone(copy_suffix(source, 2))
            source['media']['stream_count'] = 2
            self.assertIsNone(copy_suffix(source, 1))

    def test_fixed_duration_start_format_and_copy_tolerances(self):
        from test_normalization import source_probe
        from recorandro.inspection import parse_probe
        source = parse_probe(json.dumps(source_probe(rate=44100, duration=1505)).encode(), '.wav')
        media = output_media(source)
        part = {'requested_duration_seconds': 1505}
        self.assertEqual(verify_part(media, source, part, 'decode_sample_trim_aac')['tolerance_seconds'], 0.05)
        for change in ({'duration_seconds': 1506}, {'stream_start_seconds': 0.051}, {'audio_codec': 'mp3'},
                       {'sample_rate': 48000}, {'channels': 2}, {'codec_profile': 'HE-AAC'}, {'stream_count': 2}):
            broken = dict(media, **change)
            with self.assertRaises((ExportFailure, ValueError)):
                verify_part(broken, source, part, 'decode_sample_trim_aac')
        self.assertEqual(verify_part(source, source, part, 'byte_copy')['tolerance_seconds'], 0)
        with self.assertRaises(ExportFailure):
            verify_part(dict(source, duration_seconds=1505.000001), source, part, 'byte_copy')

    def test_storage_estimates_overlap_remaining_writes_not_import_reservation(self):
        parts = export_ranges(plan_boundaries(3660))
        budget = storage_budget(parts, 'decode_sample_trim_aac', 44941318, 0)
        self.assertEqual(budget['decision'], 'deny')
        self.assertEqual(budget['remaining_audio_bytes'], 30000*(1505+1505+660)+65536*3)
        self.assertFalse(budget['reservation'])
        self.assertEqual(storage_budget(parts[:1], 'byte_copy', 44941318, 10**12)['remaining_audio_bytes'], 44941318)


class ExportFixture(SessionFixture):
    def setUp(self):
        super().setUp()
        self.make_plan()
        self.commands = []

    def make_plan(self, mode='auto'):
        with patch('recorandro.normalization.run_probe', return_value=self.payload), \
                patch('recorandro.segmentation.detect_quiet_regions', return_value=[]):
            self.analysis = plan_session(self.config, self.sid, mode=mode)
        self.ranges = export_ranges(self.analysis['plan'])

    def fake_execute(self, args, timeout, phase, **kwargs):
        self.commands.append((args, timeout, phase, kwargs))
        if phase == 'part_encode':
            Path(args[-1]).write_bytes(('encoded '+Path(args[-1]).name).encode())
        return ''

    def fake_probe(self, config, stream, folder, leaf):
        index = int(re.search(r'part_(\d+)', leaf)[1]) - 1
        media = output_media(self.normalization['input']['media'])
        media['duration_seconds'] = self.ranges[index]['requested_duration_seconds']
        media['duration_consistency']['disagreements'] = []
        return media

    def mocked_export(self, **kwargs):
        with patch('recorandro.normalization.run_probe', return_value=self.payload), \
                patch('recorandro.exports._probe_part', side_effect=self.fake_probe), \
                patch('recorandro.exports._execute', side_effect=self.fake_execute), \
                patch('recorandro.exports._executable', return_value='ffmpeg'), \
                patch.object(OwnedDirectory, 'free_bytes', return_value=10**12):
            return export_session(self.config, self.sid, **kwargs)


class SessionTests(ExportFixture):
    def test_multi_part_success_hashes_metadata_and_original_unchanged(self):
        before = self.record()
        self.external.unlink()
        result = self.mocked_export()
        self.assertTrue(result['success'])
        self.assertEqual(result['status'], 'export_succeeded')
        self.assertEqual(result['part_count'], 3)
        self.assertEqual([p['filename'] for p in result['parts']], ['part_01.m4a','part_02.m4a','part_03.m4a'])
        self.assertTrue(result['coverage']['no_gaps'] and result['coverage']['source_end_covered'])
        for part in result['parts']:
            path = self.directory / part['managed_path']
            self.assertEqual(path.stat().st_size, part['size_bytes'])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), part['sha256'])
            self.assertTrue(part['verification']['full_decode_passed'])
        self.assertEqual(self.original.read_bytes(), self.contents)
        for key in ('audio', 'inspection', 'normalization', 'segmentation', 'state', 'visual_count'):
            self.assertEqual(self.record()[key], before[key])
        pointer = self.record()['audio_export']
        path = self.directory / pointer['record_path']
        self.assertEqual(json.loads(path.read_text()), result)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), pointer['record_sha256'])
        self.assertEqual(pointer['verified_part_count'], 3)
        self.assertEqual(list(self.directory.glob('temp/export-*/pending-*')), [])

    def test_sample_trim_explicit_stream_encoding_and_full_decode_args(self):
        with patch('recorandro.segmentation.plan_session') as replan, \
                patch('recorandro.normalization.normalize_session') as normalize:
            result = self.mocked_export()
        encode = [c for c in self.commands if c[2] == 'part_encode']
        self.assertEqual(len(encode), 3)
        for args, timeout, phase, kwargs in encode:
            for option, expected in (('-c:a','aac'),('-profile:a','aac_low'),('-b:a','128000'),('-ar','16000'),
                                      ('-f','ipod'),('-movflags','+faststart'),('-map','0:0'),
                                      ('-map_metadata','-1'),('-map_chapters','-1')):
                self.assertEqual(args[args.index(option)+1], expected)
            self.assertEqual(timeout, 7380)
            self.assertTrue(all(flag in args for flag in ('-n','-nostdin','-xerror','-vn','-sn','-dn')))
            self.assertFalse(any(flag in args for flag in ('-ss','-t','-ac','-q:a')))
            self.assertNotIn('volume', ' '.join(args))
            self.assertNotIn('loudnorm', ' '.join(args))
        self.assertEqual(encode[1][0][encode[1][0].index('-af')+1],
                         'atrim=start_sample=24000000:end_sample=48080000,asetpts=PTS-STARTPTS')
        self.assertEqual(len([c for c in self.commands if c[2] == 'part_decode']), 3)
        replan.assert_not_called()
        normalize.assert_not_called()

    def test_wav_single_part_still_independent_canonical_encode(self):
        self.configure_duration(8)
        self.make_plan()
        result = self.mocked_export()
        self.assertEqual(result['parts'][0]['method'], 'decode_sample_trim_aac')
        self.assertEqual(result['parts'][0]['requested_duration_seconds'], 8)
        self.assertEqual(result['parts'][0]['overlap_after_seconds'], 0)
        self.assertNotEqual(result['parts'][0]['sha256'], self.imported['audio']['sha256'])

    def test_53_minute_approved_adjusted_ranges_exported_exactly(self):
        self.configure_duration(3180)
        self.make_plan()
        result = self.mocked_export()
        self.assertEqual([(p['global_start_seconds'],p['global_end_seconds']) for p in result['parts']], [(0,1565),(1560,3180)])
        self.assertTrue(result['coverage']['verified'])

    def test_latest_pending_failed_or_missing_plan_refused(self):
        baseline = self.record()
        for value in (None, {}, dict(baseline['segmentation'], status='planning_pending'),
                      dict(baseline['segmentation'], status='planning_failed')):
            record = copy.deepcopy(baseline)
            record['segmentation'] = value
            record.pop('audio_export', None)
            self.write_record(record)
            with self.assertRaises(ExportFailure):
                self.mocked_export(retry=True)
        self.assertNotIn('part_encode', [c[2] for c in self.commands])

    def test_saved_plan_hash_changed_and_inconsistent_plan_rejected(self):
        pointer = self.record()['segmentation']
        path = self.directory / pointer['record_path']
        original = path.read_bytes()
        path.write_bytes(original+b' ')
        with self.assertRaises(ExportFailure) as exc:
            self.mocked_export()
        self.assertEqual(exc.exception.code, 'plan_hash_mismatch')
        value = json.loads(original)
        value['plan']['nominal_parts'][1]['global_start_seconds'] += 1
        path.write_text(json.dumps(value))
        record = self.record()
        record['segmentation']['record_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.write_record(record)
        with self.assertRaises(ExportFailure):
            self.mocked_export(retry=True)
        self.assertEqual(self.original.read_bytes(), self.contents)

    def test_current_normalization_revision_not_silently_reused(self):
        self.configure_duration(3660)  # New valid revision; approved plan points to old one.
        with self.assertRaises(ExportFailure) as exc:
            self.mocked_export()
        self.assertEqual(exc.exception.code, 'stale_plan_source')
        self.assertEqual(len(self.commands), 0)

    def test_source_hash_mismatch_before_export_fails_closed(self):
        self.original.chmod(0o600)
        self.original.write_bytes(b'x' * len(self.contents))
        with self.assertRaises(ExportFailure) as exc:
            self.mocked_export()
        self.assertFalse(exc.exception.attempt['success'])
        self.assertEqual(exc.exception.attempt['integrity']['original_after']['status'], 'failed')
        self.assertEqual(self.commands, [])
        self.assertEqual(list(self.directory.glob('generated/exports/*/part_*')), [])

    def test_tool_missing_timeout_and_interrupt_recheck_original(self):
        from recorandro.normalization import NormalizationFailure
        with patch('recorandro.normalization.run_probe', return_value=self.payload), \
                patch('recorandro.exports._executable', side_effect=NormalizationFailure(
                    'ffmpeg_missing', 'Configured ffmpeg unavailable.')), self.assertRaises(ExportFailure) as missing:
            export_session(self.config, self.sid)
        self.assertEqual(missing.exception.code, 'ffmpeg_missing')
        self.assertEqual(missing.exception.attempt['integrity']['original_after']['status'], 'verified')
        for failure in (NormalizationFailure('tool_timeout', 'Controlled pass timeout.'), KeyboardInterrupt()):
            with patch.object(self, 'fake_execute', side_effect=failure), self.assertRaises(ExportFailure) as exc:
                self.mocked_export(retry=True)
            self.assertFalse(exc.exception.attempt['success'])
            self.assertEqual(exc.exception.attempt['integrity']['original_after']['status'], 'verified')
            self.assertEqual(exc.exception.attempt['integrity']['source_after']['status'], 'verified')
            self.assertEqual(list(self.directory.glob('temp/export-*/pending-*')), [])
            self.assertEqual(list(self.directory.glob('generated/exports/*/part_*')), [])

    def test_plan_changed_during_export_preserves_parts_without_completing(self):
        path = self.directory / self.record()['segmentation']['record_path']
        def changed(args, timeout, phase, **kwargs):
            out = ExportFixture.fake_execute(self, args, timeout, phase, **kwargs)
            if phase == 'part_encode' and 'part_01' in str(args[-1]):
                path.write_bytes(path.read_bytes() + b' ')
            return out
        with patch.object(self, 'fake_execute', side_effect=changed), self.assertRaises(ExportFailure) as exc:
            self.mocked_export()
        self.assertEqual(exc.exception.code, 'plan_changed')
        self.assertIsNone(exc.exception.attempt['coverage'])
        self.assertFalse(self.record()['audio_export']['success'])
        self.assertEqual(len(list(self.directory.glob('generated/exports/*/part_*'))), 3)
        self.assertEqual(self.original.read_bytes(), self.contents)

    def test_empty_rounded_sample_range_is_not_encoded(self):
        self.configure_duration(0.000001)
        self.make_plan()
        with self.assertRaises(ExportFailure) as exc:
            self.mocked_export()
        self.assertEqual(exc.exception.code, 'empty_sample_range')
        self.assertEqual(self.commands, [])
        self.assertEqual(exc.exception.attempt['integrity']['original_after']['status'], 'verified')

    def test_ffmpeg_failure_preserves_partial_verified_part_and_retry(self):
        def broken(args, timeout, phase, **kwargs):
            out = ExportFixture.fake_execute(self, args, timeout, phase, **kwargs)
            if phase == 'part_encode' and 'part_02' in str(args[-1]):
                raise ExportFailure('tool_nonzero_exit','Controlled encoding failure')
            return out
        with patch.object(self,'fake_execute',side_effect=broken), self.assertRaises(ExportFailure) as error:
            self.mocked_export()
        failed = error.exception.attempt
        first = self.directory / failed['parts'][0]['managed_path']
        first_bytes, first_inode = first.read_bytes(), first.stat().st_ino
        self.assertFalse(failed['success'])
        self.assertIsNone(failed['coverage'])
        self.assertEqual(failed['parts'][1]['status'],'failed')
        self.assertEqual(list(self.directory.glob('temp/export-*/pending-*')),[])
        with self.assertRaises(ExportFailure):
            self.mocked_export()
        self.commands.clear()
        complete = self.mocked_export(retry=True)
        self.assertTrue(complete['success'])
        self.assertTrue(complete['parts'][0]['reused'])
        self.assertEqual(complete['parts'][0]['source_end_sample'], failed['parts'][0]['source_end_sample'])
        self.assertEqual(complete['parts'][0]['managed_path'], failed['parts'][0]['managed_path'])
        self.assertEqual(first.read_bytes(),first_bytes)
        self.assertEqual(first.stat().st_ino,first_inode)
        self.assertEqual(len([c for c in self.commands if c[2]=='part_encode']),2)

    def test_successful_rerun_reverifies_without_reencoding(self):
        first = self.mocked_export()
        self.commands.clear()
        second = self.mocked_export()
        self.assertNotEqual(first['attempt_id'],second['attempt_id'])
        self.assertTrue(all(p['reused'] for p in second['parts']))
        self.assertEqual([p['managed_path'] for p in first['parts']], [p['managed_path'] for p in second['parts']])
        self.assertEqual([p['source_start_sample'] for p in first['parts']], [p['source_start_sample'] for p in second['parts']])
        self.assertEqual([c[2] for c in self.commands],['part_decode']*3)

    def test_corrupt_previous_output_new_owned_file_without_overwrite(self):
        first = self.mocked_export()
        file = self.directory / first['parts'][0]['managed_path']
        file.chmod(0o600)
        file.write_bytes(b'corrupt previous output')
        second = self.mocked_export()
        self.assertFalse(second['parts'][0]['reused'])
        self.assertNotEqual(first['parts'][0]['managed_path'],second['parts'][0]['managed_path'])
        self.assertEqual(file.read_bytes(),b'corrupt previous output')

    def test_invalid_output_duration_codec_channel_start_and_decode_failure(self):
        for mutation in ({'duration_seconds':1506}, {'audio_codec':'mp3'}, {'channels':2},
                         {'stream_start_seconds':0.2}, {'codec_profile':'HE-AAC'}):
            def probe(config,stream,folder,leaf):
                return dict(ExportFixture.fake_probe(self,config,stream,folder,leaf),**mutation)
            with patch.object(self,'fake_probe',side_effect=probe), self.assertRaises(ExportFailure):
                self.mocked_export(retry=True)
        def decode_failure(args,timeout,phase,**kwargs):
            out = ExportFixture.fake_execute(self,args,timeout,phase,**kwargs)
            if phase=='part_decode':
                raise ExportFailure('tool_nonzero_exit','Controlled full decode failure')
            return out
        with patch.object(self,'fake_execute',side_effect=decode_failure),self.assertRaises(ExportFailure):
            self.mocked_export(retry=True)
        self.assertEqual(list(self.directory.glob('generated/exports/*/part_*.m4a')),[])

    def test_empty_output_and_source_mutation_failure_paths(self):
        def empty(args,timeout,phase,**kwargs):
            if phase=='part_encode':
                Path(args[-1]).write_bytes(b'')
            return ''
        with patch.object(self,'fake_execute',side_effect=empty),self.assertRaises(ExportFailure):
            self.mocked_export()
        self.original.chmod(0o600)
        def changed(args,timeout,phase,**kwargs):
            result = ExportFixture.fake_execute(self,args,timeout,phase,**kwargs)
            self.original.write_bytes(b'x'*len(self.contents))
            return result
        with patch.object(self,'fake_execute',side_effect=changed),self.assertRaises(ExportFailure) as exc:
            self.mocked_export(retry=True)
        self.assertEqual(exc.exception.attempt['integrity']['original_after']['status'],'failed')
        self.assertFalse(self.record()['audio_export']['success'])

    def test_storage_denial_before_large_output(self):
        with patch('recorandro.exports.storage_budget',return_value={'decision':'deny'}),self.assertRaises(ExportFailure):
            self.mocked_export()
        self.assertEqual(self.commands,[])
        self.assertEqual(self.original.read_bytes(),self.contents)

    def test_publication_collision_preserved(self):
        actual = OwnedDirectory.publish
        def collide(folder,temporary,final,destination=None):
            (destination.path/final).write_bytes(b'preexisting final')
            return actual(folder,temporary,final,destination)
        with patch.object(OwnedDirectory,'publish',collide),self.assertRaises(ExportFailure):
            self.mocked_export()
        file = next(self.directory.glob('generated/exports/*/part_01.m4a'))
        self.assertEqual(file.read_bytes(),b'preexisting final')
        self.assertFalse(self.record()['audio_export']['success'])

    def test_metadata_failure_after_publication_never_complete(self):
        actual = OwnedDirectory.atomic_json
        def denied(folder,record):
            if record.get('audio_export',{}).get('status')=='export_succeeded':
                raise OSError('Controlled session publication error')
            return actual(folder,record)
        with patch.object(OwnedDirectory,'atomic_json',denied),self.assertRaises(ExportFailure) as exc:
            self.mocked_export()
        self.assertEqual(exc.exception.code,'metadata_persistence_failed')
        self.assertEqual(self.record()['audio_export']['status'],'export_pending')
        self.assertFalse(self.record()['audio_export']['success'])
        before = list(self.directory.glob('generated/exports/*/part_*.m4a'))
        self.assertEqual(len(before),3)
        self.assertTrue(self.mocked_export(retry=True)['success'])
        self.assertTrue(all(p.exists() for p in before))

    def test_pending_metadata_failure_no_processing(self):
        with patch.object(OwnedDirectory,'atomic_json',side_effect=OSError('controlled')), \
                patch('recorandro.exports._execute') as execute,self.assertRaises(ExportFailure):
            export_session(self.config,self.sid)
        execute.assert_not_called()
        self.assertNotIn('audio_export',self.record())

    def test_managed_plan_path_and_symlink_safety(self):
        record = self.record()
        record['segmentation']['record_path']='../../external.json'
        self.write_record(record)
        with self.assertRaises(ExportFailure):
            self.mocked_export()
        alias = self.base/'alias'
        try:
            os.symlink(self.config.data_root,alias,target_is_directory=True)
        except (OSError,NotImplementedError) as exc:
            self.skipTest(str(exc))
        from recorandro.config import Config
        with self.assertRaises((ExportFailure,OSError,ValueError)):
            export_session(Config(alias),self.sid,retry=True)

    def test_cli_existing_session_retry_machine_json_private_errors(self):
        with patch('recorandro.cli.load_config',return_value=self.config), \
                patch('recorandro.cli.export_session',return_value={'success':True}) as engine, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['export-session',self.sid,'--retry']),0)
        engine.assert_called_once_with(self.config,self.sid,retry=True)
        self.assertTrue(json.loads(output.getvalue())['ok'])
        with patch('recorandro.cli.load_config',return_value=self.config), \
                patch('recorandro.cli.export_session',side_effect=OSError('private directory')), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['export-session',self.sid]),1)
        self.assertNotIn('private directory',output.getvalue())


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'Real host tools unavailable')
class RealExportTests(ExportFixture):
    def prepare_real(self,source,mode='auto',normalization='off'):
        with patch.object(OwnedDirectory,'free_bytes',return_value=10**12):
            session = import_audio(self.config,source,provision_seconds=4000)
        sid = session['session_id']
        inspect_session(self.config,sid)
        normalize_session(self.config,sid,mode=normalization)
        plan_session(self.config,sid,mode=mode)
        return session

    def test_real_wav_encode_and_m4a_mp3_independent_exact_copies(self):
        for suffix in ('.wav','.m4a','.mp3'):
            source = self.base/('real'+suffix)
            if suffix=='.wav':
                make_wav(source)
            else:
                subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-i',str(self.external),
                                '-c:a','aac' if suffix=='.m4a' else 'libmp3lame',str(source)],
                               shell=False,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE,timeout=30,check=True)
            session = self.prepare_real(source)
            source.unlink()
            result = export_session(self.config,session['session_id'])
            part = result['parts'][0]
            folder = self.config.data_root/'sessions'/session['session_id']
            original = folder/session['audio']['managed_path']
            output = folder/part['managed_path']
            self.assertTrue(result['success'] and part['verification']['full_decode_passed'])
            self.assertNotEqual(original.stat().st_ino,output.stat().st_ino)
            self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),session['audio']['sha256'])
            if suffix!='.wav':
                self.assertEqual(part['method'],'byte_copy')
                self.assertEqual(part['sha256'],session['audio']['sha256'])
                self.assertEqual(part['size_bytes'],session['audio']['size_bytes'])
                self.assertEqual(part['verification']['tolerance_seconds'],0)
                self.assertEqual(part['filename'],'part_01'+suffix)
            else:
                self.assertEqual(part['method'],'decode_sample_trim_aac')
                self.assertEqual(part['media']['codec_profile'],'LC')

    def test_real_normalized_source_copy_and_stereo_rate_policy(self):
        source = self.base/'normalized-input.wav'
        make_wav(source,rate=44100,channels=2)
        session = self.prepare_real(source,normalization='auto')
        result = export_session(self.config,session['session_id'])
        self.assertEqual(result['source']['kind'],'normalized')
        self.assertEqual(result['parts'][0]['method'],'byte_copy')
        self.assertEqual(result['parts'][0]['media']['sample_rate'],44100)
        self.assertEqual(result['parts'][0]['media']['channels'],2)
        source = self.base/'rate-12345.wav'
        make_wav(source,rate=12345,channels=2)
        session = self.prepare_real(source)
        result = export_session(self.config,session['session_id'])
        self.assertEqual(result['parts'][0]['media']['sample_rate'],48000)
        self.assertEqual(result['parts'][0]['requested_encoding']['bitrate'],192000)
        self.assertEqual(result['parts'][0]['media']['channels'],2)

    def test_real_two_part_sample_trim_overlap_source_end_and_hashes(self):
        source = self.base/'1200-second.wav'
        rate = 8000
        tone = array('h',[round(3000*math.sin(2*math.pi*440*i/rate)) for i in range(rate)])
        if sys.byteorder!='little':
            tone.byteswap()
        with wave.open(str(source),'wb') as wav:
            wav.setparams((1,2,rate,0,'NONE','not compressed'))
            for second in range(1200):
                wav.writeframesraw(bytes(rate*2) if second==0 or 599<=second<601 or second==1199 else tone.tobytes())
        session = self.prepare_real(source,mode='force')
        source.unlink()
        result = export_session(self.config,session['session_id'])
        self.assertTrue(result['success'])
        self.assertEqual([(p['global_start_seconds'],p['global_end_seconds']) for p in result['parts']],[(0,605),(600,1200)])
        self.assertTrue(result['coverage']['no_gaps'] and result['coverage']['source_end_covered'])
        self.assertEqual(result['coverage']['overlap_seconds'],5)
        for part in result['parts']:
            self.assertLessEqual(abs(part['duration_seconds']-part['requested_duration_seconds']),0.256)
            self.assertTrue(part['verification']['full_decode_passed'])
            self.assertEqual(part['media']['codec_profile'],'LC')
            self.assertEqual(part['media']['sample_rate'],8000)
        self.assertEqual(result['integrity']['original_before'],result['integrity']['original_after'])


if __name__=='__main__':
    unittest.main()
