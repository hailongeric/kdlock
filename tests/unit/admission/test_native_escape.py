"""Reviewed marker admission; privileged instruction bytes are never executed."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from miasm.expression.expression import ExprId

from test_jit_diagnostics import render, translator
from test_instruction_policy import SYMBOLS, call
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


class RootNativeEscapeAdmissionTests(unittest.TestCase):
    prefix = bytes.fromhex("31c031c931d283f801")
    marker = b"\x0f\x31"
    metadata = bytes.fromhex("bf006000004889e64889e9ba00000000")

    def render(self, raw, abi=1, **kwargs):
        return render(raw.hex(), lock_kind="spin", abi=abi,
                      kernel_symbols=kwargs.pop("kernel_symbols", SYMBOLS),
                      root_native_escape_capable=True,
                      return_status=True, **kwargs)

    def refusal(self, raw, reason, **kwargs):
        # A refusal must precede emission, not leave an unusable NORMAL image.
        with patch.object(translator, "emit_jit_assembly",
                          side_effect=AssertionError("refused root reached emission")):
            assembly, log, status = self.render(raw, **kwargs)
        self.assertEqual((status, assembly), (2, b""), log)
        self.assertIn(reason, log)

    def terminal(self, target):
        raw = self.prefix + self.marker + self.metadata
        return raw + call(target, 0x1000 + len(raw)) + b"\xc3"

    def test_separate_capability_and_exact_image_requirement(self):
        raw = self.prefix + self.marker + b"\xc3"
        for abi in (1, 3):
            for capable in (False, True):
                with self.subTest(abi=abi, capable=capable):
                    options = {}
                    assembly, log, status = render(
                        raw.hex(), lock_kind="spin", abi=abi,
                        kernel_symbols=SYMBOLS, native_escape_capable=True,
                        root_native_escape_capable=capable,
                        return_status=True, build_options=options)
                    self.assertEqual(status, 0 if capable else 2, log)
                    if capable:
                        self.assertEqual(options["requirements"], 33)
                        self.assertIn(b"Stack_IJ, 8", assembly)
                    else:
                        self.assertEqual(assembly, b"")
        options = {}
        _, log, status = self.render(b"\xb8\x2a\0\0\0\xc3", build_options=options)
        self.assertEqual(status, 0, log)
        self.assertEqual(options["requirements"], 0)
        # The new capability cannot authorize legacy spin or mutex packets.
        for kind, abi in (("spin", 0), ("mutex", 0), ("mutex", 2)):
            assembly, log, status = render(
                raw.hex(), lock_kind=kind, abi=abi, kernel_symbols=SYMBOLS,
                root_native_escape_capable=True, return_status=True)
            self.assertEqual((status, assembly), (2, b""), log)

    def test_reviewed_set_and_source_proofs_remain_required(self):
        for abi in (1, 3):
            for name, (opcode, _, _) in native_escape.INSTRUCTIONS.items():
                with self.subTest(abi=abi, instruction=name):
                    options = {}
                    _, log, status = self.render(
                        self.prefix + opcode + b"\xc3", abi, build_options=options)
                    self.assertEqual(status, 0, log)
                    self.assertEqual(options["requirements"], 33)
            self.refusal(self.marker + b"\xc3",
                         "source-defined arithmetic flags", abi=abi)
            self.refusal(bytes.fromhex("31c083f8010fa2c3"),
                         "input RCX is uncaptured", abi=abi)
            self.refusal(self.prefix + self.marker +
                         bytes.fromhex("488b042500300000c3"),
                         "context-sensitive", abi=abi,
                         symbols={0x3000: "current_task"})
            for unsupported in ("660f31", "0f01cb", "9d", "0f22d8"):
                self.refusal(self.prefix + bytes.fromhex(unsupported) +
                             b"\xc3" + b"\x90" * 16,
                             "CONTEXT_NATIVE_ONLY", abi=abi)

    def test_terminal_unlock_and_missing_direct_callee_stay_admissible(self):
        for abi in (1, 3):
            for target in (SYMBOLS["kd_spin_unlock_clobber_v1"], 0x4000):
                with self.subTest(abi=abi, target=target):
                    _, log, status = self.render(self.terminal(target), abi)
                    self.assertEqual(status, 0, log)

    def test_nested_controls_and_services_before_or_after_marker_refuse(self):
        for abi in (1, 3):
            for name, target in (
                    ("kd_spin_lock_clobber_v1", SYMBOLS["kd_spin_lock_clobber_v1"]),
                    ("kd_rwlock_lock_pinned_clobber_v1", 0x4000),
                    ("kd_spin_direct_native_lock", 0x5000),
                    ("kd_spin_direct_native_contended", 0x6000),
                    ("kd_spin_direct_native_unlock", 0x7000),
                    ("ktime_get", 0x8000)):
                for before in (False, True):
                    with self.subTest(abi=abi, helper=name, before=before):
                        raw = self.prefix + (b"" if before else self.marker)
                        raw += call(target, 0x1000 + len(raw))
                        # A known missing native helper ends its source phase.
                        # Keep another branch's marker independently selected.
                        if before and name not in ("kd_spin_lock_clobber_v1", "ktime_get"):
                            raw = (self.prefix + b"\x74\x05" +
                                   call(target, 0x1000 + len(self.prefix) + 2) +
                                   self.prefix + self.marker + b"\xc3")
                        else:
                            raw += self.prefix + (self.marker if before else b"") + b"\xc3"
                        reason = ("hostcall services" if name == "ktime_get"
                                  else "lock control")
                        self.refusal(raw, reason, abi=abi,
                                     kernel_symbols=SYMBOLS | {name: target})

    def test_early_unlock_with_a_nested_hold_is_refused_before_trimming(self):
        target = SYMBOLS["kd_spin_lock_clobber_v1"]
        unlock = SYMBOLS["kd_spin_unlock_clobber_v1"]
        raw = self.prefix + self.marker + self.metadata
        raw += call(target, 0x1000 + len(raw)) + self.metadata
        raw += call(unlock, 0x1000 + len(raw)) + self.metadata
        raw += call(unlock, 0x1000 + len(raw)) + b"\xc3"
        for abi in (1, 3):
            self.refusal(raw, "lock control", abi=abi)

    def test_indirect_history_tail_controls_and_address_taking_refuse(self):
        for abi in (1, 3):
            for suffix in (bytes.fromhex("ffd0"), bytes.fromhex("ffe0")):
                self.refusal(self.prefix + self.marker + suffix + b"\xc3",
                             "indirect control", abi=abi)
            self.refusal(self.prefix + self.marker + b"\xc3",
                         "learned indirect control", abi=abi,
                         indirect_history={0x100b: [0x1000]})
            target = SYMBOLS["kd_spin_lock_clobber_v1"]
            self.refusal(self.prefix + self.marker +
                         b"\x48\xb8" + target.to_bytes(8, "little") + b"\xc3",
                         "lock control", abi=abi)
            branch = call(target, 0x1000 + len(self.prefix) + len(self.marker))
            self.refusal(self.prefix + self.marker + b"\xe9" + branch[1:],
                         "lock control", abi=abi)

    def test_rwlock_fast_unlock_is_only_an_unlearned_terminal_abi3_call(self):
        name, target = "kd_rwlock_fast_write_unlock", 0x4000
        symbols = SYMBOLS | {name: target}
        raw = self.terminal(target)
        _, log, status = self.render(raw, 3, kernel_symbols=symbols)
        self.assertEqual(status, 0, log)
        self.refusal(raw, "lock control", abi=1, kernel_symbols=symbols)
        # Learning the helper must not turn the native-only branch into code
        # that returns to this marker image, even when its body is just RET.
        self.refusal(b"", "lock control", abi=3, kernel_symbols=symbols,
                     regions=[(raw, 0x1000, [0x1000]),
                              (b"\xc3", target, [target])])
        # A second source edge reaches the CALL continuation, so it is not a
        # terminal native boundary for the complete selected source graph.
        raw = (self.prefix + self.marker + b"\x74\x05" +
               call(target, 0x1000 + len(self.prefix) + len(self.marker) + 2) +
               b"\xb8\x2a\0\0\0\xc3")
        self.refusal(raw, "lock control", abi=3, kernel_symbols=symbols)

    def test_marker_images_do_not_prune_source_before_flag_and_control_proof(self):
        # Constant-path specialization could otherwise hide the source UD2
        # and leave a weaker graph for the marker's original native suffix.
        raw = self.prefix + self.marker + bytes.fromhex("31c07501c30f0b")
        with patch.object(translator.constant_paths, "specialize",
                          side_effect=AssertionError("marker source was pruned")):
            self.refusal(raw, "CONTEXT_NATIVE_ONLY")


if __name__ == "__main__":
    unittest.main(verbosity=2)
