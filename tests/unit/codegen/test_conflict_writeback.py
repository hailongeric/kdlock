"""Guest-only: execute clean/dirty virtual-register spills through the wrapper.

Tests cover the hash loop's read-only key, ordinary/partial writes, and scratch
pressure that borrows SP/BP. Unknown operand roles must retain safe write-back.
"""
import ctypes
import re
import unittest

from test_jit_diagnostics import conflict, normal
from test_jit_body_witness import run_image
from miasm.arch.x86.arch import mn_x86
from miasm.core.locationdb import LocationDB


def lower(*blocks):
    assembly = ""
    for instructions in blocks:
        mapping = conflict.block_init()
        for source in instructions:
            line = mn_x86.fromstring(source, loc_db=LocationDB(), mode=64)
            assembly += normal.process_normal(line.name, line.args, 0x1000, mapping)
        assembly += conflict.release_conflict(mapping)
    return assembly


def stores(assembly, register):
    return len(re.findall(r"MOV\s+Stack_" + register + r"\s*,", assembly))


def execute(assembly, initialize):
    assembly += "MOV R14, 0x4444\nMOV Stack_IJ, 0\nJMP exit\n"
    return run_image(assembly.encode(), [0x1000], initialize)[0][0]


class ConflictWritebackTests(unittest.TestCase):
    def test_readonly_key_and_address_do_not_write_packet(self):
        assembly = lower([
            "MOV RAX, R11", "CMP RAX, R11", "TEST R12, R12",
            "LEA RDX, QWORD PTR [R11 + R12]",
        ])
        self.assertEqual(stores(assembly, "R11"), 0)
        self.assertEqual(stores(assembly, "R12"), 0)

        def initialize(regs, stack):
            regs[7], regs[6] = 0x123456789abc, 37

        regs = execute(assembly, initialize)
        self.assertEqual(regs[7], 0x123456789abc)
        self.assertEqual(regs[6], 37)
        self.assertEqual(regs[12], regs[7])
        self.assertEqual(regs[14], regs[7] + 37)

    def test_memory_store_keeps_source_and_address_readonly(self):
        word = ctypes.c_ulong()
        assembly = lower([
            "MOV QWORD PTR [R11], R12", "CMP R12, QWORD PTR [R11]",
        ])
        self.assertEqual(stores(assembly, "R11"), 0)
        self.assertEqual(stores(assembly, "R12"), 0)

        def initialize(regs, stack):
            regs[7], regs[6] = ctypes.addressof(word), 0x123456789abcdef

        regs = execute(assembly, initialize)
        self.assertEqual(word.value, 0x123456789abcdef)
        self.assertEqual(regs[7], ctypes.addressof(word))
        self.assertEqual(regs[6], word.value)

    def test_partial_writes_flush_full_logical_values(self):
        assembly = lower([
            "MOV R11W, 0x5678", "MOV R12D, 42", "MOV R13B, 0x9a",
        ])
        for register in ("R11", "R12", "R13"):
            self.assertGreater(stores(assembly, register), 0)

        def initialize(regs, stack):
            regs[7], regs[6], regs[5] = (0xabcdef1234000000,
                                       0xffffffffffffffff, 0x12345600)

        regs = execute(assembly, initialize)
        self.assertEqual(regs[7], 0xabcdef1234005678)
        self.assertEqual(regs[6], 42)
        self.assertEqual(regs[5], 0x1234569a)

    def test_unknown_operand_roles_flush_both_written_operands(self):
        assembly = lower(["XCHG R11, R12", "XADD R13, R14"])

        def initialize(regs, stack):
            regs[7], regs[6], regs[5], regs[4] = 11, 12, 13, 14

        regs = execute(assembly, initialize)
        self.assertEqual([regs[7], regs[6], regs[5], regs[4]], [12, 11, 27, 13])

    def test_pressure_spills_dirty_destination_and_recovers_stack(self):
        words = (ctypes.c_ulong * 2)(7, 0x123456789abcdef)
        assembly = lower([
            "MOV R14, QWORD PTR [R11 + R12]",
            "MOV R13, RSP", "MOV R15, RBP",
        ])
        self.assertEqual(stores(assembly, "R11"), 0)
        self.assertEqual(stores(assembly, "R12"), 0)
        self.assertGreater(stores(assembly, "R14"), 0)
        original_stack = []

        def initialize(regs, stack):
            regs[7], regs[6], regs[2] = ctypes.addressof(words), 8, 0x8000
            original_stack.append(regs[1])

        regs = execute(assembly, initialize)
        self.assertEqual(regs[4], words[1])
        self.assertEqual(regs[7], ctypes.addressof(words))
        self.assertEqual(regs[6], 8)
        self.assertEqual(regs[5], original_stack[0])
        self.assertEqual(regs[1], original_stack[0])
        self.assertEqual(regs[3], 0x8000)
        self.assertEqual(regs[2], 0x8000)

    def test_successor_reloads_committed_value_with_fresh_dirty_state(self):
        assembly = lower(["MOV R11, 99"],
                         ["MOV RAX, R11", "CMP R11, 99"])
        self.assertEqual(stores(assembly, "R11"), 1)

        def initialize(regs, stack):
            regs[7] = 17

        regs = execute(assembly, initialize)
        self.assertEqual(regs[7], 99)
        self.assertEqual(regs[12], 99)


if __name__ == "__main__":
    unittest.main(verbosity=2)
