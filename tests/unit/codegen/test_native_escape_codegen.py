"""Guest-only execution of generated prefixes and the real FULL wrapper exit.

The special source instruction is replaced, so privileged fixture instructions
never execute here. Kernel waiter restoration and lock ownership need live probes.
"""
import ctypes
import io
import mmap
import os
from pathlib import Path
import tempfile
import unittest

from test_jit_diagnostics import render, translator
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


def execute_root(assembly, abi, *, entry=0x1000, initialize=None, directory=32):
    """Invoke the actual minimal wrapper through ordinary-C-ABI fixture glue.

    This supplies only the documented batch-call metadata, not a kernel frame,
    ticket or owner. The source instruction never executes in these tests.
    """
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="kd-root-marker-") as name:
        path = Path(name)
        (path / "asm").mkdir()
        (path / "asm/jit.S").write_bytes(assembly)
        try:
            os.chdir(path)
            translator.build_jit_binary(abi, context_inputs=(False, False),
                                        requirements=33)
            binary = (path / "asm/jit.bin").read_bytes()
        finally:
            os.chdir(previous)
    # Save SysV callee-saved values around the clobber-all directory. RDI/RSI/
    # RDX already carry regs/args/metadata; code is metadata's fourth word.
    trampoline = bytes.fromhex(
        "555341544155415641574883ec08488b4218ffd04883c408415f415e415d415c5b5dc3")
    protection = mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC
    with mmap.mmap(-1, len(binary), prot=protection) as image, \
            mmap.mmap(-1, len(trampoline), prot=protection) as bridge:
        image.write(binary)
        bridge.write(trampoline)
        image_address = ctypes.addressof(ctypes.c_char.from_buffer(image))
        invoke = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_void_p)(
            ctypes.addressof(ctypes.c_char.from_buffer(bridge)))
        regs = (ctypes.c_ulong * 21)()
        stack = (ctypes.c_ulong * 16)()
        stack[8] = 0x4444
        regs[0], regs[1] = entry, ctypes.addressof(stack) + 64
        if initialize:
            initialize(regs, stack)
        state = ctypes.c_uint(1)  # KD_PACKET_MINIMAL
        call = (ctypes.c_ulong * 14)()
        call[0] = ctypes.addressof(regs)
        call[1], call[2] = 0xFEED, 0xBEEF
        call[3] = image_address + directory
        call[4], call[5] = 0x6000, SYMBOLS["kd_spin_unlock_clobber_v1"]
        call[6], call[9] = regs[1], abi
        call[10], call[11] = ctypes.addressof(state), 1
        invoke(ctypes.addressof(regs), ctypes.addressof(call) + 8,
               ctypes.addressof(call))
        return list(regs), [call[1], call[2]], state.value


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


class RootNativeEscapeCodegenTests(unittest.TestCase):
    def compile(self, source, abi):
        raw = machine_code(source)
        options = {}
        assembly, log, status = render(
            raw.hex(), lock_kind="spin", abi=abi, kernel_symbols=SYMBOLS,
            root_native_escape_capable=True, body_witness=True,
            build_options=options, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertEqual(options["requirements"], 33)
        return raw, assembly

    def test_actual_clobber_packet_preserves_flags_and_exactly_once_prefix(self):
        for abi in (1, 3):
            raw, assembly = self.compile("""
                mov rax, [rbp]
                add QWORD PTR[rbp + 8], 1
                cmp rax, 0
                je cold
                mov r11, 0x1100
                mov r12, 0x1200
                mov r14, 0x1400
                mov r15, 0x1500
                mov eax, 1
                cmp eax, 2
                jmp next
            next:
                lea r13, [r12 + r14]
                jmp marker
            marker:
                rdtsc
                mov eax, 99
                ret
            cold:
                mov eax, 42
                ret
            """, abi)
            for hot in (0, 1):
                with self.subTest(abi=abi, hot=hot):
                    memory = (ctypes.c_ulong * 2)(hot, 0)
                    before = []
                    def initialize(regs, stack):
                        regs[2] = ctypes.addressof(memory)
                        before.append(regs[1])
                    regs, args, state = execute_root(
                        assembly, abi, initialize=initialize)
                    self.assertEqual(memory[1], 1)
                    self.assertEqual((args[1], state), (1, 0))
                    if hot:
                        self.assertEqual(args[0], 8)
                        self.assertEqual(regs[0], 0x1000 + raw.index(b"\x0f\x31"))
                        self.assertEqual(regs[1], before[0])
                        self.assertEqual(regs[5], 0x2600)
                        self.assertEqual(regs[12], 1)
                        self.assertEqual(regs[19] & 0x8d5, 0x95)
                        self.assertEqual(regs[7], 0x1100)
                        self.assertEqual(regs[6], 0x1200)
                        self.assertEqual(regs[4], 0x1400)
                        self.assertEqual(regs[3], 0x1500)
                    else:
                        self.assertNotEqual(args[0], 8)
                        self.assertEqual(regs[12], 42)
                        self.assertEqual(regs[1], before[0] + 8)

    def test_only_root_minimal_directory_can_execute_body(self):
        for abi in (1, 3):
            raw, assembly = self.compile("""
                add QWORD PTR[rbp], 1
                mov eax, 1
                cmp eax, 2
                jmp marker
            marker:
                rdtsc
                ret
            """, abi)
            for directory, entry in (
                    (0, 0x1000), (16, 0x1000),
                    (32, 0x1000 + raw.index(b"\x0f\x31")), (32, 0x7777)):
                with self.subTest(abi=abi, directory=directory, entry=entry):
                    memory = ctypes.c_ulong()
                    def initialize(regs, stack):
                        regs[2] = ctypes.addressof(memory)
                    _, args, state = execute_root(
                        assembly, abi, directory=directory, entry=entry,
                        initialize=initialize)
                    self.assertEqual(memory.value, 0)
                    self.assertEqual(args, [6 if directory != 32 else 2, 0])
                    self.assertEqual(state, 1 if directory != 32 else 0)

    def test_budget_exit_does_not_become_an_instruction_marker(self):
        for abi in (1, 3):
            _, assembly = self.compile("""
                mov eax, 1
                cmp eax, 2
                jmp next
            next:
                jmp marker
            marker:
                rdtsc
                ret
            """, abi)
            bounded = assembly.replace(b"MOV     Stack_BUDGET, 0x1000000\n",
                                       b"MOV     Stack_BUDGET, 1\n")
            regs, args, state = execute_root(bounded, abi)
            self.assertEqual((args, state), ([4, 1], 0))
            self.assertEqual(regs[0], 0x1000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
