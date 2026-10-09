"""Step 2.1 host evidence; mocks are separate from guarded real-tool fixtures."""

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
import unittest
from unittest.mock import patch
import wave

from recorandro.cli import main
from recorandro.config import Config
from recorandro.inspection import (ENTRIES, InspectionFailure, MAX_JSON_BYTES, MAX_STDERR_BYTES,
                                  inspect_session, parse_probe, probe_command, run_probe)
from recorandro.sessions import import_audio
from recorandro.storage import OwnedDirectory


def metadata():
    return {"streams": [{"index": 0, "codec_type": "audio", "codec_name": "aac",
                         "sample_rate": "48000", "channels": 2, "channel_layout": "stereo",
                         "duration": "10.0", "duration_ts": 480000, "time_base": "1/48000",
                         "start_time": "0", "bit_rate": "192000"}],
            "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "10.0",
                       "size": "2048", "start_time": "0", "bit_rate": "193000"}}


class ParsingTests(unittest.TestCase):
    def parse(self, data=None, suffix=".m4a"):
        return parse_probe(json.dumps(data if data is not None else metadata()).encode(), suffix)

    def test_first_recognized_absolute_index_and_all_streams(self):
        data = metadata()
        audio = data["streams"][0]
        audio["index"] = 7
        later = dict(audio, index=8, bit_rate="999999", disposition={"default": 1})
        data["streams"] = [{"index": 0, "codec_type": "video", "codec_name": "h264"},
                           {"index": 3, "codec_type": "audio", "codec_name": "unknown"},
                           {"index": 4, "codec_type": "audio"}, audio, later]
        result = self.parse(data)
        self.assertEqual(result["selected_audio_stream_index"], 7)
        self.assertEqual(result["stream_count"], 5)
        self.assertEqual(result["stream_bitrate"], 192000)

    def test_duration_precedence_and_disagreement(self):
        data = metadata()
        data["streams"][0]["duration"] = "12"
        data["streams"][0]["duration_ts"] = 480000
        data["format"]["duration"] = "20"
        result = self.parse(data)
        self.assertEqual((result["duration_seconds"], result["duration_source"]), (12, "stream"))
        self.assertEqual(result["duration_estimates_seconds"],
                         {"stream": 12, "stream_time_base": 10, "container": 20})
        self.assertIn("duration_disagreement", result["warnings"])
        self.assertEqual(result["processing_eligibility"]["status"], "blocked")
        self.assertEqual(result["duration_consistency"]["tolerance_seconds"], 1)

    def test_duration_ticks_then_container_fallback(self):
        data = metadata()
        del data["streams"][0]["duration"]
        self.assertEqual(self.parse(data)["duration_source"], "stream_time_base")
        del data["streams"][0]["duration_ts"]
        result = self.parse(data)
        self.assertEqual(result["duration_source"], "container")
        self.assertIn("duration_no_independent_cross_check", result["warnings"])

    def test_duration_invalid_values_and_positive_floor(self):
        for value in (0, -1, "NaN", "Infinity", "-Infinity", True, [], {}, "bad", "0.0000009", 2**53 + 1):
            data = metadata()
            data["streams"][0].update(duration=value, duration_ts=None)
            data["format"]["duration"] = value
            with self.subTest(value=value):
                result = self.parse(data)
                self.assertIsNone(result["duration_seconds"])
                self.assertIn("duration_unavailable", result["processing_eligibility"]["blockers"])
        data["streams"][0]["duration"] = "0.000001"
        self.assertEqual(self.parse(data)["duration_seconds"], 0.000001)

    def test_time_base_and_integer_fields_defensive(self):
        for base in ("1/0", "0/48000", "1/-1", "1.0/48000", "1/2/3", True, "NaN/1", "1/9007199254740993"):
            data = metadata()
            data["streams"][0].update(duration=None, time_base=base)
            with self.subTest(base=base):
                result = self.parse(data)
                self.assertEqual(result["duration_source"], "container")
                self.assertIn("invalid_stream_time_base", result["warnings"])
        for value in (False, "1.5", -1, "Infinity", 2**53 + 1):
            data = metadata()
            data["streams"][0]["index"] = value
            with self.subTest(index=value), self.assertRaises(InspectionFailure):
                self.parse(data)
        data = metadata()
        data["streams"][0].update(sample_rate=True, channels="1.5", bit_rate="NaN")
        result = self.parse(data)
        for field in ("sample_rate", "channels", "stream_bitrate"):
            self.assertIsNone(result[field])
        self.assertEqual(result["processing_eligibility"]["status"], "blocked")

    def test_tick_duration_cannot_round_excess_into_numeric_limit(self):
        limit = 2**53
        data = metadata()
        data["streams"][0].update(duration=None, duration_ts=limit - 1,
                                  time_base=f"{limit - 1}/{limit - 2}")
        result = self.parse(data)
        # Exact ratio is limit + 1/(limit-2); binary float would round to limit.
        self.assertIsNone(result["duration_estimates_seconds"]["stream_time_base"])
        self.assertIn("invalid_stream_time_base_duration", result["warnings"])

    def test_valid_but_ineligible_rate_channels_and_unknown_decoder(self):
        for rate, channels in ((7349, 1), (192001, 2), (48000, 6)):
            data = metadata()
            data["streams"][0].update(sample_rate=rate, channels=channels, codec_name="alac")
            self.assertEqual(self.parse(data)["processing_eligibility"]["status"], "blocked")
        data = metadata()
        data["streams"][0]["codec_name"] = "alac"
        self.assertEqual(self.parse(data)["processing_eligibility"],
                         {"status": "unverified", "blockers": [], "decoder": "unverified"})

    def test_duration_warning_threshold_and_missing_independent_estimates(self):
        data = metadata()
        data["format"]["duration"] = "11"
        self.assertNotIn("duration_disagreement", self.parse(data)["warnings"])
        data["format"]["duration"] = "11.000001"
        self.assertIn("duration_disagreement", self.parse(data)["warnings"])
        data = metadata()
        data["streams"][0].update(duration="1000", duration_ts=48000000)
        data["format"]["duration"] = "1010"
        self.assertNotIn("duration_disagreement", self.parse(data)["warnings"])
        del data["format"]["duration"]
        self.assertIn("duration_cross_check_same_stream_only", self.parse(data)["warnings"])

    def test_raw_aac_unreliable_duration_and_permitted_family_mismatch(self):
        data = metadata()
        data["format"].update(format_name="aac", duration="63.67")
        data["streams"][0].update(duration=None, duration_ts=None)
        result = self.parse(data, ".aac")
        self.assertEqual(result["duration_seconds"], 63.67)
        self.assertIn("raw_aac_duration_unverified", result["warnings"])
        self.assertIn("raw_aac_duration_verification_required", result["processing_eligibility"]["blockers"])
        self.assertIn("suffix_demuxer_mismatch", self.parse(data, ".wav")["warnings"])
        self.assertIn("suffix_demuxer_mismatch", self.parse(metadata(), ".aac")["warnings"])

    def test_untrusted_creation_and_optional_nulls(self):
        data = metadata()
        data["streams"][0]["tags"] = {"creation_time": "2020-01-01T03:00:00+03:00"}
        data["format"]["tags"] = {"creation_time": "arbitrary informational text"}
        del data["streams"][0]["channel_layout"]
        result = self.parse(data)
        self.assertFalse(result["creation_time"]["trusted"])
        self.assertTrue(result["creation_time"]["informational_only"])
        self.assertIsNone(result["channel_layout"])
        self.assertEqual(result["stream_start_seconds"], 0)
        self.assertEqual(result["duration_human"], "00:00:10.00")

    def test_malformed_excessive_invalid_structures_and_duplicate_keys(self):
        for payload in (b"{broken", b"x" * (MAX_JSON_BYTES + 1), b"[]", b'{"streams":{},"format":{}}',
                        b'{"streams":[null],"format":{}}', b'{"streams":[],"format":null}',
                        b'{"streams":[],"streams":[],"format":{}}', b'{"x":NaN}'):
            with self.subTest(payload=payload[:60]), self.assertRaises(InspectionFailure):
                parse_probe(payload, ".wav")
        data = metadata()
        data["streams"][0]["tags"] = []
        with self.assertRaises(InspectionFailure):
            self.parse(data)

    def test_unsupported_demuxer_no_audio_duplicate_index(self):
        for name in ("flac", "ogg", "", "mov,flac", "wav,mp3"):
            data = metadata()
            data["format"]["format_name"] = name
            with self.subTest(name=name), self.assertRaises(InspectionFailure):
                self.parse(data)
        for streams in ([], [{"index": 0, "codec_type": "audio", "codec_name": "unknown"}],
                        [{"index": 0, "codec_type": "video", "codec_name": "h264"}]):
            data = metadata()
            data["streams"] = streams
            with self.assertRaises(InspectionFailure):
                self.parse(data)
        data = metadata()
        data["streams"].append(copy.deepcopy(data["streams"][0]))
        with self.assertRaises(InspectionFailure):
            self.parse(data)


