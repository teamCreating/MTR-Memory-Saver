import copy
import unittest

import client_outlier_analysis as outliers


class OutlierTests(unittest.TestCase):
    def fixture(self, count):
        policy = outliers.read(outliers.DEFAULT_POLICY)
        assessment = {"all_12_trials_qualified": True, "errors": [], "trials": {}}
        schedule = {"schedule": []}
        for pair in range(count):
            for role in policy["roles"]:
                identifier = f"{pair}-{role}"
                schedule["schedule"].append({"id": identifier, "pair": pair, "mode": "plain",
                                             "role": role, "comparison": "ab"})
                assessment["trials"][identifier] = {
                    "mode": "plain", "role": role,
                    "metrics": {"loading_ms": 100 + pair, "steady_private_bytes": 1000},
                }
        return assessment, schedule, policy

    def test_sparse_groups_preserve_all_pairs_and_show_missing_sensitivity(self):
        args = self.fixture(2)
        before = copy.deepcopy(args)
        result = outliers.analyze(*args)
        self.assertEqual(args, before)
        self.assertEqual(result["excluded_pairs"], [])
        self.assertTrue(all(group["status"] == "insufficient_replicates" for group in result["groups"]))
        single = outliers.analyze(*self.fixture(1))
        self.assertIsNone(single["modes"]["plain"]["leave_one_pair_out"][0]["result"]["loading_ms"]["median_percent_delta"])

    def test_outlier_in_either_arm_excludes_the_complete_pair(self):
        for role in ("baseline", "candidate"):
            args = self.fixture(6)
            args[0]["trials"][f"5-{role}"]["metrics"]["loading_ms"] = 1000
            result = outliers.analyze(*args)
            self.assertEqual([pair["id"] for pair in result["excluded_pairs"]], [5])
            self.assertEqual(result["modes"]["plain"]["screened"]["loading_ms"]["pairs"], 5)
            self.assertEqual(result["modes"]["plain"]["screened"]["steady_private_bytes"]["pairs"], 5)

    def test_treatment_shift_is_not_an_outlier(self):
        args = self.fixture(6)
        for trial in args[0]["trials"].values():
            if trial["role"] == "candidate":
                trial["metrics"]["loading_ms"] *= 2
        self.assertEqual(outliers.analyze(*args)["excluded_pairs"], [])

    def test_invalid_measurement_and_unqualified_data_fail(self):
        args = self.fixture(6)
        args[0]["trials"]["0-candidate"]["metrics"]["loading_ms"] = float("nan")
        with self.assertRaises(ValueError):
            outliers.analyze(*args)
        args = self.fixture(6)
        args[0]["errors"] = ["failed replay"]
        with self.assertRaises(ValueError):
            outliers.analyze(*args)
