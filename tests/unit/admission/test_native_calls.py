"""Current ordinary-call routing and legacy provider bridge ABI compatibility."""
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

    def test_legacy_capabilities_do_not_change_ordinary_call_codegen(self):
        for target in (0x2000, 0x3000):
            outputs = []
            for direct in (False, True):
                options = {}
                assembly, log, status = self.render(
                    self.source(target), direct_strings_capable=direct,
                    build_options=options)
                self.assertEqual(status, 0, log)
                self.assertEqual(options["requirements"], 0)
                for marker in (b"KDNC0001", b"KD_HOSTCALL id=4",
                               b"KD_HOSTCALL id=5", b"KD_DIRECT_STRING"):
                    self.assertNotIn(marker, assembly)
                outputs.append(assembly)
            self.assertEqual(*outputs)

    def test_scalar_service_remains_the_only_selected_dispatcher(self):
        options = {}
        assembly, log, status = render(
            (call(0x4000, 0x1000) + b"\xc3").hex(), abi=1,
            kernel_symbols=SYMBOLS | {"ktime_get": 0x4000},
            string_services_capable=True, string_write_capable=True,
            audited_strings_capable=True, direct_strings_capable=True,
            build_options=options, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertEqual(options["requirements"], 0)
        self.assertIn(b"KD_HOSTCALL id=1", assembly)
        self.assertNotIn(b"KDNC0001", assembly)

    def test_legacy_bridge_mapping_and_directory_bounds_remain_fail_closed(self):
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
