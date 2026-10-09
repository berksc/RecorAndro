"""Frozen nominal policy, controlled session faults and real read-only detection."""

from array import array
import contextlib
import copy
import hashlib
import io
import itertools
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch
import wave

from recorandro.cli import main
from recorandro.config import Config
from recorandro.inspection import inspect_session
from recorandro.normalization import normalize_session
from recorandro.segmentation import (MAX_LOG_BYTES, QUIET_FILTER, PlanningFailure,
                                    _run_detection, detect_quiet_regions, parse_quiet_regions,
                                    part_count, plan_boundaries, plan_session, validate_plan)
from recorandro.storage import OwnedDirectory
from recorandro.sessions import import_audio
from test_normalization import make_wav, source_probe, output_media


def quiet(start, end):
    return {"start_seconds": start, "end_seconds": end}


def events(*items):
    return [f"[silencedetect @ 0xabc] silence_{kind}: {timestamp}\n" for kind, timestamp in items]


class PlannerTests(unittest.TestCase):
    def lengths(self, duration, mode="auto", regions=None):
        return [p["duration_seconds"] for p in plan_boundaries(duration, regions, mode=mode)["nominal_parts"]]

    def test_short_and_just_below_exact_auto_cutoff(self):
        for duration in (0.000001, 0.02, 300, 1499.9, 1500, 1500.1, 1560, 1619.999999, 1620):
            self.assertEqual(self.lengths(duration), [duration])

    def test_just_above_cutoff_balances_without_tiny_tail(self):
        plan = plan_boundaries(1620.1)
        self.assertEqual(self.lengths(1620.1), [810.05, 810.05])
        self.assertEqual(plan["boundaries"][0]["reason"], "fallback_redistributed_balance")
        self.assertFalse(plan["audio_split"] or plan["audio_exported"])

    def test_force_too_short_valid_unfulfilled_plan_and_exact_feasibility(self):
        for duration in (0.02, 300, 1199.999999):
            plan = plan_boundaries(duration, mode="force")
            self.assertFalse(plan["mode_fulfilled"])
            self.assertEqual(plan["decision"], "force_not_feasible_minimum_duration")
            self.assertEqual(plan["requested_minimum_count"], 2)
            self.assertEqual(plan["expected_part_count"], 1)
        self.assertEqual(self.lengths(1200, "force"), [600, 600])
        self.assertEqual(self.lengths(1560, "force"), [780, 780])
        self.assertEqual(self.lengths(1620, "force"), [810, 810])

    def test_off_all_durations_one_complete_nominal_range(self):
        for duration in (0.02, 300, 1620.1, 3180, 5400):
            self.assertEqual(self.lengths(duration, "off"), [duration])

    def test_all_frozen_fallback_examples_and_counts(self):
        examples = {1800: [1200, 600], 2940: [1500, 1440], 3060: [1500, 1560],
                    3180: [1560, 1620], 3300: [1500, 1200, 600], 3660: [1500, 1500, 660],
                    4440: [1500, 1500, 1440], 4560: [1500, 1500, 1560],
                    4800: [1560, 1620, 1620], 5400: [1500, 1500, 1500, 900],
                    5437: [1500, 1500, 1500, 937]}
        for duration, expected in examples.items():
            with self.subTest(duration=duration):
                self.assertEqual(self.lengths(duration), expected)
                self.assertEqual(self.lengths(duration, "force"), expected)
                self.assertEqual(part_count(duration), math.ceil(duration / 1620))

    def test_51_52_53_minute_tiny_tail_regression(self):
        self.assertEqual(self.lengths(3120), [1500, 1620])
        for duration in (3060, 3120, 3180):
            self.assertEqual(part_count(duration), 2)
            self.assertTrue(all(600 <= d <= 1620 for d in self.lengths(duration)))

    def test_80_minute_reserves_every_remaining_part(self):
        plan = plan_boundaries(4800, [quiet(1499, 1501)])
        self.assertEqual(plan["boundaries"][0]["feasible_interval_seconds"], [1560, 1620])
        self.assertEqual(plan["boundaries"][0]["global_timestamp_seconds"], 1560)
        self.assertEqual(plan["boundaries"][1]["global_timestamp_seconds"], 3180)
        self.assertEqual(plan["expected_part_count"], 3)

    def test_single_point_normal_window_and_no_tiny_parts(self):
        plan = plan_boundaries(1800, [quiet(1199, 1201)])
        boundary = plan["boundaries"][0]
        self.assertEqual(boundary["search_interval_seconds"], [1200, 1200])
        self.assertEqual(boundary["reason"], "quiet_region")
        self.assertEqual(self.lengths(1800), [1200, 600])

    def test_ranking_nearest_then_full_length_then_earliest(self):
        regions = [quiet(1496, 1498), quiet(1502, 1504), quiet(1495, 1499)]
        for ordering in itertools.permutations(regions):
            boundary = plan_boundaries(3660, list(ordering))["boundaries"][0]
            self.assertEqual(boundary["global_timestamp_seconds"], 1497)
            self.assertEqual(boundary["quiet_interval"]["start_seconds"], 1495)
        nearest = plan_boundaries(3660, regions + [quiet(1499.5, 1500.5)])["boundaries"][0]
        self.assertEqual(nearest["global_timestamp_seconds"], 1500)

    def test_full_interval_length_ranks_intersection_candidate(self):
        # Both candidates at 1500, but full 900..2100 interval wins duration.
        b = plan_boundaries(2100, [quiet(1499, 1501), quiet(900, 2100)])["boundaries"][0]
        self.assertEqual(b["quiet_interval"]["start_seconds"], 900)

    def test_long_quiet_uses_intersection_midpoint(self):
        b = plan_boundaries(3660, [quiet(0, 3660)])["boundaries"][0]
        self.assertEqual(b["global_timestamp_seconds"], 1410)
        self.assertEqual(b["quiet_interval"]["candidate_method"], "intersection_midpoint")

    def test_quiet_redistribution_prefers_quiet_inside_feasible_window(self):
        b = plan_boundaries(1620.1, [quiet(805, 809), quiet(1499, 1501)])["boundaries"][0]
        self.assertEqual(b["global_timestamp_seconds"], 807)
        self.assertEqual(b["search_kind"], "redistribution")

    def test_actual_chosen_boundary_defines_next_ideal(self):
        plan = plan_boundaries(3660, [quiet(1458, 1462), quiet(2958, 2962)])
        self.assertEqual([b["global_timestamp_seconds"] for b in plan["boundaries"]], [1460, 2960])
        self.assertEqual(plan["boundaries"][1]["ideal_seconds"], 2960)

    def test_minimum_full_and_intersection_comparison_allowance(self):
        b = plan_boundaries(3660, [quiet(1499.5, 1500.499995)])["boundaries"][0]
        self.assertEqual(b["reason"], "quiet_region")
        plan = plan_boundaries(3660, [quiet(1499.5, 1500.49998)])
        self.assertEqual(plan["boundaries"][0]["reason"], "fallback_target")
        # Full midpoint outside window, only ~1 s of intersection qualifies.
        b = plan_boundaries(3660, [quiet(0, 1200.999995)])["boundaries"][0]
        self.assertEqual(b["reason"], "quiet_region")

    def test_invalid_duration_mode_regions_and_part_limit(self):
        for duration in (True, 0, -1, float("nan"), float("inf"), "3660", 0.0000009):
            with self.assertRaises(PlanningFailure):
                plan_boundaries(duration)
        with self.assertRaises(PlanningFailure):
            plan_boundaries(1620 * 10000 + 0.1)
        self.assertEqual(part_count(1620 * 10000), 10000)
        for regions in ([quiet(-1, 2)], [quiet(2, 1)], [quiet(1, 3661)], [quiet(True, 2)],
                        [quiet(1, 10**400)], "bad"):
            with self.assertRaises(PlanningFailure):
                plan_boundaries(3660, regions)
        with self.assertRaises(PlanningFailure):
            plan_boundaries(300, mode="unknown")

    def test_dense_candidates_order_independent_and_count_fixed(self):
        regions = [quiet(t, t + 1.1) for t in range(1, 4700, 2)]
        expected = plan_boundaries(4800, regions)
        random.Random(7).shuffle(regions)
        self.assertEqual(plan_boundaries(4800, regions), expected)
        self.assertEqual(expected["expected_part_count"], 3)

    def test_coverage_and_useful_bounds_across_duration_grid(self):
        for duration in (d + 0.001 for d in range(1, 6000, 17)):
            for mode in ("auto", "force", "off"):
                p = plan_boundaries(duration, mode=mode)
                validate_plan(p)
                self.assertEqual(p["nominal_parts"][0]["global_start_seconds"], 0)
                self.assertEqual(p["nominal_parts"][-1]["global_end_seconds"], duration)
                self.assertTrue(p["source_end_covered"])

    def test_plan_validator_rejects_gaps_missing_end_and_tiny_part(self):
        base = plan_boundaries(3180)
        for mutation in (lambda p: p["nominal_parts"][1].update(global_start_seconds=1561),
                         lambda p: p["nominal_parts"][-1].update(global_end_seconds=3179),
                         lambda p: p.update(expected_part_count=3),
                         lambda p: p.update(silence_removed=True)):
            p = copy.deepcopy(base)
            mutation(p)
            with self.assertRaises(PlanningFailure):
                validate_plan(p)


