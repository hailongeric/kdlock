"""Guest-only pure fixtures for generated-image relocation evidence.

No real device, kernel text, helper instructions or helper arguments are read.
The capture tests substitute only the registry, device open and image readback.
"""
import contextlib
import ctypes
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime
import native_image
from native_only_protocol import Entry

BASE = 0xffffffffc1000000
SYMBOLS = {'strcmp': BASE - 0x1000, 'strscpy_pad': BASE + 0x1000}


def image(services=(4, 5), requirements=28):
    start = 128
    upload = bytearray(b'\x90' * (start + 16 * len(services) + 16))
    upload[9:16], upload[25:32], upload[41:45] = b'KDWB002', b'KDWC002', b'KDAB'
    upload[45:48] = bytes((1, 2, requirements))
    for index, service in enumerate(services):
        offset = 64 + 8 * index
        upload[offset:offset + 5] = b'\xe8\0\0\0\0'
        struct.pack_into('<IIQ', upload, start + 16 * index,
                         offset, service, BASE + 0x8000 + index * 16)
    struct.pack_into('<8sII', upload, len(upload) - 16, b'KDNC0001', start, len(services))
    return bytes(upload)


def entry(requirements=28):
    return dict(entry=BASE + 0x2000, code=BASE, status=0, pid=0, tgid=10,
                lock_kind=1, entry_abi=1, requirements=requirements, generation=3)


