#!/usr/bin/env python3
"""Guest-only failure and deadline checks for accounting-triggered captures."""
import copy
from types import SimpleNamespace
import queue
import unittest
import boundary_trigger as trigger

S = trigger.SECOND


def sample(sequence=1, stamp=10*S):
    tasks = [dict(tid=i, comm='cpu'+str(i), affinity=[i % 64], complete=True,
                  identity_matches=True, identity_before=[i, 100+i], identity_after=[i, 100+i]) for i in range(67)]
    return dict(received=dict(mono_ns=stamp), remote=dict(event='sample', sequence=sequence,
        scan_began=dict(mono_ns=stamp+1000*S), scan_finished=dict(mono_ns=stamp+1000*S+1),
        mono_ns=stamp+1000*S+2, tasks=tasks))


class FakeStream:
    def __init__(self, events):
        self.now = 0
        self.events = events
        self.items = self

    def get(self, timeout):
        if self.events:
            at, event = self.events[0]
            if at <= self.now+int(timeout*S):
                self.now = max(self.now, at)
                self.events.pop(0)
                return event
        self.now += int(timeout*S)
        raise queue.Empty

    def sleep(self, seconds):
        self.now += int(seconds*S)


class BoundaryTrigger(unittest.TestCase):
    def setUp(self):
        self.event = sample()
        self.original = [dict(tid=i, comm='cpu'+str(i), affinity=[i % 64]) for i in range(67)]
        self.anchor = trigger.reference(self.original, self.event['remote'])

    def reason(self, event=None, now=10*S):
        return trigger.candidate(self.event if event is None else event, self.anchor, 1000*S, now)

    def test_exact_complete_sample_is_only_a_candidate(self):
        self.assertIsNone(self.reason())
        self.assertEqual(len(self.anchor['identities']), 67)

    def test_count_alone_cannot_trigger(self):
        mutations = [lambda t: t.update(tid=999), lambda t: t.update(comm='other'),
                     lambda t: t.update(affinity=[63]), lambda t: t.update(complete=False),
                     lambda t: t.update(identity_matches=False),
                     lambda t: t.update(identity_before=[0, 999], identity_after=[0, 999]),
                     lambda t: t.update(identity_after=[0, 999])]
        for mutation in mutations:
            changed = copy.deepcopy(self.event)
            mutation(changed['remote']['tasks'][0])
            with self.subTest(mutation=mutation):
                self.assertIsNotNone(self.reason(changed))
        changed = copy.deepcopy(self.event)
        changed['remote']['tasks'][0] = changed['remote']['tasks'][1]
        self.assertIsNotNone(self.reason(changed))

    def test_old_and_invalid_clock_samples_refuse(self):
        self.assertIsNotNone(self.reason(now=13*S))
        self.assertIsNotNone(self.reason(now=9*S))
        changed = copy.deepcopy(self.event)
        changed['remote']['scan_began']['mono_ns'] = 999*S
        self.assertIsNotNone(self.reason(changed))
        changed['remote']['scan_finished']['mono_ns'] = 998*S
        self.assertIsNotNone(self.reason(changed))

    def test_anchor_rejects_missing_original_or_partial_identity(self):
        changed = copy.deepcopy(self.event['remote'])
        changed['tasks'].pop()
        with self.assertRaises(ValueError):
            trigger.reference(self.original, changed)
        with self.assertRaises(ValueError):
            trigger.reference(self.original[:-1]+[self.original[0]], self.event['remote'])

    def test_host_capture_age_cannot_be_inferred_from_queue_age(self):
        for age, qualified in [(0, True), (2*S, True), (2*S+1, False), (-1, False)]:
            result = trigger.capture_age(dict(scan_began_ns=1000*S), dict(capture_began=dict(mono_ns=1000*S+age)))
            self.assertEqual(result['qualified'], qualified)

    def generator(self, stream, decisions):
        return trigger.triggers(stream, self.anchor, 1000*S, 0, decisions, lambda: None,
                                clock=lambda: stream.now, sleep=stream.sleep)

    def test_one_deadline_cooldown_duplicates_and_terminal(self):
        stream = FakeStream([(5*S, sample(1, 5*S)), (10*S, sample(2, 10*S)),
                             (24*S, sample(1, 24*S)), (25*S, sample(3, 25*S))])
        decisions = []
        values = self.generator(stream, decisions)
        self.assertEqual(next(values)['sequence'], 1)
        stream.now = 8*S  # First full capture returns refused after three seconds.
        self.assertEqual(next(values)['sequence'], 3)
        self.assertEqual(decisions[1]['reason'], 'capture refusal cooldown')
        self.assertEqual(decisions[2]['reason'], 'duplicate or reordered sample')
        terminal = next(values)
        self.assertEqual(terminal['kind'], 'terminal')
        self.assertEqual(stream.now, 120*S)
        with self.assertRaises(StopIteration):
            next(values)

    def test_silent_observer_is_bounded_and_eof_is_not_refusal(self):
        stream = FakeStream([])
        self.assertEqual(list(self.generator(stream, []))[0]['kind'], 'terminal')
        self.assertEqual(stream.now, 120*S)
        for event in (None, {'reader_error': 'broken'}, {'remote': {'event': 'complete'}}):
            with self.subTest(event=event), self.assertRaises(RuntimeError):
                next(self.generator(FakeStream([(0, event)]), []))

    def test_candidate_budget_reserves_terminal(self):
        stream = FakeStream([(i*20*S, sample(i, i*20*S)) for i in range(1, 6)])
        values = list(self.generator(stream, []))
        self.assertEqual([v['kind'] for v in values], ['sample']*4+['terminal'])
        self.assertEqual(stream.now, 120*S)
        late = FakeStream([(96*S, sample(1, 96*S))])
        self.assertEqual([v['kind'] for v in self.generator(late, [])], ['terminal'])
        self.assertEqual(late.now, 120*S)


if __name__ == '__main__':
    unittest.main()
