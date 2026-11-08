"""Real miasm/codegen coverage for CFG edges outside the first text window."""

import contextlib
import errno
import io
import os
from pathlib import Path
import re
import struct
import tempfile
import unittest
from unittest.mock import patch

from test_jit_diagnostics import render, translator

memread = translator.memread
device_session = memread.device_session
BASE = 0xFFFFFFFFC1000000


def branch(source, target, opcode=b"\xe9"):
    return opcode + struct.pack("<i", target - source - 5)


class DeviceSessionTests(unittest.TestCase):
    """Real FDs, substituted control ioctls; this is not live module pinning."""

    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(device_session, "DEVICE", "/dev/null"))
        stack.enter_context(patch.dict(os.environ))
        os.environ.pop("KD_DEVICE_FD", None)
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stderr = io.StringIO()
        stack.enter_context(contextlib.redirect_stderr(self.stderr))
        self.pins = []
        self.source_state = device_session.OPEN
        self.pin_error = None
        self.caps_packet = device_session.CAPS_STRUCT.pack(10, 1019, 256, 8192)
        self.caps_result = 0
        self.caps_error = None
        self.caps_queries = []
        stack.enter_context(patch.object(device_session.fcntl, "ioctl", self.ioctl))

    def ioctl(self, fd, command, packet, mutate=False):
        os.fstat(fd)
        if command == device_session.INFO:
            self.assertTrue(mutate)
            packet[:] = device_session.INFO_STRUCT.pack(self.source_state, 0, 0, 1)
        elif command == device_session.CAPS:
            self.assertTrue(mutate)
            self.caps_queries.append(fd)
            if self.caps_error:
                raise OSError(self.caps_error, os.strerror(self.caps_error))
            if self.caps_packet is not None:
                packet[:] = self.caps_packet
            return self.caps_result
        elif command == device_session.PIN:
            self.pins.append(device_session.RANGE_STRUCT.unpack(packet))
            if self.pin_error:
                raise OSError(self.pin_error, os.strerror(self.pin_error))
        else:
            self.fail(f"unexpected ioctl: {command:#x}")
        return 0

    def assert_closed(self, fd):
        with self.assertRaises(OSError):
            os.fstat(fd)

    def test_direct_cli_lease_closes_after_normal_exit(self):
        with device_session.session() as fd:
            self.assertEqual(device_session.require(), fd)
            self.assertFalse(os.get_inheritable(fd))
            self.assertEqual(device_session.mutex_stack_bytes(), 256)
            self.assertEqual(device_session.percpu_module_bytes(), 8192)
            self.assertTrue(device_session.native_escape())
            self.assertTrue(device_session.string_services())
            self.assertTrue(device_session.string_write())
            self.assertTrue(device_session.audited_strings())
            self.assertTrue(device_session.address_guard())
            self.assertEqual(self.caps_queries, [fd])
        self.assert_closed(fd)
        with self.assertRaisesRegex(RuntimeError, "active kd_dev session"):
            device_session.require()

    def test_inherited_lease_never_reopens_or_closes_the_original(self):
        parent = os.open("/dev/null", os.O_RDWR)
        try:
            os.set_inheritable(parent, True)
            os.environ["KD_DEVICE_FD"] = str(parent)
            with (
                patch.object(os, "open", side_effect=AssertionError("reopen")),
                device_session.session() as fd,
            ):
                self.assertNotEqual(fd, parent)
                self.assertEqual(os.fstat(fd), os.fstat(parent))
                self.assertFalse(os.get_inheritable(fd))
                self.assertFalse(os.get_inheritable(parent))
                self.assertEqual(self.caps_queries, [fd])
                self.assertEqual(device_session.mutex_stack_bytes(), 256)
                self.assertEqual(device_session.percpu_module_bytes(), 8192)
            self.assert_closed(fd)
            os.fstat(parent)
        finally:
            os.close(parent)

    def test_invalid_inherited_descriptor_is_not_a_new_session(self):
        for value in ("", "invalid", "-1", "0", "1", "2", "2147483647"):
            with self.subTest(value=value):
                os.environ["KD_DEVICE_FD"] = value
                with (
                    patch.object(os, "open", side_effect=AssertionError("reopen")),
                    self.assertRaises((ValueError, OSError)),
                    device_session.session(),
                ):
                    self.fail("invalid descriptor accepted")
                self.assertIsNone(device_session._fd)

    def test_wrong_or_readonly_device_is_rejected_without_fd_leak(self):
        for path, mode in (("/dev/zero", os.O_RDWR), ("/dev/null", os.O_RDONLY)):
            with self.subTest(path=path, mode=mode):
                parent = os.open(path, mode)
                try:
                    os.environ["KD_DEVICE_FD"] = str(parent)
                    before = set(os.listdir("/proc/self/fd"))
                    with (
                        self.assertRaisesRegex(
                            RuntimeError, "current read/write device"
                        ),
                        device_session.session(),
                    ):
                        self.fail("unrelated device accepted")
                    self.assertEqual(before, set(os.listdir("/proc/self/fd")))
                finally:
                    os.close(parent)

    def test_matching_regular_file_is_not_a_device(self):
        with tempfile.NamedTemporaryFile() as file:
            os.environ["KD_DEVICE_FD"] = str(file.fileno())
            with (
                patch.object(device_session, "DEVICE", file.name),
                self.assertRaisesRegex(RuntimeError, "current read/write device"),
                device_session.session(),
            ):
                self.fail("regular file accepted")

    def test_exception_closes_lease_and_allows_the_next_translation(self):
        with (
            self.assertRaisesRegex(RuntimeError, "fixture failure"),
            device_session.session() as fd,
        ):
            raise RuntimeError("fixture failure")
        self.assert_closed(fd)
        with device_session.session() as new_fd:
            self.assertEqual(device_session.require(), new_fd)

    def test_nested_session_cannot_discard_the_outer_lease(self):
        with device_session.session() as fd:
            with (
                self.assertRaisesRegex(RuntimeError, "already active"),
                device_session.session(),
            ):
                self.fail("nested session accepted")
            self.assertEqual(device_session.require(), fd)
            self.assertEqual(device_session.mutex_stack_bytes(), 256)
            os.fstat(fd)

    def test_capability_is_cached_only_for_the_validated_lease(self):
        with device_session.session() as fd:
            self.assertEqual(device_session.mutex_stack_bytes(), 256)
            self.assertEqual(device_session.percpu_module_bytes(), 8192)
            self.caps_packet = device_session.CAPS_STRUCT.pack(1, 0, 0, 0)
            self.assertEqual(device_session.mutex_stack_bytes(), 256)
            self.assertEqual(device_session.percpu_module_bytes(), 8192)
            self.assertTrue(device_session.native_escape())
            self.assertEqual(self.caps_queries, [fd])
        self.assertEqual(device_session._mutex_stack_bytes, 0)
        self.assertEqual(device_session._percpu_module_bytes, 0)
        self.assertFalse(device_session._native_escape)
        self.assertFalse(device_session._address_guard)
        self.assertFalse(device_session._string_services)
        self.assertFalse(device_session._string_write)
        self.assertFalse(device_session._audited_strings)
        self.assertFalse(device_session._direct_strings)
        self.assertFalse(device_session._root_native_escape)
        self.assertFalse(device_session._indirect_call)
        self.assertFalse(device_session._origin_instruction)
        with self.assertRaisesRegex(RuntimeError, "active kd_dev session"):
            device_session.mutex_stack_bytes()
        with self.assertRaisesRegex(RuntimeError, "active kd_dev session"):
            device_session.percpu_module_bytes()
        with self.assertRaisesRegex(RuntimeError, "active kd_dev session"):
            device_session.native_escape()
        with self.assertRaisesRegex(RuntimeError, "active kd_dev session"):
            device_session.address_guard()
        with self.assertRaisesRegex(RuntimeError, "active kd_dev session"):
            device_session.string_services()
        with self.assertRaisesRegex(RuntimeError, "active kd_dev session"):
            device_session.string_write()
        with self.assertRaisesRegex(RuntimeError, "active kd_dev session"):
            device_session.audited_strings()
        with self.assertRaisesRegex(RuntimeError, "active kd_dev session"):
            device_session.direct_strings()
        with self.assertRaisesRegex(RuntimeError, "active kd_dev session"):
            device_session.root_native_escape()
        with self.assertRaisesRegex(RuntimeError, "active kd_dev session"):
            device_session.indirect_call()
        with self.assertRaisesRegex(RuntimeError, "active kd_dev session"):
            device_session.origin_instruction()
        with self.assertRaisesRegex(RuntimeError, "active kd_dev session"):
            device_session.indirect_tail()
        with self.assertRaisesRegex(RuntimeError, "exclusive KD mutex object"), device_session.session():
            self.fail("old provider entered translator")
        self.assertEqual(len(self.caps_queries), 2)

    def test_known_versions_never_infer_an_unadvertised_module_arena(self):
        # Raw observers can inspect old providers; translation needs v5 exclusive objects and immutable images.
        for version, features, stack, module in (
            (1, 0, 0, 0), (1, 1, 256, 0), (2, 0, 0, 0),
            (2, 1, 256, 0), (2, 2, 0, 8192), (2, 3, 256, 8192),
            (3, 3, 256, 8192), (3, 7, 256, 8192),
        ):
            with self.subTest(version=version, features=features):
                self.caps_packet = device_session.CAPS_STRUCT.pack(version, features, stack, module)
                fd = os.open('/dev/null', os.O_RDWR)
                try:
                    self.assertEqual(device_session.query_capabilities(fd), {
                        'mutex_stack_bytes': stack, 'percpu_module_bytes': module,
                        'mutex_images': False, 'mutex_exclusive': False,
                        'native_escape': False, 'address_guard': False,
                        'string_services': False, 'string_write': False,
                        'audited_strings': False, 'direct_strings': False,
                        'root_native_escape': False, 'indirect_call': False,
                        'origin_instruction': False, 'origin_call': False,
                        'origin_memory': False, 'origin_context_read': False,
                        'indirect_tail': False, 'source_frontier': False,
                        'source_frontier_extensions': False,
                        'source_frontier_controls': False,
                        'source_frontier_direction': False})
                finally:
                    os.close(fd)
                with self.assertRaisesRegex(RuntimeError, "exclusive KD mutex object"), device_session.session():
                    self.fail("old provider entered translator")
        self.assertNotIn("JIT_CAPABILITY_INVALID", self.stderr.getvalue())

    def test_shared_linux_object_provider_is_refused(self):
        self.caps_packet = device_session.CAPS_STRUCT.pack(4, 11, 256, 8192)
        with self.assertRaisesRegex(RuntimeError, "exclusive KD mutex object"), device_session.session():
            self.fail("Linux-object provider entered KD-only translator")
        self.assertEqual(self.pins, [])

    def test_marker_capability_is_optional_and_versioned(self):
        for version, features, expected in ((5, 27, False), (6, 27, False), (6, 59, True)):
            with self.subTest(version=version, features=features):
                self.caps_packet = device_session.CAPS_STRUCT.pack(version, features, 256, 8192)
                with device_session.session():
                    self.assertEqual(device_session.native_escape(), expected)
                self.assertFalse(device_session._native_escape)
        self.caps_packet = device_session.CAPS_STRUCT.pack(5, 59, 256, 8192)
        with self.assertRaisesRegex(RuntimeError, "exclusive KD mutex object"), device_session.session():
            self.fail("old provider advertised an unknown marker guarantee")

    def test_old_optional_capability_does_not_enable_preservation(self):
        self.caps_error = errno.ENOTTY
        with self.assertRaisesRegex(RuntimeError, "exclusive KD mutex object"), device_session.session():
            self.fail("old provider entered translator")
        self.assertEqual(self.pins, [])
        self.assertIn("reason=JIT_CAPABILITY_UNAVAILABLE", self.stderr.getvalue())

    def test_address_guard_capability_is_optional_and_versioned(self):
        for version, features, expected in ((5, 27, False), (6, 59, False),
                                            (7, 59, False), (7, 123, True)):
            with self.subTest(version=version, features=features):
                self.caps_packet = device_session.CAPS_STRUCT.pack(version, features, 256, 8192)
                with device_session.session():
                    self.assertEqual(device_session.address_guard(), expected)
                self.assertFalse(device_session._address_guard)
        self.caps_packet = device_session.CAPS_STRUCT.pack(6, 123, 256, 8192)
        with self.assertRaisesRegex(RuntimeError, "exclusive KD mutex object"), device_session.session():
            self.fail("older provider advertised an unknown address-guard contract")

    def test_string_service_capability_requires_current_provider_and_lease(self):
        for version, features, expected in ((7, 123, False), (8, 123, False),
                                            (8, 251, True), (9, 507, True)):
            with self.subTest(version=version, features=features):
                self.caps_packet = device_session.CAPS_STRUCT.pack(version, features, 256, 8192)
                with device_session.session():
                    self.assertEqual(device_session.string_services(), expected)
                self.assertFalse(device_session._string_services)
        self.caps_packet = device_session.CAPS_STRUCT.pack(7, 251, 256, 8192)
        with self.assertRaisesRegex(RuntimeError, "exclusive KD mutex object"), device_session.session():
            self.fail("older provider advertised an unknown string-service contract")

    def test_string_writer_requires_its_separate_capability_and_lease(self):
        for version, features, expected in ((8, 251, False), (9, 251, False),
                                            (9, 507, True), (9, 379, True)):
            with self.subTest(version=version, features=features):
                self.caps_packet = device_session.CAPS_STRUCT.pack(version, features, 256, 8192)
                with device_session.session():
                    self.assertEqual(device_session.string_write(), expected)
                    self.assertEqual(device_session.string_services(), bool(features & 128))
                self.assertFalse(device_session._string_write)
        self.caps_packet = device_session.CAPS_STRUCT.pack(8, 507, 256, 8192)
        with self.assertRaisesRegex(RuntimeError, "exclusive KD mutex object"), device_session.session():
            self.fail("readonly string provider advertised an unknown writing contract")

    def test_audited_string_calls_require_new_capability_and_same_lease(self):
        for version, features, expected in ((8, 251, False), (9, 507, False),
                                            (10, 507, False), (10, 1019, True),
                                            (10, 763, True), (10, 891, True)):
            with self.subTest(version=version, features=features):
                self.caps_packet = device_session.CAPS_STRUCT.pack(version, features, 256, 8192)
                with device_session.session() as fd:
                    self.assertEqual(device_session.audited_strings(), expected)
                    # The active source lease keeps its negotiated contract;
                    # changing a later ioctl response cannot upgrade it.
                    self.caps_packet = device_session.CAPS_STRUCT.pack(10, 1019, 256, 8192)
                    self.assertEqual(device_session.audited_strings(), expected)
                    self.assertEqual(self.caps_queries[-1], fd)
                self.assertFalse(device_session._audited_strings)
                with self.assertRaisesRegex(RuntimeError, "active kd_dev session"):
                    device_session.audited_strings()
        for version, features in ((9, 1019), (10, 635), (device_session.CAPS_VERSION + 1, 1019)):
            self.caps_packet = device_session.CAPS_STRUCT.pack(version, features, 256, 8192)
            with self.subTest(version=version, features=features):
                with self.assertRaisesRegex(RuntimeError, "exclusive KD mutex object"), device_session.session():
                    self.fail("unknown or service-less audited-string contract admitted")

    def test_direct_string_calls_require_a_new_optional_capability_and_lease(self):
        for version, features, expected in ((10, 1019, False), (11, 1019, False),
                                            (11, 2043, True), (11, 1787, True),
                                            (11, 1915, True), (12, 2043, True)):
            with self.subTest(version=version, features=features):
                self.caps_packet = device_session.CAPS_STRUCT.pack(version, features, 256, 8192)
                with device_session.session() as fd:
                    self.assertEqual(device_session.direct_strings(), expected)
                    self.caps_packet = device_session.CAPS_STRUCT.pack(11, 2043, 256, 8192)
                    self.assertEqual(device_session.direct_strings(), expected)
                    self.assertEqual(self.caps_queries[-1], fd)
                self.assertFalse(device_session._direct_strings)
                with self.assertRaisesRegex(RuntimeError, "active kd_dev session"):
                    device_session.direct_strings()
        for version, features in ((10, 2043), (11, 1531), (11, 1659), (device_session.CAPS_VERSION + 1, 2043)):
            self.caps_packet = device_session.CAPS_STRUCT.pack(version, features, 256, 8192)
            with self.subTest(version=version, features=features):
                with self.assertRaisesRegex(RuntimeError, "exclusive KD mutex object"), device_session.session():
                    self.fail("unknown or missing native-API contract admitted")

    def test_root_markers_require_separate_capability_on_this_lease(self):
        for version, features, expected in (
                (6, 59, False), (11, 2043, False), (12, 59, False),
                (12, 2107, True), (12, 4091, True)):
            with self.subTest(version=version, features=features):
                self.caps_packet = device_session.CAPS_STRUCT.pack(version, features, 256, 8192)
                with device_session.session() as fd:
                    self.assertEqual(device_session.root_native_escape(), expected)
                    self.caps_packet = device_session.CAPS_STRUCT.pack(12, 4091, 256, 8192)
                    self.assertEqual(device_session.root_native_escape(), expected)
                    self.assertEqual(self.caps_queries[-1], fd)
                self.assertFalse(device_session._root_native_escape)
                with self.assertRaisesRegex(RuntimeError, "active kd_dev session"):
                    device_session.root_native_escape()
        # Old/future providers and a root bit without the shared flags contract
        # cannot opt into the new retained-root restore merely by setting bit11.
        for version, features in ((11, 4091), (device_session.CAPS_VERSION + 1, 4091), (12, 2075)):
            self.caps_packet = device_session.CAPS_STRUCT.pack(version, features, 256, 8192)
            with self.subTest(version=version, features=features):
                with self.assertRaisesRegex(RuntimeError, "exclusive KD mutex object"), device_session.session():
                    self.fail("unnegotiated root marker restore admitted")
                self.assertFalse(device_session._root_native_escape)

    def test_indirect_call_exit_requires_optional_bit_on_this_v12_lease(self):
        for version, features, expected in (
                (11, 2043, False), (12, 59, False), (12, 4091, False),
                (12, 27 | 4096, True), (12, 59 | 4096, True),
                (12, 4091 | 4096, True)):
            with self.subTest(version=version, features=features):
                self.caps_packet = device_session.CAPS_STRUCT.pack(version, features, 256, 8192)
                with device_session.session() as fd:
                    self.assertEqual(device_session.indirect_call(), expected)
                    self.caps_packet = device_session.CAPS_STRUCT.pack(12, 59 | 4096, 256, 8192)
                    self.assertEqual(device_session.indirect_call(), expected)
                    self.assertEqual(self.caps_queries[-1], fd)
                self.assertFalse(device_session._indirect_call)
                with self.assertRaisesRegex(RuntimeError, "active kd_dev session"):
                    device_session.indirect_call()
        for version in (11, device_session.CAPS_VERSION + 1):
            self.caps_packet = device_session.CAPS_STRUCT.pack(version, 59 | 4096, 256, 8192)
            with self.assertRaisesRegex(RuntimeError, "exclusive KD mutex object"), device_session.session():
                self.fail("unnegotiated indirect CALL exit admitted")
            self.assertFalse(device_session._indirect_call)

    def test_origin_instruction_requires_v13_flags_contract_and_this_lease(self):
        for version, features, expected in ((12, 59, False), (13, 59, False),
                                            (13, 59 | 8192, True),
                                            (13, 59 | 4096 | 8192, True)):
            with self.subTest(version=version, features=features):
                self.caps_packet = device_session.CAPS_STRUCT.pack(version, features, 256, 8192)
                with device_session.session() as fd:
                    self.assertEqual(device_session.origin_instruction(), expected)
                    self.caps_packet = device_session.CAPS_STRUCT.pack(13, 59 | 8192, 256, 8192)
                    self.assertEqual(device_session.origin_instruction(), expected)
                    self.assertEqual(self.caps_queries[-1], fd)
                self.assertFalse(device_session._origin_instruction)
                with self.assertRaisesRegex(RuntimeError, "active kd_dev session"):
                    device_session.origin_instruction()
        for version,features in ((12,59|8192),(13,27|8192),(device_session.CAPS_VERSION+1,59|8192)):
            self.caps_packet = device_session.CAPS_STRUCT.pack(version,features,256,8192)
            with self.assertRaisesRegex(RuntimeError, "exclusive KD mutex object"), device_session.session():
                self.fail("unnegotiated original-task instruction contract admitted")
            self.assertFalse(device_session._origin_instruction)

    def test_returning_calls_require_v14_and_provider_registry(self):
        self.caps_packet = device_session.CAPS_STRUCT.pack(14, 59 | 16384, 256, 8192)
        row = '1 ffffffff81001000 6 1 1 primitive_call\n'
        parameters = Path('/sys/module/kdlock_km/parameters')
        contents = dict(service_call_table_state='1 1 1\n')
        contents.update({f'service_call_page_{page}': row if page == 0 else ''
                         for page in range(8)})
        reads = []

        def read_registry(path, **kwargs):
            self.assertEqual(path.parent, parameters)
            self.assertEqual(kwargs, dict(encoding='ascii'))
            self.assertIn(path.name, contents)
            reads.append(path.name)
            return contents[path.name]

        # State is checked on both sides of the real paged reader. A service
        # declaration belongs in its page, never in the discovery-state file.
        with patch.object(Path, 'read_text', read_registry), device_session.session() as fd:
            calls = device_session.service_calls()
            self.assertEqual(calls[0xffffffff81001000]['nargs'], 6)
            self.assertEqual(calls[0xffffffff81001000]['cookie'], 1)
            self.assertEqual(self.caps_queries, [fd])
        self.assertEqual(reads, ['service_call_table_state'] +
                         [f'service_call_page_{page}' for page in range(8)] +
                         ['service_call_table_state'])
        self.assertFalse(device_session._origin_call)
        with self.assertRaisesRegex(RuntimeError, 'active kd_dev session'):
            device_session.service_calls()
        for version in (13, device_session.CAPS_VERSION + 1):
            self.caps_packet = device_session.CAPS_STRUCT.pack(version, 59 | 16384, 256, 8192)
            with self.assertRaisesRegex(RuntimeError, 'exclusive KD mutex object'), device_session.session():
                self.fail('unnegotiated returning CALL contract admitted')

    def test_context_reads_require_v16_and_this_lease(self):
        features = 59 | 16384 | 32768 | 65536
        self.caps_packet = device_session.CAPS_STRUCT.pack(16, features, 256, 8192)
        with device_session.session() as fd:
            self.assertTrue(device_session.origin_context_read())
            self.assertTrue(device_session.origin_memory())
            self.assertEqual(device_session.require(), fd)
        self.assertFalse(device_session._origin_context_read)
        with self.assertRaisesRegex(RuntimeError, "active kd_dev session"):
            device_session.origin_context_read()
        for version, bits in ((15, features), (device_session.CAPS_VERSION + 1, features),
                              (16, features & ~32768)):
            self.caps_packet = device_session.CAPS_STRUCT.pack(version, bits, 256, 8192)
            with self.assertRaisesRegex(RuntimeError, "exclusive KD mutex object"), device_session.session():
                self.fail("unnegotiated context-read contract admitted")

    def test_indirect_tails_require_v17_returning_call_contract_on_this_lease(self):
        for version, features, expected in (
                (16, 59 | 16384, False), (17, 59 | 16384, False),
                (17, 59 | 16384 | 131072, True)):
            with self.subTest(version=version, features=features):
                self.caps_packet = device_session.CAPS_STRUCT.pack(version, features, 256, 8192)
                with device_session.session() as fd:
                    self.assertEqual(device_session.indirect_tail(), expected)
                    self.caps_packet = device_session.CAPS_STRUCT.pack(17, 59 | 16384, 256, 8192)
                    self.assertEqual(device_session.indirect_tail(), expected)
                    self.assertEqual(device_session.require(), fd)
                self.assertFalse(device_session._indirect_tail)
                with self.assertRaisesRegex(RuntimeError, "active kd_dev session"):
                    device_session.indirect_tail()
        for version, features in ((16, 59 | 16384 | 131072),
                                  (17, 59 | 131072),
                                  (device_session.CAPS_VERSION + 1, 59 | 16384 | 131072)):
            self.caps_packet = device_session.CAPS_STRUCT.pack(version, features, 256, 8192)
            with self.subTest(version=version, features=features):
                with self.assertRaisesRegex(RuntimeError, "exclusive KD mutex object"), device_session.session():
                    self.fail("unnegotiated indirect tail contract admitted")
                self.assertFalse(device_session._indirect_tail)

    def test_source_frontier_requires_v18_and_resets_with_lease(self):
        for version, features, expected in ((17, 59 | 16384, False),
                (18, 59 | 16384, False), (18, 59 | 16384 | 262144, True)):
            self.caps_packet = device_session.CAPS_STRUCT.pack(version, features, 256, 8192)
            with device_session.session():
                self.assertEqual(device_session.source_frontier(), expected)
            self.assertFalse(device_session._source_frontier)
            with self.assertRaisesRegex(RuntimeError, 'active kd_dev session'):
                device_session.source_frontier()
        for version, features in ((17, 59 | 16384 | 262144), (18, 59 | 262144)):
            self.caps_packet = device_session.CAPS_STRUCT.pack(version, features, 256, 8192)
            with self.assertRaisesRegex(RuntimeError, 'exclusive KD mutex object'), device_session.session():
                self.fail('unnegotiated source frontier admitted')

    def test_frontier_controls_require_v20_and_reset_with_lease(self):
        for version, feature, extended, controls in (
                (18, 262144, False, False), (19, 262144, True, False),
                (20, 0, False, False), (20, 262144, True, True)):
            self.caps_packet = device_session.CAPS_STRUCT.pack(version, 59 | 16384 | feature, 256, 8192)
            with device_session.session():
                self.assertEqual(device_session.source_frontier_extensions(), extended)
                self.assertEqual(device_session.source_frontier_controls(), controls)
            self.assertFalse(device_session._source_frontier_controls)
            with self.assertRaisesRegex(RuntimeError, 'active kd_dev session'):
                device_session.source_frontier_controls()

    def test_frontier_direction_requires_v21_and_resets_with_lease(self):
        for version, feature, expected in (
                (19, 262144, False), (20, 262144, False),
                (21, 0, False), (21, 262144, True)):
            self.caps_packet = device_session.CAPS_STRUCT.pack(version, 59 | 16384 | feature, 256, 8192)
            with device_session.session():
                self.assertEqual(device_session.source_frontier_direction(), expected)
            self.assertFalse(device_session._source_frontier_direction)
            with self.assertRaisesRegex(RuntimeError, 'active kd_dev session'):
                device_session.source_frontier_direction()

    def test_partial_unknown_and_inconsistent_capabilities_stay_disabled(self):
        # Exact version/feature/window/reserved fields are one contract. Do
        # not infer a weaker bound from a larger, shorter or future response.
        packets = [None, b"", b"\x01" * 12]
        packets += [
            device_session.CAPS_STRUCT.pack(*values)
            for values in (
                (0, 1, 256, 0),
                (device_session.CAPS_VERSION + 1, 1, 256, 0),
                (1, 3, 256, 0),
                (1, 0, 256, 0),
                (1, 1, 0, 0),
                (1, 1, 255, 0),
                (1, 1, 512, 0),
                (1, 1, 256, 1),
                (1, 3, 256, 8192),
                (2, 3, 256, 0),
                (2, 1, 256, 8192),
                (2, 3, 256, 8191),
                (2, 3, 256, 8193),
                (2, 3, 255, 8192),
                (2, 7, 256, 8192),
            )
        ]
        for packet in packets:
            self.caps_packet = packet
            with self.subTest(packet=packet), self.assertRaisesRegex(RuntimeError, "exclusive KD mutex object"), device_session.session():
                self.fail("invalid contract entered translator")
            self.assertEqual(device_session._mutex_stack_bytes, 0)
            self.assertEqual(device_session._percpu_module_bytes, 0)
        self.caps_packet = device_session.CAPS_STRUCT.pack(1, 1, 256, 0)
        self.caps_result = 1
        with self.assertRaisesRegex(RuntimeError, "exclusive KD mutex object"), device_session.session():
            self.fail("invalid query result entered translator")
        self.assertEqual(
            self.stderr.getvalue().count("reason=JIT_CAPABILITY_INVALID"),
            len(packets) + 1,
        )

    def test_capability_io_failure_closes_without_inspection_or_cached_state(self):
        for error in (errno.EIO, errno.EBADF, errno.ETIMEDOUT):
            self.caps_error = error
            with (
                self.subTest(error=error),
                self.assertRaises(OSError),
                device_session.session(),
            ):
                self.fail("failed capability query entered translator")
            self.assert_closed(self.caps_queries[-1])
            self.assertIsNone(device_session._fd)
            self.assertEqual(device_session._mutex_stack_bytes, 0)
            self.assertEqual(device_session._percpu_module_bytes, 0)

    def test_unleased_kcore_read_is_refused_before_open(self):
        with (
            patch("builtins.open", side_effect=AssertionError("kcore opened")),
            self.assertRaisesRegex(RuntimeError, "active kd_dev session"),
        ):
            memread.read_kernel_addr_data(BASE, 4)

    def test_leased_kcore_read_preserves_the_existing_elf_mapping(self):
        segment = {"p_type": "PT_LOAD", "p_vaddr": BASE, "p_memsz": 4, "p_offset": 8}
        with (
            device_session.session() as fd,
            patch("builtins.open", return_value=io.BytesIO(b"padding!text")),
            patch.object(memread, "ELFFile") as elf,
        ):
            elf.return_value.iter_segments.return_value = [segment]
            self.assertEqual(memread.read_kernel_addr_data(BASE, 4), b"text")
            self.assertEqual(device_session.require(), fd)
            self.assertEqual(self.pins, [(BASE, 4)])

    def test_pin_refusal_precedes_kcore_read(self):
        with device_session.session():
            for error in (errno.EPERM, errno.ESTALE, errno.ENOSPC, errno.EINVAL):
                self.pin_error = error
                with (
                    self.subTest(error=error),
                    patch(
                        "builtins.open", side_effect=AssertionError("unresident read")
                    ),
                    self.assertRaises(device_session.SourceRefused) as refused,
                ):
                    memread.read_kernel_addr_data(BASE, 4)
                self.assertEqual(refused.exception.errno, error)
            for error in (errno.ENOTTY, errno.ESHUTDOWN, errno.EBADF):
                self.pin_error = error
                with self.subTest(error=error), self.assertRaises(OSError):
                    memread.read_kernel_addr_data(BASE, 4)

    def test_retired_or_incompatible_provider_closes_before_inspection(self):
        before = set(os.listdir("/proc/self/fd"))
        self.source_state = device_session.RETIRED
        with self.assertRaisesRegex(RuntimeError, "retired"), device_session.session():
            self.fail("retired writer accepted")
        with (
            patch.object(
                device_session.fcntl, "ioctl", side_effect=OSError(errno.ENOTTY, "old")
            ),
            self.assertRaises(OSError),
            device_session.session(),
        ):
            self.fail("unversioned provider accepted")
        self.assertEqual(before, set(os.listdir("/proc/self/fd")))
        self.source_state = device_session.DRAINING
        with device_session.session():
            device_session.pin_range(BASE, 4)
        self.assertEqual(self.pins, [(BASE, 4)])


