"""Refuse processor-state bytes before emission; never execute these fixtures."""
import struct
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import mock_open, patch

from miasm.expression.expression import ExprId
from test_jit_diagnostics import TEST_LOCK_SYMBOLS, decode, render, translator
import instruction_policy
import special_inst
import conflict
from miasm.core.locationdb import LocationDB


SYMBOLS = {
    name: 0x2000000 + index * 0x1000
    for index, name in enumerate((
        "kd_spin_lock_clobber_v1", "kd_spin_unlock_clobber_v1",
        "kd_mutex_lock_clobber_v1", "kd_mutex_unlock_clobber_v1",
        "kd_mutex_direct_lock_clobber_v1", "kd_mutex_direct_unlock_clobber_v1",
        "kd_mutex_direct_contended_clobber_v1", "kd_mutex_outer_contended_clobber_v1",
    ))
}
ENTRIES = (("spin", 0), ("spin", 1), ("spin", 3), ("mutex", 0),
           ("mutex", 2))
CORE = {
    "cli": "fa", "sti": "fb", "stac": "0f01cb", "clac": "0f01ca",
    "rdmsr": "0f32", "wrmsr": "0f30", "pushfq": "9c", "popfq": "9d",
    "rdpkru": "0f01ee", "wrpkru": "0f01ef", "xgetbv": "0f01d0",
    "xsetbv": "0f01d1", "swapgs": "0f01f8",
}


def call(target, source=0x1000):
    return b"\xe8" + struct.pack("<i", target - source - 5)


