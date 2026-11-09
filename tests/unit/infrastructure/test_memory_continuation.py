"""Focused receipt checks; actual instructions/ownership require the VM fixture."""
import copy
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tests/kernel/jit_continuation'))
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import memory_mode as memory


class MemoryObservations(unittest.TestCase):
    def state(self, early=False):
        plan = [(0, 0), (1, 0), (0, 0)] if early else [(0, 0), (0, 1), (1, 1), (0, 0)]
        checks = len(memory.memory_plan(early))
        return dict(version=1, errors=0, count=len(plan), origin_stack=0x1000,
                    origin_stack_high=0x5000, body_after=1, cf_checks=checks,
                    reg_checks=checks, sp_checks=checks, read_value=0x80000001, read_checks=1,
                    events=[dict(zip(memory.FIELDS, (stage, 10, 1, 0x2000, preempt, 0, counter)))
                            for stage, (preempt, counter) in enumerate(plan)])

    def messages(self, early=False):
        lines = []
        for sequence, (operation, width, preempt) in enumerate(memory.memory_plan(early), 1):
            final = early and sequence == len(memory.memory_plan(early))
            reading = operation == 3
            owns_preempt = preempt and not reading
            flags = 0x203 | (0x40 if width == 64 and operation == 2 else 0)
            for stage, task in [('request', 20), ('enter', 10), ('done', 10),
                                ('complete' if final else 'resume', 20)]:
                output = flags if stage in ('done', 'resume', 'complete') else 0
                value = 0x80000001 if reading and stage in ('done', 'resume') else 0
                lines.append('kd_service memory: '
                    f'stage={stage} origin=10 executor=20 task={task} identity=100 generation=7 '
                    f'sequence={sequence} image_generation=44 ip={0x7000 + sequence * 16:x} '
                    f'next={0x7007 + sequence * 16:x} sp=3000 offset={0xe00 if preempt else 0xd00:x} '
                    f'width={width} operation={operation} preempt_operand={preempt} '
                    f'preempt_seq={(1 if early else 2) if owns_preempt else 0} '
                    f'preempt_object={0xffff0010 if owns_preempt else 0:x} input_flags=203 output_flags={output:x} '
                    f'read={int(reading)} destination={12 if reading else 17} value={value:x}')
        return '\n'.join(lines)

    def validate(self, text, state, early=False):
        return memory.validate_memory_trace(text, dict(identity=0x100, generation=7, executor=20),
                                            10, 44, state, 1, early)

    def test_exact_counter_and_final_instruction_receipts(self):
        for early in (False, True):
            result = self.validate(self.messages(early), self.state(early), early)
            self.assertEqual(len(result['transactions']), 3 if early else 5)

    def test_native_need_resched_bit_is_retained_without_runtime_pin(self):
        state = self.state()
        state['read_value'] = 1
        self.validate(self.messages().replace('value=80000001', 'value=1'), state)

    def test_wrong_actor_flags_ticket_and_final_boundary_refused(self):
        normal, early = self.messages(), self.messages(True)
        mutations = [(normal.replace('task=10', 'task=20', 1), False),
                     (normal.replace('generation=7', 'generation=8', 1), False),
                     (normal.replace('output_flags=203', 'output_flags=202', 1), False),
                     (normal.replace('preempt_seq=2', 'preempt_seq=1'), False),
                     (normal.replace('read=1', 'read=0', 1), False),
                     (normal.replace('destination=12', 'destination=4'), False),
                     (normal.replace('value=80000001', 'value=80000002', 1), False),
                     (early.replace('stage=complete', 'stage=resume'), True)]
        for text, final in mutations:
            with self.subTest(final=final, text=text), self.assertRaises(memory.rt.Failure):
                self.validate(text, self.state(final), final)

    def test_mov_has_no_new_ticket_and_preserves_all_arithmetic_flags(self):
        normal = self.messages()
        owned_read = '\n'.join(line.replace('preempt_seq=0', 'preempt_seq=2')
                               if 'operation=3 ' in line else line for line in normal.splitlines())
        changed_flags = '\n'.join(line.replace('output_flags=203', 'output_flags=243')
                                  if 'operation=3 ' in line else line for line in normal.splitlines())
        for text in (owned_read, changed_flags):
            with self.subTest(text=text), self.assertRaises(memory.rt.Failure):
                self.validate(text, self.state())

    def test_counter_context_gpr_sp_and_replay_observations_refused(self):
        for field in ('errors', 'body_after', 'cf_checks', 'reg_checks', 'sp_checks', 'read_checks'):
            state = self.state()
            state[field] += 1
            with self.subTest(field=field), self.assertRaises(memory.rt.Failure):
                self.validate(self.messages(), state)
        for value in (0x80000002, 0x100000001):
            state = self.state()
            state['read_value'] = value
            with self.subTest(value=value), self.assertRaises(memory.rt.Failure):
                self.validate(self.messages(), state)
        for field in ('pid', 'cpu', 'preempt', 'counter'):
            state = copy.deepcopy(self.state())
            state['events'][2][field] += 1
            with self.subTest(field=field), self.assertRaises(memory.rt.Failure):
                self.validate(self.messages(), state)

    def test_separate_observation_layout(self):
        state = self.state()
        words = [state[field] for field in memory.HEADER]
        for event in state['events']:
            words.extend(event[field] for field in memory.FIELDS)
        data = struct.pack('=39Q', *words)
        self.assertEqual(memory.decode_memory_snapshot(data), state)
        with self.assertRaises(memory.rt.Failure):
            memory.decode_memory_snapshot(data[:-8])


if __name__ == '__main__':
    unittest.main()
