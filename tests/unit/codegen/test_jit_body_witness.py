"""Guest userspace: execute the actual wrapper with a bounded generated corpus."""

import ctypes
import mmap
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_jit_diagnostics import ROOT, translator
from test_jit_diagnostics import render as render_source

MARKER = b"MOV             Stack_JIT_WITNESS, 1\n"


def render(raw, **kwargs):
    return render_source(raw, body_witness=True, **kwargs)


def run_image(assembly, entries, initialize=None, *, resume=None, context=(0xFEED, 0xBEEF)):
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="kdlock-body-witness-") as directory:
        directory = Path(directory)
        (directory / "asm").mkdir()
        (directory / "asm/jit.S").write_bytes(assembly)
        os.chdir(directory)
        try:
            translator.build_jit_binary()
            binary = (directory / "asm/jit.bin").read_bytes()
        finally:
            os.chdir(previous)
    result = []
    with mmap.mmap(
        -1, len(binary), prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC
    ) as memory:
        memory.write(binary)
        address = ctypes.addressof(ctypes.c_char.from_buffer(memory))
        invoke = ctypes.CFUNCTYPE(
            None, ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong)
        )(address)
        args = (ctypes.c_ulong * 2)()
        for entry in entries:
            regs = (ctypes.c_ulong * 21)()
            stack = (ctypes.c_ulong * 16)()
            stack[8] = 0x4444
            regs[16] = entry
            regs[19] = ctypes.addressof(stack) + 8 * 8
            # Boundary tests seed entry packets without replacing the real wrapper.
            if initialize is not None:
                initialize(regs, stack)
            args[0], args[1] = context
            invoke(regs, args)
            # Optional bounded control bridge keeps the same real wrapper,
            # register packet and virtual stack across generated continuations.
            # Callers must state which native handler behavior they substitute.
            if resume is not None:
                for _ in range(16):
                    if not resume(regs, args, stack):
                        break
                    # The wrapper reuses args for output; each real invocation
                    # supplies the original GS/task inputs again, not exit codes.
                    args[0], args[1] = context
                    invoke(regs, args)
                else:
                    raise AssertionError("generated continuation budget exhausted")
            result.append((list(regs), list(args)))
    return result


class JitBodyWitnessTests(unittest.TestCase):
    def test_default_off_preserves_original_codegen(self):
        plain, _ = render_source("48c7c02a000000c3")
        observed, _ = render("48c7c02a000000c3")
        self.assertEqual(observed.replace(MARKER, b""), plain)
        results = run_image(plain, [0x1000])
        self.assertEqual(results[0][0][10], 42)
        self.assertEqual(results[0][1][1], 0)

    def test_real_wrapper_body_and_dispatch_only(self):
        assembly, _ = render("48c7c02a000000c3")
        results = run_image(assembly, [0x1000, 0x7777, 0x1000])
        self.assertEqual([args[1] for _, args in results], [1, 0, 1])
        self.assertEqual([regs[10] for regs, _ in results], [42, 0, 42])

    def test_direct_dispatch_to_later_block(self):
        assembly, _ = render("eb0048c7c02a000000c3")
        self.assertEqual(assembly.count(MARKER), 2)
        results = run_image(assembly, [0x1000, 0x1002, 0x7777])
        self.assertEqual([args[1] for _, args in results], [1, 1, 0])
        self.assertEqual([regs[10] for regs, _ in results], [42, 42, 0])

    def test_missing_marker_is_not_proof_of_body_execution(self):
        assembly, _ = render("48c7c02a000000c3")
        self.assertIn(MARKER, assembly)
        results = run_image(assembly.replace(MARKER, b""), [0x1000])
        self.assertEqual(results[0][0][10], 42)
        self.assertEqual(results[0][1][1], 0)

    def test_original_call_and_hostcall_continuation(self):
        raw = "e8fb0f000048c7c02a000000c3"
        assembly, _ = render(raw, kernel_symbols={"ktime_get": 0x2000})
        results = run_image(assembly, [0x1000, 0x1005])
        self.assertEqual(results[0][1], [5, 1])
        self.assertEqual(results[0][0][16], 0x2000)
        self.assertEqual(results[1][0][10], 42)
        self.assertEqual(results[1][1][1], 1)
        missing, _ = render(raw)
        self.assertEqual(run_image(missing, [0x1000])[0][1], [1, 1])

    def test_dispatcher_and_exit_tables_do_not_mark_the_body(self):
        assembly, _ = render("e8fb0f0000c3")
        body = assembly.split(b"loc_1000:\n", 1)
        self.assertEqual(len(body), 2)
        self.assertNotIn(MARKER, body[0])
        stub = assembly.split(b"loc_2000:\n", 1)[1]
        self.assertNotIn(MARKER, stub)
        self.assertTrue(re.search(rb"loc_1000:\n" + re.escape(MARKER), assembly))


if __name__ == "__main__":
    unittest.main(verbosity=2)
