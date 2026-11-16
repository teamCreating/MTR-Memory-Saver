"""Independent native reload contracts; generated sequences are engineering controls only."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import observe_packaged_client as observer
import reload_before_recorder as recorder
from log_stream_test_support import fixture_stream


FIXTURE = recorder.ROOT / "evidence/engineering-048/neutral-runtime-02-review/capture-02"


class NeutralReloadTest(unittest.TestCase):
    def setUp(self):
        factory = mock.patch.object(observer.native_log_stream.NativeLogStream, "from_launch", side_effect=fixture_stream)
        factory.start()
        self.addCleanup(factory.stop)
        self.state = json.loads((FIXTURE / "final-snapshot.json").read_bytes())
        self.process = json.loads((FIXTURE / "process.json").read_bytes())
        self.metadata = json.loads((FIXTURE / "observer-target.json").read_bytes())
        self.review = json.loads((FIXTURE / "sources/config/native-diagnostic-review.json").read_bytes())
        self.launch = json.loads((FIXTURE / "packaged-client-launch.json").read_bytes())
        self.plan = json.loads((FIXTURE / "packaged-client-plan.json").read_bytes())
        self.epoch = recorder.json_lines((FIXTURE / "game-probe/native-resource-epochs.jsonl").read_bytes())
        self.diagnostic = recorder.json_lines((FIXTURE / "game-probe/native-invalid-model.jsonl").read_bytes())
        self.original_log = (FIXTURE / "logs/latest.log").read_bytes()

    def generated_contract(self, count=21):
        epochs, diagnostics, observations, inputs = [], [copy.deepcopy(self.diagnostic[0])], [], []
        log = b""
        for sequence in range(1, count + 1):
            shift = dt.timedelta(seconds=(sequence-1)*900)
            nanos = (sequence-1)*900*10**9
            def moved(value):
                result = copy.deepcopy(value)
                for key in ("timestamp", "observed_at"):
                    result[key] = (observer.instant(value[key])+shift).isoformat()
                result["monotonic_nanos"] += nanos
                return result
            pair = [moved(value) for value in self.epoch]
            for value in pair:
                value["sequence"] = value["epoch_id"] = sequence
            epochs.extend(pair)
            for index, original in enumerate(self.diagnostic[1:]):
                value = moved(original)
                value["sequence"] = 2*sequence+index
                value["call_id"] = value["epoch_id"] = sequence
                diagnostics.append(value)
            settled = copy.deepcopy(self.state)
            stamp = observer.instant(pair[1]["timestamp"])+dt.timedelta(seconds=1)
            settled["timestamp"] = settled["observed_at"] = stamp.isoformat()
            settled["capture_started_at"] = stamp.isoformat()
            settled["monotonic_nanos"] = settled["capture_started_monotonic_nanos"] = pair[1]["monotonic_nanos"]+10**9
            settled["resource_epochs"].update(started=sequence, completed=sequence, last_completed_sequence=sequence)
            settled["native_model_diagnostics"].update(started=sequence, completed=sequence)
            state_hash = hashlib.sha256(recorder.canonical(settled)).hexdigest()
            observations.append({"verified": True, "raw_state": settled, "state": {"timestamp": settled["timestamp"]}, "state_sha256": state_hash})
            if sequence > 1:
                before = copy.deepcopy(settled)
                begin = observer.instant(pair[0]["timestamp"])
                before["timestamp"] = before["observed_at"] = (begin-dt.timedelta(seconds=.5)).isoformat()
                before["resource_epochs"]["last_completed_sequence"] = sequence-1
                inputs.append({"event_id": str(sequence), "record_status": "selected", "timestamp": (begin-dt.timedelta(seconds=.4)).isoformat(),
                    "pid": self.process["pid"], "process_created": self.process["created"], "method": "native_f3_t", "before": before,
                    "log_offset": len(log), "log_prefix_sha256": hashlib.sha256(log).hexdigest(),
                    "input": {"method": "native_f3_t", "provider": "synthetic-engineering-control-only", "succeeded": True,
                              "issued_at": (begin-dt.timedelta(seconds=.2)).isoformat(), "confirmed_at": (begin-dt.timedelta(seconds=.1)).isoformat()}})
            log += self.original_log if sequence == 1 else self.original_log[self.original_log.find(observer.START):]
        return log, inputs, epochs, diagnostics, observations

    def assess(self, contract):
        log, inputs, epochs, diagnostics, observations = contract
        finish = (observer.instant(observations[-1]["raw_state"]["timestamp"])+dt.timedelta(seconds=1)).isoformat()
        return observer.neutral_reload_evidence(log, inputs, epochs, diagnostics, observations, 1,
            self.launch, self.process, 1091, 1092, self.metadata, self.review, self.plan["timestamp"], finish)

    def test_twenty_generated_native_contracts_need_no_companion_log_or_fields(self):
        records, diagnostics = self.assess(self.generated_contract())
        self.assertTrue(diagnostics["native_attribution"]["passed"], diagnostics)
        self.assertEqual(observer.consecutive_reloads(records), 20, records)
        self.assertTrue(all(record["module_report_offset"] is None for record in records))
        self.assertNotIn("shared_blockbench", self.state)

    def test_changed_before_prefix_foreign_epoch_and_missing_native_call_fail(self):
        for change in ("prefix", "process", "missing-call", "rejected-attempt"):
            contract = self.generated_contract(2)
            if change == "prefix": contract[1][0]["log_prefix_sha256"] = "0"*64
            if change == "process": contract[2][-1]["process_created"] = "2000-01-01T00:00:00Z"
            if change == "missing-call": contract[3].pop()
            if change == "rejected-attempt": contract[1][0]["record_status"] = "rejected"
            with self.subTest(change=change):
                records, _ = self.assess(contract)
                self.assertFalse(records[0]["verified"])

    def test_creator_only_cycle_and_paused_or_straddling_snapshot_do_not_pass(self):
        for change in ("creator-only", "paused", "capture-before-return"):
            contract = self.generated_contract(2)
            if change == "creator-only": contract = (b"", *contract[1:])
            if change == "paused": contract[4][-1]["raw_state"]["paused"] = True
            if change == "capture-before-return": contract[4][-1]["raw_state"]["capture_started_monotonic_nanos"] = contract[2][-1]["monotonic_nanos"]-1
            with self.subTest(change=change):
                records, _ = self.assess(contract)
                self.assertFalse(records[0]["verified"])

    def test_neutral_snapshot_uses_native_fields_without_fabricating_module_zeros(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "snapshot.json"
            path.write_bytes(recorder.canonical(self.state))
            stamp = observer.instant(self.state["timestamp"])+dt.timedelta(seconds=1)
            result, _ = observer.state_observation(path, stamp, None, 15, 1091, True, True, expected_declarations=1092, expected_process=self.process)
            self.assertTrue(result["verified"], result)
            self.assertEqual(set(result["state"]["runtime_counters"]), {"native_pending", "resource_in_flight"})
            self.assertEqual(result["state"]["vehicles"][0]["railProgress"], self.state["train_state"]["vehicles"][0]["rail_progress"])
            wrong = {**self.process, "pid": 1}
            result, _ = observer.state_observation(path, stamp, None, 15, 1091, False, True, expected_declarations=1092, expected_process=wrong)
            self.assertFalse(result["verified"])

    def test_only_reviewed_metadata_versions_and_capabilities_are_accepted(self):
        for version in ("1.0.2", "1.0.3"):
            metadata = {**self.metadata, "observer_version": version}
            self.assertEqual(observer.validate_neutral_contract(metadata, self.state)["schema"], 1)
        for field, value in (("observer_version", "1.0.4"), ("schema_version", 2),
                             ("probe_kind", "other-observer"), ("diagnostics_schema", None)):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "reviewed consumer"):
                observer.validate_neutral_contract({**self.metadata, field: value}, self.state)
        for capabilities in ({}, None, {**self.state["capabilities"], "native_model_diagnostics": False},
                             {**self.state["capabilities"], "native_model_diagnostics": 1}):
            with self.subTest(capabilities=capabilities), self.assertRaisesRegex(ValueError, "diagnostic capabilities"):
                observer.validate_neutral_contract(self.metadata, {**self.state, "capabilities": capabilities})

    def test_repaired_snapshot_preserves_actual_version_and_unavailable_module_fields(self):
        state = copy.deepcopy(self.state)
        state["target"]["observer_version"] = "1.0.3"
        stamp = observer.instant(state["timestamp"])+dt.timedelta(seconds=1)
        result, _ = observer.neutral_state_observation(state, "fixture-sha", Path("fixture.json"), stamp,
            None, 15, 1091, 1092, True, True, self.process)
        self.assertTrue(result["verified"], result)
        self.assertEqual(result["raw_state"]["target"], state["target"])
        self.assertNotIn("text_workspace", result["state"])
        self.assertNotIn("module_pending", result["state"]["runtime_counters"])

    def test_neutral_startup_consumes_real_contract_without_module_observer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = {**self.plan, "instance": str(root)}
            for name in ("packaged-client-plan.json", "packaged-client-launch.json"):
                (root / name).write_bytes((FIXTURE / name).read_bytes())
            for name in ("logs/latest.log", "game-probe/native-resource-epochs.jsonl", "game-probe/native-invalid-model.jsonl"):
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((FIXTURE / name).read_bytes())
                if name == "logs/latest.log":
                    path.write_bytes(path.read_bytes().replace(self.plan["instance"].encode("utf-8"), str(root).encode("utf-8")))
            clock, state = [0.0], copy.deepcopy(self.state)
            base = observer.instant(state["timestamp"])+dt.timedelta(seconds=1)
            datetime_class = dt.datetime
            class SimulatedDatetime(datetime_class):
                @classmethod
                def now(cls, tz=None): return base+dt.timedelta(seconds=clock[0])
            identity = self.process
            class Process:
                def __init__(self, *unused): self.identity, self.created = identity, identity["created"]
                def sample(self):
                    stamp = (base+dt.timedelta(seconds=clock[0])).isoformat()
                    state["timestamp"] = state["observed_at"] = stamp
                    (root / "game-probe/native-observer.json").write_bytes(recorder.canonical(state))
                    return {"running": True, "working_set": 100, "private_usage": 200}
                def close(self): pass
            args = SimpleNamespace(instance=root, output=root / "observed", state_file=None, vehicle_state_file=None,
                epoch_events=None, mode="startup", require_world=False, unpaused=True, duration=5, interval=1,
                freshness_seconds=15, expected_count=1091, expected_declarations=1092, stable_seconds=1,
                auxiliary_interval=60, route_windows=3, minimum_window_progress_displacement=.01,
                gpu_counter=[], nmt=False, reload_events=None, reload_recorder=None, require_reloads=0)
            with mock.patch.object(observer, "frozen_context", return_value=(plan, self.launch)), \
                 mock.patch.object(observer, "neutral_context", return_value=self.metadata), \
                 mock.patch.object(observer, "WindowsProcess", Process), \
                 mock.patch.object(observer.time, "monotonic", side_effect=lambda: clock[0]), \
                 mock.patch.object(observer.time, "sleep", side_effect=lambda seconds: clock.__setitem__(0, clock[0]+seconds)), \
                 mock.patch.object(observer.dt, "datetime", SimulatedDatetime):
                result = observer.observe(args)
            summary = observer.read(args.output / "summary.json")
            self.assertEqual(result, 0, summary)
            self.assertTrue(summary["native_diagnostics"]["native_attribution"]["passed"])
            self.assertFalse((root / "game-probe/packaged-observer.json").exists())


if __name__ == "__main__":
    unittest.main()
