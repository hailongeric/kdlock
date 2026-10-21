#!/usr/bin/env python3
"""Guest-only ordering, refusal and identity checks for the no-timing control."""
import copy
import ast
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
import prewarmup_control
from prewarmup_control import PreWarmupRefused, capture_policy, run_once, validate_transition


class PreWarmupControl(unittest.TestCase):
    def invoke(self, pre=True, post=True, fail=None):
        self.events, self.record = [], {}
        def exchange(stage):
            self.events.append(stage)
            if fail == stage:
                raise TimeoutError(stage)
            return dict(gate=dict(passed=pre if stage == 'before-warmup' else post))
        def warmup():
            self.events.append('original-warmup')
            if fail == 'warmup':
                raise ValueError('malformed reply')
            return dict(ok=True, completed=42)
        return run_once(exchange, warmup, self.record, lambda: len(self.events))

    def test_original_warmup_once_and_immediate_post_even_when_refused(self):
        for post in (True, False):
            self.assertEqual(self.invoke(post=post), dict(ok=True, completed=42))
            self.assertEqual(self.events, ['before-warmup', 'original-warmup', 'after-warmup-immediate'])
            self.assertEqual(self.record['prewarmup_control']['warmup_commands'], 1)
            self.assertEqual(self.record['prewarmup_control']['measurement_commands'], 0)

    def test_observed_pre_refusal_skips_warmup_and_post(self):
        with self.assertRaises(PreWarmupRefused):
            self.invoke(pre=False)
        self.assertEqual(self.events, ['before-warmup'])
        self.assertEqual(self.record['prewarmup_control']['warmup_commands'], 0)
        self.assertTrue(self.record['prewarmup_control']['warmup_skipped'])
        self.assertNotIn('boundary_warmup', self.record)

    def test_coordination_uncertainty_propagates_without_retry(self):
        for stage, expected in [('before-warmup', ['before-warmup']),
                                ('after-warmup-immediate', ['before-warmup', 'original-warmup', 'after-warmup-immediate'])]:
            with self.subTest(stage=stage), self.assertRaises(TimeoutError):
                self.invoke(fail=stage)
            self.assertEqual(self.events, expected)
            self.assertEqual(self.record['prewarmup_control']['measurement_commands'], 0)

    def test_invalid_warmup_reply_cannot_create_post_success(self):
        with self.assertRaises(ValueError):
            self.invoke(fail='warmup')
        self.assertEqual(self.events, ['before-warmup', 'original-warmup'])
        self.assertNotIn('boundary_warmup', self.record)

    def test_repeat_cannot_send_another_warmup(self):
        self.invoke()
        with self.assertRaises(ValueError):
            run_once(lambda _: self.fail('repeated gate'), lambda: self.fail('repeated warmup'), self.record, lambda: 0)

    def test_stage_order_and_one_immediate_capture_policy(self):
        self.assertEqual(capture_policy(True, 1, 'before-warmup'), 'wait')
        self.assertEqual(capture_policy(True, 2, 'after-warmup-immediate'), 'immediate')
        self.assertEqual(capture_policy(False, 1, 'after-warmup'), 'wait')
        for args in [(True, True, 'before-warmup'), (True, 1, 'after-warmup-immediate'),
                     (True, 2, 'before-warmup'), (True, 3, 'after-warmup-immediate'),
                     (False, 2, 'after-warmup'), (False, 1, 'before-warmup')]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                capture_policy(*args)

    def test_joined_counter_changes_preserve_identity(self):
        before = dict(client_pid=12, publication=dict(image='immutable', frames=0), physical_idle=True,
                      calls=1, counters=dict(bench_jit_bodies=0, bench_jit_completions=0, address_guard_count=0))
        after = copy.deepcopy(before)
        after['calls'] += 42
        after['counters'].update(bench_jit_bodies=17, bench_jit_completions=17)
        work = dict(ok=True, completed=42)
        self.assertEqual(validate_transition(before, after, work)['bench_jit_completions'], 17)
        mutations = [lambda r: r.update(client_pid=13), lambda r: r.update(calls=42),
                     lambda r: r.update(physical_idle=False), lambda r: r['publication'].update(image='other'),
                     lambda r: r['counters'].update(bench_jit_completions=16),
                     lambda r: r['counters'].update(address_guard_count=1),
                     lambda r: r['counters'].update(bench_jit_bodies=43, bench_jit_completions=43)]
        for mutate in mutations:
            changed = copy.deepcopy(after)
            mutate(changed)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                validate_transition(before, changed, work)


