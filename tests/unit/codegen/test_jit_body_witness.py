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
            translator.build_jit_binary(context_inputs=
                translator.wrapper_context_inputs(assembly.decode()))
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
            regs[0] = entry
            regs[1] = ctypes.addressof(stack) + 8 * 8
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
        # Witnesses belong to valid entry stubs; source blocks stay identical
        # whether observation is enabled or disabled.
        without_stubs = re.sub(
            rb"kd_body_entry_([0-9a-f]+):\n" + re.escape(MARKER)
            + rb"JMP     loc_\1\n", b"", observed,
        ).replace(b"JZ      kd_body_entry_", b"JZ      loc_")
        self.assertEqual(without_stubs, plain)
        results = run_image(plain, [0x1000])
        self.assertEqual(results[0][0][12], 42)
        self.assertEqual(results[0][1][1], 0)

    def test_real_wrapper_body_and_dispatch_only(self):
        assembly, _ = render("48c7c02a000000c3")
        results = run_image(assembly, [0x1000, 0x7777, 0x1000])
        self.assertEqual([args[1] for _, args in results], [1, 0, 1])
        self.assertEqual([regs[12] for regs, _ in results], [42, 0, 42])

    def test_direct_dispatch_to_later_block(self):
        assembly, _ = render("eb0048c7c02a000000c3")
        self.assertEqual(assembly.count(MARKER), 2)
        results = run_image(assembly, [0x1000, 0x1002, 0x7777])
        self.assertEqual([args[1] for _, args in results], [1, 1, 0])
        self.assertEqual([regs[12] for regs, _ in results], [42, 42, 0])

    def test_missing_marker_is_not_proof_of_body_execution(self):
        assembly, _ = render("48c7c02a000000c3")
        self.assertIn(MARKER, assembly)
        results = run_image(assembly.replace(MARKER, b""), [0x1000])
        self.assertEqual(results[0][0][12], 42)
        self.assertEqual(results[0][1][1], 0)

    def test_original_call_and_hostcall_continuation(self):
        raw = "e8fb0f000048c7c02a000000c3"
        for symbols, reason in (({"ktime_get": 0x2000}, 5), ({}, 1)):
            with self.subTest(exit_reason=reason):
                assembly, _ = render(raw, kernel_symbols=symbols)
                packets = []

                def capture_stack(regs, stack):
                    packets.append((regs[1], stack))

                # Only admitted hostcalls retain a JIT continuation; an
                # ordinary missing callee continues on the original waiter.
                entries = [0x1000, 0x1005] if reason == 5 else [0x1000]
                results = run_image(assembly, entries, initialize=capture_stack)
                self.assertEqual(results[0][1], [reason, 1])
                self.assertEqual(results[0][0][0], 0x2000)
                # Both callee exits export the pushed virtual SP and preserve
                # the source CALL's return word for native/hostcall resumption.
                self.assertEqual(results[0][0][1], packets[0][0] - 8)
                self.assertEqual(packets[0][1][7], 0x1005)
                self.assertEqual(packets[0][1][8], 0x4444)
                if reason == 5:
                    self.assertEqual(results[1][0][12], 42)
                    self.assertEqual(results[1][0][1], packets[1][0] + 8)
                    self.assertEqual(results[1][1][1], 1)

    def test_only_valid_dispatch_stubs_mark_the_body(self):
        assembly, _ = render("e8fb0f0000c3")
        body = assembly.split(b"loc_1000:\n", 1)
        self.assertEqual(len(body), 2)
        self.assertNotIn(MARKER, body[1])
        self.assertIn(
            b"kd_body_entry_1000:\n" + MARKER + b"JMP     loc_1000\n", body[0],
        )
        stub = assembly.split(b"loc_2000:\n", 1)[1]
        self.assertNotIn(MARKER, stub)

    def test_loop_edges_bypass_witness_and_keep_exact_budget_exit(self):
        # mov eax,3; sub eax,1; jne 0x1005; ret. Set a small remaining
        # budget only in the fixture so the real wrapper exercises expiry.
        assembly, log, status = render("b80300000083e80175fbc3", return_status=True)
        self.assertEqual(status, 0, log)
        loop = assembly.split(b"loc_1005:\n", 1)[1]
        self.assertNotIn(MARKER, loop)
        self.assertIn(b"DEC             Stack_BUDGET\n", loop)
        self.assertNotIn(b"TEST            Stack_BUDGET", assembly)
        for limit, value, reason in ((1, 3, 4), (2, 2, 4), (4, 0, 0x100b)):
            with self.subTest(limit=limit):
                bounded = assembly.replace(
                    b"MOV     Stack_BUDGET, 0x1000000\n",
                    f"MOV     Stack_BUDGET, {limit}\n".encode(),
                )
                regs, args = run_image(bounded, [0x1000])[0]
                self.assertEqual(regs[12], value)
                self.assertEqual(args, [reason, 1])
                self.assertEqual(regs[0], 0x1005 if reason == 4 else 0x4444)


if __name__ == "__main__":
    unittest.main(verbosity=2)