class TextRegionTests(unittest.TestCase):
    def setUp(self):
        self.text = bytearray(b"\xc3" * 0x90000)
        self.entry = BASE + 0x2125
        self.body = BASE + 0x1F63
        self.reads = []
        self.put(self.entry, branch(self.entry, self.body))
        self.put(self.body, bytes.fromhex("b8df9b5713c3"))

    def put(self, address, data):
        offset = address - BASE
        self.text[offset : offset + len(data)] = data

    def read_memory(self, address, size):
        self.reads.append((address, size))
        self.assertGreaterEqual(address, BASE)
        self.assertLessEqual(address + size, BASE + len(self.text))
        return bytes(self.text[address - BASE : address - BASE + size])

    def initial(self):
        return [[bytes(self.text[0x2000:0x4000]), BASE + 0x2000, [self.entry]]]

    def translate(self, **kwargs):
        return render(
            "",
            entry=self.entry,
            regions=self.initial(),
            memory_reader=self.read_memory,
            return_status=True,
            **kwargs,
        )

    def test_backward_page_branch_contains_the_actual_body(self):
        assembly, log, status = self.translate()
        self.assertEqual(status, 0, log)
        self.assertIn(f"loc_{self.body:x}:".encode(), assembly)
        self.assertIn(b"0x13579bdf", assembly.lower())
        self.assertIn("TEXT_RANGE_EXTEND", log)
        self.assertEqual(self.reads, [(BASE + 0x1000, 0x3000)])

    def test_cold_source_refusal_is_terminal_policy_not_partial_code(self):
        with patch.object(
            self, "read_memory", side_effect=device_session.SourceRefused("source gone")
        ):
            assembly, log, status = self.translate()
        self.assertEqual(status, 2, log)
        self.assertEqual(assembly, b"")
        self.assertIn("source gone", log)

    def test_new_text_is_checked_for_context_dependencies(self):
        self.put(self.body, bytes.fromhex("64488b042528000000c3"))
        assembly, log, status = self.translate()
        self.assertEqual(status, 2)
        self.assertEqual(assembly, b"")
        self.assertIn("TEXT_RANGE_EXTEND", log)
        self.assertIn("FS-prefixed", log)
        self.assertIn(f'rip="{self.body:#x}"', log)

    def test_expanded_root_marker_rechecks_later_lock_control(self):
        # The marker appears only after the first expansion; its source
        # suffix then needs a second window. Neither discovery can trim the
        # original graph before the root-control and context proofs finish.
        later, lock = BASE + 0x7100, BASE + 0x9000
        prefix = bytes.fromhex("31c031c931d283f8010f31")
        metadata = bytes.fromhex("bf006000004889e64889e9ba00000000")
        call_ip = later + len(metadata)
        self.put(self.body, prefix + branch(self.body + len(prefix), later))
        for abi in (1, 3):
            for forbidden in (False, True):
                with self.subTest(abi=abi, forbidden=forbidden):
                    self.reads.clear()
                    self.put(later, metadata + branch(call_ip, lock, b"\xe8") + b"\xc3"
                             if forbidden else bytes.fromhex("b82a000000c3"))
                    options = {}
                    with contextlib.ExitStack() as stack:
                        if forbidden:
                            stack.enter_context(patch.object(
                                translator, "emit_jit_assembly",
                                side_effect=AssertionError("refused root reached emission")))
                        assembly, log, status = self.translate(
                            lock_kind="spin", abi=abi, root_native_escape_capable=True,
                            kernel_symbols={
                                "kd_spin_lock_clobber_v1": lock,
                                "kd_spin_unlock_clobber_v1": BASE + 0xA000,
                            },
                            build_options=options)
                    self.assertEqual(status, 2 if forbidden else 0, log)
                    if forbidden:
                        self.assertEqual(assembly, b"")
                        self.assertIn(
                            "root instruction markers reject nested or nonterminal lock control",
                            log)
                        self.assertIn(f'rip="{call_ip:#x}"', log)
                    else:
                        self.assertTrue(assembly)
                        self.assertEqual(options["requirements"], 33)
                    self.assertEqual(log.count("reason=TEXT_RANGE_EXTEND"), 2)
                    self.assertEqual(self.reads, [
                        (BASE + 0x1000, 0x3000),
                        (BASE + 0x1000, 0x3000),
                        (BASE + 0x7000, 0x2000),
                    ])

    def test_instruction_split_at_read_boundary_is_fetched_before_rejection(self):
        self.entry = BASE + 0x3FFF
        self.put(self.entry, bytes.fromhex("b8e0ac6824c3"))
        assembly, log, status = self.translate()
        self.assertEqual(status, 0, log)
        self.assertIn(b"0x2468ace0", assembly.lower())
        self.assertEqual(self.reads, [(BASE + 0x2000, 0x3000)])

    def test_fetched_branch_is_not_promoted_to_a_full_scan_callee(self):
        unlock = BASE + 0x9000
        self.put(
            self.body,
            branch(self.body, unlock, b"\xe8") + bytes.fromhex("64488b042528000000c3"),
        )
        assembly, log, status = self.translate(
            kernel_symbols={"_raw_spin_unlock": unlock}
        )
        self.assertEqual(status, 0, log)
        self.assertTrue(assembly)
        self.assertIn("reason=TEXT_RANGE_EXTEND", log)
        self.assertIn(f"loc_{self.body:x}:".encode(), assembly)
        self.assertNotIn(b"FS:[", assembly)

    def test_known_callee_keeps_full_scan_after_its_nested_unlock(self):
        lock, unlock = BASE + 0x8000, BASE + 0x9000
        # The root holds an outer lock and acquires a nested lock before this
        # actual callee releases it. That release cannot end the callee's scan
        # or hide the instruction before the root's outer release.
        root = branch(self.entry, lock, b"\xe8")
        root += branch(self.entry + len(root), self.body, b"\xe8")
        root += branch(self.entry + len(root), unlock, b"\xe8") + b"\xc3"
        self.put(self.entry, root)
        self.put(self.body, branch(self.body, unlock, b"\xe8") +
                 bytes.fromhex("64488b042528000000c3"))
        regions = [[bytes(self.text[0x1000:0x2000]), BASE + 0x1000, [self.body]],
                   self.initial()[0]]
        assembly, log, status = render(
            "", entry=self.entry, regions=regions, memory_reader=self.read_memory,
            kernel_symbols={"_raw_spin_lock": lock, "_raw_spin_unlock": unlock},
            return_status=True)
        self.assertEqual(status, 2, log)
        self.assertEqual(assembly, b"")
        self.assertIn("FS-prefixed memory access is unsupported", log)
        self.assertIn(f'rip="{self.body + 5:#x}"', log)

    def test_real_block_wins_over_cross_region_bad_placeholder_in_both_orders(self):
        previous = [bytes(self.text[0x1000:0x2000]), BASE + 0x1000, [self.body]]
        current = self.initial()[0]
        for regions in ([previous, current], [current, previous]):
            with self.subTest(reverse=regions[0] is current):
                assembly, log, status = render(
                    "",
                    entry=self.entry,
                    regions=regions,
                    memory_reader=self.read_memory,
                    return_status=True,
                )
                self.assertEqual(status, 0, log)
                self.assertIn(b"0x13579bdf", assembly.lower())
        self.assertEqual(self.reads, [])

    def test_new_hot_path_seeds_another_block_in_already_fetched_cold_window(self):
        # Both windows are fetched in one round. Only then does the backward
        # hot path expose a second cold entry; byte coverage is not CFG coverage.
        first, second, hot = BASE + 0x7100, BASE + 0x7200, BASE + 0x1100
        self.put(
            self.entry,
            b"\x85\xc0\x0f\x84"
            + struct.pack("<i", first - self.entry - 8)
            + branch(self.entry + 8, hot),
        )
        self.put(hot, branch(hot, second))
        self.put(first, bytes.fromhex("b82a000000c3"))
        for raw, error in (
            ("b863000000c3", None),
            ("64488b042528000000c3", "FS-prefixed"),
            ("0f04c3", "undecodable or empty basic block"),
        ):
            with self.subTest(error=error):
                self.reads.clear()
                self.put(second, bytes.fromhex(raw))
                assembly, log, status = self.translate()
                self.assertEqual(status, 2 if error else 0, log)
                self.assertEqual(log.count("reason=CFG_ROOT_EXTEND"), 1)
                if error:
                    self.assertEqual(assembly, b"")
                    self.assertIn(error, log)
                    self.assertIn(f'rip="{second:#x}"', log)
                else:
                    self.assertIn(f"loc_{second:x}:".encode(), assembly)
                    self.assertIn(b"0x63", assembly)
                self.assertEqual(
                    self.reads, [(BASE + 0x1000, 0x3000), (BASE + 0x7000, 0x2000)]
                )

    def test_additional_root_inside_existing_block_gets_a_dispatch_label(self):
        # A second source root may already have been decoded as a predecessor's
        # interior instruction. It still needs its own checked dispatch block.
        start = BASE + 0x2100
        raw = bytes.fromhex("b82a000000b863000000c3")
        assembly, log, status = render(
            "",
            entry=start + 5,
            regions=[(raw, start, [start, start + 5])],
            return_status=True,
        )
        self.assertEqual(status, 0, log)
        self.assertIn(f"loc_{start + 5:x}:".encode(), assembly)

    def test_cached_window_reseeding_shares_the_cfg_expansion_budget(self):
        # Alternating windows reveal one further target per pass without any
        # text read. The existing finite expansion limit must still apply.
        hot, cold = BASE + 0x2000, BASE + 0x7000
        for index in range(40):
            source, target = hot + index * 0x20, cold + index * 0x20
            self.put(source, branch(source, target))
            self.put(target, branch(target, source + 0x20))
        assembly, log, status = render(
            "",
            entry=hot,
            regions=[
                (bytes(self.text[0x2000:0x3000]), hot, [hot]),
                (bytes(self.text[0x7000:0x8000]), cold, [cold]),
            ],
            memory_reader=self.read_memory,
            return_status=True,
        )
        self.assertEqual(status, 2, log)
        self.assertEqual(assembly, b"")
        self.assertIn("32 CFG expansions", log)
        self.assertEqual(log.count("reason=CFG_ROOT_EXTEND"), 32)
        self.assertEqual(self.reads, [])

    def test_overlapping_windows_are_merged_and_roots_preserved(self):
        with patch.object(
            memread, "read_kernel_addr_data", side_effect=self.read_memory
        ):
            result = memread.extend_regions(self.initial(), {self.body})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1:], [BASE + 0x1000, [self.body, self.entry]])
        self.assertEqual(len(result[0][0]), 0x3000)

    def test_byte_budget_refuses_before_read_or_codegen(self):
        with patch.object(memread, "MAX_TEXT_BYTES", 0x2000):
            assembly, log, status = self.translate()
        self.assertEqual(status, 2)
        self.assertEqual(assembly, b"")
        self.assertIn("reachable text exceeds 8192 bytes", log)
        self.assertEqual(self.reads, [])

    def test_short_reads_are_errors_not_executable_placeholders(self):
        for responses in ([b'\xc3'], [device_session.SourceRefused(
                'outside resident module text', errno=errno.ESTALE), b'\xc3']):
            with (self.subTest(trimmed=len(responses) == 2),
                  patch.object(memread, 'read_kernel_addr_data', side_effect=responses),
                  self.assertRaisesRegex(RuntimeError, 'incomplete kernel text read')):
                memread.extend_regions([], {self.entry})

    def bounded_reader(self, end, error=errno.ESTALE):
        """Model a provider rejecting a window before any unavailable read."""
        def read(address, size):
            if address + size > end:
                self.reads.append((address, size))
                raise device_session.SourceRefused('outside resident module text', errno=error)
            return self.read_memory(address, size)
        return read

    def test_single_page_module_keeps_its_complete_body(self):
        entry = BASE + 0xE3
        self.put(entry, bytes.fromhex('b82a000000c3'))
        for error in (errno.ESTALE, errno.EPERM):
            with self.subTest(error=error):
                self.reads.clear()
                warnings = io.StringIO()
                reader = self.bounded_reader(BASE + 0x1000, error)
                translator.diagnostics.begin(0, entry)
                translator.diagnostics.set_instruction(entry, '<CFG text coverage>')
                with (patch.object(memread, 'read_kernel_addr_data', side_effect=reader),
                      contextlib.redirect_stderr(warnings)):
                    regions = memread.extend_regions([], {entry})
                self.assertEqual(regions[0][1:], [BASE, [entry]])
                self.assertEqual(len(regions[0][0]), 0x1000)
                self.assertEqual(self.reads, [(BASE, 0x2000), (BASE, 0x1000)])
                self.assertIn('reason=TEXT_WINDOW_TRIM', warnings.getvalue())
                self.assertIn('outside resident module text', warnings.getvalue())
                assembly, log, status = render('', entry=entry, regions=regions,
                    memory_reader=reader, return_status=True)
                self.assertEqual(status, 0, log)
                self.assertIn(b'0x2a', assembly.lower())

    def test_trim_preserves_old_bytes_and_every_new_root(self):
        old, target = BASE + 0xE3, BASE + 0x1125
        initial = [[bytes(self.text[:0x1000]), BASE, [old]]]
        with patch.object(memread, 'read_kernel_addr_data',
                          side_effect=self.bounded_reader(BASE + 0x2000)):
            regions = memread.extend_regions(initial, {target})
        self.assertEqual(regions[0][1:], [BASE, [old, target]])
        self.assertEqual(regions[0][0], bytes(self.text[:0x2000]))
        self.assertEqual(self.reads, [(BASE, 0x3000), (BASE, 0x2000)])

    def test_old_bytes_cannot_be_trimmed_when_their_lease_is_refused(self):
        initial = [[bytes(self.text[:0x2000]), BASE, [BASE + 0xE3]]]
        with (patch.object(memread, 'read_kernel_addr_data',
                           side_effect=self.bounded_reader(BASE + 0x1000)),
              self.assertRaises(device_session.SourceRefused)):
            memread.extend_regions(initial, {BASE + 0x100})
        self.assertEqual(self.reads, [(BASE, 0x2000)])

    def test_required_split_instruction_is_never_trimmed(self):
        entry = BASE + 0xFFF
        self.put(entry, bytes.fromhex('b82a000000c3'))
        reader = self.bounded_reader(BASE + 0x1000)
        with (patch.object(memread, 'read_kernel_addr_data', side_effect=reader),
              self.assertRaises(device_session.SourceRefused)):
            memread.extend_regions([], {entry})
        self.assertEqual(self.reads, [(BASE, 0x2000)])
        # A truncated block discovered inside an earlier read still fails the
        # existing decoder/CFG coverage gate; no partial image may be emitted.
        assembly, log, status = render('', entry=entry,
            regions=[[bytes(self.text[:0x1000]), BASE, [entry]]],
            memory_reader=reader, return_status=True)
        self.assertEqual(status, 2, log)
        self.assertEqual(assembly, b'')
        self.assertIn('outside resident module text', log)

    def test_reached_hole_or_fallthrough_is_refused_without_partial_image(self):
        reader = self.bounded_reader(BASE + 0x1000)
        for fallthrough in (False, True):
            with self.subTest(fallthrough=fallthrough):
                entry = BASE + 0xFF0 if fallthrough else BASE + 0xE3
                self.put(entry, b'\x90' * 16 if fallthrough else
                         branch(entry, BASE + 0x1100))
                with patch.object(memread, 'read_kernel_addr_data', side_effect=reader):
                    regions = memread.extend_regions([], {entry})
                assembly, log, status = render('', entry=entry, regions=regions,
                    memory_reader=reader, return_status=True)
                self.assertEqual(status, 2, log)
                self.assertEqual(assembly, b'')
                self.assertIn('outside resident module text', log)

    def test_capacity_invalid_and_untyped_refusals_never_retry(self):
        for error in (errno.ENOSPC, errno.EINVAL, errno.ESHUTDOWN, None):
            with self.subTest(error=error), patch.object(memread, 'read_kernel_addr_data',
                    side_effect=device_session.SourceRefused('refused', errno=error)) as reader:
                with self.assertRaises(device_session.SourceRefused):
                    memread.extend_regions([], {BASE + 0xE3})
                reader.assert_called_once_with(BASE, 0x2000)

    def test_non_kernel_branch_target_is_not_read(self):
        with (
            patch.object(memread, "read_kernel_addr_data") as reader,
            self.assertRaisesRegex(RuntimeError, "outside kernel space"),
        ):
            memread.extend_regions([], {0x1000})
        reader.assert_not_called()

    def test_expansion_count_is_bounded_even_when_byte_budget_allows_more(self):
        entry = BASE + 0x100
        for i in range(33):
            source = entry + i * 0x4000
            self.put(source, branch(source, source + 0x4000))
        with patch.object(memread, "MAX_TEXT_BYTES", 1024 * 1024):
            assembly, log, status = render(
                "",
                entry=entry,
                regions=[[bytes(self.text[:0x2000]), BASE, [entry]]],
                memory_reader=self.read_memory,
                return_status=True,
            )
        self.assertEqual(status, 2)
        self.assertEqual(assembly, b"")
        self.assertIn("32 CFG expansions", log)
        self.assertEqual(log.count("reason=TEXT_RANGE_EXTEND"), 32)
        self.assertLessEqual(
            max(start + size for start, size in self.reads), BASE + 0x82000
        )


