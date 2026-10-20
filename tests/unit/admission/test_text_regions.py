"""Real miasm/codegen coverage for CFG edges outside the first text window."""

import contextlib
import errno
import io
import os
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
                        'root_native_escape': False})
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
        for version, features in ((9, 1019), (10, 635), (13, 1019)):
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
        for version, features in ((10, 2043), (11, 1531), (11, 1659), (13, 2043)):
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
        for version, features in ((11, 4091), (13, 4091), (12, 2075)):
            self.caps_packet = device_session.CAPS_STRUCT.pack(version, features, 256, 8192)
            with self.subTest(version=version, features=features):
                with self.assertRaisesRegex(RuntimeError, "exclusive KD mutex object"), device_session.session():
                    self.fail("unnegotiated root marker restore admitted")
                self.assertFalse(device_session._root_native_escape)

    def test_partial_unknown_and_inconsistent_capabilities_stay_disabled(self):
        # Exact version/feature/window/reserved fields are one contract. Do
        # not infer a weaker bound from a larger, shorter or future response.
        packets = [None, b"", b"\x01" * 12]
        packets += [
            device_session.CAPS_STRUCT.pack(*values)
            for values in (
                (0, 1, 256, 0),
                (13, 1, 256, 0),
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
                    self.assertRaises(device_session.SourceRefused),
                ):
                    memread.read_kernel_addr_data(BASE, 4)
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
        self.assertNotIn(b"FS:[", assembly)

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
        with (
            patch.object(memread, "read_kernel_addr_data", return_value=b"\xc3"),
            self.assertRaisesRegex(RuntimeError, "incomplete kernel text read"),
        ):
            memread.extend_regions([], {self.entry})

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
