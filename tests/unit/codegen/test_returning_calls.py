"""Focused returning-CALL registry and emitted continuation checks."""
import struct
import unittest

from test_jit_diagnostics import render, translator


class ReturningCallTests(unittest.TestCase):
    @staticmethod
    def body(with_helper=True):
        base, helper, unlock = 0x1000, 0x5500, 0x6100
        raw = b''
        if with_helper:
            raw += b'\xe8' + struct.pack('<i', helper - base - 5)
        raw += bytes.fromhex('480534120000')
        raw += b'\xe8' + struct.pack('<i', unlock - (base + len(raw)) - 5) + b'\xc3'
        return raw.hex()

    def emit(self, with_helper=True):
        options = {}
        assembly, log, status = render(
            self.body(with_helper), lock_kind='mutex', abi=2,
            trusted_source=True, native_escape_capable=True,
            kernel_symbols={'kd_mutex_direct_lock_clobber_v1': 0x7000,
                            'kd_mutex_direct_unlock_clobber_v1': 0x7100,
                            'kd_rwsem_up_write_clobber_v1': 0x6100},
            returning_services={0x5500: dict(cookie=1, nargs=6, result_kind=1,
                                             context_kind=1, symbol='primitive_call')},
            build_options=options, return_status=True)
        self.assertEqual(status, 0, log)
        return assembly, options

    def test_declared_call_keeps_body_and_exact_flags_successor(self):
        assembly, options = self.emit()
        self.assertEqual(options['requirements'], 896)
        self.assertIn(b'KD_REG_SERVICE_REENTRY_TAG', assembly)
        self.assertIn(b'kd_service_dispatch_1005:', assembly)
        self.assertIn(b'loc_1005:', assembly)
        self.assertIn(b'0x1234', assembly)
        self.assertIn(b'loc_5500:', assembly)

    def test_unused_descriptor_keeps_ordinary_image_contract(self):
        assembly, options = self.emit(False)
        self.assertEqual(options['requirements'], 128)
        self.assertNotIn(b'KD_REG_SERVICE_REENTRY_TAG', assembly)

    def test_native_context_values_and_indirect_successor(self):
        parse = translator.memread.device_session.parse_service_calls
        for context in range(1, 10):
            row = f'1 ffffffff81001000 1 1 {context} primitive_call\n'
            self.assertEqual(parse(row)[0xffffffff81001000]['context_kind'], context)
        options = {}
        assembly, log, status = render(
            'ffd0480534120000e8f3500000c3', lock_kind='mutex', abi=2,
            trusted_source=True, native_escape_capable=True,
            indirect_call_capable=True,
            kernel_symbols={'kd_mutex_direct_lock_clobber_v1': 0x7000,
                            'kd_mutex_direct_unlock_clobber_v1': 0x7100,
                            'kd_rwsem_up_write_clobber_v1': 0x6100},
            returning_services={0x5500: dict(cookie=1, nargs=1, result_kind=1,
                                             context_kind=2, symbol='primitive_call')},
            build_options=options, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertEqual(options['requirements'], 896)
        self.assertIn(b'kd_service_dispatch_1002:', assembly)
        self.assertIn(b'PUSHFQ\nPOP QWORD PTR[REG_BANK + KD_REG_FLAGS]', assembly)

    def test_registry_refuses_partial_duplicate_and_unknown_contracts(self):
        parse = translator.memread.device_session.parse_service_calls
        row = '1 ffffffff81001000 6 1 1 primitive_call\n'
        self.assertEqual(len(parse(row)), 1)
        for text in (row + row, row.replace('6 1 1', '7 1 1'),
                     row.replace('6 1 1', '6 3 1'), row.replace('6 1 1', '6 1 10'),
                     row.replace('1 ffffffff', '0 ffffffff'), '1 ffffffff81001000',
                     'x' * 4097):
            with self.subTest(text=text[:100]), self.assertRaises(ValueError):
                parse(text)

    def test_native_tail_target_keeps_real_callers_successor(self):
        raw = bytearray.fromhex('e81b000000480534120000e8f0500000c3')
        raw.extend(b'\x90' * (0x20 - len(raw)))
        raw.extend(b'\xe9' + struct.pack('<i', 0x5500 - 0x1025))
        raw.extend(b'\x90' * 16)
        options = {}
        assembly, log, status = render(
            raw.hex(),
            lock_kind='mutex', abi=2, trusted_source=True,
            native_escape_capable=True,
            kernel_symbols={'kd_mutex_direct_lock_clobber_v1': 0x7000,
                            'kd_mutex_direct_unlock_clobber_v1': 0x7100,
                            'kd_rwsem_up_write_clobber_v1': 0x6100},
            returning_services={0x5500: dict(cookie=1, nargs=1, result_kind=1,
                                             context_kind=2, symbol='primitive_call')},
            build_options=options, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertEqual(options['requirements'], 896)
        self.assertIn(b'kd_service_dispatch_1005:', assembly)
        self.assertIn(b'loc_5500:', assembly)

    def test_conditional_native_tail_keeps_both_source_paths(self):
        raw = bytearray.fromhex('e81b000000480534120000e8f0500000c3')
        raw.extend(b'\x90' * (0x20 - len(raw)))
        raw.extend(b'\x85\xc0\x0f\x85' + struct.pack('<i', 0x5500 - 0x1028))
        raw.extend(b'\xc3' + b'\x90' * 16)
        options = {}
        assembly, log, status = render(
            raw.hex(), lock_kind='mutex', abi=2, trusted_source=True,
            native_escape_capable=True,
            kernel_symbols={'kd_mutex_direct_lock_clobber_v1': 0x7000,
                            'kd_mutex_direct_unlock_clobber_v1': 0x7100,
                            'kd_rwsem_up_write_clobber_v1': 0x6100},
            returning_services={0x5500: dict(cookie=1, nargs=1, result_kind=1,
                                             context_kind=2, symbol='primitive_call')},
            build_options=options, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertEqual(options['requirements'], 896)
        self.assertIn(b'kd_service_dispatch_1005:', assembly)
        self.assertIn(b'loc_5500:', assembly)
        self.assertIn(b'loc_1028:', assembly)


if __name__ == '__main__':
    unittest.main()
