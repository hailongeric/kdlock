"""Execute shared spill backing and real allocator/continuation code in guest.

The packet is observed before epilogue, so a copied wrapper stack cannot pass.
No kernel modules are loaded by this test. Live tests cover ownership handoff.
"""
import ctypes
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

from test_jit_body_witness import render, run_image


def source_bytes(source):
    with tempfile.TemporaryDirectory(prefix="kd-bank-source-") as directory:
        path = Path(directory)
        (path / "source.S").write_text(".intel_syntax noprefix\n.text\n" + source)
        subprocess.run(shlex.split(os.environ.get("CC", "gcc")) + [
            "-c", str(path / "source.S"), "-o", str(path / "source.o")],
            check=True, timeout=30)
        subprocess.run(["objcopy", "-O", "binary", "-j", ".text",
                        str(path / "source.o"), str(path / "source.bin")],
                       check=True, timeout=30)
        return (path / "source.bin").read_bytes().hex()


class SharedRegisterBankTests(unittest.TestCase):
    def test_aliases_in_both_directions_before_exit(self):
        # A real wrapper invocation must expose each write immediately through
        # the other addressing form. Failure traps before any export can hide it.
        slots = {"R15": 0, "R14": 8, "R13": 16, "R12": 24,
                 "RBP": 32, "R11": 48, "RSP": 152}
        body = ["cmp REG_BANK, Stack_PT_REG", "jne bad_bank"]
        for name, offset in slots.items():
            body += [f"mov Stack_{name}, {0x100 + offset}",
                     f"cmp QWORD PTR[REG_BANK + {offset}], {0x100 + offset}",
                     "jne bad_bank", f"mov QWORD PTR[REG_BANK + {offset}], {0x200 + offset}",
                     f"cmp Stack_{name}, {0x200 + offset}", "jne bad_bank"]
        body += ["mov Stack_JIT_WITNESS, 1", "mov Stack_IJ, 5",
                 "mov R14, 0x2000", "jmp exit", "bad_bank: ud2"]
        regs, args = run_image(("\n".join(body) + "\n").encode(), [0x1000])[0]
        for name, offset in slots.items():
            if name not in ("RSP", "RBP"):
                self.assertEqual(regs[offset // 8], 0x200 + offset)
        self.assertEqual(args, [5, 1])

    def test_allocator_pressure_partial_registers_and_hostcall_resume(self):
        # Three simultaneous virtual operands evict SP/BP from the four-slot
        # pool. Then partial logical R11 updates must not damage physical R11.
        raw = source_bytes("""
            mov r12, rsp
            mov r13, 8
            mov r14, 0x1234
            mov [r12 + r13], r14
            mov r11, 0x12340000
            mov r11w, 0x5678
            mov r15, r11
            mov r11b, 0x9a
            mov r14, [r12 + r13]
            mov r12, 17
            mov r13, 19
            mov r8, rbp
            .byte 0xe8
            .long 0x51525354
            add r11, rax
            add r12, r13
            add r15, r14
            ret
        """)
        # Replace the entire unique placeholder, not an arbitrary 0xe8 byte
        # (that byte can also be a ModRM operand). No linker relocation is used.
        call_at = bytes.fromhex(raw).index(b"\xe8\x54\x53\x52\x51")
        native = bytearray.fromhex(raw)
        native[call_at + 1:call_at + 5] = (0x2000 - (0x1000 + call_at + 5)).to_bytes(4, "little", signed=True)
        assembly, log, status = render(native.hex(), kernel_symbols={"ktime_get": 0x2000}, return_status=True)
        self.assertEqual(status, 0, log)
        seen = []
        stack_refs = []

        def initialize(regs, stack):
            regs[4] = 0x8000
            stack_refs.append(stack)

        def resume(regs, args, stack):
            if args[0] != 5:
                return False
            self.assertFalse(seen, "hostcall prefix replayed")
            seen.append(1)
            self.assertEqual(regs[0:4], [0x12345678, 0x1234, 19, 17])
            self.assertEqual(regs[6], 0x1234569a)
            self.assertEqual(regs[9], 0x8000)
            self.assertEqual(stack[9], 0x1234)
            self.assertEqual(regs[19], ctypes.addressof(stack) + 7 * 8)
            self.assertEqual(stack[7], 0x1000 + call_at + 5)
            # Substitute only the typed hostcall's result/virtual return.
            regs[10], regs[16], regs[19] = 42, stack[7], regs[19] + 8
            return True

        regs, args = run_image(assembly, [0x1000], initialize, resume=resume)[0]
        self.assertEqual(seen, [1])
        self.assertEqual(regs[6], 0x1234569a + 42)
        self.assertEqual(regs[3], 36)
        self.assertEqual(regs[0], 0x12345678 + 0x1234)
        self.assertEqual(regs[4], 0x8000)
        self.assertEqual(regs[19], ctypes.addressof(stack_refs[0]) + 9 * 8)
        self.assertEqual(args[1], 1)

    def test_budget_exit_keeps_bank_and_logical_r11(self):
        assembly, log, status = render("4883f800750190c3", return_status=True)
        self.assertEqual(status, 0, log)
        self.assertIn(b"INC             Stack_BUDGET", assembly)
        # Exercise the exact overflow edge without spending 2**24 iterations.
        assembly = assembly.replace(b"MOV     Stack_BUDGET, 0\n",
                                    b"MOV     Stack_BUDGET, 0xffffff\n")

        def initialize(regs, _):
            regs[6] = 0xabcdef0123456789

        regs, args = run_image(assembly, [0x1000], initialize)[0]
        self.assertEqual(args, [4, 1])
        self.assertEqual(regs[16], 0x1000)
        self.assertEqual(regs[6], 0xabcdef0123456789)


if __name__ == "__main__":
    unittest.main(verbosity=2)
