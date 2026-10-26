"""Guest-only tests of nano identities, exact write accounting and drain."""
import copy
import importlib.util
import tempfile
from pathlib import Path
import unittest
from unittest.mock import mock_open, patch

import run
import session
from oracle import validate
from test_bench import fixture


class NanoTests(unittest.TestCase):
    def test_launcher_commands_bind_the_underlying_profiles(self):
        path = Path(__file__).resolve().parents[1] / 'nano/best_case.py'
        module_spec = importlib.util.spec_from_file_location('nano_launcher_test', path)
        launcher = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(launcher)
        defaults = launcher.parser().parse_args(['--output', '/tmp/nano-default-grid', '--plan-only'])
        self.assertEqual(defaults.threads, [*range(1, 9), *range(12, 61, 4)])
        args = launcher.parser().parse_args(['--output', '/tmp/nano-plan-only',
            '--threads', '1', '60', '--plan-only'])
        self.assertEqual((args.mutex_batch_limit, args.mutex_numa_boundary), (1024, 768))
        commands = list(launcher.commands(args))
        self.assertEqual([name for name, _ in commands],
                         ['mutex-throughput', 'mutex-locality', 'rwsem-read', 'rwsem-mixed'])
        for name, argv in commands:
            plan = run.make_plan(run.parser().parse_args(argv[2:]))
            self.assertEqual(len(plan), 6)
            family, percent = launcher.PROFILES[name]
            counter_profile = name in ('mutex-throughput', 'mutex-locality')
            self.assertTrue(all(r['lock_kind'] == family and r['write_percent'] == percent and
                                r['repeat'] == 0 and r['workload'] ==
                                ('cacheline' if counter_profile else 'nano') for r in plan))
            self.assertEqual({r['cachelines'] for r in plan},
                             {1 if name == 'mutex-throughput' else 16 if counter_profile else 2})
            self.assertEqual({r['post_work_rounds'] for r in plan},
                             {256 if counter_profile else 4})
            self.assertTrue(all(r['provider_mutex_policy'] == dict(total_cap=1024,
                numa_boundary=768, deferred_handoff=8, scan_budget=64)
                for r in plan if r['arm'] == 'kdlock'))
        args.post_work_rounds = 4
        for _, argv in launcher.commands(args):
            plan = run.make_plan(run.parser().parse_args(argv[2:]))
            self.assertTrue(all(r['post_work_rounds'] == 4 for r in plan))

    def test_launcher_forwards_policy_only_for_public_mutex_profiles(self):
        path = Path(__file__).resolve().parents[1] / 'nano/best_case.py'
        spec = importlib.util.spec_from_file_location('nano_policy_launcher_test', path)
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        base = ['--output', '/tmp/nano-policy-plan', '--profiles', 'mutex', 'mutex-throughput', 'mutex-locality',
                '--threads', '16', '--plan-only']
        for cap, boundary in ((1024, 768), (4096, 768), (1024, 256)):
            args = launcher.parser().parse_args(base + ['--mutex-batch-limit', str(cap),
                                                       '--mutex-numa-boundary', str(boundary)])
            for _, argv in launcher.commands(args):
                plan = run.make_plan(run.parser().parse_args(argv[2:]))
                kd = next(row for row in plan if row['arm'] == 'kdlock')
                self.assertEqual(kd['provider_mutex_policy'], dict(total_cap=cap,
                    numa_boundary=boundary, deferred_handoff=8, scan_budget=64))
                if kd['workload'] == 'nano':
                    self.assertEqual((kd['cachelines'], kd['post_work_rounds']), (2, 4))
        invalid = [['--mutex-batch-limit', '0'], ['--mutex-batch-limit', '32768'],
                   ['--mutex-numa-boundary', '0'], ['--mutex-numa-boundary', '32768'],
                   ['--mutex-batch-limit', '4096', '--delegate', 'off'],
                   ['--mutex-batch-limit', '4096', '--backends', 'native'],
                   ['--mutex-batch-limit', '4096', '--profiles', 'mutex', 'rwsem-read']]
        for extra in invalid:
            with self.subTest(extra=extra), patch.object(launcher.sys, 'argv', ['best_case.py', *base, *extra]), \
                    patch.object(launcher.subprocess, 'Popen') as launch, self.assertRaises(ValueError):
                launcher.main()
            launch.assert_not_called()
        defaults = launcher.parser().parse_args(['--output', '/tmp/nano-policy-plan',
                                                '--mutex-batch-limit', '4096'])
        with self.assertRaises(ValueError):
            list(launcher.commands(defaults))

    def test_mutex_policy_is_independent_and_invalid_cli_stops_before_build(self):
        base = ['--lock-kind', 'mutex', '--workloads', 'nano', '--write-percent', '100',
                '--threads', '16', '--collector-cpu', '63', '--repeats', '1']
        for cap, boundary in ((1024, 768), (4096, 768), (1024, 256), (4096, 256)):
            plan = run.make_plan(run.parser().parse_args(base +
                ['--mutex-batch-limit', str(cap), '--mutex-numa-boundary', str(boundary)]))
            kd = next(row for row in plan if row['arm'] == 'kdlock')
            self.assertEqual(kd['delegation_batch_limit'], cap)
            self.assertEqual(kd['provider_mutex_policy'], dict(total_cap=cap,
                numa_boundary=boundary, deferred_handoff=8, scan_budget=64))
            tc = next(row for row in plan if row['arm'] == 'tclock')
            self.assertEqual(tc['delegation_batch_limit'], 1024)
            self.assertIsNone(tc['provider_mutex_policy'])
            self.assertIsNone(next(row for row in plan if row['arm'] == 'native')['provider_mutex_policy'])
        invalid = [['--mutex-batch-limit', '0'], ['--mutex-batch-limit', '32768'],
                   ['--mutex-numa-boundary', '0'], ['--mutex-numa-boundary', '32768'],
                   ['--mutex-batch-limit', '4096', '--delegate', 'off'],
                   ['--mutex-batch-limit', '4096', '--backends', 'native'],
                   ['--mutex-batch-limit', '4096', '--lock-kind', 'rwsem']]
        for extra in invalid:
            with self.subTest(extra=extra), patch.object(run, 'idle') as idle, \
                    patch.object(run, 'build') as build, self.assertRaises(run.Failure):
                run.main(base + extra)
            idle.assert_not_called()
            build.assert_not_called()

    def test_locality_profile_checks_every_counter_and_returned_body(self):
        args = run.parser().parse_args(['--lock-kind', 'mutex', '--workloads', 'cacheline',
            '--cachelines', '16', '--write-percent', '100', '--threads', '1', '60',
            '--collector-cpu', '63', '--repeats', '1'])
        plan = run.make_plan(args)
        self.assertTrue(all(r['cachelines'] == 16 and r['post_work_rounds'] == 4 for r in plan))
        self.assertTrue(all(r['call_shell'] == 'bulk_ioctl' and
                            r['nano_working_set_bytes'] == 1024 and
                            r['nano_layout'] == '16_aligned_counters' for r in plan))
        self.assertTrue(all(r['mutex_api'] == 'public' and r['entry_abi'] == 2
                            for r in plan if r['arm'] == 'kdlock'))
        spec, measurement = fixture('cacheline', 100)
        spec.update(cachelines=16, lock_kind='mutex')
        for key in ('before', 'after'):
            measurement[key].update(lines=16, values=[0]*16)
        measurement['after']['values'] = [200]*16
        validate(measurement, spec)
        for index in range(16):
            bad = copy.deepcopy(measurement)
            bad['after']['values'][index] -= 1
            with self.assertRaises(ValueError):
                validate(bad, spec)
        row = dict(spec, arm='kdlock', jit_bodies=10, jit_completions=0, measurement=measurement)
        self.assertEqual(run.list_execution_class(row), 'PARTIAL_JIT')

    def test_profiles_bind_packed_record_and_public_or_local_shell(self):
        for family, percent in [('mutex', 100), ('rwsem', 1), ('rwsem', 20)]:
            for delegate in ('on', 'off'):
                args = run.parser().parse_args(['--lock-kind', family, '--workloads', 'nano',
                    '--threads', '1', '60', '--write-percent', str(percent),
                    '--delegate', delegate, '--repeats', '1', '--collector-cpu', '63'])
                plan = run.make_plan(args)
                self.assertEqual(len(plan), 6)
                self.assertEqual({r['cachelines'] for r in plan}, {2})
                self.assertTrue(all(r['nano_words'] == 2 and r['nano_record_bytes'] == 64 and
                                    r['call_shell'] == 'bulk_ioctl' for r in plan))
                kd = next(r for r in plan if r['arm'] == 'kdlock')
                self.assertEqual(kd['entry_abi'], 2 if delegate == 'on' else None)
                self.assertEqual(kd['caller_abi'], 'clobber' if delegate == 'on' else 'c')
                candidate = object.__new__(session.RWSession)
                candidate.record = kd
                self.assertEqual(candidate.has_entry(), delegate == 'on')
                if family == 'mutex':
                    self.assertEqual(kd['mutex_api'], 'public' if delegate == 'on' else 'callable-local')

    def test_mutex_factor_grid_keeps_body_identity_and_exact_counter_oracle(self):
        for post in (4, 64, 256):
            args = run.parser().parse_args(['--lock-kind', 'mutex', '--workloads', 'cacheline',
                '--cachelines', '1', '4', '16', '--write-percent', '100', '--threads', '16',
                '--collector-cpu', '63', '--repeats', '1', '--post-work-rounds', str(post)])
            plan = run.make_plan(args)
            self.assertEqual(len(plan), 9)
            for row in plan:
                lines = row['cachelines']
                self.assertEqual(row['nano_working_set_bytes'], 64 * lines)
                self.assertEqual(row['nano_layout'], f'{lines}_aligned_counters')
                self.assertEqual(row['post_work_rounds'], post)
                spec, measurement = fixture('cacheline', 100)
                spec.update(cachelines=lines, lock_kind='mutex')
                for key in ('before', 'after'):
                    measurement[key].update(lines=lines, values=[0] * 16)
                measurement['after']['values'] = [200] * lines + [0] * (16 - lines)
                validate(measurement, spec)
                bad = copy.deepcopy(measurement)
                bad['after']['values'][lines - 1] -= 1
                with self.assertRaises(ValueError):
                    validate(bad, spec)
                if lines < 16:
                    bad = copy.deepcopy(measurement)
                    bad['after']['values'][lines] = 1
                    with self.assertRaises(ValueError):
                        validate(bad, spec)

    def test_unsupported_mutex_mixes_and_nano_spin_are_refused(self):
        for argv in (['--lock-kind', 'mutex', '--workloads', 'nano', '--write-percent', '1'],
                     ['--lock-kind', 'mutex', '--workloads', 'cacheline', '--write-percent', '20'],
                     ['--lock-kind', 'rwlock', '--workloads', 'nano']):
            with self.assertRaises(run.Failure):
                run.make_plan(run.parser().parse_args(argv))

    def test_exact_both_word_totals_and_torn_read_detection(self):
        for percent in (1, 20, 100):
            spec, measurement = fixture('cacheline', percent)
            spec.update(workload='nano', cachelines=2, nano_words=2,
                        nano_record_bytes=64, call_shell='bulk_ioctl')
            for key in ('before', 'after'):
                measurement[key].update(workload=6, lines=2, values=[0]*16)
            measurement['after']['values'][:2] = [2*percent]*2
            validate(measurement, spec)
            for mutate in (lambda m: m['after']['values'].__setitem__(0, 2*percent+1),
                           lambda m: m['after']['values'].__setitem__(1, 2*percent-1),
                           lambda m: m['after']['values'].__setitem__(2, 1),
                           lambda m: m['workers'][0].__setitem__('read_errors', 1),
                           lambda m: m['after'].__setitem__('workload', 0),
                           lambda m: m['after'].__setitem__('gate', 1)):
                bad = copy.deepcopy(measurement)
                mutate(bad)
                with self.assertRaises(ValueError):
                    validate(bad, spec)
            bad_spec = dict(spec, nano_record_bytes=128)
            with self.assertRaises(ValueError):
                validate(measurement, bad_spec)

    def test_mutex_tclock_context_drain_is_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            params = Path(temporary)
            (params/'quiescent').write_text('1')
            candidate = object.__new__(session.RWSession)
            candidate.record = dict(lock_kind='mutex')
            candidate.tc_params = params
            candidate.loaded_source = True
            with patch('session.open', mock_open(), create=True), patch.object(session.fcntl, 'ioctl') as call:
                self.assertEqual(candidate.tc_idle()['quiescent'], 1)
                self.assertEqual(call.call_args.args[1], session.DRAIN)
            (params/'quiescent').write_text('0')
            with patch('session.open', mock_open(), create=True), patch.object(session.fcntl, 'ioctl'), self.assertRaises(run.Failure):
                candidate.tc_idle()

    def test_nano_return_evidence_is_not_inferred_from_entries(self):
        base = dict(workload='nano', arm='kdlock', jit_bodies=10, jit_completions=10,
                    measurement=dict(writes=10))
        self.assertEqual(run.list_execution_class(base), 'RETURNED_JIT')
        self.assertEqual(run.list_execution_class(dict(base, jit_completions=0)), 'PARTIAL_JIT')
        self.assertEqual(run.list_execution_class(dict(base, jit_bodies=0, jit_completions=0)), 'NO_JIT')


if __name__ == '__main__':
    unittest.main()
