"""Guest-only source flags-stack execution through the production wrapper.

These fixtures check executor flags, virtual stack words, physical stack balance
and live GPRs. They do not load a kernel provider or compare task contexts.
"""
import ctypes
import mmap
import unittest

from test_jit_diagnostics import decode, render
from test_jit_body_witness import run_image
from test_ordinary_callee_bytes import source_bytes
import conflict
import instruction_policy
import special_inst
from miasm.core.locationdb import LocationDB


ARITHMETIC = 0x8D5
ADD_FLAGS = 0x890
SYMBOLS = {"kd_raw_spin_lock_clobber_v1": 0x6000,
           "kd_raw_spin_unlock_clobber_v1": 0x7000}


def native_push_width(raw):
    # Preserve/restore physical SP around the one original PUSHF encoding.
    # RDX and RAX are ordinary caller-clobbered registers in this fixture.
    code = (bytes.fromhex("4889e2") + raw +
            bytes.fromhex("4889d04829e04889d4c3"))
    with mmap.mmap(-1, len(code), prot=mmap.PROT_READ | mmap.PROT_WRITE |
                   mmap.PROT_EXEC) as memory:
        memory.write(code)
        address = ctypes.addressof(ctypes.c_char.from_buffer(memory))
        return ctypes.CFUNCTYPE(ctypes.c_ulong)(address)()


class FlagsStackTests(unittest.TestCase):
    def generate(self, source, *, trusted=True, abi=1):
        regions, _ = source_bytes(source)
        options = {}
        assembly, log, status = render(
            "", regions=regions, abi=abi, trusted_source=trusted,
            body_witness=True, kernel_symbols=SYMBOLS,
            build_options=options, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertEqual(options["requirements"], 0)
        self.assertNotIn("ORIGIN_INSTRUCTION_SERVICE", log)
        self.assertNotIn("NATIVE_ESCAPE_MARKER", log)
        return assembly

    def execute(self, assembly, *, abi=1):
        captures = []

        def initialize(regs, stack):
            for index in range(8):
                stack[index] = 0xA1B2C3D4E5F60718
            captures.append((regs[1], stack))

        regs, args = run_image(assembly, [0x1000], initialize, abi=abi)[0]
        initial_sp, stack = captures[0]
        self.assertEqual(regs[0], 0x4444)
        self.assertEqual(regs[1], initial_sp + 8)
        self.assertEqual(args[1], 1)
        self.assertEqual(stack[8], 0x4444)
        return regs, stack, initial_sp

    def test_pushfq_uses_virtual_word_and_preserves_live_registers(self):
        assembly = self.generate("""
            mov rdx, rsp
            mov r11, 0x1111
            mov r12, 0x2222
            mov r13, 0x3333
            mov r14, 0x4444
            mov r15, 0x5555
            mov eax, 127
            add al, 1
            pushfq
            mov rbx, qword ptr [rsp]
            pop rax
            pushfq
            pop rcx
            ret
        """)
        regs, stack, initial_sp = self.execute(assembly)
        for index in (8, 12, 13):
            self.assertEqual(regs[index] & ARITHMETIC, ADD_FLAGS)
        self.assertEqual(regs[14], initial_sp)
        self.assertEqual(stack[7], regs[12])
        self.assertEqual(regs[3:8], [0x5555, 0x4444, 0x3333, 0x2222, 0x1111])

    def test_popfq_restores_source_arithmetic_flags(self):
        for expected in (0, ARITHMETIC, 1, 0x40, 0x800, ADD_FLAGS):
            with self.subTest(flags=hex(expected)):
                assembly = self.generate(f"""
                    pushfq
                    pop rax
                    and rax, {-1 ^ ARITHMETIC}
                    or rax, {expected}
                    push rax
                    popfq
                    setc bl
                    seto cl
                    sets dl
                    setz sil
                    setp dil
                    pushfq
                    pop rax
                    ret
                """)
                regs, _, _ = self.execute(assembly)
                self.assertEqual(regs[12] & ARITHMETIC, expected)
                for index, bit in ((8, 1), (13, 0x800), (14, 0x80),
                                   (15, 0x40), (16, 4)):
                    self.assertEqual(regs[index] & 0xFF, int(bool(expected & bit)))

    def test_word_forms_have_two_byte_virtual_stack_effect(self):
        assembly = self.generate("""
            mov rdx, rsp
            mov eax, 127
            add al, 1
            pushfw
            mov bx, word ptr [rsp]
            xor eax, eax
            popfw
            mov rcx, rsp
            pushfq
            pop rax
            ret
        """)
        regs, _, initial_sp = self.execute(assembly)
        self.assertEqual(regs[8] & ARITHMETIC, ADD_FLAGS)
        self.assertEqual(regs[12] & ARITHMETIC, ADD_FLAGS)
        self.assertEqual(regs[13], initial_sp)
        self.assertEqual(regs[14], initial_sp)

    def test_push_width_matches_original_encoding(self):
        for encoded in ("9c", "669c", "489c", "66489c"):
            with self.subTest(encoded=encoded):
                raw = bytes.fromhex(encoded)
                width = native_push_width(raw)
                self.assertIn(width, (2, 8))
                directive = ", ".join(hex(byte) for byte in raw)
                assembly = self.generate(f"""
                    mov rdx, rsp
                    .byte {directive}
                    mov rax, rdx
                    sub rax, rsp
                    lea rsp, [rsp + {width}]
                    ret
                """)
                regs, stack, _ = self.execute(assembly)
                self.assertEqual(regs[12], width)
                if width == 2:
                    self.assertEqual(stack[7] & ((1 << 48) - 1),
                                     0xA1B2C3D4E5F60718 & ((1 << 48) - 1))

    def test_flags_survive_nested_call_and_block_dispatch(self):
        assembly = self.generate("""
            mov eax, 127
            add al, 1
            pushfq
            call helper
            popfq
            jo restored
            mov eax, 99
            ret
        restored:
            mov eax, 42
            ret
        helper:
            pushfq
            xor eax, eax
            popfq
            ret
        """)
        regs, _, _ = self.execute(assembly)
        self.assertEqual(regs[12], 42)

    def test_instruction_policy_and_checked_coordinator_accept_family(self):
        for raw in ("9c", "669c", "9d", "669d"):
            with self.subTest(raw=raw):
                line = decode(raw)
                self.assertIsNone(instruction_policy.rejection(line))
                mapping = conflict.block_init()
                lowered = special_inst.translate(line, line.l, LocationDB(), mapping, False)
                self.assertIn("R13", lowered)
        for abi in (0, 1):
            with self.subTest(checked_abi=abi):
                assembly = self.generate("pushfq\npopfq\nret", trusted=False, abi=abi)
                self.execute(assembly, abi=abi)


if __name__ == "__main__":
    unittest.main()
