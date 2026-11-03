"""Focused returning-CALL registry and emitted continuation checks."""
import ctypes
import struct
import unittest
from unittest.mock import patch

from test_jit_diagnostics import render, translator
from test_jit_body_witness import run_image


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

    def test_retained_text_policy_covers_initial_read_and_callee_extension(self):
        base = 0xffffffffc1000000
        callee, unlock = base + 0x4000, base + 0x5000
        raw = b'\xe8' + struct.pack('<i', callee - base - 5)
        raw += b'\xe8' + struct.pack('<i', unlock - base - 10) + b'\xc3'
        body = bytes.fromhex('b82a000000c3')
        reads, policies = [], []

        def read(address, size):
            reads.append((address, size))
            if address == base:
                self.assertEqual(size, len(raw))
                return raw
            self.assertEqual(address, callee)
            return body + b'\x90' * (size - len(body))

        memread = translator.memread
        with patch.object(memread, 'extend_regions', wraps=memread.extend_regions) as extend:
            assembly, log, status = render(
                raw.hex(), entry=base, lock_kind='mutex', abi=2, trusted_source=True,
                native_escape_capable=True, memory_reader=read, read_policies=policies,
                kernel_symbols={'kd_mutex_direct_lock_clobber_v1': base + 0x6000,
                                'kd_mutex_direct_unlock_clobber_v1': base + 0x6100,
                                'kd_rwsem_up_write_clobber_v1': unlock},
                returning_services={base + 0x5500: dict(cookie=1, nargs=1,
                    result_kind=1, context_kind=1, symbol='unused_primitive')},
                return_status=True)
        self.assertEqual(status, 0, log)
        self.assertEqual(policies, [memread.RETAINED_WINDOW_POLICY])
        self.assertEqual(reads, [(base, len(raw)), (callee, 1024)])
        extend.assert_called_once()
        self.assertIs(extend.call_args.kwargs['policy'], policies[0])
        self.assertIn(f'loc_{callee:x}:'.encode(), assembly)
        self.assertIn('reason=TEXT_CACHE_PLAN', log)
        self.assertIn('reason=DECODED_TEXT_COVERAGE', log)

    def test_ordinary_translation_keeps_default_text_policy(self):
        policies = []
        _, log, status = render('90c3', read_policies=policies, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertEqual(policies, [translator.memread.DEFAULT_WINDOW_POLICY])

    def test_return_flow_work_profile_is_explicit_and_retained_only(self):
        original = translator.indirect_jump.find
        with patch.object(translator.indirect_jump, 'find', wraps=original) as find:
            self.emit()
        self.assertGreater(len(find.call_args_list), 0)
        self.assertTrue(all(call.kwargs['max_visits'] == 262144
                            for call in find.call_args_list))
        with patch.object(translator.indirect_jump, 'find', wraps=original) as find:
            _, log, status = render('90c3', return_status=True)
        self.assertEqual(status, 0, log)
        self.assertGreater(len(find.call_args_list), 0)
        self.assertTrue(all(call.kwargs.get('max_visits', 65536) == 65536
                            for call in find.call_args_list))
        self.assertIn('work_limit=65536', log)

    def test_retained_return_flow_exhaustion_still_refuses_emission(self):
        original = translator.indirect_jump.find

        def limited(blocks, databases, table, **kwargs):
            self.assertEqual(kwargs['max_visits'], 262144)
            return original(blocks, databases, table,
                            terminal_targets=kwargs['terminal_targets'], max_visits=1)

        with patch.object(translator.indirect_jump, 'find', limited):
            assembly, log, status = render(
                self.body(), lock_kind='mutex', abi=2,
                trusted_source=True, native_escape_capable=True,
                kernel_symbols={'kd_mutex_direct_lock_clobber_v1': 0x7000,
                                'kd_mutex_direct_unlock_clobber_v1': 0x7100,
                                'kd_rwsem_up_write_clobber_v1': 0x6100},
                returning_services={0x5500: dict(cookie=1, nargs=6, result_kind=1,
                    context_kind=1, symbol='primitive_call')},
                return_status=True)
        self.assertEqual((assembly, status), (b'', 2))
        self.assertIn('return dispatch exceeds its work budget', log)

    def test_return_flow_budget_boundary_keeps_original_history_on_refusal(self):
        # One actual decoded RET spends exactly one unit. Larger retained
        # headroom changes the ceiling, not proof completion or publication.
        blocks, databases = translator.decode_regions(
            [(b'\xc3', 0x1000, [0x1000])], 0, set())
        table = {0x4444: [0x5555]}
        with self.assertRaises(translator.indirect_jump.ReturnFlowError):
            translator.indirect_jump.find(blocks, databases, table, max_visits=0)
        self.assertEqual(table, {0x4444: [0x5555]})
        self.assertEqual(translator.indirect_jump.find(
            blocks, databases, table, max_visits=1), [])
        self.assertEqual(table, {0x4444: [0x5555], 0x1001: []})

    def test_native_context_values_and_indirect_successor(self):
        parse = translator.memread.device_session.parse_service_calls
        for context in range(1, 11):
            row = f'1 ffffffff81001000 1 1 {context} primitive_call\n'
            self.assertEqual(parse(row)[0xffffffff81001000]['context_kind'], context)
        for call in ('ffd0', '2effd0', '2e2effd0', '2e2e2effd0',
                     '2e41ffd0', '2e2e41ffd0', '2e2e2e41ffd0'):
            with self.subTest(call=call):
                raw = bytes.fromhex(call)
                successor = 0x1000 + len(raw)
                raw += bytes.fromhex('480534120000')
                raw += b'\xe8' + struct.pack('<i', 0x6100 - (0x1000 + len(raw)) - 5) + b'\xc3'
                options = {}
                assembly, log, status = render(
                    raw.hex(), lock_kind='mutex', abi=2,
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
                self.assertIn(f'kd_service_dispatch_{successor:x}:'.encode(), assembly)
                self.assertIn(f'loc_{successor:x}:'.encode(), assembly)
                self.assertIn(b'PUSHFQ\nPOP QWORD PTR[REG_BANK + KD_REG_FLAGS]', assembly)

    def test_registry_refuses_partial_duplicate_and_unknown_contracts(self):
        parse = translator.memread.device_session.parse_service_calls
        row = '1 ffffffff81001000 6 1 1 primitive_call\n'
        self.assertEqual(len(parse(row)), 1)
        for text in (row + row, row.replace('6 1 1', '7 1 1'),
                     row.replace('6 1 1', '6 3 1'), row.replace('6 1 1', '6 1 15'),
                     row.replace('1 ffffffff', '0 ffffffff'), '1 ffffffff81001000',
                     'x' * 4097):
            with self.subTest(text=text[:100]), self.assertRaises(ValueError):
                parse(text)

    def test_argument_dependent_context_requires_captured_first_argument(self):
        parse = translator.memread.device_session.parse_service_calls
        for nargs in range(1, 7):
            for result in (1, 2):
                row = f'1 ffffffff81001000 {nargs} {result} 14 scalar_api\n'
                parsed = parse(row)[0xffffffff81001000]
                self.assertEqual((parsed['nargs'], parsed['result_kind'], parsed['context_kind']),
                                 (nargs, result, 14))
        row = '1 ffffffff81001000 2 2 14 kvfree_call_rcu\n'
        self.assertEqual(parse(row)[0xffffffff81001000]['symbol'], 'kvfree_call_rcu')
        for text in (row.replace('2 2 14', '0 2 14'), row.replace('2 2 14', '7 2 14'),
                     row.replace('2 2 14', '2 3 14'), row.replace('2 2 14', '2 2 15')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse(text)
        options = {}
        assembly, log, status = render(
            self.body(), lock_kind='mutex', abi=2, trusted_source=True,
            native_escape_capable=True,
            kernel_symbols={'kd_mutex_direct_lock_clobber_v1': 0x7000,
                            'kd_mutex_direct_unlock_clobber_v1': 0x7100,
                            'kd_rwsem_up_write_clobber_v1': 0x6100},
            returning_services=parse('1 5500 2 2 14 kvfree_call_rcu\n'),
            build_options=options, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertEqual(options['requirements'], 896)
        self.assertIn(b'kd_service_dispatch_1005:', assembly)
        self.assertIn(b'loc_1005:', assembly)

    def test_native_writer_pair_requires_one_argument_and_void_result(self):
        parse = translator.memread.device_session.parse_service_calls
        for context in (12, 13):
            row = f'1 ffffffff81001000 1 2 {context} native_writer\n'
            self.assertEqual(parse(row)[0xffffffff81001000]['context_kind'], context)
            for text in (row.replace('1 2 ' + str(context), '0 2 ' + str(context)),
                         row.replace('1 2 ' + str(context), '2 2 ' + str(context)),
                         row.replace('1 2 ' + str(context), '1 1 ' + str(context))):
                with self.subTest(text=text), self.assertRaises(ValueError):
                    parse(text)

    def test_nonreturning_registry_is_exact_zero_arg_void_target(self):
        parse = translator.memread.device_session.parse_service_calls
        row = '1 ffffffff81001000 0 2 11 __stack_chk_fail\n'
        self.assertEqual(parse(row)[0xffffffff81001000]['context_kind'], 11)
        for text in (row.replace('0 2 11', '1 2 11'), row.replace('0 2 11', '0 1 11'),
                     row.replace('__stack_chk_fail', 'panic')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse(text)

    def test_conditional_nonreturning_call_keeps_other_path_without_cold_closure(self):
        # Source failure branch remains explicit. Its impossible CALL return
        # contains another ordinary CALL which must never enter the image.
        raw = bytearray.fromhex('85c0751c480534120000e8f1500000c3')
        raw.extend(b'\x90' * (0x20 - len(raw)))
        raw.extend(b'\xe8' + struct.pack('<i', 0x5500 - 0x1025))
        raw.extend(b'\xe8' + struct.pack('<i', 0x5700 - 0x102a) + b'\xc3')
        options = {}
        assembly, log, status = render(
            raw.hex(), lock_kind='mutex', abi=2, trusted_source=True,
            native_escape_capable=True,
            kernel_symbols={'kd_mutex_direct_lock_clobber_v1': 0x7000,
                            'kd_mutex_direct_unlock_clobber_v1': 0x7100,
                            'kd_rwsem_up_write_clobber_v1': 0x6100},
            returning_services={0x5500: dict(cookie=1, nargs=0, result_kind=2,
                                             context_kind=11, symbol='__stack_chk_fail')},
            build_options=options, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertEqual(options['requirements'], 896)
        self.assertIn(b'loc_1020:', assembly)
        self.assertIn(b'loc_5500:', assembly)
        self.assertIn(b'0x1234', assembly)
        self.assertNotIn(b'loc_1025:', assembly)
        self.assertNotIn(b'loc_5700:', assembly)
        self.assertNotIn(b'kd_service_dispatch_1025:', assembly)

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

    def indirect_tail_image(self, tail, *, capable=True, history=None, local=False):
        # The source CALL is real: the thunk inherits its word, rather than
        # manufacturing a JMP-specific continuation. Arithmetic precedes CALL
        # so target staging and the tail miss must preserve its flags too.
        raw = bytearray.fromhex('b27f80c201')  # MOV DL,127; ADD DL,1.
        raw += b'\xe8' + struct.pack('<i', 0x1020 - (0x1000 + len(raw)) - 5)
        raw += bytes.fromhex('0f90c10f98c20f94c3')  # SETO CL; SETS DL; SETZ BL.
        raw += b'\xe8' + struct.pack('<i', 0x6100 - (0x1000 + len(raw)) - 5) + b'\xc3'
        raw += b'\x90' * (0x20 - len(raw))
        raw += bytes.fromhex(tail)
        if local:
            raw += b'\x90' * (0x40 - len(raw))
            raw += bytes.fromhex('b82a000000c3')
        # Supply the decoded text roots that the real source reader returns
        # for ordinary callees and learned targets. Keep a full instruction
        # lookahead at the last root so closure never invents a device read
        # outside this synthetic text window.
        raw += b'\x90' * 15
        roots = [0x1000, 0x1020] + ([0x1040] if local else [])
        options = {}
        assembly, log, status = render(
            raw.hex(), lock_kind='mutex', abi=2, trusted_source=True,
            regions=[(bytes(raw), 0x1000, roots)],
            native_escape_capable=True, indirect_tail_capable=capable,
            indirect_history=history,
            kernel_symbols={'kd_mutex_direct_lock_clobber_v1': 0x7000,
                            'kd_mutex_direct_unlock_clobber_v1': 0x7100,
                            'kd_rwsem_up_write_clobber_v1': 0x6100},
            returning_services={0x5500: dict(cookie=1, nargs=1, result_kind=1,
                                             context_kind=2, symbol='primitive_call')},
            body_witness=True, build_options=options, return_status=True)
        self.assertEqual(status, 0, log)
        return assembly, options

    def test_indirect_tail_exports_full_packet_without_another_call_push(self):
        for tail in ('ffe0', '41ffe0', '2e2e2effe0', '2e2e2e41ffe0',
                     'ff20', '41ff20'):
            with self.subTest(tail=tail):
                assembly, options = self.indirect_tail_image(tail)
                self.assertEqual(options['requirements'], 4992)
                self.assertIn(b'kd_service_dispatch_100a:', assembly)
                before = []
                pointer = ctypes.c_ulong(0x5500)

                def initialize(regs, stack):
                    regs[12] = regs[11] = (ctypes.addressof(pointer)
                        if tail in ('ff20', '41ff20') else 0x5500)
                    before.append((regs[1], stack))

                regs, args = run_image(assembly, [0x1000], initialize=initialize,
                                       abi=2, requirements=options['requirements'])[0]
                source_sp, stack = before[0]
                self.assertEqual(args, [14, 1])
                self.assertEqual((regs[0], regs[17]), (0x5500, 0x1020))
                self.assertEqual(regs[1], source_sp - 8)
                self.assertEqual((stack[7], stack[8]), (0x100a, 0x4444))
                self.assertEqual(regs[19] & 0x8d5, 0x890)

    def test_indirect_tail_service_returns_once_to_same_image_caller(self):
        assembly, options = self.indirect_tail_image('ffe0')
        before, exits = [], []
        answer = 0xfedcba9876543210

        def initialize(regs, stack):
            regs[12] = 0x5500
            before.append(regs[1])

        def service(regs, args, stack):
            exits.append(list(args))
            if len(exits) != 1:
                return False
            self.assertEqual(list(args), [14, 1])
            self.assertEqual((regs[0], regs[17], regs[1]),
                             (0x5500, 0x1020, before[0] - 8))
            self.assertEqual((stack[7], stack[8]), (0x100a, 0x4444))
            # Substitute only the declared Native primitive's return: runtime
            # consumes its retained CALL word once and rejoins the same bytes.
            regs[0], regs[1], regs[12] = stack[7], regs[1] + 8, answer
            regs[19] = 0x202 | 0x880
            regs[17] = 0x4b44535643524545
            return True

        regs, args = run_image(assembly, [0x1000], initialize=initialize, resume=service,
                               abi=2, requirements=options['requirements'])[0]
        self.assertEqual(exits, [[14, 1], [1, 1]])
        self.assertEqual((regs[0], regs[1]), (0x6100, before[0] - 8))
        self.assertEqual(regs[12], answer)
        self.assertEqual((regs[13] & 255, regs[14] & 255, regs[8] & 255), (1, 1, 0))

    def test_old_provider_jump_and_return_do_not_get_tail_provenance(self):
        for raw in ('ffe0', 'c3', '85c07500ffe0'):
            with self.subTest(raw=raw):
                assembly, options = self.indirect_tail_image(raw, capable=False)
                self.assertFalse(options['requirements'] & 4096)
                self.assertNotIn(b'Stack_IJ, 14', assembly)

    def test_returns_and_conditional_branches_never_get_tail_provenance(self):
        for raw in ('c3', '85c07500c3'):
            with self.subTest(raw=raw):
                assembly, options = self.indirect_tail_image(raw)
                self.assertFalse(options['requirements'] & 4096)
                self.assertNotIn(b'Stack_IJ, 14', assembly)

    def test_known_local_tail_keeps_normal_dispatch_and_real_return(self):
        assembly, options = self.indirect_tail_image(
            'ffe0', history={0x1022: [0x1040], 0x1046: [0x100a]}, local=True)
        self.assertIn(b'loc_1040:', assembly)
        before = []

        def initialize(regs, stack):
            regs[12] = 0x1040
            before.append((regs[1], stack))

        regs, args = run_image(assembly, [0x1000], initialize=initialize,
                               abi=2, requirements=options['requirements'])[0]
        self.assertEqual(args, [1, 1])
        self.assertEqual((regs[0], regs[1]), (0x6100, before[0][0] - 8))
        self.assertEqual(regs[12], 42)
        self.assertEqual((regs[13] & 255, regs[14] & 255, regs[8] & 255), (1, 1, 0))

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