class ParserTests(unittest.TestCase):
    def parse(self, items, duration=10, rate=44100):
        return parse_quiet_regions(events(*items), duration, rate)

    def test_leading_middle_and_open_trailing_quiet(self):
        self.assertEqual(self.parse([("start", 0), ("end", 2), ("start", 4), ("end", 5), ("start", 8)]),
                         [quiet(0, 2), quiet(4, 5), quiet(8, 10)])

    def test_endpoint_tolerance_clamps_only_within_allowance(self):
        self.assertEqual(self.parse([("start", -0.05), ("end", 10.05)]), [quiet(0, 10)])
        for timestamp in (-0.05001, 10.05001, "NaN", "inf"):
            with self.assertRaises(PlanningFailure):
                self.parse([("start", timestamp)])
        self.assertEqual(self.parse([("start", -0.25), ("end", 10.25)], rate=8000), [quiet(0, 10)])

    def test_unmatched_duplicate_and_unordered_events_fail(self):
        for items in ([('end', 2)], [('start', 1), ('start', 2)], [('start', 2), ('end', 1)],
                      [('start', 1), ('end', 3), ('start', 2)], [('start', 1), ('end', 1)]):
            with self.assertRaises(PlanningFailure):
                self.parse(items)
        with self.assertRaises(PlanningFailure):
            parse_quiet_regions(['[silencedetect @ x] silence_end:\n'], 10, 44100)

    def test_minimum_and_retained_interval_bound_includes_trailing(self):
        self.assertEqual(self.parse([('start', 1), ('end', 1.999995)]), [quiet(1, 1.999995)])
        self.assertEqual(self.parse([('start', 1), ('end', 1.99998)]), [])
        with patch('recorandro.segmentation.MAX_REGIONS', 1), self.assertRaises(PlanningFailure):
            self.parse([('start', 0), ('end', 1), ('start', 8)])

    def test_multiple_events_on_one_line_and_complete_log(self):
        lines = events(('start', 0), ('end', 1)) + ['unrelated private diagnostic\n'] * 20000 + events(('start', 8))
        self.assertEqual(parse_quiet_regions(lines, 10, 44100), [quiet(0, 1), quiet(8, 10)])
        self.assertEqual(parse_quiet_regions([' '.join(events(('start', 1), ('end', 3)))], 10, 44100), [quiet(1, 3)])


