import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import benchmark_sources as runner
from source_experiment_analysis import METRICS, analyze, decision, median_interval, paired_summary


def fixture(pairs=6):
    policy = runner.read(runner.ROOT / 'config/source-experiment.json')
    policy['pairs'] = pairs
    plan = {'policy': policy, 'schedule': runner.schedule(policy), 'inputs': [{'sha256': '0' * 64}],
            'expected_result_sha256': 'f' * 64, 'expected_warmup_sha256': 'a' * 64, 'heap_bytes': 3 * 1024 ** 3}
    trials = []
    for spec in plan['schedule']:
        result = dict.fromkeys(METRICS, 100)
        result.update(mode=spec['mode'], instrumentation=spec['instrumentation'],
                      warmup_epochs=policy['warmup_epochs'], epochs=policy['epochs'], queries=policy['queries'],
                      result_sha256=plan['expected_result_sha256'], warmup_result_sha256=plan['expected_warmup_sha256'],
                      max_heap_bytes=plan['heap_bytes'], warmup_start='2026-11-14T01:00:00+08:00',
                      warmup_end='2026-11-14T01:01:00+08:00', start='2026-11-14T01:01:01+08:00',
                      end='2026-11-14T01:01:02+08:00',
                      digest_calls=policy['epochs'] * (policy['queries'] if spec['mode'] == 'baseline' else 1))
        if spec['mode'] == 'candidate':
            result['allocated_bytes_live_threads'] = 60
        trials.append({**spec, 'status': 'complete', 'returncode': 0, 'result': result})
    return plan, {'status': 'complete', 'trials': trials}


