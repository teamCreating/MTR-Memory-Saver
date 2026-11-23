import copy
import unittest

from spark_profile_analysis import analyze


def fixture():
    return {"metadata": {"samplerMode": {"name": "EXECUTION", "number": 0},
                         "samplerEngine": {"name": "JAVA", "number": 0}, "interval": 4000,
                         "startTime": 1794977005615, "endTime": 1794977040000},
            "timeWindows": [20, 10], "timeWindowStatistics": {"20": {"players": -1}, "10": {"players": 2}},
            "classSources": {"Root": "host", "Child": "mod"},
            "threads": [{"name": "Render thread", "times": [10, 20], "childrenRefs": [1],
                         "children": [{"className": "Child", "methodName": "work", "times": [4, 5], "childrenRefs": []},
                                      {"className": "Root", "methodName": "run", "times": [10, 20], "childrenRefs": [0]}]}]}


class SparkProfileAnalysisTest(unittest.TestCase):
    def test_flat_direct_children_determine_self_time_and_explicit_window_order(self):
        result = analyze(fixture(), "Render thread")
        self.assertEqual(result["window_sample_weights"], {"20": 10, "10": 20})
        self.assertEqual(result["ranked_self"][0]["self_sample_weight"], 21)
        self.assertEqual(result["metadata"]["interval_ms"], 4)
        self.assertEqual(result["raw_world_statistics"]["20"]["players"], -1)
        self.assertFalse(result["performance_accepted"])

    def test_missing_thread_never_silently_selects_another_thread(self):
        with self.assertRaisesRegex(ValueError, "match exactly once"):
            analyze(fixture(), "Server thread")

    def test_out_of_pool_duplicate_shared_and_orphan_nodes_fail(self):
        cases = []
        value = fixture(); value["threads"][0]["children"][1]["childrenRefs"] = [7]; cases.append(value)
        value = fixture(); value["threads"][0]["children"][1]["childrenRefs"] = [0, 0]; cases.append(value)
        value = fixture(); value["threads"][0]["children"][0]["childrenRefs"] = [1]; cases.append(value)
        value = fixture(); value["threads"][0]["children"][1]["childrenRefs"] = []; cases.append(value)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError): analyze(value, "Render thread")

    def test_missing_negative_nonfinite_and_misaligned_weights_are_rejected(self):
        for weights in ([1], [-1, 2], [float("nan"), 2]):
            value = fixture(); value["threads"][0]["children"][0]["times"] = weights
            with self.subTest(weights=weights), self.assertRaises(ValueError): analyze(value, "Render thread")
        value = fixture(); value["threads"][0]["times"] = [9, 19]
        with self.assertRaisesRegex(ValueError, "disagree"): analyze(value, "Render thread")

    def test_negative_self_residual_is_retained_as_quality_diagnostic(self):
        value = fixture(); value["threads"][0]["children"][0]["times"] = [11, 5]
        result = analyze(value, "Render thread")
        self.assertEqual(result["negative_self_residuals"], [{"node": 1, "window": 20, "residual": -1}])
        root = next(row for row in result["ranked_self"] if row["class"] == "Root")
        self.assertEqual(root["self_sample_weight"], 15)

    def test_allocation_profile_cannot_be_interpreted_as_execution_time(self):
        value = copy.deepcopy(fixture()); value["metadata"]["samplerMode"]["name"] = "ALLOCATION"
        with self.assertRaisesRegex(ValueError, "own metric interpretation"): analyze(value, "Render thread")
