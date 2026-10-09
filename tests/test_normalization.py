"""Frozen-policy regressions and separate real-tool Step 2.2 fixtures."""

from array import array
import contextlib
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

from recorandro.cli import main
from recorandro.config import Config
from recorandro.inspection import inspect_session, parse_probe
from recorandro.normalization import (NormalizationFailure, MEASUREMENT_FILTER, AAC_RATES,
                                     TAIL_BYTES, MAX_DIAGNOSTIC_BYTES, _execute, _input_args,
                                     choose_gain, normalize_session, parse_loudness,
                                     pass_timeout, storage_budget, verify_output, verify_peak)
from recorandro.sessions import import_audio
from recorandro.storage import OwnedDirectory


def log_levels(integrated=-36, peak=-15, **extra):
    data = {"input_i": str(integrated), "input_tp": str(peak), "input_lra": "1.0", "input_thresh": "-46",
            "output_i": "-26", "output_tp": "-3"}
    data.update(extra)
    return "private FFmpeg messages\n" + json.dumps(data)


def source_probe(rate=16000, channels=1, duration=8):
    return {"streams": [{"index": 0, "codec_type": "audio", "codec_name": "pcm_s16le",
                          "sample_rate": str(rate), "channels": channels, "duration": str(duration),
                          "duration_ts": round(rate * duration), "time_base": f"1/{rate}", "start_time": "0"}],
            "format": {"format_name": "wav", "duration": str(duration)}}


def output_media(source):
    result = copy.deepcopy(source)
    result.update(audio_codec="aac", demuxer_family="mov", container_format="mov,mp4,m4a,3gp,3g2,mj2",
                  codec_profile="LC", stream_count=1, selected_audio_stream_index=0,
                  sample_rate=source["sample_rate"] if source["sample_rate"] in AAC_RATES else 48000)
    return result


def make_wav(path, amplitude=0.01, rate=16000, channels=1, seconds=8):
    samples = array("h")
    for index in range(round(rate * seconds)):
        t = index / rate
        # Pauses at beginning, middle and end remain part of the timeline.
        quiet = t < 0.5 or 3 <= t < 3.5 or t >= seconds - 0.5
        value = 0 if quiet else round(32767 * amplitude * math.sin(2 * math.pi * 440 * t))
        for channel in range(channels):
            samples.append(value if channel == 0 else round(value * 0.8))
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as output:
        output.setparams((channels, 2, rate, 0, "NONE", "not compressed"))
        output.writeframes(samples.tobytes())


