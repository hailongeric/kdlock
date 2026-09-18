"""Admission rejects uncaptured entry values and stale facts after a new CALL."""
import ctypes
from io import StringIO
import unittest
from unittest.mock import patch
from test_jit_diagnostics import decode, render
from context_policy import FlowConstants
from context_guards import EntryGuards
from context_memory import MemoryValues
import hostcall
from miasm.expression.expression import ExprId, ExprInt, ExprMem
from test_jit_body_witness import run_image

SYMBOLS={"kd_raw_spin_lock_clobber_v1":0x3000,"kd_raw_spin_unlock_clobber_v1":0x4000}

class ClobberEntryTests(unittest.TestCase):
    def generate(self, code):
        return render(code, abi=1, kernel_symbols=SYMBOLS, return_status=True, muted=True)

    def test_stack_reload_is_a_valid_minimal_input(self):
        assembly, _, status=self.generate('488b45f848890424c3')
        self.assertEqual(status,0)
        self.assertTrue(assembly)

    def test_uncaptured_memory_value_and_address_refused(self):
        for code in ('48890424c3','488b00c3','4885c0740148c3'):
            with self.subTest(code=code):
                _,_,status=self.generate(code)
                self.assertEqual(status,2)

    def test_partial_low_write_does_not_require_high_bits(self):
        self.assertEqual(self.generate('b007880424c3')[2],0)
        self.assertEqual(self.generate('b00748890424c3')[2],2)

    def test_overwrite_and_branch_merge(self):
        self.assertEqual(self.generate('31c048890424c3')[2],0)
        # One arm fails to define RAX: cannot authorize the joined store.
        self.assertEqual(self.generate('48833c2400740748c7c00100000048890424c3')[2],2)

    def test_clobber_contract_is_spin_only(self):
        self.assertEqual(render('c3',abi=1,lock_kind='mutex',return_status=True,muted=True)[2],2)

    def test_new_control_drops_saved_register_facts(self):
        for new_contract in (False, True):
            tracker = FlowConstants()
            # Known pointer facts must not survive a compiler-clobbered CALL.
            for instruction in ('48bb0010000000000000', '48bd0020000000000000',
                                '48bc0030000000000000', '49bc0040000000000000'):
                tracker.update(decode(instruction))
            call = decode('e800000000')
            tracker.control_calls.add(id(call))
            if new_contract:
                tracker.clobber_calls.add(id(call))
            tracker.update(call)
            for name, value in (('RBP', 0x2000), ('RSP', 0x3000)):
                self.assertEqual(list(tracker.resolve_many(ExprId(name, 64))), [ExprInt(value, 64)])
            for name in ('RBX', 'R12'):
                self.assertEqual(ExprId(name, 64) in tracker.values, not new_contract)

    def test_control_memory_keeps_spills_but_invalidates_lock_aliases(self):
        for aliased in (False, True):
            tracker = FlowConstants(EntryGuards())
            # Use concrete distinct addresses: a write to L must invalidate a
            # pointer stored at L, while another caller spill remains exact.
            tracker.update(decode('48bc0030000000000000'))
            tracker.update(decode('48bf0020000000000000'))
            pointer = ExprInt(0x2000 if aliased else 0x4000, 64)
            tracker.memory.store([({pointer}, {ExprInt(0x12345678, 64)}, 64)])
            call = decode('e800000000')
            tracker.control_calls.add(id(call))
            tracker.clobber_calls.add(id(call))
            tracker.update(call)
            values = tracker.memory.load(ExprMem(pointer, 64))
            self.assertEqual(values == (ExprInt(0x12345678, 64),), not aliased)

    def test_initial_spill_identity_requires_an_untouched_slot(self):
        for overwritten in (False, True):
            tracker = FlowConstants(EntryGuards(), entry_spill_guards=True)
            bp = tracker.origins[ExprId('RBP', 64)]
            slot = tracker.memory.offset(bp, -8)
            if overwritten:
                tracker.memory.store([({slot}, {ExprId('unknown_store', 64)}, 64)])
            tracker.update(decode('488b7df8'))
            origin = tracker.origins.get(ExprId('RDI', 64))
            self.assertEqual(str(origin).startswith('kd_entry_SPILL_'), not overwritten)

    def test_spill_budget_is_bounded_and_legacy_budget_is_unchanged(self):
        with patch.object(MemoryValues, 'MAX_WORK', 2):
            old = FlowConstants(EntryGuards()).memory
            new = FlowConstants(EntryGuards(), entry_spill_guards=True).memory
            self.assertTrue(old.spend(2))
            self.assertFalse(old.spend(1))
            self.assertTrue(new.spend(8))
            self.assertFalse(new.spend(1))
            self.assertEqual(old.MAX_BYTES, 256)
            self.assertEqual(new.MAX_BYTES, 512)

    def test_only_audited_services_keep_sequential_waiter_memory(self):
        specs = {i: spec for i, spec in enumerate(hostcall.load_hostcall_specs(), 1)}
        self.assertEqual(hostcall.readonly_waiter_targets(specs), set(specs))
        specs[4] = hostcall.HostcallSpec('FUTURE', 4, 'unknown')
        self.assertNotIn(4, hostcall.readonly_waiter_targets(specs))
        for readonly in (False, True):
            tracker = FlowConstants(EntryGuards(), entry_spill_guards=True)
            tracker.update(decode('488b45f8'))
            before = tracker.origins[ExprId('RBP', 64)]
            call = decode('e800000000')
            if readonly:
                tracker.control_calls.add(id(call))
                tracker.readonly_calls.add(id(call))
            tracker.update(call)
            self.assertEqual(tracker.memory.entry_spills_blocked, not readonly)
            if readonly:
                self.assertEqual(tracker.origins[ExprId('RBP', 64)], before)
                tracker.update(decode('488b45f8'))
                self.assertTrue(str(tracker.origins[ExprId('RAX', 64)]).startswith('kd_entry_SPILL_'))

    def test_unknown_writes_and_callees_cannot_reacquire_initial_spills(self):
        for opaque_call in (False, True):
            tracker = FlowConstants(EntryGuards(), entry_spill_guards=True)
            previous = tracker.snapshot()
            if opaque_call:
                tracker.memory.clobber()
            else:
                tracker.memory.store([({ExprId('unknown_address', 64)},
                                       {ExprId('unknown_data', 64)}, 64)])
            # Both cases can still have entirely UNKNOWN bytes. Neither is
            # evidence that a later load equals the word checked at entry.
            tracker.update(decode('488b7df8'))
            self.assertNotIn(ExprId('RDI', 64), tracker.origins)
            changed = tracker.snapshot()
            tracker.restore(tracker.merge_state(previous, changed))
            tracker.update(decode('488b7df8'))
            self.assertNotIn(ExprId('RDI', 64), tracker.origins)
            # An independent untouched branch can still acquire an identity.
            tracker.restore(previous)
            tracker.update(decode('488b7df8'))
            self.assertTrue(str(tracker.origins[ExprId('RDI', 64)]).startswith('kd_entry_SPILL_'))

    def test_real_guard_checks_stack_bounds_and_loaded_pointer(self):
        guards = EntryGuards()
        spill = guards.stack_value((ExprId('kd_entry_RBP', 64), -8))
        self.assertTrue(guards.separate((ExprId('kd_entry_' + spill, 64), 0), (None, 0x7000), 8, 8))
        self.assertEqual(guards.register_dependencies(), {'RSP', 'RBP'})
        output = StringIO()
        guards.emit(output, 0x1000)
        assembly = (output.getvalue() + '\nMOV Stack_JIT_WITNESS, 1\nMOV R14, 0x2000\nMOV Stack_IJ, 1\nJMP exit\n').encode()
        for value, valid_bp, expected in ((0x6000, True, 1), (0x7000, True, 6), (0x6000, False, 6)):
            def initialize(regs, stack):
                regs[4] = ctypes.addressof(stack) + 12 * 8 if valid_bp else 0
                stack[11] = value
            _, args = run_image(assembly, [0x1000], initialize)[0]
            self.assertEqual(args, [expected, int(expected == 1)])

    def test_scaled_spill_guard_checks_actual_modulo_address(self):
        tracker = FlowConstants(EntryGuards(), entry_spill_guards=True)
        tracker.update(decode('488b45f8'))
        tracker.update(decode('48c1e005'))
        origin = tracker.origins[ExprId('RAX', 64)]
        guards = tracker.memory.guards
        self.assertTrue(guards.separate((origin, 0), (None, 0x7000), 8, 8))
        self.assertEqual(guards.register_dependencies(), {'RSP', 'RBP'})
        output = StringIO()
        guards.emit(output, 0x1000)
        assembly = (output.getvalue() + '\nMOV Stack_JIT_WITNESS, 1\nMOV R14, 0x2000\nMOV Stack_IJ, 1\nJMP exit\n').encode()
        for value, expected in ((0x300, 1), (0x380, 6), ((1 << 63) + 0x380, 6)):
            def initialize(regs, stack):
                regs[4] = ctypes.addressof(stack) + 12 * 8
                stack[11] = value
            _, args = run_image(assembly, [0x1000], initialize)[0]
            self.assertEqual(args, [expected, int(expected == 1)])

    def test_byte_guard_collection_counts_union_without_losing_overlap(self):
        guards = EntryGuards()
        guards.MAX_RANGES = 2
        for offset in range(64):
            self.assertTrue(guards.separate((ExprId('kd_entry_RBP', 64), offset),
                                           (ExprId('kd_entry_RSP', 64), offset)))
        self.assertEqual(guards.range_count, 2)
        self.assertEqual(len(guards.conditions()), 1)
        for distance in (0, 1, 63, 64, 65):
            self.assertEqual(guards.accepts({'RBP': 0x1000, 'RSP': 0x1000 + distance}), distance >= 64)

if __name__=='__main__':
    unittest.main()
