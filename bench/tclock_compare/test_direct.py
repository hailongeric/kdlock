"""Direct comparison matrix and result exclusion; no modules are loaded."""
from argparse import Namespace
import copy
import json
from pathlib import Path
import tempfile
import unittest

import run
from session import hash_layout, tc_quiescent, check_jit_evidence
from context_audit import audit as audit_context


class DirectTests(unittest.TestCase):
    def test_disabled_control_rejects_any_jit(self):
        record = dict(arm='kdlock', threads=4, jit_bodies=0,
                      hotlock_mode='observe', spin_delegate='off')
        check_jit_evidence(record)
        self.assertEqual(record['jit_acceptance'], 'DISABLED_CONTROL')
        with self.assertRaisesRegex(run.Failure, 'disabled control executed JIT'):
            check_jit_evidence(dict(record, jit_bodies=1))

    def test_policy_no_jit_is_not_protocol_acceptance(self):
        record = dict(arm='kdlock', threads=4, jit_bodies=0, hotlock_mode='observe')
        with self.assertRaisesRegex(run.Failure, 'no actual JIT'):
            check_jit_evidence(record)
        check_jit_evidence(record := dict(record, hotlock_mode='adaptive'))
        self.assertEqual(record['jit_acceptance'], 'NO_JIT')
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

    def test_hash_matrix_and_outcome_oracle(self):
        plan = run.make_plan(Namespace(workload='rcuht', cachelines=None,
            threads=[1, 4, 8, 16, 20], repeats=5, iterations=100000,
            backends=['native', 'tclock', 'kdlock']))
        self.assertEqual(len(plan), 75)
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

    def test_matrix_and_alternating_order(self):
        plan = run.make_plan(Namespace(cachelines=[1, 16], threads=[1, 4, 8, 16, 20],
            repeats=5, iterations=100000, backends=['native', 'tclock', 'kdlock']))
        self.assertEqual(len(plan), 150)
        self.assertEqual([s['arm'] for s in plan[:6]],
                         ['native', 'tclock', 'kdlock', 'kdlock', 'tclock', 'native'])
        self.assertTrue(all(s['api_mode'] == 'direct' for s in plan))

    def test_summary_excludes_bad_and_undrained_samples(self):
        plan = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=3,
            iterations=100, backends=['native', 'tclock', 'kdlock']))
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plan)
            for spec in plan:
                folder = out/spec['name']; folder.mkdir()
                # Valid rates are 1, 2 and 4 Mops/s. Reject tempting fast rows.
                bad = spec['repeat'] == 2 and spec['arm'] != 'native'
                rate = {'native': 1, 'tclock': 2, 'kdlock': 4}[spec['arm']]
                record = dict(spec, execution_status='OK', drained=not bad,
                    measurement=dict(completed=400, wall_ns=1 if bad else 400000/rate,
                                     data_ok=True, complete=True))
                run.write_json(folder/'session.json', record)
            run.report(out)
            rows = {r['arm']: r for r in json.loads((out/'summary.json').read_text())}
            for arm, ratio in [('native', 1), ('tclock', 2), ('kdlock', 4)]:
                self.assertEqual(rows[arm]['throughput_over_linux'], ratio)
                self.assertEqual(rows[arm]['valid'], 3 if arm == 'native' else 2)
                self.assertNotIn('median_delegation_share', rows[arm])


if __name__ == '__main__':
    unittest.main()