class CompactTextWindowTests(unittest.TestCase):
    """Demand windows preserve complete source bytes with bounded lookahead."""

    def setUp(self):
        self.text = bytearray(b"\xc3" * 0x90000)
        self.reads = []
        self.policy = memread.RETAINED_WINDOW_POLICY

    def put(self, address, data):
        offset = address - BASE
        self.text[offset:offset + len(data)] = data

    def read_memory(self, address, size):
        self.reads.append((address, size))
        self.assertGreaterEqual(address, BASE)
        self.assertLessEqual(address + size, BASE + len(self.text))
        return bytes(self.text[address - BASE:address - BASE + size])

    def extend(self, regions, targets, **kwargs):
        with patch.object(memread, "read_kernel_addr_data", side_effect=self.read_memory):
            return memread.extend_regions(regions, targets, policy=self.policy, **kwargs)

    def render_retained(self, entry, regions, **kwargs):
        return render(
            "", entry=entry, regions=regions, memory_reader=self.read_memory,
            lock_kind="mutex", abi=2, trusted_source=True, return_status=True,
            kernel_symbols={
                "kd_mutex_direct_lock_clobber_v1": BASE + 0x82000,
                "kd_mutex_direct_unlock_clobber_v1": BASE + 0x83000,
                "kd_rwsem_up_write_clobber_v1": BASE + 0x84000,
            },
            returning_services={BASE + 0x85000: dict(
                cookie=1, nargs=1, result_kind=1, context_kind=1,
                symbol="primitive_call")},
            **kwargs,
        )

    def cfg_terminal(self, address):
        self.put(address, bytes.fromhex('b82a000000') +
                 branch(address + 5, BASE + 0x84000, b'\xe8') + b'\xc3')

    def cfg_source_chain(self, extensions):
        nodes = [BASE + 0x10000 + i * 0x3000 for i in range(extensions + 1)]
        for source, target in zip(nodes, nodes[1:]):
            self.put(source, branch(source, target))
        self.cfg_terminal(nodes[-1])
        start = nodes[0]
        offset = start - BASE
        return start, [(bytes(self.text[offset:offset + 1024]), start, [start])], nodes[-1]

    def cfg_seed_chain(self, rebuilds):
        hot, cold = BASE + 0x2000, BASE + 0x7000
        nodes = [(hot if i % 2 == 0 else cold) + i // 2 * 0x20
                 for i in range(rebuilds + 2)]
        for source, target in zip(nodes, nodes[1:]):
            self.put(source, branch(source, target))
        self.cfg_terminal(nodes[-1])
        regions = [(bytes(self.text[start - BASE:start - BASE + 4096]), start, [start])
                   for start in (hot, cold)]
        return hot, regions, nodes[-1]

    def cfg_mixed_chain(self, extensions):
        # Each new cold window reveals one unseeded entry in the existing hot
        # window. The real decoder alternates one read and one seed rebuild.
        hot = BASE + 0x2000
        for index in range(extensions):
            cold = BASE + 0x10000 + index * 0x3000
            self.put(hot + index * 0x20, branch(hot + index * 0x20, cold))
            self.put(cold, branch(cold, hot + (index + 1) * 0x20))
        terminal = hot + extensions * 0x20
        self.cfg_terminal(terminal)
        return hot, [(bytes(self.text[0x2000:0x3000]), hot, [hot])], terminal

    def test_abi2_source_extensions_obey_32_combined_transitions(self):
        for extensions in (32, 33):
            with self.subTest(extensions=extensions):
                self.reads.clear()
                entry, regions, terminal = self.cfg_source_chain(extensions)
                options = {}
                with patch.object(translator, 'decode_regions',
                                  wraps=translator.decode_regions) as decode:
                    assembly, log, status = self.render_retained(
                        entry, regions, build_options=options)
                self.assertEqual(decode.call_count, 33)
                self.assertEqual(log.count('reason=TEXT_RANGE_EXTEND'), 32)
                self.assertIn('source_extensions=32', log)
                self.assertIn('covered_rebuilds=0', log)
                self.assertIn('retained_profile=false', log)
                self.assertIn('total_transition_limit=32 decode_pass_limit=33', log)
                if extensions == 32:
                    self.assertEqual(status, 0, log)
                    self.assertIn(f'loc_{terminal:x}:'.encode(), assembly)
                    self.assertIn('requirements', options)
                    self.assertTrue(options['requirements'] & (1 << 13))
                else:
                    self.assertEqual((assembly, status, options), (b'', 2, {}))
                    self.assertIn('exhausted_budget="combined"', log)
                    self.assertIn('work_kind="source"', log)
                    self.assertIn('pending_targets_kind="source"', log)
                    # No 33rd source transition or late image construction.
                    self.assertTrue(all(address < terminal for address, _ in self.reads))

    def test_abi2_covered_rebuilds_obey_32_combined_transitions(self):
        for rebuilds in (32, 33):
            with self.subTest(rebuilds=rebuilds):
                self.reads.clear()
                entry, regions, terminal = self.cfg_seed_chain(rebuilds)
                options = {}
                with patch.object(translator, 'decode_regions',
                                  wraps=translator.decode_regions) as decode:
                    assembly, log, status = self.render_retained(
                        entry, regions, build_options=options)
                self.assertEqual(decode.call_count, 33)
                self.assertEqual(log.count('reason=CFG_ROOT_EXTEND'), 32)
                self.assertEqual(self.reads, [])
                self.assertIn('covered_rebuilds=32', log)
                self.assertIn('source_extensions=0', log)
                self.assertIn('retained_profile=false', log)
                self.assertIn('total_transition_limit=32 decode_pass_limit=33', log)
                if rebuilds == 32:
                    self.assertEqual(status, 0, log)
                    self.assertIn(f'loc_{terminal:x}:'.encode(), assembly)
                    self.assertIn('requirements', options)
                    self.assertTrue(options['requirements'] & (1 << 13))
                else:
                    self.assertEqual((assembly, status, options), (b'', 2, {}))
                    self.assertIn('exhausted_budget="combined"', log)
                    self.assertIn('work_kind="covered"', log)
                    self.assertIn('pending_targets_kind="covered"', log)

    def test_abi2_mixed_frontier_completes_at_32_combined_transitions(self):
        # Keep the original 32-pair stress graph as an explicit refusal case.
        for pairs in (16, 17, 32):
            with self.subTest(pairs=pairs):
                self.reads.clear()
                entry, regions, terminal = self.cfg_mixed_chain(pairs)
                options = {}
                with patch.object(translator, 'decode_regions',
                                  wraps=translator.decode_regions) as decode:
                    assembly, log, status = self.render_retained(
                        entry, regions, build_options=options)
                self.assertEqual(decode.call_count, 33)
                self.assertEqual(log.count('reason=CFG_ROOT_EXTEND'), 16)
                self.assertEqual(log.count('reason=TEXT_RANGE_EXTEND'), 16)
                self.assertIn('decode_pass=33', log)
                self.assertIn('covered_rebuilds=16 source_extensions=16', log)
                self.assertIn('retained_profile=false', log)
                self.assertIn('total_transition_limit=32 decode_pass_limit=33', log)
                if pairs == 16:
                    self.assertEqual(status, 0, log)
                    self.assertIn(f'loc_{terminal:x}:'.encode(), assembly)
                    self.assertIn('requirements', options)
                    self.assertTrue(options['requirements'] & (1 << 13))
                    self.assertNotIn('reason=CFG_WORK_LIMIT', log)
                else:
                    self.assertEqual((assembly, status, options), (b'', 2, {}))
                    self.assertIn('exhausted_budget="combined"', log)
                    self.assertIn('work_kind="source"', log)
                    self.assertIn('pending_targets_kind="source"', log)
                    pending_source = BASE + 0x10000 + 16 * 0x3000
                    self.assertTrue(all(address < pending_source for address, _ in self.reads))
                    self.assertNotIn(f'loc_{terminal:x}:'.encode(), assembly)

    def test_abi2_combined_ceiling_refuses_before_a34th_decode_or_read(self):
        entry, regions, terminal = self.cfg_mixed_chain(33)
        options = {}
        with patch.object(translator, 'decode_regions',
                          wraps=translator.decode_regions) as decode:
            assembly, log, status = self.render_retained(
                entry, regions, build_options=options)
        self.assertEqual((assembly, status, options), (b'', 2, {}))
        self.assertEqual(decode.call_count, 33)
        self.assertEqual(log.count('reason=CFG_ROOT_EXTEND'), 16)
        self.assertEqual(log.count('reason=TEXT_RANGE_EXTEND'), 16)
        self.assertIn('exhausted_budget="combined"', log)
        self.assertIn('work_kind="source"', log)
        self.assertIn('pending_targets_kind="source"', log)
        self.assertIn('covered_rebuilds=16 source_extensions=16', log)
        self.assertIn('retained_profile=false', log)
        self.assertIn('total_transition_limit=32 decode_pass_limit=33', log)
        pending_source = BASE + 0x10000 + 16 * 0x3000
        self.assertTrue(all(address < pending_source for address, _ in self.reads))
        self.assertNotIn(f'loc_{terminal:x}:'.encode(), assembly)

    def test_ordinary_mixed_frontier_keeps_32_combined_transitions(self):
        entry, regions, _ = self.cfg_mixed_chain(32)
        options = {}
        with patch.object(translator, 'decode_regions',
                          wraps=translator.decode_regions) as decode:
            assembly, log, status = render(
                '', entry=entry, regions=regions, memory_reader=self.read_memory,
                build_options=options, return_status=True)
        self.assertEqual((assembly, status, options), (b'', 2, {}))
        self.assertEqual(decode.call_count, 33)
        self.assertEqual(log.count('reason=CFG_ROOT_EXTEND'), 16)
        self.assertEqual(log.count('reason=TEXT_RANGE_EXTEND'), 16)
        self.assertIn('32 CFG expansions', log)
        self.assertIn('exhausted_budget="combined"', log)
        self.assertIn('covered_rebuilds=16 source_extensions=16', log)

    def test_retained_seeded_undecodable_block_is_not_a_complete_fixed_point(self):
        entry = BASE + 0x2000
        self.put(entry, bytes.fromhex('0f04') + b'\xc3' * 30)
        options = {}
        assembly, log, status = self.render_retained(
            entry, [(bytes(self.text[0x2000:0x2020]), entry, [entry])],
            build_options=options)
        self.assertEqual((assembly, status, options), (b'', 2, {}))
        self.assertEqual(self.reads, [])
        self.assertIn('reachable CFG contains an undecodable block', log)
        self.assertIn('pending_targets_kind="decode"', log)

    def test_compact_multi_root_closure_preserves_complete_decoding(self):
        targets = [BASE + 0x100 + index * 0x3000 for index in range(34)]
        entry = targets[0]
        body = bytearray()
        for index, target in enumerate(targets[1:], 1):
            body.extend(branch(entry + len(body), target, b"\xe8"))
            self.put(target, b"\xb8" + struct.pack("<I", index) + b"\xc3")
        body.extend(branch(entry + len(body), BASE + 0x84000, b"\xe8"))
        body.extend(b"\xc3")
        self.put(entry, body)
        with (patch.object(memread, "MAX_TEXT_BYTES", 256 * 1024),
              patch.object(memread, "read_kernel_addr_data", side_effect=self.read_memory),
              self.assertRaisesRegex(memread.TextReadLimit, "262144 bytes")):
            memread.extend_regions([], targets)
        self.assertEqual(self.reads, [])
        regions = self.extend([], targets)
        self.assertEqual(sum(len(data) for data, _, _ in regions), 34 * 1024)
        self.assertLess(34 * 1024, memread.MAX_TEXT_BYTES)
        self.assertEqual({root for _, _, roots in regions for root in roots}, set(targets))
        self.assertTrue(all(size == 1024 for _, size in self.reads))
        assembly, log, status = self.render_retained(entry, regions)
        self.assertEqual(status, 0, log)
        for target in targets:
            self.assertIn(f"loc_{target:x}:".encode(), assembly)

    def test_budget_plan_selects_largest_fit_before_any_source_read(self):
        targets = {BASE + 0x100, BASE + 0x3100}
        log = io.StringIO()
        memread.diagnostics.begin(0, min(targets))
        with (patch.object(memread, "RETAINED_MAX_TEXT_BYTES", 1024),
              contextlib.redirect_stderr(log)):
            regions = self.extend([], targets)
        self.assertEqual(self.reads, [(BASE + 0x100, 512), (BASE + 0x3100, 512)])
        self.assertEqual(sum(len(data) for data, _, _ in regions), 1024)
        self.assertEqual({root for _, _, roots in regions for root in roots}, targets)
        # One diagnostic survives the per-site coalescing and includes both
        # the rejected preferred plan and the selected, actually read plan.
        self.assertEqual(log.getvalue().count("reason=TEXT_CACHE_PLAN"), 1)
        self.assertIn("lookahead_bytes=512 ", log.getvalue())
        self.assertIn('"lookahead_bytes": 1024', log.getvalue())
        self.assertIn('"planned_bytes": 2048', log.getvalue())
        self.assertIn('"within_budget": false', log.getvalue())
        self.assertIn("selected=true", log.getvalue())

    def test_budget_retry_merges_roots_without_shrinking_old_bytes(self):
        old, overlap, separate = BASE + 0x103, BASE + 0x14F, BASE + 0x310F
        self.put(BASE + 0x100, bytes(range(80)))
        data = bytes(self.text[0x100:0x150])
        initial = [[data, BASE + 0x100, [old]]]
        with patch.object(memread, "RETAINED_MAX_TEXT_BYTES", 400):
            regions = self.extend(initial, {overlap, separate})
        self.assertEqual(self.reads, [(BASE + 0x100, 192), (BASE + 0x3100, 128)])
        self.assertEqual(regions[0][0][:len(data)], data)
        self.assertEqual(regions[0][2], [old, overlap])
        self.assertEqual(regions[1][2], [separate])
        self.assertEqual(initial, [[data, BASE + 0x100, [old]]])

    def test_compact_budget_retry_completes_learned_callee_before_emission(self):
        entry, callee = BASE + 0x100, BASE + 0x3100
        raw = branch(entry, callee, b"\xe8")
        raw += branch(entry + len(raw), BASE + 0x84000, b"\xe8") + b"\xc3"
        self.put(entry, raw)
        self.put(callee, bytes.fromhex("b82a000000c3"))
        plans = io.StringIO()
        with patch.object(memread, "RETAINED_MAX_TEXT_BYTES", 1536):
            initial = self.extend([], {entry})
            self.reads.clear()
            # Exercise the compact planner explicitly with a learned root.
            # Ordinary ABI2 translation does not select this window policy.
            memread.diagnostics.begin(0, entry)
            with contextlib.redirect_stderr(plans):
                complete = self.extend(initial, {callee})
            self.assertEqual(complete[0][0], initial[0][0])
            self.assertEqual({root for _, _, roots in complete for root in roots},
                             {entry, callee})
            policies = []
            assembly, log, status = self.render_retained(
                entry, complete, direct_call_depth=1, read_policies=policies)
        self.assertEqual(status, 0, log)
        self.assertEqual(self.reads, [(entry, 1024), (callee, 512)])
        self.assertEqual(policies, [memread.DEFAULT_WINDOW_POLICY])
        self.assertIn(f"loc_{entry:x}:".encode(), assembly)
        self.assertIn(f"loc_{callee:x}:".encode(), assembly)
        self.assertIn(f"loc_{callee:x}\nMOV".encode(), assembly)
        self.assertIn(b"0x2a", assembly.lower())
        self.assertIn("lookahead_bytes=512 ", plans.getvalue())
        self.assertIn('"within_budget": false', plans.getvalue())
        self.assertIn('selected=true', plans.getvalue())
        self.assertIn("pending_targets=0", log)

    def test_budget_minimum_keeps_full_instruction_across_alignment(self):
        entry, other = BASE + 0x10F, BASE + 0x3100
        raw = bytes.fromhex("666666666666660f1f840000000000")
        self.assertEqual(len(raw), 15)
        self.put(entry, raw)
        with patch.object(memread, "RETAINED_MAX_TEXT_BYTES", 45):
            regions = self.extend([], {entry, other})
        self.assertEqual(self.reads, [(BASE + 0x100, 30), (other, 15)])
        self.assertEqual(regions[0][0][15:], raw)
        self.assertEqual({root for _, _, roots in regions for root in roots}, {entry, other})

    def test_budget_retry_cannot_evict_old_bytes_to_fit_new_prefix(self):
        old, target = BASE + 0x103, BASE + 0x310F
        data = bytes(self.text[0x100:0x140])
        initial = [[data, BASE + 0x100, [old]]]
        with (patch.object(memread, "RETAINED_MAX_TEXT_BYTES", 93),
              patch.object(memread, "read_kernel_addr_data") as reader,
              self.assertRaisesRegex(memread.TextReadLimit, "93 bytes")):
            memread.extend_regions(initial, {target}, policy=self.policy)
        reader.assert_not_called()
        self.assertEqual(initial, [[data, BASE + 0x100, [old]]])

    def test_budget_fallback_requires_explicit_retained_policy(self):
        targets = {BASE + 0x100, BASE + 0x3100}
        for policy in (memread.DEFAULT_WINDOW_POLICY, memread.TextWindowPolicy(1024, 16)):
            with (self.subTest(policy=policy),
                  patch.object(memread, "MAX_TEXT_BYTES", 1024),
                  patch.object(memread, "read_kernel_addr_data") as reader,
                  self.assertRaisesRegex(memread.TextReadLimit, "1024 bytes")):
                memread.extend_regions([], targets, policy=policy)
            reader.assert_not_called()

    def test_source_refusal_does_not_restart_budget_planning(self):
        for error in (errno.EPERM, errno.ESTALE):
            with (self.subTest(error=error), patch.object(memread, "RETAINED_MAX_TEXT_BYTES", 64),
                  patch.object(memread.diagnostics, "warn") as warn,
                  patch.object(memread, "read_kernel_addr_data", side_effect=
                               device_session.SourceRefused("mandatory source unavailable", errno=error)) as reader,
                  self.assertRaises(device_session.SourceRefused)):
                memread.extend_regions([], {BASE + 0x100}, policy=self.policy)
            reader.assert_called_once_with(BASE + 0x100, 64)
            warn.assert_called_once()
            self.assertEqual(warn.call_args.kwargs["lookahead_bytes"], 64)
            self.assertTrue(warn.call_args.kwargs["selected"])

    def test_full_fifteen_byte_prefix_crosses_the_policy_alignment(self):
        entry = BASE + 0xFFF
        raw = bytes.fromhex("666666666666660f1f840000000000")
        self.assertEqual(len(raw), 15)
        self.put(entry, raw)
        short = memread.TextWindowPolicy(16, 16)
        with patch.object(memread, "read_kernel_addr_data", side_effect=self.read_memory):
            regions = memread.extend_regions([], {entry}, policy=short)
        data, start, roots = regions[0]
        self.assertEqual(start, BASE + 0xFF0)
        self.assertGreaterEqual(start + len(data), entry + 15)
        self.assertEqual(data[entry - start:entry - start + 15], raw)
        self.assertEqual(roots, [entry])

    def test_backward_extension_keeps_original_entry_and_body(self):
        entry, body = BASE + 0x4125, BASE + 0x1FFB
        self.put(entry, branch(entry, body))
        raw = bytes.fromhex("b8df9b5713")
        raw += branch(body + len(raw), BASE + 0x84000, b"\xe8") + b"\xc3"
        self.put(body, raw)
        initial = self.extend([], {entry})
        old = initial[0][0]
        self.reads.clear()
        regions = self.extend(initial, {body})
        self.assertEqual([start for _, start, _ in regions], [BASE + 0x1FF0, BASE + 0x4120])
        self.assertEqual(regions[1][0], old)
        assembly, log, status = self.render_retained(entry, regions)
        self.assertEqual(status, 0, log)
        self.assertIn(f"loc_{body:x}:".encode(), assembly)
        self.assertIn(b"0x13579bdf", assembly.lower())

    def test_truncated_instruction_fetches_a_complete_ordinary_extension(self):
        entry, cut = BASE + 0x2110, BASE + 0x2125
        self.put(entry, b"\x90" * (cut - entry))
        raw = bytes.fromhex("48b87856341200000000")
        raw += branch(cut + len(raw), BASE + 0x84000, b"\xe8") + b"\xc3"
        self.put(cut, raw)
        # The cached prefix ends inside MOVABS, before the complete immediate.
        initial = [[bytes(self.text[0x2110:0x212A]), entry, [entry]]]
        policies = []
        assembly, log, status = self.render_retained(entry, initial, read_policies=policies)
        self.assertEqual(status, 0, log)
        self.assertIn("TEXT_RANGE_EXTEND", log)
        self.assertIn(b"0x12345678", assembly.lower())
        self.assertEqual(len(self.reads), 1)
        address, size = self.reads[0]
        policy = memread.DEFAULT_WINDOW_POLICY
        self.assertEqual(policies, [policy])
        self.assertEqual(address, cut & ~(policy.alignment - 1))
        self.assertEqual(size, max(policy.lookahead, cut + 15 - address))
        self.assertGreaterEqual(address + size, cut + 15)
        self.assertIn(f'loc_{entry:x}:'.encode(), assembly)

    def test_retry_retains_old_bytes_and_every_root(self):
        old, target = BASE + 0xF03, BASE + 0xFE1
        initial = [[bytes(self.text[0xF00:0x1000]), BASE + 0xF00, [old]]]
        for error in (errno.EPERM, errno.ESTALE):
            self.reads.clear()
            def reader(address, size):
                self.reads.append((address, size))
                if address + size > BASE + 0x1000:
                    raise device_session.SourceRefused("outside resident module text", errno=error)
                return bytes(self.text[address - BASE:address - BASE + size])
            with (self.subTest(error=error),
                  patch.object(memread, "read_kernel_addr_data", side_effect=reader)):
                regions = memread.extend_regions(initial, {target}, policy=self.policy)
            self.assertEqual(regions, [[initial[0][0], BASE + 0xF00, [old, target]]])
            self.assertEqual(self.reads, [(BASE + 0xF00, 0x4E0), (BASE + 0xF00, 0x100)])

    def test_source_refusal_never_discards_mandatory_old_bytes(self):
        old, target = BASE + 0xF03, BASE + 0xF81
        initial = [[bytes(self.text[0xF00:0x1100]), BASE + 0xF00, [old]]]
        def reader(address, size):
            self.reads.append((address, size))
            raise device_session.SourceRefused("old prefix no longer resident", errno=errno.ESTALE)
        with (patch.object(memread, "read_kernel_addr_data", side_effect=reader),
              self.assertRaises(device_session.SourceRefused)):
            memread.extend_regions(initial, {target}, policy=self.policy)
        self.assertTrue(all(address + size >= BASE + 0x1100 for address, size in self.reads))
        self.assertEqual(initial[0][0], bytes(self.text[0xF00:0x1100]))

    def test_split_required_instruction_is_not_trimmed_to_a_page(self):
        entry = BASE + 0xFFF
        def reader(address, size):
            self.reads.append((address, size))
            raise device_session.SourceRefused("required instruction crosses text", errno=errno.ESTALE)
        with (patch.object(memread, "read_kernel_addr_data", side_effect=reader),
              self.assertRaises(device_session.SourceRefused)):
            memread.extend_regions([], {entry}, policy=self.policy)
        self.assertEqual(self.reads, [(BASE + 0xFF0, 1024)])

    def test_compact_mandatory_budget_failure_happens_before_any_source_read(self):
        targets = {BASE + 0x100, BASE + 0x3100}
        for error in (errno.EPERM, errno.ESTALE):
            with (self.subTest(error=error), patch.object(memread, "RETAINED_MAX_TEXT_BYTES", 29),
                  patch.object(memread, "read_kernel_addr_data", side_effect=
                               device_session.SourceRefused("unavailable lookahead", errno=error)) as reader,
                  self.assertRaisesRegex(memread.TextReadLimit, "29 bytes")):
                memread.extend_regions([], targets, policy=self.policy)
            reader.assert_not_called()


