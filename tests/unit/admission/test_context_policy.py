"""Select the complete context-policy corpus without duplicate discovery."""
import struct
import unittest
from test_jit_diagnostics import render
from context_symbols_cases import ContextSymbolsCases
from context_flow_cases import ContextFlowCases
from context_instructions_cases import ContextInstructionsCases


class ContextPolicyTests(ContextSymbolsCases, ContextFlowCases,
                         ContextInstructionsCases, unittest.TestCase):
    """One public entrypoint; inherited cases are each collected once."""


class JitPhaseTests(unittest.TestCase):
    """Guard the boundary between emitted JIT and waiter-only continuation."""

    FS = bytes.fromhex("64488b042528000000c3")

    @staticmethod
    def call(target, offset=0x1000):
        return b"\xe8" + struct.pack("<i", target - offset - 5)

    def test_missing_direct_call_ends_episode_before_context_suffix(self):
        assembly, log, status = render(
            (self.call(0x5000) + self.FS).hex(), return_status=True
        )
        self.assertEqual(status, 0, log)
        self.assertIn(b"loc_5000:", assembly)
        self.assertNotIn(b"loc_1005:", assembly)
        self.assertNotIn(b"FS:", assembly)

    def test_alternate_jit_branch_still_checks_same_suffix(self):
        # JNZ skips the terminal CALL and reaches the otherwise native suffix.
        raw = bytes.fromhex("7505") + self.call(0x5000, 0x1002) + self.FS
        assembly, log, status = render(raw.hex(), return_status=True)
        self.assertEqual(status, 2, log)
        self.assertFalse(assembly)

    def test_native_edge_does_not_pollute_alternate_live_successor(self):
        # Return-address bytes must not flow out of the native exit
        # into a suffix reached only by the branch that never executes CALL.
        raw = bytes.fromhex("7505") + self.call(0x5000, 0x1002)
        raw += bytes.fromhex("488b4424f8488b00c3")
        assembly, log, status = render(raw.hex(), return_status=True)
        self.assertEqual(status, 0, log)
        self.assertIn(b"loc_1007:", assembly)

    def test_control_and_hostcall_successors_remain_in_scope(self):
        for name in ("_raw_spin_lock", "ktime_get_ns"):
            with self.subTest(name=name):
                assembly, log, status = render(
                    (self.call(0x5000) + self.FS).hex(),
                    kernel_symbols={name: 0x5000},
                    return_status=True,
                )
                self.assertEqual(status, 2, log)
                self.assertFalse(assembly)

    def test_learned_callee_restores_return_scope_on_retranslation(self):
        raw = self.call(0x5000) + self.FS
        # A later version can return from this decoded callee. Admission must
        # reconsider the suffix instead of reusing the first version's verdict.
        assembly, log, status = render(
            "",
            regions=[(raw, 0x1000, [0x1000]), (b"\xc3", 0x5000, [0x5000])],
            return_status=True,
        )
        self.assertEqual(status, 2, log)
        self.assertFalse(assembly)

    def test_indirect_call_keeps_conservative_return_scope(self):
        assembly, log, status = render(
            (bytes.fromhex("ffd0") + self.FS).hex(), return_status=True
        )
        self.assertEqual(status, 2, log)
        self.assertFalse(assembly)

    def test_owned_outer_entries_are_outer_only_for_calls_and_addresses(self):
        names = ('kd_owned_mutex_lock_v1', 'kd_owned_mutex_unlock_v1',
            'kd_owned_mutex_outer_unlock_v1', 'kd_owned_mutex_direct_lock_clobber_v1',
            'kd_owned_mutex_direct_contended_clobber_v1',
            'kd_owned_mutex_outer_contended_clobber_v1',
            'kd_owned_mutex_outer_prepared_clobber_v1',
            'kd_owned_mutex_outer_preflight_v1', 'kd_owned_mutex_direct_unlock_clobber_v1')
        for endpoint in ('kd_owned_mutex_outer_preflight_v1',
                         'kd_owned_mutex_outer_prepared_clobber_v1'):
            target = 0x5000
            controls = {name: 0x7000000+i*0x100 for i, name in enumerate(names)}
            controls[endpoint] = target
            cases = (self.call(target) + b'\xc3',
                     b'\x48\xb8' + struct.pack('<Q', target) + b'\xc3',
                     b'\xe9' + struct.pack('<i', target - 0x1000 - 5))
            for kind in ('mutex-owned', 'mutex', 'spin'):
                for raw in cases:
                    with self.subTest(endpoint=endpoint, kind=kind, raw=raw.hex()):
                        assembly, log, status = render(raw.hex(), kernel_symbols=controls,
                            lock_kind=kind, abi=2 if kind == 'mutex-owned' else 0,
                            return_status=True)
                        self.assertEqual(status, 2, log)
                        self.assertFalse(assembly)
                        self.assertIn('outer-only mutex entry', log)
                        self.assertIn(endpoint, log)
        for missing in ('kd_owned_mutex_outer_preflight_v1',
                        'kd_owned_mutex_outer_prepared_clobber_v1'):
            controls = {name: 0x7000000+i*0x100 for i, name in enumerate(names) if name != missing}
            assembly, log, status = render('c3', kernel_symbols=controls,
                lock_kind='mutex-owned', abi=2, return_status=True)
            self.assertEqual(status, 2, log)
            self.assertFalse(assembly)
            self.assertIn('owned mutex entry symbols unavailable', log)

    def test_native_call_stack_write_is_still_checked(self):
        prefix = bytes.fromhex("48bc0830000000000000")
        assembly, log, status = render(
            (prefix + self.call(0x5000, 0x1000 + len(prefix)) + b"\xc3").hex(),
            symbols={0x3000: "__per_cpu_offset"},
            return_status=True,
        )
        self.assertEqual(status, 2, log)
        self.assertIn("IR memory access", log)
        self.assertFalse(assembly)



if __name__ == "__main__":
    unittest.main()