class RunnerTests(unittest.TestCase):
    def run_tool(self, script, **kwargs):
        with tempfile.TemporaryFile() as log:
            _run_detection([sys.executable, '-c', script], 5, log, **kwargs)
            return log.read()

    def test_complete_spool_larger_than_tail(self):
        text = self.run_tool("import sys; sys.stderr.write('a'*70000+'END')")
        self.assertEqual(len(text), 70003)
        self.assertTrue(text.endswith(b'END'))

    def test_bounded_spool_nonzero_and_missing_tool(self):
        with patch('recorandro.segmentation.MAX_LOG_BYTES', 1000), self.assertRaises(PlanningFailure):
            self.run_tool("import sys; sys.stderr.write('x'*50000)")
        with self.assertRaises(PlanningFailure):
            self.run_tool("raise SystemExit(3)")
        with tempfile.TemporaryFile() as log, self.assertRaises(PlanningFailure):
            _run_detection(['nonexistent-recorandro-media-tool'], 5, log)

    def test_timeout_and_interrupt_kill_reap(self):
        actual = subprocess.Popen
        for injected in (subprocess.TimeoutExpired('controlled', 5), KeyboardInterrupt()):
            seen = []
            def start(*args, **kwargs):
                p = actual(*args, **kwargs)
                wait = p.wait
                calls = []
                def controlled(*a, **kw):
                    if not calls:
                        calls.append(True)
                        raise injected
                    return wait(*a, **kw)
                p.wait = controlled
                seen.append(p)
                return p
            with patch('recorandro.segmentation.subprocess.Popen', side_effect=start), \
                    self.assertRaises((PlanningFailure, KeyboardInterrupt)):
                self.run_tool("import time; time.sleep(20)")
            self.assertIsNotNone(seen[0].poll())

    def test_reader_start_failure_stops_process(self):
        with patch('recorandro.segmentation.threading.Thread.start', side_effect=RuntimeError('controlled')), \
                self.assertRaises(PlanningFailure):
            self.run_tool("import time; time.sleep(20)")


class SessionFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = Config(self.base / 'data')
        self.external = self.base / 'source.wav'
        make_wav(self.external)
        with patch.object(OwnedDirectory, 'free_bytes', return_value=10**12):
            self.imported = import_audio(self.config, self.external, provision_seconds=4000)
        self.sid = self.imported['session_id']
        self.directory = self.config.data_root / 'sessions' / self.sid
        self.original = self.directory / self.imported['audio']['managed_path']
        self.contents = self.original.read_bytes()
        self.configure_duration(3660)

    def configure_duration(self, duration):
        # Byte integrity is real; fictitious long duration/decoder facts are mocked.
        self.payload = json.dumps(source_probe(duration=duration)).encode()
        with patch('recorandro.inspection.run_probe', return_value=self.payload):
            inspect_session(self.config, self.sid)
        with patch('recorandro.normalization.run_probe', return_value=self.payload), \
                patch('recorandro.normalization._execute', return_value=''), \
                patch('recorandro.normalization._executable', return_value='ffmpeg'):
            self.normalization = normalize_session(self.config, self.sid, mode='off')

    def record(self):
        return json.loads((self.directory / 'session.json').read_text())

    def write_record(self, record):
        with OwnedDirectory.root(self.directory) as directory:
            directory.atomic_json(record)

    def mocked(self, *, regions=None, **kwargs):
        with patch('recorandro.normalization.run_probe', return_value=self.payload), \
                patch('recorandro.segmentation.detect_quiet_regions', return_value=regions or []) as detector:
            result = plan_session(self.config, self.sid, **kwargs)
        return result, detector


