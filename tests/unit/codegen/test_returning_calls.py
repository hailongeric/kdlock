"""Focused returning-CALL registry and emitted continuation checks."""
import ctypes
import hashlib
import inspect
import json
import os
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

from test_jit_diagnostics import render, translator
from test_jit_body_witness import run_image
from test_ordinary_callee_bytes import source_bytes


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

    def test_paged_registry_is_complete_and_exact(self):
        read = translator.memread.device_session.read_service_call_table
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            rows = [f'{i:x} {0xffffffff81000000+i:x} 1 1 2 api_{i}\n' for i in range(1, 129)]
            state = directory / 'service_call_table_state'
            state.write_text('128 128 128\n')
            for page in range(8):
                (directory / f'service_call_page_{page}').write_text(''.join(rows[page*16:(page+1)*16]))
            self.assertEqual(read(directory), ''.join(rows))
            (directory / 'service_call_page_7').unlink()
            with self.assertRaises(FileNotFoundError): read(directory)
            (directory / 'service_call_page_7').write_text(''.join(rows[112:]))
            (directory / 'service_call_page_0').write_text(''.join(rows[1:16]))
            with self.assertRaises(ValueError): read(directory)
            (directory / 'service_call_page_0').write_text(''.join(rows[:16]))
            (directory / 'service_call_page_1').write_text(rows[0]+''.join(rows[17:32]))
            with self.assertRaises(ValueError): read(directory)
            (directory / 'service_call_page_1').write_text(''.join(rows[16:32]))
            original = Path.read_text
            calls = []
            def changing(path, *args, **kwargs):
                if path == state:
                    calls.append(1)
                    if len(calls) == 2: return '129 128 128\n'
                return original(path, *args, **kwargs)
            with patch.object(Path, 'read_text', changing):
                with self.assertRaises(ValueError): read(directory)
            state.write_text('1 1 1\n')
            for page in range(8): (directory / f'service_call_page_{page}').write_text(rows[0] if page==0 else '')
            self.assertEqual(read(directory), rows[0])
            state.unlink()
            (directory / 'service_call_table').write_text(rows[0])
            self.assertEqual(read(directory), rows[0])

    def test_declared_call_keeps_body_and_exact_flags_successor(self):
        assembly, options = self.emit()
        self.assertEqual(options['requirements'], 896 | (1 << 13))
        self.assertIn(b'KD_REG_SERVICE_REENTRY_TAG', assembly)
        self.assertIn(b'kd_service_dispatch_1005:', assembly)
        self.assertIn(b'loc_1005:', assembly)
        self.assertIn(b'0x1234', assembly)
        self.assertIn(b'loc_5500:', assembly)

    def test_unused_descriptor_keeps_ordinary_image_contract(self):
        assembly, options = self.emit(False)
        self.assertEqual(options['requirements'], 128 | (1 << 13))
        self.assertNotIn(b'KD_REG_SERVICE_REENTRY_TAG', assembly)

    def test_ordinary_callee_is_learned_instead_of_eagerly_expanded(self):
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
        self.assertEqual(policies, [memread.DEFAULT_WINDOW_POLICY])
        self.assertEqual(reads, [])
        extend.assert_not_called()
        self.assertIn(f'loc_{callee:x}:'.encode(), assembly)
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
        self.assertTrue(all(call.kwargs['max_visits'] == 65536
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
            self.assertEqual(kwargs['max_visits'], 65536)
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

    def test_return_flow_follows_only_decoded_learned_tail_jumps(self):
        # CALL thunk; learned tail -> callback; CALL inner; shared RET. The
        # callback's inner RET has its own CALL word, while the shared RET
        # inherits the original caller's word through the learned tail.
        for name, thunk, source, targets, terminals, expected in (
                ('tail', 'ffe2', 0x1022, [0x1040, 0x1040], (), [0x1005]),
                ('cycle', 'ffe2', 0x1022, [0x1020, 0x1040], (), [0x1005]),
                ('unlearned', 'ffe2', 0x1022, [], (), []),
                ('undecoded', 'ffe2', 0x1022, [0x9000], (), []),
                ('terminal', 'ffe2', 0x1022, [0x1040], (0x1040,), []),
                ('call', 'ffd2c3', 0x1022, [0x1040], (), []),
                ('return', 'c3', 0x1021, [0x1040], (), [])):
            with self.subTest(transfer=name):
                blocks, databases = translator.decode_regions([
                    (bytes.fromhex('e81b000000c3'), 0x1000, [0x1000]),
                    (bytes.fromhex(thunk), 0x1020, [0x1020]),
                    (bytes.fromhex('e81b000000e936000000'), 0x1040, [0x1040]),
                    (b'\xc3', 0x1060, [0x1060]),
                    (b'\xc3', 0x1080, [0x1080]),
                ], 0, set())
                history = {source: targets}
                self.assertEqual(translator.indirect_jump.find(
                    blocks, databases, history, terminal_targets=terminals), [])
                self.assertEqual(history[0x1081], expected)
                self.assertEqual(history[0x1061], [0x1045])
                if name == 'tail':
                    # The added edges use the existing work budget. Refusal
                    # must leave the original history wholly unchanged.
                    limited = {source: list(targets)}
                    with self.assertRaises(translator.indirect_jump.ReturnFlowError):
                        translator.indirect_jump.find(
                            blocks, databases, limited, max_visits=10)
                    self.assertEqual(limited, {source: targets})

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
                self.assertEqual(options['requirements'], 896 | (1 << 13))
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
        self.assertEqual(options['requirements'], 896 | (1 << 13))
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
            raw.hex(), regions=[(bytes(raw), 0x1000, [0x1000, 0x1020])], lock_kind='mutex', abi=2, trusted_source=True,
            native_escape_capable=True,
            kernel_symbols={'kd_mutex_direct_lock_clobber_v1': 0x7000,
                            'kd_mutex_direct_unlock_clobber_v1': 0x7100,
                            'kd_rwsem_up_write_clobber_v1': 0x6100},
            returning_services={0x5500: dict(cookie=1, nargs=0, result_kind=2,
                                             context_kind=11, symbol='__stack_chk_fail')},
            build_options=options, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertEqual(options['requirements'], 896 | (1 << 13))
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
            raw.hex(), regions=[(bytes(raw), 0x1000, [0x1000, 0x1020])],
            lock_kind='mutex', abi=2, trusted_source=True,
            native_escape_capable=True,
            kernel_symbols={'kd_mutex_direct_lock_clobber_v1': 0x7000,
                            'kd_mutex_direct_unlock_clobber_v1': 0x7100,
                            'kd_rwsem_up_write_clobber_v1': 0x6100},
            returning_services={0x5500: dict(cookie=1, nargs=1, result_kind=1,
                                             context_kind=2, symbol='primitive_call')},
            build_options=options, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertEqual(options['requirements'], 896 | (1 << 13))
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
                self.assertEqual(options['requirements'], 4992 | (1 << 13))
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
        # Supply only the observed tail. Return propagation must derive the
        # actual CALL continuation without a separately learned RET record.
        assembly, options = self.indirect_tail_image(
            'ffe0', history={0x1022: [0x1040]}, local=True)
        self.assertIn(b'loc_1040:', assembly)
        self.assertIn(b'kd_ij_1046_100a:', assembly)
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

    def test_learned_tail_nested_call_returns_through_shared_ret(self):
        # Join the saved g9 motif using independent synthetic source bytes.
        # The only learned input is the JMP edge; neither RET is seeded.
        regions, names = source_bytes("""
            mov r8, QWORD PTR [rdi]
            lea r8, [r8+1]
            mov QWORD PTR [rdi], r8
            mov bl, 127
            add bl, 1
        outer_call:
            call tail_thunk
        outer_continuation:
            mov QWORD PTR [rdi+72], rsp
            mov r8, QWORD PTR [rdi+32]
            lea r8, [r8+1]
            mov QWORD PTR [rdi+32], r8
            seto cl
            sets dl
            setz bl
        root_ret:
            ret
            .balign 4096
        tail_thunk:
            jmp rdx
            .balign 4096
        callback:
            mov r8, QWORD PTR [rdi+8]
            lea r8, [r8+1]
            mov QWORD PTR [rdi+8], r8
        inner_call:
            call inner
        inner_continuation:
            mov QWORD PTR [rdi+64], rsp
            mov r8, QWORD PTR [rdi+24]
            lea r8, [r8+1]
            mov QWORD PTR [rdi+24], r8
            jmp shared_ret
            .balign 4096
        inner:
            mov QWORD PTR [rdi+40], rsp
            mov r9, QWORD PTR [rsp]
            mov QWORD PTR [rdi+48], r9
            mov r9, QWORD PTR [rsp+8]
            mov QWORD PTR [rdi+56], r9
            mov r8, QWORD PTR [rdi+16]
            lea r8, [r8+1]
            mov QWORD PTR [rdi+16], r8
        inner_ret:
            ret
            .balign 4096
        shared_ret:
            ret
        """)
        raw, base, _ = regions[0]
        regions = [(raw, base, [names[name] for name in
            ('source_entry', 'tail_thunk', 'callback', 'inner', 'shared_ret')])]
        self.assertEqual(names['outer_continuation'], names['outer_call'] + 5)
        self.assertEqual(names['inner_continuation'], names['inner_call'] + 5)
        tail_source = names['tail_thunk'] + 2
        inner_source, shared_source = names['inner_ret'] + 1, names['shared_ret'] + 1

        # This mutation retains actual dispatch/emission and decoded bodies.
        # It removes only the corrected walk, reproducing its former omission.
        module = translator.indirect_jump
        original_find, original_decode = module.find, translator.decode_regions
        walk = ('            for target in sorted(learned_tails[start]):\n'
                '                spend(1, start)\n'
                '                targets.add(target)\n')
        source = inspect.getsource(original_find)
        self.assertEqual(source.count(walk), 1)
        scope = dict(vars(module))
        exec(compile(source.replace(walk, ''), '<tail-walk-control>', 'exec'), scope)
        snapshots = []

        def generate(finder):
            decoded = []

            def capture_decode(*args, **kwargs):
                blocks, databases = original_decode(*args, **kwargs)
                decoded.append(tuple((start, tuple((line.offset, bytes(line.b))
                    for line in block.lines)) for start, block in sorted(blocks.items())))
                return blocks, databases

            def unexpected_read(address, size):
                self.fail(f'joined motif requested extra text at {address:#x}, size {size}')

            options = {}
            with patch.object(module, 'find', finder), \
                    patch.object(translator, 'decode_regions', side_effect=capture_decode):
                assembly, log, status = render('', regions=regions,
                    indirect_history={tail_source: [names['callback']]},
                    memory_reader=unexpected_read, lock_kind='mutex', abi=2,
                    trusted_source=True, body_witness=True,
                    native_escape_capable=True, indirect_tail_capable=True,
                    kernel_symbols={'kd_mutex_direct_lock_clobber_v1': 0x7000,
                                    'kd_mutex_direct_unlock_clobber_v1': 0x7100},
                    build_options=options, return_status=True)
            self.assertEqual(status, 0, log)
            self.assertTrue(decoded)
            snapshots.append(decoded)
            self.assertTrue(options['requirements'] & (1 << 13))
            return assembly, options

        control, control_options = generate(scope['find'])
        corrected, corrected_options = generate(original_find)
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertEqual(control_options, corrected_options)
        inner_match = f'kd_ij_{inner_source:x}_{names["inner_continuation"]:x}:'.encode()
        outer_match = f'kd_ij_{shared_source:x}_{names["outer_continuation"]:x}:'.encode()
        for assembly in (control, corrected):
            self.assertIn(inner_match, assembly)
        self.assertNotIn(outer_match, control)
        self.assertIn(outer_match, corrected)

        # An isolated check may retain the exact synthetic inputs and wrapper
        # outputs. Never replace an existing artifact directory or image.
        directory = os.environ.get('KD_RETURN_FIXTURE_DIR')
        directory = Path(directory).resolve() if directory else None
        if directory is not None:
            directory.mkdir(mode=0o700)
        artifacts, outcomes = {}, {}

        def retain(name, data):
            artifacts[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            if directory is not None:
                with (directory / name).open('xb') as stream:
                    stream.write(data)

        retain('source.bin', raw)
        retain('source.json', (json.dumps({'base': base, 'symbols': names,
            'roots': regions[0][2], 'indirect_history': {tail_source: [names['callback']]},
            'decode_passes': len(snapshots[0]),
            'decoded_instructions': sum(len(lines) for _, lines in snapshots[0][-1])},
            sort_keys=True, indent=2) + '\n').encode())
        retain('control.S', control)
        retain('corrected.S', corrected)
        real_build = translator.build_jit_binary
        for label, assembly, options, returns in (
                ('control', control, control_options, False),
                ('corrected', corrected, corrected_options, True)):
            with self.subTest(corrected=returns):
                effects = (ctypes.c_ulong * 10)()
                before = []

                def initialize(regs, stack):
                    regs[12] = 0x123456789abcdef0
                    regs[14] = names['callback']  # Source RDX selects JMP RDX.
                    regs[16] = ctypes.addressof(effects)
                    before.append((regs[1], stack))

                def capture_build(*args, **kwargs):
                    result = real_build(*args, **kwargs)
                    retain(label + '.bin', Path('asm/jit.bin').read_bytes())
                    return result

                with patch.object(translator, 'build_jit_binary', side_effect=capture_build):
                    regs, args = run_image(assembly, [base], initialize=initialize,
                        abi=2, requirements=options['requirements'])[0]
                original_sp, stack = before[0]
                self.assertEqual(args, [15, 1])
                self.assertEqual(list(effects)[:5], [1, 1, 1, 1, int(returns)])
                self.assertEqual(list(effects)[5:9], [original_sp - 16,
                    names['inner_continuation'], names['outer_continuation'], original_sp - 8])
                self.assertEqual((stack[5], stack[6], stack[7], stack[8]),
                    (0, names['inner_continuation'], names['outer_continuation'], 0x4444))
                self.assertEqual(regs[12], 0x123456789abcdef0)
                self.assertEqual(regs[19] & 0x8d5, 0x890)
                if returns:
                    self.assertEqual(effects[9], original_sp)
                    self.assertEqual((regs[0], regs[1], regs[17]),
                        (0x4444, original_sp + 8, names['root_ret'] + 1))
                    self.assertEqual((regs[13] & 255, regs[14] & 255, regs[8] & 255),
                                     (1, 1, 0))
                else:
                    self.assertEqual(effects[9], 0)
                    self.assertEqual((regs[0], regs[1], regs[17]),
                        (names['outer_continuation'], original_sp, shared_source))
                outcomes[label] = {'exit': args, 'target': regs[0],
                    'source_next_pc': regs[17], 'sp_delta': regs[1] - original_sp,
                    'arithmetic_flags': regs[19] & 0x8d5,
                    'effects': list(effects)[:5],
                    'inner_sp_delta': effects[5] - original_sp,
                    'inner_word': effects[6], 'outer_word': effects[7],
                    'after_inner_sp_delta': effects[8] - original_sp,
                    'outer_continuation_sp_delta': effects[9] - original_sp if returns else None}
        self.assertIs(module.find, original_find)
        receipt = {'synthetic_source': True, 'artifacts': artifacts, 'outcomes': outcomes,
                   'decoded_source_equal': snapshots[0] == snapshots[1],
                   'requirements_equal': control_options == corrected_options}
        if directory is not None:
            (directory / 'result.json').write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n')
        print('JOINED_TAIL_RESULT ' + json.dumps(receipt, sort_keys=True))

    def test_conditional_native_tail_keeps_both_source_paths(self):
        raw = bytearray.fromhex('e81b000000480534120000e8f0500000c3')
        raw.extend(b'\x90' * (0x20 - len(raw)))
        raw.extend(b'\x85\xc0\x0f\x85' + struct.pack('<i', 0x5500 - 0x1028))
        raw.extend(b'\xc3' + b'\x90' * 16)
        options = {}
        assembly, log, status = render(
            raw.hex(), lock_kind='mutex', abi=2, trusted_source=True,
            regions=[(bytes(raw), 0x1000, [0x1000, 0x1020])],
            native_escape_capable=True,
            kernel_symbols={'kd_mutex_direct_lock_clobber_v1': 0x7000,
                            'kd_mutex_direct_unlock_clobber_v1': 0x7100,
                            'kd_rwsem_up_write_clobber_v1': 0x6100},
            returning_services={0x5500: dict(cookie=1, nargs=1, result_kind=1,
                                             context_kind=2, symbol='primitive_call')},
            build_options=options, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertEqual(options['requirements'], 896 | (1 << 13))
        self.assertIn(b'kd_service_dispatch_1005:', assembly)
        self.assertIn(b'loc_5500:', assembly)
        self.assertIn(b'loc_1028:', assembly)


if __name__ == '__main__':
    unittest.main()