class ExecutionTests(unittest.TestCase):
    def test_exact_safe_command_and_no_shell_input_interpretation(self):
        path = "managed/İstanbul 🎧; $(never executed).wav"
        command = probe_command("ffprobe", path)
        self.assertEqual(command, ["ffprobe", "-v", "error", "-protocol_whitelist", "file",
                                  "-format_whitelist", "mov,mp3,wav,aac", "-enable_drefs", "0",
                                  "-use_absolute_path", "0", "-show_entries", ENTRIES,
                                  "-of", "json", "-i", path])

    def test_missing_and_execution_failure(self):
        with patch("recorandro.inspection.shutil.which", return_value=None), self.assertRaises(InspectionFailure) as error:
            run_probe("absent", "owned.wav")
        self.assertEqual(error.exception.code, "ffprobe_missing")
        with patch("recorandro.inspection.shutil.which", return_value=sys.executable), \
                patch("recorandro.inspection.subprocess.Popen", side_effect=PermissionError("private path")), \
                self.assertRaises(InspectionFailure) as error:
            run_probe("tool", "owned.wav")
        self.assertNotIn("private path", str(error.exception))

    def helper(self, script):
        return patch("recorandro.inspection.probe_command", return_value=[sys.executable, "-c", script])

    def test_bounded_stdout_stderr_real_helper_processes(self):
        for pipe, size in (("stdout", MAX_JSON_BYTES), ("stderr", MAX_STDERR_BYTES)):
            script = f"import sys; sys.{pipe}.buffer.write(b'x' * {size + 20000})"
            with self.subTest(pipe=pipe), self.helper(script), self.assertRaises(InspectionFailure) as error:
                run_probe(sys.executable, "unused")
            self.assertEqual(error.exception.code, "excessive_output")

    def test_stdout_one_byte_over_limit_is_killed_without_waiting_for_timeout(self):
        script = f"import sys,time; sys.stdout.buffer.write(b'x' * {MAX_JSON_BYTES + 1}); sys.stdout.flush(); time.sleep(60)"
        with self.helper(script), self.assertRaises(InspectionFailure) as error:
            run_probe(sys.executable, "unused")
        self.assertEqual(error.exception.code, "excessive_output")

    def test_shell_false_stdin_and_posix_fd_arguments(self):
        original = subprocess.Popen
        def observed(command, **kwargs):
            self.assertIsInstance(command, list)
            self.assertFalse(kwargs["shell"])
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            self.assertEqual(kwargs["stdout"], subprocess.PIPE)
            self.assertEqual(kwargs["stderr"], subprocess.PIPE)
            if os.name == "posix":
                self.assertEqual(kwargs["pass_fds"], ())
            return original(command, **kwargs)
        with self.helper("print('{}')"), patch("recorandro.inspection.subprocess.Popen", side_effect=observed):
            self.assertEqual(run_probe(sys.executable, "unused").strip(), b"{}")

    def test_nonzero_exit_and_private_diagnostics(self):
        with self.helper("import sys; sys.stderr.write('private/path secret'); sys.exit(7)"), \
                self.assertRaises(InspectionFailure) as error:
            run_probe(sys.executable, "unused")
        self.assertEqual(error.exception.code, "ffprobe_nonzero_exit")
        self.assertNotIn("secret", str(error.exception))

    def test_timeout_kills_process_and_disconnected_stdin(self):
        # Mock only wait's timeout, while spawning/cleaning up a real helper.
        real_wait = subprocess.Popen.wait
        observed = []
        def timeout_once(process, timeout=None):
            if timeout is not None:
                observed.append(timeout)
                raise subprocess.TimeoutExpired("private command", timeout)
            return real_wait(process, timeout)
        with self.helper("import time; time.sleep(60)"), \
                patch.object(subprocess.Popen, "wait", timeout_once), self.assertRaises(InspectionFailure) as error:
            run_probe(sys.executable, "unused")
        self.assertEqual(observed, [30])
        self.assertEqual(error.exception.code, "ffprobe_timeout")
        with self.helper("import sys; assert sys.stdin.read() == ''; print('{}')"):
            self.assertEqual(run_probe(sys.executable, "unused").strip(), b"{}")


