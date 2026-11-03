"""Guest-only real decoder/emitter/wrapper checks for reached Native CALLs.

Source bytes and symbol/learning records are substitutes. Native APIs are never
invoked here; the wrapper must export their exact pending CALL to the runtime.
"""
import tempfile
import ctypes
import unittest
from pathlib import Path
from unittest.mock import patch

from test_jit_diagnostics import render, decode, translator
from test_jit_body_witness import run_image
from test_ordinary_callee_bytes import source_bytes
import native_terminals
import special_inst


class NativeCallBoundariesTests(unittest.TestCase):
    def generated(self, raw="", **kwargs):
        assembly, log, status = render(raw, trusted_source=True,
                                      body_witness=True, return_status=True, **kwargs)
        self.assertEqual(status, 0, log)
        return assembly

    def test_manifest_is_exact_and_shared_not_a_name_pattern(self):
        specs = native_terminals.load_specs()
        for name in ("mutex_lock", "down_read", "_raw_spin_lock", "schedule",
                     "migrate_disable", "kthread_use_mm", "kd_api_files_lock_clobber",
                     "kd_api_pipe_unlock_clobber"):
            self.assertIn(name, specs)
        self.assertNotIn("mutex_lock.isra.0", specs)
        self.assertNotIn("kd_mutex_direct_lock_clobber_v1", specs)
        observed = []
        def lookup(name, default):
            observed.append(name)
            return {"mutex_lock": 0x2000, "down_read": 0x3000}.get(name, default)
        self.assertEqual(set(native_terminals.resolve(lookup)), {0x2000, 0x3000})
        self.assertEqual(set(observed), set(specs))
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "manifest.def"
            for text in ("KD_NATIVE_TERMINAL(mutex_*, NATIVE_LOCK)",
                         "KD_NATIVE_TERMINAL(mutex_lock, NATIVE_LOCK)\n" * 2):
                path.write_text(text)
                with self.assertRaises(ValueError):
                    native_terminals.load_specs(path)

    def test_exact_near_call_encodings_and_only_alternatives_cs_register_prefixes(self):
        for raw in ("ffd0", "41ffd0", "ff1424", "ff1501020304",
                    "ff942401020304", "41ff942401020304",
                    "2effd0", "2e2effd0", "2e2e2effd0",
                    "2e41ffd0", "2e2e41ffd0", "2e2e2e41ffd0"):
            with self.subTest(raw=raw):
                instruction = decode(raw)
                self.assertEqual(instruction.name, "CALL")
                self.assertEqual(native_terminals.indirect_call_length(instruction.b),
                                 instruction.l)
        for raw in ("ffe0", "ffd8", "c3", "66ffd0", "f3ffd0", "67ff1424",
                    "e800000000", "ff", "ff94", "41ff9424010203",
                    "2e2e2e2effd0", "2e66ffd0", "662effd0", "2ef3ffd0",
                    "2effe0", "2effd8", "2eff1424", "2e41ff1424",
                    "412effd0", "2e4141ffd0", "2e", "2e2e2e41ff",
                    "2e2e2effd090"):
            self.assertIsNone(native_terminals.indirect_call_length(bytes.fromhex(raw)), raw)

    def test_fresh_call_exports_pre_push_target_once_with_actual_return_word(self):
        # Include RSP and [RSP]: evaluating either after the virtual push is wrong.
        for raw, target_kind in (("ffd0c3", "rax"), ("41ffd0c3", "r8"),
                                 ("2effd0c3", "rax"), ("2e2e2effd0c3", "rax"),
                                 ("2e2e41ffd0c3", "r8"),
                                 ("2e2e2e41ffd0c3", "r8"),
                                 ("ffd4c3", "rsp"), ("ff1424c3", "stack")):
            for capable in (False, True):
                with self.subTest(raw=raw, capable=capable):
                    assembly = self.generated(raw, indirect_call_capable=capable)
                    observations = []
                    def initialize(regs, stack):
                        regs[12] = regs[11] = 0xb000
                        stack[8] = 0xc000
                        observations.append((regs[1], stack))
                    regs, args = run_image(assembly, [0x1000], initialize=initialize)[0]
                    original_sp, stack = observations[0]
                    expected = original_sp if target_kind == "rsp" else 0xc000 if target_kind == "stack" else 0xb000
                    length = decode(raw).l
                    self.assertEqual(regs[0], expected)
                    self.assertEqual(regs[1], original_sp - 8)
                    self.assertEqual((stack[7], stack[8]), (0x1000 + length, 0xc000))
                    self.assertEqual(args, [11 if capable else 0x1000 + length, 1])
                    self.assertEqual(regs[17], 0x1000 if capable else 0)

    def test_exact_near_tail_encodings_are_separate_from_calls_and_returns(self):
        for raw in ("ffe0", "41ffe0", "ff2424", "ff2501020304",
                    "ffa42401020304", "41ffa42401020304", "2effe0",
                    "2e2effe0", "2e2e2effe0", "2e41ffe0",
                    "2e2e41ffe0", "2e2e2e41ffe0"):
            with self.subTest(raw=raw):
                instruction = decode(raw)
                self.assertEqual(instruction.name, "JMP")
                self.assertEqual(native_terminals.indirect_tail_length(instruction.b),
                                 instruction.l)
                self.assertIsNone(native_terminals.indirect_call_length(instruction.b))
                for size in range(len(instruction.b)):
                    self.assertIsNone(native_terminals.indirect_tail_length(
                        instruction.b[:size]))
        for raw in ("ffd0", "ffe8", "c3", "7500", "66ffe0", "f3ffe0",
                    "67ff2424", "e900000000", "ff", "ffa4",
                    "41ffa424010203", "2e2e2e2effe0", "2e66ffe0",
                    "662effe0", "2ef3ffe0", "2effd0", "2effe8",
                    "2eff2424", "2e41ff2424", "412effe0", "2e4141ffe0",
                    "2e", "2e2e2e41ff", "2e2e2effe090"):
            self.assertIsNone(native_terminals.indirect_tail_length(bytes.fromhex(raw)), raw)

    def test_unknown_ret_and_jump_never_get_call_exit(self):
        for raw in ("c3", "ffe0"):
            assembly = self.generated(raw, indirect_call_capable=True)
            def initialize(regs, stack):
                regs[12] = 0xb000
            regs, args = run_image(assembly, [0x1000], initialize=initialize)[0]
            self.assertNotEqual(args[0], 11)
            self.assertEqual(regs[17], 0)

    def test_complex_target_register_mapping_preserves_source_gprs(self):
        targets = (ctypes.c_ulong * 4)(0x9000, 0xa000, 0xb000, 0xc000)
        # Two virtual address GPRs plus a destination scratch used to exhaust
        # the four-register pool and overwrite the staged target/SP mapping.
        for operand in ("[r12+r13*8]", "[r14+r15*8]", "[r11+r13*8]", "[rax+r13*8]"):
            regions, _ = source_bytes("call QWORD PTR " + operand + "\nret")
            assembly = self.generated(regions=regions, indirect_call_capable=True)
            before = []
            def initialize(regs, stack):
                regs[3], regs[5] = 2, 2  # R15, R13 indexes
                for slot in (4, 6, 7, 12):  # R14, R12, R11, RAX bases
                    regs[slot] = ctypes.addressof(targets)
                before.append(list(regs))
            regs, args = run_image(assembly, [0x1000], initialize=initialize)[0]
            self.assertEqual((regs[0], args), (0xb000, [11, 1]))
            for slot in range(3, 17):
                self.assertEqual(regs[slot], before[0][slot], (operand, slot))
            self.assertEqual(regs[2], before[0][2])
            self.assertEqual(regs[1], before[0][1] - 8)

    def test_fresh_call_native_suffix_is_not_decoded_as_a_jit_path(self):
        # UD2 is retained by trusted lowering when reachable; this assertion
        # checks scope, without executing the deliberately unsupported suffix.
        assembly = self.generated("ffd00f0b", indirect_call_capable=True)
        self.assertNotIn(b"loc_1002:", assembly)
        self.assertNotIn(b"UD2", assembly)
        def initialize(regs, stack):
            regs[12] = 0xb000
        regs, args = run_image(assembly, [0x1000], initialize=initialize)[0]
        self.assertEqual((regs[0], regs[17], args), (0xb000, 0x1000, [11, 1]))

    def test_terminal_branch_keeps_hot_path_and_discards_stale_descendants(self):
        regions, names = source_bytes("""
            test edi, edi
            jne cold
            mov eax, 42
            ret
        cold:
            call helper
            mov eax, 99
            ret
            .balign 4096
        helper:
            call helper_pad
            ret
            .balign 4096
        helper_pad:
            ud2
        """)
        assembly = self.generated(regions=regions,
            kernel_symbols={"mutex_lock": names["helper"]},
            indirect_history={names["helper"] + 5: [names["helper_pad"]]})
        self.assertIn(f"loc_{names['helper']:x}:".encode(), assembly)
        self.assertNotIn(f"loc_{names['helper_pad']:x}:".encode(), assembly)
        self.assertNotIn(f"ij_{names['helper'] + 5:x}:".encode(), assembly)
        for taken in (0, 1, 0, 1):
            def initialize(regs, stack):
                regs[16] = taken
            regs, args = run_image(assembly, [0x1000], initialize=initialize)[0]
            if taken:
                self.assertEqual((regs[0], args), (names["helper"], [1, 1]))
            else:
                self.assertEqual((regs[12], regs[0], args[1]), (42, 0x4444, 1))

    def test_learned_indirect_terminal_has_call_stub_but_other_live_callee_remains(self):
        regions, names = source_bytes("""
            call rax
            mov eax, 42
            ret
            .balign 4096
        helper:
            ud2
            .balign 4096
        helper_pad:
            mov eax, 9
            ret
        """)
        history = {0x1002: [names["helper"], names["helper_pad"]],
                   names["helper_pad"] + 6: [0x1002]}
        assembly = self.generated(regions=regions, indirect_history=history,
            kernel_symbols={"down_read": names["helper"]}, indirect_call_capable=True)
        for target, terminal in ((names["helper"], True), (names["helper_pad"], False)):
            def initialize(regs, stack):
                regs[12] = target
            regs, args = run_image(assembly, [0x1000], initialize=initialize)[0]
            if terminal:
                self.assertEqual((regs[0], args), (target, [1, 1]))
            else:
                self.assertEqual((regs[12], regs[0], args[1]), (42, 0x4444, 1))

    def test_ret_and_jmp_history_cannot_enter_native_call_stub(self):
        for raw, source in (("c3", 0x1001), ("ffe0", 0x1002)):
            assembly = self.generated(raw, kernel_symbols={"down_read": 0x2000},
                indirect_history={source: [0x2000]}, indirect_call_capable=True)
            self.assertNotIn(b"loc_2000:", assembly)
            def initialize(regs, stack):
                regs[12] = stack[8] = 0x2000
            _, args = run_image(assembly, [0x1000], initialize=initialize)[0]
            self.assertEqual(args, [source, 1])

    def test_indirect_target_staging_preserves_flags_until_a_known_return(self):
        regions, names = source_bytes("""
            mov dl, 127
            add dl, 1
        call_site:
            call rax
            seto cl
            sets dl
            setz bl
            ret
            .balign 4096
        helper:
            ret
        """)
        continuation = names["call_site"] + 2
        history = {continuation: [names["helper"]], names["helper"] + 1: [continuation]}
        assembly = self.generated(regions=regions, indirect_history=history,
                                  indirect_call_capable=True)
        def initialize(regs, stack):
            regs[12] = names["helper"]
        regs, args = run_image(assembly, [0x1000], initialize=initialize)[0]
        self.assertEqual((regs[13] & 255, regs[14] & 255, regs[8] & 255), (1, 1, 0))
        self.assertEqual((regs[0], args[1]), (0x4444, 1))

    def test_target_after_push_mutation_changes_real_stack_call(self):
        # Reintroduce the previous ordering only for this fixture. A real
        # wrapper execution must expose the wrong [RSP] target (the CALL word).
        original = special_inst.special_inst_dispatch
        def stale_order(line, args, offset, db, reg_map, block_end):
            if line.name != "CALL":
                return original(line, args, offset, db, reg_map, block_end)
            from miasm.expression.expression import ExprId, ExprInt
            code = special_inst.conflict_resolve(reg_map, {"T2"})
            code += special_inst.process_normal("MOVABS", [ExprId("RT2", 64), ExprInt(offset, 64)], offset, reg_map)
            code += special_inst.process_push(ExprId("RT2", 64), offset, reg_map)
            return code + special_inst.process_jump("JMP", line, args[0], offset, db, reg_map)
        with patch.object(special_inst, "special_inst_dispatch", side_effect=stale_order):
            assembly = self.generated("ff1424c3", indirect_call_capable=True)
        regs, args = run_image(assembly, [0x1000])[0]
        self.assertEqual((regs[0], args), (0x1003, [11, 1]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
