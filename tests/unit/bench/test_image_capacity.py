"""VM-only shared C/Python image capacity and complete-boundary checks."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime
import native_image


class ImageCapacityTests(unittest.TestCase):
    def test_pool_count_default_and_bounded_build_override(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            source, binary = path / 'pool.c', path / 'pool'
            source.write_text(
                '#include <stdio.h>\n#include "kd_image_pool.h"\n'
                'int main(void) { printf("%u\\n", (unsigned int)KD_CODE_BLOCK_POOL); return 0; }\n')
            for count, expected in ((None, 64), (128, 128), (0, None), (257, None)):
                with self.subTest(count=count):
                    command = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                               '-I', str(ROOT / 'include'), str(source), '-o', str(binary)]
                    if count is not None:
                        command.append(f'-DKD_CODE_BLOCK_POOL={count}')
                    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                    if expected is None:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn('KD_CODE_BLOCK_POOL must be between 1 and 256', result.stderr)
                    else:
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(int(subprocess.check_output([str(binary)], text=True)), expected)

    def test_shared_header_compiles_to_the_python_capacity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            source, binary = path / 'capacity.c', path / 'capacity'
            source.write_text(
                '#include <stdio.h>\n#include "exe_info.h"\n'
                'int main(void) { printf("%lu\\n", KD_CODE_BLOCK_SIZE); return 0; }\n')
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-I', str(ROOT / 'include'), str(source), '-o', str(binary)],
                           check=True)
            compiled = int(subprocess.check_output([str(binary)], text=True))
        self.assertEqual(compiled, 4 * 1024 * 1024)
        self.assertEqual(bench_runtime.image_capacity(), compiled)

    def test_direct_image_accepts_exact_capacity_and_refuses_one_extra_byte(self):
        capacity, base = bench_runtime.image_capacity(), 0xffffffffc1000000
        upload = bytearray(capacity)
        upload[9:16], upload[25:32], upload[41:45] = b'KDWB002', b'KDWC002', b'KDAB'
        upload[45:48] = bytes((1, 2, 20))
        upload[64:69] = b'\xe8\0\0\0\0'
        struct.pack_into('<IIQ', upload, capacity - 32, 64, 4, 0xffffffff81001000)
        struct.pack_into('<8sII', upload, capacity - 16, b'KDNC0001', capacity - 32, 1)
        result, rows = native_image.relocate(upload, base, {'strcmp': base + 4096})
        self.assertEqual(len(result), capacity)
        self.assertEqual(len(rows), 1)
        self.assertEqual(struct.unpack_from('<i', result, 65)[0], 4096 - 69)
        with self.assertRaisesRegex(bench_runtime.Failure, 'invalid direct-image header'):
            native_image.relocate(upload + b'\0', base, {'strcmp': base + 4096})

    def test_unreadable_capacity_definition_does_not_use_a_stale_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'include').mkdir()
            for definition in ('#define KD_CODE_BLOCK_SIZE 4194304\n',
                               '#define KD_CODE_BLOCK_SIZE (4096UL * 0)\n'):
                with self.subTest(definition=definition):
                    (path / 'include/exe_info.h').write_text(definition)
                    with patch.object(bench_runtime, 'ROOT', path):
                        with self.assertRaises(bench_runtime.Failure):
                            bench_runtime.image_capacity()

    def test_utf8_comments_preserve_the_exact_shared_capacity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'include').mkdir()
            (path / 'include/exe_info.h').write_text(
                '/* Per-image capacity — comments do not change the bound. */\n'
                '#define KD_CODE_BLOCK_SIZE (4096UL * 1024)\n', encoding='utf-8')
            with patch.object(bench_runtime, 'ROOT', path):
                self.assertEqual(bench_runtime.image_capacity(), 4 * 1024 * 1024)


if __name__ == '__main__':
    unittest.main(verbosity=2)
