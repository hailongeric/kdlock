"""Guest-only planning/publication checks; no live modules loaded."""
from argparse import Namespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import run
from evidence import helper_ready, jit_evidence


def arguments(**changes):
    args = dict(kinds=['pipebytes'], queries=['query'], entries=[16],
        threads=[1, 60], cpus=','.join(map(str, range(63))), collector_cpu=63,
        repeats=3, backends=['stock', 'native', 'tclock', 'kdlock'], value_size=64,
        duration_ms=2000, warmup=48000, warmup_ms=1000, helper_waves=4,
        helper_workers=8, require_jit=False, mutex_lock_offset=None)
    return Namespace(**(args | changes))


class PlanTests(unittest.TestCase):
    def test_mutex_placement_diagnostics_cannot_enter_ordinary_comparisons(self):
        for offset in (0, 32, 40, 56):
            plan = run.make_plan(arguments(backends=['kdlock'], mutex_lock_offset=offset))
            self.assertTrue(all(row['diagnostic'] and row['mutex_lock_offset'] == offset
                                for row in plan))
        for changes in (dict(backends=['native']), dict(backends=['kdlock', 'native']),
                        dict(backends=['kdlock'], kinds=['xattr'])):
            with self.subTest(changes=changes), self.assertRaises(run.Failure):
                run.make_plan(arguments(mutex_lock_offset=40, **changes))
        self.assertTrue(all(row['mutex_lock_offset'] is None and not row.get('diagnostic')
                            for row in run.make_plan(arguments())))

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

    def test_xattr_single_worker_keeps_separate_recorded_learning_cohort(self):
        plan = run.make_plan(arguments(kinds=['xattr'], queries=['tail'],
            entries=[16, 128], threads=[1, 60], backends=['native', 'tclock', 'kdlock'],
            require_jit=True))
        self.assertEqual(len(plan), 36)
        for row in plan:
            self.assertEqual(row['helper_cpus'], list(range(8)))
            self.assertEqual(row['cpus'], list(range(row['threads'])))
            self.assertEqual(row['jit_evidence_version'], 2)
            self.assertEqual(row['jit_completion_probe'], row['arm'] == 'kdlock')
            self.assertEqual(row['require_jit'], row['arm'] == 'kdlock' and row['threads'] > 1)

    def test_helper_cohort_cannot_share_collector_or_have_only_one_cpu(self):
        for changes in (dict(cpus='0', threads=[1]),
                        dict(threads=[1], collector_cpu=7), dict(helper_workers=1),
                        dict(helper_workers=17)):
            with self.subTest(changes=changes), self.assertRaises(run.Failure):
                run.make_plan(arguments(kinds=['xattr'], queries=['tail'], **changes))

    def test_live_translator_writer_blocks_measurement(self):
        session = run.SyscallSession.__new__(run.SyscallSession)
        session.record = {}
        session.loaded_kd = True
        session.publication = Mock(return_value=dict(source=dict(writers=1)))
        session.tell = Mock()
        with self.assertRaisesRegex(run.Failure, 'translator writer remains'):
            session.measure()
        session.tell.assert_not_called()


class CompleteBodyTests(unittest.TestCase):
    def test_entries_and_normal_publication_do_not_establish_helper_readiness(self):
        for entries in (0, 7):
            evidence = jit_evidence(entries, 0, 10, enabled=True)
            self.assertFalse(helper_ready([dict(status=0)], evidence))
            self.assertEqual(evidence['jit_status'], 'PARTIAL_JIT' if entries else 'NO_JIT')
        evidence = jit_evidence(7, 5, 10, enabled=True)
        self.assertTrue(helper_ready([dict(status=0)], evidence))
        self.assertFalse(helper_ready([dict(status=1)], evidence))
        self.assertEqual(evidence['jit_complete_share'], .5)

    def test_impossible_completion_counts_and_native_entries_fail(self):
        for args in ((1, 2, 5, True), (6, 2, 5, True), (1, -1, 5, True),
                     (1, 1, 5, False)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                jit_evidence(*args[:3], enabled=args[3])

    def learning_session(self, temporary, counter_steps):
        counts = Path(temporary)
        (counts/'bench_jit_bodies').write_text('0')
        (counts/'bench_jit_completions').write_text('0')
        session = run.SyscallSession.__new__(run.SyscallSession)
        session.record = dict(helper_waves=len(counter_steps), helper_cpus=[0, 1],
                              warmup=48000, warmup_ms=1)
        session.daemon = Namespace(pid=12345)
        session.pause_daemon = Mock()
        session.save = Mock()
        session.await_publication = Mock()
        steps = iter(counter_steps)
        def phase(*args, **kwargs):
            entered, completed = next(steps)
            (counts/'bench_jit_bodies').write_text(str(entered))
            (counts/'bench_jit_completions').write_text(str(completed))
            return dict(ok=True, completed=96000, started_ns=0, workers=[
                dict(cpu=cpu, observed_cpu=cpu, error=0, completed=48000,
                     finished_ns=1000000) for cpu in (0, 1)])
        session.tell = Mock(side_effect=phase)
        return session

    def test_cold_and_partial_learning_waves_continue_until_returned_body(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = self.learning_session(temporary, [(0, 0), (1, 0), (3, 2)])
            with patch.object(run, 'Path', return_value=Path(temporary)), \
                 patch.object(run, 'status', return_value=dict(frames=0, writers=1)), \
                 patch.object(run, 'registry', side_effect=[[dict(status=0)], [dict(status=1)], [dict(status=0)]]), \
                 patch.object(run.os, 'kill'):
                session.learn_helpers()
            self.assertEqual(session.tell.call_count, 3)
            self.assertEqual(session.await_publication.call_count, 1)
            self.assertEqual([r['jit_status'] for r in session.record['learning_waves']],
                             ['NO_JIT', 'PARTIAL_JIT', 'PASS'])

    def test_exhausted_cold_learning_is_not_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = self.learning_session(temporary, [(0, 0), (0, 0)])
            with patch.object(run, 'Path', return_value=Path(temporary)), \
                 patch.object(run, 'status', return_value=dict(frames=0, writers=1)), \
                 patch.object(run, 'registry', return_value=[dict(status=0)]), \
                 patch.object(run.os, 'kill'), \
                 self.assertRaisesRegex(run.Failure, 'did not establish complete delegation'):
                session.learn_helpers()
            self.assertEqual(session.tell.call_count, 2)
            self.assertEqual(len(session.record['learning_waves']), 2)


if __name__ == '__main__':
    unittest.main()