class PolicyTests(unittest.TestCase):
    def decide(self, integrated, peak, mode="auto"):
        return choose_gain(parse_loudness(log_levels(integrated, peak)), mode)

    def test_auto_default_exact_threshold_and_usable_skip(self):
        for integrated in (-30, -28, -26, -5):
            result = self.decide(integrated, -10)
            self.assertEqual(result["decision"], "auto_already_usable_level")
            self.assertEqual(result["gain_db"], 0)
        self.assertEqual(self.decide(-30.001, -10)["gain_db"], 3)

    def test_low_level_boost_cap_floor_and_useful_gain_boundary(self):
        self.assertEqual(self.decide(-45, -15)["gain_db"], 3)
        self.assertEqual(self.decide(-36, -3.5)["gain_db"], 0.5)
        self.assertEqual(self.decide(-36, -3.499)["gain_db"], 0)
        self.assertEqual(self.decide(-36, -4.2349)["gain_db"], 1.234)
        self.assertEqual(self.decide(-36, -4.9999)["gain_db"], 1.999)

    def test_peak_constrained_and_already_clipped_input(self):
        for peak in (-3, -2, 0, 0.5):
            result = self.decide(-36, peak)
            self.assertEqual(result["gain_db"], 0)
            self.assertEqual(result["decision"], "insufficient_safe_gain")
            if peak >= 0:
                self.assertIn("input_possible_existing_clipping", result["warnings"])
        self.assertEqual(self.decide(-10, 1)["gain_db"], 0)

    def test_force_bypasses_only_auto_cutoff(self):
        self.assertEqual(self.decide(-28, -10)["gain_db"], 0)
        self.assertEqual(self.decide(-28, -10, "force")["gain_db"], 2)
        self.assertEqual(self.decide(-50, -10, "force")["gain_db"], 3)
        self.assertEqual(self.decide(-26, -10, "force")["decision"], "force_no_gain_at_or_above_target")
        self.assertEqual(self.decide(-25, -10, "force")["decision"], "force_no_gain_at_or_above_target")
        self.assertEqual(self.decide(-27.7, -1.39, "force")["decision"], "force_no_gain_insufficient_safe_gain")

    def test_below_gate_silence_and_off(self):
        levels = parse_loudness(log_levels("-inf", "-inf", input_lra="0"))
        self.assertIsNone(levels["integrated_lufs"])
        self.assertEqual(choose_gain(levels)["decision"], "below_measurement_gate")
        self.assertEqual(choose_gain(levels, "force")["decision"], "force_no_gain_below_measurement_gate")
        self.assertEqual(choose_gain(None, "off"), {"gain_db": 0, "decision": "normalization_off", "warnings": []})

    def test_parse_input_measurements_not_transformed_output(self):
        levels = parse_loudness(log_levels(-36, -15))
        self.assertEqual(levels["integrated_lufs"], -36)
        self.assertEqual(levels["true_peak_dbtp"], -15)
        self.assertEqual(levels["threshold_lufs"], -46)
        self.assertEqual(levels["loudness_range_lu"], 1)
        self.assertEqual(choose_gain(levels)["gain_db"], 3)

    def test_loudness_malformed_nonfinite_bounds_and_missing_input(self):
        for key in ("input_i", "input_tp", "input_lra", "input_thresh"):
            for value in (True, None, "NaN", "inf", "Infinity", [], "not numeric", 101, -121):
                with self.subTest(key=key, value=value), self.assertRaises(NormalizationFailure):
                    parse_loudness(log_levels(**{key: value}))
        for payload in ('{"output_i":"-26","output_tp":"-3"}', "not JSON", '{"input_i":NaN,"input_tp":1}'):
            with self.assertRaises(NormalizationFailure):
                parse_loudness(payload)
        with self.assertRaises(NormalizationFailure):
            parse_loudness(log_levels(-35, "-inf"))
        with self.assertRaises(NormalizationFailure):
            parse_loudness(log_levels(input_lra="-1"))
        data = json.loads(log_levels().splitlines()[-1])
        del data["input_thresh"]
        self.assertIsNone(parse_loudness(json.dumps(data))["threshold_lufs"])

    def test_malformed_latest_measurement_cannot_reuse_previous_json(self):
        with self.assertRaises(NormalizationFailure):
            parse_loudness(log_levels() + '\n{"input_i":NaN,"input_tp":"-3"}')

    def test_fixed_timing_lecture_duration_and_rate_conversion(self):
        source = parse_probe(json.dumps(source_probe(rate=44100, duration=3691.787029)), ".wav")
        result = verify_output(output_media(source), source)
        self.assertEqual(result["tolerance_seconds"], 0.05)
        invalid = output_media(source)
        invalid["duration_seconds"] += 1
        with self.assertRaises(NormalizationFailure):
            verify_output(invalid, source)
        for start in (0.051, None):
            invalid = output_media(source)
            invalid["stream_start_seconds"] = start
            with self.assertRaises(NormalizationFailure):
                verify_output(invalid, source)
        source = parse_probe(json.dumps(source_probe(rate=12345)), ".wav")
        self.assertTrue(verify_output(output_media(source), source)["passed"])

    def test_bad_derivative_codec_profile_rate_channels_streams(self):
        source = parse_probe(json.dumps(source_probe()), ".wav")
        for key, value in (("audio_codec", "mp3"), ("codec_profile", "HE-AAC"), ("sample_rate", 48000),
                           ("channels", 2), ("stream_count", 2), ("demuxer_family", "wav")):
            result = output_media(source)
            result[key] = value
            with self.subTest(key=key), self.assertRaises(NormalizationFailure):
                verify_output(result, source)

    def test_encoded_peak_required_rejection_and_warning_boundaries(self):
        for peak in (None, "NaN", math.inf, True, -0.999):
            with self.subTest(peak=peak), self.assertRaises(NormalizationFailure):
                verify_peak({"true_peak_dbtp": peak})
        self.assertTrue(verify_peak({"true_peak_dbtp": -1})["passed"])
        self.assertTrue(verify_peak({"true_peak_dbtp": -2.899})["overshoot_warning"])
        self.assertFalse(verify_peak({"true_peak_dbtp": -2.9})["overshoot_warning"])

    def test_per_pass_timeout_and_current_storage_bound(self):
        self.assertEqual(pass_timeout(1), 120)
        self.assertEqual(pass_timeout(3691.787029), 7444)
        self.assertEqual(pass_timeout(50000), 21600)
        report = storage_budget(8, 0)
        self.assertEqual(report["derivative_temporary_bytes"], 305536)
        required = report["estimated_required_bytes"]
        self.assertEqual(storage_budget(8, required)["decision"], "allow")
        self.assertEqual(storage_budget(8, required - 1)["decision"], "deny")
        self.assertFalse(report["reservation"])