class SessionTests(SessionFixture):
    def test_managed_original_after_off_and_external_deleted(self):
        self.external.unlink()
        before = self.record()
        result, detector = self.mocked()
        self.assertEqual(result['status'], 'planned')
        self.assertEqual(result['source']['kind'], 'original')
        self.assertEqual(result['plan']['expected_part_count'], 3)
        detector.assert_called_once()
        after = self.record()
        for key in ('audio', 'inspection', 'normalization', 'state', 'visual_count'):
            self.assertEqual(after[key], before[key])
        self.assertEqual(after['state'], 'imported')
        self.assertEqual(after['visual_count'], 0)
        self.assertEqual(self.original.read_bytes(), self.contents)
        self.assertEqual(result['integrity']['source_before'], result['integrity']['source_after'])
        history = self.directory / after['segmentation']['record_path']
        self.assertEqual(hashlib.sha256(history.read_bytes()).hexdigest(), after['segmentation']['record_sha256'])
        self.assertEqual(json.loads(history.read_text()), result)
        self.assertEqual(list(self.directory.glob('generated/segmentation/**/*.m4a')), [])

    def test_short_auto_force_infeasible_and_off_do_not_analyze_quiet(self):
        for duration, mode in ((300, 'auto'), (300, 'force'), (1620, 'auto'), (3660, 'off')):
            self.configure_duration(duration)
            result, detector = self.mocked(mode=mode)
            detector.assert_not_called()
            self.assertFalse(result['quiet_analysis']['performed'])
            self.assertEqual(result['plan']['expected_part_count'], 1)

    def test_modes_independent_no_normalization_or_encoding_invoked(self):
        self.configure_duration(1560)
        with patch('recorandro.normalization.normalize_session') as normalize, \
                patch('recorandro.normalization._execute') as encoding:
            auto, _ = self.mocked()
            force, _ = self.mocked(mode='force')
        self.assertEqual(auto['plan']['expected_part_count'], 1)
        self.assertEqual(force['plan']['expected_part_count'], 2)
        self.assertEqual(force['source']['normalization_attempt_id'], self.normalization['attempt_id'])
        normalize.assert_not_called()
        encoding.assert_not_called()

    def test_current_normalization_required_never_falls_back(self):
        baseline = self.record()
        for value in (None, {}, dict(self.normalization, status='normalization_pending'),
                      dict(self.normalization, status='normalization_failed')):
            record = copy.deepcopy(baseline)
            record['normalization'] = value
            record.pop('segmentation', None)
            self.write_record(record)
            with self.assertRaises(PlanningFailure):
                self.mocked(retry=True)

    def test_selected_normalized_source_and_its_working_duration(self):
        record = self.record()
        n = record['normalization']
        derived = self.directory / 'generated' / 'normalization' / n['attempt_id'] / 'normalized.m4a'
        derived.write_bytes(b'independently verified mock derivative')
        media = output_media(n['input']['media'])
        media['duration_seconds'] += 0.02
        media['duration_estimates_seconds'] = dict.fromkeys(('stream', 'stream_time_base', 'container'), media['duration_seconds'])
        source = {'managed_path': str(derived.relative_to(self.directory)).replace('\\', '/'),
                  'size_bytes': derived.stat().st_size, 'sha256': hashlib.sha256(derived.read_bytes()).hexdigest(),
                  'media': media, 'full_decode_verified': True}
        n.update(output_source='normalized', output=source, working_source=source,
                 normalization_applied=True, encoding_applied=True, mode_requested='auto',
                 output_duration_seconds=media['duration_seconds'], gain_db=3, applied_gain_db=3,
                 encoding_performed=True, encoded_peak_safety={'passed': True, 'true_peak_dbtp': -12})
        self.write_record(record)
        data = source_probe(duration=3660.02)
        data['streams'][0]['codec_name'] = 'aac'
        data['format']['format_name'] = 'mov,mp4,m4a,3gp,3g2,mj2'
        with patch('recorandro.normalization.run_probe', side_effect=[self.payload, json.dumps(data).encode()]), \
                patch('recorandro.segmentation.detect_quiet_regions', return_value=[]) as detector:
            result = plan_session(self.config, self.sid)
        self.assertEqual(result['source']['kind'], 'normalized')
        self.assertEqual(result['plan']['timeline_start_seconds'], 0)
        self.assertEqual(result['plan']['timeline_end_seconds'], 3660.02)
        self.assertEqual(result['original_duration_seconds'], 3660)
        self.assertEqual(detector.call_args.args[3], 'normalized.m4a')
        self.assertEqual(derived.read_bytes(), b'independently verified mock derivative')

    def test_normalized_artifact_hash_and_symlink_are_not_trusted_from_metadata(self):
        record = self.record()
        n = record['normalization']
        derived = self.directory / 'generated' / 'normalization' / n['attempt_id'] / 'normalized.m4a'
        derived.write_bytes(b'managed derivative')
        source = {'managed_path': str(derived.relative_to(self.directory)).replace('\\', '/'),
                  'size_bytes': derived.stat().st_size, 'sha256': hashlib.sha256(derived.read_bytes()).hexdigest(),
                  'media': output_media(n['input']['media']), 'full_decode_verified': True}
        n.update(output_source='normalized', output=source, working_source=source,
                 normalization_applied=True, encoding_applied=True, mode_requested='auto', gain_db=3,
                 applied_gain_db=3, encoding_performed=True,
                 encoded_peak_safety={'passed': True, 'true_peak_dbtp': -12})
        self.write_record(record)
        derived.write_bytes(b'changed derivative')
        with self.assertRaises(PlanningFailure):
            self.mocked()
        self.assertEqual(self.original.read_bytes(), self.contents)
        derived.unlink()
        try:
            os.symlink(self.external, derived)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(str(exc))
        with self.assertRaises(PlanningFailure):
            self.mocked(retry=True)

    def test_quiet_command_maps_absolute_index_and_uses_discarded_filter_only(self):
        captured = []
        def run(args, timeout, log, **kwargs):
            captured.append((args, timeout, kwargs))
            log.write(''.join(events(('start', 1499), ('end', 1501))).encode())
            log.seek(0)
        media = copy.deepcopy(self.normalization['input']['media'])
        media['selected_audio_stream_index'] = 7
        with OwnedDirectory.root(self.directory) as folder, ExitDirectories(folder) as children:
            fd = children.audio.open(self.imported['audio']['imported_filename'], os.O_RDONLY)
            with os.fdopen(fd, 'rb') as source, \
                    patch('recorandro.segmentation._executable', return_value='ffmpeg'), \
                    patch('recorandro.segmentation._run_detection', side_effect=run):
                regions = detect_quiet_regions(self.config, source, children.audio,
                                              self.imported['audio']['imported_filename'], media, children.temp)
            self.assertEqual(list(children.temp.path.iterdir()), [])
        args, timeout, kwargs = captured[0]
        self.assertEqual(regions, [quiet(1499, 1501)])
        for key, value in (('-af', QUIET_FILTER), ('-map', '0:7'), ('-f', 'null'),
                           ('-protocol_whitelist', 'file'), ('-format_whitelist', 'mov,mp3,wav,aac'),
                           ('-err_detect', 'explode')):
            self.assertEqual(args[args.index(key) + 1], value)
        self.assertEqual(timeout, 7380)
        self.assertTrue(all(flag in args for flag in ('-nostdin', '-n', '-vn', '-sn', '-dn', '-xerror')))
        self.assertNotIn('-c:a', args)
        self.assertNotIn('loudnorm', ' '.join(args))

    def test_pending_metadata_failure_invokes_no_probe_or_analysis(self):
        with patch.object(OwnedDirectory, 'atomic_json', side_effect=OSError('controlled')), \
                patch('recorandro.segmentation.detect_quiet_regions') as detector, \
                patch('recorandro.normalization.run_probe') as probe, self.assertRaises(PlanningFailure):
            plan_session(self.config, self.sid)
        detector.assert_not_called()
        probe.assert_not_called()
        self.assertNotIn('segmentation', self.record())

    def test_failed_decode_preserves_audio_prior_plan_and_retry(self):
        first, _ = self.mocked()
        old = self.directory / self.record()['segmentation']['record_path']
        for injected in (PlanningFailure('tool_timeout', 'Controlled timeout'),
                         PlanningFailure('tool_nonzero_exit', 'Controlled decode failure'), KeyboardInterrupt()):
            with patch('recorandro.normalization.run_probe', return_value=self.payload), \
                    patch('recorandro.segmentation.detect_quiet_regions', side_effect=injected), \
                    self.assertRaises(PlanningFailure):
                plan_session(self.config, self.sid, retry=True)
            self.assertEqual(self.record()['segmentation']['status'], 'planning_failed')
            self.assertEqual(self.original.read_bytes(), self.contents)
            self.assertEqual(json.loads(old.read_text()), first)
        with self.assertRaises(PlanningFailure) as exc:
            self.mocked()
        self.assertEqual(exc.exception.code, 'retry_required')
        self.assertEqual(self.mocked(retry=True)[0]['status'], 'planned')

    def test_original_hash_change_before_and_after_analysis(self):
        self.original.chmod(0o600)
        self.original.write_bytes(b'z' * len(self.contents))
        with self.assertRaises(PlanningFailure):
            self.mocked()
        self.original.write_bytes(self.contents)
        def changed(*args):
            self.original.write_bytes(b'y' * len(self.contents))
            return []
        with patch('recorandro.normalization.run_probe', return_value=self.payload), \
                patch('recorandro.segmentation.detect_quiet_regions', side_effect=changed), \
                self.assertRaises(PlanningFailure):
            plan_session(self.config, self.sid, retry=True)
        latest = self.record()['segmentation']
        self.assertEqual(latest['status'], 'planning_failed')
        self.assertIsNone(json.loads((self.directory / latest['record_path']).read_text())['plan'])

    def test_stale_duration_absolute_index_and_bad_path_refused(self):
        baseline = self.record()
        for change in ({'duration': '3661'}, {'index': 7}, {'codec_name': 'unknown'}):
            payload = source_probe(duration=3660)
            payload['streams'][0].update(change)
            with patch('recorandro.normalization.run_probe', return_value=json.dumps(payload).encode()), \
                    self.assertRaises(PlanningFailure):
                plan_session(self.config, self.sid, retry=True)
        record = copy.deepcopy(baseline)
        record['normalization']['working_source']['managed_path'] = '../../external.wav'
        self.write_record(record)
        with self.assertRaises(PlanningFailure):
            self.mocked(retry=True)

    def test_metadata_failure_pending_not_success_and_history_preserved(self):
        actual = OwnedDirectory.atomic_json
        def denied(folder, record):
            if record.get('segmentation', {}).get('status') == 'planned':
                raise OSError('controlled publication error')
            return actual(folder, record)
        with patch.object(OwnedDirectory, 'atomic_json', denied), self.assertRaises(PlanningFailure):
            self.mocked()
        self.assertEqual(self.record()['segmentation']['status'], 'planning_pending')
        self.assertIsNone(self.record()['segmentation']['record_sha256'])
        self.assertEqual(self.original.read_bytes(), self.contents)
        self.assertEqual(self.mocked(retry=True)[0]['status'], 'planned')

    def test_managed_symlink_rejected(self):
        alias = self.base / 'alias'
        try:
            os.symlink(self.config.data_root, alias, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(str(exc))
        with self.assertRaises((PlanningFailure, OSError, ValueError)):
            plan_session(Config(alias), self.sid)

    def test_cli_auto_default_modes_retry_and_private_errors(self):
        with patch('recorandro.cli.load_config', return_value=self.config), \
                patch('recorandro.cli.plan_session', return_value={'status': 'planned'}) as planner, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['plan-session', self.sid]), 0)
        planner.assert_called_once_with(self.config, self.sid, mode='auto', retry=False)
        self.assertTrue(json.loads(output.getvalue())['ok'])
        with patch('recorandro.cli.load_config', return_value=self.config), \
                patch('recorandro.cli.plan_session', side_effect=OSError('private path')), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['plan-session', self.sid, '--mode', 'off', '--retry']), 1)
        self.assertNotIn('private path', output.getvalue())


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Real host media tools unavailable')
class RealDetectionTests(SessionFixture):
    def test_real_short_quiet_log_and_no_audio_write(self):
        inspect_session(self.config, self.sid)
        normalize_session(self.config, self.sid, mode='off')
        result = plan_session(self.config, self.sid)
        self.assertEqual(result['plan']['expected_part_count'], 1)
        with OwnedDirectory.root(self.directory) as folder, ExitDirectories(folder) as children:
            audio = children.audio
            temp = children.temp
            fd = audio.open(self.imported['audio']['imported_filename'], os.O_RDONLY)
            with os.fdopen(fd, 'rb') as source:
                regions = detect_quiet_regions(self.config, source, audio, self.imported['audio']['imported_filename'],
                                              self.record()['normalization']['input']['media'], temp)
        # Fixture's 0.5-second pauses are below the exact 1-second minimum.
        self.assertEqual(regions, [])
        self.assertEqual(self.original.read_bytes(), self.contents)

    def test_real_applied_normalization_selects_derivative_without_rerunning_it(self):
        inspect_session(self.config, self.sid)
        n = normalize_session(self.config, self.sid)
        self.assertTrue(n['normalization_applied'])
        with patch('recorandro.normalization.normalize_session') as normalize, \
                patch('recorandro.segmentation.detect_quiet_regions') as detector:
            result = plan_session(self.config, self.sid)
        self.assertEqual(result['source']['kind'], 'normalized')
        self.assertEqual(result['source']['sha256'], n['output']['sha256'])
        self.assertEqual(result['source']['normalization_attempt_id'], n['attempt_id'])
        normalize.assert_not_called()
        detector.assert_not_called()

    def test_real_combined_stereo_and_secondary_formats(self):
        rate = 8000
        for suffix in ('.wav', '.m4a', '.mp3'):
            wav_path = self.base / ('combined' + suffix + '.wav')
            samples = array('h')
            for index in range(6 * rate):
                value = round(3000 * math.sin(2 * math.pi * 440 * index / rate))
                # One quiet channel is not combined-channel silence. Both go
                # quiet during 3..5, which must produce exactly that interval.
                t = index / rate
                samples.extend((0 if 1 <= t < 5 else value, 0 if 3 <= t < 5 else value))
            if sys.byteorder != 'little':
                samples.byteswap()
            with wave.open(str(wav_path), 'wb') as wav:
                wav.setparams((2, 2, rate, 0, 'NONE', 'not compressed'))
                wav.writeframes(samples.tobytes())
            source = wav_path
            if suffix != '.wav':
                source = self.base / ('combined' + suffix)
                subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-n', '-i', str(wav_path),
                                '-c:a', 'aac' if suffix == '.m4a' else 'libmp3lame', str(source)],
                               shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE, timeout=30, check=True)
            with patch.object(OwnedDirectory, 'free_bytes', return_value=10**12):
                s = import_audio(self.config, source, provision_seconds=60)
            inspected = inspect_session(self.config, s['session_id'])
            folder_path = self.config.data_root / 'sessions' / s['session_id']
            with OwnedDirectory.root(folder_path) as folder, ExitDirectories(folder) as children:
                leaf = s['audio']['imported_filename']
                with os.fdopen(children.audio.open(leaf, os.O_RDONLY), 'rb') as stream:
                    regions = detect_quiet_regions(self.config, stream, children.audio, leaf,
                                                  inspected['media'], children.temp)
            self.assertEqual(len(regions), 1)
            self.assertAlmostEqual(regions[0]['start_seconds'], 3, delta=0.1)
            self.assertAlmostEqual(regions[0]['end_seconds'], 5, delta=0.1)

    def test_real_long_multipart_quiet_boundary_and_full_coverage(self):
        source = self.base / 'long.wav'
        rate, duration = 8000, 1621
        tone = array('h', [round(3000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(rate)])
        if sys.byteorder != 'little':
            tone.byteswap()
        with wave.open(str(source), 'wb') as wav:
            wav.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
            for second in range(duration):
                wav.writeframesraw(bytes(rate * 2) if 809 <= second < 813 else tone.tobytes())
        with patch.object(OwnedDirectory, 'free_bytes', return_value=10**12):
            session = import_audio(self.config, source, provision_seconds=1700)
        sid = session['session_id']
        inspect_session(self.config, sid)
        normalize_session(self.config, sid, mode='off')
        source.unlink()
        result = plan_session(self.config, sid)
        self.assertTrue(result['quiet_analysis']['completed'])
        self.assertEqual(result['plan']['expected_part_count'], 2)
        self.assertEqual(result['plan']['boundaries'][0]['reason'], 'quiet_region')
        self.assertAlmostEqual(result['plan']['boundaries'][0]['global_timestamp_seconds'], 811, delta=0.01)
        self.assertEqual(result['plan']['nominal_parts'][-1]['global_end_seconds'], duration)
        self.assertEqual(result['integrity']['original_before'], result['integrity']['original_after'])


class ExitDirectories:
    def __init__(self, folder):
        from contextlib import ExitStack
        self.stack = ExitStack()
        self.folder = folder

    def __enter__(self):
        original = self.stack.enter_context(self.folder.child('originals'))
        self.audio = self.stack.enter_context(original.child('audio'))
        parent = self.stack.enter_context(self.folder.child('temp'))
        self.temp = self.stack.enter_context(parent.child('real-quiet-' + uuid.uuid4().hex, exclusive=True))
        return self

    def __exit__(self, *args):
        self.stack.close()


if __name__ == '__main__':
    unittest.main()