class ChunkedTextReadTests(unittest.TestCase):
    """Production I/O ordering with substituted leases and a complete ELF span."""

    def setUp(self):
        self.limit = memread.MAX_SOURCE_READ
        self.data = b"A" * self.limit + b"B" * self.limit + b"C" * 17
        self.policy = memread.RETAINED_WINDOW_POLICY

    @contextlib.contextmanager
    def kcore(self, *, refuse_at=None, error=errno.ESTALE):
        events, pins, reads = [], [], []
        fixture = self

        def pin(address, size):
            pins.append((address, size))
            events.append(("pin", address, size))
            if len(pins) == refuse_at:
                raise device_session.SourceRefused("piece lease refused", errno=error)

        class File(io.BytesIO):
            def read(self, size=-1):
                reads.append((self.tell(), size))
                events.append(("read", self.tell(), size))
                return super().read(size)

        def opened(path, mode):
            fixture.assertEqual((path, mode), ("/proc/kcore", "rb"))
            events.append(("open",))
            return File(b"padding!" + fixture.data)

        segment = {"p_type": "PT_LOAD", "p_vaddr": BASE,
                   "p_memsz": len(self.data), "p_offset": 8}
        with (patch.object(device_session, "pin_range", side_effect=pin),
              patch("builtins.open", side_effect=opened),
              patch.object(memread, "ELFFile") as elf):
            elf.return_value.iter_segments.return_value = [segment]
            yield events, pins, reads

    def test_request_limit_matches_provider_and_refuses_oversize_before_pin(self):
        header = (Path(__file__).resolve().parents[3] / "include/kd_source_api.h").read_text()
        match = re.search(r"#define KD_SOURCE_MAX_READ \((\d+) \* (\d+)\)", header)
        self.assertIsNotNone(match)
        self.assertEqual(self.limit, int(match[1]) * int(match[2]))
        self.assertEqual(self.limit, 262144)
        for size in (0, -1, self.limit + 1):
            with (self.subTest(size=size), patch.object(device_session, "pin_range") as pin,
                  patch("builtins.open") as opened, self.assertRaises(ValueError)):
                memread.read_kernel_addr_data(BASE, size)
            pin.assert_not_called()
            opened.assert_not_called()

    def test_every_piece_is_leased_before_read_and_concatenated_without_gaps(self):
        roots = [BASE + 1, BASE + self.limit + 2]
        initial = [[self.data, BASE, roots.copy()]]
        with self.kcore() as (events, pins, reads):
            result = memread.extend_regions(initial, {roots[-1]}, policy=self.policy)
        self.assertEqual(result, initial)
        self.assertEqual(pins, [(BASE, self.limit), (BASE + self.limit, self.limit),
                                (BASE + 2 * self.limit, 17)])
        self.assertEqual(reads, [(8, self.limit), (8 + self.limit, self.limit),
                                 (8 + 2 * self.limit, 17)])
        expected = []
        for (address, size), (offset, _) in zip(pins, reads):
            expected.extend((("pin", address, size), ("open",), ("read", offset, size)))
        self.assertEqual(events, expected)
        self.assertEqual(initial, [[self.data, BASE, roots]])

    def test_exact_provider_boundary_remains_one_ordinary_request(self):
        self.data = self.data[:self.limit]
        initial = [[self.data, BASE, [BASE + 1]]]
        with self.kcore() as (_, pins, _):
            result = memread.extend_regions(initial, set())
        self.assertEqual(result, initial)
        self.assertEqual(pins, [(BASE, self.limit)])

    def test_retained_aggregate_boundary_fits_four_requests_then_refuses_one_byte(self):
        self.assertEqual(memread.RETAINED_MAX_TEXT_BYTES, 1048576)
        self.data = b"Q" * memread.RETAINED_MAX_TEXT_BYTES
        initial = [[self.data, BASE, [BASE + 1]]]
        with self.kcore() as (_, pins, _):
            result = memread.extend_regions(initial, set(), policy=self.policy)
        self.assertEqual(result, initial)
        self.assertEqual(pins, [(BASE + i * self.limit, self.limit) for i in range(4)])
        with (patch.object(memread, "read_kernel_addr_data") as reader,
              self.assertRaisesRegex(memread.TextReadLimit, "1048576 bytes")):
            memread.extend_regions([[self.data + b"X", BASE, [BASE + 1]]], set(), policy=self.policy)
        reader.assert_not_called()
        self.assertEqual(initial, [[self.data, BASE, [BASE + 1]]])

    def test_ordinary_and_custom_nonretained_policies_keep_aggregate_limit(self):
        self.assertEqual(memread.MAX_TEXT_BYTES, 1048576)
        self.data = b"Q" * memread.MAX_TEXT_BYTES
        initial = [[self.data, BASE, [BASE + 1]]]
        for policy in (memread.DEFAULT_WINDOW_POLICY, memread.TextWindowPolicy(1024, 16)):
            with self.subTest(policy=policy), self.kcore() as (_, pins, _):
                result = memread.extend_regions(initial, set(), policy=policy)
            self.assertEqual(result, initial)
            self.assertEqual(pins, [(BASE + i * self.limit, self.limit) for i in range(4)])
            with (self.subTest(policy=policy), patch.object(memread, "read_kernel_addr_data") as reader,
                  self.assertRaisesRegex(memread.TextReadLimit, "1048576 bytes")):
                memread.extend_regions([[self.data + b"X", BASE, [BASE + 1]]], set(), policy=policy)
            reader.assert_not_called()
        self.assertEqual(initial, [[self.data, BASE, [BASE + 1]]])

    def test_original_page_policy_fits_observed_plan_with_separate_read_limit(self):
        previous, planned = 241664, 270336
        page = memread.PAGE_SIZE
        targets = {BASE + previous + index * page for index in range(-2, 6)}
        initial = [[self.data[:previous], BASE, [BASE + 1]]]
        self.assertEqual(memread.DEFAULT_WINDOW_POLICY, memread.TextWindowPolicy(8192, 4096))
        with (patch.object(memread, "MAX_TEXT_BYTES", 256 * 1024),
              patch.object(memread, "read_kernel_addr_data") as reader,
              self.assertRaisesRegex(memread.TextReadLimit, "262144 bytes")):
            memread.extend_regions(initial, targets)
        reader.assert_not_called()
        with self.kcore() as (_, pins, _):
            result = memread.extend_regions(initial, targets)
        self.assertEqual(result, [[self.data[:planned], BASE, sorted(targets | {BASE + 1})]])
        self.assertEqual(pins, [(BASE, self.limit), (BASE + self.limit, planned - self.limit)])
        self.assertTrue(all(0 < size <= self.limit for _, size in pins))
        self.assertEqual(initial, [[self.data[:previous], BASE, [BASE + 1]]])

    def test_later_lease_refusal_never_reads_that_piece_or_returns_old_prefix(self):
        initial = [[self.data, BASE, [BASE + 1]]]
        for position in (2, 3):
            for error in (errno.EPERM, errno.ESTALE, errno.ENOSPC, errno.EINVAL):
                with (self.subTest(position=position, error=error),
                      self.kcore(refuse_at=position, error=error) as (events, pins, reads),
                      self.assertRaises(device_session.SourceRefused) as caught):
                    memread.extend_regions(initial, set(), policy=self.policy)
                self.assertEqual(caught.exception.errno, error)
                self.assertEqual(len(pins), position)
                self.assertEqual(len(reads), position - 1)
                self.assertEqual(events[-1][0], "pin")
                self.assertEqual(initial, [[self.data, BASE, [BASE + 1]]])

    def test_later_missing_short_or_failed_read_never_returns_a_partial_region(self):
        initial = [[self.data, BASE, [BASE + 1]]]
        for failure in (None, b"B" * (self.limit - 1), OSError(errno.EIO, "read failed")):
            with (self.subTest(failure=type(failure).__name__),
                  patch.object(memread, "read_kernel_addr_data", side_effect=[
                      self.data[:self.limit], failure]) as reader,
                  self.assertRaises((RuntimeError, OSError))):
                memread.extend_regions(initial, set(), policy=self.policy)
            self.assertEqual([call.args for call in reader.call_args_list],
                             [(BASE, self.limit), (BASE + self.limit, self.limit)])
            self.assertEqual(initial, [[self.data, BASE, [BASE + 1]]])

    def test_optional_tail_refusal_keeps_chunked_mandatory_prefix_and_roots(self):
        old, target = BASE + 1, BASE + self.limit + 0xFE1
        initial = [[self.data[:self.limit + 0xFE0], BASE, [old]]]
        requests = []
        def reader(address, size):
            requests.append((address, size))
            if address + size > BASE + self.limit + 0x1000:
                raise device_session.SourceRefused("optional tail unavailable", errno=errno.ESTALE)
            return self.data[address - BASE:address - BASE + size]
        with patch.object(memread, "read_kernel_addr_data", side_effect=reader):
            result = memread.extend_regions(initial, {target}, policy=self.policy)
        self.assertEqual(requests, [(BASE, self.limit), (BASE + self.limit, 0x13E0),
                                    (BASE, self.limit), (BASE + self.limit, 0x1000)])
        self.assertEqual(result, [[self.data[:self.limit + 0x1000], BASE, [old, target]]])
        self.assertEqual(initial, [[self.data[:self.limit + 0xFE0], BASE, [old]]])

    def test_full_mandatory_instruction_can_cross_a_provider_request_boundary(self):
        target = BASE + self.limit - 1
        initial = [[self.data[:self.limit - 5], BASE, [BASE + 1]]]
        with (patch.object(memread, "RETAINED_MAX_TEXT_BYTES", self.limit + 14),
              self.kcore() as (_, pins, _)):
            result = memread.extend_regions(initial, {target}, policy=self.policy)
        self.assertEqual(pins, [(BASE, self.limit), (BASE + self.limit, 14)])
        self.assertEqual(result, [[self.data[:self.limit + 14], BASE, [BASE + 1, target]]])
        self.assertEqual(result[0][0][self.limit - 1:], self.data[self.limit - 1:self.limit + 14])


if __name__ == "__main__":
    unittest.main(verbosity=2)