class ProcessTests(unittest.TestCase):
    def execute(self, script, **kwargs):
        return _execute([sys.executable, "-c", script], 120, "fixture", **kwargs)

    def test_bounded_tail_and_disconnected_stdin_shell_false(self):
        original = subprocess.Popen
        def observed(args, **kwargs):
            self.assertFalse(kwargs["shell"])
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            return original(args, **kwargs)
        with patch("recorandro.normalization.subprocess.Popen", side_effect=observed):
            log = self.execute(f"import sys; assert sys.stdin.read()==''; sys.stderr.write('x'*{TAIL_BYTES+100}); sys.stderr.write('END')")
        self.assertEqual(len(log), TAIL_BYTES)
        self.assertTrue(log.endswith("END"))

    def test_nonzero_and_excessive_output_are_private_failures(self):
        with self.assertRaises(NormalizationFailure) as error:
            self.execute("import sys; sys.stderr.write('private media path'); sys.exit(1)")
        self.assertNotIn("private media path", str(error.exception))
        with patch("recorandro.normalization.MAX_DIAGNOSTIC_BYTES", 1024), self.assertRaises(NormalizationFailure):
            self.execute("import sys; sys.stderr.write('x'*5000)")
        with patch("recorandro.normalization.MAX_JSON_BYTES", 1024), self.assertRaises(NormalizationFailure):
            self.execute("print('x'*5000)", capture_stdout=True)

    def test_timeout_and_interrupt_kill_and_reap_real_helper(self):
        original_wait = subprocess.Popen.wait
        original_popen = subprocess.Popen
        for interruption in (subprocess.TimeoutExpired("private", 120), KeyboardInterrupt()):
            processes = []
            def popen(*args, **kwargs):
                process = original_popen(*args, **kwargs)
                processes.append(process)
                return process
            def wait(process, timeout=None):
                if timeout is not None:
                    raise interruption
                return original_wait(process)
            expected = NormalizationFailure if isinstance(interruption, subprocess.TimeoutExpired) else KeyboardInterrupt
            with patch.object(subprocess.Popen, "wait", wait), \
                    patch("recorandro.normalization.subprocess.Popen", side_effect=popen), self.assertRaises(expected):
                self.execute("import time; time.sleep(60)")
            self.assertIsNotNone(processes[0].poll())

    def test_input_safeguards_and_actual_mov_family_options(self):
        for family in ("mov", "wav", "mp3", "aac"):
            media = {"demuxer_family": family, "selected_audio_stream_index": 7}
            args = _input_args("owned/İ;$(never).wav", media)
            self.assertIn("file", args)
            self.assertIn("mov,mp3,wav,aac", args)
            self.assertIn("0:7", args)
            self.assertIn("explode", args)
            self.assertIn("-vn", args)
            self.assertIn("-sn", args)
            self.assertIn("-dn", args)
            self.assertEqual("-enable_drefs" in args, family == "mov")

    def test_diagnostic_reader_start_failure_reaps_process(self):
        original = subprocess.Popen
        processes = []
        def observed(*args, **kwargs):
            process = original(*args, **kwargs)
            processes.append(process)
            return process
        with patch("recorandro.normalization.subprocess.Popen", side_effect=observed), \
                patch("recorandro.normalization.threading.Thread.start", side_effect=RuntimeError("reader unavailable")), \
                self.assertRaises(NormalizationFailure):
            self.execute("import time; time.sleep(60)")
        self.assertIsNotNone(processes[0].poll())


