"""Context admission instructions cases, collected only by test_context_policy."""
import contextlib
import io
import os
import re
import struct
import tempfile
from pathlib import Path
from unittest.mock import patch
from miasm.expression.expression import ExprId
from test_jit_diagnostics import TEST_LOCK_SYMBOLS, render, translator
context_policy = translator.context_policy
from context_case_support import ContextCaseSupport


class ContextInstructionsCases(ContextCaseSupport):
    def test_remote_continuation_needs_parent_admission_scope(self):
        base = 0x1000
        lock = TEST_LOCK_SYMBOLS["_raw_spin_lock"]
        unlock = TEST_LOCK_SYMBOLS["_raw_spin_unlock"]

        def call(target, offset):
            return b"\xe8" + struct.pack("<i", target - offset - 5)

        for suffix in (
            bytes.fromhex("b878563412"),
            bytes.fromhex("64488b042500000000"),
        ):
            with self.subTest(suffix=suffix.hex()):
                raw = call(lock, base) + call(unlock, base + 5) + suffix
                raw += call(unlock, base + len(raw)) + b"\xc3"
                child, _, child_status = render(
                    raw[5:].hex(), entry=base + 5, return_status=True
                )
                parent, _, parent_status = render(raw.hex(), return_status=True)
                # A standalone B starts at depth one and stops at unlock(A).
                self.assertEqual(child_status, 0)
                self.assertNotIn(b"0x12345678", child.lower())
                if suffix[0] == 0x64:
                    self.assertEqual(parent_status, context_policy.NATIVE_ONLY_EXIT)
                    self.assertEqual(parent, b"")
                else:
                    self.assertEqual(parent_status, 0)
                    self.assertIn(b"0x12345678", parent.lower())


    def test_gs_reads_writes_and_rmw_use_origin_base(self):
        for kind in ("spin", "mutex"):
            for raw in (
                "65488b042528000000c3",
                "654889042528000000c3",
                "6548ff042528000000c3",
                "4839d87501c365488b042528000000c3",
            ):
                with self.subTest(kind=kind, raw=raw):
                    assembly, log, status = render(
                        raw, lock_kind=kind, return_status=True
                    )
                    self.assertEqual(status, 0, log)
                    self.assertIn(b"Stack_RGS", assembly)
                    self.assertNotIn(b"GS:[", re.sub(rb"/\*.*?\*/", b"", assembly, flags=re.S))


    def test_current_task_uses_logical_task_despite_known_symbol(self):
        for kind in ("spin", "mutex"):
            assembly, log, status = render(
                "65488b042528000000c3", lock_kind=kind,
                kernel_symbols={"current_task": 0x28},
                symbols={0x28: "current_task"}, return_status=True,
            )
            self.assertEqual(status, 0, log)
            self.assertIn(b"Stack_RCT", assembly)
            self.assertNotIn(b"Stack_RGS", assembly)
        for raw in ("654889042528000000c3", "6548ff042528000000c3"):
            log = self.assert_rejected(raw, kernel_symbols={"current_task": 0x28})
            self.assertIn("current_task is only supported as a 64-bit MOV source", log)


    def test_branch_and_nested_body_are_checked(self):
        self.assert_rejected("4839d87501c364488b042528000000c3")
        self.assert_rejected(
            "e8fb1f000064488b042528000000c3",
            kernel_symbols={"_raw_spin_lock": 0x3000},
        )


    def test_implicit_string_and_xlat_segments_are_checked(self):
        for raw in ("65a5c3", "65acc3", "65d7c3", "65f3a5c3", "64acc3"):
            with self.subTest(raw=raw):
                self.assert_rejected(raw)


    def test_ir_implicit_sources_and_destinations_without_segments(self):
        for prefix, opcodes in (
            ("48bef82f0000000000004883c610", ("ac", "66ad", "ad", "48ad", "a4", "a6")),
            (
                "48bff82f0000000000004883c710",
                ("aa", "66ab", "ab", "48ab", "ae", "48af"),
            ),
        ):
            for opcode in opcodes:
                with self.subTest(prefix=prefix, opcode=opcode):
                    log = self.assert_rejected(
                        prefix + opcode + "c3", symbols=self.context_ranges()
                    )
                    self.assertIn("__per_cpu_offset", log)
                    self.assertIn('rip="0x100e"', log)


    def test_ir_memory_access_width_and_data_values_are_distinct(self):
        self.assert_rejected(
            "48befc2f00000000000048adc3", symbols=self.context_ranges()
        )
        for raw in (
            "48befc2f000000000000adc3",  # Four bytes end exactly before the table.
            "48bef82f00000000000048adc3",  # Eight bytes end before it too.
            "48bff81f00000000000048ab48a4c3",  # An unrelated destination.
            "b8f82f00004883c010bff81f000048abc3",  # Sensitive value, not a pointer.
            "f3a4c3",  # Runtime-only source/destination remain unknown.
        ):
            with self.subTest(raw=raw):
                _, _, status = render(
                    raw, symbols=self.context_ranges(), return_status=True
                )
                self.assertEqual(status, 0)


    def test_ir_xlat_checks_the_computed_byte_address(self):
        log = self.assert_rejected(
            "48bbf82f000000000000b810000000d7c3", symbols=self.context_ranges()
        )
        self.assertIn('inst="XLAT', log)
        self.assertIn("__per_cpu_offset", log)
        _, _, status = render(
            "48bbf82f00000000000031c0d7c3",
            symbols=self.context_ranges(),
            return_status=True,
        )
        self.assertEqual(status, 0)


    def test_ir_stack_reads_writes_and_call_are_checked_before_invalidation(self):
        prefix = bytes.fromhex("48bcfc2f0000000000004883c410")
        call = b"\xe8" + struct.pack("<i", 0x6000 - (0x1000 + len(prefix) + 5))
        for opcode, name in (
            (b"\x58", "POP"),
            (b"\x50", "PUSH"),
            (b"\xc3", "RET"),
            (call, "CALL"),
        ):
            with self.subTest(name=name):
                log = self.assert_rejected(
                    (prefix + opcode + b"\xc3").hex(), symbols=self.context_ranges()
                )
                self.assertIn(f'inst="{name}', log)
                self.assertIn("__per_cpu_offset", log)
        # The POP itself overlaps the table although its starting address does not.
        self.assert_rejected("48bcfc2f00000000000058c3", symbols=self.context_ranges())


    def test_ir_checks_each_successive_and_repeated_memory_access(self):
        log = self.assert_rejected(
            "48bef82f00000000000048ad48adc3", symbols=self.context_ranges()
        )
        self.assertIn('rip="0x100c"', log)
        self.assertIn('inst="LODSQ', log)
        for raw in (
            "48bef82f000000000000b910000000f3acc3",
            "48bff82f000000000000b910000000f3aac3",
            "48bef82f000000000000b910000000f3a4c3",
        ):
            with self.subTest(raw=raw):
                log = self.assert_rejected(raw, symbols=self.context_ranges())
                self.assertIn('inst="REP', log)
                self.assertIn("__per_cpu_offset", log)


    def test_ir_memory_widening_refuses_at_original_instruction(self):
        # Internal count/DF edges remain unpruned, even with native count one.
        # Exhaustion must not become an unknown pointer that silently passes.
        log = self.assert_rejected(
            "48bef81f000000000000b901000000f3acc3", symbols=self.context_ranges()
        )
        self.assertIn("bounded register-address alternatives", log)
        self.assertIn('rip="0x100f"', log)
        self.assertIn('inst="REP LODSB', log)


    def test_ir_memory_temporary_parallel_store_nested_and_condition(self):
        from miasm.expression.expression import ExprCond, ExprInt, ExprLoc, ExprMem
        from miasm.ir.ir import AssignBlock, IRBlock
        from test_jit_diagnostics import decode

        for kind in ("load", "store", "nested", "condition"):
            with self.subTest(kind=kind):
                tracker = context_policy.FlowConstants()
                tracker.update(decode("b8f82f0000"))
                line = decode("48d3e0")
                line.offset = 0x1234
                db = tracker.lifter.loc_db
                taken = db.add_location()
                end = db.get_or_create_offset_location(line.offset + line.l)
                target, finish = ExprLoc(taken, 64), ExprLoc(end, 64)
                rax, rdx = ExprId("RAX", 64), ExprId("RDX", 64)
                temp = ExprId("instruction_memory_address", 64)
                dst = tracker.lifter.IRDst
                entry = AssignBlock({temp: rax, rax: ExprInt(0, 64), dst: target})
                memory = ExprMem(temp + ExprInt(16, 64), 64)
                # Memory uses the old temp, even though this same block clears it.
                assignments = {temp: ExprInt(0, 64), dst: finish}
                if kind == "store":
                    assignments[memory] = ExprInt(0, 64)
                elif kind == "condition":
                    assignments[dst] = ExprCond(memory, finish, finish)
                else:
                    assignments[rdx] = (
                        ExprMem(memory, 64) if kind == "nested" else memory
                    )
                block = IRBlock(db, taken, [AssignBlock(assignments)])
                with (
                    patch.object(
                        tracker.lifter, "instr2ir", return_value=(entry, [block])
                    ),
                    self.assertRaises(context_policy.ContextFlowLimit) as error,
                ):
                    tracker.update(line, self.context_ranges())
                self.assertIn("__per_cpu_offset", str(error.exception))
                self.assertEqual(error.exception.offset, 0x1234)
                self.assertIs(error.exception.instruction, line)


    def test_ir_implicit_memory_after_outer_unlock_is_outside_admission(self):
        unlock = TEST_LOCK_SYMBOLS["_raw_spin_unlock"]
        suffix = bytes.fromhex("48bef82f0000000000004883c61048ad")

        def call(offset):
            return b"\xe8" + struct.pack("<i", unlock - offset - 5)

        assembly, _, status = render(
            (call(0x1000) + suffix + b"\xc3").hex(),
            symbols=self.context_ranges(),
            return_status=True,
        )
        self.assertEqual(status, 0)
        self.assertNotIn(b"LODS", assembly)
        self.assert_rejected(
            (suffix + call(0x1000 + len(suffix)) + b"\xc3").hex(),
            symbols=self.context_ranges(),
        )


    def test_irq_instructions_and_existing_base_restrictions(self):
        for raw in ("fac3", "fbc3", "0f01f8c3", "f3480faec0c3"):
            with self.subTest(raw=raw):
                # Complete decoder lookahead, not an artificially truncated read.
                self.assert_rejected(raw + "c3" * 15)


    def test_known_context_calls_and_tail_calls(self):
        for opcode in ("e8", "e9"):
            log = self.assert_rejected(
                opcode + "fb1f0000c3", symbols={0x3000: "schedule"}
            )
            self.assertIn("schedule", log)


    def test_irq_wrapper_after_outer_unlock_is_not_part_of_caller(self):
        assembly, _, status = render(
            "e8fb1f0000e8f62f0000c3",
            kernel_symbols={"_raw_spin_unlock": 0x3000},
            symbols={0x4000: "_raw_spin_lock_irqsave"},
            return_status=True,
        )
        self.assertEqual(status, 0)
        self.assertNotIn(b"loc_1005:", assembly)


    def test_rip_relative_context_data(self):
        self.assert_rejected("488b05f91f0000c3", symbols={0x3000: "current_task"})


    def test_linux_mutex_apis_are_refused_in_kd_only_entries(self):
        for name in ("mutex_lock", "mutex_unlock", "__mutex_lock_slowpath",
                     "kd_mutex_lock_clobber_v1", "kd_mutex_lock_interruptible"):
            with self.subTest(name=name):
                self.assert_rejected("e8fb1f0000c3", lock_kind="mutex",
                                     symbols={0x3000: name})

    def test_unknown_calls_keep_dynamic_completion(self):
        for raw in ("e8fb0f0000c3", "ffd0c3"):
            assembly, _, status = render(raw, return_status=True)
            self.assertEqual(status, 0)
            self.assertTrue(assembly)


    def test_mixed_spin_mutex_calls_are_not_admitted(self):
        self.assert_rejected(
            "e8fb2f0000e8f61f0000c3",
            kernel_symbols={"_raw_spin_lock": 0x4000, "kd_mutex_local_unlock": 0x3000},
        )


    def test_foreign_lock_references_need_no_visible_outer_unlock(self):
        for kind, symbol in (("spin", "kd_mutex_local_lock"), ("mutex", "_raw_spin_lock")):
            for raw in ("e8fb1f0000c3", "e9fb1f0000", "48c7c000300000c3"):
                with self.subTest(kind=kind, raw=raw):
                    log = self.assert_rejected(
                        raw, lock_kind=kind, kernel_symbols={symbol: 0x3000}
                    )
                    self.assertIn(symbol, log)
                    self.assertIn(f"in {kind} entry", log)


    def test_matching_lock_backends_still_admitted(self):
        for kind, symbol in (("spin", "_raw_spin_lock"), ("mutex", "kd_mutex_local_lock")):
            assembly, _, status = render(
                "e8fb1f0000c3",
                lock_kind=kind,
                kernel_symbols={symbol: 0x3000},
                return_status=True,
            )
            self.assertEqual(status, 0)
            self.assertTrue(assembly)


    def test_lexical_lock_capacity_boundary(self):
        symbols = {"kd_mutex_local_lock": 0x3000}
        assembly, _, status = render(
            self.mutex_calls(0x1000, 7).hex(),
            lock_kind="mutex",
            kernel_symbols=symbols,
            return_status=True,
        )
        self.assertEqual(status, 0)
        self.assertTrue(assembly)
        log = self.assert_rejected(
            self.mutex_calls(0x1000, 8).hex(),
            lock_kind="mutex",
            kernel_symbols=symbols,
        )
        self.assertIn("excessive lexical lock nesting", log)


    def test_retained_deep_scope_uses_explicit_image_requirement(self):
        symbols = {"kd_mutex_local_lock": 0x3000,
                   "kd_mutex_local_unlock": 0x4000}
        for children, expected in ((7, 128), (8, 384)):
            with self.subTest(children=children):
                raw = bytearray()
                for target in [0x3000] * children + [0x4000] * (children + 1):
                    raw += b"\xe8" + struct.pack("<i", target - (0x1000 + len(raw) + 5))
                after_release = 0x1000 + len(raw)
                raw += b"\xb8\x78\x56\x34\x12\xc3"
                options = {}
                assembly, log, status = render(
                    raw.hex(), lock_kind="mutex", abi=2, trusted_source=True,
                    kernel_symbols=symbols, return_status=True, build_options=options,
                )
                self.assertEqual(status, 0, log)
                self.assertEqual(options["requirements"], expected)
                # Only the service contract leaves final delimiting to the
                # exact runtime record; the ordinary image keeps its pruning.
                self.assertEqual(f"loc_{after_release:x}:".encode() in assembly,
                                 children == 8)


    def test_retained_balanced_child_loop_keeps_ordinary_image_contract(self):
        # The loop revisits one LOCAL acquisition/release pair; maximum live
        # depth stays two, so it must not acquire the deep-image requirement.
        raw = b"\xe8" + struct.pack("<i", 0x3000 - 0x1005)
        raw += b"\xe8" + struct.pack("<i", 0x4000 - 0x100a)
        raw += b"\xff\xc9\x75\xf2"
        raw += b"\xe8" + struct.pack("<i", 0x4000 - 0x1013) + b"\xc3"
        options = {}
        assembly, log, status = render(
            raw.hex(), lock_kind="mutex", abi=2, trusted_source=True,
            kernel_symbols={"kd_mutex_local_lock": 0x3000,
                            "kd_mutex_local_unlock": 0x4000},
            return_status=True, build_options=options,
        )
        self.assertEqual(status, 0, log)
        self.assertTrue(assembly)
        self.assertEqual(options["requirements"], 128)


    def test_retained_callee_owned_child_keeps_early_outer_release_tail(self):
        # The callee returns with B still held. A's unlock cannot prune the
        # source instructions before B's later exact release.
        caller = b"\xe8" + struct.pack("<i", 0x2000 - 0x1005)
        caller += b"\xe8" + struct.pack("<i", 0x4000 - 0x100a)
        caller += b"\xb8\x78\x56\x34\x12"
        caller += b"\xe8" + struct.pack("<i", 0x4000 - 0x1014) + b"\xc3"
        callee = b"\xe8" + struct.pack("<i", 0x3000 - 0x2005) + b"\xc3"
        options = {}
        assembly, log, status = render(
            "", regions=[(caller, 0x1000, [0x1000]), (callee, 0x2000, [0x2000])],
            lock_kind="mutex", abi=2, trusted_source=True,
            kernel_symbols={"kd_mutex_local_lock": 0x3000,
                            "kd_mutex_local_unlock": 0x4000},
            return_status=True, build_options=options,
        )
        self.assertEqual(status, 0, log)
        self.assertEqual(options["requirements"], 384)
        self.assertIn(b"loc_100a:", assembly)


    def test_callee_depth_needs_the_runtime_capacity_guard(self):
        # Callees are scanned with unknown entry depth. Admission here is not
        # evidence that A plus these eight acquisitions fits a runtime frame.
        regions = [
            (bytes.fromhex("e8fb0f0000c3"), 0x1000, [0x1000]),
            (self.mutex_calls(0x2000, 8), 0x2000, [0x2000]),
        ]
        assembly, _, status = render(
            "",
            regions=regions,
            lock_kind="mutex",
            kernel_symbols={"kd_mutex_local_lock": 0x3000},
            return_status=True,
        )
        self.assertEqual(status, 0)
        self.assertIn(b"loc_2000:", assembly)


    def test_unknown_entry_kind_is_not_guessed(self):
        for kind in ("unknown", "", "invalid"):
            self.assertIn(
                "entry lock kind", self.assert_rejected("90c3", lock_kind=kind)
            )


    def test_foreign_backend_in_late_callee_rejects_entry(self):
        self.assertEqual(render("e8fb0f0000c3", return_status=True)[2], 0)
        regions = [
            (bytes.fromhex("e8fb0f0000c3"), 0x1000, [0x1000]),
            (bytes.fromhex("e8fb0f0000c3"), 0x2000, [0x2000]),
        ]
        log = self.assert_rejected(
            "", regions=regions, kernel_symbols={"kd_mutex_local_lock": 0x3000}
        )
        self.assertIn('rip="0x2000"', log)


    def test_foreign_backend_after_outer_unlock_is_outside_cs(self):
        assembly, _, status = render(
            "e8fb1f0000e8f62f0000c3",
            kernel_symbols={"_raw_spin_unlock": 0x3000, "kd_mutex_local_lock": 0x4000},
            return_status=True,
        )
        self.assertEqual(status, 0)
        self.assertNotIn(b"loc_1005:", assembly)


    def test_post_outer_unlock_gs_is_outside_the_translation(self):
        assembly, _, status = render(
            "e8fb1f000065488b042528000000c3",
            kernel_symbols={"_raw_spin_unlock": 0x3000},
            return_status=True,
        )
        self.assertEqual(status, 0)
        self.assertNotIn(b"GS:[", assembly)
        self.assertNotIn(b"Stack_RGS", assembly)


    def test_nested_unlock_does_not_hide_fs_in_parent(self):
        self.assert_rejected(
            "e8fb2f0000e8f61f000064488b042528000000c3",
            kernel_symbols={"_raw_spin_lock": 0x4000, "_raw_spin_unlock": 0x3000},
        )


    def test_callee_scan_does_not_assume_outer_unlock(self):
        regions = [
            (bytes.fromhex("e8fb0f0000c3"), 0x1000, [0x1000]),
            (bytes.fromhex("e8fb0f000064488b042528000000c3"), 0x2000, [0x2000]),
        ]
        self.assert_rejected(
            "", regions=regions, kernel_symbols={"_raw_spin_unlock": 0x3000}
        )


    def test_new_callee_rejects_the_whole_entry(self):
        raw = "e8fb0f0000c3"
        self.assertEqual(render(raw, return_status=True)[2], 0)
        regions = [
            (bytes.fromhex(raw), 0x1000, [0x1000]),
            (bytes.fromhex("64488b042528000000c3"), 0x2000, [0x2000]),
        ]
        log = self.assert_rejected(raw, regions=regions)
        self.assertIn('entry="0x1000"', log)
        self.assertIn('rip="0x2000"', log)


    def test_plain_code_and_segmented_nop_still_admitted(self):
        for raw in ("488b034801d8c3", "650f1f00c3"):
            self.assertEqual(render(raw, return_status=True)[2], 0)


    def test_rejection_removes_only_stale_generated_images(self):
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as temp:
            os.chdir(temp)
            try:
                Path("asm").mkdir()
                for name in (
                    "jit.S",
                    "jit.o",
                    "jit.bin",
                    "bin.txt",
                    "callee_table.txt",
                ):
                    Path("asm", name).write_text("old image", encoding="ascii")
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(translator.reject_translation("fixture"), 2)
                self.assertEqual(
                    [p.name for p in Path("asm").iterdir()], ["callee_table.txt"]
                )
            finally:
                os.chdir(previous)
