"""VM-only exact site-decoder fixtures; synthetic ELF listings, no live module."""
import ast
import os
from pathlib import Path
import re
import types
import unittest

ROOT = Path(__file__).resolve().parents[3]


class SiteFailure(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise SiteFailure(message)


def listing(name, start, targets):
    """One real E8 encoding and following instruction boundary per target."""
    rows = [f'{start:x} <{name}>:']
    for index, (target, address) in enumerate(targets):
        pc = start + index * 6
        code = b'\xe8' + (address - pc - 5).to_bytes(4, 'little', signed=True)
        rows += [f' {pc:x}: {code.hex(" ")} call {address:x} <{target}>',
                 f' {pc+5:x}: 90 nop']
    return '\n'.join(rows) + '\n'


class WriterReturnSites(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.geteuid() != 0 or os.uname().release not in (
                '7.0.0-38-kdlock1', '7.0.0-38-kdscope1', '7.0.0-38-kdscope3'):
            raise RuntimeError('writer site fixtures must run in the Linux 7 development VM')
        source = ROOT / 'bench/mmap_writer/sites.py'
        names = {'function_rows', 'call_returns', 'linked_edge', 'waiter_argument',
                 'wait_arguments', 'gate_chain'}
        nodes = [node for node in ast.parse(source.read_text()).body
                 if isinstance(node, ast.FunctionDef) and node.name in names]
        if {node.name for node in nodes} != names:
            raise RuntimeError('actual site-decoder extraction changed')
        cls.code = dict(re=re, ACQUIRE='down_write_killable', rt=types.SimpleNamespace(require=require))
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), cls.code)

    def assembly(self, count):
        writer, gate, slow = ('kd_mmap_down_write_killable',
                             'kd_mmap_mutex_local_lock_signal', 'kd_mmap_local_lock_slow_signal')
        return {writer: listing(writer, 0x1000, [(gate, 0x2000)] * 2),
                gate: listing(gate, 0x2000, [(slow, 0x3000)]),
                slow: listing(slow, 0x3000, [('schedule', 0x5000)] * count)}

    def chain(self, assembly):
        return self.code['gate_chain'](assembly, 'kd_mmap_down_write_killable', 43)

    def test_three_calls_keep_every_decoded_pc_and_both_intermediate_frames(self):
        chain = self.chain(self.assembly(3))
        self.assertEqual(chain['wait_returns'], [5, 11, 17])
        self.assertEqual([row['return_offset'] for row in chain['instructions']], [5, 11, 17])
        self.assertEqual(chain['intermediate'], [
            dict(symbol='kd_mmap_mutex_local_lock_signal', return_offsets=[5]),
            dict(symbol='kd_mmap_down_write_killable', return_offsets=[5, 11])])
        self.assertEqual(self.code['wait_arguments'](chain), ['--wait-returns', '5:11:17'])

    def test_one_and_two_site_argument_forms_stay_unchanged(self):
        for count, returns in ((1, [5, 5]), (2, [5, 11])):
            chain = self.chain(self.assembly(count))
            self.assertEqual(chain['wait_returns'], returns)
            self.assertEqual(len(chain['instructions']), count)
            self.assertEqual(self.code['wait_arguments'](chain), list(map(str, returns)))

    def test_fourth_site_is_refused_without_truncation(self):
        with self.assertRaisesRegex(SiteFailure, 'too many gate'):
            self.chain(self.assembly(4))
        with self.assertRaises(SiteFailure):
            self.code['wait_arguments'](dict(wait_returns=[5, 11, 17, 23]))

    def test_third_call_bytes_and_next_boundary_are_checked(self):
        for old, new in (('e8 ef 1f 00 00', 'e8 ee 1f 00 00'),
                         ('3011: 90 nop', '3012: 90 nop')):
            assembly = self.assembly(3)
            slow = 'kd_mmap_local_lock_slow_signal'
            self.assertIn(old, assembly[slow])
            assembly[slow] = assembly[slow].replace(old, new)
            with self.assertRaisesRegex(SiteFailure, 'bytes/target/return boundary'):
                self.chain(assembly)

    def test_argument_values_are_positive_bounded_and_three_distinct(self):
        for values in ([5, 11, 0], [5, 11, 1 << 64], [5, 11, True], [5, 11, 5]):
            with self.subTest(values=values), self.assertRaises(SiteFailure):
                self.code['wait_arguments'](dict(wait_returns=values))


if __name__ == '__main__':
    unittest.main()
