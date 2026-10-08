import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from recorandro.cli import main
from recorandro.config import Config, ConfigError, load_config
from recorandro.diagnostics import check_data_root, doctor, environment, run_tool, tool_version


class ConfigTests(unittest.TestCase):
    def test_explicit_root_required(self):
        with self.assertRaises(ConfigError):
            load_config(env={})

    def test_file_relative_root_and_environment_precedence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            path.write_text(json.dumps({"data_root": "owned", "ffmpeg": "file-tool"}))
            config = load_config(str(path), env={})
            self.assertEqual(config.data_root, (Path(folder) / "owned").resolve())
            self.assertFalse(config.data_root.exists())
            root = str(Path(folder) / "override")
            config = load_config(str(path), env={"RECORANDRO_DATA_ROOT": root,
                                                 "RECORANDRO_FFMPEG": "env-tool"})
            self.assertEqual(config.data_root, Path(root).resolve())
            self.assertEqual(config.ffmpeg, "env-tool")

    def test_environment_config_file_and_cli_override(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            path.write_text('{"data_root":"owned"}')
            self.assertEqual(load_config(env={"RECORANDRO_CONFIG": str(path)}).data_root,
                             (Path(folder) / "owned").resolve())
            self.assertEqual(load_config(str(path), {"RECORANDRO_CONFIG": "missing"}).data_root,
                             (Path(folder) / "owned").resolve())

    def test_bad_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            for contents in ("not json", "[]", '{"data_root":false}',
                             '{"data_root":"owned","unknown":1}',
                             '{"data_root":"owned","ffmpeg":[]}', "x" * 65537):
                path.write_text(contents)
                with self.subTest(contents=contents[:70]), self.assertRaises(ConfigError):
                    load_config(str(path), {})
            with self.assertRaises(ConfigError):
                load_config(str(Path(folder) / "missing"), {})
        for root in ("", "relative", str(Path.cwd().anchor), "bad\x00path"):
            with self.subTest(root=root), self.assertRaises(ConfigError):
                load_config(env={"RECORANDRO_DATA_ROOT": root})


class DiagnosticsTests(unittest.TestCase):
    def test_write_probe_free_space_and_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "owned"
            report = check_data_root(root)
            self.assertTrue(report["writable"])
            self.assertIsInstance(report["available_bytes"], int)
            self.assertGreaterEqual(report["available_bytes"], 0)
            self.assertEqual(list(root.iterdir()), [])

    def test_invalid_root_and_permission_denied(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "file"
            path.write_text("existing")
            self.assertFalse(check_data_root(path)["writable"])
            with patch("recorandro.diagnostics.tempfile.TemporaryFile", side_effect=PermissionError("denied")):
                report = check_data_root(Path(folder))
                self.assertFalse(report["writable"])
                self.assertIn("denied", report["error"])

    def test_safe_subprocess_array_timeout_and_bounded_output(self):
        def fake_run(args, **kwargs):
            self.assertEqual(args, ["tool", "path with spaces; $(ignored)"])
            self.assertFalse(kwargs["shell"])
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            self.assertEqual(kwargs["timeout"], 30)
            kwargs["stdout"].write(b"x" * 70000)
            return subprocess.CompletedProcess(args, 0)
        with patch("recorandro.diagnostics.subprocess.run", side_effect=fake_run):
            report = run_tool(["tool", "path with spaces; $(ignored)"])
            self.assertTrue(report["truncated"])
            self.assertEqual(len(report["output"]), 65536)
        for error in (FileNotFoundError("missing"), subprocess.TimeoutExpired("tool", 30)):
            with patch("recorandro.diagnostics.subprocess.run", side_effect=error):
                self.assertIsNone(run_tool(["tool"])["returncode"])

    def test_missing_and_failed_version(self):
        with patch("recorandro.diagnostics.shutil.which", return_value=None):
            self.assertFalse(tool_version("absent")["ok"])
        with patch("recorandro.diagnostics.shutil.which", return_value="tool"), \
             patch("recorandro.diagnostics.run_tool", return_value={"returncode": 1, "output": "failure"}):
            self.assertFalse(tool_version("tool")["ok"])

    def test_termux_detection_never_calls_su(self):
        with patch.dict(os.environ, {"PREFIX": "/data/data/com.termux/files/usr", "TERMUX_VERSION": "test"}), \
             patch("recorandro.diagnostics.run_tool") as run:
            report = environment()
            self.assertTrue(report["termux_detected"])
            self.assertEqual(report["termux_version"], "test")
            self.assertFalse(any(call.args[0][0] == "su" for call in run.call_args_list))

    def test_doctor_failure_keeps_android_pending(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch("recorandro.diagnostics.tool_version", return_value={"ok": False}):
            report = doctor(Config(Path(folder)))
            self.assertFalse(report["ok"])
            self.assertIn("PENDING", report["android_capability_validation"])

    def test_cli_json_logging_and_status(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.dict(os.environ, {"RECORANDRO_DATA_ROOT": folder, "RECORANDRO_CONFIG": ""}), \
             patch("recorandro.cli.load_config", return_value=Config(Path(folder))), \
             patch("recorandro.diagnostics.tool_version", return_value={"ok": True}):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(main(["doctor", "--json"]), 0)
            self.assertTrue(json.loads(stdout.getvalue())["data_root"]["writable"])
            contents = (Path(folder) / "recorandro.log").read_text()
            self.assertIn("doctor completed: ok", contents)
            self.assertNotIn(folder, contents)
            self.assertNotIn("ffmpeg", contents)

    def test_cli_config_and_logging_failure(self):
        with patch("recorandro.cli.load_config", side_effect=ConfigError("required")), \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["doctor"]), 2)
        with tempfile.TemporaryDirectory() as folder, \
             patch("recorandro.cli.load_config", return_value=Config(Path(folder))), \
             patch("recorandro.diagnostics.tool_version", return_value={"ok": True}), \
             patch("recorandro.cli.log_result", side_effect=OSError("denied")), \
             contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main(["doctor", "--json"]), 1)
            self.assertIn("logging_error", json.loads(stdout.getvalue()))


if __name__ == "__main__":
    unittest.main()
