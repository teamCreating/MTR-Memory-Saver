"""Synthetic live-trace controls; no client or native call is manufactured."""
import copy
import unittest

import native_diagnostic_review as review_tool

from minecraft_testkit import ROOT
from minecraft_testkit.fixtures.diagnostics import fixture, evaluate


class NativeDiagnosticReviewTests(unittest.TestCase):
    def test_complete_trace_classifies_only_known_live_default_and_keeps_raw_line(self):
        case = fixture()
        result = evaluate(case)
        self.assertTrue(result["native_attribution"]["passed"], result)
        self.assertEqual(result["unreviewed_native"], [])
        self.assertEqual(result["reviewed_native"][0]["text"], case["log"].strip())
        review_tool.validate_review(case["review"], case["metadata"], root=ROOT)

    def test_other_native_errors_and_non_native_errors_are_not_masked(self):
        case = fixture()
        case["log"] += "[main/ERROR] [MinecraftTransitRailway/]: Failed to decode resource x\n[main/ERROR] [authlib/]: HTTP 401\n"
        result = evaluate(case)
        self.assertTrue(result["native_attribution"]["passed"])
        self.assertEqual(len(result["unreviewed_native"]), 1)
        self.assertEqual(len(result["other_errors_requiring_contextual_review"]), 1)

    def test_missing_extra_reordered_unfinished_or_transplanted_events_fail_closed(self):
        for mutate in (lambda c: c["events"].clear(), lambda c: c["events"].pop(),
                       lambda c: c["events"].append(copy.deepcopy(c["events"][-1])),
                       lambda c: c["events"].reverse(), lambda c: c["events"][1].update(pid=112),
                       lambda c: c["events"][2].update(call_id=2), lambda c: c["events"][1].update(epoch_id=None),
                       lambda c: c["events"][1].update(thread_id=2), lambda c: c["events"][1].update(render_thread=False),
                       lambda c: c["events"][1].update(native_reload_nesting=2),
                       lambda c: c["events"][1].update(timestamp="2026-11-14T00:00:00Z"),
                       lambda c: c["events"][1].update(monotonic_nanos=1),
                       lambda c: c["events"][2].update(observation_errors=1),
                       lambda c: c["events"][1]["target"].update(observer_version="old")):
            case = fixture()
            # metadata is shared by fixture events, as a decoded file would not be.
            case["events"] = copy.deepcopy(case["events"])
            mutate(case)
            result = evaluate(case)
            self.assertFalse(result["native_attribution"]["passed"], result)
            self.assertEqual(len(result["unreviewed_native"]), 1)
            self.assertEqual(result["reviewed_native"], [])

    def test_wrong_factory_arguments_descriptor_callsite_or_return_stays_unreviewed(self):
        for mutate in (lambda c: c["events"][1].update(model_resource="missing.model"),
                       lambda c: c["events"][1].update(texture_resource="other.png"),
                       lambda c: c["events"][1].update(flip_texture_v=True),
                       lambda c: c["events"][2].update(returned_loader_class="OtherLoader"),
                       lambda c: c["events"][1]["stack"][1].update(descriptor="(LReader;)V"),
                       lambda c: c["events"][2]["stack"][1].update(bytecode_index=999),
                       lambda c: c["events"][1]["stack"][2].update(method="anotherReload")):
            case = fixture()
            mutate(case)
            result = evaluate(case)
            self.assertFalse(result["native_attribution"]["passed"], result)
            self.assertEqual(len(result["unreviewed_native"]), 1)

    def test_extra_missing_newline_or_other_texture_log_diagnostics_fail_closed(self):
        for mutate in (lambda c: c.update(log=c["log"] * 2), lambda c: c.update(log=""),
                       lambda c: c.update(log=c["log"].replace("transparent.png", "other.png")),
                       lambda c: c.update(log=c["log"].replace("Render thread", "Worker thread")),
                       lambda c: c.update(log=c["log"].replace("MinecraftTransitRailway", "DifferentLogger")),
                       lambda c: c.update(log=c["log"].replace("Invalid model!", "Invalid\nmodel!"))):
            case = fixture()
            mutate(case)
            self.assertFalse(evaluate(case)["native_attribution"]["passed"])

    def test_final_counter_and_snapshot_gaps_cannot_be_silently_accepted(self):
        for mutate in (lambda c: c["snapshot"].pop("native_model_diagnostics"),
                       lambda c: c["snapshot"]["native_model_diagnostics"].update(started=2, in_flight=1),
                       lambda c: c["snapshot"]["native_model_diagnostics"].update(observation_errors=1),
                       lambda c: c["snapshot"].update(observed_at="2026-11-15T00:00:00Z"),
                       lambda c: c["snapshot"].update(pid=112), lambda c: c["epochs"].pop()):
            case = fixture()
            mutate(case)
            self.assertFalse(evaluate(case)["native_attribution"]["passed"])

    def test_review_cannot_broaden_to_other_models_or_targets(self):
        for mutate in (lambda c: c["review"]["contract"].update(model_resource="any"),
                       lambda c: c["review"]["target"].update(mtrSha256="changed"),
                       lambda c: c["review"]["contract"].update(calls_per_completed_epoch=2),
                       lambda c: c["review"].update(proofs=[])):
            case = fixture()
            mutate(case)
            self.assertFalse(evaluate(case)["native_attribution"]["passed"])


if __name__ == "__main__":
    unittest.main()
