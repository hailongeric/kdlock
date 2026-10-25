"""Synthetic receipts and mocked transports; never execute a live controller."""
import argparse
import copy
import datetime
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'bench/mmap_lock'))
import paired
import controller
import report


def fixture_bindings():
    return {key: dict(path='/fixture/case-' + str(i) + '/result.json',
                      sha256=hashlib.sha256(str(key).encode()).hexdigest())
            for i, key in enumerate(paired.ORDER)}


def rows():
    result = []
    bindings = fixture_bindings()
    for index, (repeat, mode, case) in enumerate(paired.ORDER):
        block = paired.expected_block(repeat, mode)
        result.append(dict(passed=True, drained=True, accepted=True, endpoint_checked=True,
            prepared=dict(path='fixture', sha256='same'), repeat=repeat, mode=mode, case=case,
            block=block, boot_id='boot-' + str(block), ready=dict(path='ready-' + str(block), sha256='same'),
            previous=bindings[paired.ORDER[index-1]] if index else None,
            spec=paired.specification(case, repeat, mode),
            measurement=dict(whole_ops_s=(100 if mode == 'native' else 90) + repeat,
                latency_samples=0 if case % 2 == 0 else 100 + repeat,
                latency_percentiles_ns=dict(zip(('50', '95', '99'), (10, 30, 50))))))
    return result


def summary(data):
    return report.summarize(data, fixture_bindings())


class Report(unittest.TestCase):
    def test_complete_pairs_and_observations_separate(self):
        r = summary(rows())
        self.assertEqual(r['qualified_cases'], 24)
        self.assertEqual(len(r['points']), 4)
        self.assertLess(r['points'][0]['paired_kd_over_native_throughput']['median'], 1)
        self.assertEqual(r['points'][0]['arms']['native']['latency_percentiles_ns'], {})
        self.assertEqual(r['points'][1]['arms']['native']['latency_percentiles_ns']['95']['median'], 30)

    def test_no_partial_pairs(self):
        with self.assertRaises(ValueError):
            summary(rows()[:-1])

    def test_rejected_duplicate_mixed_and_wrong_observation_fail(self):
        for key, value in [('accepted', False), ('drained', False), ('endpoint_checked', False),
                           ('prepared', dict(path='other', sha256='other')),
                           ('spec', dict(threads=1, observation='sampled'))]:
            with self.subTest(key=key):
                bad = rows()
                bad[0][key] = value
                with self.assertRaises(ValueError):
                    summary(bad)
        bad = rows()
        bad[0] = copy.deepcopy(bad[1])
        with self.assertRaises(ValueError):
            summary(bad)

    def test_boot_order_and_session_count(self):
        self.assertEqual(len(paired.BLOCKS), 5)
        self.assertEqual(len(paired.ORDER), 24)
        self.assertEqual([paired.ORDER[i][:2] for i in range(0, 24, 4)],
                         [(0, 'kd'), (0, 'native'), (1, 'native'), (1, 'kd'), (2, 'kd'), (2, 'native')])

    def test_trial_spec_chain_and_boot_mutations_fail(self):
        for field, value in [('block', 4), ('boot_id', 'unrelated-boot'),
                             ('ready', dict(path='other', sha256='same')),
                             ('previous', dict(path='other', sha256='same'))]:
            with self.subTest(field=field):
                bad = rows()
                bad[5][field] = value
                with self.assertRaises(ValueError):
                    summary(bad)
        bad = rows()
        bad[4]['repeat'], bad[8]['repeat'] = bad[8]['repeat'], bad[4]['repeat']
        with self.assertRaises(ValueError):
            summary(bad)
        for field, value in [('repeat', 2), ('arm', 'kd')]:
            bad = rows()
            bad[4]['spec'][field] = value
            with self.assertRaises(ValueError):
                summary(bad)
        bad = rows()
        for row in bad:
            if row['block'] == 3:
                row['boot_id'] = 'boot-1'
        with self.assertRaises(ValueError):
            summary(bad)

    def test_sample_counts_and_matching_instrumentation_ratio(self):
        before = summary(rows())
        self.assertEqual(before['points'][1]['arms']['kd']['latency_sample_counts'], [100, 101, 102])
        data = rows()
        data[1]['measurement']['whole_ops_s'] *= 2
        after = summary(data)
        self.assertNotEqual(before['sampled_over_plain_throughput']['1']['kd'],
                            after['sampled_over_plain_throughput']['1']['kd'])
        self.assertEqual(before['sampled_over_plain_throughput']['16'],
                         after['sampled_over_plain_throughput']['16'])
        self.assertEqual(before['sampled_over_plain_throughput']['1']['native'],
                         after['sampled_over_plain_throughput']['1']['native'])


