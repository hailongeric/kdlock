"""Guest-only admission and code generation for one-invocation API bridges."""
import struct
import unittest
from types import SimpleNamespace

from test_jit_diagnostics import render
import conflict
import hostcall
import native_calls


SYMBOLS = {"strcmp": 0x2000, "strscpy_pad": 0x3000,
           "kd_raw_spin_lock_clobber_v1": 0x6000,
           "kd_raw_spin_unlock_clobber_v1": 0x7000}


def call(target, source):
    return b"\xe8" + struct.pack("<i", target - source - 5)


class NativeCallTests(unittest.TestCase):
    def render(self, raw, **kwargs):
        return render(raw.hex(), abi=1, kernel_symbols=SYMBOLS,
                      memory_reader=lambda *_: self.fail("helper code/data inspected"),
                      string_services_capable=True, string_write_capable=True,
                      audited_strings_capable=True, return_status=True, **kwargs)

    def source(self, target=0x2000):
        prefix = bytes.fromhex("488b7df8488b75f0" if target == 0x2000 else
                               "488d7d90be00900000ba40000000")
        return prefix + call(target, 0x1000 + len(prefix)) + bytes.fromhex("4839c0c3")

    def test_direct_calls_require_new_capability_and_preserve_existing_dispatcher(self):
        for direct in (False, True):
            options = {}
            assembly, log, status = self.render(
                self.source(), direct_strings_capable=direct, build_options=options)
            self.assertEqual(status, 0, log)
            self.assertEqual(options["requirements"], 20 if direct else 4)
            self.assertEqual(b"KDNC0001" in assembly, direct)
            self.assertEqual(b"KD_HOSTCALL id=4" in assembly, not direct)
            self.assertEqual(b"KD_DIRECT_STRING id=4" in assembly, direct)

    def test_writer_has_distinct_effect_requirement_and_original_return_pc(self):
        options = {}
        assembly, log, status = self.render(
            self.source(0x3000), direct_strings_capable=True, build_options=options)
        self.assertEqual(status, 0, log)
        self.assertEqual(options["requirements"], 24)
        self.assertIn(b"KD_DIRECT_STRING id=5 symbol=strscpy_pad", assembly)
        call_ip = 0x1000 + len(bytes.fromhex("488d7d90be00900000ba40000000"))
        self.assertIn(f".long kd_native_call_{call_ip:x} - main\n.long 5\n.quad 0x{call_ip + 5:x}".encode(), assembly)
        self.assertIn(b"MOV QWORD PTR[R13], R14", assembly)
        self.assertIn(b"MOV R14, QWORD PTR[R13]", assembly)
        self.assertNotIn(b"MOV EAX, EAX", assembly)

    def test_only_root_is_dispatchable_and_quota_exit_precedes_call(self):
        assembly, log, status = self.render(self.source(), direct_strings_capable=True)
        self.assertEqual(status, 0, log)
        self.assertNotIn(b"JZ      loc_100d", assembly.split(b"loc_1000:", 1)[0])
        self.assertIn(b"JMP loc_100d", assembly)
        self.assertIn(b"MOV EAX, EAX", assembly)
        self.assertLess(assembly.index(b"JRCXZ kd_native_call_1008_limit"),
                        assembly.index(b"kd_native_call_1008:\n.byte 0xe8"))
        self.assertIn(b"MOV Stack_IJ, 10\nJMP full_exit", assembly)
        self.assertIn(b"MOV Stack_IJ, 2\nJMP full_exit", assembly)
        self.assertIn(b"PUSH R11", assembly)
        self.assertIn(b"POP R11", assembly)
        self.assertIn(b"MOV RCX, R14\nMOVABS R14, 0x2000", assembly)
        self.assertIn(b"JRCXZ kd_native_call_1008_returned", assembly)
        self.assertIn(b"MOV RCX, R15\nMOV Stack_IJ, 2", assembly)
        self.assertNotIn(b"AND RSP", assembly)
        self.assertNotIn(b"Stack_NATIVE_", assembly)
        self.assertNotIn(b"PUSHFQ", assembly)
        self.assertNotIn(b"POPFQ", assembly)
        self.assertNotIn(b"CALL R", assembly)

    def test_scalar_service_keeps_dispatcher_and_cannot_reset_direct_quotas(self):
        raw = self.source()[:-4]
        raw += call(0x4000, 0x1000 + len(raw)) + bytes.fromhex("4839c0c3")
        options = {}
        assembly, log, status = render(
            raw.hex(), abi=1, kernel_symbols=SYMBOLS | {"ktime_get": 0x4000},
            memory_reader=lambda *_: self.fail("helper code/data inspected"),
            string_services_capable=True, audited_strings_capable=True,
            direct_strings_capable=True, build_options=options, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertEqual(options["requirements"], 4)
        self.assertNotIn(b"KDNC0001", assembly)
        self.assertIn(b"KD_HOSTCALL id=4", assembly)

    def test_guarded_images_keep_the_existing_dispatcher_contract(self):
        prefix = bytes.fromhex("488b7df8488b5df0488b1b48c74424f833330000488b334839ff")
        raw = prefix + call(0x2000, 0x1000 + len(prefix)) + bytes.fromhex("4839c0c3")
        options = {}
        assembly, log, status = self.render(raw, direct_strings_capable=True,
                                           address_guard_capable=True, build_options=options)
        self.assertEqual(status, 0, log)
        self.assertEqual(options["requirements"], 6)
        self.assertIn(b"KDAG0001", assembly)
        self.assertNotIn(b"KDNC0001", assembly)

    def test_learned_indirect_service_target_is_never_a_direct_call_site(self):
        # MOV EAX,strcmp; load original pointer args; CALL RAX. A learned
        # target cannot turn this into the direct source-CALL contract.
        raw = bytes.fromhex("b800200000488b7df8488b75f0ffd04839c0c3")
        for capable in (False, True):
            assembly, log, status = self.render(
                raw, direct_strings_capable=capable,
                indirect_history={0x100f: [0x2000]})
            self.assertEqual((assembly, status), (b"", 2), log)
            self.assertIn("cannot use learned indirect-call targets", log)

    def test_mapping_spills_and_directory_bound_remain_fail_closed(self):
        spec = hostcall.HostcallSpec("STRCMP", 4, "strcmp")
        bridge = native_calls.NativeCalls({0x2000: spec})
        mapping = conflict.block_init()
        mapping["14"] = "15"
        mapping.dirty.add("15")
        emitted = bridge.emit(SimpleNamespace(offset=0x1000), 0x1005, 0x2000, mapping)
        self.assertIn("Stack_R15", emitted)
        self.assertEqual(mapping, conflict.block_init())
        self.assertEqual(mapping.dirty, set())
        for index in range(native_calls.MAX_SITES - 1):
            bridge.emit(SimpleNamespace(offset=0x1100 + index * 5), 0x2000, 0x2000, mapping)
        with self.assertRaisesRegex(ValueError, "64 sites"):
            bridge.emit(SimpleNamespace(offset=0x3000), 0x3005, 0x2000, mapping)
        bad = conflict.block_init()
        bad["13"] = "15"
        with self.assertRaisesRegex(ValueError, "canonical virtual SP/BP"):
            native_calls.NativeCalls({0x2000: spec}).emit(
                SimpleNamespace(offset=0x1000), 0x1005, 0x2000, bad)


if __name__ == "__main__":
    unittest.main()
