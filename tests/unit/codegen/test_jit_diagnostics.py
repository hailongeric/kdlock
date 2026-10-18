# Reusable mocked-text translator harness and diagnostics/codegen checks.
# Real kernel symbols/reads and publication are substituted; wrapper execution
# is supplied separately by test_jit_body_witness and never counted as live JIT.
import contextlib
import hashlib
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "disassem"))

import conflict
import diagnostics
import normal
import special_inst

# This acceptance test requires real code generation, not a successful SKIP.
from miasm.arch.x86.arch import mn_x86
from miasm.core.bin_stream import bin_stream_str
from miasm.core.locationdb import LocationDB
from miasm.expression.expression import ExprId, ExprOp

import disassem as translator

TEST_LOCK_SYMBOLS = {
    name: 0x1000000 + index * 0x1000
    for index, name in enumerate(translator.context_policy.CONTROL_SYMBOLS)
}


def decode(raw):
    return mn_x86.dis(bin_stream_str(bytes.fromhex(raw)), 64, 0)


def render(
    raw,
    muted=False,
    regions=None,
    symbols=None,
    return_status=False,
    kernel_symbols=None,
    lock_kind="spin",
    entry=0x1000,
    memory_reader=None,
    body_witness=False,
    indirect_history=None,
    mutex_stack_bytes=0,
    abi=0,
    native_escape_capable=False,
    build_options=None,
):
    output = io.StringIO()
    resolved_symbols = TEST_LOCK_SYMBOLS | (kernel_symbols or {})
    previous = os.getcwd()

    def read_regions(entry, jump_table, excluded_callees):
        # Reproduce learned dispatch metadata as well as bytes so tests cannot
        # accidentally validate a single-entry graph with its IJ history erased.
        jump_table.update(
            {
                source: list(targets)
                for source, targets in (indirect_history or {}).items()
            }
        )
        return regions or [(bytes.fromhex(raw), entry, [entry])]

    with tempfile.TemporaryDirectory() as temp, contextlib.ExitStack() as stack:
        stack.enter_context(contextlib.redirect_stderr(output))
        # Byte fixtures replace the validated device query, never open or
        # load a provider merely to exercise analysis. Live tests keep the
        # real lease; existing fixtures default to the old conservative bound.
        stack.enter_context(
            patch.object(
                translator.memread.device_session,
                "mutex_stack_bytes",
                return_value=mutex_stack_bytes,
            )
        )
        stack.enter_context(patch.object(translator.memread.device_session,
                                        "native_escape", return_value=native_escape_capable))
        stack.enter_context(
            patch.object(
                translator.memread.device_session,
                "percpu_module_bytes",
                return_value=8192,
            )
        )
        stack.enter_context(
            patch.object(
                translator.memread,
                "read",
                side_effect=read_regions,
            )
        )
        stack.enter_context(
            patch.object(
                translator.memread,
                "read_kernel_addr_data",
                side_effect=memory_reader
                or AssertionError("unexpected kernel text read"),
            )
        )
        stack.enter_context(
            patch.object(
                translator,
                "get_kernel_symbol",
                side_effect=lambda name, default=0: resolved_symbols.get(name, default),
            )
        )
        build_mock = stack.enter_context(patch.object(translator, "build_jit_binary"))
        stack.enter_context(
            patch.object(
                translator.context_policy,
                "load_context_symbols",
                return_value=symbols or {},
            )
        )
        if muted:
            stack.enter_context(patch.object(diagnostics, "_emit"))
        os.chdir(temp)
        try:
            status = translator.dis_assem(
                0, entry, lock_kind, body_witness=body_witness, abi=abi
            )
            path = Path("asm/jit.S")
            assembly = path.read_bytes() if path.exists() else b""
            if build_options is not None and build_mock.call_args:
                build_options.update(build_mock.call_args.kwargs)
        finally:
            os.chdir(previous)
    result = assembly, output.getvalue()
    return (*result, status) if return_status else result


class JitDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        diagnostics.begin(7, 0x1000)

    def test_int_is_refused_with_source_location(self):
        assembly, log, status = render("90cd80c3", return_status=True)
        warning = next(line for line in log.splitlines() if "reason=CONTEXT_NATIVE_ONLY" in line)
        self.assertIn('entry="0x1000"', warning)
        self.assertIn('rip="0x1001"', warning)
        self.assertIn('action="reject_entry"', warning)
        self.assertIn("INT", warning)
        self.assertEqual((status, assembly), (2, b""))
        self.assertNotIn("INT_AS_NOP", log)

    def test_unhandled_special_names_cannot_be_silently_omitted(self):
        for name in ("PUSHF", "POPF"):
            with self.subTest(name=name):
                diagnostics.begin(7, 0x1000)
                line = decode("9c")
                # Exercise the existing dispatch names, not PUSHFQ/POPFQ aliases.
                line.name = name
                diagnostics.set_instruction(0x1010, line)
                with self.assertRaisesRegex(ValueError, "unsupported special instruction"):
                    special_inst.special_inst_dispatch(
                        line, [], 0x1011, LocationDB(), conflict.block_init(), True
                    )

    def test_operand_warning_retains_existing_result(self):
        arg = ExprOp("-", ExprId("RAX", 64), ExprId("RBX", 64))
        diagnostics.set_instruction(0x1020, "MOV RAX, <unresolved operand>")
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            result = normal.arg_purify(arg, 0x1023)
            address = {"sz": 64, "regs": [], "im": "", "mul": []}
            normal.mem_addr(arg, address)
        self.assertEqual(result, "")
        self.assertEqual(address, {"sz": 64, "regs": [], "im": "", "mul": []})
        self.assertIn("reason=UNRESOLVED_OPERAND_OP", output.getvalue())
        self.assertIn("reason=UNRESOLVED_ADDRESS_OP", output.getvalue())
        self.assertIn('rip="0x1020"', output.getvalue())

    def test_dedup_is_per_reason_location_and_translation(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            diagnostics.set_instruction(0x1001, "INT 0x80")
            diagnostics.warn("INT_AS_NOP", "emit_nop", "line1\nline2")
            diagnostics.warn("INT_AS_NOP", "emit_nop")
            diagnostics.set_instruction(0x1002, "INT 0x80")
            diagnostics.warn("INT_AS_NOP", "emit_nop")
            diagnostics.begin(8, 0x2000)
            diagnostics.set_instruction(0x1001, "INT 0x80")
            diagnostics.warn("INT_AS_NOP", "emit_nop")
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("line1\\nline2", lines[0])
        self.assertIn("pid=8", lines[-1])
        self.assertIn('entry="0x2000"', lines[-1])

    def test_flags_summary_and_lea_diagnostic(self):
        assembly, log = render("4f8d2c344839d8750190c3")
        self.assertEqual(log.count("reason=FLAGS_UNPRESERVED"), 1)
        self.assertEqual(log.count("reason=LEA_FLAGS_REWRITE"), 1)
        self.assertIn("budget_blocks=1", log)
        self.assertIn('first_budget_rip="0x1000"', log)
        self.assertIn('action="emit_mov_add"', log)
        self.assertIn(b"DEC             Stack_BUDGET\n", assembly)
        self.assertIn(b"JZ              kd_budget_limit_1000\n", assembly)
        self.assertNotIn(b"TEST            Stack_BUDGET", assembly)
        self.assertEqual(assembly, render("4f8d2c344839d8750190c3", muted=True)[0])

    def test_pre_log_miasm_015_assembly_baselines(self):
        # Captured from unmodified 044dba1 in the guest; includes original comments.
        fixtures = {
            "4f8d2c344839d8750190c3": "7f95692fd0fead784e376e38ac766c25bd48abe33ac2ef76f8b7bcced4e18720",
        }
        for raw, expected in fixtures.items():
            with self.subTest(raw=raw):
                assembly, _ = render(raw)
                # Normalize the intentional budget-only change back to the
                # original spelling; all unrelated emitted bytes keep their
                # historical oracle. Runtime countdown checks live separately.
                assembly = assembly.replace(
                    b"MOV     Stack_BUDGET, 0x1000000\n",
                    b"MOV     Stack_BUDGET, 0\n",
                )
                assembly = re.sub(
                    rb"DEC             Stack_BUDGET\n"
                    rb"JZ              kd_budget_limit_([0-9a-f]+)\n",
                    lambda match: b"MOVABS          R14, 0x" + match[1]
                    + b"\nINC             Stack_BUDGET\n"
                    b"TEST            Stack_BUDGET, 0x1000000\n"
                    b"JNZ             inst_limit\n",
                    assembly,
                )
                assembly = re.sub(
                    rb"kd_budget_limit_([0-9a-f]+):\n"
                    rb"MOVABS          R14, 0x\1\nJMP             inst_limit\n",
                    b"", assembly,
                )
                if raw == "4f8d2c344839d8750190c3":
                    # LEA's legacy MOV/ADD rewrite reads logical R14, then
                    # reuses physical R14 for logical R12. Dirty tracking now
                    # omits exactly this unchanged R14 spill. Restore only
                    # that known obsolete store for the historical byte hash.
                    clean_eviction = (
                        b"MOV             R15, R14\n"
                        b"MOV             R14, Stack_R12\n"
                    )
                    self.assertEqual(assembly.count(clean_eviction), 1)
                    assembly = assembly.replace(
                        clean_eviction,
                        b"MOV             R15, R14\n"
                        b"MOV             Stack_R14, R14\n"
                        b"MOV             R14, Stack_R12\n",
                    )
                assembly = assembly.replace(b"Stack_BUDGET", b"R11")
                self.assertEqual(hashlib.sha256(assembly).hexdigest(), expected)

    def test_segment_rejection_does_not_generate_an_error_stub(self):
        assembly, log, status = render("64488b042528000000c3", return_status=True)
        self.assertEqual(status, 2)
        self.assertIn("[KD_JIT][WARN] reason=CONTEXT_NATIVE_ONLY", log)
        self.assertIn('rip="0x1000"', log)
        self.assertIn("FS:", log)
        self.assertEqual(assembly, b"")
        self.assertNotIn("FLAGS_UNPRESERVED", log)
        self.assertNotIn("CONTEXT_SCREENING_ONLY", log)
        self.assertNotIn("CONTEXT_ADDRESS_WIDENED", log)

    def test_address_widening_reports_explicit_and_implicit_accesses(self):
        seed_call = "48b8f82f000000000000488945f8e800400000488b75f8"
        for access, instruction in (("488b4610", "MOV"), ("4883c61048ad", "LODSQ")):
            with self.subTest(instruction=instruction):
                raw = seed_call + access + "c3"
                # Use a returning control service: an ordinary missing CALL
                # now leaves this suffix entirely in the waiter's native path.
                options = {"kernel_symbols": {"_raw_spin_lock": 0x5013}}
                assembly, log, status = render(raw, return_status=True, **options)
                self.assertEqual((assembly, status), (b"", 2), log)
                warning = next(
                    line
                    for line in log.splitlines()
                    if "reason=CONTEXT_ADDRESS_WIDENED" in line
                )
                self.assertIn(f'inst="{instruction}', warning)
                self.assertIn('wide_registers=["RSI"]', warning)
                self.assertIn('"RSI": "kd_wide_RSI"', warning)
                self.assertIn("analysis_work_limit=1000000", warning)
                self.assertIn("analysis_work_exceeded=false", warning)
                self.assertEqual(log.count("reason=CONTEXT_ADDRESS_WIDENED"), 1)
                muted_assembly, _, muted_status = render(
                    raw, muted=True, return_status=True, **options
                )
                self.assertEqual((assembly, status), (muted_assembly, muted_status))

    def test_address_widening_distinguishes_actual_work_exhaustion(self):
        memory = translator.context_policy.context_memory.MemoryValues
        with patch.object(memory, "MAX_WORK", 0):
            assembly, log, status = render(
                "48b8f82f000000000000488945f8488b75f848adc3", return_status=True
            )
        self.assertEqual((assembly, status), (b"", 2), log)
        self.assertIn("reason=CONTEXT_ADDRESS_WIDENED", log)
        self.assertIn("analysis_work_limit=0", log)
        self.assertIn("analysis_work_exceeded=true", log)

    def test_failure_details_are_bounded_and_do_not_modify_analysis(self):
        policy = translator.context_policy
        tracker = policy.FlowConstants()
        rsi = ExprId("RSI", 64)
        large = ExprId("diagnostic_" + "x" * 512, 64)
        before, work = tracker.snapshot(), tracker.memory.work
        fields = tracker.address_failure_details(large, large, {rsi: large})
        self.assertEqual(tracker.snapshot(), before)
        self.assertEqual(tracker.memory.work, work)
        for text in (
            fields["address_expression"],
            fields["address_candidate"],
            fields["register_inputs"]["RSI"],
        ):
            self.assertEqual(len(text), 240)
            self.assertTrue(text.endswith("..."))

    def test_admitted_unknown_address_reports_screening_not_precision_failure(self):
        # Keep the diagnostic distinct from precision refusal, for direct and
        # memory-loaded pointers in both backends. This is not an assertion of
        # runtime safety; muted diagnostics must preserve the exact verdict/code.
        for kind in ("spin", "mutex"):
            for raw in ("488b07c3", "488b07488b00c3"):
                with self.subTest(kind=kind, raw=raw):
                    assembly, log, status = render(
                        raw, lock_kind=kind, return_status=True
                    )
                    self.assertEqual(status, 0, log)
                    self.assertTrue(assembly)
                    self.assertNotIn("CONTEXT_ADDRESS_WIDENED", log)
                    warnings = [
                        line
                        for line in log.splitlines()
                        if "reason=CONTEXT_SCREENING_ONLY" in line
                    ]
                    self.assertEqual(len(warnings), 1, log)
                    warning = warnings[0]
                    for field in (
                        'entry="0x1000"',
                        'rip="0x1000"',
                        'inst="<context admission scope>"',
                        'action="emit_unchanged"',
                        "runtime_address_guard=false",
                        "concurrent_memory_validated=false",
                    ):
                        self.assertIn(field, warning)
                    muted_assembly, _, muted_status = render(
                        raw, lock_kind=kind, return_status=True, muted=True
                    )
                    self.assertEqual((assembly, status), (muted_assembly, muted_status))

    def test_build_failure_is_reraised(self):
        output = io.StringIO()
        failure = subprocess.CalledProcessError(9, ["gcc", "fixture.S"])
        with (
            patch.object(translator.subprocess, "run", side_effect=failure),
            contextlib.redirect_stderr(output),
            self.assertRaises(subprocess.CalledProcessError) as caught,
        ):
            translator.run_build_step(["gcc", "fixture.S"])
        self.assertIs(caught.exception, failure)
        self.assertIn("[KD_JIT][ERROR] reason=BUILD_FAILED", output.getvalue())
        self.assertIn('command=["gcc", "fixture.S"]', output.getvalue())

    def test_build_success_keeps_checked_subprocess_arguments(self):
        output = io.StringIO()
        with patch.object(translator.subprocess, "run") as run:
            translator.run_build_step(["objdump", "fixture.bin"], stdout=output)
        run.assert_called_once_with(
            ["objdump", "fixture.bin"], check=True, stdout=output
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
