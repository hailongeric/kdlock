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
        args = launcher.parser().parse_args(['--output', '/tmp/nano-plan-only',
            '--threads', '1', '60', '--plan-only'])
        commands = list(launcher.commands(args))
        self.assertEqual([name for name, _ in commands], ['mutex', 'rwsem-read', 'rwsem-mixed'])
        for name, argv in commands:
            plan = run.make_plan(run.parser().parse_args(argv[2:]))
            self.assertEqual(len(plan), 6)
            family, percent = launcher.PROFILES[name]
            self.assertTrue(all(r['lock_kind'] == family and r['write_percent'] == percent and
                                r['repeat'] == 0 and r['workload'] == 'nano' for r in plan))

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

    def test_unsupported_mutex_mixes_and_nano_spin_are_refused(self):
        for argv in (['--lock-kind', 'mutex', '--workloads', 'nano', '--write-percent', '1'],
                     ['--lock-kind', 'mutex', '--workloads', 'cacheline', '--write-percent', '100'],
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
