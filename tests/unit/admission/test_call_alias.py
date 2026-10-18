"""Guest-only conservative CALL aliases and isolated original-load lowering."""
import ctypes
import mmap
import struct
import unittest
from unittest.mock import patch

from miasm.expression.expression import ExprId, ExprInt, ExprMem
from miasm.ir.ir import AssignBlock
from test_jit_diagnostics import decode, render, translator
from test_jit_body_witness import run_image
from context_guards import EntryGuards

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

    def tracker(self, returned=0x2ff8, displacement=None):
        tracker = policy.FlowConstants()
        line = decode("e800000000")
        line.offset = returned - line.l
        tracker.control_calls.add(id(line))
        tracker.readonly_calls.add(id(line))
        tracker.update(line)
        if displacement is None:
            tracker.update(decode("488b03"))
        else:
            tracker.update_assignments(AssignBlock({ExprId("RAX", 64):
                ExprMem(ExprId("RSP", 64) + ExprInt(displacement - 8, 64), 64)}))
        return tracker

    def assert_wide(self, values):
        self.assertTrue(any(memory_model.is_wide(value) for value in values))

    def add_constant(self, tracker, amount):
        tracker.update(decode((b"\x48\xba" + struct.pack("<Q", amount)).hex()))
        tracker.update(decode("4801d0"))

    def test_ordinary_call_bytes_keep_conservative_aliases_through_join(self):
        memory, base = self.memory()
        self.assert_wide(self.dynamic_load(memory))
        self.assertEqual(memory.load(ExprMem(base, 64)), (ExprInt(0x2ff8, 64),))
        untouched = memory_model.MemoryValues(frozenset({base})).snapshot()
        memory.restore(memory.merge(memory.snapshot(), untouched))
        self.assert_wide(self.dynamic_load(memory))

    def test_partial_and_modulo_overlaps_keep_the_original_byte_model(self):
        for start in (0, (1 << 64) - 4):
            memory, base = self.memory()
            pointer = memory.offset(base, start)
            memory = memory_model.MemoryValues(frozenset({base}))
            memory.store([({pointer}, {ExprInt(0x1122334455667788, 64)}, 64)], call_return=True)
            for delta in range(-8, 9):
                with self.subTest(start=start, delta=delta):
                    operand = ExprMem(memory.offset(pointer, delta), 64)
                    values = memory.load(operand)
                    if delta == 0:
                        self.assertEqual(values, (ExprInt(0x1122334455667788, 64),))
                    elif -8 < delta < 8:
                        self.assert_wide(values)
                    else:
                        self.assertEqual(values, (operand,))

    def test_entry_identity_does_not_authorize_an_unchecked_alias_exclusion(self):
        guards = EntryGuards()
        stack, pointer = (ExprId("kd_entry_" + name, 64) for name in ("RSP", "RDI"))
        memory = memory_model.MemoryValues(frozenset({stack, pointer}), guards)
        memory.store([({stack}, {ExprInt(0x2ff8, 64)}, 64)], call_return=True)
        values = memory.load(ExprMem(pointer, 64))
        self.assertTrue(any(memory_model.is_wide(value) for value in values)
                        or guards.conditions())

    def test_arbitrary_writes_and_exhaustion_cannot_become_ordinary_unknown(self):
        for change in ("literal", "ordinary", "opaque", "wide", "budget", "combinations"):
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
            elif change == "budget":
                memory.MAX_WORK = memory.work
            else:
                memory.MAX_COMBINATIONS = 1
            with self.subTest(change=change):
                self.assert_wide(self.dynamic_load(memory))

    def test_copies_and_constant_offsets_do_not_relax_widened_values(self):
        for raw in ("4889c3", "488d5810"):
            tracker = self.tracker()
            tracker.update(decode(raw))
            with self.assertRaises(policy.ContextFlowLimit):
                tracker.resolve_many(ExprId("RBX", 64))

    def test_nonlinear_operations_refuse_unless_all_outputs_are_enumerated(self):
        for raw in ("482500ffff00", "0fb7c0", "48c1e808", "4801c8", "4809c8"):
            with self.subTest(raw=raw):
                tracker = self.tracker()
                tracker.update(decode(raw))
                with self.assertRaises(policy.ContextFlowLimit):
                    tracker.resolve_many(ExprId("RAX", 64))
        tracker = self.tracker()
        tracker.update(decode("4883e001"))
        self.assertEqual(set(tracker.resolve_many(ExprId("RAX", 64))),
                         {ExprInt(0, 64), ExprInt(1, 64)})
        with self.assertRaises(policy.ContextFlowLimit):
            tracker.update(decode("488b18"), {1: "current_task"})

    def test_partial_alias_cannot_hide_context_after_extraction(self):
        tracker = self.tracker(returned=0x123456789a3000)
        tracker.update(decode("482500ffff00"))
        tracker.update(decode("48c1e808"))
        with self.assertRaises(policy.ContextFlowLimit):
            tracker.update(decode("488b18"), {0x3000: "current_task"})

    def test_high_prefix_plus_offset_and_conflicting_joins_keep_refusal(self):
        offset = 0xffff88bf869ee700
        first = self.tracker(0xffffffffc0796149, displacement=-1)
        second = self.tracker(0xffffffffc0796149, displacement=-1)
        self.add_constant(first, offset)
        self.add_constant(second, (offset + 0x10000) & ((1 << 64) - 1))
        first.restore(first.merge_state(first.snapshot(), second.snapshot()))
        with self.assertRaises(policy.ContextFlowLimit):
            first.update(decode("488b08"), {0xffff888000003055: "current_task"})

    def test_wrap_and_operand_boundary_values_do_not_erase_widening(self):
        tracker = self.tracker(0xffffffffc0796149, displacement=-1)
        known = (0xffffffffc0796149 << 8) & ((1 << 64) - 1)
        self.add_constant(tracker, (-128 - known) & ((1 << 64) - 1))
        with self.assertRaises(policy.ContextFlowLimit):
            tracker.update(decode("488b08"), {0x40: "current_task"})

    def test_unknown_high_bits_do_not_gain_a_pointer_exception(self):
        tracker = self.tracker(0xffffffffc0796149, displacement=7)
        with self.assertRaises(policy.ContextFlowLimit):
            tracker.update(decode("488b08"), {0xffff888000003000: "current_task"})

    def test_all_fourteen_partial_positions_remain_conservative(self):
        memory, base = self.memory(0x1122334455667788)
        for displacement in (*range(-7, 0), *range(1, 8)):
            with self.subTest(displacement=displacement):
                self.assert_wide(memory.load(ExprMem(memory.offset(base, displacement), 64)))

    def test_stored_indirect_control_and_stack_reuse_keep_refusal(self):
        tracker = self.tracker()
        tracker.update(decode("488945e0"))
        tracker.update(decode("488b75e0"))
        with self.assertRaises(policy.ContextFlowLimit):
            tracker.resolve_many(ExprId("RSI", 64))
        for raw in ("ffe0", "ff20"):
            tracker = self.tracker()
            line = decode(raw)
            rejection = policy.instruction_rejection(
                line, 0x1000, tracker.lifter.loc_db, {}, constants=tracker)
            self.assertIsNotNone(rejection)
        for later_store in (False, True):
            tracker = self.tracker()
            tracker.update(decode("4889c4"))
            if later_store:
                tracker.update(decode("48c745e000000000"))
            with self.assertRaises(policy.ContextFlowLimit):
                tracker.update(decode("c3"), {})

    def test_join_with_untouched_path_does_not_erase_widening(self):
        tracker = self.tracker()
        tracker.restore(tracker.merge_state(tracker.snapshot(), policy.FlowConstants().snapshot()))
        tracker.update(decode("48c1e808"))
        with self.assertRaises(policy.ContextFlowLimit):
            tracker.resolve_many(ExprId("RAX", 64))

    def test_distinct_uncertain_reads_cannot_cancel_as_the_same_value(self):
        tracker = self.tracker()
        tracker.update_assignments(AssignBlock({ExprId("RAX", 64):
            ExprMem(ExprId("RBX", 64), 64) - ExprMem(ExprId("RDI", 64), 64)}))
        with self.assertRaises(policy.ContextFlowLimit):
            tracker.resolve_many(ExprId("RAX", 64))

    def test_scalar_list_loop_cannot_inherit_the_typed_string_contract(self):
        prefix = bytes.fromhex("488b5df04c8b65f8")
        loop = 0x1000 + len(prefix)
        raw = prefix + bytes.fromhex("488b73104c89e7")
        target = 0x2000
        raw += b"\xe8" + struct.pack("<i", target - (0x1000 + len(raw) + 5))
        raw += bytes.fromhex("85c07405488b1b")
        raw += b"\xeb" + struct.pack("b", loop - (0x1000 + len(raw) + 2)) + b"\xc3"
        assembly, log, status = render(
            raw.hex(), kernel_symbols=SYMBOLS | {"ktime_get": target}, abi=1,
            return_status=True)
        self.assertEqual((assembly, status), (b"", 2), log)
        self.assertIn("bounded register-address alternatives", log)

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
            self.assertEqual((assembly, status), (b"", 2), log)
            self.assertIn("bounded register-address alternatives", log)
            # Isolate lowering in this user-memory fixture after asserting that
            # production admission refuses it. This mock never reaches a live
            # provider and is not evidence of accepted kernel delegation.
            with patch.object(translator, "find_segment_policy_error", return_value=None):
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
