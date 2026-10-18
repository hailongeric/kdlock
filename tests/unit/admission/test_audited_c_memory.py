"""Guest-only C-object/control-token separation; ordinary CALL aliases remain."""
import json
import unittest
from pathlib import Path

from miasm.expression.expression import ExprId, ExprInt, ExprMem
from miasm.ir.ir import AssignBlock
from test_jit_diagnostics import decode, render
from context_values import FlowConstants, ContextFlowLimit
import context_memory as memory_model

SYMBOLS = {"strcmp": 0x2000,
           "kd_raw_spin_lock_clobber_v1": 0x3000,
           "kd_raw_spin_unlock_clobber_v1": 0x4000}


class AuditedCMemoryTests(unittest.TestCase):
    def memory(self):
        stack = ExprId("source_stack", 64)
        return memory_model.MemoryValues(frozenset({stack})), stack

    def write_token(self, memory, slot, value=0x123456789abcdef0, *, audited=True):
        memory.store([({slot}, {ExprInt(value, 64)}, 64)],
                     call_return=True, audited_call=audited)

    def call(self, tracker, *, audited=True, writer=0, offset=0x1000):
        line = decode("e800000000")
        line.offset = offset
        tracker.control_calls.add(id(line))
        if writer:
            tracker.writer_calls[id(line)] = writer
        else:
            tracker.readonly_calls.add(id(line))
        if audited:
            tracker.audited_c_calls.add(id(line))
        tracker.update(line)
        return line

    def test_only_audited_token_is_absent_from_ordinary_object_bytes(self):
        for audited in (False, True):
            memory, slot = self.memory()
            self.write_token(memory, slot, audited=audited)
            load = ExprMem(ExprId("ordinary_object", 64), 64)
            result = memory.load(load)
            if audited:
                self.assertEqual(result, (load,))
                self.assertEqual(memory.control_words,
                                 {ExprMem(slot, 64): frozenset({0x123456789abcdef0})})
                self.assertEqual(memory.cells, {})
            else:
                self.assertIn(ExprInt(0x123456789abcdef0, 64), result)
                self.assertTrue(any(memory_model.has_call_alias(value) for value in result))

    def test_explicit_full_partial_modular_reads_and_writes_are_refused(self):
        for start in (0, (1 << 64) - 4):
            memory, stack = self.memory()
            slot = memory.offset(stack, start)
            self.write_token(memory, slot)
            for delta in range(-7, 8):
                at = memory.offset(slot, delta)
                with self.subTest(start=start, delta=delta):
                    with self.assertRaises(memory_model.AuditedScratchAccess):
                        memory.load(ExprMem(at, 64))
                    with self.assertRaises(memory_model.AuditedScratchAccess):
                        memory.store([({at}, {ExprInt(1, 64)}, 64)])
            for delta in (-8, 8):
                at = memory.offset(slot, delta)
                self.assertEqual(memory.load(ExprMem(at, 64)), (ExprMem(at, 64),))

    def test_pointer_copy_and_imminent_typed_arguments_keep_observer_refusal(self):
        tracker = FlowConstants()
        self.call(tracker)
        tracker.update(decode("488d4424f8"))  # LEA RAX, [RSP-8]
        tracker.update(decode("4889c3"))      # MOV RBX, RAX
        with self.assertRaisesRegex(ContextFlowLimit, "control scratch"):
            tracker.update(decode("488b03"))  # MOV RAX, [RBX]
        for raw in ("488d7c24f8", "488d7424f7"):
            tracker = FlowConstants()
            tracker.update(decode(raw))
            with self.assertRaisesRegex(ContextFlowLimit, "control scratch"):
                self.call(tracker)
        tracker = FlowConstants()
        self.call(tracker)
        tracker.update(decode("488d7c24f8"))  # RDI names the previous token.
        tracker.update(decode("4883ec20"))    # New CALL will use another slot.
        with self.assertRaisesRegex(ContextFlowLimit, "control scratch"):
            self.call(tracker, offset=0x2000)

    def test_typed_overwrite_replaces_old_token_without_resetting_data(self):
        memory, slot = self.memory()
        object_at = memory.offset(slot, 32)
        memory.store([({object_at}, {ExprInt(0x3000, 64)}, 64)])
        self.write_token(memory, slot, 0x1111111111111111, audited=False)
        self.write_token(memory, slot, 0x2222222222222222)
        self.assertEqual(memory.control_words[ExprMem(slot, 64)],
                         frozenset({0x2222222222222222}))
        self.assertEqual(memory.load(ExprMem(object_at, 64)), (ExprInt(0x3000, 64),))
        self.assertFalse(memory.call_words)
        self.write_token(memory, slot, 0x3333333333333333, audited=False)
        self.assertEqual(memory.control_words, {})
        self.assertEqual(memory.load(ExprMem(slot, 64)),
                         (ExprInt(0x3333333333333333, 64),))

    def test_control_joins_retain_observers_and_ordinary_path_aliases(self):
        memory, slot = self.memory()
        untouched = memory.snapshot()
        self.write_token(memory, slot, 0x1111111111111111)
        typed = memory.snapshot()
        memory.restore(untouched)
        self.write_token(memory, slot, 0x2222222222222222, audited=False)
        ordinary = memory.snapshot()
        memory.restore(memory.merge(typed, ordinary))
        with self.assertRaises(memory_model.AuditedScratchAccess):
            memory.load(ExprMem(slot, 64))
        values = memory.load(ExprMem(ExprId("ordinary_object", 64), 64))
        self.assertTrue(ExprInt(0x2222222222222222, 64) in values
                        or any(memory_model.is_wide(value) for value in values))
        memory.restore(memory.merge(typed, untouched))
        with self.assertRaises(memory_model.AuditedScratchAccess):
            memory.load(ExprMem(slot, 64))

    def test_preexisting_wide_memory_and_known_context_data_are_not_erased(self):
        tracker = FlowConstants()
        tracker.memory.store([({ExprId("unknown_pointer", 64)},
                               {memory_model.wide_value(64)}, 64)])
        self.call(tracker)
        tracker.update(decode("488b03"))
        with self.assertRaises(ContextFlowLimit):
            tracker.resolve_many(ExprId("RAX", 64))
        tracker = FlowConstants()
        tracker.update_assignments(AssignBlock({
            ExprMem(ExprId("RBP", 64) - ExprInt(32, 64), 64): ExprInt(0x3000, 64)}))
        self.call(tracker)
        tracker.update(decode("488b45e0"))
        with self.assertRaisesRegex(ContextFlowLimit, "context-sensitive"):
            tracker.update(decode("488b00"), {0x3000: "current_task"})

    def test_writer_keeps_all_64_ordinary_destination_bytes(self):
        tracker = FlowConstants()
        tracker.update(decode("488d7dc0"))  # LEA RDI, [RBP-64]
        self.call(tracker, writer=64)
        base = tracker.origins[ExprId("RBP", 64)]
        for offset in range(-64, 0):
            self.assertIn(tracker.memory.offset(base, offset), tracker.memory.cells)
        self.assertEqual(len(tracker.memory.control_words), 1)

    def test_unproved_control_identity_and_budget_fail_closed(self):
        memory, slot = self.memory()
        with self.assertRaises(memory_model.AuditedScratchAccess):
            self.write_token(memory, ExprId("untracked_stack", 64))
        self.write_token(memory, slot)
        memory.MAX_WORK = memory.work
        with self.assertRaises(memory_model.AuditedScratchAccess):
            memory.load(ExprMem(ExprId("ordinary_object", 64), 64))

    def test_coordinator_selects_typed_contract_without_pointer_guards(self):
        # List-node -> original strcmp -> list-node repeats. The original
        # virtual CALL store remains emitted; no stack exclusion is introduced.
        raw = "488b5dc8488b75c0488b7b10e8ef0f0000488b5b08488b03c3"
        assembly, log, status = render(
            raw, abi=1, kernel_symbols=SYMBOLS,
            string_services_capable=True, audited_strings_capable=True,
            return_status=True)
        self.assertEqual(status, 0, log)
        self.assertIn(b"KD_HOSTCALL id=4 symbol=strcmp", assembly)
        self.assertRegex(assembly, rb"QWORD PTR \[R13\], R(?:14|15)")
        self.assertNotIn("ADDRESS_GUARDED_ADMISSION", log)

    def memcpy_transfer(self, *, audited_copy):
        # The caller operands and learned helper are the actual xattr shape.
        # Compare the original assembly-CALL model with the explicit C-copy
        # contract. Both execute the same actual byte-memory transfer model.
        tracker = FlowConstants()
        for raw in ("488b5dc8", "4c8b65c0", "488b7310", "4c89e7"):
            tracker.update(decode(raw))
        self.call(tracker, offset=0xffffffffc0796144)
        for raw in ("488b5318", "488b7db8", "488d7320"):
            tracker.update(decode(raw))
        self.assertFalse(any(memory_model.has_call_alias(value) for value in
                             tracker.resolve_many(ExprId("RDI", 64))))
        line = decode("e800000000")
        line.offset = 0xffffffffc0796167
        if audited_copy:
            tracker.audited_c_calls.add(id(line))
            tracker.audited_copy_calls.add(id(line))
        tracker.update(line)
        tracker.restore(tracker.call_entries[id(line)])
        # Captured __memcpy -> memcpy_erms body: MOV RAX,RDI; MOV RCX,RDX;
        # REP MOVSB; RET. Real byte writes and all DF/count possibilities stay.
        for raw in ("4889f8", "4889d1", "f3a4", "c3"):
            tracker.update(decode(raw))
        tracker.update(decode("488b7dd0"))
        return tracker

    def test_captured_memcpy_preserves_ordinary_calls_and_all_copy_writes(self):
        tracker = self.memcpy_transfer(audited_copy=False)
        with self.assertRaises(ContextFlowLimit):
            tracker.resolve_many(ExprId("RDI", 64))
        tracker = self.memcpy_transfer(audited_copy=True)
        self.assertTrue(tracker.resolve_many(ExprId("RDI", 64)))
        # The unknown destination stores actually occurred. In particular,
        # entry spill identities cannot be reacquired after the decoded copy.
        self.assertTrue(tracker.memory.entry_spills_blocked)
        self.assertIsNone(tracker.memory.call_words)

    def test_plain_ret_keeps_all_targets_across_may_token_joins(self):
        tracker = FlowConstants(scoped_calls=True)
        stack = tracker.origins[ExprId("RSP", 64)]
        untouched = tracker.snapshot()
        tracker.memory.store([({stack}, {ExprInt(0x2000, 64)}, 64)],
                             call_return=True, audited_call=True)
        tracker.restore(tracker.merge_state(tracker.snapshot(), untouched))
        line = decode("c3")
        tracker.update(line)
        self.assertNotIn(id(line), tracker.return_targets)
        # The same union must not turn an explicit data observer into RET.
        tracker.restore(untouched)
        tracker.memory.store([({stack}, {ExprInt(0x2000, 64)}, 64)],
                             call_return=True, audited_call=True)
        with self.assertRaisesRegex(ContextFlowLimit, "control scratch"):
            tracker.update(decode("488b0424"))
        tracker.update(decode("4883c401"))
        with self.assertRaisesRegex(ContextFlowLimit, "partially overlaps"):
            tracker.update(decode("c3"))

    def test_decoded_copy_preserves_known_context_byte_effects(self):
        tracker = FlowConstants()
        # The source byte is known context-derived data. The real copy store
        # into an unresolved destination must retain that byte, not reset the
        # entire object state to ordinary unknown or call memcpy readonly.
        tracker.update_assignments(AssignBlock({
            ExprMem(ExprId("RBP", 64) - ExprInt(32, 64), 8): ExprInt(0x30, 8)}))
        tracker.update(decode("488d75e0"))
        tracker.update(decode("488b7dd0"))  # Unknown destination from another live local.
        line = decode("e800000000")
        line.offset = 0x1000
        tracker.audited_c_calls.add(id(line))
        tracker.audited_copy_calls.add(id(line))
        tracker.update(line)
        tracker.restore(tracker.call_entries[id(line)])
        tracker.update(decode("a4"))  # The original MOVSB effect.
        self.assertIn(ExprInt(0x30, 8), tracker.memory.default)
        self.assertTrue(any(memory_model.is_wide(value) for value in
                            tracker.memory.load(ExprMem(ExprId("later_object", 64), 64))))

    def captured_regions(self, *, string_call=True):
        # Exact instructions from the drained candidate2 diagnostic admission
        # graph, including list loop, all result paths, clobber endpoint and
        # runtime-patched __memcpy -> memcpy_erms -> REP MOVSB -> RET.
        graph = json.loads(Path(__file__).with_name("fixtures").joinpath(
            "xattr_memcpy_scoped.json").read_text())
        roots = (0xffffffffc07961ae, 0xffffffff81ed94c0)
        regions = []
        for root in roots:
            blocks = [block for block in graph
                      if (int(block["start"], 16) >> 24) == (root >> 24)]
            instructions = [line for block in blocks for line in block["instructions"]]
            start = min(int(line["ip"], 16) for line in instructions)
            end = max(int(line["ip"], 16) + line["length"] for line in instructions)
            data = bytearray(b"\xcc" * (end - start))
            for line in instructions:
                offset = int(line["ip"], 16) - start
                data[offset:offset + line["length"]] = bytes.fromhex(line["bytes"])
            if root == roots[0] and not string_call:
                offset = 0xffffffffc0796144 - start
                data[offset:offset + 5] = b"\x90" * 5
            regions.append((bytes(data), start, [root]))
        return regions

    def test_captured_graph_needs_actual_typed_api_and_resolved_copy_contract(self):
        symbols = {"strcmp": 0xffffffff81e00b90,
                   "kd_raw_spin_lock_clobber_v1": 0xffffffffc0864000,
                   "kd_raw_spin_unlock_clobber_v1": 0xffffffffc0864840}
        for string_call, copy_symbol in ((True, True), (True, False), (False, True)):
            with self.subTest(string_call=string_call, copy_symbol=copy_symbol):
                options = {}
                assembly, log, status = render(
                    "", regions=self.captured_regions(string_call=string_call),
                    entry=0xffffffffc07961ae, abi=1,
                    kernel_symbols=symbols | ({"__memcpy": 0xffffffff81ed94c0}
                                               if copy_symbol else {}),
                    string_services_capable=True, audited_strings_capable=True,
                    return_status=True, build_options=options)
                accepted = string_call and copy_symbol
                self.assertEqual(status, 0 if accepted else 2, log)
                if accepted:
                    self.assertEqual(options["requirements"], 4)
                    self.assertIn(b"KD_HOSTCALL id=4 symbol=strcmp", assembly)
                    self.assertRegex(assembly, rb"REP\s+MOVSB")
                    self.assertNotIn("ADDRESS_GUARDED_ADMISSION", log)
                    self.assertNotIn(b"kd_address_guard_failed_", assembly)
                else:
                    self.assertEqual(assembly, b"")


if __name__ == "__main__":
    unittest.main()