class Replay(unittest.TestCase):
    def test_saved_capture_deletion_or_substitution_rejects_accepted_flags(self):
        for target, action in [('endpoint', 'delete'), ('endpoint', 'change'), ('controller', 'change')]:
            with self.subTest(target=target, action=action), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)
                r = rows()[0]
                r['client_exited'] = True
                client = copy.deepcopy(r)
                for key in ('passed', 'accepted', 'drained'):
                    client[key] = False
                (out / 'client-result.json').write_text(json.dumps(client))
                (out / 'client.jsonl').write_text('{}\n')
                for name in ('controller', 'endpoint', 'admission', 'native', 'kd'):
                    (out / (name + '.json')).write_text('{}')
                evidence = {name: paired.bind(out / (name + '.json'))
                            for name in ('controller', 'endpoint', 'admission')}
                evidence['captured_utc'] = 'fixture-time'
                r.update(qualification=evidence, endpoint_captured_utc='fixture-time',
                         validated=[paired.bind(out / (mode + '.json')) for mode in ('native', 'kd')])
                # These are synthetic saved receipts. Only filesystem binding
                # validation runs; no host observation or workload can occur.
                (out / 'result.json').write_text(json.dumps(r))
                ready = {k: r[k] for k in ('mode', 'boot_id', 'block', 'prepared')}
                ready['passed'] = True
                with patch.object(paired, 'load_bound', return_value=ready), \
                     patch.object(paired, 'validation_receipt', return_value={}), \
                     patch.object(paired, 'qualify', return_value=evidence) as qualification, \
                     patch.object(paired, 'measurement', return_value=r['measurement']):
                    report.replay(out / 'result.json')
                    qualification.reset_mock()
                    path = out / (target + '.json')
                    if action == 'delete':
                        path.unlink()
                    else:
                        path.write_text('{"changed":true}')
                    with self.assertRaises((OSError, paired.rt.Failure)):
                        report.replay(out / 'result.json')
                    qualification.assert_not_called()


class Validation(unittest.TestCase):
    def fixture(self):
        return dict(passed=True, drained=True, accepted=False, mode='kd', prepared={},
            cases=[dict(spec=paired.specification(i, 0, 'kd')) for i in range(4)],
            fixed=dict(passed=True, mode='cycle', threads=16, iterations=5000,
                protocol='KD_LOCAL_MMAP_LOCK', health='files=0 mm_refs=0 destroyed=1 release_errors=0',
                rejected_mutations=['different_lock', 'wrong_caller_return', 'wrong_wait_return',
                    'wrong_adapter_return', 'running_task', 'other_wait_channel', 'rescheduled_task',
                    'missing_chain', 'missing_writer_proof']))

    def test_exact_cases_and_fixed_work_are_required(self):
        paired.validation_shape(self.fixture(), 'kd', {})
        v = self.fixture()
        v['cases'][1] = copy.deepcopy(v['cases'][0])
        with self.assertRaises(paired.rt.Failure):
            paired.validation_shape(v, 'kd', {})
        v = self.fixture()
        del v['fixed']
        with self.assertRaises(KeyError):
            paired.validation_shape(v, 'kd', {})
        v = self.fixture()
        v['fixed']['rejected_mutations'].pop()
        with self.assertRaises(paired.rt.Failure):
            paired.validation_shape(v, 'kd', {})

    def test_post_load_warning_prevents_client_launch(self):
        inputs = dict(binaries=dict(payload='fixture.ko', fixed='fixture-fixed', timed='fixture-timed'))
        for kind in ('fixed', 'timed'):
            with self.subTest(kind=kind), patch.object(paired.rt, 'command') as command, \
                 patch.object(paired, 'fault_check', side_effect=paired.rt.Failure('KERNEL_FAULT', 'fixture warning')), \
                 patch.object(paired, 'health'):
                with self.assertRaises(paired.rt.Failure):
                    if kind == 'fixed':
                        paired.fixed(inputs, Path('/fixture'), 'kd')
                    else:
                        paired.timed(inputs, Path('/fixture'), paired.specification(0, 0, 'kd'))
                self.assertEqual(command.call_count, 1)
                self.assertEqual(command.call_args.args[0][0], 'insmod')


