"""VM-only original-backend direct CALL depth and release-scope fixtures."""
import struct
import unittest

from test_jit_diagnostics import render


class DirectCallDepthTests(unittest.TestCase):
    entry = 0xffffffff81000000
    lock = entry + 0x8000
    unlock = entry + 0x8100
    downgrade = entry + 0x8200
    symbols = {'kd_mutex_direct_lock_clobber_v1': lock,
               'kd_mutex_direct_unlock_clobber_v1': unlock,
               'kd_downgrade_write': downgrade}

    @staticmethod
    def call(source, target):
        return b'\xe8' + struct.pack('<i', target - source - 5)

    def emit(self, raw, functions, depth=5):
        reads = []
        functions = {self.entry: raw, **functions}
        def read(address, size):
            reads.append((address, size))
            data = bytearray(b'\x90' * size)
            for start, body in functions.items():
                if address <= start < address + size:
                    data[start-address:start-address+len(body)] = body
            return bytes(data)
        assembly, log, status = render(raw.hex(), entry=self.entry, lock_kind='mutex', abi=2,
            trusted_source=True, native_escape_capable=True,
            regions=[(raw, self.entry, [self.entry])], memory_reader=read,
            kernel_symbols=self.symbols, direct_call_depth=depth, return_status=True)
        self.assertEqual(status, 0, log)
        return assembly, reads, log

    def test_exact_five_edges_and_zero_depth(self):
        targets = [self.entry + (n+1) * 0x10000 for n in range(6)]
        raw = self.call(self.entry, targets[0]) + self.call(self.entry+5, self.unlock) + b'\xc3'
        functions = {source: self.call(source, targets[n+1]) + b'\xc3'
                     for n, source in enumerate(targets[:-1])}
        functions[targets[-1]] = b'\xc3'
        assembly, reads, log = self.emit(raw, functions)
        for target in targets[:5]:
            self.assertTrue(f'loc_{target:x}:'.encode() in assembly, f'missing callee {target:x}')
            self.assertTrue(any(address <= target < address+size for address,size in reads))
        # An undiscovered callee still needs the ordinary first-CALL
        # continuation label. Its body must not be fetched or decoded.
        self.assertTrue(f'loc_{targets[5]:x}:'.encode() in assembly)
        self.assertFalse(any(address <= targets[5] < address+size for address,size in reads))
        self.assertIn('call_depth=5', log)
        self.assertIn('decode_pass_limit=33', log)
        self.assertIn('total_transition_limit=32', log)
        assembly, reads, _ = self.emit(raw, functions, 0)
        self.assertFalse(reads)
        self.assertTrue(f'loc_{targets[0]:x}:'.encode() in assembly)

    def test_outer_release_stops_callee_discovery(self):
        target = self.entry + 0x10000
        raw = self.call(self.entry, self.unlock) + self.call(self.entry+5, target) + b'\xc3'
        assembly, reads, _ = self.emit(raw, {target: b'\xc3'})
        self.assertFalse(reads)
        self.assertNotIn(f'loc_{target:x}:'.encode(), assembly)

    def test_inner_release_stops_source_unit_before_later_callee(self):
        target = self.entry + 0x10000
        raw = self.call(self.entry, self.lock) + self.call(self.entry+5, self.unlock)
        raw += self.call(self.entry+10, target) + self.call(self.entry+15, self.unlock) + b'\xc3'
        assembly, reads, _ = self.emit(raw, {target: b'\xc3'})
        self.assertNotIn(f'loc_{target:x}:'.encode(), assembly)
        self.assertFalse(reads)

    def test_downgrade_stops_source_unit_before_read_tail(self):
        target = self.entry + 0x10000
        raw = self.call(self.entry, self.downgrade) + self.call(self.entry+5, target) + b'\xc3'
        assembly, reads, _ = self.emit(raw, {target: b'\xc3'})
        self.assertNotIn(f'loc_{target:x}:'.encode(), assembly)
        self.assertFalse(reads)


if __name__ == '__main__':
    unittest.main()
