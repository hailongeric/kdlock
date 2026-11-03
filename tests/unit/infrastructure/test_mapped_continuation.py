"""Guest-only validators with synthetic observations; no live mapping claim."""
import copy
import struct
import sys
import unittest
from source_text import ROOT

sys.path.insert(0, str(ROOT / 'tests/kernel/jit_continuation'))
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import mapped_mode as mapped
import helper_mode as helper


class MappedObservations(unittest.TestCase):
    def state(self):
        row = dict.fromkeys((*mapped.HEADER, *mapped.TAIL), 0)
        row.update(version=1, registered=1, source_target=0x200, execution_target=0x300,
                   calls=1, pid=10, stack_address=0x1800, stack_low=0x1000, stack_high=0x5000,
                   arguments=[1, 0, mapped.WORD, (1 << 64) - 1, 0x400], result=mapped.RESULT,
                   body_result=mapped.RESULT, body_after=1, body_flags=0x295, source_return=0x400)
        return row

    def events(self):
        text = '\n'.join(f'kd_service primitive: stage={stage} origin=10 executor=20 task={task} '
            f'identity=100 generation=7 sequence=1 target=200 return=400 image_generation=44 '
            f'ax={mapped.RESULT:x} flags=295 execution_target=300'
            for stage, task in (('request', 20), ('enter', 10), ('done', 10), ('resume', 20)))
        return helper.primitive_events(text)

    def validate(self, state, events):
        helper.validate_transaction(events, dict(identity=0x100, generation=7, executor=20),
                                    10, 0x200, 44, mapped.RESULT)
        mapped.validate_mapped(state, events, 10)

    def test_exact_mapped_task_stack_arguments_return_and_registers(self):
        self.validate(self.state(), self.events())
        for key, value in (('logical_calls', 1), ('calls', 2), ('body_after', 2), ('pid', 20),
                           ('stack_address', 0x5000), ('preempt', 1), ('irqs', 1),
                           ('source_return', 0x401), ('body_result', mapped.RESULT ^ 1),
                           ('body_flags', 0x294), ('execution_target', 0x200), ('allocation_freed', 1)):
            state = self.state(); state[key] = value
            with self.subTest(key=key), self.assertRaises(mapped.rt.Failure):
                self.validate(state, self.events())
        for index in range(5):
            state = self.state(); state['arguments'][index] ^= 1
            with self.subTest(argument=index), self.assertRaises(mapped.rt.Failure):
                self.validate(state, self.events())

    def test_native_target_trace_and_same_image_lifetime_cannot_be_substituted(self):
        for index, key, value in ((0, 'execution_target', 0x200), (1, 'task', 20),
                                  (2, 'return', 0x408), (3, 'image_generation', 45),
                                  (3, 'executor', 21), (3, 'flags', 0x294)):
            events = self.events(); events[index][key] = value
            with self.subTest(key=key), self.assertRaises(mapped.rt.Failure):
                self.validate(self.state(), events)
        events = self.events(); del events[2]['execution_target']
        with self.assertRaises(mapped.rt.Failure): self.validate(self.state(), events)
        with self.assertRaises(mapped.rt.Failure): self.validate(self.state(), self.events() * 2)

    def test_snapshot_keeps_logical_and_execution_identities_distinct(self):
        state = self.state()
        data = struct.pack('=30Q', *(state[key] for key in mapped.HEADER),
                           *state['arguments'], *(state[key] for key in mapped.TAIL))
        self.assertEqual(mapped.decode_snapshot(data), state)
        with self.assertRaises(mapped.rt.Failure): mapped.decode_snapshot(data[:-8])
        for key in ('version', 'registered', 'errors'):
            changed = dict(state); changed[key] ^= 1
            data = struct.pack('=30Q', *(changed[name] for name in mapped.HEADER),
                               *changed['arguments'], *(changed[name] for name in mapped.TAIL))
            with self.subTest(key=key), self.assertRaises(mapped.rt.Failure): mapped.decode_snapshot(data)

    def test_allocation_null_partial_contents_or_missing_free_refused(self):
        state = dict.fromkeys((*mapped.HEADER, *mapped.TAIL), 0)
        state.update(allocation_size=53, allocation_flags=0x100, allocation_pointer=0x8000,
                     allocation_zero_bytes=53, allocation_written_bytes=53,
                     allocation_freed=1, allocation_body_after=1)
        mapped.validate_allocation(state)
        for key in ('allocation_size', 'allocation_flags', 'allocation_pointer', 'allocation_zero_bytes',
                    'allocation_written_bytes', 'allocation_freed', 'allocation_body_after'):
            changed = copy.deepcopy(state); changed[key] = 0
            with self.subTest(key=key), self.assertRaises(mapped.rt.Failure): mapped.validate_allocation(changed)


if __name__ == '__main__':
    unittest.main()
