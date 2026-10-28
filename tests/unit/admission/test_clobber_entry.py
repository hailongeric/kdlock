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

    def test_direct_unlock_is_the_critical_section_boundary(self):
        direct = {'kd_spin_lock_legacy': 0x7000, 'kd_spin_unlock_legacy': 0x8000,
                  'kd_spin_lock_clobber_v1': 0x5000,
                  'kd_spin_unlock_clobber_v1': 0x6000}
        # Set RDI and the clobber shell's RSI/RDX/RCX metadata; CALL direct
        # unlock; forbidden FS load outside CS. Missing metadata must refuse.
        # The direct endpoint must stop the lexical CS before that suffix.
        _, _, status = render('48c7c7009000004889e648c7c2191000004889e9e8e74f000064488b042500000000c3',
                              abi=1, kernel_symbols=SYMBOLS | direct,
                              return_status=True, muted=True)
        self.assertEqual(status, 0)

    def test_uncaptured_memory_value_and_address_refused(self):
        for code in ('48890424c3','488b00c3','4885c0740148c3'):
            with self.subTest(code=code):
                _,_,status=self.generate(code)
                self.assertEqual(status,2)

    def test_helper_entry_defines_saves_without_relaxing_admission(self):
        # The helper entry defines only the five already-clobbered callee-save
        # scratch registers. Reproduce an ordinary helper prologue/epilogue;
        # omitting any one definition must retain the uncaptured-store refusal.
        definitions = ('31db', '4531e4', '4531ed', '4531f6', '4531ff')
        helper = '554889e5415541545341564157'
        helper += '415f415e5b415c415d5dc3'
        for omitted in (None, *range(len(definitions))):
            with self.subTest(omitted=omitted):
                code = ''.join(value for index, value in enumerate(definitions)
                               if index != omitted) + helper
                assembly, log, status = self.generate(code)
                self.assertEqual(status, 0 if omitted is None else 2, log)
                self.assertEqual(bool(assembly), omitted is None)
        # This is not a new captured-register contract: volatile RAX and
        # unsupported FS writes remain rejected after the same setup. Ordinary
        # GS memory accesses have a separate origin-CPU lowering contract.
        setup = ''.join(definitions)
        self.assertEqual(self.generate(setup + '48890424c3')[2], 2)
        self.assertEqual(self.generate(setup + '6448c704250000000001000000c3')[2], 2)

    def test_paired_stack_restore_and_control_abis(self):
        # The paired continuation reloads callee saves from the entry stack;
        # its cookie must be defined here, not inherited from uncaptured EAX.
        symbols = SYMBOLS | {'kd_spin_lock_pinned_clobber_v1': 0x5000,
                             'kd_spin_direct_native_unlock': 0x6000}
        restore = bytes.fromhex('415f415e415d415c5b')
        for target, clobber in ((0x4000, True), (0x5000, True), (0x6000, False)):
            code = restore + bytes.fromhex('b80100000053415441554156415748c7c700900000')
            if clobber:
                # RSI/RDX/RCX are shell metadata, even for the new pinned symbol.
                ip = 0x1000 + len(code) + 3 + 7 + 3 + 5
                code += bytes.fromhex('4889e648c7c2') + ip.to_bytes(4, 'little')
                code += bytes.fromhex('4889e9')
            call_ip = 0x1000 + len(code)
            code += b'\xe8' + (target-call_ip-5).to_bytes(4, 'little', signed=True)
            # A lock needs its matching unlock boundary. No unsafe suffix can
            # enter the generated CS after either ordinary-C or clobber unlock.
            if target == 0x5000:
                code += bytes.fromhex('48c7c700900000')
                call_ip = 0x1000 + len(code)
                code += b'\xe8' + (0x6000-call_ip-5).to_bytes(4, 'little', signed=True)
                # Nested depth remains one: finish the outer hold too.
                code += bytes.fromhex('48c7c700900000')
                call_ip = 0x1000 + len(code)
                code += b'\xe8' + (0x6000-call_ip-5).to_bytes(4, 'little', signed=True)
            code += bytes.fromhex('64488b042500000000c3')
            with self.subTest(target=hex(target)):
                self.assertEqual(render(code.hex(), abi=1, kernel_symbols=symbols,
                                        return_status=True, muted=True)[2], 0)

    def test_paired_outer_requires_reload_after_inner_clobber(self):
        # The mixed nested workload must preserve values that its paired outer
        # unlock will save. Do not admit arbitrary pushes of uncaptured GPRs
        # merely because C has no other use of them before its epilogue.
        save = bytes.fromhex('534154415541564157')
        restore = bytes.fromhex('415f415e415d415c5b')
        for preserved in (False, True):
            code = restore

            def call(target, lock):
                nonlocal code
                code += bytes.fromhex('48c7c7') + lock.to_bytes(4, 'little')
                ip = 0x1000 + len(code) + 3 + 7 + 3 + 5
                code += bytes.fromhex('4889e648c7c2') + ip.to_bytes(4, 'little')
                code += bytes.fromhex('4889e9')
                code += b'\xe8' + (target-0x1000-len(code)-5).to_bytes(4, 'little', signed=True)

            for target in (0x3000, 0x4000):
                if preserved:
                    code += save
                call(target, 0x9100)
                if preserved:
                    code += restore
            code += save
            call(0x4000, 0x9000)
            code += restore + b'\xc3'
            self.assertEqual(self.generate(code.hex())[2], 0 if preserved else 2)

    def test_partial_low_write_does_not_require_high_bits(self):
        self.assertEqual(self.generate('b007880424c3')[2],0)
        self.assertEqual(self.generate('b00748890424c3')[2],2)

    def test_extensions_preserve_defined_low_bits_without_defining_high_bits(self):
        # EDX's high bits are absent at entry. Defining DL must suffice for a
        # later byte store, even after extension through EDI or RAX. A wider
        # store still observes uncaptured bits and must refuse admission.
        for prefix, byte_store, wide_store in (
            ('b20789d7', '40883c24', '893c24'),       # MOV EDI, EDX
            ('b2070fb7fa', '40883c24', '893c24'),     # MOVZX EDI, DX
            ('b207480fbfc2', '880424', '48890424'),   # MOVSX RAX, DX
            ('b2074863c2', '880424', '48890424'),     # MOVSXD RAX, EDX
        ):
            with self.subTest(prefix=prefix):
                self.assertEqual(self.generate(prefix + byte_store + 'c3')[2], 0)
                self.assertEqual(self.generate(prefix + wide_store + 'c3')[2], 2)

    def test_cmov_partial_source_can_control_low_byte_branch(self):
        # Mirrors the hash-loop boolean: defined EDI, defined DL, a 32-bit
        # conditional move from EDX, then TEST DIL. Uncaptured upper EDX bits
        # must not taint DIL; testing all of EDI must still be rejected.
        prefix = '31ff31c085c0b2070f45fa'
        self.assertEqual(self.generate(prefix + '4084ff7501c3c3')[2], 0)
        self.assertEqual(self.generate(prefix + '85ff7501c3c3')[2], 2)

    def test_extension_high_bits_depend_only_on_the_source_sign_bit(self):
        # Observe only extended high bits: zero extension always defines them,
        # while sign extension must carry an uncaptured source sign bit. DH
        # defines the sign of DX even when DL remains absent at entry.
        self.assertEqual(self.generate('b2070fb7fac1ef10893c24c3')[2], 0)
        self.assertEqual(self.generate('b207480fbfc248c1e81048890424c3')[2], 2)
        self.assertEqual(self.generate('b607480fbfc248c1e81048890424c3')[2], 0)

    def test_overwrite_and_branch_merge(self):
        self.assertEqual(self.generate('31c048890424c3')[2],0)
        # One arm fails to define RAX: cannot authorize the joined store.
        self.assertEqual(self.generate('48833c2400740748c7c00100000048890424c3')[2],2)

    def test_contract_identity_matches_backend(self):
        mutex_symbols = {"kd_mutex_direct_lock_clobber_v1": 0x5000,
                         "kd_mutex_direct_unlock_clobber_v1": 0x6000}
        for abi, kind, expected in ((1, 'mutex', 2), (2, 'spin', 2), (2, 'mutex', 0),
                                    (3, 'mutex', 2), (3, 'spin', 0)):
            with self.subTest(abi=abi, lock_kind=kind):
                self.assertEqual(render('c3', abi=abi, lock_kind=kind,
                                        kernel_symbols=SYMBOLS | mutex_symbols,
                                        return_status=True, muted=True)[2], expected)
        for code in ('488b45f848890424c3', '48890424c3'):
            self.assertEqual(render(code, abi=3, kernel_symbols=SYMBOLS,
                                    return_status=True, muted=True)[2],
                             0 if code.startswith('488b45') else 2)
            self.assertEqual(render(code, abi=2, lock_kind='mutex',
                                    kernel_symbols=mutex_symbols, return_status=True,
                                    muted=True)[2], 0 if code.startswith('488b45') else 2)

    def test_obsolete_mutex_bridge_cannot_supply_abi2_identity(self):
        # KD-only ABI2 resolves its own module endpoints. The old Linux bridge
        # names cannot establish an available clobber contract, even for RET.
        symbols = {"kd_mutex_lock_clobber_v1": 0x5000,
                   "kd_mutex_unlock_clobber_v1": 0x6000}
        assembly, log, status = render('c3', abi=2, lock_kind='mutex',
                                      kernel_symbols=symbols, return_status=True)
        self.assertEqual((status, assembly), (2, b''))
        self.assertIn('clobber entry symbols unavailable', log)

    def test_direct_mutex_unlock_bounds_abi2(self):
        # The provider's direct endpoint terminates the body before the unsafe
        # suffix and is eligible for checked COMPLETE rather than a CALL miss.
        symbols = {"kd_mutex_direct_lock_clobber_v1": 0x7000,
                   "kd_mutex_direct_unlock_clobber_v1": 0x8000}
        code = bytes.fromhex('48c7c7009000004889e648c7c2191000004889e9')
        code += b'\xe8' + (0x8000 - 0x1019).to_bytes(4, 'little', signed=True)
        code += bytes.fromhex('64488b042500000000c3')
        asm, _, status = render(code.hex(), abi=2, lock_kind='mutex',
                                kernel_symbols=symbols, return_status=True, muted=True)
        self.assertEqual(status, 0)
        self.assertIn(b'clobber_complete', asm)

    def test_contended_mutex_symbol_is_an_abi2_control_boundary(self):
        symbols = {"kd_mutex_direct_lock_clobber_v1": 0x5000,
                   "kd_mutex_direct_contended_clobber_v1": 0x6000,
                   "kd_mutex_direct_unlock_clobber_v1": 0x7000}
        code = bytes.fromhex('48c7c700910000')
        for target in (0x6000, 0x7000):
            ip = 0x1000 + len(code) + 3 + 7 + 3 + 5
            code += bytes.fromhex('4889e648c7c2') + ip.to_bytes(4, 'little')
            code += bytes.fromhex('4889e9')
            code += b'\xe8' + (target-0x1000-len(code)-5).to_bytes(4, 'little', signed=True)
            code += bytes.fromhex('48c7c700910000')
        # Finish the outer A after the deliberately constructed inner B.
        code += bytes.fromhex('48c7c700900000')
        ip = 0x1000 + len(code) + 3 + 7 + 3 + 5
        code += bytes.fromhex('4889e648c7c2') + ip.to_bytes(4, 'little')
        code += bytes.fromhex('4889e9')
        code += b'\xe8' + (0x7000-0x1000-len(code)-5).to_bytes(4, 'little', signed=True)
        code += b'\xc3'
        _, log, status = render(code.hex(), abi=2, lock_kind='mutex',
                                kernel_symbols=symbols, return_status=True, muted=True)
        self.assertEqual(status, 0, log)

    def test_outer_mutex_return_endpoint_is_not_a_nested_void_control(self):
        symbols = {"kd_mutex_direct_lock_clobber_v1": 0x5000,
                   "kd_mutex_outer_contended_clobber_v1": 0x6000,
                   "kd_mutex_direct_unlock_clobber_v1": 0x7000}
        # Root starts after the CALL; a CALL inside an image would need a
        # return-valued acquisition model, which the old nested service lacks.
        code = bytes.fromhex('48c7c7009100004889e648c7c2191000004889e9')
        code += b'\xe8' + (0x6000-0x1019).to_bytes(4, 'little', signed=True)
        code += bytes.fromhex('eb0231c048890424c3')
        _, log, status = render(code.hex(), abi=2, lock_kind='mutex',
                                kernel_symbols=symbols, return_status=True)
        self.assertEqual(status, 2, log)
        self.assertIn('outer-only mutex entry', log)

    def test_mutex_clobber_cannot_use_spin_word_memory_summary(self):
        tracker = FlowConstants(EntryGuards())
        tracker.update(decode('48bc0030000000000000'))
        tracker.update(decode('48bf0020000000000000'))
        pointer = ExprInt(0x4000, 64)
        tracker.memory.store([({pointer}, {ExprInt(0x12345678, 64)}, 64)])
        call = decode('e800000000')
        tracker.control_calls.add(id(call))
        tracker.clobber_calls.add(id(call))
        tracker.mutex_calls.add(id(call))
        tracker.update(call)
        self.assertNotEqual(tracker.memory.load(ExprMem(pointer, 64)),
                            (ExprInt(0x12345678, 64),))

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

    def test_checked_mutex_preserves_late_entry_spill_with_range_guard(self):
        tracker = FlowConstants(EntryGuards(), entry_spill_guards=True,
                                mutex_stack_bytes=256)
        call = decode('e800000000')
        tracker.control_calls.add(id(call))
        tracker.clobber_calls.add(id(call))
        tracker.mutex_calls.add(id(call))
        tracker.update(call)
        tracker.update(decode('488b7df8'))
        self.assertTrue(str(tracker.origins[ExprId('RDI', 64)]).startswith('kd_entry_SPILL_'))
        self.assertTrue(tracker.memory.guards.checked_windows)
        # Unknown callee or store on either incoming path must still block
        # recreation of an entry identity after the join.
        before = tracker.snapshot()
        tracker.memory.clobber()
        blocked = tracker.snapshot()
        tracker.restore(tracker.merge_state(before, blocked))
        tracker.update(decode('488b75f0'))
        self.assertNotIn(ExprId('RSI', 64), tracker.origins)

    def test_checked_mutex_windows_intersect_at_cfg_join(self):
        tracker = FlowConstants(EntryGuards(), entry_spill_guards=True)
        sp = tracker.origins[ExprId('RSP', 64)]
        clean = tracker.snapshot()
        tracker.memory.clobber(checked_windows=(sp,), window_bytes=256)
        first = tracker.snapshot()
        tracker.restore(clean)
        tracker.memory.clobber(checked_windows=(sp + ExprInt(16, 64),), window_bytes=256)
        second = tracker.snapshot()
        tracker.restore(tracker.merge_state(first, second))
        tracker.update(decode('488b7df8'))
        guards = tracker.memory.guards
        # Slot BP-8 must belong to both checked windows, including all bytes.
        for delta, accepted in ((8, False), (24, True), (256, True), (264, False)):
            registers = {'RSP': 0x1000, 'RBP': 0x1000 + delta}
            self.assertEqual(guards.accepts(registers, {registers['RBP']-8: 0x7000}), accepted)

    def test_checked_window_history_is_bounded_and_opaque_is_sticky(self):
        tracker = FlowConstants(EntryGuards(), entry_spill_guards=True)
        sp = tracker.origins[ExprId('RSP', 64)]
        for offset in range(65):
            tracker.memory.clobber(checked_windows=(sp + ExprInt(offset, 64),), window_bytes=256)
        self.assertTrue(tracker.memory.entry_spills_blocked)
        self.assertFalse(tracker.memory.checked_spill_windows)
        tracker.memory.clobber(checked_windows=(sp,), window_bytes=256)
        self.assertTrue(tracker.memory.entry_spills_blocked)
        self.assertFalse(tracker.memory.checked_spill_windows)

    def test_machine_code_checked_window_guard_covers_entire_word(self):
        guards = EntryGuards()
        bp, sp = ExprId('kd_entry_RBP', 64), ExprId('kd_entry_RSP', 64)
        self.assertTrue(guards.inside_checked_window((bp, -8), (sp, 0), 8, 256))
        output = StringIO()
        guards.emit(output, 0x1000)
        assembly = (output.getvalue() + '\nMOV Stack_JIT_WITNESS, 1\nMOV R14, 0x2000\nMOV Stack_IJ, 1\nJMP exit\n').encode()
        for offset in (0, 8, 256, 257, 264):
            expected = 1 if 8 <= offset <= 256 else 6
            def initialize(regs, stack):
                regs[2] = regs[1] + offset
            _, args = run_image(assembly, [0x1000], initialize)[0]
            self.assertEqual(args, [expected, int(expected == 1)])

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

    def test_only_scalar_services_keep_sequential_waiter_memory(self):
        specs = {i: spec for i, spec in enumerate(hostcall.load_hostcall_specs(), 1)}
        scalar = {address for address, spec in specs.items()
                  if (spec.name, spec.service_id, spec.symbol) in {
                      ('KTIME_GET', 1, 'ktime_get'), ('KTIME_GET_NS', 2, 'ktime_get_ns'),
                      ('INT_SQRT', 3, 'int_sqrt')}}
        self.assertEqual(len(scalar), 3)
        self.assertEqual(hostcall.readonly_waiter_targets(specs), scalar)
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
                regs[2] = ctypes.addressof(stack) + 12 * 8 if valid_bp else 0
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
                regs[2] = ctypes.addressof(stack) + 12 * 8
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
