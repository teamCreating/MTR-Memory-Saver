from contextlib import contextmanager
import copy
import ctypes
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.frame_diagnostics import etw_diagnostic as diagnostic
from tools.frame_diagnostics.contract import fingerprint
from .test_frame_contract import FIXTURES, TARGET, WINDOW


class FakeBackend:
    """Synthetic only: never starts ETW, GL, a JVM, or any operating-system helper."""
    def __init__(self, root, csv=True, change_identity=False, foreign_session=False):
        self.system32 = root / "system32"
        self.system32.mkdir()
        for name in ("logman.exe", "tracerpt.exe"):
            (self.system32 / name).write_bytes(b"synthetic helper identity; never run")
        self.has_csv, self.change_identity, self.foreign_session = csv, change_identity, foreign_session
        self.running = None
        self.stopped, self.labels, self.observations, self.clocks = [], [], 0, 0

    @contextmanager
    def target(self, expected):
        def observe():
            self.observations += 1
            return {**expected, "created": "2026-01-01T00:00:10Z"} if self.change_identity and self.observations > 1 else dict(expected)
        yield observe

    def query(self, session):
        if self.foreign_session:
            return {"session_name": session, "status": 5, "counters": None}
        return dict(self.running) if self.running else {"session_name": session, "status": 4201, "counters": None}

    def clock(self):
        key = "start" if self.clocks == 0 else "end"
        self.clocks += 1
        return {**WINDOW[key], "frequency_hz": WINDOW["frequency_hz"]}

    def sleep(self, duration):
        assert duration == 25

    def stop_owned(self, token):
        assert token == self.running
        self.stopped.append(token["session_name"])
        self.running = None
        return {**token, "operation": "owned_session_stop", "counters": {"EventsLost": 0, "LogBuffersLost": 0, "RealTimeBuffersLost": 0}}

    def run(self, argv, folder, label):
        self.labels.append(label)
        if label == "start":
            self.running = {"session_name": argv[3], "status": 0, "guid": "00000000-0000-4000-8000-000000000002", "trace_handle": 123}
            (folder / "raw.etl").write_bytes(b"synthetic ETL fixture; not a real trace")
        elif label == "headers":
            (folder / "headers.xml").write_bytes((FIXTURES / "headers.xml").read_bytes())
            (folder / "tracerpt-summary.txt").write_text("synthetic summary; not parsed as a loss guarantee")
        elif label == "replay" and self.has_csv:
            (folder / "presents.csv").write_bytes((FIXTURES / "presents.csv").read_bytes())
        for stream in ("stdout", "stderr"):
            (folder / f"{label}.{stream}.log").write_bytes(b"synthetic-only" if stream == "stdout" else b"")
        receipt = {"argv": argv, "cwd": str(folder), "owner_pid": __import__("os").getpid(), "helper_pid": 999,
                   "exit_code": 0, "helper_exited": True, "started": "2026-01-01T00:00:00Z", "ended": "2026-01-01T00:00:25Z",
                   "stdout": fingerprint(folder / f"{label}.stdout.log"), "stderr": fingerprint(folder / f"{label}.stderr.log")}
        receipt["executable"] = receipt["executable_after"] = {"path": str(Path(argv[0]).resolve()), **fingerprint(argv[0])}
        diagnostic.write_new(folder / f"{label}.exit.json", receipt)
        diagnostic.write_new(folder / f"{label}.execution.json", receipt)
        return receipt


