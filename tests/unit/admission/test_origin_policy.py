"""Decode real instructions and check the bounded build-audit policy."""
import unittest
import sys
from source_text import ROOT
sys.path.insert(0, str(ROOT / "disassem"))
from types import SimpleNamespace
from miasm.analysis.machine import Machine
from miasm.core.bin_stream import bin_stream_str
from miasm.core.locationdb import LocationDB
import normal
import origin_policy as policy


class OriginPolicy(unittest.TestCase):
    def check(self, raw, entries=None):
        db = LocationDB()
        stream = bin_stream_str(raw, base_address=0x1000)
        lines = []
        offset = 0x1000
        while offset < 0x1000 + len(raw):
            line = Machine('x86_64').mn.dis(stream, 64, offset)
            if line.dstflow():
                line.dstflow2label(db)
            lines.append(line)
            offset += line.l
        block = type('Block', (), {})()
        block.lines = lines
        return policy.requirements({0x1000: block}, {block: db}, 0x1000,
                                   {0x2000}, entries or [policy.Entry('cpu_number',0x199e0,4,frozenset({'read'}))])

    @staticmethod
    def unlock(body):
        return body + b'\xe8' + (0x2000-0x1000-len(body)-5).to_bytes(4,'little',signed=True)

    def test_cpu_read(self):
        self.assertEqual(self.check(self.unlock(bytes.fromhex('658b0425e0990100'))),1)

    def test_rip_relative_cpu_read(self):
        read = bytes.fromhex('658b15') + (0x199e0 - 0x1007).to_bytes(4, 'little')
        self.assertEqual(self.check(self.unlock(read)), 1)

    def test_unknown_width_write_and_dynamic(self):
        for raw in ('658b0425e4990100', '65488b0425e0990100',
                    '65890425e0990100','658b00'):
            with self.assertRaises(ValueError):
                self.check(self.unlock(bytes.fromhex(raw)))

    def test_shared_counter_has_no_audit(self):
        with self.assertRaises(ValueError):
            self.check(self.unlock(bytes.fromhex('6548ff042500030000')))

    def test_audited_counter(self):
        self.assertEqual(self.check(self.unlock(bytes.fromhex('6548ff042500030000')),
            [policy.Entry('kd_origin_test_counter',0x300,8,frozenset({'rmw'}))]),1)

    def test_blocking_call_cycle_and_limit(self):
        read = bytes.fromhex('658b0425e0990100')
        for suffix in (b'\xe8\0\0\0\0', b'\xeb\xfe', b'\xff\xd0', b'\xf4', b'\x90'*256):
            with self.assertRaises(ValueError):
                self.check(self.unlock(read + suffix))

    def test_logical_current_unchanged(self):
        normal.set_current_task_offset(0x20b80)
        self.assertEqual(self.check(self.unlock(bytes.fromhex('65488b0425800b0200'))),0)
        normal.set_current_task_offset(None)


if __name__ == '__main__':
    unittest.main()
