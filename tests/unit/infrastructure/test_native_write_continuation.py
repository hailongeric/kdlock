"""VM-only exact Native writer observation and transaction pairing fixtures."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest

from source_text import ROOT
sys.path.insert(0, str(ROOT / 'tests/kernel/jit_continuation'))
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import native_write_mode as writer


class NativeWriters(unittest.TestCase):
    def state(self, early=False):
        state = dict(version=1, errors=0, count=2 if early else 4, body_after=1,
            lock_a=0x8000, lock_b=0x9000, stack_low=0x1000, stack_high=0x5000,
            attempts=1 if early else 2, grants=1 if early else 2, holder_active=0, native_waiters=0,
            progress=0 if early else 1, progress_pid=0 if early else 11, progress_cpu=2)
        state['events'] = []
        for sequence, (operation, obj, _, _) in enumerate(writer.plan(state, early), 1):
            state['events'].append(dict(operation=operation, object=obj, pid=10, cpu=1, stack_address=0x1800,
                preempt_before=0, preempt_after=0, rcu_before=0, rcu_after=0, irqs_before=0, irqs_after=0,
                switches_before=100+sequence, switches_after=100+sequence+int(not early and sequence == 1)))
        return state

    def messages(self, early=False):
        descriptors = {'jit_test_native_write_lock': dict(target=0x200), 'jit_test_native_write_unlock': dict(target=0x300)}
        lines = []
        for sequence, (operation, obj, owner_stage, acquisition) in enumerate(writer.plan(self.state(early), early), 1):
            for stage, task in (('request', 20), ('enter', 10), ('done', 10),
                                ('complete' if early and sequence == 2 else 'resume', 20)):
                lines.append(f'kd_service primitive: stage={stage} origin=10 executor=20 task={task} '
                    f'identity=100 generation=7 sequence={sequence} target={0x200 if operation == 1 else 0x300:x} '
                    f'return={0x400+8*sequence:x} image_generation=44 ax=0 flags=202')
            lines.append(f'kd_service native: stage={owner_stage} origin=10 executor=20 task=10 '
                f'identity=100 generation=7 sequence={sequence} acquisition_seq={acquisition} '
                f'kind=4 object={obj:x} preempt=0 rcu=0')
        return '\n'.join(lines), descriptors

    def validate(self, early=False, state=None, messages=None):
        original, descriptors = self.messages(early)
        return writer.validate(original if messages is None else messages,
            dict(identity=0x100, generation=7, executor=20), 10, 1, descriptors, 44,
            self.state(early) if state is None else state, early)

    def test_two_native_objects_nonlifo_and_final_native_release(self):
        regular = self.validate()
        self.assertEqual([event['acquisition_seq'] for event in regular['owners']], [1, 2, 1, 2])
        self.assertEqual([event['object'] for event in regular['owners']], [0x8000, 0x9000, 0x8000, 0x9000])
        final = self.validate(True)
        self.assertTrue(final['final_native_complete'])
        self.assertEqual(final['transactions'][-1][-1]['stage'], 'complete')

    def test_actual_origin_native_blocking_and_context_negative_controls(self):
        changes = (lambda x: x['events'][0].update(switches_after=x['events'][0]['switches_before']),
                   lambda x: x['events'][0].update(pid=20), lambda x: x['events'][1].update(cpu=0),
                   lambda x: x['events'][2].update(object=0x9000), lambda x: x['events'][0].update(stack_address=0x5000),
                   lambda x: x['events'][3].update(irqs_after=1), lambda x: x['events'][1].update(rcu_after=1),
                   lambda x: x.update(body_after=0), lambda x: x.update(holder_active=1),
                   lambda x: x.update(native_waiters=1), lambda x: x.update(progress=0))
        for change in changes:
            state = copy.deepcopy(self.state())
            change(state)
            with self.assertRaises(writer.rt.Failure):
                self.validate(state=state)
        text, _ = self.messages()
        for changed in (text.replace('kind=4', 'kind=1', 1),
                        text.replace('sequence=3 acquisition_seq=1', 'sequence=3 acquisition_seq=2'),
                        text.replace('stage=release origin=10 executor=20 task=10',
                                     'stage=release origin=10 executor=20 task=20', 1),
                        '\n'.join(text.splitlines()[:-1])):
            with self.assertRaises(writer.rt.Failure):
                self.validate(messages=changed)
        early, _ = self.messages(True)
        with self.assertRaises(writer.rt.Failure):
            self.validate(True, messages=early.replace('stage=complete', 'stage=resume'))

    def test_separate_952_byte_abi_and_partial_observation(self):
        state = self.state()
        words = [state[name] for name in writer.HEADER]
        for event in state['events']:
            words.extend(event[name] for name in writer.FIELDS)
        words += [0] * (119-len(words))
        data = struct.pack('=119Q', *words)
        self.assertEqual(writer.decode_snapshot(data), state)
        for changed in (data[:-8], struct.pack('=119Q', *words[:2], 9, *words[3:]),
                        struct.pack('=119Q', *words[:-1], 1)):
            with self.assertRaises(writer.rt.Failure):
                writer.decode_snapshot(changed)

    def test_root_enter_is_collected_after_the_blocked_snapshot(self):
        line = ('kd_service event=enter origin=10 executor=20 identity=100 generation=7 '
                'object=8000 depth=0 entry=a000 may_delegate=1\n')
        with tempfile.TemporaryDirectory() as directory:
            session = SimpleNamespace(path=Path(directory), messages='', trace_start=0)
            calls = []
            def drain():
                calls.append(1)
                if len(calls) == 2:
                    session.messages += line
            session.faults = drain
            root = writer.wait_root_enter(session, 'delayed-enter', 10, 0x8000, 0xA000)
            self.assertEqual(root['executor'], 20)
            self.assertEqual(json.loads((session.path/'delayed-enter.json').read_text())['capture_reads'], 2)
            for name, changed in (('duplicate', line+line), ('same-task', line.replace('executor=20', 'executor=10')),
                                  ('wrong-object', line.replace('object=8000', 'object=8001')),
                                  ('wrong-entry', line.replace('entry=a000', 'entry=a001')),
                                  ('zero-generation', line.replace('generation=7', 'generation=0'))):
                session.messages = changed
                session.faults = lambda: None
                with self.assertRaises(writer.rt.Failure) as failure:
                    writer.wait_root_enter(session, name, 10, 0x8000, 0xA000)
                self.assertTrue(failure.exception.unsafe)
                self.assertEqual(failure.exception.status, 'UNDRAINED')
            session.messages = ''
            with self.assertRaises(writer.rt.Failure) as failure:
                writer.wait_root_enter(session, 'missing', 10, 0x8000, 0xA000, timeout=0)
            self.assertTrue(failure.exception.unsafe)
            self.assertTrue((session.path/'missing.timeout.json').is_file())


if __name__ == '__main__':
    unittest.main()
