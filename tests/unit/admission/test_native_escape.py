"""Reviewed marker admission; privileged instruction bytes are never executed."""
import unittest
from types import SimpleNamespace
from miasm.expression.expression import ExprId

from test_jit_diagnostics import render
from test_instruction_policy import SYMBOLS
import native_escape


def escape(raw, **kwargs):
    return render(raw, lock_kind="mutex", abi=2, kernel_symbols=SYMBOLS,
                  native_escape_capable=True, return_status=True, **kwargs)


class NativeEscapeAdmissionTests(unittest.TestCase):
    def test_reviewed_instructions_emit_exit_before_source_instruction(self):
        # Initialize implicit EAX/ECX/EDX inputs, AH and all arithmetic flags.
        prefix = "31c031c931d283f801"
        for name, (opcode, _, _) in native_escape.INSTRUCTIONS.items():
            with self.subTest(instruction=name):
                options = {}
                assembly, log, status = escape(prefix + opcode.hex() + "c3",
                                               build_options=options)
                self.assertEqual(status, 0, log)
                self.assertEqual(options["requirements"], 1)
                self.assertIn(b"POP QWORD PTR[REG_BANK + KD_REG_FLAGS]", assembly)
                self.assertIn(b"R14, 0x1009", assembly)
                self.assertIn(b"Stack_IJ, 8", assembly)
                self.assertIn(b"full_exit", assembly)
                self.assertIn("NATIVE_ESCAPE_MARKER", log)
                self.assertNotIn("FLAGS_UNPRESERVED", log)

    def test_contract_is_only_mutex_abi2_and_negotiated(self):
        for kind, abi, capable in (("spin", 0, True), ("spin", 1, True),
                                   ("spin", 3, True), ("mutex", 0, True),
                                   ("mutex", 2, False)):
            with self.subTest(kind=kind, abi=abi, capable=capable):
                assembly, log, status = render("31c083f8010f31c3", lock_kind=kind,
                    abi=abi, kernel_symbols=SYMBOLS, native_escape_capable=capable,
                    return_status=True)
                self.assertEqual((status, assembly), (2, b""), log)
        options = {}
        _, log, status = escape("b82a000000c3", build_options=options)
        self.assertEqual(status, 0, log)
        self.assertEqual(options["requirements"], 0)
        self.assertIn("FLAGS_UNPRESERVED", log)

    def test_source_flags_and_implicit_inputs_must_be_defined(self):
        for raw, reason in (
            ("0f31c3", "source-defined arithmetic flags"),
            ("31c083f8010fa2c3", "input RCX is uncaptured"),
            ("31c083f8010f32c3", "input RCX is uncaptured"),
            ("31c031c983f8010f30c3", "input RDX is uncaptured"),
            ("31c983f9019ec3", "input RAX is uncaptured"),
            ("31c083f8010f3148891c2500600000c3", "uncaptured GPR"),
            ("750231c00f31c3", "uncaptured GPR"),
        ):
            with self.subTest(raw=raw):
                assembly, log, status = escape(raw)
                self.assertEqual((status, assembly), (2, b""), log)
                self.assertIn(reason, log)

    def test_prefixed_misdecoded_unknown_and_nonlocal_instructions_still_refuse(self):
        for raw in ("660f31", "480f31", "f30f31", "0f01cb", "9c", "9d",
                    "0f22d8", "48cf", "0f05", "c7f800000000", "0f01d5"):
            with self.subTest(raw=raw):
                assembly, log, status = escape("31c031c931d283f801" + raw + "c3" + "90" * 16)
                self.assertEqual((status, assembly), (2, b""), log)
        for line in (
            SimpleNamespace(name="NOP", args=[], b=b"\x0f\x31", l=2),
            SimpleNamespace(name="RDTSC", args=[], b=b"\x0f\x31", l=3),
            SimpleNamespace(name="RDTSC", args=[1], b=b"\x0f\x31", l=2),
        ):
            self.assertIsNone(native_escape.descriptor(line))

    def test_only_exact_rdtscp_decoder_alias_is_normalized(self):
        for name, operand, raw, expected in (
            ("INVLPG", ExprId("ECX", 32), b"\x0f\x01\xf9", "RDTSCP"),
            ("INVLPG", ExprId("EAX", 32), b"\x0f\x01\xf9", "INVLPG"),
            ("INVLPG", ExprId("ECX", 32), b"\x0f\x01\xf8", "INVLPG"),
            ("NOP", ExprId("ECX", 32), b"\x0f\x01\xf9", "NOP"),
        ):
            with self.subTest(name=name, operand=operand, raw=raw):
                original = SimpleNamespace(name=name, args=[operand], b=raw, l=3)
                block = SimpleNamespace(lines=[original])
                native_escape.normalize_decoded({0x1000: block})
                self.assertEqual(block.lines[0].name, expected)
                self.assertEqual(original.name, name)
                self.assertEqual(bool(native_escape.descriptor(block.lines[0])), expected == "RDTSCP")

    def test_native_suffix_and_cold_branch_keep_original_context_checks(self):
        # Both reachable branches are checked even though their markers exit.
        for raw in ("31c083f8010f31488b042500300000c3",
                    "31c083f80174020f31488b042500300000c3"):
            assembly, log, status = escape(raw, symbols={0x3000: "current_task"})
            self.assertEqual((status, assembly), (2, b""), log)
            self.assertIn("context-sensitive", log)

    def test_taken_and_untaken_paths_share_a_checked_marker_image(self):
        assembly, log, status = escape("31c083f80074020f31b82a000000c3")
        self.assertEqual(status, 0, log)
        self.assertIn(b"R14, 0x1007", assembly)
        self.assertIn(b"loc_1009:", assembly)
        self.assertRegex(assembly, rb"MOV\s+EAX,\s+0x2A")
        self.assertIn(b"PUSHFQ\nDEC", assembly)


if __name__ == "__main__":
    unittest.main(verbosity=2)