class NativeImageTests(unittest.TestCase):
    def test_registry_layout_and_parser_preserve_real_requirements_generation(self):
        self.assertEqual(ctypes.sizeof(Entry), 64)
        self.assertEqual((Entry.entry_abi.offset, Entry.requirements.offset, Entry.generation.offset),
                         (48, 52, 56))
        # Construct the wire bytes independently of the ctypes field declarations.
        raw = struct.pack('<iiiiQQQQIIQ', 0, 0, 10, 1, BASE + 0x2000, BASE,
                          0x1111, 0x2222, 1, 28, 3)
        with patch.object(bench_runtime, 'entries', return_value=[Entry.from_buffer_copy(raw)]):
            self.assertEqual(bench_runtime.registry(), [entry()])

    def test_exact_reconstruction_changes_only_displacements(self):
        upload = image()
        loaded, rows = native_image.relocate(upload, BASE, SYMBOLS)
        expected = bytearray(upload)
        for index, (offset, name) in enumerate(((64, 'strcmp'), (72, 'strscpy_pad'))):
            value = SYMBOLS[name] - BASE - offset - 5
            struct.pack_into('<i', expected, offset + 1, value)
            self.assertEqual(rows[index], dict(offset=offset, service=index + 4, symbol=name,
                target=SYMBOLS[name], continuation=BASE + 0x8000 + index * 16, displacement=value))
        self.assertEqual(loaded, bytes(expected))
        self.assertNotEqual(upload, loaded)

    def test_signed_rel32_limits_use_address_after_call(self):
        upload = image((4,), 20)
        for displacement in (-(2**31), 2**31 - 1):
            target = BASE + 64 + 5 + displacement
            loaded, _ = native_image.relocate(upload, BASE, {'strcmp': target})
            self.assertEqual(struct.unpack_from('<i', loaded, 65)[0], displacement)
        for displacement in (-(2**31) - 1, 2**31):
            with self.assertRaises(bench_runtime.Failure):
                native_image.relocate(upload, BASE, {'strcmp': BASE + 69 + displacement})

    def test_malformed_generated_metadata_is_refused(self):
        candidates = []
        for offset in (9, 25, 41, 45, 46, 47, 64, 65, len(image()) - 16):
            value = bytearray(image())
            value[offset] ^= 1
            candidates.append(value)
        for offset, value in ((128, 47), (144, 64), (132, 3), (len(image()) - 4, 65)):
            mutated = bytearray(image())
            struct.pack_into('<I', mutated, offset, value)
            candidates.append(mutated)
        value = bytearray(image())
        struct.pack_into('<Q', value, 136, 0)
        candidates += [value, image((4,), 28), image((5,), 28), image()[:47]]
        for upload in candidates:
            with self.subTest(upload=bytes(upload).hex()), self.assertRaises(bench_runtime.Failure):
                native_image.relocate(upload, BASE, SYMBOLS)
        for symbols in ({}, {'strcmp': 0, 'strscpy_pad': SYMBOLS['strscpy_pad']}):
            with self.assertRaises(bench_runtime.Failure):
                native_image.relocate(image(), BASE, symbols)

    @contextlib.contextmanager
    def captured(self, directory, *, loaded=None, registries=None):
        uploaded = image()
        path = directory / 'jit.bin'
        path.write_bytes(uploaded)
        expected, _ = native_image.relocate(uploaded, BASE, SYMBOLS)
        symbols = '\n'.join(f'{address:016x} T {name}' for name, address in SYMBOLS.items())
        # Substitute only the external symbol table. Capacity headers and
        # evidence files retain their actual bytes and readers.
        read_text = Path.read_text

        def captured_read_text(path, *args, **kwargs):
            if path == Path('/proc/kallsyms'):
                return symbols
            return read_text(path, *args, **kwargs)

        with contextlib.ExitStack() as stack:
            opened = stack.enter_context(patch.object(native_image.os, 'open', return_value=77))
            closed = stack.enter_context(patch.object(native_image.os, 'close'))
            stack.enter_context(patch.object(native_image, 'registry', side_effect=registries or [[entry()], [entry()]]))
            reader = stack.enter_context(patch.object(native_image, 'read_image', return_value=expected if loaded is None else loaded))
            stack.enter_context(patch.object(Path, 'read_text', new=captured_read_text))
            yield path, opened, closed, reader

    def test_capture_reads_only_loaded_image_and_keeps_reproducible_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with self.captured(directory) as (path, opened, closed, reader):
                receipt = native_image.capture(directory, entry(), path)
                opened.assert_called_once_with('/dev/kd_dev', os.O_RDONLY | os.O_CLOEXEC)
                closed.assert_called_once_with(77)
                reader.assert_called_once_with(BASE, len(image()))
            loaded = (directory / receipt['path']).read_bytes()
            self.assertEqual(receipt['loaded_sha256'], hashlib.sha256(loaded).hexdigest())
            self.assertEqual(receipt['uploaded_sha256'], hashlib.sha256(image()).hexdigest())
            self.assertEqual(json.loads((directory / receipt['path']).with_suffix('.json').read_text()), receipt)
            with self.captured(directory) as (path, *_):
                self.assertEqual(native_image.capture(directory, entry(), path), receipt)

    def test_capture_refuses_mismatch_registry_drift_and_changed_immutable_bytes(self):
        expected, _ = native_image.relocate(image(), BASE, SYMBOLS)
        corrupted = bytes([expected[0] ^ 1]) + expected[1:]
        for options in ({'loaded': corrupted}, {'registries': [[], []]},
                        {'registries': [[entry()], [entry() | {'generation': 4}]]}):
            with tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                with self.captured(directory, **options) as (path, _, closed, _):
                    with self.assertRaises(bench_runtime.Failure):
                        native_image.capture(directory, entry(), path)
                    closed.assert_called_once_with(77)
                self.assertFalse((directory / 'loaded-images').exists())
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with self.captured(directory) as (path, *_):
                receipt = native_image.capture(directory, entry(), path)
            (directory / receipt['path']).write_bytes(corrupted)
            with self.captured(directory) as (path, *_), self.assertRaises(bench_runtime.Failure):
                native_image.capture(directory, entry(), path)

    def test_direct_registry_cannot_silently_skip_readback(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = directory / 'jit.bin'
            for upload, row in ((b'abc', entry()), (image((4,), 4), entry()),
                                (image(), entry(4)), (image(), entry() | {'generation': 0})):
                path.write_bytes(upload)
                with patch.object(native_image.os, 'open', side_effect=AssertionError('device opened')):
                    with self.assertRaises(bench_runtime.Failure):
                        native_image.capture(directory, row, path)
            path.write_bytes(b'ordinary image')
            self.assertIsNone(native_image.capture(directory, entry(0), path))


if __name__ == '__main__':
    unittest.main()
