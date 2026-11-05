"""Original-image state queries and actual learned-root filtering.

These generated-code and source-discovery fixtures run only on the VM. Native
ownership is checked separately by the production runtime predicate fixture.
"""
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_jit_diagnostics import render, translator
from test_jit_body_witness import run_image


class RwsemQueryImageTests(unittest.TestCase):
    entry = 0x1000
    queries = {operation: 0x2000 + (operation - 14) * 0x100 for operation in range(14, 19)}
    ledger = 0x5500
    symbols = {
        'kd_mutex_direct_lock_clobber_v1': 0x7000,
        'kd_mutex_direct_unlock_clobber_v1': 0x7100,
        'kd_rwsem_up_write_clobber_v1': 0x6100,
    }

    def controls(self):
        rows = ''.join(f'{target:x} {operation} 4 rwsem_control_{operation}_4\n'
                       for operation, target in self.queries.items())
        return translator.memread.device_session.parse_rwsem_controls(rows)

    def services(self):
        rows = ''.join(f'{index} {self.queries[operation]:x} 1 1 1 rwsem_query_{operation}\n'
                       for index, operation in enumerate((17, 18), 1))
        rows += f'3 {self.ledger:x} 2 1 2 kd_service_write_owned\n'
        return translator.memread.device_session.parse_service_calls(rows)

    def emit(self, operation, *, learned=False, helper=None, services=None, exclusions=None):
        target = self.queries[operation]
        raw = b'\xb8\x07\x00\x00\x00'
        raw += b'\xe8' + struct.pack('<i', target - self.entry - len(raw) - 5)
        raw += b'\x48\x83\xc0\x01\xc3'
        regions = [(raw, self.entry, [self.entry])]
        if learned:
            regions.append((helper or bytes.fromhex('b82a000000c3'), target, [target]))
        options = {}
        assembly, log, status = render(
            raw.hex(), regions=regions, entry=self.entry, lock_kind='mutex', abi=2,
            trusted_source=True, native_escape_capable=True, kernel_symbols=self.symbols,
            returning_services=self.services() if services is None else services,
            bound_controls=self.controls(), callee_exclusions=exclusions,
            body_witness=True, build_options=options, return_status=True)
        return assembly, log, status, options

    def test_only_selected_operations_leave_runtime_controls(self):
        controls = self.controls()
        selected = translator.memread.device_session.runtime_rwsem_controls(controls, self.services())
        self.assertEqual(set(selected), {self.queries[17], self.queries[18]})
        self.assertEqual(set(controls), set(self.queries.values()))
        for operation in (1, 3, 5, 6, 11):
            row = {0x9000: dict(operation=operation, flags=0, symbol='ordinary_control')}
            self.assertEqual(translator.memread.device_session.runtime_rwsem_controls(row, {}), row)

    def test_old_native_query_declaration_fails_instead_of_overriding_JIT(self):
        for operation in (14, 15, 16):
            with self.subTest(operation=operation):
                services = self.services() | {self.queries[operation]: dict(
                    cookie=4, nargs=1, result_kind=1 if operation == 16 else 2,
                    context_kind=1, symbol=f'rwsem_query_{operation}')}
                assembly, log, status, _ = self.emit(operation, services=services)
                self.assertEqual((assembly, status), (b'', 2), log)
                self.assertIn('compiled rwsem state query is registered as a Native service', log)

    def test_cold_query_reports_actual_CALL_with_effects_and_return_word(self):
        for operation in (14, 15, 16):
            with self.subTest(operation=operation):
                exclusions = []
                assembly, log, status, options = self.emit(operation, exclusions=exclusions)
                self.assertEqual(status, 0, log)
                self.assertNotIn(self.queries[operation], exclusions[0])
                self.assertTrue(options['requirements'] & (1 << 13))
                packets = []
                def observe(regs, stack):
                    packets.append((regs[1], stack))
                regs, args = run_image(assembly, [self.entry], initialize=observe,
                                       abi=2, requirements=options['requirements'])[0]
                self.assertEqual(args, [1, 1])
                self.assertEqual((regs[0], regs[12]), (self.queries[operation], 7))
                self.assertEqual(regs[1], packets[0][0] - 8)
                self.assertEqual(packets[0][1][7], self.entry + 10)

    def test_learned_queries_execute_in_the_original_wrapper(self):
        for operation in (14, 15, 16):
            with self.subTest(operation=operation):
                assembly, log, status, options = self.emit(operation, learned=True)
                self.assertEqual(status, 0, log)
                self.assertIn(f'loc_{self.queries[operation]:x}:'.encode(), assembly)
                regs, args = run_image(assembly, [self.entry], abi=2,
                                       requirements=options['requirements'])[0]
                self.assertEqual(regs[12], 43)
                self.assertNotEqual(args[0], 1)

    def test_only_inner_ownership_query_uses_returning_native_service(self):
        target = self.queries[15]
        helper = b'\xe8' + struct.pack('<i', self.ledger - target - 5)
        helper += bytes.fromhex('4883c001c3')
        assembly, log, status, options = self.emit(15, learned=True, helper=helper)
        self.assertEqual(status, 0, log)
        self.assertTrue(options['requirements'] & (1 << 9))
        self.assertIn(f'kd_service_dispatch_{target + 5:x}:'.encode(), assembly)
        self.assertNotIn(f'kd_service_dispatch_{self.entry + 10:x}:'.encode(), assembly)

    def test_actual_history_import_keeps_compiled_query_roots(self):
        exclusions = []
        _, log, status, _ = self.emit(14, exclusions=exclusions)
        self.assertEqual(status, 0, log)
        expected = {self.entry, *(self.queries[operation] for operation in (14, 15, 16))}
        previous = os.getcwd()
        with tempfile.TemporaryDirectory(prefix='kd-query-history-') as name:
            folder = Path(name)
            (folder / 'asm').mkdir()
            (folder / 'asm/ij_table.txt').write_text(''.join(
                f'{self.entry + index:x} {target:x}\n'
                for index, target in enumerate((*self.queries.values(), self.ledger))))
            (folder / 'asm/callee_table.txt').write_text(''.join(
                f'{target:x}\n' for target in (*self.queries.values(), self.ledger)))
            try:
                os.chdir(folder)
                with patch.object(translator.memread, 'extend_regions', return_value=[]) as extend:
                    history = {}
                    translator.memread.read(self.entry, history, exclusions[0])
                    self.assertEqual(set(extend.call_args.args[1]), expected)
                    self.assertEqual({target for targets in history.values() for target in targets},
                                     {*self.queries.values(), self.ledger})
            finally:
                os.chdir(previous)


if __name__ == '__main__':
    unittest.main()