class RunnerBranches(unittest.TestCase):
    """Exercise actual runner methods with a fake original client, never ioctl."""
    def session(self, refused=False, warmup_error=None, work=None, post=False):
        events = self.events = []
        class Failure(Exception):
            def __init__(self, status, message, unsafe=False):
                self.status, self.unsafe = status, unsafe
                super().__init__(message)
        self.Failure = Failure
        class Original:
            def prepare(self):
                self.tell('warmup')
                events.append('original-prepare-after-warmup')
            def tell(self, action, timeout=180, label=None):
                events.append('original-'+action)
                if warmup_error:
                    raise warmup_error
                return work if action == 'warmup' else dict(check=True)
            def save(self):
                events.append('save')
            def faults(self):
                events.append('faults')
        def require(ok, message):
            if not ok:
                raise ValueError(message)
        tree = ast.parse(Path(__file__).with_name('unlock_run.py').read_text())
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        cls = next(n for n in main.body if isinstance(n, ast.ClassDef) and n.name == 'MatchedSession')
        scope = dict(api=SimpleNamespace(SyscallSession=Original, Failure=Failure),
            a=SimpleNamespace(prewarmup_boundary_probe=True, setup_boundary_probe=True, mode='timing'),
            prewarmup=prewarmup_control, require=require, expected_offset=32, time=time,
            phase=lambda label, edge: events.append(label+'-'+edge))
        exec(compile(ast.Module(body=[cls], type_ignores=[]), '<actual runner class>', 'exec'), scope)
        session = scope['MatchedSession']()
        session.record = dict(lock_addr=32, threads=5, cpus=list(range(5)), warmup=48000, warmup_ms=1000)
        def exchange(stage):
            events.append(stage)
            state = dict(client_pid=12, publication=dict(image='immutable'), physical_idle=True,
                         calls=1, counters=dict(bench_jit_bodies=0, bench_jit_completions=0, address_guard_count=0))
            if stage == 'after-warmup-immediate':
                state['calls'] += work['completed']
            boundary = dict(gate=dict(passed=not refused if stage == 'before-warmup' else post),
                            before=state, after=state)
            session.record.setdefault('boundaries', []).append(boundary)
            return boundary
        session.exchange_boundary = exchange
        return session

    def test_safe_pre_refusal_is_caught_inside_prepare(self):
        session = self.session(refused=True)
        session.prepare()
        self.assertNotIn('original-warmup', self.events)
        self.assertNotIn('original-prepare-after-warmup', self.events)
        self.assertIn('prepare-end', self.events)
        self.assertTrue(session.record['prewarmup_control']['warmup_skipped'])
        session.measure()
        self.assertNotIn('original-measure', self.events)
        self.assertIn('original-check', self.events)

    def test_uncertain_warmup_is_unsafe_for_base_execute_cleanup(self):
        for error in (ValueError('malformed JSON'), OSError('pipe lost'), KeyError('missing field')):
            session = self.session(warmup_error=error)
            with self.subTest(error=error), self.assertRaises(self.Failure) as caught:
                session.prepare()
            self.assertTrue(caught.exception.unsafe)
            self.assertEqual(caught.exception.status, 'UNDRAINED')
            self.assertNotIn('after-warmup-immediate', self.events)
            self.assertNotIn('prepare-end', self.events)

    def test_loaded_placement_refuses_before_gate_and_warmup(self):
        session = self.session()
        session.record['lock_addr'] = 0
        with self.assertRaises(ValueError):
            session.prepare()
        self.assertNotIn('before-warmup', self.events)
        self.assertNotIn('original-warmup', self.events)

    def work(self):
        return dict(ok=True, completed=240000, started_ns=1, collector_cpu=63,
            collector_observed_cpu=63, collector_error=0,
            workers=[dict(cpu=i, observed_cpu=i, completed=48000, finished_ns=1000000001, error=0)
                     for i in range(5)])

    def test_returned_invalid_work_is_unsafe(self):
        wrong_worker = self.work()
        wrong_worker['workers'][0]['observed_cpu'] = 63
        for work in (None, {}, dict(self.work(), ok=False), wrong_worker,
                     dict(self.work(), collector_error=1)):
            session = self.session(work=work)
            with self.subTest(work=work), self.assertRaises(self.Failure) as caught:
                session.prepare()
            self.assertTrue(caught.exception.unsafe)
            self.assertNotIn('after-warmup-immediate', self.events)

    def test_immediate_post_precedes_phase_end_and_original_prepare_continuation(self):
        session = self.session(work=self.work(), post=False)
        session.prepare()
        post = self.events.index('after-warmup-immediate')
        self.assertLess(post, self.events.index('client-warmup-end'))
        self.assertLess(post, self.events.index('original-prepare-after-warmup'))
        session.measure()
        self.assertEqual(self.events.count('original-warmup'), 1)
        self.assertEqual(self.events.count('after-warmup-immediate'), 1)
        self.assertNotIn('original-measure', self.events)


if __name__ == '__main__':
    unittest.main()
