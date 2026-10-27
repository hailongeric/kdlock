"""Current ordinary-call routing plus explicitly legacy provider helper tests."""
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

    def test_legacy_capabilities_never_select_a_string_service(self):
        lookup = lambda name, default=0: SYMBOLS.get(name, default)
        for services in (False, True):
            for audited in (False, True):
                resolved = hostcall.resolve_hostcalls(
                    lookup, string_services=services, audited_strings=audited)
                self.assertNotIn(ADDRESS, resolved)
                self.assertFalse(strcmp_service.targets(resolved))
                self.assertNotIn(ADDRESS, hostcall.readonly_waiter_targets(resolved))

    def test_missing_original_callee_uses_ordinary_call_exit(self):
        options = {}
        assembly, log, status = self.render(build_options=options)
        self.assertEqual(status, 0, log)
        self.assertEqual(options["requirements"], 0)
        self.assertNotIn(b"KD_HOSTCALL id=4", assembly)
        self.assertNotIn(b"KD_DIRECT_STRING", assembly)
        self.assertRegex(assembly, rb"QWORD PTR \[R13\], R(?:14|15)")

    def test_original_callee_bytes_keep_context_admission(self):
        raw = bytes.fromhex("bf00900000be00a00000")
        raw += call(ADDRESS, 0x1000 + len(raw)) + b"\xc3"
        # An actual unsafe callee must be decoded and refused regardless of
        # legacy advertised string capabilities or its resolved symbol name.
        regions = [(raw, 0x1000, [0x1000]),
                   (bytes.fromhex("64488b042528000000c3"), ADDRESS, [ADDRESS])]
        assembly, log, status = render(
            "", regions=regions, abi=1, kernel_symbols=SYMBOLS,
            string_services_capable=True, audited_strings_capable=True,
            return_status=True)
        self.assertEqual((assembly, status), (b"", 2), log)
        self.assertIn("FS:", log)

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
        self.assertEqual(strcmp_service.targets(resolved), set())
        with self.assertRaises(translator.context_policy.ContextFlowLimit):
            guards.validate(blocks, dbs)

    def test_original_callee_is_emitted_even_with_legacy_capabilities(self):
        raw = call(ADDRESS, 0x1000) + b"\xc3"
        regions = [(raw, 0x1000, [0x1000]),
                   (bytes.fromhex("b82a000000c3"), ADDRESS, [ADDRESS])]
        options = {}
        assembly, log, status = render(
            "", regions=regions, abi=1, kernel_symbols=SYMBOLS,
            string_services_capable=True, audited_strings_capable=True,
            build_options=options, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertIn(b"loc_2000:", assembly)
        self.assertNotIn(b"KD_HOSTCALL id=4", assembly)
        self.assertEqual(options["requirements"], 0)




if __name__ == "__main__":
    unittest.main()