class SessionFixture(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.base = Path(self.folder.name)
        self.config = Config(self.base / "managed")
        self.source = self.base / "İstanbul ders 🎧.wav"
        make_wav(self.source)
        with patch.object(OwnedDirectory, "free_bytes", return_value=10**12):
            self.imported = import_audio(self.config, self.source, provision_seconds=60)
        self.session_id = self.imported["session_id"]
        self.directory = self.config.data_root / "sessions" / self.session_id
        self.managed = self.directory / self.imported["audio"]["managed_path"]
        self.contents = self.managed.read_bytes()
        self.payload = json.dumps(source_probe()).encode()
        with patch("recorandro.inspection.run_probe", return_value=self.payload):
            self.inspected = inspect_session(self.config, self.session_id)
        self.media = self.inspected["media"]
        self.commands = []
        self.addCleanup(self.writable)

    def writable(self):
        for path in self.config.data_root.rglob("*.m4a"):
            if path.is_file() and not path.is_symlink():
                path.chmod(0o600)
        self.managed.chmod(0o600)

    def record(self):
        return json.loads((self.directory / "session.json").read_text(encoding="utf-8"))

    def write_record(self, record):
        with OwnedDirectory.root(self.directory) as directory:
            directory.atomic_json(record)

    def fake_execute(self, args, timeout, phase, **kwargs):
        self.commands.append((args, timeout, phase, kwargs))
        if phase == "encode":
            Path(args[-1]).write_bytes(b"mock derivative bytes")
            return ""
        return log_levels(-36, -15) if phase == "input_measurement" else log_levels(-33, -12)

    def mocked(self, **kwargs):
        with patch("recorandro.normalization.run_probe", return_value=self.payload), \
                patch("recorandro.normalization._execute", side_effect=self.fake_execute), \
                patch("recorandro.normalization._probe_output", return_value=output_media(self.media)), \
                patch.object(OwnedDirectory, "free_bytes", return_value=10**12):
            return normalize_session(self.config, self.session_id, **kwargs)


class SessionTests(SessionFixture):
    def test_default_applied_independent_artifact_and_immutable_original(self):
        self.source.unlink()
        before = self.managed.stat()
        result = self.mocked()
        self.assertEqual(result["mode_requested"], "auto")
        self.assertEqual(result["status"], "normalization_succeeded")
        self.assertEqual(result["gain_db"], 3)
        self.assertEqual(result["applied_gain_db"], 3)
        self.assertTrue(result["evaluation_performed"] and result["evaluation_completed"])
        self.assertTrue(result["normalization_applied"])
        output = self.directory / result["output"]["managed_path"]
        self.assertEqual(output.name, "normalized.m4a")
        self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), result["output"]["sha256"])
        self.assertNotEqual(output.stat().st_ino, self.managed.stat().st_ino)
        self.assertEqual(self.managed.read_bytes(), self.contents)
        self.assertEqual(before.st_mtime_ns, self.managed.stat().st_mtime_ns)
        current = self.record()
        self.assertEqual(current["state"], "imported")
        self.assertEqual(current["audio"], self.imported["audio"])
        self.assertEqual(current["inspection"], self.inspected)
        self.assertEqual(current["visual_count"], 0)
        history = json.loads(output.parent.joinpath("session.json").read_text())
        self.assertEqual(history, result)
        self.assertEqual(result["integrity"]["before"], result["integrity"]["after"])

    def test_exact_encode_args_volume_only_and_selected_original(self):
        self.mocked()
        encode, timeout, _, kwargs = next(command for command in self.commands if command[2] == "encode")
        self.assertEqual(encode[encode.index("-af") + 1], "volume=3.000dB:precision=double")
        self.assertEqual(encode[encode.index("-map") + 1], "0:0")
        for option, value in (("-c:a", "aac"), ("-profile:a", "aac_low"), ("-b:a", "128000"),
                              ("-ar", "16000"), ("-map_metadata", "-1"), ("-map_chapters", "-1"),
                              ("-movflags", "+faststart"), ("-f", "ipod")):
            self.assertEqual(encode[encode.index(option) + 1], value)
        self.assertIn("-n", encode)
        self.assertIn("-nostdin", encode)
        self.assertIn("-xerror", encode)
        self.assertNotIn("-ac", encode)
        self.assertNotIn("-q:a", encode)
        self.assertNotIn(MEASUREMENT_FILTER, encode)
        source = encode[encode.index("-i") + 1]
        self.assertEqual(Path(source).read_bytes() if os.name == "nt" else self.contents, self.contents)
        if os.name == "nt":
            self.assertEqual(Path(source), self.managed)
        else:
            self.assertTrue(source.startswith("/proc/self/fd/"))

    def test_auto_force_no_gain_never_encode_or_create_artifact(self):
        for mode, levels, reason in (("auto", log_levels(-28, -10), "auto_already_usable_level"),
                                    ("force", log_levels(-26, -10), "force_no_gain_at_or_above_target"),
                                    ("force", log_levels(-28, -2), "force_no_gain_insufficient_safe_gain"),
                                    ("auto", log_levels("-inf", "-inf"), "below_measurement_gate")):
            def measured(args, timeout, phase, **kwargs):
                self.assertEqual(phase, "input_measurement")
                return levels
            with patch.object(self, "fake_execute", measured):
                result = self.mocked(mode=mode)
            self.assertEqual(result["decision"], reason)
            self.assertEqual(result["output_source"], "original")
            self.assertIsNone(result["output"])
            self.assertFalse(result["normalization_applied"] or result["encoding_applied"])
            self.assertEqual(result["working_source"]["sha256"], self.imported["audio"]["sha256"])

    def test_off_full_decode_without_loudness_or_artifact(self):
        result = self.mocked(mode="off")
        self.assertEqual(result["decision"], "normalization_off")
        self.assertFalse(result["evaluation_performed"] or result["evaluation_completed"])
        self.assertTrue(result["full_decode_verified"])
        self.assertIsNone(result["input_levels"])
        self.assertEqual([c[2] for c in self.commands], ["input_decode"])
        self.assertNotIn("-af", self.commands[0][0])
        self.assertIsNone(result["output"])

    def test_force_positive_gain_and_reruns_always_from_original(self):
        def measured(args, timeout, phase, **kwargs):
            result = self.fake_execute(args, timeout, phase, **kwargs)
            return log_levels(-28, -10) if phase == "input_measurement" else result
        with patch("recorandro.normalization.run_probe", return_value=self.payload), \
                patch("recorandro.normalization._execute", side_effect=measured), \
                patch("recorandro.normalization._probe_output", return_value=output_media(self.media)):
            first = normalize_session(self.config, self.session_id, mode="force")
            second = normalize_session(self.config, self.session_id, mode="force")
        self.assertEqual(first["gain_db"], 2)
        self.assertNotEqual(first["output"]["managed_path"], second["output"]["managed_path"])
        self.assertEqual(second["input"]["sha256"], self.imported["audio"]["sha256"])
        self.assertTrue((self.directory / first["output"]["managed_path"]).exists())

    def test_missing_tool_nonzero_timeout_interrupt_preserve_inspection_and_retry(self):
        first = self.mocked()
        first_path = self.directory / first["output"]["managed_path"]
        for injected in (NormalizationFailure("tool_nonzero_exit", "Controlled decoder error"),
                         NormalizationFailure("tool_timeout", "Controlled timeout"), KeyboardInterrupt()):
            with patch.object(self, "fake_execute", side_effect=injected), self.assertRaises(NormalizationFailure):
                self.mocked(retry=True)
            current = self.record()
            self.assertEqual(current["inspection"], self.inspected)
            self.assertEqual(current["normalization"]["status"], "normalization_failed")
            self.assertEqual(current["normalization"]["integrity"]["after"]["status"], "verified")
            self.assertEqual(self.managed.read_bytes(), self.contents)
            self.assertTrue(first_path.exists())
        with self.assertRaises(NormalizationFailure) as error:
            self.mocked()
        self.assertEqual(error.exception.code, "retry_required")
        self.assertEqual(self.mocked(retry=True)["status"], "normalization_succeeded")
        with patch("recorandro.normalization._executable", side_effect=NormalizationFailure("ffmpeg_missing", "Missing FFmpeg")), \
                self.assertRaises(NormalizationFailure):
            self.mocked()
        self.assertEqual(self.record()["normalization"]["error"]["code"], "ffmpeg_missing")

    def test_hash_mismatch_and_changed_original_after_processing(self):
        self.managed.chmod(0o600)
        self.managed.write_bytes(b"x" * len(self.contents))
        with self.assertRaises(NormalizationFailure) as error:
            self.mocked()
        self.assertEqual(error.exception.code, "original_hash_mismatch")
        self.managed.write_bytes(self.contents)
        def mutated(*args, **kwargs):
            self.managed.write_bytes(b"z" * len(self.contents))
            return log_levels(-28, -10)
        with patch.object(self, "fake_execute", mutated), self.assertRaises(NormalizationFailure):
            self.mocked(retry=True)
        self.assertIsNone(self.record()["normalization"]["working_source"])

    def test_required_inspection_and_invalid_media_blocks_off_too(self):
        for mutation in (lambda r: r.pop("inspection"), lambda r: r["inspection"].update(status="probe_failed"),
                         lambda r: r["inspection"]["media"].update(channels=6),
                         lambda r: r["inspection"]["media"].update(demuxer_family="aac"),
                         lambda r: r["inspection"]["media"]["warnings"].append("duration_disagreement")):
            record = copy.deepcopy(self.imported)
            record["inspection"] = copy.deepcopy(self.inspected)
            mutation(record)
            self.write_record(record)
            with self.assertRaises(NormalizationFailure):
                self.mocked(mode="off", retry=True)

    def test_malformed_nested_inspection_fails_actionably(self):
        for field, value in (("source", []), ("integrity", []), ("media", [])):
            record = self.record()
            record.pop("normalization", None)
            record["inspection"] = copy.deepcopy(self.inspected)
            record["inspection"][field] = value
            self.write_record(record)
            with self.subTest(field=field), self.assertRaises(NormalizationFailure):
                self.mocked(mode="off", retry=True)
        for field in ("duration_consistency", "processing_eligibility", "warnings"):
            record = self.record()
            record.pop("normalization", None)
            record["inspection"] = copy.deepcopy(self.inspected)
            record["inspection"]["media"][field] = "invalid"
            self.write_record(record)
            with self.assertRaises(NormalizationFailure):
                self.mocked(mode="off", retry=True)

    def test_absolute_selected_index_is_mapped_and_persisted(self):
        data = source_probe()
        data["streams"][0]["index"] = 7
        data["streams"].insert(0, {"index": 0, "codec_type": "video", "codec_name": "h264"})
        self.payload = json.dumps(data).encode()
        with patch("recorandro.inspection.run_probe", return_value=self.payload):
            self.inspected = inspect_session(self.config, self.session_id)
        self.media = self.inspected["media"]
        result = self.mocked()
        self.assertEqual(result["input"]["media"]["selected_audio_stream_index"], 7)
        commands = [c[0] for c in self.commands if c[2] in ("input_measurement", "encode")]
        self.assertTrue(all(c[c.index("-map") + 1] == "0:7" for c in commands))

    def test_missing_configured_ffmpeg_fails_before_decode(self):
        configuration = Config(self.config.data_root, ffmpeg=str(self.base / "missing-ffmpeg"))
        with patch("recorandro.normalization.run_probe", return_value=self.payload), \
                patch("recorandro.normalization._execute") as execute, self.assertRaises(NormalizationFailure) as error:
            normalize_session(configuration, self.session_id)
        self.assertEqual(error.exception.code, "ffmpeg_missing")
        execute.assert_not_called()
        self.assertEqual(self.record()["normalization"]["integrity"]["after"]["status"], "verified")

    def test_fresh_selected_stream_decoder_and_duration_facts_must_match(self):
        for change in ({"index": 7}, {"codec_name": "unknown"}, {"sample_rate": "0"}, {"duration": "9"}):
            data = source_probe()
            data["streams"][0].update(change)
            with patch("recorandro.normalization.run_probe", return_value=json.dumps(data).encode()), \
                    self.assertRaises(NormalizationFailure):
                normalize_session(self.config, self.session_id, retry=True)
        with patch.object(self, "fake_execute", side_effect=NormalizationFailure("tool_nonzero_exit", "Missing decoder")), \
                self.assertRaises(NormalizationFailure):
            self.mocked(mode="off", retry=True)

    def test_storage_denial_before_encode_and_partial_cleanup(self):
        with patch("recorandro.normalization.storage_budget", return_value={"decision": "deny"}), \
                self.assertRaises(NormalizationFailure) as error:
            self.mocked()
        self.assertEqual(error.exception.code, "insufficient_storage")
        self.assertNotIn("encode", [c[2] for c in self.commands])
        def fail_encode(args, timeout, phase, **kwargs):
            result = SessionFixture.fake_execute(self, args, timeout, phase, **kwargs)
            if phase == "encode":
                raise NormalizationFailure("tool_nonzero_exit", "Controlled encode failure")
            return result
        with patch.object(self, "fake_execute", fail_encode), self.assertRaises(NormalizationFailure):
            self.mocked(retry=True)
        self.assertEqual(list(self.directory.glob("temp/normalize-*/pending.m4a")), [])
        self.assertEqual(list(self.directory.glob("generated/normalization/*/normalized.m4a")), [])

    def test_bad_output_peak_and_timing_never_publish(self):
        for levels in (log_levels(-33, "-inf"), log_levels(-33, "NaN"), log_levels(-33, -0.9)):
            def invalid(args, timeout, phase, **kwargs):
                result = SessionFixture.fake_execute(self, args, timeout, phase, **kwargs)
                return levels if phase == "output_measurement" else result
            with patch.object(self, "fake_execute", invalid), self.assertRaises(NormalizationFailure):
                self.mocked(retry=True)
        invalid = output_media(self.media)
        invalid["duration_seconds"] += 1
        with patch("recorandro.normalization.verify_output", side_effect=NormalizationFailure("invalid_derivative_timing", "Controlled mismatch")), \
                self.assertRaises(NormalizationFailure):
            self.mocked(retry=True)
        self.assertEqual(list(self.directory.glob("generated/normalization/*/normalized.m4a")), [])

    def test_encoded_peak_overshoot_warns_when_otherwise_valid(self):
        def overshoot(args, timeout, phase, **kwargs):
            result = SessionFixture.fake_execute(self, args, timeout, phase, **kwargs)
            return log_levels(-33, -2.8) if phase == "output_measurement" else result
        with patch.object(self, "fake_execute", overshoot):
            result = self.mocked()
        self.assertIn("encoded_peak_overshoot", result["warnings"])
        self.assertTrue(result["encoded_peak_safety"]["passed"])

    def test_final_publication_collision_preserves_competitor(self):
        original = OwnedDirectory.publish
        def collision(directory, temporary, final, destination=None):
            (destination.path / final).write_bytes(b"existing output")
            return original(directory, temporary, final, destination)
        with patch.object(OwnedDirectory, "publish", collision), self.assertRaises(NormalizationFailure):
            self.mocked()
        artifact = next(self.directory.glob("generated/normalization/*/normalized.m4a"))
        self.assertEqual(artifact.read_bytes(), b"existing output")
        self.assertIsNone(self.record()["normalization"]["output"])

    def test_unexpected_existing_temporary_output_is_not_encoded_or_overwritten(self):
        original = OwnedDirectory.child
        created = []
        def competing(directory, name, exclusive=False):
            child = original(directory, name, exclusive)
            if name.startswith("normalize-"):
                (child.path / "pending.m4a").write_bytes(b"unexpected existing file")
                created.append(child.path / "pending.m4a")
            return child
        with patch.object(OwnedDirectory, "child", competing), self.assertRaises(NormalizationFailure) as error:
            self.mocked()
        self.assertEqual(error.exception.code, "temporary_output_exists")
        self.assertNotIn("encode", [command[2] for command in self.commands])
        self.assertEqual(created[0].read_bytes(), b"unexpected existing file")

    def test_metadata_failure_after_publication_leaves_pending_and_orphan(self):
        original = OwnedDirectory.atomic_json
        def denied(directory, record):
            if record.get("normalization", {}).get("status") == "normalization_succeeded":
                raise OSError("controlled metadata failure")
            return original(directory, record)
        with patch.object(OwnedDirectory, "atomic_json", denied), self.assertRaises(NormalizationFailure) as error:
            self.mocked()
        self.assertEqual(error.exception.code, "metadata_persistence_failed")
        self.assertEqual(self.record()["normalization"]["status"], "normalization_pending")
        self.assertIsNone(self.record()["normalization"]["output"])
        orphan = next(self.directory.glob("generated/normalization/*/normalized.m4a"))
        self.assertEqual(self.mocked(retry=True)["status"], "normalization_succeeded")
        self.assertTrue(orphan.exists())

    def test_pending_metadata_failure_never_invokes_tool(self):
        with patch.object(OwnedDirectory, "atomic_json", side_effect=OSError("controlled pending failure")), \
                patch("recorandro.normalization._execute") as execute, self.assertRaises(NormalizationFailure):
            normalize_session(self.config, self.session_id)
        execute.assert_not_called()
        self.assertNotIn("normalization", self.record())

    def test_managed_path_and_symlink_security(self):
        record = self.record()
        record["audio"]["managed_path"] = "../../external.wav"
        self.write_record(record)
        with self.assertRaises((NormalizationFailure, ValueError, OSError)):
            self.mocked()
        record["audio"] = self.imported["audio"]
        self.write_record(record)
        alias = self.base / "alias"
        try:
            os.symlink(self.config.data_root, alias, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(str(exc))
        with self.assertRaises((NormalizationFailure, ValueError, OSError)):
            normalize_session(Config(alias), self.session_id)

    def test_cli_default_modes_retry_exit_and_private_errors(self):
        with patch("recorandro.cli.load_config", return_value=self.config), \
                patch("recorandro.cli.normalize_session", return_value={"status": "normalization_succeeded"}) as engine, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["normalize-session", self.session_id]), 0)
        engine.assert_called_once_with(self.config, self.session_id, mode="auto", retry=False)
        self.assertTrue(json.loads(output.getvalue())["ok"])
        with patch("recorandro.cli.load_config", return_value=self.config), \
                patch("recorandro.cli.normalize_session", side_effect=OSError("private path")), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["normalize-session", self.session_id, "--mode", "off", "--retry"]), 1)
        self.assertNotIn("private path", output.getvalue())


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Real host media tools unavailable")
class RealNormalizationTests(SessionFixture):
    def ingest_real(self, source):
        with patch.object(OwnedDirectory, "free_bytes", return_value=10**12):
            record = import_audio(self.config, source, provision_seconds=60)
        inspect_session(self.config, record["session_id"])
        return record

    def test_real_auto_boost_wav_and_original_hash(self):
        # Reinspect using actual tools before processing this synthetic WAV.
        inspect_session(self.config, self.session_id)
        self.source.unlink()
        result = normalize_session(self.config, self.session_id)
        self.assertEqual(result["decision"], "low_level_safe_boost")
        self.assertEqual(result["gain_db"], 3)
        self.assertTrue(result["normalization_applied"])
        self.assertEqual(result["output"]["media"]["codec_profile"], "LC")
        self.assertEqual(result["output"]["media"]["sample_rate"], 16000)
        self.assertTrue(result["encoded_peak_safety"]["passed"])
        self.assertEqual(hashlib.sha256(self.managed.read_bytes()).hexdigest(), result["input"]["sha256"])

    def test_real_usable_auto_skip_force_applied_off_and_silence(self):
        usable = self.base / "usable.wav"
        make_wav(usable, amplitude=0.065)
        record = self.ingest_real(usable)
        automatic = normalize_session(self.config, record["session_id"])
        forced = normalize_session(self.config, record["session_id"], mode="force")
        off = normalize_session(self.config, record["session_id"], mode="off")
        self.assertEqual(automatic["decision"], "auto_already_usable_level")
        self.assertFalse(automatic["encoding_applied"])
        self.assertTrue(forced["normalization_applied"])
        self.assertGreaterEqual(forced["gain_db"], 0.5)
        self.assertEqual(off["decision"], "normalization_off")
        self.assertFalse(off["evaluation_performed"])
        silent = self.base / "silent.wav"
        make_wav(silent, amplitude=0)
        record = self.ingest_real(silent)
        silence = normalize_session(self.config, record["session_id"])
        self.assertEqual(silence["decision"], "below_measurement_gate")
        self.assertIsNone(silence["output"])

    def test_real_m4a_mp3_stereo_and_rate_conversion(self):
        for suffix, codec in ((".m4a", "aac"), (".mp3", "libmp3lame")):
            fixture = self.base / ("secondary" + suffix)
            subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(self.source),
                            "-c:a", codec, str(fixture)], shell=False, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30, check=True)
            record = self.ingest_real(fixture)
            result = normalize_session(self.config, record["session_id"])
            self.assertTrue(result["normalization_applied"])
            self.assertTrue(result["full_decode_verified"])
        for rate, channels in ((44100, 2), (12345, 1)):
            fixture = self.base / f"rate-{rate}-{channels}.wav"
            make_wav(fixture, rate=rate, channels=channels)
            record = self.ingest_real(fixture)
            result = normalize_session(self.config, record["session_id"])
            self.assertEqual(result["output"]["media"]["channels"], channels)
            self.assertEqual(result["output"]["media"]["sample_rate"], rate if rate in AAC_RATES else 48000)
            self.assertEqual(result["parameters"]["requested_encoding"]["bitrate"], 192000 if channels == 2 else 128000)


if __name__ == "__main__":
    unittest.main()
