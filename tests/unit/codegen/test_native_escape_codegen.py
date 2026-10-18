"""Guest-only execution of generated prefixes and the real FULL wrapper exit.

The special source instruction is replaced, so privileged fixture instructions
never execute here. Kernel waiter restoration and lock ownership need live probes.
"""
import ctypes
import io
import unittest

from test_jit_diagnostics import render
from test_jit_body_witness import run_image
from test_rip_relative_codegen import machine_code
from test_instruction_policy import SYMBOLS
import conflict
import indirect_jump
import special_inst
from translation_image import write_entry_dispatch
from test_jit_diagnostics import decode


def compile_marker(source):
    raw = machine_code(source)
    assembly, log, status = render(raw.hex(), lock_kind="mutex", abi=2,
        kernel_symbols=SYMBOLS, native_escape_capable=True, body_witness=True,
        return_status=True)
    if status:
        raise AssertionError(log)
    return raw, assembly


def execute(assembly, initialize=None):
    return run_image(assembly, [0x1000], initialize=initialize,
                     abi=2, requirements=1)[0]


class NativeEscapeCodegenTests(unittest.TestCase):
    def test_flags_cross_branch_budget_reserved_registers_and_lea_rewrite(self):
        raw, assembly = compile_marker("""
            mov eax, 1
            mov r11, 0x1100
            mov r12, 0x1200
            mov r14, 0x1400
            mov r15, 0x1500
            cmp eax, 2
            jmp next
        next:
            lea r13, [r12 + r14]
            jmp marker
        marker:
            rdtsc
            ret
        """)
        registers, args = execute(assembly)
        self.assertEqual(args, [8, 1])
        self.assertEqual(registers[0], 0x1000 + raw.index(b"\x0f\x31"))
        self.assertEqual(registers[19] & 0x8d5, 0x95)
        self.assertEqual(registers[12], 1)  # RDTSC has not overwritten EAX.
        self.assertEqual(registers[7], 0x1100)
        self.assertEqual(registers[6], 0x1200)
        self.assertEqual(registers[5], 0x2600)
        self.assertEqual(registers[4], 0x1400)
        self.assertEqual(registers[3], 0x1500)

    def test_mutable_cold_branch_and_exactly_once_prefix_stores(self):
        raw, assembly = compile_marker("""
            mov rax, [rbp]
            add QWORD PTR[rbp + 8], 1
            cmp rax, 0
            je cold
            mov eax, 1
            cmp eax, 2
            jmp boundary
        boundary:
            jmp marker
        marker:
            rdtsc
            mov eax, 99
            ret
        cold:
            mov eax, 42
            ret
        """)
        for value in (0, 1):
            with self.subTest(hot=value):
                memory = (ctypes.c_ulong * 2)(value, 0)
                stack_before = []
                def initialize(registers, stack):
                    registers[2] = ctypes.addressof(memory)
                    stack_before.append(registers[1])
                registers, args = execute(assembly, initialize)
                self.assertEqual(memory[1], 1)
                self.assertEqual(args[1], 1)
                if value:
                    self.assertEqual(args[0], 8)
                    self.assertEqual(registers[0], 0x1000 + raw.index(b"\x0f\x31"))
                    self.assertEqual(registers[1], stack_before[0])
                    self.assertEqual(registers[12], 1)
                    self.assertEqual(registers[19] & 0x8d5, 0x95)
                else:
                    self.assertNotEqual(args[0], 8)
                    self.assertEqual(registers[12], 42)
                    self.assertEqual(registers[1], stack_before[0] + 8)

    def test_indirect_dispatch_and_entry_dispatch_preserve_arithmetic_flags(self):
        # Exercise the production dispatch emitter with one valid source marker.
        # Assembly substitutes only entry dispatch to make flags live across it;
        # production ABI2 admission forbids undefined flags at the real root.
        marker = decode("0f31")
        marker.offset = 0x2000
        output = io.StringIO()
        write_entry_dispatch(output, 0x1000, {0x1000: None}, preserve_flags=True)
        prefix = "MOV EAX, 1\nCMP EAX, 2\n" + output.getvalue()
        prefix += "loc_1000:\nMOV R14, 0x2000\nJMP ij_1234\n"
        table = indirect_jump.make_jump_table({0x1234: [0x2000]}, preserve_flags=True)
        body = "loc_2000:\n" + special_inst.native_escape_marker(marker, conflict.block_init())
        registers, args = execute((prefix + table + body).encode())
        self.assertEqual(args[0], 8)
        self.assertEqual(registers[12], 1)
        self.assertEqual(registers[19] & 0x8d5, 0x95)

    def test_budget_expiry_stays_a_nonresumable_budget_exit(self):
        _, assembly = compile_marker("""
            mov eax, 1
            cmp eax, 2
            jmp next
        next:
            jmp marker
        marker:
            rdtsc
            ret
        """)
        assembly = assembly.replace(b"MOV     Stack_BUDGET, 0x1000000\n",
                                    b"MOV     Stack_BUDGET, 1\n")
        registers, args = execute(assembly)
        self.assertEqual(args, [4, 1])
        self.assertEqual(registers[0], 0x1000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