class Admission(unittest.TestCase):
    def fixture(self):
        h = paired.PROFILE['host']
        tasks = [dict(tid=i, comm='fixture', affinity=[63]) for i in range(67)]
        return dict(passed=True, capture=dict(complete=True, tasks=tasks), pins_verified=True,
                    snapshot_listed=True, recovery_snapshot=h['snapshot'], boot_id=h['boot_id'],
                    final_identity=dict(pid=h['pid'], start_ticks=h['start_ticks'],
                                        command_sha256=h['command_sha256']),
                    qemu=[dict(tasks=tasks)])

    def test_strict_67_gate_rejects_extra_endpoint_task(self):
        old, host = self.fixture(), self.fixture()
        hashes = paired.common.scheduler.REPLAY_ENVIRONMENT_SHA256
        with patch.object(paired.rt, 'digest', side_effect=lambda p: hashes[p.name]), \
             patch.object(paired.common, 'load', return_value=old):
            paired.host_check(host, fresh=False)
            host['qemu'][0]['tasks'].append(dict(tid=99, comm='worker', affinity=[63]))
            with self.assertRaises(paired.rt.Failure):
                paired.host_check(host, fresh=False)

    def test_changed_process_start_and_incomplete_capture_fail(self):
        host = self.fixture()
        host['final_identity']['start_ticks'] += 1
        with self.assertRaises(paired.rt.Failure):
            paired.host_check(host, fresh=False)
        host = self.fixture()
        host['capture']['complete'] = False
        with self.assertRaises(paired.rt.Failure):
            paired.host_check(host, fresh=False)


class Cleanup(unittest.TestCase):
    def test_malformed_endpoint_still_allows_independent_exact_drain(self):
        for error in (FileNotFoundError('missing endpoint'), ValueError('malformed'), KeyError('substituted')):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)
                client = dict(client_exited=True, boot_id='boot', mode='kd', spec={},
                              ready={}, prepared=dict(path='fixture'))
                (out / 'client-result.json').write_text(json.dumps(client))
                with patch.object(paired, 'check_kernel'), \
                     patch.object(paired, 'load_bound', return_value=dict(files={})), \
                     patch.object(paired, 'prepared'), \
                     patch.object(paired, 'business_finish', return_value=({}, 'exact drain')) as drain, \
                     patch.object(paired, 'qualify', side_effect=error):
                    with self.assertRaises(paired.rt.Failure):
                        paired.finish(argparse.Namespace(output=out, controller=out / 'capture'))
                r = json.loads((out / 'result.json').read_text())
                drain.assert_called_once()
                self.assertTrue(r['passed'] and r['drained'])
                self.assertFalse(r['accepted'])
                self.assertIn('qualification_error', r)

    def test_client_failure_never_starts_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'client-result.json').write_text(json.dumps(dict(client_exited=False)))
            with patch.object(paired, 'business_finish') as finish:
                with self.assertRaises(paired.rt.Failure):
                    paired.finish(argparse.Namespace(output=out, controller=out / 'capture'))
            finish.assert_not_called()


class Transport(unittest.TestCase):
    def test_fetch_timeout_cannot_retain_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            admission = out / 'admission.json'
            admission.write_text(json.dumps(dict(passed=True, captured_utc=
                datetime.datetime.now(datetime.timezone.utc).isoformat())))
            guest = MagicMock(pid=11)
            guest.wait.return_value = 0
            fetch = MagicMock(pid=12)
            fetch.wait.side_effect = subprocess.TimeoutExpired('fetch fixture', 30)
            def capture(out, record, payload):
                record.update(host_returncode=0, host_capture_started_monotonic_ns=
                    record['guest_exit_observed_monotonic_ns'] + 1,
                    host_capture_finished_monotonic_ns=record['guest_exit_observed_monotonic_ns'] + 2)
                (out / 'host-endpoint.json').write_text(json.dumps(dict(passed=True)))
            with patch.object(controller, 'capture', side_effect=capture), \
                 patch.object(controller.subprocess, 'Popen', side_effect=[guest, fetch]):
                r = controller.execute(out, 'fixture command', '/fixture/result.json', admission)
            self.assertFalse(r['passed'])
            self.assertTrue(r['fetch_completion_unconfirmed'])
            self.assertTrue(r['drain_unconfirmed'])
            self.assertEqual(r['failed_phase'], 'fetch')
            self.assertEqual(r['guest_returncode'], 0)
            guest.kill.assert_not_called()
            fetch.kill.assert_not_called()
            self.assertFalse(json.loads((out / 'controller.json').read_text())['passed'])


if __name__ == '__main__':
    unittest.main()
