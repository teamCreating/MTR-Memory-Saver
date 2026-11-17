import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.frame_diagnostics.contract import decision, inspect_csv, inspect_headers, validate_window


FIXTURES = Path(__file__).with_name("fixtures")
TARGET = {"pid": 42, "created": "2025-12-31T23:00:00Z", "executable": "C:/synthetic/java.exe", "command": "synthetic-only --gameDir fixture"}
SESSION = "mtr-frame-diagnostic-00000000-0000-4000-8000-000000000001"
GUID = "00000000-0000-4000-8000-000000000002"
WINDOW = {"frequency_hz": 1000, "session_name": SESSION, "session_guid": GUID,
    "start": {"qpc_before": 1000000, "qpc_after": 1000001, "utc_between_qpc_reads": "2026-01-01T00:00:00Z"},
    "end": {"qpc_before": 1025000, "qpc_after": 1025001, "utc_between_qpc_reads": "2026-01-01T00:00:25Z"}}
STOP = {"status": 0, "operation": "owned_session_stop", "session_name": SESSION, "guid": GUID,
        "counters": {"EventsLost": 0, "LogBuffersLost": 0, "RealTimeBuffersLost": 0}}


class FrameContractTest(unittest.TestCase):
    def test_synthetic_positive_keeps_present_native_frame_and_cpu_semantics_separate(self):
        csv = inspect_csv(FIXTURES / "presents.csv", TARGET, WINDOW)
        headers = inspect_headers(FIXTURES / "headers.xml", TARGET)
        result = decision(TARGET, TARGET, WINDOW, csv, headers, STOP)
        self.assertTrue(result["data_source_available"])
        self.assertTrue(result["sampling_window_ready"])
        self.assertIsNone(result["native_frame_p99_ms"])
        self.assertIsNone(result["process_cpu_seconds"])
        self.assertFalse(result["calibration_accepted"])
        self.assertFalse(result["performance_accepted"])
        self.assertEqual(csv["chains"]["0x1234"]["present_runtime_values"], ["Other"])
        self.assertIn("Not inferred", result["opengl_identification"])

    def test_no_csv_and_empty_csv_are_not_zero_measurements_or_availability(self):
        self.assertFalse(inspect_csv(None, TARGET, WINDOW)["present_records_available"])
        with tempfile.TemporaryDirectory() as temporary:
            p = Path(temporary) / "empty.csv"
            p.write_text((FIXTURES / "presents.csv").read_text().splitlines()[0] + "\n")
            result = inspect_csv(p, TARGET, WINDOW)
            self.assertFalse(result["present_records_available"])
            self.assertEqual(result["rows"], 0)
            self.assertTrue(result["errors"])

    def test_corrupt_pid_qpc_missing_values_duplicate_headers_and_legacy_aliases_fail_closed(self):
        raw = (FIXTURES / "presents.csv").read_text()
        variants = [raw.replace(",42,", ",43,", 1), raw.replace("1024999", "1026000"),
                    raw.replace("1004000", "1000001"), raw.replace(",3999,", ",NA,"),
                    raw.replace(",3999,", ",NaN,"), raw.replace("TimeInQPC", "CPUStartTime"),
                    raw.replace("MsCPUBusy", "ProcessID"), raw.replace(",3999,", ",-1,")]
        with tempfile.TemporaryDirectory() as temporary:
            for index, text in enumerate(variants):
                with self.subTest(index=index):
                    p = Path(temporary) / f"{index}.csv"
                    p.write_text(text, encoding="utf-8")
                    report = inspect_csv(p, TARGET, WINDOW)
                    self.assertTrue(report["errors"])
                    self.assertFalse(report["present_records_available"])

    def test_truncated_window_does_not_become_complete_by_dropping_boundary_gaps(self):
        with tempfile.TemporaryDirectory() as temporary:
            p = Path(temporary) / "partial.csv"
            p.write_text("\n".join((FIXTURES / "presents.csv").read_text().splitlines()[:3]) + "\n")
            report = inspect_csv(p, TARGET, WINDOW)
            self.assertTrue(report["present_records_available"])
            self.assertFalse(report["window_covered"])

    def test_utf16_bom_is_explicitly_decoded_without_locale_guessing(self):
        with tempfile.TemporaryDirectory() as temporary:
            p = Path(temporary) / "utf16.csv"
            p.write_bytes((FIXTURES / "presents.csv").read_text().encode("utf-16"))
            self.assertTrue(inspect_csv(p, TARGET, WINDOW)["present_records_available"])

    def test_header_writer_pid_is_not_the_process_id_inside_payload(self):
        result = inspect_headers(FIXTURES / "headers.xml", TARGET)
        self.assertTrue(result["all_headers_decoded"])
        self.assertEqual(result["header_writer_pid_counts"], {"42": 1, "4": 1})
        self.assertEqual(result["target_header_writer_events"], 1)
        self.assertNotIn("999", result["header_writer_pid_counts"])
        self.assertFalse(result["target_presents_claim"])

    def test_missing_guid_or_execution_and_xml_entities_are_not_silently_counted(self):
        raw = (FIXTURES / "headers.xml").read_text()
        with tempfile.TemporaryDirectory() as temporary:
            p = Path(temporary) / "bad.xml"
            for text in (raw.replace('Guid="{802EC45A-1E99-4B83-9920-87C98277BA9D}"', 'Name="DxgKrnl"'),
                         raw.replace('ProcessID="42"', 'Writer="42"', 1)):
                p.write_text(text)
                self.assertFalse(inspect_headers(p, TARGET)["all_headers_decoded"])
            p.write_bytes(('<!DOCTYPE Events [<!ENTITY x "payload">]>' + raw.split("?>", 1)[1]).encode("utf-16"))
            with self.assertRaisesRegex(ValueError, "entity/DTD"):
                inspect_headers(p, TARGET)

    def test_querypoint_zero_loss_or_another_session_never_certifies_the_whole_window(self):
        csv, headers = inspect_csv(FIXTURES / "presents.csv", TARGET, WINDOW), inspect_headers(FIXTURES / "headers.xml", TARGET)
        for change in ({"operation": "session_query"}, {"guid": "different"}, {"status": 4201, "counters": None}):
            with self.subTest(change=change):
                stop = {**STOP, **change}
                result = decision(TARGET, TARGET, WINDOW, csv, headers, stop)
                self.assertFalse(result["whole_owned_session_loss_known"])
                self.assertFalse(result["sampling_window_ready"])
        lost = copy.deepcopy(STOP)
        lost["counters"]["EventsLost"] = 1
        self.assertFalse(decision(TARGET, TARGET, WINDOW, csv, headers, lost)["sampling_window_ready"])

    def test_pid_reuse_and_inconsistent_clock_relationship_are_rejected(self):
        csv, headers = inspect_csv(FIXTURES / "presents.csv", TARGET, WINDOW), inspect_headers(FIXTURES / "headers.xml", TARGET)
        changed = {**TARGET, "created": "2026-01-01T00:00:10Z"}
        self.assertFalse(decision(TARGET, changed, WINDOW, csv, headers, STOP)["data_source_available"])
        bad = copy.deepcopy(WINDOW)
        bad["end"]["utc_between_qpc_reads"] = "2026-01-01T01:00:25Z"
        with self.assertRaisesRegex(ValueError, "UTC/QPC"):
            validate_window(bad)
