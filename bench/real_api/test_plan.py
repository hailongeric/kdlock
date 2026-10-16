"""Guest-only placement and supported-backend checks; no live modules loaded."""
from argparse import Namespace
import unittest

import run


def arguments(**changes):
    args = dict(kinds=['pipebytes'], queries=['query'], entries=[16],
        threads=[1, 64], cpus=','.join(map(str, [*range(32), *range(33, 65)])),
        collector_cpu=65, repeats=3, backends=['stock', 'native', 'tclock', 'kdlock'],
        value_size=64,
        duration_ms=2000, warmup=48000, warmup_ms=1000, helper_waves=4)
    return Namespace(**(args | changes))


class PlanTests(unittest.TestCase):
    def test_sixty_four_workers_are_distinct_from_collector(self):
        plan = run.make_plan(arguments())
        self.assertEqual(len(plan), 24)
        self.assertEqual(len({s['name'] for s in plan}), len(plan))
        for row in plan:
            self.assertEqual(len(row['cpus']), row['threads'])
            self.assertNotIn(32, row['cpus'])
            self.assertNotIn(65, row['cpus'])
        self.assertEqual(plan[-1]['cpus'], [*range(32), *range(33, 65)])

    def test_private_mutex_adapter_keeps_each_backend_once_per_round(self):
        plan = run.make_plan(arguments(threads=[64]))
        for repeat in range(3):
            rows = [r for r in plan if r['repeat'] == repeat]
            kd = [r for r in rows if r['arm'] == 'kdlock']
            self.assertEqual(len(kd), 1)
            self.assertEqual((kd[0]['registry_lock_kind'], kd[0]['entry_abi'],
                              kd[0]['caller_abi']), (3, 4, 'c'))
            self.assertEqual(kd[0]['mutex_implementation'], 'owned-v1')
            self.assertEqual(kd[0]['owned_mutex_reuse_spins'], 32)
            for arm in ('stock', 'native', 'tclock', 'kdlock'):
                self.assertEqual(sum(r['arm'] == arm for r in rows), 1)

    def test_invalid_affinity_cannot_start_a_run(self):
        for changes in (dict(threads=[65]), dict(collector_cpu=64),
                        dict(cpus='0,0'), dict(cpus='0,1'),
                        dict(threads=[0]), dict(threads=[1, 1])):
            with self.subTest(changes=changes), self.assertRaises(run.Failure):
                run.make_plan(arguments(**changes))

    def test_kd_mutex_covers_all_pipe_and_seek_variants(self):
        threads = [*range(1, 9), *range(12, 61, 4)]
        for kind, queries, entries in (('pipebytes', ['query'], [16, 128]),
                                       ('pipecap', ['query'], [16]),
                                       ('seek', ['set', 'end'], [16])):
            with self.subTest(kind=kind):
                plan = run.make_plan(arguments(kinds=[kind], queries=queries, entries=entries,
                    backends=['kdlock'], threads=threads, cpus=','.join(map(str, range(60))),
                    collector_cpu=63))
                self.assertEqual(len(plan), len(queries)*len(entries)*len(threads)*3)
                self.assertEqual({r['threads'] for r in plan}, set(threads))
                self.assertTrue(all(r['entry_abi'] == 4 and r['registry_lock_kind'] == 3
                                    and r['mutex_wait_mode'] == 'blocking' for r in plan))

    def test_mixed_plan_retains_kd_for_supported_spin_payloads(self):
        plan = run.make_plan(arguments(kinds=['pipecap', 'ofd'], threads=[1]))
        kd = [r for r in plan if r['arm'] == 'kdlock']
        self.assertEqual([r['kind'] for r in kd], ['pipecap'] * 3 + ['ofd'] * 3)
        self.assertTrue(all(r['registry_lock_kind'] == 1 and r['entry_abi'] == 1
                            and r['caller_abi'] == 'clobber' for r in kd if r['kind'] == 'ofd'))
        self.assertEqual({r['kind'] for r in plan}, {'pipecap', 'ofd'})

    def test_owned_mutex_parameters_and_imports_reject_wrong_protocol(self):
        spec = run.make_plan(arguments(backends=['kdlock']))[0]
        params = {k: str(v) for k, v in run.owned_mutex_parameters(spec).items()}
        params['owned_mutex_protocol'] = 'linux_local_first_v1'
        run.check_owned_mutex_parameters(params, spec)
        for key in run.owned_mutex_parameters(spec):
            with self.subTest(key=key):
                wrong = dict(params); del wrong[key]
                with self.assertRaises(run.Failure):
                    run.check_owned_mutex_parameters(wrong, spec)
                wrong[key] = str(int(params[key])+1)
                with self.assertRaises(run.Failure):
                    run.check_owned_mutex_parameters(wrong, spec)
        required = {'kd_owned_mutex_prepare', 'kd_mutex_init', 'kd_owned_mutex_is_idle',
                    'kd_owned_mutex_outer_lock_cabi_v2', 'kd_owned_mutex_outer_unlock_cabi_v2'}
        run.audit_owned_mutex_imports(' '.join(required))
        for name in required:
            with self.assertRaises(run.Failure):
                run.audit_owned_mutex_imports(' '.join(required - {name}))
        for name in ('mutex_lock', 'mutex_unlock', 'kd_owned_mutex_outer_contended_clobber_v1'):
            with self.assertRaises(run.Failure):
                run.audit_owned_mutex_imports(' '.join(required | {name}))


if __name__ == '__main__':
    unittest.main()
