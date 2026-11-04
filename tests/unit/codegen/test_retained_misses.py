"""Execute original generated miss packets; no provider or kernel module load."""
import unittest

from test_jit_diagnostics import translator
from test_jit_body_witness import run_image


class RetainedMissTests(unittest.TestCase):
    @staticmethod
    def emit(raw):
        blocks, databases = translator.decode_regions(
            [(bytes.fromhex(raw), 0x1000, [0x1000])], 0, set())
        table = {}
        missing = translator.indirect_jump.find(blocks, databases, table)
        return translator.emit_jit_assembly(
            0x1000, blocks, databases, table, missing, {}, set(),
            body_witness=True, trusted_source=True, retained_misses=True).encode()

    def test_return_exports_post_pop_target_and_source_flags(self):
        # XOR sets ZF, STC sets CF; RET itself preserves both.
        code = self.emit('31c0f9c3')
        before = []
        def initialize(regs, stack):
            before.append(regs[1])
        regs, result = run_image(code, [0x1000], initialize=initialize)[0]
        self.assertEqual(result, [15, 1])
        self.assertEqual(regs[0], 0x4444)
        self.assertEqual(regs[1], before[0] + 8)
        self.assertEqual(regs[17], 0x1004)  # source next-PC, not target or CALL
        self.assertEqual(regs[19] & 0x41, 0x41)

    def test_direct_missing_call_keeps_pushed_word_and_flags(self):
        code = self.emit('31c0f9e8f80f0000c3')
        before = []
        def initialize(regs, stack):
            before.append((regs[1], stack))
        regs, result = run_image(code, [0x1000], initialize=initialize)[0]
        self.assertEqual(result, [1, 1])
        self.assertEqual(regs[0], 0x2000)
        self.assertEqual(regs[1], before[0][0] - 8)
        self.assertEqual(before[0][1][7], 0x1008)
        self.assertEqual(regs[19] & 0x41, 0x41)

    def test_generic_jump_keeps_stack_and_exports_actual_edge(self):
        code = self.emit('b80020000031c9f9ffe0')
        before = []
        regs, result = run_image(code, [0x1000],
            initialize=lambda regs, stack: before.append(regs[1]))[0]
        self.assertEqual(result, [15, 1])
        self.assertEqual(regs[0], 0x2000)
        self.assertEqual(regs[1], before[0])
        self.assertEqual(regs[17], 0x100a)
        self.assertEqual(regs[19] & 0x41, 0x41)


if __name__ == '__main__':
    unittest.main(verbosity=2)
