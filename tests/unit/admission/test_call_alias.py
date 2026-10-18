"""Guest-only original CALL-memory aliases and restricted pointer provenance."""
import ctypes
import mmap
import struct
import unittest

from miasm.expression.expression import ExprId, ExprInt, ExprMem
from miasm.ir.ir import AssignBlock
from test_jit_diagnostics import decode, render, translator
from test_jit_body_witness import run_image
from context_guards import EntryGuards
from context_symbols import ContextSymbols

policy = translator.context_policy
memory_model = policy.context_memory
SYMBOLS = {"kd_raw_spin_lock_clobber_v1": 0x3000,
           "kd_raw_spin_unlock_clobber_v1": 0x4000}


class CallAliasTests(unittest.TestCase):
    def memory(self, value=0x2ff8):
        base = ExprId("source_stack", 64)
        memory = memory_model.MemoryValues(frozenset({base}))
        memory.store([({base}, {ExprInt(value, 64)}, 64)], call_return=True)
        return memory, base

    def dynamic_load(self, memory):
        return memory.load(ExprMem(ExprId("ordinary_source_pointer", 64), 64))

    def tracker(self, returned=0x2ff8):
        tracker = policy.FlowConstants()
        line = decode("e800000000")
        line.offset = returned - line.l
        # Only the established readonly service summary restores source SP
        # and callee-save state after the real lifted CALL write.
        tracker.control_calls.add(id(line))
        tracker.readonly_calls.add(id(line))
        tracker.update(line)
        tracker.update(decode("488b03"))  # MOV RAX, [RBX]
        return tracker

    def partial_tracker(self, returned, displacement=-1):
        tracker = policy.FlowConstants()
        line = decode("e800000000")
        line.offset = returned - line.l
        tracker.control_calls.add(id(line))
        tracker.readonly_calls.add(id(line))
        tracker.update(line)
        stack, result = ExprId("RSP", 64), ExprId("RAX", 64)
        tracker.update_assignments(AssignBlock({
            result: ExprMem(stack + ExprInt(displacement - 8, 64), 64)}))
        return tracker

    def add_constant(self, tracker, amount):
        tracker.update(decode((b"\x48\xba" + struct.pack("<Q", amount)).hex()))
        tracker.update(decode("4801d0"))  # ADD RAX, RDX

    def test_full_call_alternatives_and_partial_provenance_survive_untouched_join(self):
        memory, base = self.memory()
        values = self.dynamic_load(memory)
        self.assertIn(ExprInt(0x2ff8, 64), values)
        self.assertTrue(any(memory_model.has_call_alias(value) for value in values))
        self.assertFalse(any(memory_model.is_wide(value) for value in values))
        untouched = memory_model.MemoryValues(frozenset({base})).snapshot()
        memory.restore(memory.merge(memory.snapshot(), untouched))
        self.assertFalse(memory.words)  # No must-written word on the first loop visit.
        self.assertIn(ExprInt(0x2ff8, 64), self.dynamic_load(memory))
        self.assertTrue(any(memory_model.has_call_alias(value)
                            for value in self.dynamic_load(memory)))

    def test_partial_and_modulo_overlaps_do_not_become_disjoint(self):
        for start in (0, (1 << 64) - 4):
            memory, base = self.memory()
            pointer = memory.offset(base, start)
            memory = memory_model.MemoryValues(frozenset({base}))
            memory.store([({pointer}, {ExprInt(0x1122334455667788, 64)}, 64)],
                         call_return=True)
            for delta in range(-8, 9):
                with self.subTest(start=start, delta=delta):
                    values = memory.load(ExprMem(memory.offset(pointer, delta), 64))
                    if delta == 0:
                        self.assertEqual(values, (ExprInt(0x1122334455667788, 64),))
                    elif -8 < delta < 8:
                        self.assertTrue(any(memory_model.has_call_alias(v) for v in values))
                    else:
                        self.assertEqual(values, (ExprMem(memory.offset(pointer, delta), 64),))

    def test_entry_named_pointer_does_not_add_an_overlap_exclusion(self):
        guards = EntryGuards()
        stack, pointer = (ExprId("kd_entry_" + name, 64) for name in ("RSP", "RDI"))
        memory = memory_model.MemoryValues(frozenset({stack, pointer}), guards)
        memory.store([({stack}, {ExprInt(0x2ff8, 64)}, 64)], call_return=True)
        values = memory.load(ExprMem(pointer, 64))
        self.assertIn(ExprInt(0x2ff8, 64), values)
        self.assertTrue(any(memory_model.has_call_alias(value) for value in values))
        self.assertEqual(guards.conditions(), [])

    def test_arbitrary_writes_and_exhaustion_never_gain_call_provenance(self):
        for change in ("literal", "ordinary", "opaque", "wide", "second_word",
                       "budget", "combinations"):
            memory, base = self.memory()
            if change == "literal":
                memory = memory_model.MemoryValues(frozenset({base}))
                memory.store([({base}, {ExprInt(0x2ff8, 64)}, 64)])
            elif change == "ordinary":
                memory.store([({memory.offset(base, 16)}, {ExprInt(0x30, 8)}, 8)])
            elif change == "opaque":
                memory.clobber()
            elif change == "wide":
                memory.store([({base}, {memory_model.wide_value(64)}, 64)])
            elif change == "second_word":
                memory.store([({memory.offset(base, -8)}, {ExprInt(0x3000, 64)}, 64)],
                             call_return=True)
            elif change == "budget":
                memory.MAX_WORK = memory.work
            else:
                memory.MAX_COMBINATIONS = 1
            with self.subTest(change=change):
                values = self.dynamic_load(memory)
                self.assertTrue(any(memory_model.is_wide(value) for value in values))
                self.assertFalse(any(memory_model.has_call_alias(value) for value in values))

    def test_only_real_lifted_call_and_ordinary_pointer_operations_are_recognized(self):
        for raw in ("4889c3", "488d5810"):
            tracker = self.tracker()
            tracker.update(decode(raw))
            values = tracker.resolve_many(ExprId("RBX", 64))
            self.assertTrue(any(memory_model.has_call_alias(value) for value in values))
            self.assertIn(ExprInt(0x2ff8 + (16 if raw == "488d5810" else 0), 64), values)
        tracker = policy.FlowConstants()
        tracker.update(decode("48c74424f8f82f0000"))
        tracker.update(decode("488b03"))
        with self.assertRaises(policy.ContextFlowLimit):
            tracker.resolve_many(ExprId("RAX", 64))

    def test_mask_extract_shift_and_unrelated_arithmetic_keep_refusal(self):
        for raw in ("482500ffff00", "0fb7c0", "48c1e808", "4801c8", "4809c8"):
            with self.subTest(raw=raw):
                tracker = self.tracker()
                tracker.update(decode(raw))
                with self.assertRaises(policy.ContextFlowLimit):
                    tracker.resolve_many(ExprId("RAX", 64))
        # A small mask may enumerate every result without losing a candidate.
        # Those concrete alternatives still undergo the ordinary address check.
        tracker = self.tracker()
        tracker.update(decode("4883e001"))  # AND RAX, 1
        self.assertEqual(set(tracker.resolve_many(ExprId("RAX", 64))),
                         {ExprInt(0, 64), ExprInt(1, 64)})
        with self.assertRaisesRegex(policy.ContextFlowLimit, "context-sensitive"):
            tracker.update(decode("488b18"), {1: "current_task"})

    def test_partial_alias_cannot_hide_known_context_after_extraction(self):
        # One ordinary byte before the CALL slot plus seven return bytes can
        # form a pointer whose bits 8..23 equal 0x3000. It must not become an
        # unconstrained register when the source extracts those exact bits.
        tracker = self.tracker(returned=0x123456789a3000)
        tracker.update(decode("482500ffff00"))  # AND RAX, 0xffff00
        tracker.update(decode("48c1e808"))      # SHR RAX, 8
        with self.assertRaises(policy.ContextFlowLimit):
            tracker.update(decode("488b18"), {0x3000: "current_task"})
        # A complete overlap remains an explicit return-address alternative;
        # a constant offset into context storage is rejected without a mask.
        tracker = self.tracker()
        with self.assertRaisesRegex(policy.ContextFlowLimit, "context-sensitive"):
            tracker.update(decode("488b5808"), {0x3000: "current_task"})

    def test_partial_known_range_survives_add_copy_and_conflicting_join(self):
        returned, offset = 0xffffffffc0796149, 0xffff88bf869ee700
        context = 0xffff888000003000
        # The load begins one byte before the real CALL word. Seven known
        # return bytes become the high 56 bits; one unknown low byte gives
        # exactly [context, context+255] after the source ADD, with no masking.
        tracker = self.partial_tracker(returned)
        self.add_constant(tracker, offset)
        tracker.update(decode("4889c3"))  # MOV RBX, RAX
        with self.assertRaisesRegex(policy.ContextFlowLimit, "context-sensitive"):
            tracker.update(decode("488b0b"), {context + 0x55: "current_task"})

        first = self.partial_tracker(returned)
        second = self.partial_tracker(returned)
        self.add_constant(first, offset)
        self.add_constant(second, (offset + 0x10000) & ((1 << 64) - 1))
        first.restore(first.merge_state(first.snapshot(), second.snapshot()))
        first.update(decode("4889c3"))
        with self.assertRaisesRegex(policy.ContextFlowLimit, "context-sensitive"):
            first.update(decode("488b0b"), {context + 0x10055: "current_task"})
        # Joining with an ordinary untouched path cannot remove those facts.
        first.restore(first.merge_state(first.snapshot(), policy.FlowConstants().snapshot()))
        with self.assertRaisesRegex(policy.ContextFlowLimit, "context-sensitive"):
            first.update(decode("488b0b"), {context + 0x55: "current_task"})

    def test_partial_ranges_include_operand_overlap_and_modulo_wrap(self):
        returned, offset = 0xffffffffc0796149, 0xffff88bf869ee700
        context = 0xffff888000003000
        tracker = self.partial_tracker(returned)
        self.add_constant(tracker, offset)
        symbols = ContextSymbols({context + 0x103: "current_task"},
                                 {context + 0x103: context + 0x104})
        with self.assertRaisesRegex(policy.ContextFlowLimit, "context-sensitive"):
            tracker.update(decode("488b08"), symbols)  # 8 bytes overlap the range.
        outside = {context + 0x107: "current_task"}
        tracker.update(decode("488b08"), outside)

        tracker = self.partial_tracker(returned)
        known = (returned << 8) & ((1 << 64) - 1)
        self.add_constant(tracker, (-128 - known) & ((1 << 64) - 1))
        with self.assertRaisesRegex(policy.ContextFlowLimit, "context-sensitive"):
            tracker.update(decode("488b08"), {0x40: "current_task"})

    def test_unknown_high_bits_keep_known_base_without_interval_hull(self):
        returned = 0xffffffffc0796149
        # Starting seven bytes after the word retains only its high byte FF
        # as the result's low byte. The high 56 bits remain ordinary unknown.
        tracker = self.partial_tracker(returned, displacement=7)
        context = 0xffff888000003000
        tracker.update(decode("488b08"), {context: "current_task"})
        # Its known residue plus a source constant still names a known base.
        self.add_constant(tracker, context - 0xff)
        with self.assertRaisesRegex(policy.ContextFlowLimit, "context-sensitive"):
            tracker.update(decode("488b08"), {context: "current_task"})

    def test_every_partial_position_keeps_exact_mask_and_budget_loss_refuses(self):
        returned = 0x1122334455667788
        memory, slot = self.memory(returned)
        for displacement in (*range(-7, 0), *range(1, 8)):
            with self.subTest(displacement=displacement):
                values = memory.load(ExprMem(memory.offset(slot, displacement), 64))
                alias, = (value for value in values if memory_model.has_call_alias(value))
                patterns = memory_model.call_alias_patterns(alias)
                self.assertEqual(len(patterns), 1)
                mask, bits, amount = patterns[0]
                self.assertEqual(amount, 0)
                expected_mask = expected_bits = 0
                for index in range(8):
                    original = index + displacement
                    if 0 <= original < 8:
                        expected_mask |= 0xff << (index * 8)
                        expected_bits |= ((returned >> (original * 8)) & 0xff) << (index * 8)
                self.assertEqual((mask, bits), (expected_mask, expected_bits))
                # Every placement keeps its known base after an arbitrary
                # modulo offset; high-prefix placements also keep the final
                # byte of their exact range, not just its first address.
                context = 0xffff888000003000
                shifted = alias + ExprInt((context - bits) & ((1 << 64) - 1), 64)
                self.assertEqual(policy.context_reference(
                    shifted, None, 0, {context: "current_task"}), "current_task")
                unknown = ((1 << 64) - 1) ^ mask
                if unknown & (unknown + 1) == 0:
                    last = (context + unknown) & ((1 << 64) - 1)
                    self.assertEqual(policy.context_reference(
                        shifted, None, 0, {last: "current_task"}), "current_task")
        # The finite pattern union may not erase an alternative on overflow.
        values = [memory_model.call_alias_value(
                      64, index, {(0xffffffffffffff00, index << 8, 0)})
                  for index in range(memory_model.MAX_CALL_PATTERNS + 1)]
        wide = memory_model.merge_call_aliases(values, 64, "budget")
        self.assertTrue(memory_model.is_wide(wide))
        tracker = policy.FlowConstants()
        reg = ExprId("RAX", 64)
        tracker.origins[reg] = wide
        tracker.restore(tracker.merge_state(tracker.snapshot(), policy.FlowConstants().snapshot()))
        with self.assertRaises(policy.ContextFlowLimit):
            tracker.resolve_many(reg)

    def test_stored_and_indirect_control_reuse_are_not_ordinary_pointer_uses(self):
        tracker = self.tracker()
        tracker.update(decode("488945e0"))
        tracker.update(decode("488b75e0"))
        with self.assertRaises(policy.ContextFlowLimit):
            tracker.resolve_many(ExprId("RSI", 64))
        for raw in ("ffe0", "ff23"):
            tracker = self.tracker()
            line = decode(raw)
            rejection = policy.instruction_rejection(
                line, 0x1000, tracker.lifter.loc_db, {}, constants=tracker)
            self.assertIsNotNone(rejection)
            self.assertIn("indirect control", rejection[0])
        for invalidate_call_record in (False, True):
            tracker = self.tracker()
            tracker.update(decode("4889c4"))  # MOV RSP, RAX
            if invalidate_call_record:
                tracker.update(decode("48c745e000000000"))
                self.assertIsNone(tracker.memory.call_words)
            with self.assertRaisesRegex(policy.ContextFlowLimit, "return control"):
                tracker.update(decode("c3"))

    def test_join_with_unconstrained_path_does_not_erase_restricted_use(self):
        tracker = self.tracker()
        loaded = tracker.snapshot()
        untouched = policy.FlowConstants().snapshot()
        tracker.restore(tracker.merge_state(loaded, untouched))
        tracker.update(decode("48c1e808"))
        with self.assertRaises(policy.ContextFlowLimit):
            tracker.resolve_many(ExprId("RAX", 64))

    def test_distinct_partial_reads_cannot_cancel_as_one_unknown(self):
        tracker = self.tracker()
        left = ExprMem(ExprId("RBX", 64), 64)
        right = ExprMem(ExprId("RDI", 64), 64)
        tracker.update_assignments(AssignBlock({ExprId("RAX", 64): left - right}))
        with self.assertRaises(policy.ContextFlowLimit):
            tracker.resolve_many(ExprId("RAX", 64))

    def test_list_pointer_loop_needs_no_address_guard(self):
        # The first iteration has no CALL bytes; later iterations can alias
        # exactly the same real return slot. This is the xattr traversal shape.
        prefix = bytes.fromhex("488b5df04c8b65f8")
        loop = 0x1000 + len(prefix)
        raw = prefix + bytes.fromhex("488b73104c89e7")
        target = 0x2000
        raw += b"\xe8" + struct.pack("<i", target - (0x1000 + len(raw) + 5))
        raw += bytes.fromhex("85c07405")
        raw += bytes.fromhex("488b1b")
        raw += b"\xeb" + struct.pack("b", loop - (0x1000 + len(raw) + 2))
        raw += b"\xc3"
        options = {}
        assembly, log, status = render(
            raw.hex(), kernel_symbols=SYMBOLS | {"ktime_get": target}, abi=1,
            address_guard_capable=True, build_options=options, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertEqual(options["requirements"], 0)
        self.assertNotIn(b"kd_address_guard_failed_", assembly)
        self.assertNotIn("ADDRESS_GUARDED_ADMISSION", log)

    def test_real_emitted_partial_and_full_aliases_keep_source_effects(self):
        # Execute the real wrapper and lowering. The fixture substitutes only
        # the scalar ktime service bridge; its original virtual CALL word and
        # all aliasing loads/dereferences execute unchanged in generated code.
        # Source dispatch uses the production signed-32-bit text address form.
        # Linux x86 MAP_32BIT gives a real data pointer that also fits that form;
        # this is fixture memory only, never a change to generated dispatch.
        with mmap.mmap(-1, mmap.PAGESIZE,
                       flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS | 0x40) as storage:
            pointer = ctypes.addressof(ctypes.c_char.from_buffer(storage))
            self.assertLess(pointer + 0x1000, 1 << 31)
            value = 0x1122334455667788
            ctypes.c_ulong.from_address(pointer).value = value
            self.execute_aliases(pointer, value)

    def execute_aliases(self, pointer, value):
        ordinary = ctypes.c_ulong(pointer)
        for delta in (None, 0, -1):
            returned = pointer if delta != -1 else pointer >> 8
            entry, target = returned - 9, returned + 0x1000
            raw = bytes.fromhex("488b5df8")  # captured BP-relative source spill
            raw += b"\xe8" + struct.pack("<i", target - returned)
            raw += bytes.fromhex("488b03488b10c3")
            options = {}
            assembly, log, status = render(
                raw.hex(), entry=entry, kernel_symbols=SYMBOLS | {"ktime_get": target},
                abi=1,
                body_witness=True, build_options=options, return_status=True)
            self.assertEqual(status, 0, log)
            self.assertEqual(options["requirements"], 0)
            self.assertNotIn(b"kd_address_guard_failed_", assembly)
            observed = []

            def initialize(regs, stack):
                regs[2] = regs[1] + 32
                if delta is None:
                    stack[11] = ctypes.addressof(ordinary)
                else:
                    source = regs[1] - 8 + delta
                    stack[7] = 0xa5a5a5a5a5a5a5a5
                    if delta == -1:
                        ctypes.c_ubyte.from_address(source).value = pointer & 0xff
                    stack[11] = source

            def resume(regs, args, stack):
                if args[0] != 5:
                    return False
                self.assertFalse(observed)
                self.assertEqual((regs[0], stack[7]), (target, returned))
                self.assertEqual(ctypes.c_ulong.from_address(regs[8]).value, pointer)
                observed.append(stack[7])
                regs[0], regs[1], regs[12] = stack[7], regs[1] + 8, 0
                return True

            with self.subTest(delta=delta):
                regs, args = run_image(assembly, [entry], initialize, resume=resume,
                                       abi=1)[0]
                self.assertEqual(observed, [returned])
                self.assertEqual(regs[14], value)
                self.assertEqual((regs[0], args[1]), (0x4444, 1))


if __name__ == "__main__":
    unittest.main()