class InspectionSessionFixture(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.base = Path(self.folder.name)
        self.config = Config(self.base / "managed")
        self.source = self.base / "İstanbul ders 🎧.wav"
        with wave.open(str(self.source), "wb") as out:
            out.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
            out.writeframes(b"\x00\x00" * 8000)
        with patch.object(OwnedDirectory, "free_bytes", return_value=10**12):
            self.imported = import_audio(self.config, self.source, provision_seconds=60)
        self.session_id = self.imported["session_id"]
        self.directory = self.config.data_root / "sessions" / self.session_id
        self.managed = self.directory / self.imported["audio"]["managed_path"]
        self.contents = self.managed.read_bytes()
        self.addCleanup(self.writable)

    def writable(self):
        for path in self.config.data_root.glob("sessions/*/originals/audio/*"):
            if path.is_file() and not path.is_symlink():
                path.chmod(0o600)

    def record(self):
        return json.loads((self.directory / "session.json").read_text(encoding="utf-8"))

    def write_record(self, record):
        with OwnedDirectory.root(self.directory) as directory:
            directory.atomic_json(record)

    def mocked(self, **kwargs):
        data = metadata()
        data["format"]["size"] = str(len(self.contents))
        with patch("recorandro.inspection.run_probe", return_value=json.dumps(data).encode()):
            return inspect_session(self.config, self.session_id, **kwargs)


class SessionInspectionTests(InspectionSessionFixture):
    def test_existing_step_1_2_zero_photo_session_external_source_gone(self):
        self.assertNotIn("inspection", self.record())
        self.source.unlink()
        before = self.managed.stat()
        result = self.mocked()
        self.assertEqual(result["status"], "probed")
        self.assertEqual(result["integrity"]["before"], result["integrity"]["after"])
        self.assertEqual(self.managed.read_bytes(), self.contents)
        self.assertEqual(self.managed.stat().st_mtime_ns, before.st_mtime_ns)
        after = self.record()
        self.assertEqual(after["audio"], self.imported["audio"])
        self.assertEqual(after["state"], "imported")
        self.assertEqual(after["visual_count"], 0)
        self.assertEqual(after["media_eligibility"], "not_inspected")
        self.assertEqual(after["storage_preflight"], self.imported["storage_preflight"])

    def test_only_managed_original_argument_and_absolute_index_persisted(self):
        def probe(executable, path, **kwargs):
            self.assertEqual(executable, self.config.ffprobe)
            if os.name == "posix":
                self.assertTrue(str(path).startswith("/proc/self/fd/"))
                self.assertEqual(Path(path).read_bytes(), self.contents)
                self.assertEqual(len(kwargs["pass_fds"]), 1)
            else:
                self.assertEqual(path, self.managed)
            data = metadata()
            data["streams"][0]["index"] = 9
            return json.dumps(data).encode()
        with patch("recorandro.inspection.run_probe", side_effect=probe):
            result = inspect_session(self.config, self.session_id)
        self.assertEqual(self.record()["inspection"]["media"]["selected_audio_stream_index"], 9)
        self.assertIn("container_reported_size_mismatch", result["warnings"])

    def test_failure_after_success_invalidates_stale_media_and_retry_success(self):
        first = self.mocked()
        def failed(*args, **kwargs):
            persisted = self.record()["inspection"]
            self.assertEqual(persisted["status"], "probe_pending")
            self.assertIsNone(persisted["media"])
            raise InspectionFailure("ffprobe_nonzero_exit", "Controlled tool failure.")
        with patch("recorandro.inspection.run_probe", side_effect=failed), self.assertRaises(InspectionFailure):
            inspect_session(self.config, self.session_id)
        failed_record = self.record()
        self.assertEqual(failed_record["state"], "imported")
        self.assertEqual(failed_record["audio"], self.imported["audio"])
        self.assertEqual(failed_record["inspection"]["status"], "probe_failed")
        self.assertIsNone(failed_record["inspection"]["media"])
        self.assertEqual(failed_record["inspection"]["integrity"]["after"]["status"], "verified")
        self.assertEqual(self.managed.read_bytes(), self.contents)
        with self.assertRaises(InspectionFailure) as error:
            self.mocked()
        self.assertEqual(error.exception.code, "retry_required")
        retried = self.mocked(retry=True)
        self.assertTrue(retried["retry_requested"])
        self.assertNotEqual(retried["attempt_id"], first["attempt_id"])
        self.assertEqual(retried["status"], "probed")

    def test_response_failures_and_interrupt_recheck_integrity(self):
        for failure in (b"{malformed", b"x" * (MAX_JSON_BYTES + 1),
                        InspectionFailure("ffprobe_missing", "Configured ffprobe is missing."),
                        InspectionFailure("ffprobe_timeout", "ffprobe exceeded 30 seconds."), KeyboardInterrupt()):
            def failed(*args, **kwargs):
                if isinstance(failure, BaseException):
                    raise failure
                return failure
            with self.subTest(failure=type(failure).__name__), \
                    patch("recorandro.inspection.run_probe", side_effect=failed), self.assertRaises(InspectionFailure):
                inspect_session(self.config, self.session_id, retry=True)
            result = self.record()["inspection"]
            self.assertEqual(result["status"], "probe_failed")
            self.assertEqual(result["integrity"]["before"], result["integrity"]["after"])
            self.assertEqual(self.managed.read_bytes(), self.contents)
            self.assertEqual(self.record()["audio"], self.imported["audio"])

    def test_size_and_hash_mismatch_before_probe(self):
        for modified in (b"x", b"x" * len(self.contents)):
            self.managed.chmod(0o600)
            self.managed.write_bytes(modified)
            with patch("recorandro.inspection.run_probe") as probe, self.assertRaises(InspectionFailure) as error:
                inspect_session(self.config, self.session_id, retry=True)
            probe.assert_not_called()
            self.assertIn(error.exception.code, ("original_size_mismatch", "original_hash_mismatch"))
            self.assertEqual(self.record()["state"], "imported")

    def test_changed_original_after_success_or_tool_failure_refused(self):
        for tool_failure in (False, True):
            self.managed.chmod(0o600)
            self.managed.write_bytes(self.contents)
            def mutate(*args, **kwargs):
                self.managed.write_bytes(b"z" * len(self.contents))
                if tool_failure:
                    raise InspectionFailure("ffprobe_timeout", "Controlled timeout.")
                return json.dumps(metadata()).encode()
            with patch("recorandro.inspection.run_probe", side_effect=mutate), self.assertRaises(InspectionFailure):
                inspect_session(self.config, self.session_id, retry=True)
            result = self.record()["inspection"]
            self.assertEqual(result["status"], "probe_failed")
            self.assertEqual(result["integrity"]["after"]["status"], "failed")
            self.assertEqual(result["processing_eligibility"]["status"], "blocked")

    def test_original_path_replacement_after_probe_detected(self):
        original_info = OwnedDirectory.info
        changed = []
        alternate = self.directory / "replacement.wav"
        alternate.write_bytes(self.contents)
        def info(directory, leaf):
            if os.name == "nt" and changed and directory.path == self.managed.parent and leaf == self.managed.name:
                # Windows denies replacement while our read handle is open.
                # Inject the replacement identity into the pathname recheck.
                return alternate.stat()
            return original_info(directory, leaf)
        def replace(*args, **kwargs):
            if os.name == "posix":
                os.replace(alternate, self.managed)
            changed.append(True)
            return json.dumps(metadata()).encode()
        with patch("recorandro.inspection.run_probe", side_effect=replace), \
                patch.object(OwnedDirectory, "info", info), self.assertRaises(InspectionFailure):
            inspect_session(self.config, self.session_id)
        self.assertEqual(self.record()["inspection"]["integrity"]["after"]["status"], "failed")

    def test_managed_path_session_identity_state_hash_schema_validation(self):
        for key, value in (("managed_path", "../../external.wav"), ("managed_path", str(self.source)),
                           ("imported_filename", "../escape.wav"), ("sha256", "bad"), ("size_bytes", True)):
            record = copy.deepcopy(self.imported)
            record["audio"][key] = value
            self.write_record(record)
            with self.subTest(key=key, value=value), patch("recorandro.inspection.run_probe") as probe, \
                    self.assertRaises(InspectionFailure):
                inspect_session(self.config, self.session_id)
            probe.assert_not_called()
        for key, value in (("session_id", "0" * 32), ("state", "failed"), ("schema_version", True)):
            record = copy.deepcopy(self.imported)
            record[key] = value
            self.write_record(record)
            with self.assertRaises(InspectionFailure):
                self.mocked()
        for session_id in ("../escape", str(self.source), "a" * 31, "A" * 32):
            with self.assertRaises(InspectionFailure):
                inspect_session(self.config, session_id)

    def symlink(self, target, link, directory=False):
        try:
            os.symlink(target, link, target_is_directory=directory)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Host cannot create symlink: {exc}")

    def test_managed_original_symlink_refused(self):
        self.managed.chmod(0o600)
        self.managed.unlink()
        self.symlink(self.source, self.managed)
        with patch("recorandro.inspection.run_probe") as probe, self.assertRaises((InspectionFailure, OSError)):
            inspect_session(self.config, self.session_id)
        probe.assert_not_called()
        self.assertEqual(self.source.read_bytes(), self.contents)

    def test_session_metadata_symlink_refused(self):
        outside = self.base / "outside.json"
        outside.write_text(json.dumps(self.imported))
        (self.directory / "session.json").unlink()
        self.symlink(outside, self.directory / "session.json")
        with self.assertRaises((InspectionFailure, OSError, ValueError)):
            self.mocked()
        self.assertEqual(json.loads(outside.read_text()), self.imported)

    def test_managed_directory_and_root_symlink_refused(self):
        alias = self.base / "alias"
        self.symlink(self.config.data_root, alias, True)
        with self.assertRaises((InspectionFailure, OSError, ValueError)):
            inspect_session(Config(alias), self.session_id)
        audio = self.directory / "originals/audio"
        moved = self.directory / "saved-audio"
        audio.rename(moved)
        self.symlink(moved, audio, True)
        with self.assertRaises((InspectionFailure, OSError, ValueError)):
            self.mocked()

    def test_atomic_final_failure_leaves_pending_without_old_success(self):
        self.mocked()
        original = OwnedDirectory.atomic_json
        def failed(directory, record):
            if record["inspection"]["status"] == "probed":
                raise OSError("controlled failure")
            return original(directory, record)
        with patch.object(OwnedDirectory, "atomic_json", failed), self.assertRaises(InspectionFailure):
            self.mocked()
        pending = self.record()["inspection"]
        self.assertEqual(pending["status"], "probe_pending")
        self.assertIsNone(pending["media"])
        self.assertEqual(self.managed.read_bytes(), self.contents)
        self.assertEqual(self.mocked(retry=True)["status"], "probed")

    def test_pending_publication_failure_never_runs_tool(self):
        first = self.mocked()
        with patch.object(OwnedDirectory, "atomic_json", side_effect=OSError("controlled failure")), \
                patch("recorandro.inspection.run_probe") as probe, self.assertRaises(InspectionFailure):
            inspect_session(self.config, self.session_id)
        probe.assert_not_called()
        self.assertEqual(self.record()["inspection"], first)

    def test_atomic_old_or_new_complete_inspection_records(self):
        first = self.mocked()
        replace = os.replace
        statuses = []
        def observed(src, dst, **kwargs):
            old = self.record()["inspection"]
            statuses.append(old["status"])
            pending_path = self.directory / Path(src).name
            new = json.loads(pending_path.read_text(encoding="utf-8"))["inspection"]
            self.assertIn(new["status"], ("probe_pending", "probed"))
            return replace(src, dst, **kwargs)
        with patch("recorandro.storage.os.replace", side_effect=observed):
            self.mocked()
        self.assertEqual(statuses, ["probed", "probe_pending"])
        self.assertNotEqual(self.record()["inspection"]["attempt_id"], first["attempt_id"])

    def test_concurrent_inspection_rejected_lock_released_on_failure(self):
        def competing(*args, **kwargs):
            with self.assertRaises(InspectionFailure) as error:
                inspect_session(self.config, self.session_id, retry=True)
            self.assertEqual(error.exception.code, "inspection_busy")
            raise InspectionFailure("ffprobe_timeout", "Controlled timeout.")
        with patch("recorandro.inspection.run_probe", side_effect=competing), self.assertRaises(InspectionFailure):
            inspect_session(self.config, self.session_id)
        self.assertEqual(self.mocked(retry=True)["status"], "probed")

    def test_cli_json_exit_codes_and_retry_private_failures(self):
        data = json.dumps(metadata()).encode()
        with patch("recorandro.cli.load_config", return_value=self.config):
            with patch("recorandro.inspection.run_probe", return_value=data), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["inspect-session", self.session_id]), 0)
            self.assertTrue(json.loads(output.getvalue())["ok"])
            with patch("recorandro.inspection.run_probe", side_effect=OSError("private/path")), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["inspect-session", self.session_id]), 1)
            self.assertNotIn("private/path", output.getvalue())
            self.assertFalse(json.loads(output.getvalue())["ok"])
            with patch("recorandro.inspection.run_probe", return_value=data), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["inspect-session", self.session_id, "--retry"]), 0)