class SourceExperimentTests(unittest.TestCase):
    def test_schedule_balances_order_within_every_stratum(self):
        plan, _ = fixture()
        schedule = plan['schedule']
        self.assertEqual(len(schedule), 48)
        self.assertEqual(schedule, runner.schedule(plan['policy']))
        for comparison in ('aa', 'ab'):
            for probe in ('plain', 'profile'):
                selected = [t for t in schedule if t['comparison'] == comparison and t['instrumentation'] == probe]
                self.assertEqual([t['arm'] for t in selected[::2]].count('a'), 3)
                if comparison == 'aa':
                    self.assertEqual({t['mode'] for t in selected}, {'baseline'})

    def test_interval_uses_independent_pairs_not_queries(self):
        self.assertIsNone(median_interval([-30] * 3, .95))
        self.assertEqual(median_interval([-30] * 6, .95), [-30, -30])
        plan, state = fixture(3)
        self.assertEqual(analyze(plan, state)['status'], 'inconclusive')

    def test_absolute_and_paired_relative_statistics(self):
        pairs = [({'elapsed_ms': 100}, {'elapsed_ms': 50}), ({'elapsed_ms': 1000}, {'elapsed_ms': 900})]
        summary = paired_summary(pairs, 'elapsed_ms', .95)
        self.assertAlmostEqual(summary['median_relative_delta_percent'], -30)
        self.assertEqual(summary['absolute_deltas'], [-50, -100])

    def test_zero_reference_is_not_an_infinite_or_zero_improvement(self):
        summary = paired_summary([({'gc_count': 0}, {'gc_count': 1})] * 6, 'gc_count', .95)
        self.assertIsNone(summary['median_relative_interval_percent'])
        self.assertEqual(decision(summary, 5, 6), 'inconclusive')
        self.assertEqual(summary['absolute_deltas'], [1] * 6)

    def test_known_improvement_with_stable_controls_passes(self):
        self.assertEqual(analyze(*fixture())['status'], 'pass')

    def test_timing_regression_blocks_allocation_gain(self):
        plan, state = fixture()
        for trial in state['trials']:
            if trial['mode'] == 'candidate':
                trial['result']['elapsed_ms'] = 130
        report = analyze(plan, state)
        self.assertEqual(report['gates']['primary'], 'pass')
        self.assertEqual(report['gates']['guardrail_elapsed_ms'], 'fail')
        self.assertFalse(report['performance_accepted'])

    def test_aa_drift_cannot_be_called_equivalent(self):
        plan, state = fixture()
        for trial in state['trials']:
            if trial['comparison'] == 'aa' and trial['arm'] == 'b':
                trial['result']['elapsed_ms'] = 140
        self.assertEqual(analyze(plan, state)['status'], 'fail')

    def test_shared_wrong_answer_and_wrong_warmup_rejected(self):
        for field in ('result_sha256', 'warmup_result_sha256'):
            plan, state = fixture()
            for trial in state['trials']:
                trial['result'][field] = 'c' * 64
            self.assertEqual(analyze(plan, state)['status'], 'invalid')

    def test_missing_failed_duplicate_and_reordered_runs_are_invalid(self):
        for defect in ('missing', 'failed', 'duplicate', 'order'):
            plan, state = fixture()
            if defect == 'missing':
                state['trials'].pop()
            elif defect == 'failed':
                state['trials'][0]['status'] = 'failed'
            elif defect == 'duplicate':
                state['trials'].append(copy.deepcopy(state['trials'][0]))
            else:
                state['trials'].reverse()
            self.assertEqual(analyze(plan, state)['status'], 'invalid', defect)

    def test_nonfinite_heap_controls_and_windows_rejected(self):
        for field, value in [('elapsed_ms', float('nan')), ('allocated_bytes_live_threads', -1),
                             ('max_heap_bytes', 1), ('queries', 1), ('mode', 'wrong'),
                             ('start', '2026-11-14T01:01:01'), ('end', '2026-11-14T00:00:00+08:00')]:
            plan, state = fixture()
            state['trials'][0]['result'][field] = value
            self.assertEqual(analyze(plan, state)['status'], 'invalid', field)

    def test_policy_rejects_unknown_missing_and_posthoc_shortcuts(self):
        plan, _ = fixture()
        runner.validate_policy(plan['policy'])
        for key, value in [('extra', True), ('pairs', 0), ('confidence', float('nan')),
                           ('aa_tolerance_percent', {}), ('guardrails', {'typo': 10})]:
            policy = copy.deepcopy(plan['policy'])
            policy[key] = value
            with self.assertRaises(ValueError):
                runner.validate_policy(policy)

    def test_independent_utf8_input_oracle_and_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = '车厢\ufeff\U0001f686\r\n'.encode('utf-8')
            digest = hashlib.sha256(raw).hexdigest()
            with zipfile.ZipFile(root / 'data.zip', 'w') as archive:
                archive.writestr('模型.bbmodel', raw)
            runner.save(root / 'jobs.json', [{'archive': 'data.zip', 'model': '模型.bbmodel', 'sha256': digest}])
            inputs, archives = runner.input_controls(root / 'jobs.json')
            self.assertEqual(runner.oracle(inputs, 2, 3), hashlib.sha256((digest * 6).encode('ascii')).hexdigest())
            self.assertEqual(archives[0]['path'], str((root / 'data.zip').resolve()))
            runner.save(root / 'jobs.json', [{'archive': 'data.zip', 'model': '模型.bbmodel', 'sha256': 'a' * 64}])
            with self.assertRaises(ValueError):
                runner.input_controls(root / 'jobs.json')

    def test_environment_cannot_silently_inject_jvm_settings(self):
        with patch.dict(os.environ, {'JAVA_TOOL_OPTIONS': '-Xmx8g'}):
            with self.assertRaises(ValueError):
                runner.environment()

    def test_only_artifact_version_may_differ_in_target_controls(self):
        identities = {'a': {'version': 'old', 'loader': '248'}, 'b': {'version': 'new', 'loader': '248'}}
        self.assertEqual(runner.compatible_targets(identities), {'loader': '248'})
        identities['b']['loader'] = '265'
        with self.assertRaises(ValueError):
            runner.compatible_targets(identities)

    def test_exclusive_save_preserves_existing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'evidence.json'
            runner.save(path, {'original': True}, exclusive=True)
            with self.assertRaises(FileExistsError):
                runner.save(path, {}, exclusive=True)
            self.assertEqual(runner.read(path), {'original': True})

    def test_failed_jvms_are_all_preserved_and_cannot_be_rerun(self):
        plan, _ = fixture(1)
        plan.update(java={'path': 'java'}, javac={'path': 'javac'},
                    artifacts={mode: {'path': mode + '.jar'} for mode in ('baseline', 'candidate')},
                    jvm_arguments=['-Xmx3g'], sources=[])
        plan['inputs'][0].update(archive='archive.zip', model='model.bbmodel')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plan.json'
            runner.save(path, plan)
            def failed(command, **kwargs):
                # Compilation succeeds; each launched workload exits abnormally.
                return runner.subprocess.CompletedProcess(command, 0 if command[0] == 'javac' else 7)
            with patch.object(runner, 'validate_plan'), patch.object(runner, 'verify_inputs'), \
                    patch.object(runner.subprocess, 'run', side_effect=failed):
                self.assertEqual(runner.run_plan(path), 2)
                with self.assertRaises(FileExistsError):
                    runner.run_plan(path)
            state = runner.read(path.parent / 'execution.json')
            self.assertEqual(len(state['trials']), 8)
            self.assertTrue(all(t['status'] == 'failed' and t['returncode'] == 7 for t in state['trials']))
            self.assertTrue(all(t['files'][0]['sha256'] == hashlib.sha256(b'').hexdigest() for t in state['trials']))

    def test_audit_rejects_tampered_log_and_mutated_plan(self):
        plan, state = fixture(1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'plan.json'
            runner.save(path, plan)
            state['plan_sha256'] = runner.sha(path)
            for trial in state['trials']:
                folder = root / trial['id']
                folder.mkdir()
                runner.save(folder / 'result.json', trial['result'])
                (folder / 'process.log').write_text('original')
                if trial['instrumentation'] == 'profile':
                    (folder / 'recording.jfr').write_bytes(b'raw recording')
                trial['files'] = [runner.fingerprint(p) for p in folder.iterdir()]
            runner.save(root / 'execution.json', state)
            with patch.object(runner, 'validate_plan'):
                self.assertEqual(runner.audit(path)['status'], 'inconclusive')
                (root / state['trials'][0]['id'] / 'process.log').write_text('edited')
                self.assertEqual(runner.audit(path)['status'], 'invalid')
                runner.save(path, {**plan, 'extra': 'after measurement'})
                self.assertIn('Plan fingerprint mismatch.', runner.audit(path)['integrity_errors'])


if __name__ == '__main__':
    unittest.main()
