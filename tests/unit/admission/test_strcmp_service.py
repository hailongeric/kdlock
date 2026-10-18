"""Guest-only original API resolution and ordinary caller admission regressions."""
import struct
import unittest

from miasm.expression.expression import ExprId
from test_jit_diagnostics import decode, render, translator
from address_guards import AddressGuards, GuardSite
from context_values import FlowConstants
import hostcall
import strcmp_service


ADDRESS = 0x2000
SYMBOLS = {"strcmp": ADDRESS,
           "kd_raw_spin_lock_clobber_v1": 0x3000,
           "kd_raw_spin_unlock_clobber_v1": 0x4000}


def call(target, address):
    return b"\xe8" + struct.pack("<i", target - address - 5)


class StrcmpServiceTests(unittest.TestCase):
    def reader(self, address, size):
        self.fail("original strcmp code or data must not be inspected")

    def render(self, prefix="488b7df8488b75f0", suffix="4839c0c3", **kwargs):
        before = bytes.fromhex(prefix)
        raw = before + call(ADDRESS, 0x1000 + len(before)) + bytes.fromhex(suffix)
        return render(raw.hex(), abi=1, kernel_symbols=SYMBOLS,
                      memory_reader=self.reader, string_services_capable=True,
                      audited_strings_capable=True, return_status=True, **kwargs)

    def test_resolver_uses_only_original_symbol_and_negotiated_api_contract(self):
        lookup = lambda name, default=0: SYMBOLS.get(name, default)
        self.assertNotIn(ADDRESS, hostcall.resolve_hostcalls(lookup))
        self.assertNotIn(ADDRESS, hostcall.resolve_hostcalls(
            lookup, string_services=True))
        self.assertNotIn(ADDRESS, hostcall.resolve_hostcalls(
            lookup, audited_strings=True))
        resolved = hostcall.resolve_hostcalls(lookup, string_services=True, audited_strings=True)
        self.assertEqual(strcmp_service.targets(resolved), {ADDRESS})
        self.assertIn(ADDRESS, hostcall.readonly_waiter_targets(resolved))
        self.assertFalse(strcmp_service.targets(hostcall.resolve_hostcalls(
            lambda name, default=0: default, string_services=True, audited_strings=True)))

    def test_actual_service_call_sets_image_requirement_and_keeps_virtual_call(self):
        options = {}
        assembly, log, status = self.render(build_options=options)
        self.assertEqual(status, 0, log)
        self.assertIn(b"KD_HOSTCALL id=4 symbol=strcmp", assembly)
        self.assertEqual(options["requirements"], strcmp_service.REQUIREMENT)
        self.assertNotIn(b"KDCS0001", assembly)
        self.assertRegex(assembly, rb"QWORD PTR \[R13\], R(?:14|15)")
        # Negotiating a service does not add an image requirement to unrelated
        # source; immutable-image selection remains tied to actual CALL use.
        options = {}
        _, log, status = render("31c0c3", abi=1, kernel_symbols=SYMBOLS,
                                memory_reader=self.reader, string_services_capable=True,
                                audited_strings_capable=True, build_options=options,
                                return_status=True)
        self.assertEqual(status, 0, log)
        self.assertEqual(options["requirements"], 0)

    def test_pointer_arguments_must_be_captured_and_context_screened(self):
        for prefix, symbols, reason in (
            ("488b75f0", {}, "uncaptured"),
            ("488b7df8", {}, "uncaptured"),
            ("48c7c700600000488b75f0", {0x6008: "current_task"}, "context-sensitive strcmp"),
            ("488b7df848c7c600600000", {0x60ff: "current_task"}, "context-sensitive strcmp"),
        ):
            with self.subTest(prefix=prefix):
                assembly, log, status = self.render(prefix=prefix, symbols=symbols)
                self.assertEqual((assembly, status), (b"", 2), log)
                self.assertIn(reason, log)

    def test_widened_argument_is_not_hidden_by_readonly_service_summary(self):
        tracker = FlowConstants()
        tracker.values[ExprId("RDI", 64)] = None
        line = decode("e8fb0f0000")
        line.offset = 0x1000
        blocks, dbs = translator.decode_regions([(bytes.fromhex("e8fb0f0000c3"),
                                                  0x1000, [0x1000])], 0, {ADDRESS})
        line = blocks[0x1000].lines[0]
        with self.assertRaises(translator.context_policy.ContextFlowLimit):
            strcmp_service.argument_rejection(line, dbs[blocks[0x1000]], tracker,
                                               {ADDRESS}, {})

    def test_original_api_contract_does_not_supply_a_source_flags_proof(self):
        raw = bytes.fromhex("488b07") + call(ADDRESS, 0x1003) + b"\xc3"
        blocks, dbs = translator.decode_regions([(raw, 0x1000, [0x1000])], 0, {ADDRESS})
        line = blocks[0x1000].lines[0]
        guards = AddressGuards()
        guards.sites[0x1000] = GuardSite(line, line.args[1], {("RSP", -8, 0)})
        with self.assertRaises(translator.context_policy.ContextFlowLimit):
            guards.validate(blocks, dbs)
        resolved = hostcall.resolve_hostcalls(lambda name, default=0: SYMBOLS.get(name, default),
                                             string_services=True, audited_strings=True)
        self.assertEqual(strcmp_service.targets(resolved), {ADDRESS})
        with self.assertRaises(translator.context_policy.ContextFlowLimit):
            guards.validate(blocks, dbs)

    def test_dynamic_node_load_keeps_call_word_alias_model_and_emits_guard(self):
        # Exact dynamic list-pointer shape: stack write can alias the node's
        # name pointer. The pointer argument must not be treated as a scalar;
        # only the checked actual MOV can replace that uncertain alternative.
        # A source CMP, not an unchecked helper assumption, kills the flags.
        prefix = "488b7df8488b5df0488b1b48c74424f833330000488b33"
        assembly, log, status = self.render(prefix=prefix, address_guard_capable=True)
        self.assertEqual((assembly, status), (b"", 2), log)
        assembly, log, status = self.render(prefix=prefix + "4839ff", address_guard_capable=True)
        self.assertEqual(status, 0, log)
        self.assertIn("ADDRESS_GUARDED_ADMISSION", log)
        self.assertIn(b"kd_address_guard_failed_", assembly)
        self.assertIn(b"KD_HOSTCALL id=4 symbol=strcmp", assembly)

    def test_service_scope_rejects_nested_control_and_keeps_outer_completion(self):
        for nested in (False, True):
            raw = bytes.fromhex("488b7df8488b75f0")
            raw += call(ADDRESS, 0x1000 + len(raw))
            targets = (0x3000, 0x4000, 0x4000) if nested else (0x4000,)
            for target in targets:
                raw += bytes.fromhex("bf009000004889e6")
                continuation = 0x1000 + len(raw) + 5 + 3 + 5
                raw += b"\xba" + struct.pack("<I", continuation)
                raw += bytes.fromhex("4889e9")
                raw += call(target, 0x1000 + len(raw))
            raw += b"\xc3"
            with self.subTest(nested=nested):
                assembly, log, status = render(
                    raw.hex(), abi=1, kernel_symbols=SYMBOLS,
                    memory_reader=self.reader, string_services_capable=True,
                    audited_strings_capable=True, return_status=True)
                self.assertEqual(status, 2 if nested else 0, log)
                if nested:
                    self.assertEqual(assembly, b"")
                    self.assertIn("typed string services require a top-level single-lock scope", log)
                else:
                    self.assertIn(b"KD_HOSTCALL id=4 symbol=strcmp", assembly)


if __name__ == "__main__":
    unittest.main()
