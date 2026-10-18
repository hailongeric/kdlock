"""Source-graph proof for flags-clobbering spin address guards; guest only."""

import struct
import unittest
from unittest.mock import patch

from test_jit_diagnostics import translator
from context_values import FlowConstants
from guard_flags import prove_flags_dead


def call(target, source):
    return b'\xe8' + struct.pack('<i', target - source - 5)


class GuardFlagsTests(unittest.TestCase):
    def proof(self, raw, *, regions=None, entry=0x1000, **kwargs):
        terminals = tuple(kwargs.get('terminal_calls', ()))
        blocks, databases = translator.decode_regions(
            regions or [(bytes.fromhex(raw), 0x1000, [0x1000])],
            terminals[0] if terminals else 0, set())
        return prove_flags_dead(blocks, databases, entry, **kwargs)

    def test_loads_then_full_flag_overwrite(self):
        # Xattr's pointer/name loads before strcmp do not consume flags.
        self.assertIsNone(self.proof('488b7310488b7df829c0c3'))

    def test_carry_and_condition_reads_before_overwrite_refuse(self):
        for raw in ('488b73104883d00029c0c3', '0f94c029c0c3',
                    '740229c0c3', '480f44c329c0c3'):
            with self.subTest(raw=raw):
                self.assertIn('incoming arithmetic flags', self.proof(raw))

    def test_partial_flag_writer_does_not_define_carry(self):
        self.assertIn('cf', self.proof('ffc083d30029c0c3'))
        # OF is defined by INC; observing it is safe if SUB subsequently
        # replaces all remaining incoming flags before their first use.
        self.assertIsNone(self.proof('ffc00f90c329c0c3'))

    def test_every_flag_free_branch_arm_is_checked(self):
        # JRCXZ selects either SUB or ADC without reading an arithmetic flag.
        self.assertIsNone(self.proof('e30329c0c329dbc3'))
        self.assertIn('incoming arithmetic flags',
                      self.proof('e30329c0c383d30029c0c3'))

    def test_call_requires_callee_and_checks_real_flag_reads(self):
        caller = call(0x2000, 0x1000) + bytes.fromhex('29c0c3')
        for helper, accepted in (('0fb6070fb61629d0c3', True),
                                  ('83d00029c0c3', False)):
            reason = self.proof('', regions=[(caller, 0x1000, [0x1000]),
                (bytes.fromhex(helper), 0x2000, [0x2000])])
            self.assertEqual(reason is None, accepted, reason)
        self.assertIn('helper CALL', self.proof(caller.hex()))

    def test_return_follows_every_source_caller(self):
        # A callee that simply returns must not hide a caller's carry use.
        caller = call(0x2000, 0x1000) + bytes.fromhex('83d00029c0c3')
        self.assertIn('incoming arithmetic flags', self.proof('', entry=0x2000,
            regions=[(caller, 0x1000, [0x1000]), (b'\xc3', 0x2000, [0x2000])]))
        caller = call(0x2000, 0x1000) + bytes.fromhex('29c0c3')
        self.assertIsNone(self.proof('', entry=0x2000,
            regions=[(caller, 0x1000, [0x1000]), (b'\xc3', 0x2000, [0x2000])]))

    def test_only_explicit_terminal_clobber_call_can_end_scope(self):
        raw = (call(0x4000, 0x1000) + b'\xc3').hex()
        self.assertIsNone(self.proof(raw, terminal_calls={0x4000}))
        self.assertIn('helper CALL', self.proof(raw))
        self.assertIn('return continuation', self.proof('c3'))
        # A selected continuation makes this a nested/nonterminal CALL even
        # when its symbol is also used by an outer unlock elsewhere.
        blocks, databases = translator.decode_regions(
            [(bytes.fromhex(raw), 0x1000, [0x1000])], 0, set())
        self.assertIn('helper CALL', prove_flags_dead(
            blocks, databases, 0x1000, terminal_calls={0x4000}))

    def test_indirect_control_cycles_and_budget_fail_closed(self):
        self.assertIn('indirect control', self.proof('ffe0'))
        self.assertIn('cycle retains', self.proof('ebfe'))
        self.assertIn('work budget', self.proof('90909029c0c3', max_visits=2))

    def test_unknown_ir_and_interior_pc_fail_closed(self):
        with patch.object(FlowConstants, 'instruction_plan', return_value=None):
            self.assertIn('no arithmetic-flag proof', self.proof('29c0c3'))
        self.assertIn('not a selected source instruction',
                      self.proof('488b0029c0c3', entry=0x1001))

    def test_crossing_byte_instruction_streams_refuse(self):
        # MOV RAX,[RBX+0xc3c029]; SUB EAX,EAX; RET. A second entry
        # inside MOV's displacement decodes SUB EAX,EAX; RET from the
        # same bytes. Each stream alone defines flags before use, and all
        # instruction starting PCs differ, but their byte ranges overlap.
        raw = bytes.fromhex('488b8329c0c30029c0c3')
        main = (raw, 0x1000, [0x1000])
        alternate = (raw[3:], 0x1003, [0x1003])
        self.assertIsNone(self.proof('', regions=[main]))
        self.assertIsNone(self.proof('', regions=[alternate], entry=0x1003))
        blocks, databases = translator.decode_regions([main, alternate], 0, set())
        starts = [line.offset for block in blocks.values() for line in block.lines]
        self.assertEqual(len(starts), len(set(starts)))
        self.assertIn('overlapping source instructions',
                      prove_flags_dead(blocks, databases, 0x1000))


if __name__ == '__main__':
    unittest.main()
