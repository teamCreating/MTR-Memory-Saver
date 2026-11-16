import copy
import unittest

from analyze_native_model_trace import analyze


class NativeTraceTests(unittest.TestCase):
    def setUp(self):
        self.target = {"fixture": True}
        self.log = "[test] [mtr:textures/block/transparent.png] Invalid model!"
        base = {"schema_version": 1, "pid": 123, "process_started_at": "2026-11-16T00:00:00Z", "target": self.target,
                "thread_id": 1, "observation_errors": 0, "model_resource": "", "texture_resource": "", "flip_texture_v": False,
                "timestamp": "2026-11-16T00:00:01Z", "stack": [
                    {"class": "org.mtr.resource.VehicleModel", "method": "getModelLoaderBase"},
                    {"class": "org.mtr.resource.RailResource", "method": "<init>"},
                    {"class": "org.mtr.client.CustomResourceLoader", "method": "reload"}]}
        self.events = [dict(copy.deepcopy(base), phase=phase, sequence=i + 1, monotonic_nanos=i + 1,
                            returned_loader_class="org.mtr.model.BlockbenchModelLoader")
                       for i, phase in enumerate(("installed", "before_native_invalid_log", "native_fallback_return"))]

    def check(self, events=None, log=None):
        return analyze(events or self.events, self.log if log is None else log, self.target, 123, "2026-11-16T00:00:00Z")

    def test_generated_call_is_attributed_without_general_acceptance(self):
        result = self.check()
        self.assertTrue(result["all_captured_invalid_calls_attributed"])
        self.assertNotIn("passed", result)

    def test_extra_log_or_missing_return_rejected(self):
        for events, log in ((self.events, self.log + "\n" + self.log), (self.events[:-1], self.log), (self.events, "")):
            with self.subTest(events=len(events), log=log), self.assertRaises(ValueError): self.check(events, log)

    def test_other_constructor_or_nonempty_model_remains_unattributed(self):
        for field in ("stack", "model_resource"):
            rows = copy.deepcopy(self.events)
            for row in rows[1:]:
                if field == "stack": row["stack"][1]["class"] = "org.mtr.resource.ObjectResource"
                else: row[field] = "broken.unsupported"
            self.assertFalse(self.check(rows)["all_captured_invalid_calls_attributed"])

    def test_wrong_process_target_sequence_or_observation_error_rejected(self):
        for field, value in (("pid", 124), ("process_started_at", "wrong"), ("sequence", 20), ("target", {}),
                             ("observation_errors", 1), ("returned_loader_class", "unexpected"), ("monotonic_nanos", 0)):
            rows = copy.deepcopy(self.events); rows[2][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.check(rows)

    def test_changed_native_arguments_or_caller_rejected(self):
        rows = copy.deepcopy(self.events); rows[2]["texture_resource"] = "different"
        with self.assertRaises(ValueError): self.check(rows)
        rows = copy.deepcopy(self.events); rows[2]["stack"][1]["method"] = "other"
        with self.assertRaises(ValueError): self.check(rows)

    def test_raw_diagnostic_failure_and_wrong_identifier_rejected(self):
        for log in (self.log + "\nNative model diagnostic observation failed", self.log.replace("transparent", "different")):
            with self.assertRaises(ValueError): self.check(log=log)


if __name__ == "__main__":
    unittest.main()
