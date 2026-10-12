"""Guest-only placement and paired-policy checks; no live modules loaded."""
from argparse import Namespace
import unittest

import run


def arguments(**changes):
    args = dict(kinds=['pipebytes'], queries=['query'], entries=[16],
        threads=[1, 64], cpus=','.join(map(str, [*range(32), *range(33, 65)])),
        collector_cpu=65, repeats=3, backends=['stock', 'native', 'tclock', 'kdlock'],
        mutex_wait_mode='both', mutex_spin_limit=4096, value_size=64,
        duration_ms=2000, warmup=48000, warmup_ms=1000, helper_waves=4)
    return Namespace(**(args | changes))


class PlanTests(unittest.TestCase):
    def test_sixty_four_workers_are_distinct_from_collector(self):
        plan = run.make_plan(arguments())
        self.assertEqual(len(plan), 30)
        self.assertEqual(len({s['name'] for s in plan}), len(plan))
        for row in plan:
            self.assertEqual(len(row['cpus']), row['threads'])
            self.assertNotIn(32, row['cpus'])
            self.assertNotIn(65, row['cpus'])
        self.assertEqual(plan[-1]['cpus'], [*range(32), *range(33, 65)])

    def test_pair_order_alternates_and_baselines_are_not_duplicated(self):
        plan = run.make_plan(arguments(threads=[64]))
        for repeat in range(3):
            rows = [r for r in plan if r['repeat'] == repeat]
            kd = [r for r in rows if r['arm'] == 'kdlock']
            self.assertEqual([r['mutex_wait_mode'] for r in kd],
                             ['blocking', 'spin'] if repeat % 2 else ['spin', 'blocking'])
            self.assertEqual(rows.index(kd[1]), rows.index(kd[0]) + 1)
            for arm in ('stock', 'native', 'tclock'):
                self.assertEqual(sum(r['arm'] == arm for r in rows), 1)

    def test_invalid_affinity_cannot_start_a_run(self):
        for changes in (dict(threads=[65]), dict(collector_cpu=64),
                        dict(cpus='0,0'), dict(cpus='0,1'),
                        dict(threads=[0]), dict(threads=[1, 1])):
            with self.subTest(changes=changes), self.assertRaises(run.Failure):
                run.make_plan(arguments(**changes))

    def test_single_policy_preserves_existing_session_names(self):
        plan = run.make_plan(arguments(threads=[1], mutex_wait_mode='blocking'))
        self.assertEqual(len(plan), 12)
        kd = [r for r in plan if r['arm'] == 'kdlock']
        self.assertEqual([r['name'] for r in kd],
                         [f'pipebytes-query-n16-t01-r{i}-kdlock' for i in range(3)])
        self.assertEqual({r['mutex_wait_mode'] for r in kd}, {'blocking'})


if __name__ == '__main__':
    unittest.main()
