"""Guest-only C-object/control-token separation; ordinary CALL aliases remain."""
import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

from miasm.expression.expression import ExprId, ExprInt, ExprMem
from miasm.ir.ir import AssignBlock
from test_jit_diagnostics import decode, render, translator
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
                self.assertTrue(any(memory_model.is_wide(value) for value in result))

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

    def test_coordinator_does_not_classify_missing_string_call_as_readonly(self):
        raw = "488b5dc8488b75c0488b7b10e8ef0f0000488b5b08488b03c3"
        options = {}
        assembly, log, status = render(
            raw, abi=1, kernel_symbols=SYMBOLS,
            string_services_capable=True, audited_strings_capable=True,
            build_options=options, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertEqual(options["requirements"], 0)
        self.assertNotIn(b"KD_HOSTCALL id=4", assembly)
        self.assertNotIn(b"KD_DIRECT_STRING", assembly)
        self.assertRegex(assembly, rb"QWORD PTR \[R13\], R(?:14|15)")

    def memcpy_transfer(self):
        # The caller operands and learned helper are the actual xattr shape.
        # The copy is an ordinary CALL with the original byte-memory model,
        # not a readonly service or a specially classified C control token.
        tracker = FlowConstants()
        for raw in ("488b5dc8", "4c8b65c0", "488b7310", "4c89e7"):
            tracker.update(decode(raw))
        self.call(tracker, offset=0xffffffffc0796144)
        for raw in ("488b5318", "488b7db8", "488d7320"):
            tracker.update(decode(raw))
        self.assertFalse(any(memory_model.is_wide(value) for value in
                             tracker.resolve_many(ExprId("RDI", 64))))
        line = decode("e800000000")
        line.offset = 0xffffffffc0796167
        tracker.update(line)
        tracker.restore(tracker.call_entries[id(line)])
        # Captured __memcpy -> memcpy_erms body: MOV RAX,RDI; MOV RCX,RDX;
        # REP MOVSB; RET. Real byte writes and all DF/count possibilities stay.
        for raw in ("4889f8", "4889d1", "f3a4", "c3"):
            tracker.update(decode(raw))
        tracker.update(decode("488b7dd0"))
        return tracker

    def test_captured_memcpy_preserves_ordinary_calls_and_all_copy_writes(self):
        tracker = self.memcpy_transfer()
        # This final value is uncertain under the ordinary byte analysis. The
        # real xattr body passes it directly to terminal physical-owner unlock
        # handling; it never dereferences it in another generated instruction.
        with self.assertRaises(ContextFlowLimit):
            tracker.resolve_many(ExprId("RDI", 64))
        self.assertTrue(tracker.memory.entry_spills_blocked)

    def test_generic_call_replaces_token_and_uses_original_ret_analysis(self):
        tracker = FlowConstants(scoped_calls=True)
        self.call(tracker)
        ordinary = decode("e800000000")
        ordinary.offset = 0x2000
        tracker.update(ordinary)
        tracker.restore(tracker.call_entries[id(ordinary)])
        self.assertEqual(tracker.memory.control_words, {})
        returned = decode("c3")
        tracker.update(returned)
        self.assertEqual(tracker.return_targets[id(returned)], frozenset({0x2005}))
        # A caller which deliberately returns through its earlier API token is
        # outside the audited scratch contract; no special RET exception exists.
        tracker = FlowConstants()
        self.call(tracker)
        tracker.update(decode("4883ec08"))
        with self.assertRaisesRegex(ContextFlowLimit, "control scratch"):
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
        fixtures = Path(__file__).with_name("fixtures")
        metadata = (
            ("xattr-memcpy-kernel.bin", 0xffffffff81ed9000, 0xffffffff81ed94c0,
             "e89947113d6232f9fdacd43088f29fa97e92b74a0dfe60d8aaad507f2c796a0e"),
            ("xattr-memcpy-caller.bin", 0xffffffffc0796000, 0xffffffffc07961ae,
             "8e1ea5d9987ce22e9e7ddfb45c6b57670ed45727c737765ddd2be2fa63ed40a0"),
        )
        regions = []
        for name, start, root, expected in metadata:
            original = (fixtures / name).read_bytes()
            self.assertEqual(len(original), 8192)
            self.assertEqual(hashlib.sha256(original).hexdigest(), expected)
            data = bytearray(original)
            if root == 0xffffffffc07961ae and not string_call:
                offset = 0xffffffffc0796144 - start
                data[offset:offset + 5] = b"\x90" * 5
            regions.append((bytes(data), start, [root]))
        return regions

    def test_raw_captured_graph_returns_from_copy_and_reaches_terminal_unlock(self):
        symbols = {"strcmp": 0xffffffff81e00b90,
                   "kd_raw_spin_lock_clobber_v1": 0xffffffffc0864000,
                   "kd_raw_spin_unlock_clobber_v1": 0xffffffffc0864840,
                   "__x86_return_thunk": 0xffffffff822024e0}
        # This historical copy fixture omits the unavailable string callee.
        # Full ordinary byte-call coverage is in test_ordinary_callee_bytes.
        # Merely resolving the copy symbol must not change its ordinary CALL,
        # full copied-memory effects or source RET dispatch.
        for copy_symbol in (False, True):
            with self.subTest(copy_symbol=copy_symbol):
                options, tables, selected = {}, [], set()
                original_find = translator.indirect_jump.find
                original_policy = translator.find_segment_policy_error
                def observe_returns(*args, **kwargs):
                    result = original_find(*args, **kwargs)
                    tables.append({source: tuple(targets) for source, targets in args[2].items()})
                    return result
                def observe_policy(*args, **kwargs):
                    selected.update(line.offset for block in args[0].values() for line in block.lines)
                    return original_policy(*args, **kwargs)
                with patch.object(translator.indirect_jump, "find", side_effect=observe_returns), \
                     patch.object(translator, "find_segment_policy_error", side_effect=observe_policy):
                    assembly, log, status = render(
                        "", regions=self.captured_regions(string_call=False), entry=0xffffffffc07961ae, abi=1,
                        kernel_symbols=symbols | ({"__memcpy": 0xffffffff81ed94c0}
                                                   if copy_symbol else {}),
                        string_services_capable=True, audited_strings_capable=True,
                        return_status=True, build_options=options)
                self.assertEqual(status, 0, log)
                self.assertEqual(options["requirements"], 0)
                self.assertNotIn(b"KD_HOSTCALL id=4 symbol=strcmp", assembly)
                self.assertRegex(assembly, rb"REP\s+MOVSB")
                self.assertTrue(any(0xffffffffc079616c in targets
                                    for table in tables for targets in table.values()))
                self.assertTrue({0xffffffff81ed94fa, 0xffffffff81ed94fc,
                                 0xffffffffc079616c, 0xffffffffc079617d} <= selected)
                self.assertNotIn("ADDRESS_GUARDED_ADMISSION", log)
                self.assertNotIn(b"kd_address_guard_failed_", assembly)


if __name__ == "__main__":
    unittest.main()
