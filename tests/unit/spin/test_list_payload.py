"""Guest-only production list payload, structural corruption and hint checks."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


class ListPayloadTests(unittest.TestCase):
    def test_sizes_and_prefetch_variants_keep_exact_data_and_bounded_oracle(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder/'linux').mkdir()
            # The kernel's architecture prefetch wrapper is substituted by
            # the same read/locality hint; inspect emitted code independently.
            (folder/'linux/prefetch.h').write_text(
                '#define prefetch(address) __builtin_prefetch((address), 0, 3)\n')
            for nodes in (16, 128):
                for prefetch in (0, 1):
                    with self.subTest(nodes=nodes, prefetch=prefetch):
                        binary = folder/f'list-{nodes}-{prefetch}'
                        subprocess.run(['cc', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-std=gnu11', '-pthread', '-I', str(folder),
                            f'-DSC_LIST_NODES={nodes}', f'-DSC_LIST_PREFETCH={prefetch}',
                            str(Path(__file__).with_name('list_payload_fixture.c')),
                            '-o', str(binary)], check=True, capture_output=True, timeout=30)
                        subprocess.run([str(binary)], check=True, timeout=30)
                        for symbol in ('fixture_read', 'fixture_write'):
                            assembly = subprocess.check_output(
                                ['objdump', '-d', '--no-show-raw-insn',
                                 '--disassemble='+symbol, str(binary)], text=True, timeout=10)
                            self.assertEqual(bool(re.search(r'\bprefetcht0\b', assembly)),
                                             bool(prefetch), assembly)


if __name__ == '__main__':
    unittest.main()
