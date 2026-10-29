"""Guest-only real decoder/emitter/assembler checks for in-JIT instructions.

Execute only ordinary owned userspace memory. This checks exact instruction
presence and sequential effects, not a weak-memory or kernel contention proof.
"""
import ctypes
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_jit_diagnostics import decode, render, translator
from test_jit_body_witness import run_image
from test_rip_relative_codegen import machine_code


def disassemble_image(assembly):
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="kd-pause-ordering-") as name:
        path = Path(name)
        (path / "asm").mkdir()
        (path / "asm/jit.S").write_bytes(assembly)
        try:
            os.chdir(path)
            translator.build_jit_binary(0, context_inputs=(False, False), requirements=0)
            result = subprocess.run(
                ["objdump", "-D", "-b", "binary", "-m", "i386:x86-64", "-Mintel",
                 "asm/jit.bin"], check=True, capture_output=True, text=True, timeout=15)
        finally:
            os.chdir(previous)
    return result.stdout


class PauseOrderingTests(unittest.TestCase):
    def test_exact_pause_alias_and_other_nops(self):
        line = decode("f390")
        self.assertEqual(line.name, "NOP")  # The pinned dependency's actual alias.
        self.assertEqual((line.l, bytes(line.b)), (2, b"\xf3\x90"))
        for raw, expected in (("f390", 1), ("90", 0), ("6690", 0), ("0f1f00", 0)):
            with self.subTest(source=raw):
                assembly, log, status = render(raw + "c3", trusted_source=True,
                                               return_status=True)
                self.assertEqual(status, 0, log)
                self.assertEqual(len(re.findall(r"\bpause\b", disassemble_image(assembly))), expected)

    def test_loop_fences_and_locked_operations_remain_in_generated_code(self):
        source = machine_code("""
            mov ecx, 3
        retry:
            pause
            dec ecx
            jne retry
            lfence
            mfence
            sfence
            mov eax, 5
            lock xadd QWORD PTR [rbp], rax
            mov QWORD PTR [rbp + 8], rax
            mov eax, 12
            mov edx, 19
            lock cmpxchg QWORD PTR [rbp], rdx
            sete BYTE PTR [rbp + 16]
            cmp eax, 13
            pause
            setb BYTE PTR [rbp + 17]
            ret
        """)
        # Both modes use the same backend. Production trust must not turn a
        # spin hint, fence or LOCK prefix into a native marker or a no-op.
        for trusted in (False, True):
            with self.subTest(trusted_source=trusted):
                options = {}
                assembly, log, status = render(source.hex(), trusted_source=trusted,
                    body_witness=True, build_options=options, return_status=True)
                self.assertEqual(status, 0, log)
                self.assertEqual(options.get("requirements", 0), 0)
                emitted = disassemble_image(assembly)
                self.assertEqual(len(re.findall(r"\bpause\b", emitted)), 2)
                for instruction in ("lfence", "mfence", "sfence"):
                    self.assertEqual(len(re.findall(r"\b" + instruction + r"\b", emitted)), 1)
                for instruction in ("xadd", "cmpxchg"):
                    self.assertEqual(len(re.findall(r"\block\s+" + instruction + r"\b", emitted)), 1)
                # Instruction order is independently visible in the final
                # machine image; executing it then checks flags/old values.
                positions = [emitted.index(text) for text in
                             ("lfence", "mfence", "sfence", "lock xadd", "lock cmpxchg")]
                self.assertEqual(positions, sorted(positions))
                memory = (ctypes.c_ulong * 4)(7, 0, 0, 0)

                def initialize(regs, stack):
                    regs[2] = ctypes.addressof(memory)

                regs, args = run_image(assembly, [0x1000], initialize=initialize)[0]
                self.assertEqual(list(memory), [19, 7, 0x101, 0])
                self.assertEqual(regs[0], 0x4444)
                self.assertEqual(args[1], 1)
                self.assertNotIn(args[0], (1, 3, 4, 5, 8))


if __name__ == "__main__":
    unittest.main(verbosity=2)
