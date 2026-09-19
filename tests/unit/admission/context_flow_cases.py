"""Context admission flow cases, collected only by test_context_policy."""
import struct
from unittest.mock import patch
from miasm.expression.expression import ExprId
from test_jit_diagnostics import TEST_LOCK_SYMBOLS, render, translator
context_policy = translator.context_policy
from context_case_support import ContextCaseSupport


class ContextFlowCases(ContextCaseSupport):
    def test_register_derived_sensitive_memory_and_calls_are_rejected(self):
        for raw in (
            "48b8f82f0000000000004883c010488b00c3",  # ADD then read.
            "48b8f82f000000000000488d581048891bc3",  # LEA then write.
            "b8f82f00004883c010488b00c3",  # EAX zero extends RAX.
            "48b8f82f0000000000004883c01048ff00c3",  # RMW.
            "48b8f82f000000000000488b580848891bc3",  # Displacement reaches start.
            "48b8ff2f0000000000000fb700c3",  # Widening source overlaps.
            "48b8f82f000000000000488b44c808c3",  # Unknown index, known base.
            "48b8f83f0000000000004883c010ffd0c3",  # Computed context CALL.
        ):
            with self.subTest(raw=raw):
                self.assert_rejected(raw, symbols=self.context_ranges())


    def test_overwrites_and_unknown_values_do_not_leave_stale_addresses(self):
        for raw in (
            "48b8f82f0000000000004883c0104831c0488b00c3",  # XOR clears RAX.
            "48b8f82f0000000000004883c010b800000000488b00c3",  # EAX overwrite.
            "48b8f82f0000000000004883c010488b07488b00c3",  # Memory load is unknown.
            "48b8f82f00000000000048f7e1488b4010c3",  # MUL implicitly writes RAX.
            "48b8f82f0000000000004883d010488b00c3",  # ADC needs unknown flags.
            "48b8f82f0000000000000fb600c3",  # One byte ends before the table.
        ):
            with self.subTest(raw=raw):
                _, _, status = render(
                    raw, symbols=self.context_ranges(), return_status=True
                )
                self.assertEqual(status, 0)


    def test_constant_tracker_uses_partial_register_and_parallel_write_semantics(self):
        from test_jit_diagnostics import decode

        tracker = context_policy.RegisterConstants()
        for raw in ("48b8f82f000000000000", "b008"):
            tracker.update(decode(raw))
        self.assertEqual(int(tracker.resolve(ExprId("RAX", 64))), 0x2F08)
        tracker.update(decode("b800300000"))
        self.assertEqual(int(tracker.resolve(ExprId("RAX", 64))), 0x3000)
        tracker.update(decode("bb01000000"))
        tracker.update(decode("4893"))  # XCHG RAX, RBX uses the old values in parallel.
        self.assertEqual(int(tracker.resolve(ExprId("RAX", 64))), 1)
        self.assertEqual(int(tracker.resolve(ExprId("RBX", 64))), 0x3000)
        tracker.update(decode("e800000000"))
        self.assertEqual(tracker.values, {})


    def test_unliftable_instruction_forgets_constants(self):
        from test_jit_diagnostics import decode

        tracker = context_policy.RegisterConstants()
        tracker.update(decode("b800300000"))
        self.assertTrue(tracker.values)
        with patch.object(tracker.lifter, "instr2ir", side_effect=NotImplementedError):
            tracker.update(decode("90"))
        self.assertEqual(tracker.values, {})


    def test_constant_context_addresses_cross_control_edges(self):
        for raw in (
            "48b8f82f000000000000eb004883c010488b00c3",
            "48b8f82f0000000000004885c9750231c04883c010488b00c3",
            "eb04488b00c348b8f82f0000000000004883c010ebec",
        ):
            with self.subTest(raw=raw):
                self.assert_rejected(raw, symbols=self.context_ranges())


    def test_conditional_move_preserves_sensitive_address_alternatives(self):
        for raw in (
            "48b8f82f000000000000480f44c1488b4010c3",  # Untaken old RAX.
            "48b8f82f000000000000480f44ca488b4010c3",  # Unaffected RAX.
            "48b9f82f000000000000480f44c1488b4010c3",  # Taken RCX.
            "48b8f82f000000000000480f4407488b4010c3",  # Unknown memory source.
            "48b8f82f000000000000660f44c1488b4010c3",  # Preserve AX alternative.
            "48b8f82f0000010000000f44c1488b4010c3",  # EAX clears upper half.
            "b9f82f00000f44c1488b4010c3",  # Taken ECX zero extension.
            "48b8f82f000000000000480f44c1eb00488b4010c3",  # Next CFG block.
        ):
            with self.subTest(raw=raw):
                log = self.assert_rejected(raw, symbols=self.context_ranges())
                self.assertIn("__per_cpu_offset", log)
                self.assertIn('inst="MOV', log)


    def test_conditional_move_never_prunes_using_flags(self):
        for opcode in range(0x40, 0x50):
            raw = "48b8f82f00000000000031c9480f" + f"{opcode:02x}c1"
            with self.subTest(opcode=opcode):
                # Even XOR-established flags cannot eliminate a possible arm.
                self.assert_rejected(raw + "488b4010c3", symbols=self.context_ranges())


    def test_conditional_move_domains_preserve_alias_semantics(self):
        from miasm.expression.expression import ExprInt
        from test_jit_diagnostics import decode

        rax, rcx, rdx = (ExprId(name, 64) for name in ("RAX", "RCX", "RDX"))
        for raw, expected in (
            ("480f44c1", {0x100002FF8, 0x2EE0}),
            ("0f44c1", {0x2FF8, 0x2EE0}),
            ("660f44c1", {0x100002FF8, 0x100002EE0}),
        ):
            with self.subTest(raw=raw):
                tracker = context_policy.FlowConstants()
                tracker.values = {
                    rax: frozenset({ExprInt(0x100002FF8, 64)}),
                    rcx: frozenset({ExprInt(0x2EE0, 64)}),
                    rdx: frozenset({ExprInt(0x1234, 64)}),
                }
                tracker.update(decode(raw))
                self.assertEqual(
                    tracker.values[rax], frozenset(ExprInt(v, 64) for v in expected)
                )
                self.assertEqual(tracker.values[rdx], frozenset({ExprInt(0x1234, 64)}))


    def test_conditional_move_safe_and_overwritten_values_remain_admitted(self):
        for raw in (
            "48b8f81f000000000000480f44c1488b4010c3",  # Known alternative is safe.
            "48b8f82f000001000000660f44c1488b4010c3",  # AX retains high bits.
            "48b8f82f000000000000480f44c131c0488b4010c3",  # Exact overwrite.
            "48b8f82f000000000000480f44c1e8ed4f0000488b4010c3",  # CALL clears facts.
        ):
            with self.subTest(raw=raw):
                _, _, status = render(
                    raw, symbols=self.context_ranges(), return_status=True
                )
                self.assertEqual(status, 0)


    def test_conditional_move_widening_cannot_erase_address_uncertainty(self):
        from test_jit_diagnostics import decode

        tracker = context_policy.FlowConstants()
        tracker.update(decode("b8f82f0000"))
        tracker.update(decode("b9f81f0000"))
        with patch.object(tracker, "MAX_VALUES", 1):
            tracker.update(decode("480f44c1"))
        with self.assertRaises(context_policy.ContextFlowLimit):
            tracker.resolve_many(ExprId("RAX", 64))
        tracker.update(decode("31c0"))
        self.assertEqual(int(tracker.resolve_many(ExprId("RAX", 64))[0]), 0)


    def test_conditional_move_unrecognized_ir_refuses_admission(self):
        from miasm.ir.ir import AssignBlock
        from test_jit_diagnostics import decode

        tracker = context_policy.FlowConstants()
        with (
            patch.object(tracker.lifter, "instr2ir", side_effect=NotImplementedError),
            self.assertRaises(context_policy.ContextFlowLimit),
        ):
            tracker.update(decode("480f44c1"))
        assignments, extra = tracker.lifter.instr2ir(decode("480f44c1"))
        unconditional = dict(assignments)
        unconditional[tracker.lifter.IRDst] = extra[0].dst
        for result in (
            (assignments, []),
            (assignments, extra * 2),
            (AssignBlock(unconditional), extra),
        ):
            tracker = context_policy.FlowConstants()
            with (
                patch.object(tracker.lifter, "instr2ir", return_value=result),
                self.assertRaises(context_policy.ContextFlowLimit),
            ):
                tracker.update(decode("480f44c1"))


    def test_unknown_predecessor_does_not_hide_sensitive_alternative(self):
        self.assert_rejected(
            "48b8f82f0000000000004885c97503488b074883c010488b00c3",
            symbols=self.context_ranges(),
        )
        # Do not prune a path using native flags: inserted code may clobber them.
        self.assert_rejected(
            "48b8f82f00000000000031c9750231c04883c010488b00c3",
            symbols=self.context_ranges(),
        )


    def test_internal_ir_shift_and_rotate_exits_preserve_addresses(self):
        for prefix, opcode in (
            (prefix, "d3" + operand)
            for prefix in ("48", "", "66")
            for operand in ("e0", "e8", "f8", "c0", "c8", "d0", "d8")
        ):
            with self.subTest(prefix=prefix, opcode=opcode):
                self.assert_rejected(
                    "48b8f82f000000000000" + prefix + opcode + "488b7810c3",
                    symbols=self.context_ranges(),
                )
        for opcode in ("48d3e2", "48d3ca", "480fa5d0", "480fadd0", "d2e0"):
            with self.subTest(opcode=opcode):
                self.assert_rejected(
                    "48b8f82f000000000000" + opcode + "488b7810c3",
                    symbols=self.context_ranges(),
                )


    def test_internal_ir_taken_shift_can_construct_sensitive_address(self):
        for opcode in ("48d3e0", "48d3c0"):
            with self.subTest(opcode=opcode):
                self.assert_rejected(
                    "b8fc170000b901000000" + opcode + "488b7810c3",
                    symbols=self.context_ranges(),
                )


    def test_internal_ir_multiple_blocks_and_loop_keep_unaffected_registers(self):
        for opcode in ("480fb1cb", "480fbcc3", "480fbdc3", "f3a4"):
            with self.subTest(opcode=opcode):
                self.assert_rejected(
                    "48baf82f000000000000" + opcode + "488b7a10c3",
                    symbols=self.context_ranges(),
                )
        self.assert_rejected(
            "48bbf82f000000000000480fb1da488b7a10c3",
            symbols=self.context_ranges(),
        )


    def test_internal_ir_safe_and_overwritten_addresses_remain_admitted(self):
        for raw in (
            "b8f81f000048d3e2488b7810c3",
            "b8f82f000048d3e031c0488b7810c3",
            "b8f82f000048d3e0e8ee4f0000488b7810c3",
            "baf81f0000480fb1cb488b7a10c3",
            "baf81f0000f3a4488b7a10c3",
        ):
            with self.subTest(raw=raw):
                _, _, status = render(
                    raw, symbols=self.context_ranges(), return_status=True
                )
                self.assertEqual(status, 0)


    def test_internal_ir_work_and_graph_limits_refuse_at_instruction(self):
        for name, limit in (("MAX_IR_BLOCKS", 1), ("MAX_IR_VISITS", 1)):
            with (
                self.subTest(name=name),
                patch.object(context_policy.FlowConstants, name, limit, create=True),
            ):
                log = self.assert_rejected("9048d3e0c3")
                self.assertIn('rip="0x1001"', log)


    def test_internal_ir_temporary_survives_parallel_and_sequential_assignments(self):
        from miasm.expression.expression import ExprCond, ExprInt, ExprLoc
        from miasm.ir.ir import AssignBlock, IRBlock
        from test_jit_diagnostics import decode

        tracker = context_policy.FlowConstants()
        tracker.update(decode("b8f82f0000"))
        line = decode("48d3e0")
        db = tracker.lifter.loc_db
        taken = db.add_location()
        end = db.get_or_create_offset_location(line.offset + line.l)
        dst = tracker.lifter.IRDst
        target, finish = ExprLoc(taken, 64), ExprLoc(end, 64)
        rax, rdx = ExprId("RAX", 64), ExprId("RDX", 64)
        temp = ExprId("instruction_saved_address", 64)
        entry = AssignBlock({temp: rax, rax: ExprInt(0, 64), dst: target})
        block = IRBlock(
            db,
            taken,
            [
                AssignBlock({rdx: temp + ExprInt(16, 64)}),
                AssignBlock({dst: ExprCond(ExprId("zf", 1), finish, finish)}),
            ],
        )
        with patch.object(tracker.lifter, "instr2ir", return_value=(entry, [block])):
            tracker.update(line)
        self.assertEqual(tracker.values[rdx], frozenset({ExprInt(0x3008, 64)}))
        self.assertEqual(tracker.values[rax], frozenset({ExprInt(0, 64)}))
        self.assertNotIn(temp, tracker.values)


    def test_internal_ir_invalid_successors_cannot_silently_forget_facts(self):
        from miasm.expression.expression import ExprInt, ExprLoc
        from miasm.ir.ir import AssignBlock
        from test_jit_diagnostics import decode

        for kind in ("indirect", "integer", "dangling", "no_exit"):
            with self.subTest(kind=kind):
                tracker = context_policy.FlowConstants()
                line = decode("48d3e0")
                assignments, extra = tracker.lifter.instr2ir(line)
                destination = {
                    "indirect": ExprId("RAX", 64),
                    "integer": ExprInt(0xDEAD, 64),
                    "dangling": ExprLoc(tracker.lifter.loc_db.add_location(), 64),
                    "no_exit": ExprLoc(extra[0].loc_key, 64),
                }[kind]
                changed = dict(assignments)
                changed[tracker.lifter.IRDst] = destination
                if kind == "no_exit":
                    extra[0] = context_policy.IRBlock(
                        tracker.lifter.loc_db,
                        extra[0].loc_key,
                        [AssignBlock({tracker.lifter.IRDst: destination})],
                    )
                with (
                    patch.object(
                        tracker.lifter,
                        "instr2ir",
                        return_value=(AssignBlock(changed), extra),
                    ),
                    self.assertRaises(context_policy.ContextFlowLimit),
                ):
                    tracker.update(line)


    def test_flow_call_and_overwrite_kill_old_values(self):
        for raw in (
            "48b8f82f000000000000eb0031c04883c010488b00c3",
            "48b8f82f000000000000eb00e8ef4f00004883c010488b00c3",
        ):
            with self.subTest(raw=raw):
                _, _, status = render(
                    raw, symbols=self.context_ranges(), return_status=True
                )
                self.assertEqual(status, 0)


    def test_flow_loops_widen_without_erasing_address_uncertainty(self):
        with patch.object(context_policy.FlowConstants, "MAX_VALUES", 4):
            for raw in (
                "31c0eb00ffc083f80a75f9c3",  # Widened counter is not an address.
                "31c0eb00ffc083f80a75f931c0488b18c3",  # Exact overwrite after loop.
            ):
                _, _, status = render(raw, return_status=True)
                self.assertEqual(status, 0)
            log = self.assert_rejected("31c0ffc0488b1883f80a75f6c3")
            self.assertIn("bounded register-address alternatives", log)


    def test_flow_combination_limit_and_parallel_writes(self):
        from miasm.expression.expression import ExprInt, ExprMem
        from test_jit_diagnostics import decode

        tracker = context_policy.FlowConstants()
        rax, rbx = ExprId("RAX", 64), ExprId("RBX", 64)
        tracker.values = {
            rax: frozenset({ExprInt(0x2FF8, 64)}),
            rbx: frozenset({ExprInt(1, 64)}),
        }
        tracker.update(decode("4893"))
        self.assertEqual(tracker.resolve_many(rax), [ExprInt(1, 64)])
        self.assertEqual(tracker.resolve_many(rbx), [ExprInt(0x2FF8, 64)])
        tracker.values = {
            reg: frozenset({ExprInt(1, 64), ExprInt(2, 64)}) for reg in (rax, rbx)
        }
        with patch.object(tracker, "MAX_COMBINATIONS", 2):
            with self.assertRaises(context_policy.ContextFlowLimit):
                tracker.resolve_many(rax + rbx)
            tracker.update(decode("4831c0"))
            self.assertEqual(tracker.resolve_many(rax), [ExprInt(0, 64)])
        # Memory results are unknown values, not persistent symbolic aliases.
        tracker.update(decode("488b03"))
        self.assertNotIn(rax, tracker.values)
        self.assertIsInstance(tracker.resolve_many(ExprMem(rbx, 64))[0], ExprMem)


    def test_flow_work_limit_refuses_instead_of_publishing_partial_scan(self):
        walk = context_policy.constant_blocks
        with patch.object(
            context_policy,
            "constant_blocks",
            side_effect=lambda blocks, db, **kwargs: walk(
                blocks, db, max_visits=1, **kwargs
            ),
        ):
            log = self.assert_rejected("31c0eb0083c001c3")
        self.assertIn("CFG analysis exceeds its work budget", log)


    def test_masked_memory_store_keeps_precision_across_a_cfg_edge(self):
        raw = self.masked_store_fixture("83e003eb00")
        assembly, log, status = render(raw, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertTrue(assembly)
        self.assert_rejected(
            raw.replace("48890cc500200000", "48890cc5f02f0000"),
            symbols=self.context_ranges(),
        )


    def test_real_alternate_path_cannot_be_removed_by_root_initialization(self):
        for branch in (
            "85d2740383e003",  # One path bypasses the mask with a wide index.
            "85d2740583e003eb05b800020000",  # The other path selects [0x3000].
        ):
            with self.subTest(branch=branch):
                self.assert_rejected(
                    self.masked_store_fixture(branch), symbols=self.context_ranges()
                )


    def test_backedge_mask_does_not_introduce_a_new_entry(self):
        raw = self.masked_store_fixture("83e003")
        raw = raw.replace("48890cc500200000", "48890cc500200000ffc085d275ef")
        assembly, log, status = render(raw, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertTrue(assembly)


    def test_explicit_cfg_roots_cover_all_selected_blocks(self):
        blocks, dbs = self.root_graph()
        with self.assertRaisesRegex(context_policy.ContextFlowLimit, "unreached"):
            list(context_policy.constant_blocks(blocks, dbs, roots={0x1000}))
        seen = {
            start
            for start, _, _ in context_policy.constant_blocks(
                blocks, dbs, roots={0x1000, 0x2000}
            )
        }
        self.assertEqual(seen, set(blocks))
        for roots in (set(), {0x3000}):
            with (
                self.subTest(roots=roots),
                self.assertRaisesRegex(
                    context_policy.ContextFlowLimit, "CFG analysis roots"
                ),
            ):
                list(context_policy.constant_blocks(blocks, dbs, roots=roots))
        self.assertEqual(list(context_policy.constant_blocks({}, {}, roots=set())), [])
        with self.assertRaisesRegex(
            context_policy.ContextFlowLimit, "CFG analysis roots"
        ):
            list(context_policy.constant_blocks({}, {}, roots={0x1000}))


    def test_direct_callees_remain_independent_analysis_roots(self):
        blocks, dbs = self.root_graph("e8fb0f0000c3")
        seen = set()
        for start, block, tracker in context_policy.constant_blocks(
            blocks,
            dbs,
            roots={0x1000},
            control_targets=set(TEST_LOCK_SYMBOLS.values()),
        ):
            seen.add(start)
            for line in block.lines:
                tracker.update(line)
        self.assertEqual(seen, set(blocks))


    def test_call_packet_precedes_clobber_and_keeps_return_slot_write(self):
        from miasm.expression.expression import ExprInt, ExprMem
        from test_jit_diagnostics import decode

        tracker = context_policy.FlowConstants()
        rdi = ExprId("RDI", 64)
        tracker.update(decode("bff82f0000"))
        call = decode("e800100000")
        tracker.update(call)
        packet = tracker.call_entries[id(call)]
        self.assertEqual(packet[0][rdi], frozenset({ExprInt(0x2FF8, 64)}))
        slot = ExprMem(tracker.memory.offset(ExprId("kd_entry_RSP", 64), -8), 64)
        self.assertEqual(packet[2][2][slot], frozenset({5}))
        self.assertNotIn(rdi, tracker.values)
        self.assertFalse(tracker.memory.words)


    def test_known_call_inputs_join_unknown_roots_without_equal_origins(self):
        from miasm.expression.expression import ExprInt

        blocks, dbs = self.root_graph("bff8220000e8f60f0000c3")
        rdi = ExprId("RDI", 64)
        observations = []
        for start, block, tracker in context_policy.constant_blocks(
            blocks, dbs, roots={0x1000}
        ):
            if start == 0x2000:
                observations.append(tracker.values.get(rdi, tracker.UNKNOWN))
                self.assertNotIn(rdi, tracker.origins)
            for line in block.lines:
                tracker.update(line)
        self.assertTrue(any(ExprInt(0x22F8, 64) in state for state in observations))
        self.assertTrue(all(None in state for state in observations))


    def test_nested_decoded_call_arguments_and_returns_remain_visible(self):
        def call(target, start):
            return b"\xe8" + struct.pack("<i", target - start - 5)

        for kind in ("argument", "return"):
            for clear in (False, True):
                with self.subTest(kind=kind, clear=clear):
                    caller = bytes.fromhex("bff82f0000") if kind == "argument" else b""
                    caller += call(0x2000, 0x1000 + len(caller))
                    if kind == "return":
                        caller += bytes.fromhex("488d701048ad")
                    caller += b"\xc3"
                    if kind == "argument":
                        leaf = ("31ff" if clear else "") + "4883c710488b07c3"
                    else:
                        leaf = "31c0c3" if clear else "b8f82f0000c3"
                    assembly, log, status = render(
                        "",
                        regions=[
                            (caller, 0x1000, [0x1000]),
                            (call(0x4000, 0x2000) + b"\xc3", 0x2000, [0x2000]),
                            (bytes.fromhex(leaf), 0x4000, [0x4000]),
                        ],
                        # Keep data addresses distinct from the decoded leaf.
                        symbols=context_policy.ContextSymbols(
                            {0x3008: "percpu_fixture"}, {0x3008: 0x3100}
                        ),
                        return_status=True,
                    )
                    self.assertEqual(status, 0 if clear else 2, log)
                    self.assertEqual(bool(assembly), clear)


    def test_decoded_return_memory_effects_reach_the_caller(self):
        from miasm.expression.expression import ExprInt

        blocks, dbs = translator.decode_regions(
            [
                (bytes.fromhex("e8fb0f0000c3"), 0x1000, [0x1000]),
                (bytes.fromhex("48c7042500840000f82f0000c3"), 0x2000, [0x2000]),
            ],
            TEST_LOCK_SYMBOLS["_raw_spin_unlock"],
            set(TEST_LOCK_SYMBOLS.values()),
        )
        observed = []
        for start, block, tracker in context_policy.constant_blocks(
            blocks, dbs, roots={0x1000}
        ):
            if start == 0x1005:
                observed.append(tracker.memory.byte_at(ExprInt(0x8400, 64)))
            for line in block.lines:
                tracker.update(line)
        self.assertTrue(any(state and ExprInt(0xF8, 8) in state for state in observed))


    def test_return_ownership_handles_shared_tails_and_nested_calls(self):
        from types import SimpleNamespace

        kinds = {1: "CALL", 2: "RET", 3: "RET", 4: "JMP", 5: "RET", 6: "RET"}
        blocks = {
            start: SimpleNamespace(lines=[SimpleNamespace(name=name)])
            for start, name in kinds.items()
        }
        successors = {1: {2}, 2: set(), 3: set(), 4: {2}, 5: set(), 6: set()}
        calls = {0: [(None, 1, 5), (None, 4, 6)], 1: [(None, 3, 2)]}
        returns = context_policy.call_return_edges(blocks, successors, calls, 100)
        self.assertEqual(dict(returns), {2: {5, 6}, 3: {2}})
        with self.assertRaisesRegex(context_policy.ContextFlowLimit, "CALL/RET CFG"):
            context_policy.call_return_edges(blocks, successors, calls, 1)


    def test_missing_decoded_call_packet_is_not_partial_success(self):
        with patch.object(context_policy.FlowConstants, "update"):
            log = self.assert_rejected(
                "",
                regions=[
                    (bytes.fromhex("e8fb0f0000c3"), 0x1000, [0x1000]),
                    (bytes.fromhex("c3"), 0x2000, [0x2000]),
                ],
            )
        self.assertIn("missing decoded CALL input state", log)


    def test_return_fanout_has_an_edge_budget(self):
        from types import SimpleNamespace

        blocks = {
            start: SimpleNamespace(lines=[SimpleNamespace(name="RET")])
            for start in range(1, 11)
        }
        successors = {start: set() for start in blocks}
        calls = {0: [(None, 1, target) for target in range(2, 11)]}
        with self.assertRaisesRegex(context_policy.ContextFlowLimit, "CALL/RET CFG"):
            context_policy.call_return_edges(blocks, successors, calls, 9)
        self.assertEqual(
            dict(context_policy.call_return_edges(blocks, successors, calls, 10)),
            {1: set(range(2, 11))},
        )


    def test_missing_cfg_database_is_not_partial_success(self):
        blocks, _ = self.root_graph()
        with self.assertRaisesRegex(
            context_policy.ContextFlowLimit, "location database"
        ):
            list(context_policy.constant_blocks(blocks, {}, roots=set(blocks)))
