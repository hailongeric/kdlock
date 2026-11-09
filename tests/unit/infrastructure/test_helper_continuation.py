"""Guest-only returning-primitive observation and normal retirement checks."""
from pathlib import Path
import copy
import struct
import sys
import unittest
from unittest.mock import patch

from source_text import ROOT

sys.path.insert(0, str(ROOT / 'tests/kernel/jit_continuation'))
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import helper_mode as helper
import bench_session


class HelperObservations(unittest.TestCase):
    def events(self, context_kind=None, argument0=None):
        value = helper.expected_result(1)
        lines = []
        for stage, task, ax in (('request', 20, 0), ('enter', 10, 0),
                                ('done', 10, value), ('resume', 20, value)):
            line = (f'kd_service primitive: stage={stage} origin=10 executor=20 task={task} '
                         f'identity=100 generation=7 sequence=3 target=200 return=400 '
                         f'image_generation=44 ax={ax:x} flags=202')
            if context_kind is not None:
                line += f' context_kind={context_kind}'
            if argument0 is not None:
                line += f' argument0={argument0:x}'
            lines.append(line)
        return helper.primitive_events('\n'.join(lines))

    def validate(self, rows):
        return helper.validate_transaction(rows, dict(identity=0x100, generation=7, executor=20),
                                           10, 0x200, 44, helper.expected_result(1))

    def test_exact_transaction_and_full_ax(self):
        self.assertEqual(helper.expected_result(1), 0x993F730E40218045)
        self.assertEqual(len(self.validate(self.events())), 4)
        for index, field, value in ((1, 'task', 20), (3, 'executor', 21),
                                     (3, 'image_generation', 45), (3, 'return', 0x408),
                                     (3, 'sequence', 4), (3, 'ax', 0x40218045),
                                     (3, 'flags', 0x203), (2, 'identity', 0x101)):
            rows = self.events()
            rows[index][field] = value
            with self.subTest(field=field), self.assertRaises(helper.rt.Failure):
                self.validate(rows)
        with self.assertRaises(helper.rt.Failure):
            self.validate(self.events()[:-1])

    def test_optional_resolved_context_and_argument_are_exact_across_ack(self):
        for context in range(1, 14):
            for argument in (0, 0xffffffffffffffff):
                rows = self.events(context, argument)
                self.assertEqual(rows[0]['context_kind'], context)
                self.assertEqual(rows[0]['argument0'], argument)
                self.assertEqual(len(self.validate(rows)), 4)
        for context in (0, 14, 15):
            with self.subTest(context=context), self.assertRaises(helper.rt.Failure):
                self.validate(self.events(context, 0))
        for argument in (-1, 1 << 64):
            with self.subTest(argument=argument), self.assertRaises(helper.rt.Failure):
                self.validate(self.events(1, argument))
        for index, field in ((0, 'context_kind'), (1, 'argument0'), (3, 'context_kind'), (3, 'argument0')):
            rows = self.events(1, 0xdead)
            rows[index].pop(field)
            with self.subTest(index=index, field=field), self.assertRaises(helper.rt.Failure):
                self.validate(rows)
        for field, value in (('context_kind', 2), ('argument0', 0xbeef)):
            rows = self.events(1, 0xdead)
            rows[2][field] = value
            with self.subTest(field=field), self.assertRaises(helper.rt.Failure):
                self.validate(rows)
        for rows in (self.events(1), self.events(argument0=0)):
            with self.assertRaises(helper.rt.Failure):
                self.validate(rows)

    def test_registration_arity_and_unique_target(self):
        table = ''.join(f'{10 + index:x} {(index + 1) * 0x1000:x} {arity} {result} {context} {name}\n'
                        for index, (name, (arity, result, context)) in enumerate(helper.DECLARATIONS.items()))
        rows, _ = helper.call_table(table)
        self.assertEqual(rows['jit_test_call_scalar']['cookie'], 10)
        for changed in (table.replace(' 6 ', ' 7 ', 1), table.replace('b 2000', '0 2000'),
                        table.replace('b 2000', 'b 1000'), table + table.splitlines()[0] + '\n',
                        table.replace(' 1 2 4 ', ' 1 2 1 ')):
            with self.assertRaises(helper.rt.Failure):
                helper.call_table(changed)

    def test_snapshot_exact_offsets_and_size(self):
        words = [1, 1, 0] + [0] * 184
        row = [0x1000, 1, 10, 0x1800, 0x1000, 0x5000, 0, 0,
               1, *helper.ARGUMENTS, helper.expected_result(1), helper.expected_result(1),
               1, 2, 1, 1, 1, 1, 1]
        self.assertEqual(len(row), 23)
        words[26:49] = row
        data = struct.pack('=187Q', *words)
        decoded = helper.decode_helper_snapshot(data)['slots'][1]
        self.assertEqual(decoded['arguments'], [1, *helper.ARGUMENTS])
        self.assertEqual(decoded['body_result'], helper.expected_result(1))
        self.assertEqual(decoded['child_released'], 1)
        with self.assertRaises(helper.rt.Failure):
            helper.decode_helper_snapshot(data[:-8])

    def native_state(self, early=False):
        rows = []
        for operation, before, after, rcu_before, rcu_after, value, _, _ in helper.native_plan(early):
            rows.append(dict(zip(helper.NATIVE_FIELDS,
                (operation, 10, 0x1800, before, after, rcu_before, rcu_after, 0, 0, value))))
        return dict(version=1, count=len(rows), errors=0, lock_address=0x8000, body_after=1,
                    stack_low=0x1000, stack_high=0x5000, events=rows)

    def native_messages(self, early=False):
        names = {1: 'jit_test_native_spin_lock', 2: 'jit_test_native_spin_try',
                 3: 'jit_test_native_spin_unlock', 4: 'jit_test_native_rcu_lock',
                 5: 'jit_test_native_rcu_unlock'}
        descriptors = {name: dict(target=0x1000 + index * 0x100)
                       for index, name in enumerate(helper.SYMBOLS)}
        lines = []
        plan = helper.native_plan(early)
        for sequence, expected in enumerate(plan, 1):
            operation, _, after, _, rcu_after, value, owner_stage, acquisition = expected
            for stage, task in (('request', 20), ('enter', 10), ('done', 10),
                                ('complete' if early and sequence == len(plan) else 'resume', 20)):
                lines.append(f'kd_service primitive: stage={stage} origin=10 executor=20 task={task} '
                    f'identity=100 generation=7 sequence={sequence} target={descriptors[names[operation]]["target"]:x} '
                    f'return={0x400 + sequence * 8:x} image_generation=44 ax={value:x} flags=202')
            lines.append(f'kd_service native: stage={owner_stage} origin=10 executor=20 task=10 '
                f'identity=100 generation=7 sequence={sequence} acquisition_seq={acquisition} '
                f'kind={1 if operation <= 3 else 2} object={"8000" if operation <= 3 else "0"} '
                f'preempt={after} rcu={rcu_after}')
        return '\n'.join(lines), descriptors

    def test_native_pair_context_results_and_final_complete(self):
        root = dict(identity=0x100, generation=7, executor=20)
        for early, count in ((False, 23), (True, 2)):
            state = self.native_state(early)
            messages, descriptors = self.native_messages(early)
            checked = helper.validate_native_trace(messages, root, 10, descriptors, 44, state, early)
            self.assertEqual(len(checked['owners']), count)
            self.assertEqual(max(row['rcu_after'] for row in state['events']), 0 if early else 9)
        messages, descriptors = self.native_messages(True)
        for changed in (messages.replace('stage=complete', 'stage=resume'),
                        messages.replace('acquisition_seq=1 kind=1', 'acquisition_seq=2 kind=1', 1),
                        messages.replace('stage=release origin=10 executor=20 task=10',
                                         'stage=release origin=10 executor=20 task=20')):
            with self.assertRaises(helper.rt.Failure):
                helper.validate_native_trace(changed, root, 10, descriptors, 44, self.native_state(True), True)
        messages, descriptors = self.native_messages()
        with self.assertRaises(helper.rt.Failure):
            helper.validate_native_trace(messages.replace('stage=not_granted', 'stage=grant'), root, 10,
                                         descriptors, 44, self.native_state())
        for index, field, value in ((1, 'result', 1), (1, 'preempt_after', 2),
                                     (2, 'rcu_after', 0), (0, 'pid', 20),
                                     (0, 'stack_address', 0x5000), (22, 'irqs_after', 1)):
            state = copy.deepcopy(self.native_state())
            state['events'][index][field] = value
            with self.subTest(field=field), self.assertRaises(helper.rt.Failure):
                helper.validate_native_observation(state, 10)

    def test_native_observation_abi_and_censoring(self):
        state = self.native_state(True)
        words = [1, 2, 0, 0x8000, 1, 0x1000, 0x5000]
        for event in state['events']:
            words.extend(event[name] for name in helper.NATIVE_FIELDS)
        words.extend([0] * (247 - len(words)))
        data = struct.pack('=247Q', *words)
        decoded = helper.decode_native_snapshot(data)
        self.assertEqual(decoded, state)
        for mutated in (data[:-8], struct.pack('=247Q', 1, 25, *words[2:])):
            with self.assertRaises(helper.rt.Failure):
                helper.decode_native_snapshot(mutated)
        state['count'] = 1
        state['events'] = state['events'][:1]
        with self.assertRaises(helper.rt.Failure):
            helper.validate_native_observation(state, 10, True)

    def test_optional_hook_follows_source_retire_before_unload(self):
        session = bench_session.Session.__new__(bench_session.Session)
        session.loaded_kd = session.loaded_source = True
        session.workload_module = Path('/unused/jit_continuation_test.ko')
        session.record = {}
        order = []
        session.faults = session.stop_daemon = session.save = lambda: None
        session.counts = lambda label: dict(active=0)
        session.run = lambda argv, log: order.append('unload-' + argv[1])
        session.after_source_retire = lambda: order.append('unregister')
        def retire(*args):
            order.append('retire')
        with patch.object(bench_session, 'status', return_value=dict(frames=0, writers=0)), \
             patch.object(bench_session, 'info', return_value=dict(state=2, modules=0, frames=0, writers=0)), \
             patch.object(bench_session.os, 'open', return_value=9), \
             patch.object(bench_session.os, 'close'), \
             patch.object(bench_session.fcntl, 'ioctl', side_effect=retire):
            session.cleanup()
        self.assertEqual(order, ['retire', 'unregister', 'unload-jit_continuation_test', 'unload-kdlock_km'])


if __name__ == '__main__':
    unittest.main()
