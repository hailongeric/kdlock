"""Guest-only planning/publication checks; no live modules loaded."""
from argparse import Namespace
import unittest
from unittest.mock import Mock

import run


def arguments(**changes):
    args = dict(kinds=['pipebytes'], queries=['query'], entries=[16],
        threads=[1, 60], cpus=','.join(map(str, range(63))), collector_cpu=63,
        repeats=3, backends=['stock', 'native', 'tclock', 'kdlock'], value_size=64,
        duration_ms=2000, warmup=48000, warmup_ms=1000, helper_waves=4)
    return Namespace(**(args | changes))


class PlanTests(unittest.TestCase):
    def test_current_mutex_abi_and_dedicated_collector(self):
        plan = run.make_plan(arguments())
        self.assertEqual(len(plan), 24)
        self.assertEqual(len({r['name'] for r in plan}), len(plan))
        for row in plan:
            self.assertEqual(len(row['cpus']), row['threads'])
            self.assertNotIn(row['collector_cpu'], row['cpus'])
            if row['arm'] == 'kdlock':
                self.assertEqual((row['entry_abi'], row['caller_abi'], row['mutex_implementation']),
                                 (2, 'clobber', 'kd-only-legacy'))

    def test_duplicate_dimensions_and_invalid_affinity_cannot_overwrite_sessions(self):
        for changes in (dict(threads=[64]), dict(collector_cpu=59), dict(cpus='0,0'),
                        dict(threads=[0]), dict(threads=[1, 1]), dict(threads=[]),
                        dict(entries=[16, 16]), dict(kinds=['pipebytes', 'pipebytes']),
                        dict(queries=['query', 'query']), dict(backends=['kdlock', 'kdlock'])):
            with self.subTest(changes=changes), self.assertRaises(run.Failure):
                run.make_plan(arguments(**changes))

    def test_all_supported_pipe_and_seek_cases_keep_kd(self):
        threads = [*range(1, 9), *range(12, 61, 4)]
        for kind, queries, entries in (('pipebytes', ['query'], [16, 128]),
                                      ('pipecap', ['query'], [16]),
                                      ('seek', ['set', 'end'], [16])):
            plan = run.make_plan(arguments(kinds=[kind], queries=queries, entries=entries,
                                          backends=['kdlock'], threads=threads))
            self.assertEqual(len(plan), len(queries)*len(entries)*len(threads)*3)
            self.assertTrue(all(r['entry_abi'] == 2 for r in plan))

    def test_live_translator_writer_blocks_measurement(self):
        session = run.SyscallSession.__new__(run.SyscallSession)
        session.record = {}
        session.loaded_kd = True
        session.publication = Mock(return_value=dict(source=dict(writers=1)))
        session.tell = Mock()
        with self.assertRaisesRegex(run.Failure, 'translator writer remains'):
            session.measure()
        session.tell.assert_not_called()


if __name__ == '__main__':
    unittest.main()