class FrameDiagnosticTest(unittest.TestCase):
    def prepare(self, root):
        binary = root / "synthetic-presentmon.exe"
        binary.write_bytes(b"synthetic executable identity; never run")
        profile = diagnostic.load_profile()
        profile["presentmon_sha256"] = fingerprint(binary)["sha256"]
        path = root / "profile.json"
        path.write_text(json.dumps(profile), encoding="utf-8")
        return binary, path

    def test_mock_capture_owns_one_session_and_raw_inventory_recomputes_without_metrics_aliases(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            binary, profile = self.prepare(root)
            backend = FakeBackend(root)
            folder = root / ".cache" / "one"
            report = diagnostic.capture_diagnostic(folder, TARGET, binary, backend=backend, repo=root, profile_path=profile)
            self.assertTrue(report["data_source_available"])
            self.assertFalse(report["sampling_window_ready"])  # This provider subset has not been qualified.
            self.assertFalse(report["performance_accepted"])
            self.assertEqual(backend.labels, ["start", "headers", "replay"])
            self.assertEqual(len(backend.stopped), 1)
            unchecked = diagnostic.inspect_bundle(folder)
            self.assertTrue(unchecked["serialized_present_records_available"])
            self.assertFalse(unchecked["data_source_available"])
            raw = (folder / "presents.csv").read_bytes()
            (folder / "presents.csv").write_bytes(raw + b"tamper")
            with self.assertRaisesRegex(ValueError, "bytes changed"):
                diagnostic.inspect_bundle(folder)

    def test_zero_decoder_exit_without_csv_keeps_the_actual_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            binary, profile = self.prepare(root)
            backend = FakeBackend(root, csv=False)
            folder = root / ".cache" / "no-csv"
            report = diagnostic.capture_diagnostic(folder, TARGET, binary, backend=backend, repo=root, profile_path=profile)
            self.assertFalse(report["data_source_available"])
            self.assertFalse(report["csv"]["exists"])
            self.assertEqual(json.loads((folder / "replay.exit.json").read_text())["exit_code"], 0)
            self.assertIn("unclassified", report["csv_failure_attribution"])

    def test_permission_error_is_not_absence_and_does_not_start_or_stop_any_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            binary, profile = self.prepare(root)
            backend = FakeBackend(root, foreign_session=True)
            folder = root / ".cache" / "denied"
            with self.assertRaisesRegex(ValueError, "definitively absent"):
                diagnostic.capture_diagnostic(folder, TARGET, binary, backend=backend, repo=root, profile_path=profile)
            self.assertEqual(backend.labels, [])
            self.assertEqual(backend.stopped, [])
            self.assertFalse(json.loads((folder / "assessment.json").read_text())["data_source_available"])

    def test_partial_start_failure_still_closes_its_created_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            binary, profile = self.prepare(root)
            backend = FakeBackend(root)
            original = backend.run
            def denied(argv, folder, label):
                receipt = original(argv, folder, label)
                if label == "start":
                    receipt["exit_code"] = 2147942405
                return receipt
            backend.run = denied
            folder = root / ".cache" / "partial-start"
            with self.assertRaisesRegex(ValueError, "Session start failed"):
                diagnostic.capture_diagnostic(folder, TARGET, binary, backend=backend, repo=root, profile_path=profile)
            self.assertEqual(backend.labels, ["start"])
            self.assertEqual(len(backend.stopped), 1)
            self.assertEqual(json.loads((folder / "session-after.json").read_text())["status"], 4201)

    def test_target_change_closes_only_its_session_and_cannot_publish_availability(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            binary, profile = self.prepare(root)
            backend = FakeBackend(root, change_identity=True)
            folder = root / ".cache" / "changed"
            result = diagnostic.capture_diagnostic(folder, TARGET, binary, backend=backend, repo=root, profile_path=profile)
            self.assertFalse(result["data_source_available"])
            self.assertEqual(len(backend.stopped), 1)

    def test_raw_outputs_cannot_escape_cache_and_prior_attempt_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for path in (root / "evidence" / "trace", root / ".cache" / ".." / "outside"):
                with self.assertRaises(ValueError): diagnostic.private_output(path, root)
            existing = root / ".cache" / "existing"
            existing.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "already exists"): diagnostic.private_output(existing, root)

    def test_profile_rejects_dxgkrnl_performance_mask_and_preserves_offline_replay_flags(self):
        with tempfile.TemporaryDirectory() as temporary:
            p = Path(temporary) / "profile.json"
            profile = diagnostic.load_profile()
            profile["providers"][0]["keywords"] = "0x4000000000000001"
            p.write_text(json.dumps(profile))
            with self.assertRaisesRegex(ValueError, "Performance"): diagnostic.load_profile(p)
        plan = diagnostic.commands(Path("cache"), Path("PresentMon.exe"), "owned", 42, 25, diagnostic.load_profile(), Path("system32"))
        self.assertIn("--etl_file", plan["replay"])
        self.assertIn("--v1_metrics", plan["replay"])
        self.assertNotIn("--v2_metrics", plan["replay"])
        self.assertNotIn("--stop_existing_session", plan["replay"])
        self.assertNotIn("--restart_as_admin", plan["replay"])
        self.assertNotIn("-lr", plan["headers"])
        self.assertNotIn("-rts", plan["headers"])  # UTC headers and summary, not falsely labeled QPC.
        self.assertEqual(ctypes.sizeof(diagnostic.Wnode), 48)
        self.assertEqual(ctypes.sizeof(diagnostic.TraceProperties), 120)

    def test_real_owned_ordinary_child_exit_is_persisted_before_post_exit_hash_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            def fail_stdout(path):
                if str(path).endswith(".stdout.log"): raise OSError("post-exit read failed")
                return fingerprint(path)
            with patch.object(diagnostic, "fingerprint", side_effect=fail_stdout):
                with self.assertRaises(OSError): diagnostic.run_command([sys.executable, "-c", "raise SystemExit(7)"], folder, "ordinary-child")
            receipt = json.loads((folder / "ordinary-child.exit.json").read_text())
            self.assertEqual(receipt["exit_code"], 7)
            self.assertTrue(receipt["helper_exited"])

    def test_start_receipt_write_error_still_waits_for_the_owned_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            original = diagnostic.write_new
            def write(path, value):
                if str(path).endswith("ordinary-child.start.json"): raise OSError("controlled start receipt failure")
                return original(path, value)
            with patch.object(diagnostic, "write_new", side_effect=write):
                with self.assertRaises(OSError): diagnostic.run_command([sys.executable, "-c", "raise SystemExit(0)"], folder, "ordinary-child")
            self.assertEqual(json.loads((folder / "ordinary-child.exit.json").read_text())["exit_code"], 0)

    def test_independent_offline_replay_rejects_rehashed_edited_csv(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            binary, profile = self.prepare(root)
            backend = FakeBackend(root)
            folder = root / ".cache" / "one"
            diagnostic.capture_diagnostic(folder, TARGET, binary, backend=backend, repo=root, profile_path=profile)
            def replay(argv, destination, label):
                (destination / ("headers.xml" if label.endswith("headers") else "presents.csv")).write_bytes(
                    (FIXTURES / ("headers.xml" if label.endswith("headers") else "presents.csv")).read_bytes())
                return {"exit_code": 0}
            checked = diagnostic.inspect_bundle(folder, root / ".cache" / "checked", runner=replay, repo=root)
            self.assertTrue(checked["data_source_available"])
            self.assertTrue(checked["independent_raw_etl_replay_verified"])
            original = (folder / "presents.csv").read_text()
            (folder / "presents.csv").write_text(original.replace("3999", "3998"), encoding="utf-8")
            inventory = json.loads((folder / "inventory.json").read_text())
            inventory["files"]["presents.csv"] = fingerprint(folder / "presents.csv")
            (folder / "inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "CSV bytes differ"):
                diagnostic.inspect_bundle(folder, root / ".cache" / "reject", runner=replay, repo=root)

    def test_replaced_trace_guid_is_not_stopped_even_with_the_same_name(self):
        backend = object.__new__(diagnostic.WindowsBackend)
        token = {"session_name": "mtr-frame-diagnostic-00000000-0000-4000-8000-000000000001", "guid": "original", "trace_handle": 7}
        backend.query = unittest.mock.Mock(return_value={**token, "status": 0, "guid": "replacement"})
        backend._control = unittest.mock.Mock()
        with self.assertRaisesRegex(ValueError, "identity changed"):
            backend.stop_owned(token)
        backend._control.assert_not_called()