class InstructionPolicyTests(unittest.TestCase):
    def refuse(self, raw, **kwargs):
        # Full lookahead distinguishes an unsupported opcode from a truncated
        # read. Defined implicit MSR inputs prevent an ABI-value refusal from
        # accidentally standing in for the processor-state policy.
        with patch.object(translator, "emit_jit_assembly",
                          side_effect=AssertionError("refused code reached emission")):
            assembly, log, status = render(raw, return_status=True, **kwargs)
        self.assertEqual((status, assembly), (2, b""), log)
        self.assertIn("reason=CONTEXT_NATIVE_ONLY", log)
        self.assertNotIn("FLAGS_UNPRESERVED", log)
        return log

    def test_state_instructions_are_refused_for_every_backend_and_abi(self):
        for kind, abi in ENTRIES:
            for name, raw in CORE.items():
                with self.subTest(kind=kind, abi=abi, instruction=name):
                    log = self.refuse("31c931c031d2" + raw + "c3" + "90" * 16,
                        lock_kind=kind, abi=abi, kernel_symbols=SYMBOLS)
                    self.assertIn('rip="0x1006"', log)
                    self.assertNotIn("minimal entry unavailable", log)

    def test_other_unvirtualized_state_and_effects_are_refused(self):
        cases = {
            "read_cr3": "0f20d8", "write_cr3": "0f22d8",
            "read_dr7": "0f21f8", "write_dr7": "0f23f8",
            "read_gs": "8ce8", "write_gs": "8ee8",
            "sgdt": "0f0100", "lgdt": "0f0110", "sidt": "0f0108",
            "lidt": "0f0118", "sldt": "0f00c0", "lldt": "0f00d0",
            "str": "0f00c8", "ltr": "0f00d8", "clts": "0f06",
            "invlpg": "0f0138", "invpcid": "660f388200", "wbinvd": "0f09",
            "rdtsc": "0f31", "rdtscp": "0f01f9", "rdpmc": "0f33", "cpuid": "0fa2",
            "int": "cd80", "int3": "cc", "iretq": "48cf", "syscall": "0f05",
            "sysret": "480f07", "sysenter": "0f34", "sysexit": "0f35",
            "hlt": "f4", "monitor": "0f01c8", "mwait": "0f01c9",
            "in": "e480", "out": "e680", "ins": "6c", "outs": "6e",
            "fld1": "d9e8", "fninit": "dbe3", "fwait": "9b", "emms": "0f77",
            "mmx": "0f6fc0", "sse": "f20f10c0", "vzeroupper": "c5f877",
            "ldmxcsr": "0fae10", "stmxcsr": "0fae18",
            "fxsave": "0fae00", "fxrstor": "0fae08",
            "xsave": "0fae20", "xrstor": "0fae28",
            "vmcall": "0f01c1", "vmrun": "0f01d8", "rsm": "0faa",
            "xbegin": "c7f800000000", "xend": "0f01d5", "xtest": "0f01d6",
            "xacquire": "f2f00fc108", "xrelease": "f3f00fc108", "bnd_ret": "f2c3",
            "cld": "fc", "std": "fd", "lahf": "9f", "sahf": "9e", "ud2": "0f0b",
        }
        for name, raw in cases.items():
            with self.subTest(instruction=name):
                self.refuse("31c931c031d2" + raw + "c3" + "90" * 16)

    def test_aliases_operands_and_future_mnemonics_fail_closed(self):
        for name in ("PUSHF", "PUSHFD", "PUSHFQ", "POPF", "POPFD", "POPFQ",
                     "IRET", "IRETD", "IRETQ", "STAC", "CLAC", "WRMSRNS",
                     "RDFSBASE", "RDGSBASE", "WRFSBASE", "WRGSBASE",
                     "INSTRUCTION_FROM_A_FUTURE_DECODER"):
            with self.subTest(name=name):
                line = SimpleNamespace(name=name, args=[], b=b"")
                self.assertIsNotNone(instruction_policy.rejection(line))
        # A mnemonic allowlist alone cannot distinguish MOV CR3 from MOV RAX,
        # or scalar MOVSD from the SSE form. Test operand screening separately
        # from its raw-opcode protection.
        for register in ("CR3", "DR7", "GS", "XMM0", "MM0", "RFLAGS", "K0", "TMM0"):
            with self.subTest(register=register):
                line = SimpleNamespace(name="MOV", args=[ExprId(register, 64), ExprId("RAX", 64)], b=b"")
                self.assertIn("hardware register", instruction_policy.rejection(line))

    def test_prefixes_and_misdecoded_names_cannot_bypass_checks(self):
        for prefix in ("", "66", "48", "f3", "6548", "666748"):
            for raw in CORE.values():
                with self.subTest(prefix=prefix, raw=raw):
                    # Treat the mnemonic as a decoder error: even NOP cannot
                    # erase a known state-changing instruction's actual bytes.
                    line = SimpleNamespace(name="NOP", args=[], b=bytes.fromhex(prefix + raw))
                    self.assertIsNotNone(instruction_policy.rejection(line))
        for raw in ("f30faec0", "f30faec8", "f30faed0", "f30faed8", "66f3480faed8"):
            self.refuse(raw + "c3" + "90" * 16)

    def test_read_prefetch_decoder_aliases_require_the_exact_memory_encoding(self):
        for hint, encoded in enumerate(("0f1808", "0f1810", "0f1818")):
            line = decode(encoded)
            self.assertEqual(line.name, "PREFETCH" + str(hint))
            self.assertIsNone(instruction_policy.rejection(line))
            # The same admitted scalar hint still traverses address/context
            # analysis and emission, with its source bytes retained.
            for kind, abi in ENTRIES:
                assembly, log, status = render("4889e0" + encoded + "c3",
                    lock_kind=kind, abi=abi, kernel_symbols=SYMBOLS, return_status=True)
                self.assertEqual(status, 0, log)
                self.assertIn(("PREFETCHT" + str(hint)).encode(), assembly)
                # render() deliberately mocks the compiler. Assemble the real
                # wrapper too, so a decoder-only spelling cannot pass this test.
                previous = Path.cwd()
                with tempfile.TemporaryDirectory(prefix="kd-prefetch-assembly-") as temporary:
                    directory = Path(temporary)
                    (directory / "asm").mkdir()
                    (directory / "asm/jit.S").write_bytes(assembly)
                    os.chdir(directory)
                    try:
                        translator.build_jit_binary(abi, context_inputs=
                            translator.wrapper_context_inputs(assembly.decode()))
                        self.assertTrue((directory / "asm/jit.bin").stat().st_size)
                    finally:
                        os.chdir(previous)
            for wrong in ("", "0f1800", "0f18c8", "0f0d08", "f00f1808", "f30f1808"):
                alias = SimpleNamespace(name=line.name, args=line.args, b=bytes.fromhex(wrong))
                self.assertIsNotNone(instruction_policy.rejection(alias))
            self.refuse("4889e064" + encoded + "c3" + "90" * 16)
        for name in ("PREFETCH3", "PREFETCH_READ_FUTURE"):
            self.assertIsNotNone(instruction_policy.rejection(
                SimpleNamespace(name=name, args=decode("0f1808").args, b=bytes.fromhex("0f1808"))))

    def test_known_undecodable_opcodes_need_no_extra_text_read(self):
        # Miasm 0.1.5 does not decode these opcodes. Refuse at their selected
        # instruction boundary even in a short window; never scan arbitrary
        # immediate/displacement bytes for the same patterns.
        for raw in ("0f01cb", "0f01ca", "0f01ef", "0f01ee", "0f01d1"):
            with self.subTest(raw=raw), patch.object(translator.memread, "extend_regions",
                    side_effect=AssertionError("known state opcode requested more text")):
                self.refuse(raw)

    def test_paired_enable_disable_is_still_native_only(self):
        for raw in ("fafb", "0f01cb0f01ca", "9c9d"):
            self.refuse(raw + "c3" + "90" * 16)

    def test_branches_learned_callees_and_indirect_targets_are_checked(self):
        for raw in ("0f30", "0f32", "9d", "0f01cb"):
            bad = bytes.fromhex(raw + "c3" + "90" * 16)
            with self.subTest(raw=raw):
                self.refuse((bytes.fromhex("7501c3") + bad).hex())
                self.assertEqual(render((call(0x2000) + b"\xc3").hex(), return_status=True)[2], 0)
                log = self.refuse("", regions=[(call(0x2000) + b"\xc3", 0x1000, [0x1000]),
                                               (bad, 0x2000, [0x2000])])
                self.assertIn('rip="0x2000"', log)
                self.refuse("", regions=[(bytes.fromhex("ffe0"), 0x1000, [0x1000]),
                                         (bad, 0x2000, [0x2000])],
                            indirect_history={0x1002: [0x2000]})

    def test_native_suffix_and_post_unlock_bytes_remain_outside_the_episode(self):
        for target in (0x5000, TEST_LOCK_SYMBOLS["_raw_spin_unlock"]):
            for raw in ("0f30", "0f01cb"):
                with self.subTest(target=target, raw=raw):
                    assembly, log, status = render(
                        (call(target) + bytes.fromhex(raw + "c3" + "90" * 16)).hex(), return_status=True)
                    self.assertEqual(status, 0, log)
                    self.assertTrue(assembly)
                    self.assertNotIn(b"loc_1005:", assembly)

    def test_helper_symbols_cannot_hide_context_effects(self):
        for name in ("user_access_begin", "__uaccess_begin_nospec", "smap_restore",
                     "_copy_from_user", "raw_copy_to_user", "__get_user_8",
                     "native_read_msr", "native_write_msr_safe.constprop.0", "kernel_fpu_begin"):
            with self.subTest(name=name):
                symbols = f"3000 T {name}\n4000 T ordinary_end\n"
                with patch("builtins.open", mock_open(read_data=symbols)):
                    resolved = translator.context_policy.load_context_symbols()
                log = self.refuse((call(0x3000) + b"\xc3").hex(), symbols=resolved)
                self.assertIn(name, log)

    def test_supported_integer_code_still_emits_for_every_entry(self):
        for kind, abi in ENTRIES:
            assembly, log, status = render("b82a0000004883c001c3", lock_kind=kind,
                abi=abi, kernel_symbols=SYMBOLS, return_status=True)
            self.assertEqual(status, 0, log)
            self.assertTrue(assembly)
        for raw in ("48b8fafb0f01cb0f309dc3", "650f1f00c3", "f390c3", "0faee80faef00faef8c3",
                    "65488b042528000000c3", "f3a4c3", "0fb1d9c3", "4883f8010f95c0c3"):
            with self.subTest(raw=raw):
                assembly, log, status = render(raw, return_status=True)
                self.assertEqual(status, 0, log)
                self.assertTrue(assembly)

    def test_direct_lowering_cannot_copy_state_instructions(self):
        for raw in ("0f30", "0f32", "9d", "cd80", "0f0138"):
            line = decode(raw)
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                special_inst.translate(line, line.l, LocationDB(), conflict.block_init(), True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