@unittest.skipUnless(shutil.which("ffprobe"), "Host ffprobe unavailable; real fixture evidence skipped")
class RealProbeTests(InspectionSessionFixture):
    def test_real_wav_probe_and_malformed_media_preserve_originals(self):
        result = inspect_session(self.config, self.session_id)
        self.assertEqual(result["media"]["audio_codec"], "pcm_s16le")
        self.assertEqual(result["media"]["sample_rate"], 8000)
        self.assertEqual(result["media"]["channels"], 1)
        self.assertAlmostEqual(result["media"]["duration_seconds"], 1)
        self.assertEqual(self.managed.read_bytes(), self.contents)
        invalid = self.base / "invalid.wav"
        invalid.write_bytes(b"not audio")
        record = import_audio(self.config, invalid, provision_seconds=60)
        with self.assertRaises(InspectionFailure):
            inspect_session(self.config, record["session_id"])
        path = self.config.data_root / "sessions" / record["session_id"] / record["audio"]["managed_path"]
        self.assertEqual(path.read_bytes(), b"not audio")

    @unittest.skipUnless(shutil.which("ffmpeg"), "Host ffmpeg fixture generator unavailable")
    def test_real_m4a_mp3_raw_aac_and_mov_under_wav_suffix(self):
        for suffix, options, codec in ((".m4a", ["-c:a", "aac", "-f", "ipod"], "aac"),
                                       (".mp3", ["-c:a", "libmp3lame", "-f", "mp3"], "mp3"),
                                       (".aac", ["-c:a", "aac", "-f", "adts"], "aac")):
            with self.subTest(suffix=suffix):
                fixture = self.base / ("fixture" + suffix)
                subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(self.source),
                                *options, str(fixture)], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                               shell=False, timeout=30, check=True)
                record = import_audio(self.config, fixture, provision_seconds=60)
                result = inspect_session(self.config, record["session_id"])
                self.assertEqual(result["media"]["audio_codec"], codec)
                self.assertEqual(result["media"]["demuxer_family"], SUFFIX_FAMILY[suffix])
                self.assertEqual(result["integrity"]["before"], result["integrity"]["after"])
                if suffix == ".aac":
                    self.assertIn("raw_aac_duration_unverified", result["warnings"])
        renamed = self.base / "mov-content.wav"
        renamed.write_bytes((self.base / "fixture.m4a").read_bytes())
        record = import_audio(self.config, renamed, provision_seconds=60)
        result = inspect_session(self.config, record["session_id"])
        self.assertEqual(result["media"]["demuxer_family"], "mov")
        self.assertIn("suffix_demuxer_mismatch", result["warnings"])


SUFFIX_FAMILY = {".m4a": "mov", ".mp3": "mp3", ".aac": "aac"}


if __name__ == "__main__":
    unittest.main()
