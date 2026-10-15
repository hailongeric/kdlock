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
        self.assertEqual(len(plan), 18)
        self.assertEqual(len({s['name'] for s in plan}), len(plan))
        for row in plan:
            self.assertEqual(len(row['cpus']), row['threads'])
            self.assertNotIn(32, row['cpus'])
            self.assertNotIn(65, row['cpus'])
        self.assertEqual(plan[-1]['cpus'], [*range(32), *range(33, 65)])

    def test_kernel_mutex_excludes_kd_and_keeps_baselines_once_per_round(self):
        plan = run.make_plan(arguments(threads=[64]))
        for repeat in range(3):
            rows = [r for r in plan if r['repeat'] == repeat]
            kd = [r for r in rows if r['arm'] == 'kdlock']
            self.assertEqual(kd, [])
            for arm in ('stock', 'native', 'tclock'):
                self.assertEqual(sum(r['arm'] == arm for r in rows), 1)

    def test_invalid_affinity_cannot_start_a_run(self):
        for changes in (dict(threads=[65]), dict(collector_cpu=64),
                        dict(cpus='0,0'), dict(cpus='0,1'),
                        dict(threads=[0]), dict(threads=[1, 1])):
            with self.subTest(changes=changes), self.assertRaises(run.Failure):
                run.make_plan(arguments(**changes))

    def test_kd_only_kernel_mutex_plan_is_rejected(self):
        with self.assertRaises(run.Failure):
            run.make_plan(arguments(backends=['kdlock']))

    def test_mixed_plan_retains_kd_for_supported_spin_payloads(self):
        plan = run.make_plan(arguments(kinds=['pipecap', 'ofd'], threads=[1]))
        kd = [r for r in plan if r['arm'] == 'kdlock']
        self.assertEqual([r['kind'] for r in kd], ['ofd'] * 3)
        self.assertEqual({r['kind'] for r in plan}, {'pipecap', 'ofd'})


if __name__ == '__main__':
    unittest.main()
