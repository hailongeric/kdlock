"""Direct comparison matrix and result exclusion; no modules are loaded."""
from argparse import Namespace
import copy
import contextlib
import io
import sys
from unittest.mock import Mock, patch
import json
from pathlib import Path
import tempfile
import unittest

import run
from session import (BackendSession, hash_layout, tc_quiescent, check_jit_evidence,
                     check_kd_parameters, parse_owned_preflight_profile,
                     parse_owned_local_first_profile)
from bench_session import Session
from context_audit import audit as audit_context


class DirectTests(unittest.TestCase):
    def test_owned_local_first_profile_is_distinct_and_strict(self):
        args = dict(cachelines=[1], threads=[4], repeats=1, iterations=100,
                    backends=['native', 'kdlock'], lock_kind='mutex', mutex_implementation='owned-v1',
                    owned_mutex_cabi=True, profile_lock=True)
        native, record = run.make_plan(Namespace(**args))
        self.assertFalse(native['profile_owned_local_first'])
        self.assertTrue(record['profile_owned_local_first'])
        self.assertFalse(record['profile_owned_preflight'])
        receipt = 'kd_mutex_profile ownedlocalfirst: acquired=7 failed=2 missed=0\n'
        expected = dict(acquired=7, failed=2, missed=0)
        self.assertEqual(parse_owned_local_first_profile(receipt, record), expected)
        self.assertIsNone(parse_owned_local_first_profile('', native))
        for log in ('', receipt+receipt, receipt.replace('failed=2', 'extra=1'),
                    receipt.replace('missed=0', 'missed=1'),
                    receipt.replace('failed=2', 'failed=-1'),
                    receipt.replace('failed=2', 'acquired=3'), receipt.rstrip()+' extra=1\n'):
            with self.subTest(log=log), self.assertRaises(run.Failure):
                parse_owned_local_first_profile(log, record)
        for changes in (dict(profile_owned_local_first=False), dict(diagnostic=False),
                        dict(owned_acquire_policy='capture_admission'), dict(owned_mutex_cabi=False),
                        dict(profile_owned_preflight=True)):
            with self.subTest(changes=changes), self.assertRaises(run.Failure):
                parse_owned_local_first_profile(receipt, dict(record, **changes))

    def test_owned_cabi_stage_controls_preserve_default_and_reject_invalid_combinations(self):
        args = dict(cachelines=[1], threads=[4], repeats=1, iterations=100,
                    backends=['native', 'tclock', 'kdlock'], lock_kind='mutex',
                    mutex_implementation='owned-v1')
        default = run.make_plan(Namespace(**args))[-1]
        self.assertEqual((default['entry_abi'], default['owned_caller_policy']), (2, 'clobber_v1'))
        self.assertEqual(default['owned_acquire_policy'], 'capture_admission')
        self.assertEqual(default['owned_release_policy'], 'guarded_owner_release')
        rows = run.make_plan(Namespace(**args, owned_mutex_cabi=True))
        row = rows[-1]
        self.assertEqual(row['entry_abi'], 4)
        self.assertEqual(row['owned_acquire_policy'], 'linux_local_first')
        self.assertEqual(row['owned_release_policy'], 'guarded_owner_release')
        self.assertNotEqual(row['name'], default['name'])
        for control in rows[:-1]:
            self.assertFalse(control['owned_mutex_cabi'])
            self.assertEqual(control['owned_acquire_policy'], 'not_applicable')
            self.assertEqual(control['owned_release_policy'], 'not_applicable')
            self.assertIsNone(control['owned_entry_abi'])
        for changes in (dict(owned_mutex_cabi=1),
                        dict(owned_mutex_cabi=True, owned_mutex_preflight=True),
                        dict(owned_mutex_cabi=True, mutex_implementation='legacy')):
            with self.subTest(changes=changes), self.assertRaises(run.Failure):
                run.make_plan(Namespace(**dict(args, **changes)))

    def test_owned_reuse_grace_identity_and_scope(self):
        args = dict(cachelines=[1], threads=[3], repeats=1, iterations=100,
                    backends=['kdlock'], lock_kind='mutex', mutex_implementation='owned-v1',
                    owned_mutex_cabi=True)
        names = set()
        for spins in (0, 8, 32, 128):
            row, = run.make_plan(Namespace(**args, owned_mutex_reuse_spins=spins))
            self.assertEqual(row['owned_mutex_reuse_spins'], spins)
            self.assertNotIn(row['name'], names)
            names.add(row['name'])
        for change in (dict(owned_mutex_reuse_spins=True), dict(owned_mutex_reuse_spins=64),
                       dict(owned_mutex_reuse_spins=8, owned_mutex_cabi=False)):
            with self.subTest(change=change), self.assertRaises(run.Failure):
                run.make_plan(Namespace(**dict(args, **change)))

    def test_owned_cabi_import_audit_excludes_other_outer_paths(self):
        common = {'kd_owned_mutex_prepare', 'kd_mutex_init', 'kd_owned_mutex_is_idle'}
        abi4 = common | {'kd_owned_mutex_outer_lock_cabi_v2', 'kd_owned_mutex_outer_unlock_cabi_v2'}
        abi2 = common | {'kd_owned_mutex_outer_contended_clobber_v1',
                         'kd_owned_mutex_outer_unlock_v1', 'kd_owned_mutex_direct_unlock_clobber_v1'}
        run.owned_workload_imports(' '.join(abi4), cabi=True)
        run.owned_workload_imports(' '.join(abi2))
        for wrong in ('mutex_lock', 'mutex_unlock', 'kd_owned_mutex_outer_preflight_v1',
                      'kd_owned_mutex_outer_contended_clobber_v1', 'kd_owned_mutex_outer_unlock_v1'):
            with self.subTest(wrong=wrong), self.assertRaises(run.Failure):
                run.owned_workload_imports(' '.join(abi4 | {wrong}), cabi=True)
        for missing in abi4:
            with self.subTest(missing=missing), self.assertRaises(run.Failure):
                run.owned_workload_imports(' '.join(abi4 - {missing}), cabi=True)
        with self.assertRaises(run.Failure):
            run.owned_workload_imports(' '.join(abi4))
        with self.assertRaises(run.Failure):
            run.owned_workload_imports(' '.join(abi4), cabi=True, preflight=True)

    def test_owned_cabi_provider_load_and_readback_are_exact(self):
        record, = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=1,
            iterations=100, backends=['kdlock'], lock_kind='mutex',
            mutex_implementation='owned-v1', owned_mutex_cabi=True))
        session = BackendSession.__new__(BackendSession)
        session.record = record
        captured = []
        def command(args, log):
            if log == 'load-kdlock.log':
                captured.extend(args)
                raise RuntimeError('captured')
        session.run = command
        with self.assertRaisesRegex(RuntimeError, 'captured'):
            session.prepare()
        self.assertFalse(any(str(arg).startswith(('owned_mutex_native_first=',
                         'owned_mutex_native_first_spins=', 'owned_mutex_early_release='))
                         for arg in captured))
        params = dict(bench_quiet='Y', jit_timing='N', bench_lock_addr='4096',
            spin_entry_ratio_limit='2', spin_prefetch='2', spin_delegate='Y',
            mutex_native_route='N', owned_mutex_spin_limit='4096',
            owned_mutex_entry_ratio_limit='256', owned_mutex_self_route='N',
            owned_mutex_native_after_control='0', owned_mutex_refill='N',
            owned_mutex_preflight_spins='0', owned_mutex_preflight_queue='N',
            owned_mutex_reuse_spins='0', owned_mutex_protocol='linux_local_first_v1',
            owned_mutex_origin_spin='N', owned_mutex_numa='N')
        check_kd_parameters(params, record, 4096)
        for value in ('', 'old_protocol'):
            with self.subTest(value=value), self.assertRaises(run.Failure):
                check_kd_parameters(dict(params, owned_mutex_protocol=value), record, 4096)
        missing = dict(params); del missing['owned_mutex_protocol']
        with self.assertRaises(run.Failure):
            check_kd_parameters(missing, record, 4096)
        for key in ('owned_mutex_native_first', 'owned_mutex_native_first_spins',
                    'owned_mutex_early_release'):
            with self.subTest(key=key), self.assertRaises(run.Failure):
                check_kd_parameters(dict(params, **{key: '0'}), record, 4096)
        for changes in (dict(entry_abi=2), dict(owned_entry_abi=2),
                        dict(owned_caller_policy='clobber_v1'), dict(caller_abi='clobber'),
                        dict(owned_mutex_cabi=False), dict(owned_mutex_preflight=True)):
            with self.subTest(changes=changes), self.assertRaises(run.Failure):
                check_kd_parameters(params, dict(record, **changes), 4096)

    def test_owned_mutex_plan_preserves_controls_and_distinct_identity(self):
        args = Namespace(cachelines=[1], threads=[4], repeats=3, iterations=100,
                         backends=['native', 'tclock', 'kdlock'], lock_kind='mutex',
                         mutex_implementation='owned-v1', owned_mutex_entry_ratio_limit=8)
        plan = run.make_plan(args)
        self.assertEqual(len(plan), 9)
        for row in plan:
            if row['arm'] == 'kdlock':
                self.assertEqual(row['mutex_implementation'], 'owned-v1')
                self.assertEqual((row['registry_lock_kind'], row['entry_abi']), (3, 2))
                self.assertEqual(row['owned_mutex_entry_ratio_limit'], 8)
                self.assertIsNone(row['mutex_entry_ratio_limit'])
                self.assertTrue(row['name'].endswith('-owned-v1-capture-first'))
            else:
                self.assertEqual(row['mutex_implementation'], 'not_applicable')
                self.assertIsNone(row['owned_mutex_entry_ratio_limit'])
                self.assertEqual(row['registry_lock_kind'], 2)
        legacy = run.make_plan(Namespace(**dict(vars(args), mutex_implementation='legacy',
                                               owned_mutex_entry_ratio_limit=256)))
        self.assertTrue(all(row['name'] not in {r['name'] for r in plan if r['arm'] == 'kdlock'}
                            for row in legacy if row['arm'] == 'kdlock'))

    def test_owned_preflight_plan_scope_and_distinct_identity(self):
        args = dict(cachelines=[1], threads=[4], repeats=1, iterations=100,
                    backends=['native', 'tclock', 'kdlock'], lock_kind='mutex',
                    mutex_implementation='owned-v1', owned_mutex_preflight=True)
        names = set()
        for budget in run.OWNED_MUTEX_PREFLIGHT_SPINS:
            rows = run.make_plan(Namespace(**args, owned_mutex_preflight_spins=budget))
            for row in rows:
                if row['arm'] == 'kdlock':
                    self.assertEqual(row['owned_preflight_policy'], 'c_abi_v1')
                    self.assertEqual(row['owned_mutex_preflight_spins'], budget)
                    names.add(row['name'])
                else:
                    self.assertEqual(row['owned_preflight_policy'], 'not_applicable')
                    self.assertIsNone(row['owned_mutex_preflight_spins'])
        self.assertEqual(len(names), len(run.OWNED_MUTEX_PREFLIGHT_SPINS))
        for budget in (-1, 1, 65, 4097, True):
            with self.subTest(budget=budget), self.assertRaises(run.Failure):
                run.make_plan(Namespace(**args, owned_mutex_preflight_spins=budget))
        for changes in (dict(mutex_implementation='legacy'), dict(lock_kind='spin')):
            with self.subTest(changes=changes), self.assertRaises(run.Failure):
                run.make_plan(Namespace(**dict(args, **changes), owned_mutex_preflight_spins=64))
        for key in ('owned_preflight_policy', 'owned_mutex_preflight_spins', 'owned_mutex_preflight'):
            self.assertIn(key, run.MUTEX_POLICY_FIELDS)

    def test_owned_preflight_requires_explicit_caller_opt_in(self):
        args = dict(cachelines=[1], threads=[4], repeats=1, iterations=100,
                    backends=['kdlock'], lock_kind='mutex', mutex_implementation='owned-v1')
        default, = run.make_plan(Namespace(**args))
        gate, = run.make_plan(Namespace(**args, owned_mutex_preflight=True))
        self.assertEqual(default['owned_preflight_policy'], 'capture_first')
        self.assertFalse(default['owned_mutex_preflight'])
        self.assertEqual(default['owned_mutex_preflight_spins'], 0)
        self.assertEqual(gate['owned_preflight_policy'], 'c_abi_v1')
        self.assertTrue(gate['owned_mutex_preflight'])
        self.assertNotEqual(default['name'], gate['name'])
        for changes in (dict(owned_mutex_preflight_spins=64),
                        dict(owned_mutex_preflight_queue=True),
                        dict(owned_mutex_preflight=1),
                        dict(owned_mutex_preflight=True, mutex_implementation='legacy')):
            with self.subTest(changes=changes), self.assertRaises(run.Failure):
                run.make_plan(Namespace(**dict(args, **changes)))

    def test_owned_preflight_summary_separates_gate_zero_from_earlier_source(self):
        args = dict(cachelines=[1], threads=[4], repeats=1, iterations=100,
                    backends=['kdlock'], lock_kind='mutex', mutex_implementation='owned-v1', owned_mutex_preflight=True,
                    mutex_acceptance='adaptive-performance')
        plans = [run.make_plan(Namespace(**args, owned_mutex_preflight_spins=budget))[0]
                 for budget in (0, 64, 256)]
        previous = dict(plans[0], name=plans[0]['name']+'-capture-first')
        del previous['owned_preflight_policy'], previous['owned_mutex_preflight_spins']
        del previous['owned_mutex_preflight_queue'], previous['owned_mutex_preflight']
        plans.append(previous)
        plans.append(run.make_plan(Namespace(**dict(args, owned_mutex_preflight=False)))[0])
        historical_gate = dict(plans[0], name=plans[0]['name']+'-implicit-gate')
        del historical_gate['owned_mutex_preflight']
        plans.append(historical_gate)
        plans.append(run.make_plan(Namespace(**args, owned_mutex_preflight_spins=64,
            owned_mutex_preflight_queue=True))[0])
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plans)
            for spec in plans:
                folder = out/spec['name']; folder.mkdir()
                row = dict(spec, execution_status='OK', drained=True, jit_bodies=0,
                    measurement=dict(complete=True, data_ok=True, completed=100, wall_ns=100000))
                check_jit_evidence(row)
                run.write_json(folder/'session.json', row)
            run.report(out)
            summary = json.loads((out/'summary.json').read_text())
            self.assertEqual(len(summary), 7)
            self.assertTrue(all(row['sessions'] == row['valid'] == 1 for row in summary))

    def test_owned_preflight_is_passed_to_provider(self):
        session = BackendSession.__new__(BackendSession)
        session.record = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=1,
            iterations=100, backends=['kdlock'], lock_kind='mutex',
            mutex_implementation='owned-v1', owned_mutex_preflight=True, owned_mutex_preflight_spins=256,
            owned_mutex_preflight_queue=True))[0]
        commands = []
        def command(args, log):
            commands.append((args, log))
            if log == 'load-kdlock.log':
                raise RuntimeError('captured provider command')
        session.run = command
        with self.assertRaisesRegex(RuntimeError, 'captured provider command'):
            session.prepare()
        args, = [args for args, log in commands if log == 'load-kdlock.log']
        self.assertIn('owned_mutex_preflight_spins=256', args)
        self.assertIn('owned_mutex_preflight_queue=1', args)
        self.assertFalse(any(str(arg).startswith('mutex_native_route=') for arg in args))

    def test_queued_preflight_plan_scope_and_provider_identity(self):
        args = dict(cachelines=[1], threads=[4], repeats=1, iterations=100,
                    backends=['native', 'tclock', 'kdlock'], lock_kind='mutex',
                    mutex_implementation='owned-v1', owned_mutex_preflight=True, owned_mutex_preflight_spins=64)
        ordinary = run.make_plan(Namespace(**args))
        queued = run.make_plan(Namespace(**args, owned_mutex_preflight_queue=True))
        self.assertTrue(all(not row['owned_mutex_preflight_queue'] for row in ordinary))
        self.assertEqual([row['owned_mutex_preflight_queue'] for row in queued], [False, False, True])
        self.assertNotEqual(ordinary[-1]['name'], queued[-1]['name'])
        for change in (dict(owned_mutex_preflight_spins=0), dict(mutex_implementation='legacy'),
                       dict(lock_kind='spin'), dict(owned_mutex_preflight=False)):
            with self.subTest(change=change), self.assertRaises(run.Failure):
                run.make_plan(Namespace(**dict(args, **change), owned_mutex_preflight_queue=True))
        self.assertIn('owned_mutex_preflight_queue', run.MUTEX_POLICY_FIELDS)

    def test_owned_mutex_rejects_unvalidated_scope_and_native_alias(self):
        base = dict(cachelines=[1], threads=[4], repeats=1, iterations=100,
                    backends=['kdlock'], lock_kind='mutex', mutex_implementation='owned-v1')
        for change in (dict(cachelines=[8]), dict(cachelines=[1, 8]),
                       dict(workload='rcuht', cachelines=None), dict(lock_kind='spin'),
                       dict(backends=['native']), dict(scenario='nested'),
                       dict(mutex_routing='native'),
                       dict(mutex_entry_ratio_limit=2)):
            with self.subTest(change=change), self.assertRaises(run.Failure):
                run.make_plan(Namespace(**dict(base, **change)))
        for change in (dict(mutex_routing='self'), dict(owned_mutex_entry_ratio_limit=2)):
            with self.subTest(change=change), self.assertRaises(run.Failure):
                run.make_plan(Namespace(**dict(base, mutex_implementation='legacy', **change)))

    def test_owned_profile_is_diagnostic(self):
        row, = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=1,
            iterations=100, backends=['kdlock'], lock_kind='mutex',
            mutex_implementation='owned-v1', owned_mutex_preflight=True, profile_lock=True))
        self.assertTrue(row['diagnostic'])
        self.assertTrue(row['profile_lock'])
        self.assertTrue(row['profile_owned_preflight'])
        default, = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=1,
            iterations=100, backends=['kdlock'], lock_kind='mutex',
            mutex_implementation='owned-v1', profile_lock=True))
        self.assertTrue(default['profile_lock'])
        self.assertFalse(default['profile_owned_preflight'])
        controls = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=1,
            iterations=100, backends=['native', 'kdlock'], lock_kind='mutex',
            mutex_implementation='legacy', profile_lock=True))
        self.assertTrue(all(not row['profile_owned_preflight'] for row in controls))
        row, = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=1,
            iterations=100, backends=['kdlock'], lock_kind='mutex', mutex_implementation='owned-v1'))
        self.assertFalse(row['profile_owned_preflight'])

    def test_owned_preflight_profile_receipt_is_optional_only_for_old_runs(self):
        record = dict(arm='kdlock', mutex_implementation='owned-v1',
            owned_preflight_policy='c_abi_v1', diagnostic=True, profile_lock=True,
            profile_owned_preflight=True)
        line = ('kd_mutex_profile ownedpreflight: gate_self=8 gate_capture=2 '
                'optimistic_acquired=3 optimistic_busy=4 optimistic_self=1 '
                'optimistic_other=0 missed=0\n')
        result = parse_owned_preflight_profile(line, record)
        self.assertEqual(result['gate_self'], 8)
        self.assertEqual(result['optimistic_busy'], 4)
        self.assertIsNone(parse_owned_preflight_profile('old profile log', {}))
        self.assertIsNone(parse_owned_preflight_profile('old profile log',
                          dict(record, profile_owned_preflight=False)))
        for text in ('', line+line, line.replace('missed=0', 'missed=1'),
                     line.replace('optimistic_other=0', 'optimistic_other=1'),
                     line.replace('gate_self=8', 'gate_self=0'),
                     line.replace('gate_capture=2', 'gate_capture=5'),
                     line.replace('optimistic_busy=4', 'optimistic_busy=40'),
                     line.replace(' missed=0', ''), line.replace('missed=0', 'missed=-1'),
                     line.replace('missed=0', 'missed=0 missed=0'),
                     line.replace('missed=0', 'missed=0.5'),
                     line.replace('missed=0', 'missed=0 ignored=garbage'),
                     line.replace('missed=0', 'missed=0 trailing')):
            with self.subTest(text=text), self.assertRaises(run.Failure):
                parse_owned_preflight_profile(text, record)
        for changes in (dict(profile_owned_preflight=False), dict(diagnostic=False),
                        dict(profile_lock=False), dict(mutex_implementation='legacy'),
                        dict(owned_preflight_policy=None), dict(arm='native')):
            with self.subTest(changes=changes), self.assertRaises(run.Failure):
                parse_owned_preflight_profile(line, dict(record, **changes))

    def test_preflight_probes_load_only_for_declared_owned_profile(self):
        for implementation, enabled in (('owned-v1', True), ('owned-v1', False), ('legacy', False)):
            session = BackendSession.__new__(BackendSession)
            session.loaded_kd = True
            session.lock_kind = 'mutex'
            session.record = dict(arm='kdlock', mutex_implementation=implementation,
                profile_lock=True, profile_owned_preflight=enabled, diagnostic=True,
                owned_preflight_policy='c_abi_v1' if implementation == 'owned-v1' else 'not_applicable',
                collector_cpu=63, layout=dict(lock_addr=4096))
            commands = []
            def command(args, log):
                commands.append((args, log))
                if log == 'load-profile.log':
                    raise RuntimeError('captured profiler command')
            session.run = command
            symbols = ('00002000 d kd_owned_mutex_bodies [kdlock_km]\n'
                       '00003000 d kd_mutex_jit_success_count [kdlock_km]\n')
            with patch.object(Path, 'read_text', return_value=symbols), \
                    self.assertRaisesRegex(RuntimeError, 'captured profiler command'):
                session.measure()
            args, = [args for args, log in commands if log == 'load-profile.log']
            self.assertEqual('preflight=1' in args, enabled)

    def test_owned_refill_has_distinct_queue_identity(self):
        args = dict(cachelines=[1], threads=[4], repeats=1, iterations=100,
                    backends=['kdlock'], lock_kind='mutex', mutex_implementation='owned-v1')
        finite, = run.make_plan(Namespace(**args))
        refill, = run.make_plan(Namespace(**args, owned_mutex_refill=True))
        self.assertEqual(finite['owned_queue_policy'], 'finite_fifo')
        self.assertFalse(finite['owned_mutex_refill'])
        self.assertEqual(refill['owned_queue_policy'], 'bounded_fifo_refill')
        self.assertTrue(refill['owned_mutex_refill'])
        self.assertNotEqual(finite['name'], refill['name'])
        with self.assertRaises(run.Failure):
            run.make_plan(Namespace(**dict(args, mutex_implementation='legacy'), owned_mutex_refill=True))

    def test_owned_full_probe_is_functional_only(self):
        base = dict(cachelines=[1], threads=[4], repeats=1, iterations=100,
            backends=['kdlock'], lock_kind='mutex', mutex_implementation='owned-v1',
            functional=True, scenario='early', owned_mutex_force_full=True)
        row, = run.make_plan(Namespace(**base))
        self.assertTrue(row['diagnostic'] and row['owned_mutex_force_full'])
        for change in (dict(functional=False), dict(scenario='plain'),
                       dict(mutex_implementation='legacy'), dict(backends=['native', 'kdlock'])):
            with self.subTest(change=change), self.assertRaises(run.Failure):
                run.make_plan(Namespace(**dict(base, **change)))

    def test_owned_nested_and_early_are_functional_only(self):
        base = dict(cachelines=[1], threads=[4], repeats=1, iterations=100,
                    backends=['kdlock'], lock_kind='mutex', mutex_implementation='owned-v1',
                    functional=True)
        for scenario in ('nested', 'early'):
            row, = run.make_plan(Namespace(**base, scenario=scenario))
            self.assertEqual(row['scenario'], scenario)
            self.assertEqual((row['registry_lock_kind'], row['entry_abi']), (3, 2))
            self.assertEqual(row['measurement_mode'], 'fixed_iterations')
            for change in (dict(functional=False), dict(mutex_implementation='legacy'),
                           dict(repeats=3), dict(backends=['native', 'kdlock']),
                           dict(mutex_routing='self'), dict(mutex_acceptance='adaptive-performance'),
                           dict(duration_ms=2000, collector_cpu=63)):
                with self.subTest(scenario=scenario, change=change), self.assertRaises(run.Failure):
                    run.make_plan(Namespace(**dict(base, scenario=scenario, **change)))
            with self.assertRaisesRegex(run.Failure, 'no actual JIT'):
                check_jit_evidence(dict(row, functional=True, jit_bodies=0))
            check_jit_evidence(dict(row, functional=True, jit_bodies=1))

    def test_owned_execution_distinguishes_self_from_linux_and_jit(self):
        base = dict(arm='kdlock', lock_kind='mutex', threads=16, jit_bodies=0,
                    mutex_implementation='owned-v1', mutex_acceptance='adaptive-performance')
        record = dict(base)
        check_jit_evidence(record)
        self.assertEqual((record['execution_class'], record['jit_acceptance']),
                         ('KD_SELF', 'ADAPTIVE_SELF'))
        record = dict(base, jit_bodies=1)
        check_jit_evidence(record)
        self.assertEqual((record['execution_class'], record['jit_acceptance']), ('JIT', 'PASS'))
        record = dict(base, mutex_routing='self')
        check_jit_evidence(record)
        self.assertEqual(record['execution_class'], 'KD_SELF')
        self.assertEqual(record['jit_acceptance'], 'SELF_ROUTING_CONTROL')
        self.assertTrue(record['diagnostic'])
        for change in (dict(jit_bodies=1), dict(functional=True), dict(mutex_implementation='legacy')):
            with self.subTest(change=change), self.assertRaises(run.Failure):
                check_jit_evidence(dict(record, **change))
        with self.assertRaises(run.Failure):
            check_jit_evidence(dict(base, mutex_routing='native'))
        with self.assertRaisesRegex(run.Failure, 'no actual JIT'):
            check_jit_evidence(dict(base, mutex_acceptance='jit-required'))

    def test_owned_parameter_identity_uses_its_own_sampler_and_route(self):
        record = dict(spin_entry_ratio_limit=2, spin_prefetch=2, spin_delegate='on',
                      mutex_wait_mode='blocking', mutex_spin_limit=4096,
                      mutex_implementation='owned-v1', owned_mutex_entry_ratio_limit=8,
                      mutex_routing='self', mutex_entry_ratio_limit=None)
        params = dict(bench_quiet='Y', jit_timing='N', bench_lock_addr='4096',
                      spin_entry_ratio_limit='2', spin_prefetch='2', spin_delegate='Y',
                      mutex_native_route='N', mutex_entry_ratio_limit='256',
                      owned_mutex_spin_limit='4096', owned_mutex_entry_ratio_limit='8',
                      owned_mutex_self_route='Y', owned_mutex_native_after_control='0')
        check_kd_parameters(params, record, 4096)
        # Historical records omit the gate; new records must prove its budget.
        with self.assertRaisesRegex(run.Failure, 'preflight'):
            check_kd_parameters(dict(params, owned_mutex_preflight_spins='64'), record, 4096)
        record.update(owned_preflight_policy='c_abi_v1', owned_mutex_preflight_spins=64)
        with self.assertRaisesRegex(run.Failure, 'preflight'):
            check_kd_parameters(params, record, 4096)
        params['owned_mutex_preflight_spins'] = '64'
        check_kd_parameters(params, record, 4096)
        check_kd_parameters(params, dict(record, owned_mutex_preflight=True), 4096)
        for flag in (False, 1, None):
            with self.subTest(flag=flag), self.assertRaisesRegex(run.Failure, 'compile-time'):
                check_kd_parameters(params, dict(record, owned_mutex_preflight=flag), 4096)
        capture = dict(record, owned_mutex_preflight=False, owned_preflight_policy='capture_first',
                       owned_mutex_preflight_spins=0, owned_mutex_preflight_queue=False)
        capture_params = dict(params, owned_mutex_preflight_spins='0', owned_mutex_preflight_queue='N')
        check_kd_parameters(capture_params, capture, 4096)
        with self.assertRaisesRegex(run.Failure, 'preflight'):
            check_kd_parameters(params, capture, 4096)
        with self.assertRaisesRegex(run.Failure, 'preflight'):
            check_kd_parameters(dict(params, owned_mutex_preflight_spins='0'), record, 4096)
        with self.assertRaisesRegex(run.Failure, 'queued preflight'):
            check_kd_parameters(dict(params, owned_mutex_preflight_queue='Y'), record, 4096)
        record['owned_mutex_preflight_queue'] = True
        with self.assertRaisesRegex(run.Failure, 'queued preflight'):
            check_kd_parameters(params, record, 4096)
        params['owned_mutex_preflight_queue'] = 'Y'
        check_kd_parameters(params, record, 4096)
        with self.assertRaisesRegex(run.Failure, 'queued preflight'):
            check_kd_parameters(dict(params, owned_mutex_preflight_queue='N'), record, 4096)
        record['owned_mutex_refill'] = True
        with self.assertRaisesRegex(run.Failure, 'refill parameter'):
            check_kd_parameters(params, record, 4096)
        params['owned_mutex_refill'] = 'Y'
        check_kd_parameters(params, record, 4096)
        record['owned_mutex_refill'] = False
        with self.assertRaisesRegex(run.Failure, 'refill parameter'):
            check_kd_parameters(params, record, 4096)
        params['owned_mutex_refill'] = 'N'
        for change in (dict(owned_mutex_entry_ratio_limit='256'), dict(owned_mutex_self_route='N'),
                       dict(mutex_native_route='Y'), dict(owned_mutex_native_after_control='1')):
            with self.subTest(change=change), self.assertRaises(run.Failure):
                check_kd_parameters(dict(params, **change), record, 4096)
        del params['owned_mutex_self_route']
        with self.assertRaisesRegex(run.Failure, 'missing owned'):
            check_kd_parameters(params, record, 4096)

    def test_report_keeps_owned_legacy_and_self_diagnostic_separate(self):
        args = dict(cachelines=[1], threads=[4], repeats=1, iterations=100,
                    backends=['kdlock'], lock_kind='mutex', mutex_acceptance='adaptive-performance')
        legacy, = run.make_plan(Namespace(**args))
        owned, = run.make_plan(Namespace(**args, mutex_implementation='owned-v1'))
        control, = run.make_plan(Namespace(**args, mutex_implementation='owned-v1', mutex_routing='self'))
        control['name'] += '-self'
        plans = [legacy, owned, control]
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plans)
            for spec in plans:
                folder = out/spec['name']; folder.mkdir()
                row = dict(spec, execution_status='OK', drained=True, jit_bodies=0,
                           measurement=dict(complete=True, data_ok=True, completed=100, wall_ns=100000))
                check_jit_evidence(row)
                run.write_json(folder/'session.json', row)
            run.report(out)
            summary = json.loads((out/'summary.json').read_text())
            self.assertEqual(len(summary), 3)
            self.assertEqual(sum(row['valid'] for row in summary), 2)
            owned_rows = [r for r in summary if r['mutex_implementation'] == 'owned-v1']
            self.assertTrue(all(r['execution_classes'] == ['KD_SELF'] for r in owned_rows))
            self.assertIsNone(next(r for r in owned_rows if r['diagnostic'])['best_session'])

    def test_mutex_plan_uses_blocking_with_one_session_per_backend(self):
        plan = run.make_plan(Namespace(cachelines=[16], threads=[16], repeats=3,
            iterations=100, backends=['native', 'tclock', 'kdlock'],
            lock_kind='mutex'))
        self.assertEqual(len(plan), 9)
        self.assertEqual(len({r['name'] for r in plan}), len(plan))
        for repeat in range(3):
            rows = [r for r in plan if r['repeat'] == repeat]
            kd = [r for r in rows if r['arm'] == 'kdlock']
            self.assertEqual([r['mutex_wait_mode'] for r in kd], ['blocking'])
            self.assertEqual({r['mutex_spin_limit'] for r in kd}, {4096})
            self.assertEqual([r['arm'] for r in rows].count('native'), 1)
            self.assertEqual([r['arm'] for r in rows].count('tclock'), 1)

    def test_provider_identity_rejects_obsolete_mutex_switches(self):
        record = dict(spin_entry_ratio_limit=2, spin_prefetch=2,
                      mutex_entry_ratio_limit=256, mutex_routing='adaptive',
                      spin_delegate='on', mutex_wait_mode='blocking', mutex_spin_limit=4096)
        params = dict(bench_quiet='Y', jit_timing='N', bench_lock_addr='4096',
                      mutex_entry_ratio_limit='256', mutex_native_route='N',
                      mutex_spin_limit='4096',
                      spin_entry_ratio_limit='2', spin_prefetch='2', spin_delegate='Y')
        check_kd_parameters(params, record, 4096)
        for key, value in (('mutex_entry_ratio_limit', '2'), ('mutex_native_route', 'Y')):
            with self.assertRaises(run.Failure):
                check_kd_parameters(dict(params, **{key: value}), record, 4096)
        for name in ('mutex_jit', 'mutex_blocking'):
            for value in ('N', 'Y'):
                with self.subTest(name=name, value=value), self.assertRaises(run.Failure):
                    check_kd_parameters(dict(params, **{name: value}), record, 4096)

    def test_mutex_runner_rejects_removed_wait_mode(self):
        for mode in ('spin', 'blocking', 'both'):
            argv = ['run_mutex.py', '--output', '/tmp/unused', '--dry-run',
                    '--mutex-wait-mode', mode]
            with self.subTest(mode=mode), patch.object(sys, 'argv', argv), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                run.main('mutex')
            self.assertEqual(error.exception.code, 2)

    def test_mutex_runner_rejects_spin_disabled_control(self):
        args = Namespace(cachelines=[1], threads=[16], repeats=1,
                         iterations=100, backends=['kdlock'],
                         lock_kind='mutex', spin_delegate='off')
        with self.assertRaisesRegex(run.Failure, 'mutex JIT is required'):
            run.make_plan(args)
        argv = ['run_mutex.py', '--output', '/tmp/unused', '--dry-run',
                '--spin-delegate', 'off']
        with patch.object(sys, 'argv', argv), \
                self.assertRaisesRegex(run.Failure, 'mutex JIT is required'):
            run.main('mutex')

    def test_mutex_cannot_bypass_returned_body_acceptance(self):
        record = dict(arm='kdlock', lock_kind='mutex', threads=16,
                      jit_bodies=0, scenario='plain', spin_delegate='off')
        with self.assertRaisesRegex(run.Failure, 'no actual JIT'):
            check_jit_evidence(record)
        self.assertEqual(record['jit_acceptance'], 'NO_JIT')
        check_jit_evidence(record := dict(record, jit_bodies=1))
        self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_mutex_adaptive_performance_is_explicit_and_not_jit(self):
        for threads in (1, 2, 4, 16, 28, 60):
            record = dict(arm='kdlock', lock_kind='mutex', threads=threads,
                          mutex_acceptance='adaptive-performance', jit_bodies=0)
            check_jit_evidence(record)
            self.assertEqual(record['jit_acceptance'], 'ADAPTIVE_NATIVE')
            self.assertEqual(record['execution_class'], 'ADAPTIVE_NATIVE')
            with self.assertRaises(run.Failure):
                check_jit_evidence(dict(record, functional=True))
            check_jit_evidence(record := dict(record, jit_bodies=1))
            self.assertEqual(record['execution_class'], 'JIT')

    def test_mutex_native_control_rejects_jit_and_is_unscored(self):
        record = dict(arm='kdlock', lock_kind='mutex', threads=16,
                      mutex_routing='native', jit_bodies=0)
        check_jit_evidence(record)
        self.assertTrue(record['diagnostic'])
        self.assertEqual(record['execution_class'], 'NATIVE_ROUTING_CONTROL')
        with self.assertRaisesRegex(run.Failure, 'control executed JIT'):
            check_jit_evidence(dict(record, jit_bodies=1))

    def test_report_excludes_diagnostics_and_separates_mutex_thresholds(self):
        base, = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=1,
            iterations=100, backends=['kdlock'], lock_kind='mutex',
            mutex_acceptance='adaptive-performance'))
        plans = [dict(base, name=str(i), mutex_entry_ratio_limit=limit, diagnostic=diagnostic)
                 for i, (limit, diagnostic) in enumerate(((2, False), (4, False), (2, True)))]
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out/'plan.json').write_text(json.dumps(plans))
            for spec in plans:
                (out/spec['name']).mkdir()
                row = dict(spec, execution_status='OK', drained=True, jit_bodies=0,
                           execution_class='ADAPTIVE_NATIVE',
                           measurement=dict(complete=True, data_ok=True, completed=100, wall_ns=100000))
                (out/spec['name']/'session.json').write_text(json.dumps(row))
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            self.assertEqual(len(rows), 3)
            for row in rows:
                if row['diagnostic']:
                    self.assertEqual(row['valid'], 0)
                    self.assertIsNone(row['best_session'])
                else:
                    self.assertEqual(row['median_whole_throughput_ops_s'], 1000000)
                    self.assertEqual(row['execution_classes'], ['ADAPTIVE_NATIVE'])

    def test_cpu_samples_are_unscored_for_every_backend(self):
        plan = run.make_plan(Namespace(cachelines=[1], threads=[16], repeats=1,
            iterations=100, backends=['native', 'tclock', 'kdlock'],
            lock_kind='mutex', perf_record=True))
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out/'plan.json').write_text(json.dumps(plan))
            for spec in plan:
                self.assertTrue(spec['diagnostic'] and spec['perf_record'])
                (out/spec['name']).mkdir()
                row = dict(spec, execution_status='OK', drained=True, jit_bodies=100,
                           measurement=dict(complete=True, data_ok=True, completed=100, wall_ns=100000))
                (out/spec['name']/'session.json').write_text(json.dumps(row))
            run.report(out)
            self.assertTrue(all(not r['score_eligible'] for r in
                                json.loads((out/'records.json').read_text())))
            self.assertTrue(all(r['valid'] == 0 and r['best_session'] is None for r in
                                json.loads((out/'summary.json').read_text())))

    def test_mutex_thresholds_and_policy_contract(self):
        args = Namespace(cachelines=[1], threads=[4], repeats=3, iterations=100,
                         backends=['native', 'kdlock'], lock_kind='mutex')
        for limit in (2, 4, 8, 16, 32, 64, 128, 256):
            args.mutex_entry_ratio_limit = limit
            rows = run.make_plan(args)
            self.assertEqual([r['arm'] for r in rows],
                             ['native', 'kdlock', 'kdlock', 'native', 'native', 'kdlock'])
            self.assertEqual({r['mutex_entry_ratio_limit'] for r in rows if r['arm']=='kdlock'}, {limit})
        for limit in (0, 1, 3, 512):
            args.mutex_entry_ratio_limit = limit
            with self.assertRaises(run.Failure):
                run.make_plan(args)
        args.mutex_entry_ratio_limit = 256
        args.mutex_acceptance = 'adaptive-performance'
        args.functional = True
        with self.assertRaisesRegex(run.Failure, 'functional checks require'):
            run.make_plan(args)
        args.functional, args.lock_kind = False, 'spin'
        with self.assertRaisesRegex(run.Failure, 'mutex controls require'):
            run.make_plan(args)

    def test_source_snapshot_covers_tclock_fragments(self):
        # A frozen run must include the bodies behind the C entry files;
        # omitting them would allow protocol changes during measurement.
        state = run.source_state()
        fragments = sorted((run.ROOT / 'tclock_backend').glob('*/*.inc'))
        self.assertTrue(fragments)
        for path in fragments:
            with self.subTest(path=path):
                self.assertEqual(state[str(path.relative_to(run.ROOT))],
                                 run.digest(path))
        reader = 'tests/unit/infrastructure/source_text.py'
        self.assertEqual(state[reader], run.digest(run.ROOT / reader))
        for name in ('include/kd_mutex.h', 'include/kd_mutex_legacy.h',
                     'include/kd_owned_mutex_direct.h', 'workload_modules/mutex_cacheline/module.c'):
            self.assertEqual(state[name], run.digest(run.ROOT / name))

    def test_collect_no_jit_preserves_failure_and_requires_verified_drain(self):
        record = dict(execution_status='NO_JIT', jit_acceptance='NO_JIT',
                      jit_bodies=0, drained=True,
                      measurement=dict(complete=True, data_ok=True))
        before = copy.deepcopy(record)
        session = Mock(record=record)
        session.execute.side_effect = run.Failure('NO_JIT', 'missing body')
        with self.assertRaises(run.Failure):
            run.execute_session(session)
        self.assertFalse(run.execute_session(session, True))
        self.assertEqual(record, before)
        # No unsafe, incomplete or contradictory session may be hidden by
        # the optional evidence-collection mode. The original verdict stays.
        variants = [dict(record, drained=False), dict(record, cleanup_error='busy'),
                    dict(record, execution_status='OK'), dict(record, jit_bodies=1),
                    dict(record, jit_acceptance='PASS'),
                    dict(record, measurement=dict(complete=False, data_ok=True)),
                    dict(record, measurement=dict(complete=True, data_ok=False))]
        for bad in variants:
            with self.subTest(record=bad), self.assertRaises(run.Failure):
                run.execute_session(Mock(record=bad, execute=Mock(
                    side_effect=run.Failure('NO_JIT', 'missing body'))), True)
        for status, unsafe in [('NO_JIT', True), ('UNDRAINED', False),
                               ('PREPARATION_FAILED', False)]:
            with self.subTest(status=status, unsafe=unsafe), self.assertRaises(run.Failure):
                run.execute_session(Mock(record=record, execute=Mock(
                    side_effect=run.Failure(status, 'failure', unsafe=unsafe))), True)
        good = Mock(record=dict(execution_status='OK', drained=True))
        self.assertTrue(run.execute_session(good, True))

    def test_collect_no_jit_does_not_change_score_exclusion(self):
        plans = run.make_plan(Namespace(cachelines=[1], threads=[16], repeats=3,
            iterations=100, backends=['kdlock'], cpus=list(range(16))))
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plans)
            for i, spec in enumerate(plans):
                folder = out/spec['name']; folder.mkdir()
                run.write_json(folder/'session.json', dict(spec, drained=True,
                    execution_status='OK' if i == 0 else 'NO_JIT',
                    jit_bodies=1 if i == 0 else 0,
                    measurement=dict(completed=100, wall_ns=100000 if i == 0 else 100,
                                     data_ok=True, complete=True)))
            run.report(out)
            summary = json.loads((out/'summary.json').read_text())[0]
            self.assertEqual(summary['valid'], 1)
            self.assertEqual(summary['best_session'], plans[0]['name'])
            records = json.loads((out/'records.json').read_text())
            self.assertTrue(all(r['throughput_ops_s'] is None for r in records[1:]))

    def test_mutex_entrypoint_and_delegation_identity(self):
        argv = ['run_mutex.py', '--output', '/tmp/unused', '--dry-run',
                '--threads', '16', '36', '--cachelines', '1']
        with patch.object(sys, 'argv', argv), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(run.main('mutex'), 0)
        plan = json.loads(output.getvalue())
        self.assertEqual(len(plan), 18)
        self.assertTrue(all(s['lock_kind'] == 'mutex' for s in plan))
        self.assertTrue(all(s['caller_shell'] == 'mutex_outer_cookie'
                            for s in plan if s['arm'] == 'kdlock'))
        self.assertTrue(all(s['cookie_storage'] == 'outer_acquisition_local'
                            for s in plan if s['arm'] == 'kdlock'))
        params = dict(target_lock=4096, komb_batch_size=1024, quiescent=1,
                      delegated=8192, batches=8, parks=4)
        tc_quiescent(params, 'mutex')
        for bad in (dict(params, quiescent=0),
                    {k: v for k, v in params.items() if k != 'delegated'}):
            with self.assertRaises(run.Failure):
                tc_quiescent(bad, 'mutex')
        # Successful data with zero JIT does not establish a contended positive.
        with self.assertRaisesRegex(run.Failure, 'no actual JIT'):
            check_jit_evidence(dict(arm='kdlock', lock_kind='mutex', threads=16,
                                    jit_bodies=0, scenario='plain'))

    def test_explicit_placement_and_collector(self):
        args = Namespace(cachelines=[1], threads=[8, 16], repeats=1,
                         iterations=100, backends=['native', 'kdlock'],
                         cpus=run.runtime.cpu_list('0-7,20-27'),
                         duration_ms=2000, collector_cpu=38)
        plans = run.make_plan(args)
        self.assertTrue(all(s['cpus'] == args.cpus[:s['threads']] for s in plans))
        args.collector_cpu = 20
        with self.assertRaisesRegex(run.Failure, 'collector CPU'):
            run.make_plan(args)
        args.collector_cpu, args.cpus = 38, [0, 1]
        with self.assertRaisesRegex(run.Failure, 'placement'):
            run.make_plan(args)

    def test_summary_keeps_placement_separate(self):
        # Different node geometries must never supply each other's winner or
        # Linux denominator, even when thread counts and policies match.
        plans = []
        for suffix, cpus in (('local', [0, 1]), ('split', [0, 20])):
            cohort = run.make_plan(Namespace(cachelines=[1], threads=[2], repeats=1,
                iterations=100, backends=['native', 'kdlock'], cpus=cpus))
            plans.extend(dict(s, name=s['name']+'-'+suffix) for s in cohort)
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plans)
            for i, spec in enumerate(plans):
                folder = out/spec['name']; folder.mkdir()
                run.write_json(folder/'session.json', dict(spec,
                    execution_status='OK', drained=True,
                    measurement=dict(completed=100, wall_ns=(i+1)*100000,
                                     data_ok=True, complete=True)))
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            self.assertEqual(len(rows), 4)
            kd = [r for r in rows if r['arm'] == 'kdlock']
            self.assertEqual([r['throughput_over_linux'] for r in kd], [0.5, 0.75])

    def test_provider_ubsan_option_and_private_build(self):
        # Both entrypoints default to off; explicit policies and direct helper
        # callers must agree with the policy saved in every new session.
        for lock_kind, option in ((kind, policy) for kind in ('spin', 'mutex')
                                  for policy in (None, 'kernel', 'off')):
            policy = option or 'off'
            argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                    '--threads', '8', '--cachelines', '1', '--repeats', '1']
            if option is not None:
                argv += ['--kd-provider-ubsan', option]
            with self.subTest(lock_kind=lock_kind, option=option), \
                    patch.object(sys, 'argv', argv), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(run.main(lock_kind), 0)
            plan = json.loads(output.getvalue())
            for spec in plan:
                self.assertEqual(spec['kd_provider_ubsan'],
                                 policy if spec['arm'] == 'kdlock' else 'not_applicable')
            args = Namespace(numa='on', kd_batch_size=1024, cachelines=[1],
                             threads=[8], repeats=1, iterations=100,
                             backends=['kdlock'], lock_kind=lock_kind)
            if option is not None:
                args.kd_provider_ubsan = option
            build = run.provider_build(args)
            self.assertEqual(build[:4], ['make', '-C', run.HERE, 'provider'])
            self.assertEqual('UBSAN_SANITIZE=n' in build, policy == 'off')
            self.assertEqual(run.make_plan(args)[0]['kd_provider_ubsan'], policy)
            # Exercise real session serialization without opening the kernel log.
            spec, = [spec for spec in plan if spec['arm'] == 'kdlock']
            with tempfile.TemporaryDirectory() as temporary, \
                    patch('bench_session.os.open', return_value=17), \
                    patch('bench_session.os.lseek'):
                session = BackendSession(Path(temporary), spec)
                record = json.loads((session.path/'session.json').read_text())
                self.assertEqual(record['kd_provider_ubsan'], policy)

    def test_provider_ubsan_off_rejects_instrumented_elf(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            imported = ' U __ubsan_handle_load_invalid_value\n U printk\n'
            with patch.object(run, 'command', return_value=imported) as command:
                run.audit_provider_ubsan(out, 'kernel')
                with self.assertRaisesRegex(run.Failure, 'still imports UBSAN'):
                    run.audit_provider_ubsan(out, 'off')
                command.assert_called_with(['nm', '-u', run.PROVIDER],
                                           out/'imports-kdlock-provider.txt')
            with patch.object(run, 'command', return_value=' U printk\n'):
                run.audit_provider_ubsan(out, 'off')
            self.assertEqual(json.loads((out/'kdlock-provider-ubsan.json').read_text()),
                             dict(policy='off', imports=[]))

    def test_summary_keeps_provider_ubsan_policies_separate(self):
        spec, = run.make_plan(Namespace(cachelines=[1], threads=[8], repeats=1,
            iterations=100, backends=['kdlock']))
        plan = []
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            for index, policy in enumerate(('kernel', 'off', 'unrecorded'), 1):
                candidate = dict(spec, name=f'provider-{policy}', kd_provider_ubsan=policy)
                if policy == 'unrecorded':
                    del candidate['kd_provider_ubsan']
                plan.append(candidate)
                folder = out/candidate['name']; folder.mkdir()
                run.write_json(folder/'session.json', dict(candidate,
                    execution_status='OK', drained=True,
                    measurement=dict(completed=index * 1000, wall_ns=1000000,
                                     data_ok=True, complete=True)))
            run.write_json(out/'plan.json', plan)
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            self.assertEqual(len(rows), 3)
            self.assertEqual({r['kd_provider_ubsan']: r['best_throughput_ops_s']
                              for r in rows},
                             dict(kernel=1e6, off=2e6, unrecorded=3e6))
            self.assertTrue(all(r['sessions'] == r['valid'] == 1 for r in rows))

    def test_numa_expanded_matrix(self):
        plan = run.make_plan(Namespace(cachelines=[1],
            threads=[1,2,3,4,5,6,7,8,12,16,20,24,28,32,36], repeats=3,
            iterations=100000, backends=['native','tclock','kdlock'],
            duration_ms=2000, collector_cpu=38, numa='on', kd_batch_size=128))
        self.assertEqual(len(plan), 135)
        for spec in plan:
            self.assertNotIn(38, spec['cpus'])
            if spec['arm'] == 'kdlock':
                self.assertEqual(spec['numa_policy'], 'on')
                self.assertEqual(spec['delegation_batch_limit'], 128)
            elif spec['arm'] == 'tclock':
                self.assertEqual(spec['delegation_batch_limit'], 1024)
        with self.assertRaises(run.Failure):
            run.make_plan(Namespace(cachelines=[1], threads=[36], repeats=1,
                iterations=100000, backends=['kdlock'], duration_ms=2000,
                collector_cpu=30))

    def test_timed_session_uses_fixed_warmup_and_continuous_measurement(self):
        session = BackendSession.__new__(BackendSession)
        spec, = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=1,
            iterations=100, backends=['native'], duration_ms=2000))
        session.record = spec
        session.counts = Mock(return_value=dict(active=0))
        session.faults = Mock()
        session.run = Mock(return_value='{}')
        peak = dict(throughput_ops_s=1e6)
        with patch('bench_session.validate_measurement', side_effect=[None, peak]) as validate:
            session.phase('warmup', 48000)
            warmup = session.run.call_args.args[0]
            self.assertIn('--iterations', warmup)
            self.assertNotIn('--duration-ms', warmup)
            self.assertEqual(validate.call_args.args[1]['duration_ms'], 0)
            result = session.phase('measure', 100)
            measure = session.run.call_args.args[0]
            self.assertNotIn('--iterations', measure)
            self.assertIn('--duration-ms', measure)
            self.assertEqual(validate.call_args.args[1]['duration_ms'], 2000)
            self.assertEqual(result['peak'], peak)

    def test_timed_plan_and_peak_summary_keep_whole_run_visible(self):
        args = Namespace(cachelines=[1], threads=[3], repeats=2, iterations=100,
            backends=['native', 'tclock', 'kdlock'],
            duration_ms=2000)
        plan = run.make_plan(args)
        self.assertTrue(all(s['peak_window_ms'] == s['peak_settle_ms'] == 300 and
                            s['sample_ms'] == 10 and s['collector_cpu'] == 30 and
                            s['measurement_mode'] == 'timed_peak' for s in plan))
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plan)
            for spec in plan:
                folder = out/spec['name']; folder.mkdir()
                # Winning peak and winning whole-run mean belong to different
                # rounds. Selection must keep the peak's matching whole rate.
                rate = (2 - spec['repeat']) * 1e6
                whole = (1 + spec['repeat']) * 0.5e6
                run.write_json(folder/'session.json', dict(spec,
                    execution_status='OK', drained=True,
                    measurement=dict(completed=whole * 2, wall_ns=2e9,
                        data_ok=True, complete=True,
                        peak=dict(throughput_ops_s=rate, amortized_ns_op=1e9/rate))))
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            for row in rows:
                self.assertEqual(row['comparison_policy'], 'best_valid_warmed_peak')
                self.assertEqual(row['best_throughput_ops_s'], 2e6)
                self.assertEqual(row['best_whole_throughput_ops_s'], 0.5e6)
                self.assertEqual(row['best_amortized_ns_op'], 500)
                self.assertEqual(row['throughput_over_linux'], 1)
                self.assertEqual(row['min_throughput_ops_s'], 1e6)
        args.collector_cpu = 1
        with self.assertRaisesRegex(run.Failure, 'collector CPU'):
            run.make_plan(args)
        args.collector_cpu, args.duration_ms = 30, 600
        with self.assertRaisesRegex(run.Failure, 'timing intervals'):
            run.make_plan(args)

    def test_shared_collector_rejects_unlabelled_or_partial_overlap(self):
        args = dict(cachelines=[1], threads=[64], repeats=3, iterations=100,
                    backends=['native'], duration_ms=2000, collector_cpu=63,
                    cpus=list(range(64)))
        with self.assertRaisesRegex(run.Failure, 'collector CPU'):
            run.make_plan(Namespace(**args))
        for change in (dict(collector_cpu=62), dict(threads=[60]),
                       dict(cpus=list(range(1,65))), dict(share_collector=1),
                       dict(duration_ms=0)):
            with self.subTest(change=change), self.assertRaises(run.Failure):
                run.make_plan(Namespace(**(args | {'share_collector': True} | change)))

    def test_warmup_uses_all_workers_without_changing_preparation(self):
        cpus, nodes = [2, 7, 11], [0, 1, 0]
        warmup = dict(schema=1, complete=True, data_ok=True, workload='cacheline',
            cachelines=1, threads=3, iterations=48000, completed=144000,
            worker_cpu_ns=60, started_ns=100, finished_ns=300, wall_ns=200,
            before=[0]*16, after=[144000]+[0]*15,
            workers=[dict(cpu=cpu, observed_cpu=cpu, error=0, completed=48000,
                          cpu_ns=20, finished_ns=300) for cpu in cpus])

        def initialize(session, out, spec):
            # Substitute only module/device setup; retain BackendSession init.
            session.record = copy.deepcopy(spec)
            session.path = Path(out)/spec['name']
            session.workload_module = Path('/unused/spin_cacheline.ko')
            session.loaded_kd = session.loaded_source = False

        for arm in ('native', 'tclock', 'kdlock'):
            with self.subTest(arm=arm), patch.object(Session, '__init__', initialize):
                spec, = run.make_plan(Namespace(cachelines=[1], threads=[3],
                    repeats=1, iterations=17, backends=[arm],
                    pmu=True))
                spec.update(cpus=cpus, cpu_nodes=nodes)
                self.assertEqual((spec['warmup_policy'],
                                  spec['warmup_iterations_per_worker'],
                                  spec['warmup_pause_seconds']),
                                 ('all_workers', 48000, 0))
                session = BackendSession('/unused', spec)
                commands = []

                def command(args, log, **kwargs):
                    commands.append((args, log))
                    return json.dumps({'layout.json': {'lock_addr': 4096},
                                       'prepare.json': {}, 'warmup.json': warmup}.get(log, {}))

                session.counts = Mock(return_value=dict(active=0, values=[0]*16))
                session.faults = session.save = Mock()
                with patch.object(Session, 'run', side_effect=command), \
                        patch('session.time.sleep') as pause, \
                        patch('bench_session.validate_measurement',
                              wraps=run.runtime.validate_measurement) as validate:
                    if arm == 'native':
                        # Exercise the production 48,000-per-worker call and
                        # require separate preparation before worker warmup.
                        session.prepare()
                        labels = [label for _, label in commands]
                        self.assertLess(labels.index('prepare.json'), labels.index('warmup.json'))
                        preparation, = [args for args, label in commands if label == 'prepare.json']
                        self.assertEqual(preparation, [run.HERE/'client', '--prepare', '--cachelines', 1])
                        pause.assert_not_called()
                    else:
                        session.phase('warmup', 48000)
                args, = [args for args, label in commands if label == 'warmup.json']
                self.assertEqual(args[0], run.HERE/'client')  # No measured PMU wrapper.
                self.assertEqual(args[args.index('--cpus')+1], '2,7,11')
                self.assertEqual(args[args.index('--iterations')+1], 48000)
                actual, geometry, iterations = validate.call_args.args
                self.assertEqual((actual, iterations), (warmup, 48000))
                self.assertEqual((geometry['threads'], geometry['cpus'], geometry['cpu_nodes']),
                                 (3, cpus, nodes))
                self.assertNotIn('preparation_cpus', session.record)
                self.assertNotIn('measurement', session.record)
                self.assertNotIn('jit_before', session.record)

    def test_jit_measurement_starts_after_unmeasured_warmup(self):
        session = BackendSession.__new__(BackendSession)
        session.record = dict(arm='kdlock', threads=3, iterations=17,
                              hotlock_mode='adaptive', scenario='plain')
        session.loaded_kd = True
        session.save = Mock()
        session.mutex_wait_stats = Mock(side_effect=[
            dict(result_schedule_calls=10, result_wakes=7, gate_wait_calls=2),
            dict(result_schedule_calls=14, result_wakes=9, gate_wait_calls=3)])
        events, counts = [], iter((700, 705))  # 700 bodies already returned in warmup.

        def counter():
            events.append('counter')
            return str(next(counts))

        def publication():
            events.append('publication')
            return {'source': {'writers': 0}}

        def phase(label, iterations):
            self.assertEqual((label, iterations), ('measure', 17))
            self.assertEqual(session.record['jit_before'], 700)
            events.append(label)
            return dict(completed=51)

        session.publication, session.phase = publication, phase
        with patch.object(Path, 'read_text', side_effect=counter):
            session.measure()
        self.assertEqual(events, ['publication', 'counter', 'measure', 'counter', 'publication'])
        self.assertEqual(session.record['jit_bodies'], 5)
        self.assertEqual(session.record['jit_share'], 5/51)
        self.assertEqual(session.record['measurement']['completed'], 51)
        self.assertEqual(session.record['mutex_wait_delta'],
                         dict(result_schedule_calls=4, result_wakes=2, gate_wait_calls=1))

    def test_functional_report_has_no_performance_scores(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out/'plan.json').write_text(json.dumps([
                dict(name='plain', scenario='plain', functional=True,
                     spin_entry_ratio_limit=4),
                dict(name='missing', scenario='early', functional=True),
                dict(name='historical', scenario='plain', functional=True,
                     spin_contention_pct=37)]))
            (out/'plain').mkdir()
            (out/'plain/session.json').write_text(json.dumps(dict(
                execution_status='PASS', drained=True, jit_bodies=9,
                jit_acceptance='PASS', measurement=dict(completed=10, wall_ns=100))))
            run.report(out)
            rows = json.loads((out/'functional.json').read_text())
            self.assertEqual(rows[0]['completed'], 10)
            self.assertEqual(rows[0]['spin_entry_ratio_limit'], 4)
            self.assertEqual(rows[0]['spin_contention_pct'], 'unrecorded')
            self.assertEqual(rows[1]['status'], 'NOT_RUN')
            self.assertFalse(rows[1]['drained'])
            self.assertEqual(rows[2]['spin_contention_pct'], 37)
            self.assertEqual(rows[2]['spin_entry_ratio_limit'], 'unrecorded')
            self.assertFalse((out/'summary.csv').exists())
            self.assertFalse((out/'summary.json').exists())
            self.assertFalse(any('throughput' in key or 'ns_op' in key for row in rows for key in row))

    def test_disabled_control_rejects_any_jit(self):
        record = dict(arm='kdlock', threads=4, jit_bodies=0,
                      hotlock_mode='adaptive', spin_delegate='off')
        check_jit_evidence(record)
        self.assertEqual(record['jit_acceptance'], 'DISABLED_CONTROL')
        with self.assertRaisesRegex(run.Failure, 'disabled control executed JIT'):
            check_jit_evidence(dict(record, jit_bodies=1))

    def test_policy_no_jit_is_not_protocol_acceptance(self):
        record = dict(arm='kdlock', threads=4, jit_bodies=0, hotlock_mode='adaptive')
        check_jit_evidence(record)
        self.assertEqual(record['jit_acceptance'], 'NO_JIT')
        check_jit_evidence(record := dict(record, jit_bodies=1))
        self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_single_thread_native_completion_is_not_jit_acceptance(self):
        record = dict(arm='kdlock', threads=1, jit_bodies=0,
            hotlock_mode='adaptive', caller_shell='cold_clobber', scenario='plain')
        check_jit_evidence(record)
        self.assertEqual(record['jit_acceptance'], 'NO_JIT')

    def test_queue_depth_option_is_removed(self):
        argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                '--spin-hot-min-queue', '4']
        with patch.object(sys, 'argv', argv), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                run.main()
        self.assertEqual(result.exception.code, 2)

    def test_shell_selection_option_is_removed(self):
        # Old commands must fail explicitly rather than silently select a
        # different caller from the one recorded in their original evidence.
        for choice in ('on', 'off'):
            argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                    '--spin-cold-fastpath', choice]
            with self.subTest(choice=choice), patch.object(sys, 'argv', argv), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    run.main()
                self.assertEqual(result.exception.code, 2)

    def test_small_plain_native_completion_is_not_jit_acceptance(self):
        for threads in (2, 3):
            with self.subTest(threads=threads):
                record = dict(arm='kdlock', threads=threads, jit_bodies=0,
                    hotlock_mode='adaptive', caller_shell='cold_clobber', scenario='plain')
                check_jit_evidence(record)
                self.assertEqual(record['jit_acceptance'], 'NO_JIT_LOW_CONTENTION')
                check_jit_evidence(record := dict(record, jit_bodies=1))
                self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_nested_protocol_cases_still_require_jit(self):
        for threads in (2, 3, 4, 8, 20):
            for scenario in ('nested', 'early'):
                with self.subTest(threads=threads, scenario=scenario):
                    record = dict(arm='kdlock', threads=threads, jit_bodies=0,
                        hotlock_mode='adaptive', caller_shell='cold_clobber',
                        spin_entry_ratio_limit=0, scenario=scenario)
                    with self.assertRaisesRegex(run.Failure, 'no actual JIT'):
                        check_jit_evidence(record)
                    check_jit_evidence(record := dict(record, jit_bodies=1))
                    self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_admission_mode_option_is_removed(self):
        # Old commands must not silently select a different admission contract.
        for choice in ('observe', 'adaptive'):
            argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                    '--hotlock-mode', choice]
            with self.subTest(choice=choice), patch.object(sys, 'argv', argv), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    run.main()
            self.assertEqual(result.exception.code, 2)

    def test_high_contention_requires_jit(self):
        for threads in (20, 24, 28, 32, 36):
            record = dict(arm='kdlock', threads=threads, jit_bodies=0,
                hotlock_mode='adaptive', caller_shell='cold_clobber', scenario='plain')
            with self.assertRaisesRegex(run.Failure, 'no actual JIT'):
                check_jit_evidence(record)
            check_jit_evidence(record := dict(record, jit_bodies=1))
            self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_contended_functional_plain_requires_jit(self):
        # Adaptive native completion is a valid performance result, but it
        # cannot satisfy an explicitly requested functional JIT positive.
        for threads in (2, 3, 4, 8, 16, 20):
            record = dict(arm='kdlock', threads=threads, jit_bodies=0,
                          functional=True, scenario='plain')
            with self.subTest(threads=threads):
                with self.assertRaisesRegex(run.Failure, 'no actual JIT'):
                    check_jit_evidence(record)
                check_jit_evidence(record := dict(record, jit_bodies=1))
                self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_hash_layout_rejects_scheduling_enabled_module(self):
        layout = dict(workload='rcuht', buckets=1024, entries=4096,
                      key_range=8192, resched=0)
        hash_layout(layout)
        with self.assertRaisesRegex(run.Failure, 'hash payload configuration differs'):
            hash_layout(dict(layout, resched=1))

    def test_no_counter_quiescence_rejects_busy_or_old_provider(self):
        params = dict(target_lock=4096, komb_batch_size=1024, quiescent=1)
        tc_quiescent(params)
        for bad in (dict(params, quiescent=0), dict(params, delegated=0, completed=0)):
            with self.assertRaises(run.Failure):
                tc_quiescent(bad)

    def test_inline_audit_rejects_compiler_stack_prologue(self):
        # An extra compiler push invalidates the saved return-address offset
        # even though all six upstream register pushes still appear later.
        bad = '0000 <komb_context_switch>:\n 0: push %rbp\n 1: mov %rsp,%rbp\n'
        with self.assertRaisesRegex(ValueError, 'unexpected stack/register layout'):
            audit_context(bad)

    def test_hash_timed_matrix(self):
        plan = run.make_plan(Namespace(workload='rcuht', cachelines=None,
            threads=[1,2,3,4,5,6,7,8,12,16,20,24,28,32,36], repeats=3,
            iterations=100000, backends=['native', 'tclock', 'kdlock'],
            duration_ms=2000, collector_cpu=38))
        self.assertEqual(len(plan), 135)
        self.assertTrue(all(s['workload'] == 'rcuht' and s['cachelines'] == 0 and
                            s['measurement_mode'] == 'timed_peak' and
                            s['warmup_iterations_per_worker'] == 48000 for s in plan))

    def test_hash_matrix_and_outcome_oracle(self):
        plan = run.make_plan(Namespace(workload='rcuht', cachelines=None,
            threads=[1, 4, 8, 16, 20], repeats=2, iterations=100000,
            backends=['native', 'tclock', 'kdlock']))
        self.assertEqual(len(plan), 30)
        self.assertTrue(all(s['workload'] == 'rcuht' and s['cachelines'] == 0 for s in plan))
        spec = dict(workload='rcuht', cachelines=0, threads=1, cpus=[0])
        measurement = dict(schema=1, complete=True, data_ok=True, workload='rcuht',
            hash_integrity_ok=True, cachelines=0, threads=1, iterations=10,
            completed=10, worker_cpu_ns=100, started_ns=100, finished_ns=300,
            wall_ns=200, before=[3, 1, 1, 1] + [0]*12,
            after=[13, 4, 3, 6] + [0]*12,
            workers=[dict(cpu=0, observed_cpu=0, error=0, completed=10,
                          cpu_ns=100, finished_ns=300)])
        run.runtime.validate_measurement(measurement, spec, 10)
        # Lost/doubled outcomes and failed structure checks cannot be OK samples.
        for mutation in ('lost_outcome', 'extra_operation', 'bad_structure', 'wrong_payload'):
            broken = copy.deepcopy(measurement)
            if mutation == 'lost_outcome': broken['after'][1] -= 1
            if mutation == 'extra_operation': broken['after'][0] += 1
            if mutation == 'bad_structure': broken['hash_integrity_ok'] = False
            if mutation == 'wrong_payload': broken['workload'] = 'cacheline'
            with self.assertRaises(run.Failure):
                run.runtime.validate_measurement(broken, spec, 10)

    def test_cli_defaults_to_three_rounds(self):
        # Performance defaults to repeated measurements for both payloads;
        # explicit one-round performance and functional runs remain available.
        for extra, sessions, repeats in (
                ([], 45, 3), (['--workload', 'rcuht'], 45, 3),
                (['--repeats', '1'], 15, 1),
                (['--functional', '--backends', 'kdlock', '--repeats', '1'], 5, 1)):
            with self.subTest(args=extra):
                output = io.StringIO()
                argv = ['run.py', '--output', '/tmp/unused', '--dry-run', *extra]
                with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(output):
                    self.assertEqual(run.main(), 0)
                plan = json.loads(output.getvalue())
                self.assertEqual(len(plan), sessions)
                self.assertEqual(len({s['name'] for s in plan}), sessions)
                self.assertEqual({s['cachelines'] for s in plan},
                                 {0} if 'rcuht' in extra else {1})
                self.assertEqual({s['repeat'] for s in plan}, set(range(repeats)))
                self.assertEqual({s['hotlock_mode'] for s in plan if s['arm'] == 'kdlock'},
                                 {'adaptive'})

    def test_functional_mode_requires_explicit_single_round(self):
        argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                '--functional', '--backends', 'kdlock']
        with patch.object(sys, 'argv', argv):
            with self.assertRaisesRegex(run.Failure, 'functional mode requires'):
                run.main()

    def test_cli_small_and_numa_thread_matrix(self):
        # The 64-worker point explicitly shares collector 63; smaller cohorts do not.
        output = io.StringIO()
        argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                '--cachelines', '1', '--duration-ms', '2000', '--collector-cpu', '63',
                '--cpus', '0-63', '--share-collector',
                '--threads', '1', '2', '3', '4', '5', '6', '7', '8',
                '12', '16', '20', '24', '28', '32', '36',
                '40', '44', '48', '52', '56', '60', '64']
        with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(output):
            self.assertEqual(run.main(), 0)
        plan = json.loads(output.getvalue())
        self.assertEqual(len(plan), 198)
        self.assertEqual(len({s['name'] for s in plan}), 198)
        self.assertEqual({s['threads'] for s in plan},
                         set(range(1, 9)) | set(range(12, 65, 4)))
        self.assertEqual({s['repeat'] for s in plan}, {0, 1, 2})
        for spec in plan:
            self.assertEqual(spec['cpus'], list(range(spec['threads'])))
            self.assertEqual(spec['collector_shared'], spec['threads'] == 64)
            self.assertEqual(spec['collector_cpu'] in spec['cpus'], spec['collector_shared'])
            self.assertEqual(spec['cpu_heat_policy'],
                             'mcs_reset1024_shift10_lock512_head6' if spec['arm'] == 'kdlock' else 'not_applicable')
            self.assertEqual(spec['spin_entry_ratio_limit'],
                             run.DEFAULT_SPIN_ENTRY_RATIO_LIMIT if spec['arm'] == 'kdlock' else None)
            self.assertNotIn('spin_contention_pct', spec)
            self.assertNotIn('spin_hot_min_queue', spec)
            self.assertNotIn('spin_cold_fastpath', spec)

    def test_contention_cli_preserves_explicit_threshold_and_zero_bypass(self):
        # A diagnostic zero must survive parsing;
        # non-KD baselines have no contention-policy setting.
        for threshold in (0, 2, 4, 1 << 31):
            with self.subTest(threshold=threshold):
                output = io.StringIO()
                argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                        '--cachelines', '1', '--threads', '4', '--repeats', '1',
                        '--spin-entry-ratio-limit', str(threshold)]
                with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(output):
                    self.assertEqual(run.main(), 0)
                plan = json.loads(output.getvalue())
                self.assertEqual(len(plan), 3)
                for spec in plan:
                    self.assertEqual(spec['spin_entry_ratio_limit'],
                                     threshold if spec['arm'] == 'kdlock' else None)

    def test_contention_threshold_rejects_out_of_range_and_non_integer(self):
        for threshold in ('-1', '1', '3', '4294967296', '2.5'):
            with self.subTest(threshold=threshold):
                argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                        '--spin-entry-ratio-limit', threshold]
                with patch.object(sys, 'argv', argv), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as result:
                        run.main()
                self.assertEqual(result.exception.code, 2)
        for threshold in (-1, 1, 3, 1 << 32):
            with self.subTest(plan_threshold=threshold):
                with self.assertRaisesRegex(run.Failure, 'invalid spin entry ratio limit'):
                    run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=1,
                        iterations=100, backends=['kdlock'], spin_entry_ratio_limit=threshold))

    def test_percentage_option_is_removed(self):
        # The new inverse ratio must not silently reinterpret an old percent.
        argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                '--spin-contention-pct', '100']
        with patch.object(sys, 'argv', argv), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                run.main()
        self.assertEqual(result.exception.code, 2)

    def test_empty_summary_has_no_winner(self):
        plan = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=2,
            iterations=100, backends=['native', 'tclock', 'kdlock']))
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plan)
            run.report(out)
            for row in json.loads((out/'summary.json').read_text()):
                self.assertEqual(row['valid'], 0)
                for key in ('best_session', 'best_throughput_ops_s',
                            'best_amortized_ns_op', 'throughput_over_linux',
                            'min_throughput_ops_s', 'median_throughput_ops_s',
                            'max_throughput_ops_s', 'throughput_spread_pct'):
                    self.assertIsNone(row[key])

    def test_matrix_and_alternating_order(self):
        plan = run.make_plan(Namespace(cachelines=[1, 16], threads=[1, 4, 8, 16, 20],
            repeats=3, iterations=100000, backends=['native', 'tclock', 'kdlock']))
        self.assertEqual(len(plan), 90)
        self.assertEqual([(s['arm'], s['hotlock_mode']) for s in plan[:9]],
                         [('native', 'not_applicable'), ('tclock', 'not_applicable'),
                          ('kdlock', 'adaptive'), ('kdlock', 'adaptive'),
                          ('tclock', 'not_applicable'), ('native', 'not_applicable'),
                          ('native', 'not_applicable'), ('tclock', 'not_applicable'),
                          ('kdlock', 'adaptive')])
        self.assertTrue(all(s['api_mode'] == 'direct' for s in plan))

    def test_summary_excludes_bad_and_undrained_samples(self):
        plan = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=3,
            iterations=100, backends=['native', 'tclock', 'kdlock']))
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plan)
            for spec in plan:
                folder = out/spec['name']; folder.mkdir()
                # Vary rates between rounds; reject the fastest corrupt/undrained rows.
                bad = spec['repeat'] == 2 and spec['arm'] != 'native'
                rate = {'native': 1, 'tclock': 2, 'kdlock': 4}[spec['arm']] * (spec['repeat'] + 1)
                record = dict(spec, execution_status='OK', drained=not (bad and spec['arm'] == 'kdlock'),
                    measurement=dict(completed=400, wall_ns=1 if bad else 400000/rate,
                                     data_ok=not (bad and spec['arm'] == 'tclock'), complete=True))
                run.write_json(folder/'session.json', record)
            run.report(out)
            rows = {r['arm']: r for r in json.loads((out/'summary.json').read_text())}
            for arm, rate, repeat in [('native', 3, 2), ('tclock', 4, 1), ('kdlock', 8, 1)]:
                self.assertEqual(rows[arm]['throughput_over_linux'], rate / 3)
                self.assertEqual(rows[arm]['valid'], 3 if arm == 'native' else 2)
                self.assertEqual(rows[arm]['best_throughput_ops_s'], rate * 1e6)
                self.assertAlmostEqual(rows[arm]['best_amortized_ns_op'], 1000 / rate)
                winner = next(s['name'] for s in plan if s['arm'] == arm and s['repeat'] == repeat)
                self.assertEqual(rows[arm]['best_session'], winner)
                self.assertEqual(rows[arm]['comparison_policy'], 'best_valid_throughput')
                minimum, median = {'native': (1, 2), 'tclock': (2, 3),
                                   'kdlock': (4, 6)}[arm]
                self.assertEqual(rows[arm]['sessions'], 3)
                self.assertEqual(rows[arm]['min_throughput_ops_s'], minimum * 1e6)
                self.assertEqual(rows[arm]['median_throughput_ops_s'], median * 1e6)
                self.assertEqual(rows[arm]['max_throughput_ops_s'], rate * 1e6)
                self.assertAlmostEqual(rows[arm]['throughput_spread_pct'],
                                       (rate - minimum) / median * 100)
            self.assertEqual(len(json.loads((out/'records.json').read_text())), 9)

    def test_summary_preserves_historical_admission_identity(self):
        # Reporting old frozen records must not merge their admission modes.
        # The live planner below creates adaptive sessions only.
        plan = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=2,
            iterations=100, backends=['native', 'tclock', 'kdlock']))
        plan += [dict(spec, name=spec['name'].replace('-adaptive', '-observe'),
                      hotlock_mode='observe') for spec in plan if spec['arm'] == 'kdlock']
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plan)
            for spec in plan:
                folder = out/spec['name']; folder.mkdir()
                mode = spec['hotlock_mode']
                rate = {'not_applicable': 1, 'observe': 2, 'adaptive': 4}[mode]
                bad = mode == 'adaptive' and spec['repeat'] == 1
                run.write_json(folder/'session.json', dict(spec,
                    execution_status='OK', drained=not bad,
                    measurement=dict(completed=400, wall_ns=1 if bad else 400000/rate,
                                     data_ok=True, complete=True)))
            run.report(out)
            rows = {(r['arm'], r['hotlock_mode']): r
                    for r in json.loads((out/'summary.json').read_text())}
            self.assertEqual(len(rows), 4)
            for mode, rate, count in [('observe', 2, 2), ('adaptive', 4, 1)]:
                row = rows['kdlock', mode]
                self.assertEqual(row['sessions'], 2)
                self.assertEqual(row['valid'], count)
                self.assertEqual(row['best_throughput_ops_s'], rate * 1e6)
                self.assertEqual(row['throughput_over_linux'], rate)
                self.assertTrue(row['best_session'].endswith('-' + mode))
            self.assertEqual(rows['native', 'not_applicable']['sessions'], 2)
            self.assertEqual(rows['tclock', 'not_applicable']['sessions'], 2)

    def test_default_heat_caller_uses_one_adaptive_session(self):
        plan = run.make_plan(Namespace(cachelines=[1], threads=[1], repeats=1,
            iterations=100, backends=['native', 'tclock', 'kdlock']))
        self.assertEqual(len(plan), 3)
        self.assertEqual(len({s['name'] for s in plan}), 3)
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plan)
            for spec in plan:
                folder = out/spec['name']; folder.mkdir()
                run.write_json(folder/'session.json', dict(spec,
                    execution_status='OK', drained=True,
                    measurement=dict(completed=100, wall_ns=100000,
                                     data_ok=True, complete=True)))
                if spec['arm'] == 'kdlock':
                    self.assertEqual(spec['caller_abi'], 'clobber')
                    self.assertEqual(spec['caller_shell'], 'cold_clobber')
                    self.assertEqual(spec['cookie_storage'], 'percpu_direct_gate')
                    self.assertEqual(spec['delegation_batch_limit'], 1024)
                    self.assertNotIn('spin_cold_fastpath', spec)
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            self.assertEqual(len(rows), 3)
            self.assertEqual({r['hotlock_mode'] for r in rows if r['arm'] == 'kdlock'},
                             {'adaptive'})
            self.assertTrue(all('spin_cold_fastpath' not in r for r in rows))
            self.assertTrue(all(r['sessions'] == r['valid'] == 1 for r in rows))
            self.assertTrue(all(r['min_throughput_ops_s'] == r['median_throughput_ops_s'] ==
                                r['max_throughput_ops_s'] == r['best_throughput_ops_s']
                                for r in rows))
            self.assertTrue(all(r['throughput_spread_pct'] is None for r in rows))
            self.assertEqual({r['cookie_storage'] for r in rows}, {'percpu_direct_gate', 'not_applicable'})

    def test_summary_keeps_gate_storage_separate(self):
        # An old indirect-gate archive must not supply the winner for the new
        # direct scalar even when admission and workload settings match.
        base = run.make_plan(Namespace(cachelines=[1], threads=[1], repeats=1,
            iterations=100, backends=['kdlock']))[0]
        plans = [dict(base, name=base['name']+'-'+storage, cookie_storage=storage)
                 for storage in ('percpu_rate_hot', 'percpu_direct_gate')]
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plans)
            for index, spec in enumerate(plans):
                folder = out/spec['name']; folder.mkdir()
                run.write_json(folder/'session.json', dict(spec,
                    execution_status='OK', drained=True,
                    measurement=dict(completed=100, wall_ns=100000*(index+1),
                                     data_ok=True, complete=True)))
            run.report(out)
            rows = {r['cookie_storage']: r
                    for r in json.loads((out/'summary.json').read_text())}
            self.assertEqual(set(rows), {'percpu_rate_hot', 'percpu_direct_gate'})
            for index, spec in enumerate(plans):
                row = rows[spec['cookie_storage']]
                self.assertEqual(row['valid'], 1)
                self.assertEqual(row['best_session'], spec['name'])
                self.assertEqual(row['best_throughput_ops_s'], 1e6/(index+1))

    def test_summary_keeps_heat_policies_separate(self):
        base = run.make_plan(Namespace(cachelines=[1], threads=[2], repeats=1,
            iterations=100, backends=['kdlock']))[0]
        # Keep each resettable cadence separate from percentage samplers and
        # older native-head policies, even when their ratio cutoffs match.
        plans = [dict(base, name=base['name']+'-'+policy, cpu_heat_policy=policy)
                 for policy in ('mcs_reset1024_shift10_lock512_head6', 'mcs_reset_shift9_head6', 'mcs_entry_ratio512_head6', 'mcs_entry_ratio512_head5', 'mcs_entry_ratio512_simple', 'mcs_entry_ratio512_batch128', 'mcs_entry_ratio512_confirm2', 'mcs_entry_ratio512', 'mcs_entry_ratio',
                                'mcs_entry', 'historical_queue_depth')]
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plans)
            for spec in plans:
                folder = out/spec['name']; folder.mkdir()
                run.write_json(folder/'session.json', dict(spec,
                    execution_status='OK', drained=True,
                    jit_bodies=int(spec['cpu_heat_policy'] == 'mcs_reset1024_shift10_lock512_head6'),
                    measurement=dict(completed=200, wall_ns=100000,
                                     data_ok=True, complete=True)))
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            self.assertEqual(len(rows), 11)
            self.assertEqual({r['cpu_heat_policy'] for r in rows},
                             {'mcs_reset1024_shift10_lock512_head6', 'mcs_reset_shift9_head6', 'mcs_entry_ratio512_head6', 'mcs_entry_ratio512_head5', 'mcs_entry_ratio512_simple', 'mcs_entry_ratio512_batch128', 'mcs_entry_ratio512_confirm2', 'mcs_entry_ratio512', 'mcs_entry_ratio',
                              'mcs_entry', 'historical_queue_depth'})
            self.assertEqual(sum(r['actual_jit_sessions'] for r in rows), 1)

    def test_summary_keeps_contention_thresholds_separate(self):
        # Historical percentages and current limits each remain independent
        # tuning inputs, including zero's bypass in either unit.
        plans = []
        rates = {('spin_entry_ratio_limit', 0): 1,
                 ('spin_entry_ratio_limit', 2): 2,
                 ('spin_entry_ratio_limit', 4): 4,
                 ('spin_contention_pct', 0): 8,
                 ('spin_contention_pct', 37): 16,
                 ('spin_contention_pct', 100): 32}
        for field, threshold in rates:
            candidate = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=2,
                iterations=100, backends=['kdlock']))
            for spec in candidate:
                if field == 'spin_contention_pct':
                    del spec['spin_entry_ratio_limit']
                    spec['cpu_heat_policy'] = 'mcs_entry_ratio512_head6'
                spec[field] = threshold
                spec['name'] += f'-{field}-{threshold}'
                plans.append(spec)
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plans)
            for spec in plans:
                folder = out/spec['name']; folder.mkdir()
                field = ('spin_contention_pct' if 'spin_contention_pct' in spec
                         else 'spin_entry_ratio_limit')
                rate = rates[field, spec[field]] * (spec['repeat'] + 1)
                run.write_json(folder/'session.json', dict(spec,
                    execution_status='OK', drained=True, jit_bodies=1,
                    measurement=dict(completed=400, wall_ns=400000/rate,
                                     data_ok=True, complete=True)))
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            self.assertEqual(len(rows), len(rates))
            self.assertEqual({row['hotlock_mode'] for row in rows}, {'adaptive'})
            observed = set()
            for row in rows:
                field = ('spin_contention_pct' if row['spin_contention_pct'] != 'unrecorded'
                         else 'spin_entry_ratio_limit')
                threshold = row[field]
                observed.add((field, threshold))
                self.assertEqual(row['sessions'], 2)
                self.assertEqual(row['valid'], 2)
                self.assertEqual(row['best_throughput_ops_s'], rates[field, threshold] * 2e6)
                self.assertEqual(row['best_amortized_ns_op'], 500 / rates[field, threshold])
                self.assertTrue(row['best_session'].endswith(f'-{field}-{threshold}'))
            self.assertEqual(observed, set(rates))

    def test_provider_load_has_no_admission_mode_parameter(self):
        session = BackendSession.__new__(BackendSession)
        session.record = dict(arm='kdlock', hotlock_mode='adaptive',
                              mutex_entry_ratio_limit=256, mutex_routing='adaptive',
                              spin_entry_ratio_limit=4, spin_delegate='on', spin_prefetch=0)
        commands = []

        def command(args, log):
            commands.append((args, log))
            if log == 'load-kdlock.log':
                raise RuntimeError('stop after provider command')

        session.run = command
        with self.assertRaisesRegex(RuntimeError, 'stop after provider command'):
            session.prepare()
        args, = [args for args, log in commands if log == 'load-kdlock.log']
        self.assertFalse(any(str(arg).startswith('hotlock_mode=') for arg in args))
        self.assertFalse(any(str(arg).startswith('spin_contention_pct=') for arg in args))
        self.assertIn('spin_entry_ratio_limit=4', args)
        self.assertIn('spin_delegate=1', args)
        self.assertIn('spin_prefetch=0', args)
        self.assertIn('mutex_entry_ratio_limit=256', args)
        self.assertIn('mutex_native_route=0', args)


if __name__ == '__main__':
    unittest.main()
