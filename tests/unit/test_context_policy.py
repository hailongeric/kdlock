# Admission corpus for context addresses, CFG scope and bounded CALL/RET facts.
# Sensitive encodings are inspected, not executed in a kernel critical section.
import contextlib
from fnmatch import fnmatchcase
import io
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

from miasm.expression.expression import ExprId
from test_jit_diagnostics import TEST_LOCK_SYMBOLS, render, translator

context_policy = translator.context_policy


class ContextPolicyTests(unittest.TestCase):
    def test_remote_continuation_needs_parent_admission_scope(self):
        base = 0x1000
        lock = TEST_LOCK_SYMBOLS["_raw_spin_lock"]
        unlock = TEST_LOCK_SYMBOLS["_raw_spin_unlock"]

        def call(target, offset):
            return b"\xe8" + struct.pack("<i", target - offset - 5)

        for suffix in (
            bytes.fromhex("b878563412"),
            bytes.fromhex("65488b042500000000"),
        ):
            with self.subTest(suffix=suffix.hex()):
                raw = call(lock, base) + call(unlock, base + 5) + suffix
                raw += call(unlock, base + len(raw)) + b"\xc3"
                child, _, child_status = render(
                    raw[5:].hex(), entry=base + 5, return_status=True
                )
                parent, _, parent_status = render(raw.hex(), return_status=True)
                # A standalone B starts at depth one and stops at unlock(A).
                self.assertEqual(child_status, 0)
                self.assertNotIn(b"0x12345678", child.lower())
                if suffix[0] == 0x65:
                    self.assertEqual(parent_status, context_policy.NATIVE_ONLY_EXIT)
                    self.assertEqual(parent, b"")
                else:
                    self.assertEqual(parent_status, 0)
                    self.assertIn(b"0x12345678", parent.lower())

    @staticmethod
    def mutex_calls(base, count):
        return (
            b"".join(
                b"\xe8" + struct.pack("<i", 0x3000 - (base + 5 * i + 5))
                for i in range(count)
            )
            + b"\xc3"
        )

    def assert_rejected(self, raw, **kwargs):
        assembly, log, status = render(raw, return_status=True, **kwargs)
        self.assertEqual(status, context_policy.NATIVE_ONLY_EXIT)
        self.assertEqual(assembly, b"")
        self.assertIn("CONTEXT_NATIVE_ONLY", log)
        self.assertNotIn("FLAGS_UNPRESERVED", log)
        return log

    def test_control_symbol_resolution_requires_all_distinct_addresses(self):
        self.assertEqual(
            context_policy.resolve_control_symbols(TEST_LOCK_SYMBOLS.get),
            TEST_LOCK_SYMBOLS,
        )
        for name in context_policy.CONTROL_SYMBOLS:
            for address in (None, 0):
                with self.subTest(name=name, address=address):
                    symbols = TEST_LOCK_SYMBOLS | {name: address}
                    with self.assertRaisesRegex(ValueError, name):
                        context_policy.resolve_control_symbols(symbols.get)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            context_policy.resolve_control_symbols(lambda name: 0x3000)

    def test_missing_lock_symbols_abort_before_reading_or_building(self):
        output = io.StringIO()
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as temp:
            os.chdir(temp)
            try:
                with (
                    contextlib.redirect_stderr(output),
                    patch.object(translator, "get_kernel_symbol", return_value=0),
                    patch.object(translator.memread, "read") as read,
                    patch.object(translator, "build_jit_binary") as build,
                    self.assertRaisesRegex(ValueError, "unavailable lock symbol"),
                ):
                    translator.dis_assem(0, 0x1000, "spin")
                read.assert_not_called()
                build.assert_not_called()
                self.assertEqual(list(Path("asm").iterdir()), [])
            finally:
                os.chdir(previous)
        self.assertIn("CONTEXT_SYMBOLS_UNAVAILABLE", output.getvalue())
        self.assertIn('action="retry_translation"', output.getvalue())
        self.assertNotIn("CONTEXT_NATIVE_ONLY", output.getvalue())

    def test_empty_hidden_or_partial_context_symbols_are_not_safe(self):
        for contents in (
            "",
            "ffffffff81001000 T unrelated\n",
            "0000000000000000 T schedule\n",
            "ffffffff81001000 T schedule\n0000000000000000 T rcu_read_lock\n",
            "invalid T schedule\n",
        ):
            with (
                self.subTest(contents=contents),
                patch("builtins.open", mock_open(read_data=contents)),
                self.assertRaises(ValueError),
            ):
                context_policy.load_context_symbols()

    def test_visible_context_symbols_keep_names_and_ignore_unrelated_zero(self):
        contents = (
            "ffffffff81001000 T schedule\n"
            "0000000000001234 D current_task\n"
            "0000000000000000 D unrelated\n"
        )
        with patch("builtins.open", mock_open(read_data=contents)):
            self.assertEqual(
                context_policy.load_context_symbols(),
                {0xFFFFFFFF81001000: "schedule", 0x1234: "current_task"},
            )

    @staticmethod
    def percpu_metadata():
        # CPU 1 is impossible and its offset is deliberately invalid. CPU 2
        # still needs coverage, independent of online CPU or current-CPU state.
        base = 0xFFFF888100000000
        metadata = {
            "__per_cpu_start": 0,
            "__per_cpu_end": 0x100,
            "__per_cpu_offset": 0xFFFFFFFF82000000,
            "nr_cpu_ids": 0xFFFFFFFF82000100,
            "__cpu_possible_mask": 0xFFFFFFFF82000200,
        }
        payloads = {
            metadata["nr_cpu_ids"]: struct.pack("<I", 3),
            metadata["__cpu_possible_mask"]: struct.pack("<Q", 5 | (1 << 63)),
            metadata["__per_cpu_offset"]: struct.pack("<QQQ", base, 0, base + 0x200),
        }
        text = "".join(f"{value:016x} A {name}\n" for name, value in metadata.items())
        text += (
            "90 A current_task\n98 A unrelated_percpu\nffffffff81000000 T schedule\n"
        )
        return base, metadata, payloads, text

    def test_runtime_percpu_ranges_cover_possible_cpus_without_truncation(self):
        base, metadata, payloads, text = self.percpu_metadata()
        # A named symbol in the middle cannot truncate whole-area coverage.
        text += f"{base + 0x20:x} D rcu_fixture\n{base + 0x30:x} D unrelated\n"
        calls = []

        def read(address, size):
            calls.append((address, size))
            raw = payloads[address]
            self.assertEqual(len(raw), size)
            return raw

        with patch("builtins.open", mock_open(read_data=text)):
            symbols = context_policy.load_context_symbols(read_memory=read)
        self.assertEqual(len(calls), 6)
        self.assertEqual(calls[:3], calls[3:])
        self.assertEqual(calls[2], (metadata["__per_cpu_offset"], 24))
        for cpu, start in ((0, base), (2, base + 0x200)):
            for address, size in (
                (start, 1),
                (start + 0x80, 1),
                (start + 0xFF, 1),
                (start - 4, 8),
            ):
                self.assertEqual(
                    symbols.resolve(address, size), f"kernel_percpu_cpu_{cpu}"
                )
            self.assertIsNone(symbols.resolve(start + 0x100))
            self.assertIsNone(symbols.resolve(start - 8, 8))
        self.assertIsNone(symbols.resolve(base + 0x100))
        self.assertIsNone(symbols.resolve(0))
        self.assertEqual(symbols.resolve(0x90), "current_task")

    def test_runtime_percpu_section_offsets_and_modular_bases(self):
        base, metadata, payloads, _ = self.percpu_metadata()
        # Relocation arithmetic is modulo 64 bits; only the resulting interval
        # must be nonwrapping. Never add the linked section itself as a range.
        metadata["__per_cpu_start"] = 0xFFFFFFFF80000000
        metadata["__per_cpu_end"] = metadata["__per_cpu_start"] + 0x100
        start = metadata["__per_cpu_start"]
        payloads[metadata["__per_cpu_offset"]] = struct.pack(
            "<QQQ", (base - start) % (1 << 64), 0, (base + 0x200 - start) % (1 << 64)
        )
        ranges = context_policy.load_static_percpu_ranges(
            metadata, lambda address, size: payloads[address]
        )
        self.assertEqual(ranges.resolve(base + 0x40), "kernel_percpu_cpu_0")
        self.assertIsNone(ranges.resolve(start + 0x40))

    def test_module_percpu_arena_alignment_boundaries_and_codegen(self):
        # A sparse possible-CPU layout and an unaligned core end distinguish
        # the reserved arena from static bytes, alignment padding and unit tail.
        base, metadata, payloads, text = self.percpu_metadata()
        metadata["__per_cpu_end"] = 0x101
        payloads[metadata["__per_cpu_offset"]] = struct.pack(
            "<QQQ", base, 0, base + 0x4000
        )
        text = text.replace(
            "0000000000000100 A __per_cpu_end", "0000000000000101 A __per_cpu_end"
        )
        text += f"{base + 0x120:x} D rcu_module_fixture\n{base + 0x130:x} D unrelated\n"
        with patch("builtins.open", mock_open(read_data=text)):
            symbols = context_policy.load_context_symbols(
                read_memory=lambda address, size: payloads[address],
                percpu_module_bytes=8192,
            )
        for cpu, core in ((0, base), (2, base + 0x4000)):
            start, end = core + 0x104, core + 0x2104
            for address, width in (
                (start, 1),
                (start + 0x80, 8),
                (end - 1, 1),
                (start - 1, 2),
            ):
                self.assertEqual(
                    symbols.resolve(address, width), f"module_percpu_cpu_{cpu}"
                )
            for address in (core + 0x101, core + 0x103, end, core + 0x3000):
                self.assertIsNone(symbols.resolve(address))
            for kind in ("spin", "mutex"):
                # Numeric direct, derived, implicit and store-forwarded inputs
                # exercise the existing refusal paths, never real unsafe loads.
                for raw in (
                    b"\x48\xb8" + struct.pack("<Q", start + 0x80) + b"\xc3",
                    b"\x48\xb8"
                    + struct.pack("<Q", start - 1)
                    + bytes.fromhex("488b00c3"),
                    b"\x48\xbe" + struct.pack("<Q", end - 4) + bytes.fromhex("48adc3"),
                    b"\x48\xb8"
                    + struct.pack("<Q", end)
                    + bytes.fromhex("488907488b374883ee0448adc3"),
                ):
                    with self.subTest(cpu=cpu, kind=kind, raw=raw.hex()):
                        self.assertIn(
                            "module_percpu_cpu_",
                            self.assert_rejected(
                                raw.hex(), symbols=symbols, lock_kind=kind
                            ),
                        )
                assembly, _, result = render(
                    (
                        b"\x48\xb8" + struct.pack("<Q", end) + bytes.fromhex("488b00c3")
                    ).hex(),
                    symbols=symbols,
                    lock_kind=kind,
                    return_status=True,
                )
                self.assertEqual(result, 0)
                self.assertTrue(assembly)

    def test_module_percpu_capability_cannot_mask_overflow_or_overlap(self):
        base, metadata, payloads, _ = self.percpu_metadata()
        for value in (-1, 1, 8191, 8193, True, "8192"):
            read = Mock()
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "range capability"),
            ):
                context_policy.load_static_percpu_ranges(
                    metadata, read, module_bytes=value
                )
            read.assert_not_called()
        with self.assertRaisesRegex(ValueError, "leased memory reader"):
            context_policy.load_context_symbols(percpu_module_bytes=8192)
        for offset, reason in (
            (base + 0x200, "overlapping"),
            ((1 << 64) - 0x100, "runtime range"),
        ):
            payloads[metadata["__per_cpu_offset"]] = struct.pack(
                "<QQQ", base, 0, offset
            )
            with (
                self.subTest(offset=offset),
                self.assertRaisesRegex(ValueError, reason),
            ):
                context_policy.load_static_percpu_ranges(
                    metadata, lambda address, size: payloads[address], module_bytes=8192
                )

    def test_runtime_percpu_bad_metadata_and_unstable_reads_abort(self):
        base, metadata, payloads, _ = self.percpu_metadata()
        variants = []
        for name in metadata:
            variants.append((metadata.keys() - {name}, {}, "unavailable"))
        for start, end in (
            (1, 1),
            (2, 1),
            (0, context_policy.MAX_PERCPU_STATIC_BYTES + 1),
        ):
            variants.append(
                (
                    metadata | {"__per_cpu_start": start, "__per_cpu_end": end},
                    {},
                    "section bounds",
                )
            )
        for name in ("nr_cpu_ids", "__cpu_possible_mask", "__per_cpu_offset"):
            variants.append((metadata | {name: 0}, {}, "metadata address"))
        for nr in (0, context_policy.MAX_PERCPU_CPUS + 1):
            variants.append(
                (metadata, {metadata["nr_cpu_ids"]: struct.pack("<I", nr)}, "CPU count")
            )
        variants.append(
            (metadata, {metadata["__cpu_possible_mask"]: bytes(8)}, "empty possible")
        )
        for offsets, reason in (
            ((0, 0, base + 0x200), "runtime range"),
            ((base, 0, base), "overlapping"),
            ((base, 0, (1 << 64) - 0x80), "runtime range"),
        ):
            variants.append(
                (
                    metadata,
                    {metadata["__per_cpu_offset"]: struct.pack("<QQQ", *offsets)},
                    reason,
                )
            )
        for address in payloads:
            for raw in (None, b"", payloads[address][:-1]):
                variants.append((metadata, {address: raw}, "incomplete"))
        for fields, changed, reason in variants:
            fields = (
                {name: metadata[name] for name in fields}
                if isinstance(fields, set)
                else fields
            )
            with (
                self.subTest(fields=fields, changed=changed),
                self.assertRaisesRegex(ValueError, reason),
            ):
                context_policy.load_static_percpu_ranges(
                    fields,
                    lambda address, size, samples=payloads | changed: samples[address],
                )
        for changing in payloads:
            reads = {}

            def unstable(address, size, reads=reads, changing=changing):
                reads[address] = reads.get(address, 0) + 1
                raw = payloads[address]
                return (
                    bytes(size) if address == changing and reads[address] > 1 else raw
                )

            with (
                self.subTest(changing=changing),
                self.assertRaisesRegex(ValueError, "changed during inspection"),
            ):
                context_policy.load_static_percpu_ranges(metadata, unstable)

    def test_runtime_percpu_metadata_requires_unambiguous_core_symbols(self):
        _, metadata, payloads, text = self.percpu_metadata()
        for changed in (
            text.replace(" A __per_cpu_end\n", " A __per_cpu_end [fixture]\n"),
            text + "200 A __per_cpu_end\n",
        ):
            with (
                patch("builtins.open", mock_open(read_data=changed)),
                self.assertRaises(ValueError),
            ):
                context_policy.load_context_symbols(
                    read_memory=lambda address, size: payloads[address]
                )
        for failure in (
            OSError("unavailable kcore"),
            translator.memread.device_session.SourceRefused("cannot pin metadata"),
        ):
            with self.subTest(failure=failure), self.assertRaises(type(failure)):
                context_policy.load_static_percpu_ranges(
                    metadata, Mock(side_effect=failure)
                )

    def test_runtime_percpu_literal_and_forwarded_accesses_refuse_both_backends(self):
        base, _, payloads, text = self.percpu_metadata()
        with patch("builtins.open", mock_open(read_data=text)):
            symbols = context_policy.load_context_symbols(
                read_memory=lambda address, size: payloads[address]
            )
        for kind in ("spin", "mutex"):
            # Direct address-taking, derived overlap, and implicit IR loads all
            # use the existing checker. No per-CPU instruction is executed here.
            for raw in (
                b"\x48\xb8" + struct.pack("<Q", base + 0x80) + b"\xc3",
                b"\x48\xb8" + struct.pack("<Q", base - 4) + bytes.fromhex("488b00c3"),
                b"\x48\xbe"
                + struct.pack("<Q", base + 0x200 - 4)
                + bytes.fromhex("48adc3"),
                b"\x48\xb8"
                + struct.pack("<Q", base - 0x10)
                + bytes.fromhex("488907488b374883c62048adc3"),
            ):
                with self.subTest(kind=kind, raw=raw.hex()):
                    self.assertIn(
                        "kernel_percpu_cpu_",
                        self.assert_rejected(
                            raw.hex(), symbols=symbols, lock_kind=kind
                        ),
                    )
            for raw in (
                "b82a000000c3",
                (
                    b"\x48\xb8"
                    + struct.pack("<Q", base - 8)
                    + bytes.fromhex("488b00c3")
                ).hex(),
            ):
                assembly, _, result = render(
                    raw, symbols=symbols, lock_kind=kind, return_status=True
                )
                self.assertEqual(result, 0)
                self.assertTrue(assembly)

    def test_production_symbol_load_requires_leased_memory_reader(self):
        # Fail before text/codegen and check the real entrypoint's mandatory
        # dependency, rather than making only the optional parser tests pass.
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as temp, contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            stack.enter_context(
                patch.object(
                    translator, "get_kernel_symbol", side_effect=TEST_LOCK_SYMBOLS.get
                )
            )
            loader = stack.enter_context(
                patch.object(
                    context_policy,
                    "load_context_symbols",
                    side_effect=RuntimeError("percpu unavailable"),
                )
            )
            capability = stack.enter_context(
                patch.object(
                    translator.memread.device_session,
                    "percpu_module_bytes",
                    return_value=8192,
                )
            )
            read = stack.enter_context(patch.object(translator.memread, "read"))
            os.chdir(temp)
            try:
                with self.assertRaisesRegex(RuntimeError, "percpu unavailable"):
                    translator.dis_assem(0, 0x1000, "spin")
                loader.assert_called_once_with(
                    read_memory=translator.memread.read_kernel_addr_data,
                    percpu_module_bytes=8192,
                )
                capability.assert_called_once_with()
                loader.reset_mock()
                capability.side_effect = RuntimeError("range capability unavailable")
                for kind in ("spin", "mutex"):
                    with (
                        self.subTest(kind=kind),
                        self.assertRaisesRegex(
                            RuntimeError, "range capability unavailable"
                        ),
                    ):
                        translator.dis_assem(0, 0x1000, kind)
                loader.assert_not_called()
                read.assert_not_called()
                self.assertEqual(list(Path("asm").iterdir()), [])
            finally:
                os.chdir(previous)

    def test_symbol_failures_are_cli_errors_not_native_only_verdicts(self):
        locks = "".join(
            f"{address:016x} T {name}\n" for name, address in TEST_LOCK_SYMBOLS.items()
        )
        bootstrap = """
import contextlib, io, runpy, sys
from pathlib import Path
from unittest.mock import patch
script, fixture = sys.argv[1:]
sys.path.insert(0, str(Path(script).parent))
real_open = open
def fixture_open(path, *args, **kwargs):
    if path == '/proc/kallsyms':
        return io.StringIO(fixture)
    return real_open(path, *args, **kwargs)
sys.argv = [script, '0', '0x1000', 'spin']
with (
    # This negative isolates symbol discovery after a successful device lease.
    # Device identity/lease errors are tested separately; never load a module
    # just to reach this CLI branch or allow it to read real kernel text.
    patch('device_session.session', return_value=contextlib.nullcontext()),
    patch('device_session.percpu_module_bytes', return_value=8192),
    patch('builtins.open', side_effect=fixture_open),
    patch('memread.read', side_effect=AssertionError('must not read kernel text')),
):
    runpy.run_path(script, run_name='__main__')
"""
        for contents in ("", locks, locks + "0000000000000000 T schedule\n"):
            with self.subTest(contents=contents), tempfile.TemporaryDirectory() as temp:
                result = subprocess.run(
                    [sys.executable, "-c", bootstrap, translator.__file__, contents],
                    cwd=temp,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=20,
                )
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("reason=CONTEXT_SYMBOLS_UNAVAILABLE", result.stderr)
                self.assertIn('action="retry_translation"', result.stderr)
                self.assertNotIn("CONTEXT_NATIVE_ONLY", result.stderr)
                self.assertNotIn("must not read kernel text", result.stderr)
                self.assertEqual(list(Path(temp, "asm").iterdir()), [])

    def test_gs_reads_writes_rmw_and_current_all_rejected(self):
        for raw in (
            "65488b042528000000c3",
            "654889042528000000c3",
            "6548ff042528000000c3",
        ):
            with self.subTest(raw=raw):
                log = self.assert_rejected(raw)
                self.assertIn('rip="0x1000"', log)
                self.assertIn("GS/current", log)

    def test_branch_and_nested_body_are_checked(self):
        self.assert_rejected("4839d87501c365488b042528000000c3")
        self.assert_rejected(
            "e8fb1f000065488b042528000000c3",
            kernel_symbols={"_raw_spin_lock": 0x3000},
        )

    def test_implicit_string_and_xlat_segments_are_checked(self):
        for raw in ("65a5c3", "65acc3", "65d7c3", "65f3a5c3", "64acc3"):
            with self.subTest(raw=raw):
                self.assert_rejected(raw)

    def test_ir_implicit_sources_and_destinations_without_segments(self):
        for prefix, opcodes in (
            ("48bef82f0000000000004883c610", ("ac", "66ad", "ad", "48ad", "a4", "a6")),
            (
                "48bff82f0000000000004883c710",
                ("aa", "66ab", "ab", "48ab", "ae", "48af"),
            ),
        ):
            for opcode in opcodes:
                with self.subTest(prefix=prefix, opcode=opcode):
                    log = self.assert_rejected(
                        prefix + opcode + "c3", symbols=self.context_ranges()
                    )
                    self.assertIn("__per_cpu_offset", log)
                    self.assertIn('rip="0x100e"', log)

    def test_ir_memory_access_width_and_data_values_are_distinct(self):
        self.assert_rejected(
            "48befc2f00000000000048adc3", symbols=self.context_ranges()
        )
        for raw in (
            "48befc2f000000000000adc3",  # Four bytes end exactly before the table.
            "48bef82f00000000000048adc3",  # Eight bytes end before it too.
            "48bff81f00000000000048ab48a4c3",  # An unrelated destination.
            "b8f82f00004883c010bff81f000048abc3",  # Sensitive value, not a pointer.
            "f3a4c3",  # Runtime-only source/destination remain unknown.
        ):
            with self.subTest(raw=raw):
                _, _, status = render(
                    raw, symbols=self.context_ranges(), return_status=True
                )
                self.assertEqual(status, 0)

    def test_ir_xlat_checks_the_computed_byte_address(self):
        log = self.assert_rejected(
            "48bbf82f000000000000b810000000d7c3", symbols=self.context_ranges()
        )
        self.assertIn('inst="XLAT', log)
        self.assertIn("__per_cpu_offset", log)
        _, _, status = render(
            "48bbf82f00000000000031c0d7c3",
            symbols=self.context_ranges(),
            return_status=True,
        )
        self.assertEqual(status, 0)

    def test_ir_stack_reads_writes_and_call_are_checked_before_invalidation(self):
        prefix = bytes.fromhex("48bcfc2f0000000000004883c410")
        call = b"\xe8" + struct.pack("<i", 0x6000 - (0x1000 + len(prefix) + 5))
        for opcode, name in (
            (b"\x58", "POP"),
            (b"\x50", "PUSH"),
            (b"\xc3", "RET"),
            (call, "CALL"),
        ):
            with self.subTest(name=name):
                log = self.assert_rejected(
                    (prefix + opcode + b"\xc3").hex(), symbols=self.context_ranges()
                )
                self.assertIn(f'inst="{name}', log)
                self.assertIn("__per_cpu_offset", log)
        # The POP itself overlaps the table although its starting address does not.
        self.assert_rejected("48bcfc2f00000000000058c3", symbols=self.context_ranges())

    def test_ir_checks_each_successive_and_repeated_memory_access(self):
        log = self.assert_rejected(
            "48bef82f00000000000048ad48adc3", symbols=self.context_ranges()
        )
        self.assertIn('rip="0x100c"', log)
        self.assertIn('inst="LODSQ', log)
        for raw in (
            "48bef82f000000000000b910000000f3acc3",
            "48bff82f000000000000b910000000f3aac3",
            "48bef82f000000000000b910000000f3a4c3",
        ):
            with self.subTest(raw=raw):
                log = self.assert_rejected(raw, symbols=self.context_ranges())
                self.assertIn('inst="REP', log)
                self.assertIn("__per_cpu_offset", log)

    def test_ir_memory_widening_refuses_at_original_instruction(self):
        # Internal count/DF edges remain unpruned, even with native count one.
        # Exhaustion must not become an unknown pointer that silently passes.
        log = self.assert_rejected(
            "48bef81f000000000000b901000000f3acc3", symbols=self.context_ranges()
        )
        self.assertIn("bounded register-address alternatives", log)
        self.assertIn('rip="0x100f"', log)
        self.assertIn('inst="REP LODSB', log)

    def test_ir_memory_temporary_parallel_store_nested_and_condition(self):
        from miasm.expression.expression import ExprCond, ExprInt, ExprLoc, ExprMem
        from miasm.ir.ir import AssignBlock, IRBlock
        from test_jit_diagnostics import decode

        for kind in ("load", "store", "nested", "condition"):
            with self.subTest(kind=kind):
                tracker = context_policy.FlowConstants()
                tracker.update(decode("b8f82f0000"))
                line = decode("48d3e0")
                line.offset = 0x1234
                db = tracker.lifter.loc_db
                taken = db.add_location()
                end = db.get_or_create_offset_location(line.offset + line.l)
                target, finish = ExprLoc(taken, 64), ExprLoc(end, 64)
                rax, rdx = ExprId("RAX", 64), ExprId("RDX", 64)
                temp = ExprId("instruction_memory_address", 64)
                dst = tracker.lifter.IRDst
                entry = AssignBlock({temp: rax, rax: ExprInt(0, 64), dst: target})
                memory = ExprMem(temp + ExprInt(16, 64), 64)
                # Memory uses the old temp, even though this same block clears it.
                assignments = {temp: ExprInt(0, 64), dst: finish}
                if kind == "store":
                    assignments[memory] = ExprInt(0, 64)
                elif kind == "condition":
                    assignments[dst] = ExprCond(memory, finish, finish)
                else:
                    assignments[rdx] = (
                        ExprMem(memory, 64) if kind == "nested" else memory
                    )
                block = IRBlock(db, taken, [AssignBlock(assignments)])
                with (
                    patch.object(
                        tracker.lifter, "instr2ir", return_value=(entry, [block])
                    ),
                    self.assertRaises(context_policy.ContextFlowLimit) as error,
                ):
                    tracker.update(line, self.context_ranges())
                self.assertIn("__per_cpu_offset", str(error.exception))
                self.assertEqual(error.exception.offset, 0x1234)
                self.assertIs(error.exception.instruction, line)

    def test_ir_implicit_memory_after_outer_unlock_is_outside_admission(self):
        unlock = TEST_LOCK_SYMBOLS["_raw_spin_unlock"]
        suffix = bytes.fromhex("48bef82f0000000000004883c61048ad")

        def call(offset):
            return b"\xe8" + struct.pack("<i", unlock - offset - 5)

        assembly, _, status = render(
            (call(0x1000) + suffix + b"\xc3").hex(),
            symbols=self.context_ranges(),
            return_status=True,
        )
        self.assertEqual(status, 0)
        self.assertNotIn(b"LODS", assembly)
        self.assert_rejected(
            (suffix + call(0x1000 + len(suffix)) + b"\xc3").hex(),
            symbols=self.context_ranges(),
        )

    def test_irq_instructions_and_existing_base_restrictions(self):
        for raw in ("fac3", "fbc3", "0f01f8c3", "f3480faec0c3"):
            with self.subTest(raw=raw):
                # Complete decoder lookahead, not an artificially truncated read.
                self.assert_rejected(raw + "c3" * 15)

    def test_known_context_calls_and_tail_calls(self):
        for opcode in ("e8", "e9"):
            log = self.assert_rejected(
                opcode + "fb1f0000c3", symbols={0x3000: "schedule"}
            )
            self.assertIn("schedule", log)

    def test_irq_bh_lock_wrappers_resolve_as_context_symbols(self):
        names = (
            "_raw_spin_lock_irqsave",
            "_raw_spin_unlock_irqrestore",
            "_raw_spin_lock_irq",
            "_raw_spin_unlock_irq",
            "_raw_spin_lock_bh",
            "_raw_spin_unlock_bh",
            "_raw_spin_trylock_bh",
            "_raw_spin_rq_lock_irqsave",
            "_raw_read_lock_irqsave",
            "_raw_write_unlock_irqrestore",
            "_raw_read_unlock_bh",
            "_raw_write_lock_bh",
            "__raw_spin_lock_irqsave",
            "__raw_write_unlock_bh",
        )
        for name in names:
            for suffix in ("", ".isra.0", ".constprop.2"):
                with self.subTest(name=name, suffix=suffix):
                    self.assertTrue(context_policy.is_context_symbol(name + suffix))
        contents = "".join(
            f"{0x3000 + i * 0x100:x} T {name}\n" for i, name in enumerate(names)
        )
        with patch("builtins.open", mock_open(read_data=contents)):
            self.assertEqual(len(context_policy.load_context_symbols()), len(names))

    def test_irq_bh_calls_tail_calls_and_address_taking_refuse_before_codegen(self):
        for name in ("_raw_spin_lock_irqsave", "_raw_spin_unlock_bh"):
            contents = f"9000 T schedule\n3000 T {name}\n"
            with patch("builtins.open", mock_open(read_data=contents)):
                symbols = context_policy.load_context_symbols()
            for raw in ("e8fb1f0000c3", "e9fb1f0000", "48c7c000300000c3"):
                with self.subTest(name=name, raw=raw):
                    log = self.assert_rejected(raw, symbols=symbols)
                    self.assertIn(name, log)
                    self.assertIn('rip="0x1000"', log)

    def test_irq_wrapper_after_outer_unlock_is_not_part_of_caller(self):
        assembly, _, status = render(
            "e8fb1f0000e8f62f0000c3",
            kernel_symbols={"_raw_spin_unlock": 0x3000},
            symbols={0x4000: "_raw_spin_lock_irqsave"},
            return_status=True,
        )
        self.assertEqual(status, 0)
        self.assertNotIn(b"loc_1005:", assembly)

    def test_rip_relative_context_data(self):
        self.assert_rejected("488b05f91f0000c3", symbols={0x3000: "current_task"})

    def test_register_derived_sensitive_memory_and_calls_are_rejected(self):
        for raw in (
            "48b8f82f0000000000004883c010488b00c3",  # ADD then read.
            "48b8f82f000000000000488d581048891bc3",  # LEA then write.
            "b8f82f00004883c010488b00c3",  # EAX zero extends RAX.
            "48b8f82f0000000000004883c01048ff00c3",  # RMW.
            "48b8f82f000000000000488b580848891bc3",  # Displacement reaches start.
            "48b8ff2f0000000000000fb700c3",  # Widening source overlaps.
            "48b8f82f000000000000488b44c808c3",  # Unknown index, known base.
            "48b8f83f0000000000004883c010ffd0c3",  # Computed context CALL.
        ):
            with self.subTest(raw=raw):
                self.assert_rejected(raw, symbols=self.context_ranges())

    def test_overwrites_and_unknown_values_do_not_leave_stale_addresses(self):
        for raw in (
            "48b8f82f0000000000004883c0104831c0488b00c3",  # XOR clears RAX.
            "48b8f82f0000000000004883c010b800000000488b00c3",  # EAX overwrite.
            "48b8f82f0000000000004883c010488b07488b00c3",  # Memory load is unknown.
            "48b8f82f00000000000048f7e1488b4010c3",  # MUL implicitly writes RAX.
            "48b8f82f0000000000004883d010488b00c3",  # ADC needs unknown flags.
            "48b8f82f0000000000000fb600c3",  # One byte ends before the table.
        ):
            with self.subTest(raw=raw):
                _, _, status = render(
                    raw, symbols=self.context_ranges(), return_status=True
                )
                self.assertEqual(status, 0)

    def test_constant_tracker_uses_partial_register_and_parallel_write_semantics(self):
        from test_jit_diagnostics import decode

        tracker = context_policy.RegisterConstants()
        for raw in ("48b8f82f000000000000", "b008"):
            tracker.update(decode(raw))
        self.assertEqual(int(tracker.resolve(ExprId("RAX", 64))), 0x2F08)
        tracker.update(decode("b800300000"))
        self.assertEqual(int(tracker.resolve(ExprId("RAX", 64))), 0x3000)
        tracker.update(decode("bb01000000"))
        tracker.update(decode("4893"))  # XCHG RAX, RBX uses the old values in parallel.
        self.assertEqual(int(tracker.resolve(ExprId("RAX", 64))), 1)
        self.assertEqual(int(tracker.resolve(ExprId("RBX", 64))), 0x3000)
        tracker.update(decode("e800000000"))
        self.assertEqual(tracker.values, {})

    def test_unliftable_instruction_forgets_constants(self):
        from test_jit_diagnostics import decode

        tracker = context_policy.RegisterConstants()
        tracker.update(decode("b800300000"))
        self.assertTrue(tracker.values)
        with patch.object(tracker.lifter, "instr2ir", side_effect=NotImplementedError):
            tracker.update(decode("90"))
        self.assertEqual(tracker.values, {})

    def test_constant_context_addresses_cross_control_edges(self):
        for raw in (
            "48b8f82f000000000000eb004883c010488b00c3",
            "48b8f82f0000000000004885c9750231c04883c010488b00c3",
            "eb04488b00c348b8f82f0000000000004883c010ebec",
        ):
            with self.subTest(raw=raw):
                self.assert_rejected(raw, symbols=self.context_ranges())

    def test_conditional_move_preserves_sensitive_address_alternatives(self):
        for raw in (
            "48b8f82f000000000000480f44c1488b4010c3",  # Untaken old RAX.
            "48b8f82f000000000000480f44ca488b4010c3",  # Unaffected RAX.
            "48b9f82f000000000000480f44c1488b4010c3",  # Taken RCX.
            "48b8f82f000000000000480f4407488b4010c3",  # Unknown memory source.
            "48b8f82f000000000000660f44c1488b4010c3",  # Preserve AX alternative.
            "48b8f82f0000010000000f44c1488b4010c3",  # EAX clears upper half.
            "b9f82f00000f44c1488b4010c3",  # Taken ECX zero extension.
            "48b8f82f000000000000480f44c1eb00488b4010c3",  # Next CFG block.
        ):
            with self.subTest(raw=raw):
                log = self.assert_rejected(raw, symbols=self.context_ranges())
                self.assertIn("__per_cpu_offset", log)
                self.assertIn('inst="MOV', log)

    def test_conditional_move_never_prunes_using_flags(self):
        for opcode in range(0x40, 0x50):
            raw = "48b8f82f00000000000031c9480f" + f"{opcode:02x}c1"
            with self.subTest(opcode=opcode):
                # Even XOR-established flags cannot eliminate a possible arm.
                self.assert_rejected(raw + "488b4010c3", symbols=self.context_ranges())

    def test_conditional_move_domains_preserve_alias_semantics(self):
        from miasm.expression.expression import ExprInt
        from test_jit_diagnostics import decode

        rax, rcx, rdx = (ExprId(name, 64) for name in ("RAX", "RCX", "RDX"))
        for raw, expected in (
            ("480f44c1", {0x100002FF8, 0x2EE0}),
            ("0f44c1", {0x2FF8, 0x2EE0}),
            ("660f44c1", {0x100002FF8, 0x100002EE0}),
        ):
            with self.subTest(raw=raw):
                tracker = context_policy.FlowConstants()
                tracker.values = {
                    rax: frozenset({ExprInt(0x100002FF8, 64)}),
                    rcx: frozenset({ExprInt(0x2EE0, 64)}),
                    rdx: frozenset({ExprInt(0x1234, 64)}),
                }
                tracker.update(decode(raw))
                self.assertEqual(
                    tracker.values[rax], frozenset(ExprInt(v, 64) for v in expected)
                )
                self.assertEqual(tracker.values[rdx], frozenset({ExprInt(0x1234, 64)}))

    def test_conditional_move_safe_and_overwritten_values_remain_admitted(self):
        for raw in (
            "48b8f81f000000000000480f44c1488b4010c3",  # Known alternative is safe.
            "48b8f82f000001000000660f44c1488b4010c3",  # AX retains high bits.
            "48b8f82f000000000000480f44c131c0488b4010c3",  # Exact overwrite.
            "48b8f82f000000000000480f44c1e8ed4f0000488b4010c3",  # CALL clears facts.
        ):
            with self.subTest(raw=raw):
                _, _, status = render(
                    raw, symbols=self.context_ranges(), return_status=True
                )
                self.assertEqual(status, 0)

    def test_conditional_move_widening_cannot_erase_address_uncertainty(self):
        from test_jit_diagnostics import decode

        tracker = context_policy.FlowConstants()
        tracker.update(decode("b8f82f0000"))
        tracker.update(decode("b9f81f0000"))
        with patch.object(tracker, "MAX_VALUES", 1):
            tracker.update(decode("480f44c1"))
        with self.assertRaises(context_policy.ContextFlowLimit):
            tracker.resolve_many(ExprId("RAX", 64))
        tracker.update(decode("31c0"))
        self.assertEqual(int(tracker.resolve_many(ExprId("RAX", 64))[0]), 0)

    def test_conditional_move_unrecognized_ir_refuses_admission(self):
        from miasm.ir.ir import AssignBlock
        from test_jit_diagnostics import decode

        tracker = context_policy.FlowConstants()
        with (
            patch.object(tracker.lifter, "instr2ir", side_effect=NotImplementedError),
            self.assertRaises(context_policy.ContextFlowLimit),
        ):
            tracker.update(decode("480f44c1"))
        assignments, extra = tracker.lifter.instr2ir(decode("480f44c1"))
        unconditional = dict(assignments)
        unconditional[tracker.lifter.IRDst] = extra[0].dst
        for result in (
            (assignments, []),
            (assignments, extra * 2),
            (AssignBlock(unconditional), extra),
        ):
            tracker = context_policy.FlowConstants()
            with (
                patch.object(tracker.lifter, "instr2ir", return_value=result),
                self.assertRaises(context_policy.ContextFlowLimit),
            ):
                tracker.update(decode("480f44c1"))

    def test_unknown_predecessor_does_not_hide_sensitive_alternative(self):
        self.assert_rejected(
            "48b8f82f0000000000004885c97503488b074883c010488b00c3",
            symbols=self.context_ranges(),
        )
        # Do not prune a path using native flags: inserted code may clobber them.
        self.assert_rejected(
            "48b8f82f00000000000031c9750231c04883c010488b00c3",
            symbols=self.context_ranges(),
        )

    def test_internal_ir_shift_and_rotate_exits_preserve_addresses(self):
        for prefix, opcode in (
            (prefix, "d3" + operand)
            for prefix in ("48", "", "66")
            for operand in ("e0", "e8", "f8", "c0", "c8", "d0", "d8")
        ):
            with self.subTest(prefix=prefix, opcode=opcode):
                self.assert_rejected(
                    "48b8f82f000000000000" + prefix + opcode + "488b7810c3",
                    symbols=self.context_ranges(),
                )
        for opcode in ("48d3e2", "48d3ca", "480fa5d0", "480fadd0", "d2e0"):
            with self.subTest(opcode=opcode):
                self.assert_rejected(
                    "48b8f82f000000000000" + opcode + "488b7810c3",
                    symbols=self.context_ranges(),
                )

    def test_internal_ir_taken_shift_can_construct_sensitive_address(self):
        for opcode in ("48d3e0", "48d3c0"):
            with self.subTest(opcode=opcode):
                self.assert_rejected(
                    "b8fc170000b901000000" + opcode + "488b7810c3",
                    symbols=self.context_ranges(),
                )

    def test_internal_ir_multiple_blocks_and_loop_keep_unaffected_registers(self):
        for opcode in ("480fb1cb", "480fbcc3", "480fbdc3", "f3a4"):
            with self.subTest(opcode=opcode):
                self.assert_rejected(
                    "48baf82f000000000000" + opcode + "488b7a10c3",
                    symbols=self.context_ranges(),
                )
        self.assert_rejected(
            "48bbf82f000000000000480fb1da488b7a10c3",
            symbols=self.context_ranges(),
        )

    def test_internal_ir_safe_and_overwritten_addresses_remain_admitted(self):
        for raw in (
            "b8f81f000048d3e2488b7810c3",
            "b8f82f000048d3e031c0488b7810c3",
            "b8f82f000048d3e0e8ee4f0000488b7810c3",
            "baf81f0000480fb1cb488b7a10c3",
            "baf81f0000f3a4488b7a10c3",
        ):
            with self.subTest(raw=raw):
                _, _, status = render(
                    raw, symbols=self.context_ranges(), return_status=True
                )
                self.assertEqual(status, 0)

    def test_internal_ir_work_and_graph_limits_refuse_at_instruction(self):
        for name, limit in (("MAX_IR_BLOCKS", 1), ("MAX_IR_VISITS", 1)):
            with (
                self.subTest(name=name),
                patch.object(context_policy.FlowConstants, name, limit, create=True),
            ):
                log = self.assert_rejected("9048d3e0c3")
                self.assertIn('rip="0x1001"', log)

    def test_internal_ir_temporary_survives_parallel_and_sequential_assignments(self):
        from miasm.expression.expression import ExprCond, ExprInt, ExprLoc
        from miasm.ir.ir import AssignBlock, IRBlock
        from test_jit_diagnostics import decode

        tracker = context_policy.FlowConstants()
        tracker.update(decode("b8f82f0000"))
        line = decode("48d3e0")
        db = tracker.lifter.loc_db
        taken = db.add_location()
        end = db.get_or_create_offset_location(line.offset + line.l)
        dst = tracker.lifter.IRDst
        target, finish = ExprLoc(taken, 64), ExprLoc(end, 64)
        rax, rdx = ExprId("RAX", 64), ExprId("RDX", 64)
        temp = ExprId("instruction_saved_address", 64)
        entry = AssignBlock({temp: rax, rax: ExprInt(0, 64), dst: target})
        block = IRBlock(
            db,
            taken,
            [
                AssignBlock({rdx: temp + ExprInt(16, 64)}),
                AssignBlock({dst: ExprCond(ExprId("zf", 1), finish, finish)}),
            ],
        )
        with patch.object(tracker.lifter, "instr2ir", return_value=(entry, [block])):
            tracker.update(line)
        self.assertEqual(tracker.values[rdx], frozenset({ExprInt(0x3008, 64)}))
        self.assertEqual(tracker.values[rax], frozenset({ExprInt(0, 64)}))
        self.assertNotIn(temp, tracker.values)

    def test_internal_ir_invalid_successors_cannot_silently_forget_facts(self):
        from miasm.expression.expression import ExprInt, ExprLoc
        from miasm.ir.ir import AssignBlock
        from test_jit_diagnostics import decode

        for kind in ("indirect", "integer", "dangling", "no_exit"):
            with self.subTest(kind=kind):
                tracker = context_policy.FlowConstants()
                line = decode("48d3e0")
                assignments, extra = tracker.lifter.instr2ir(line)
                destination = {
                    "indirect": ExprId("RAX", 64),
                    "integer": ExprInt(0xDEAD, 64),
                    "dangling": ExprLoc(tracker.lifter.loc_db.add_location(), 64),
                    "no_exit": ExprLoc(extra[0].loc_key, 64),
                }[kind]
                changed = dict(assignments)
                changed[tracker.lifter.IRDst] = destination
                if kind == "no_exit":
                    extra[0] = context_policy.IRBlock(
                        tracker.lifter.loc_db,
                        extra[0].loc_key,
                        [AssignBlock({tracker.lifter.IRDst: destination})],
                    )
                with (
                    patch.object(
                        tracker.lifter,
                        "instr2ir",
                        return_value=(AssignBlock(changed), extra),
                    ),
                    self.assertRaises(context_policy.ContextFlowLimit),
                ):
                    tracker.update(line)

    def test_flow_call_and_overwrite_kill_old_values(self):
        for raw in (
            "48b8f82f000000000000eb0031c04883c010488b00c3",
            "48b8f82f000000000000eb00e8ef4f00004883c010488b00c3",
        ):
            with self.subTest(raw=raw):
                _, _, status = render(
                    raw, symbols=self.context_ranges(), return_status=True
                )
                self.assertEqual(status, 0)

    def test_flow_loops_widen_without_erasing_address_uncertainty(self):
        with patch.object(context_policy.FlowConstants, "MAX_VALUES", 4):
            for raw in (
                "31c0eb00ffc083f80a75f9c3",  # Widened counter is not an address.
                "31c0eb00ffc083f80a75f931c0488b18c3",  # Exact overwrite after loop.
            ):
                _, _, status = render(raw, return_status=True)
                self.assertEqual(status, 0)
            log = self.assert_rejected("31c0ffc0488b1883f80a75f6c3")
            self.assertIn("bounded register-address alternatives", log)

    def test_flow_combination_limit_and_parallel_writes(self):
        from miasm.expression.expression import ExprInt, ExprMem
        from test_jit_diagnostics import decode

        tracker = context_policy.FlowConstants()
        rax, rbx = ExprId("RAX", 64), ExprId("RBX", 64)
        tracker.values = {
            rax: frozenset({ExprInt(0x2FF8, 64)}),
            rbx: frozenset({ExprInt(1, 64)}),
        }
        tracker.update(decode("4893"))
        self.assertEqual(tracker.resolve_many(rax), [ExprInt(1, 64)])
        self.assertEqual(tracker.resolve_many(rbx), [ExprInt(0x2FF8, 64)])
        tracker.values = {
            reg: frozenset({ExprInt(1, 64), ExprInt(2, 64)}) for reg in (rax, rbx)
        }
        with patch.object(tracker, "MAX_COMBINATIONS", 2):
            with self.assertRaises(context_policy.ContextFlowLimit):
                tracker.resolve_many(rax + rbx)
            tracker.update(decode("4831c0"))
            self.assertEqual(tracker.resolve_many(rax), [ExprInt(0, 64)])
        # Memory results are unknown values, not persistent symbolic aliases.
        tracker.update(decode("488b03"))
        self.assertNotIn(rax, tracker.values)
        self.assertIsInstance(tracker.resolve_many(ExprMem(rbx, 64))[0], ExprMem)

    def test_flow_work_limit_refuses_instead_of_publishing_partial_scan(self):
        walk = context_policy.constant_blocks
        with patch.object(
            context_policy,
            "constant_blocks",
            side_effect=lambda blocks, db, **kwargs: walk(
                blocks, db, max_visits=1, **kwargs
            ),
        ):
            log = self.assert_rejected("31c0eb0083c001c3")
        self.assertIn("CFG analysis exceeds its work budget", log)

    @staticmethod
    def masked_store_fixture(branch):
        # A known byte in an otherwise unknown word widens RCX, without an
        # unlocated store. Only a genuinely unknown index may taint [0x7000].
        prefix = "c604250060000001488b042500600000488b0c2500600000"
        store = "48890cc500200000"
        suffix = "488b3c2500700000488b17c3"
        return prefix + branch + store + suffix

    def test_masked_memory_store_keeps_precision_across_a_cfg_edge(self):
        raw = self.masked_store_fixture("83e003eb00")
        assembly, log, status = render(raw, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertTrue(assembly)
        self.assert_rejected(
            raw.replace("48890cc500200000", "48890cc5f02f0000"),
            symbols=self.context_ranges(),
        )

    def test_real_alternate_path_cannot_be_removed_by_root_initialization(self):
        for branch in (
            "85d2740383e003",  # One path bypasses the mask with a wide index.
            "85d2740583e003eb05b800020000",  # The other path selects [0x3000].
        ):
            with self.subTest(branch=branch):
                self.assert_rejected(
                    self.masked_store_fixture(branch), symbols=self.context_ranges()
                )

    def test_backedge_mask_does_not_introduce_a_new_entry(self):
        raw = self.masked_store_fixture("83e003")
        raw = raw.replace("48890cc500200000", "48890cc500200000ffc085d275ef")
        assembly, log, status = render(raw, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertTrue(assembly)

    @staticmethod
    def root_graph(caller="c3"):
        return translator.decode_regions(
            [
                (bytes.fromhex(caller), 0x1000, [0x1000]),
                (bytes.fromhex("c3"), 0x2000, [0x2000]),
            ],
            TEST_LOCK_SYMBOLS["_raw_spin_unlock"],
            set(TEST_LOCK_SYMBOLS.values()),
        )

    def test_explicit_cfg_roots_cover_all_selected_blocks(self):
        blocks, dbs = self.root_graph()
        with self.assertRaisesRegex(context_policy.ContextFlowLimit, "unreached"):
            list(context_policy.constant_blocks(blocks, dbs, roots={0x1000}))
        seen = {
            start
            for start, _, _ in context_policy.constant_blocks(
                blocks, dbs, roots={0x1000, 0x2000}
            )
        }
        self.assertEqual(seen, set(blocks))
        for roots in (set(), {0x3000}):
            with (
                self.subTest(roots=roots),
                self.assertRaisesRegex(
                    context_policy.ContextFlowLimit, "CFG analysis roots"
                ),
            ):
                list(context_policy.constant_blocks(blocks, dbs, roots=roots))
        self.assertEqual(list(context_policy.constant_blocks({}, {}, roots=set())), [])
        with self.assertRaisesRegex(
            context_policy.ContextFlowLimit, "CFG analysis roots"
        ):
            list(context_policy.constant_blocks({}, {}, roots={0x1000}))

    def test_direct_callees_remain_independent_analysis_roots(self):
        blocks, dbs = self.root_graph("e8fb0f0000c3")
        seen = set()
        for start, block, tracker in context_policy.constant_blocks(
            blocks,
            dbs,
            roots={0x1000},
            control_targets=set(TEST_LOCK_SYMBOLS.values()),
        ):
            seen.add(start)
            for line in block.lines:
                tracker.update(line)
        self.assertEqual(seen, set(blocks))

    def test_call_packet_precedes_clobber_and_keeps_return_slot_write(self):
        from miasm.expression.expression import ExprInt, ExprMem
        from test_jit_diagnostics import decode

        tracker = context_policy.FlowConstants()
        rdi = ExprId("RDI", 64)
        tracker.update(decode("bff82f0000"))
        call = decode("e800100000")
        tracker.update(call)
        packet = tracker.call_entries[id(call)]
        self.assertEqual(packet[0][rdi], frozenset({ExprInt(0x2FF8, 64)}))
        slot = ExprMem(tracker.memory.offset(ExprId("kd_entry_RSP", 64), -8), 64)
        self.assertEqual(packet[2][2][slot], frozenset({5}))
        self.assertNotIn(rdi, tracker.values)
        self.assertFalse(tracker.memory.words)

    def test_known_call_inputs_join_unknown_roots_without_equal_origins(self):
        from miasm.expression.expression import ExprInt

        blocks, dbs = self.root_graph("bff8220000e8f60f0000c3")
        rdi = ExprId("RDI", 64)
        observations = []
        for start, block, tracker in context_policy.constant_blocks(
            blocks, dbs, roots={0x1000}
        ):
            if start == 0x2000:
                observations.append(tracker.values.get(rdi, tracker.UNKNOWN))
                self.assertNotIn(rdi, tracker.origins)
            for line in block.lines:
                tracker.update(line)
        self.assertTrue(any(ExprInt(0x22F8, 64) in state for state in observations))
        self.assertTrue(all(None in state for state in observations))

    def test_nested_decoded_call_arguments_and_returns_remain_visible(self):
        def call(target, start):
            return b"\xe8" + struct.pack("<i", target - start - 5)

        for kind in ("argument", "return"):
            for clear in (False, True):
                with self.subTest(kind=kind, clear=clear):
                    caller = bytes.fromhex("bff82f0000") if kind == "argument" else b""
                    caller += call(0x2000, 0x1000 + len(caller))
                    if kind == "return":
                        caller += bytes.fromhex("488d701048ad")
                    caller += b"\xc3"
                    if kind == "argument":
                        leaf = ("31ff" if clear else "") + "4883c710488b07c3"
                    else:
                        leaf = "31c0c3" if clear else "b8f82f0000c3"
                    assembly, log, status = render(
                        "",
                        regions=[
                            (caller, 0x1000, [0x1000]),
                            (call(0x4000, 0x2000) + b"\xc3", 0x2000, [0x2000]),
                            (bytes.fromhex(leaf), 0x4000, [0x4000]),
                        ],
                        # Keep data addresses distinct from the decoded leaf.
                        symbols=context_policy.ContextSymbols(
                            {0x3008: "percpu_fixture"}, {0x3008: 0x3100}
                        ),
                        return_status=True,
                    )
                    self.assertEqual(status, 0 if clear else 2, log)
                    self.assertEqual(bool(assembly), clear)

    def test_decoded_return_memory_effects_reach_the_caller(self):
        from miasm.expression.expression import ExprInt

        blocks, dbs = translator.decode_regions(
            [
                (bytes.fromhex("e8fb0f0000c3"), 0x1000, [0x1000]),
                (bytes.fromhex("48c7042500840000f82f0000c3"), 0x2000, [0x2000]),
            ],
            TEST_LOCK_SYMBOLS["_raw_spin_unlock"],
            set(TEST_LOCK_SYMBOLS.values()),
        )
        observed = []
        for start, block, tracker in context_policy.constant_blocks(
            blocks, dbs, roots={0x1000}
        ):
            if start == 0x1005:
                observed.append(tracker.memory.byte_at(ExprInt(0x8400, 64)))
            for line in block.lines:
                tracker.update(line)
        self.assertTrue(any(state and ExprInt(0xF8, 8) in state for state in observed))

    def test_return_ownership_handles_shared_tails_and_nested_calls(self):
        from types import SimpleNamespace

        kinds = {1: "CALL", 2: "RET", 3: "RET", 4: "JMP", 5: "RET", 6: "RET"}
        blocks = {
            start: SimpleNamespace(lines=[SimpleNamespace(name=name)])
            for start, name in kinds.items()
        }
        successors = {1: {2}, 2: set(), 3: set(), 4: {2}, 5: set(), 6: set()}
        calls = {0: [(None, 1, 5), (None, 4, 6)], 1: [(None, 3, 2)]}
        returns = context_policy.call_return_edges(blocks, successors, calls, 100)
        self.assertEqual(dict(returns), {2: {5, 6}, 3: {2}})
        with self.assertRaisesRegex(context_policy.ContextFlowLimit, "CALL/RET CFG"):
            context_policy.call_return_edges(blocks, successors, calls, 1)

    def test_missing_decoded_call_packet_is_not_partial_success(self):
        with patch.object(context_policy.FlowConstants, "update"):
            log = self.assert_rejected(
                "",
                regions=[
                    (bytes.fromhex("e8fb0f0000c3"), 0x1000, [0x1000]),
                    (bytes.fromhex("c3"), 0x2000, [0x2000]),
                ],
            )
        self.assertIn("missing decoded CALL input state", log)

    def test_return_fanout_has_an_edge_budget(self):
        from types import SimpleNamespace

        blocks = {
            start: SimpleNamespace(lines=[SimpleNamespace(name="RET")])
            for start in range(1, 11)
        }
        successors = {start: set() for start in blocks}
        calls = {0: [(None, 1, target) for target in range(2, 11)]}
        with self.assertRaisesRegex(context_policy.ContextFlowLimit, "CALL/RET CFG"):
            context_policy.call_return_edges(blocks, successors, calls, 9)
        self.assertEqual(
            dict(context_policy.call_return_edges(blocks, successors, calls, 10)),
            {1: set(range(2, 11))},
        )

    def test_missing_cfg_database_is_not_partial_success(self):
        blocks, _ = self.root_graph()
        with self.assertRaisesRegex(
            context_policy.ContextFlowLimit, "location database"
        ):
            list(context_policy.constant_blocks(blocks, {}, roots=set(blocks)))

    @staticmethod
    def context_ranges():
        # Deliberately unsorted, with an ordinary alias at the sensitive start.
        contents = (
            "3100 D ordinary_data\n"
            "3000 D __per_cpu_offset\n"
            "3000 D offset_alias\n"
            "4100 T ordinary_function\n"
            "4000 T __schedule.isra.0\n"
            "5000 T module_context_end [fixture]\n"
            "4800 T schedule_module [fixture]\n"
        )
        with patch("builtins.open", mock_open(read_data=contents)):
            return context_policy.load_context_symbols()

    def test_context_data_interior_addresses_refuse_before_codegen(self):
        for raw in (
            "488b0501200000c3",  # MOV RAX, [RIP + __per_cpu_offset + 8]
            "488d0501200000c3",  # LEA RAX, [RIP + __per_cpu_offset + 8]
            "48c7c008300000c3",  # MOV RAX, __per_cpu_offset + 8
            "488905f8200000c3",  # Last byte before the next symbol.
        ):
            with self.subTest(raw=raw):
                log = self.assert_rejected(raw, symbols=self.context_ranges())
                self.assertIn("__per_cpu_offset", log)

    def test_context_function_interior_call_and_tail_call_refuse(self):
        for opcode in ("e8", "e9"):
            log = self.assert_rejected(
                opcode + "03300000c3", symbols=self.context_ranges()
            )
            self.assertIn("__schedule.isra.0", log)

    def test_indexed_context_base_remains_visible_without_a_static_address(self):
        for raw in (
            "488b04c500300000c3",  # MOV RAX, [RAX*8 + __per_cpu_offset]
            "488b04c508300000c3",  # Same, with an interior displacement.
            "488d84c300300000c3",  # LEA RAX, [RBX + RAX*8 + base]
            "ff14c500300000c3",  # Indirect CALL through the known data.
        ):
            with self.subTest(raw=raw):
                self.assertIn(
                    "__per_cpu_offset",
                    self.assert_rejected(raw, symbols=self.context_ranges()),
                )

    def test_memory_span_overlapping_context_symbol_refuses_before_codegen(self):
        for raw in (
            "488b05f51f0000c3",  # MOV RAX, [0x2ffc]: last four bytes in table.
            "488905f51f0000c3",  # MOV [0x2ffc], RAX.
            "48ff05f51f0000c3",  # INC QWORD PTR [0x2ffc].
            "0fb705f81f0000c3",  # MOVZX EAX, WORD PTR [0x2fff].
            "488b04c5fc2f0000c3",  # Visible indexed base also overlaps.
            "ff15f61f0000c3",  # Indirect CALL through [0x2ffc].
        ):
            with self.subTest(raw=raw):
                self.assertIn(
                    "__per_cpu_offset",
                    self.assert_rejected(raw, symbols=self.context_ranges()),
                )

    def test_memory_width_and_address_only_operands_have_distinct_boundaries(self):
        for raw in (
            "488b05f11f0000c3",  # Eight bytes ending immediately before table.
            "8b05f61f0000c3",  # Four bytes at 0x2ffc, not eight.
            "0fb605f81f0000c3",  # One byte at 0x2fff, not destination width.
            "488d05f51f0000c3",  # LEA of 0x2ffc does not read eight bytes.
            "48c7c0fc2f0000c3",  # Taking the address alone is not a read.
        ):
            with self.subTest(raw=raw):
                assembly, _, status = render(
                    raw, symbols=self.context_ranges(), return_status=True
                )
                self.assertEqual(status, 0)
                self.assertTrue(assembly)

    def test_overlap_does_not_require_a_known_symbol_end(self):
        with patch("builtins.open", mock_open(read_data="3000 D __per_cpu_offset\n")):
            symbols = context_policy.load_context_symbols()
        for table in (symbols, dict(symbols)):
            with self.subTest(table=type(table).__name__):
                self.assert_rejected("488b05f51f0000c3", symbols=table)
        self.assertIsNone(symbols.resolve(0x2FF8, 8))
        self.assertEqual(symbols.resolve(0x2FF9, 8), "__per_cpu_offset")
        self.assertIsNone(symbols.resolve(0x3001, 8))

    def test_adjacent_symbols_and_unrelated_indices_still_admitted(self):
        for raw in (
            "488b05f9200000c3",  # First address of ordinary_data.
            "e8fb300000c3",  # First address of ordinary_function.
            "488b04c500310000c3",
            "488b04c5f82f0000c3",  # Full operand before the sensitive range.
        ):
            with self.subTest(raw=raw):
                assembly, _, status = render(
                    raw, symbols=self.context_ranges(), return_status=True
                )
                self.assertEqual(status, 0)
                self.assertTrue(assembly)

    def test_ranges_respect_aliases_module_owners_and_unknown_upper_bounds(self):
        symbols = self.context_ranges()
        self.assertEqual(symbols.resolve(0x3008), "__per_cpu_offset")
        self.assertIsNone(symbols.resolve(0x3100))
        self.assertEqual(symbols.resolve(0x4808), "schedule_module")
        self.assertIsNone(symbols.resolve(0x5000))
        contents = (
            "3000 T schedule [first]\n"
            "3100 T ordinary_function [second]\n"
            "4000 T rcu_read_lock\n"
            "4200 T ordinary_core\n"
            "4100 T unrelated [second]\n"
        )
        with patch("builtins.open", mock_open(read_data=contents)):
            symbols = context_policy.load_context_symbols()
        self.assertEqual(symbols.resolve(0x3000), "schedule")
        self.assertIsNone(symbols.resolve(0x3001))
        self.assertIsNone(symbols.resolve(0x3100))
        self.assertEqual(symbols.resolve(0x4100), "rcu_read_lock")
        self.assertIsNone(symbols.resolve(0x4200))

    def test_late_callee_context_interior_rejects_whole_entry(self):
        raw = "e8fb0f0000c3"
        self.assertEqual(render(raw, return_status=True)[2], 0)
        log = self.assert_rejected(
            raw,
            regions=[
                (bytes.fromhex(raw), 0x1000, [0x1000]),
                (bytes.fromhex("488b0501100000c3"), 0x2000, [0x2000]),
            ],
            symbols=self.context_ranges(),
        )
        self.assertIn('entry="0x1000"', log)
        self.assertIn('rip="0x2000"', log)

    def test_context_interior_after_outer_unlock_is_outside_cs(self):
        assembly, _, status = render(
            "e8fb4f0000488b05fc1f0000c3",
            kernel_symbols={"_raw_spin_unlock": 0x6000},
            symbols=self.context_ranges(),
            return_status=True,
        )
        self.assertEqual(status, 0)
        self.assertNotIn(b"loc_1005:", assembly)

    def test_unknown_calls_keep_dynamic_completion(self):
        for raw in ("e8fb0f0000c3", "ffd0c3"):
            assembly, _, status = render(raw, return_status=True)
            self.assertEqual(status, 0)
            self.assertTrue(assembly)

    def test_mixed_spin_mutex_calls_are_not_admitted(self):
        self.assert_rejected(
            "e8fb2f0000e8f61f0000c3",
            kernel_symbols={"_raw_spin_lock": 0x4000, "mutex_unlock": 0x3000},
        )

    def test_foreign_lock_references_need_no_visible_outer_unlock(self):
        for kind, symbol in (("spin", "mutex_lock"), ("mutex", "_raw_spin_lock")):
            for raw in ("e8fb1f0000c3", "e9fb1f0000", "48c7c000300000c3"):
                with self.subTest(kind=kind, raw=raw):
                    log = self.assert_rejected(
                        raw, lock_kind=kind, kernel_symbols={symbol: 0x3000}
                    )
                    self.assertIn(symbol, log)
                    self.assertIn(f"in {kind} entry", log)

    def test_matching_lock_backends_still_admitted(self):
        for kind, symbol in (("spin", "_raw_spin_lock"), ("mutex", "mutex_lock")):
            assembly, _, status = render(
                "e8fb1f0000c3",
                lock_kind=kind,
                kernel_symbols={symbol: 0x3000},
                return_status=True,
            )
            self.assertEqual(status, 0)
            self.assertTrue(assembly)

    def test_lexical_lock_capacity_boundary(self):
        symbols = {"mutex_lock": 0x3000}
        assembly, _, status = render(
            self.mutex_calls(0x1000, 7).hex(),
            lock_kind="mutex",
            kernel_symbols=symbols,
            return_status=True,
        )
        self.assertEqual(status, 0)
        self.assertTrue(assembly)
        log = self.assert_rejected(
            self.mutex_calls(0x1000, 8).hex(),
            lock_kind="mutex",
            kernel_symbols=symbols,
        )
        self.assertIn("excessive lexical lock nesting", log)

    def test_callee_depth_needs_the_runtime_capacity_guard(self):
        # Callees are scanned with unknown entry depth. Admission here is not
        # evidence that A plus these eight acquisitions fits a runtime frame.
        regions = [
            (bytes.fromhex("e8fb0f0000c3"), 0x1000, [0x1000]),
            (self.mutex_calls(0x2000, 8), 0x2000, [0x2000]),
        ]
        assembly, _, status = render(
            "",
            regions=regions,
            lock_kind="mutex",
            kernel_symbols={"mutex_lock": 0x3000},
            return_status=True,
        )
        self.assertEqual(status, 0)
        self.assertIn(b"loc_2000:", assembly)

    def test_unknown_entry_kind_is_not_guessed(self):
        for kind in ("unknown", "", "invalid"):
            self.assertIn(
                "entry lock kind", self.assert_rejected("90c3", lock_kind=kind)
            )

    def test_foreign_backend_in_late_callee_rejects_entry(self):
        self.assertEqual(render("e8fb0f0000c3", return_status=True)[2], 0)
        regions = [
            (bytes.fromhex("e8fb0f0000c3"), 0x1000, [0x1000]),
            (bytes.fromhex("e8fb0f0000c3"), 0x2000, [0x2000]),
        ]
        log = self.assert_rejected(
            "", regions=regions, kernel_symbols={"mutex_lock": 0x3000}
        )
        self.assertIn('rip="0x2000"', log)

    def test_foreign_backend_after_outer_unlock_is_outside_cs(self):
        assembly, _, status = render(
            "e8fb1f0000e8f62f0000c3",
            kernel_symbols={"_raw_spin_unlock": 0x3000, "mutex_lock": 0x4000},
            return_status=True,
        )
        self.assertEqual(status, 0)
        self.assertNotIn(b"loc_1005:", assembly)

    def test_post_outer_unlock_gs_is_outside_the_translation(self):
        assembly, _, status = render(
            "e8fb1f000065488b042528000000c3",
            kernel_symbols={"_raw_spin_unlock": 0x3000},
            return_status=True,
        )
        self.assertEqual(status, 0)
        self.assertNotIn(b"GS:[", assembly)
        self.assertNotIn(b"Stack_RGS", assembly)

    def test_nested_unlock_does_not_hide_gs_in_parent(self):
        self.assert_rejected(
            "e8fb2f0000e8f61f000065488b042528000000c3",
            kernel_symbols={"_raw_spin_lock": 0x4000, "_raw_spin_unlock": 0x3000},
        )

    def test_callee_scan_does_not_assume_outer_unlock(self):
        regions = [
            (bytes.fromhex("e8fb0f0000c3"), 0x1000, [0x1000]),
            (bytes.fromhex("e8fb0f000065488b042528000000c3"), 0x2000, [0x2000]),
        ]
        self.assert_rejected(
            "", regions=regions, kernel_symbols={"_raw_spin_unlock": 0x3000}
        )

    def test_new_callee_rejects_the_whole_entry(self):
        raw = "e8fb0f0000c3"
        self.assertEqual(render(raw, return_status=True)[2], 0)
        regions = [
            (bytes.fromhex(raw), 0x1000, [0x1000]),
            (bytes.fromhex("65488b042528000000c3"), 0x2000, [0x2000]),
        ]
        log = self.assert_rejected(raw, regions=regions)
        self.assertIn('entry="0x1000"', log)
        self.assertIn('rip="0x2000"', log)

    def test_plain_code_and_segmented_nop_still_admitted(self):
        for raw in ("488b034801d8c3", "650f1f00c3"):
            self.assertEqual(render(raw, return_status=True)[2], 0)

    def test_rejection_removes_only_stale_generated_images(self):
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as temp:
            os.chdir(temp)
            try:
                Path("asm").mkdir()
                for name in (
                    "jit.S",
                    "jit.o",
                    "jit.bin",
                    "bin.txt",
                    "callee_table.txt",
                ):
                    Path("asm", name).write_text("old image", encoding="ascii")
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(translator.reject_translation("fixture"), 2)
                self.assertEqual(
                    [p.name for p in Path("asm").iterdir()], ["callee_table.txt"]
                )
            finally:
                os.chdir(previous)

    def test_symbol_families_and_compiler_clones(self):
        for name in (
            "__schedule.isra.0",
            "rcu_read_unlock",
            "synchronize_rcu_expedited",
            "local_bh_enable",
            "migrate_disable",
            "__per_cpu_offset",
        ):
            self.assertTrue(context_policy.is_context_symbol(name), name)
        for name in (
            "mutex_lock",
            "_raw_spin_unlock",
            "ktime_get",
            "kd_resume_native_probe",
        ):
            self.assertFalse(context_policy.is_context_symbol(name), name)
        # The faster matcher must retain every old glob's anchors, case and
        # compiler-clone treatment. Near misses matter as much as refusals;
        # do not add a time threshold or relax admission to make profiling pass.
        candidates = {"", ".isra.0", "schedule\n", "SCHEDULE", "get_current_taskx"}
        for pattern in context_policy.CONTEXT_SYMBOLS:
            for wildcard in ("", "x", "_irq", "rcu", "[x]", "?", "\n"):
                name = pattern.replace("*", wildcard)
                for prefix in ("", "x", "_"):
                    for suffix in ("", "x", ".isra.0", ".constprop.2", "\n"):
                        candidates.add(prefix + name + suffix)
                candidates.add(name.upper())
        for name in sorted(candidates):
            expected = any(
                fnmatchcase(name.split(".", 1)[0], pattern)
                for pattern in context_policy.CONTEXT_SYMBOLS
            )
            self.assertEqual(context_policy.is_context_symbol(name), expected, name)
        with (
            patch("builtins.open", side_effect=OSError("unavailable")),
            self.assertRaises(OSError),
        ):
            context_policy.load_context_symbols()


class JitPhaseTests(unittest.TestCase):
    """Guard the boundary between emitted JIT and waiter-only continuation."""

    GS = bytes.fromhex("65488b042528000000c3")

    @staticmethod
    def call(target, offset=0x1000):
        return b"\xe8" + struct.pack("<i", target - offset - 5)

    def test_missing_direct_call_ends_episode_before_context_suffix(self):
        assembly, log, status = render(
            (self.call(0x5000) + self.GS).hex(), return_status=True
        )
        self.assertEqual(status, 0, log)
        self.assertIn(b"loc_5000:", assembly)
        self.assertNotIn(b"loc_1005:", assembly)
        self.assertNotIn(b"GS:", assembly)

    def test_alternate_jit_branch_still_checks_same_suffix(self):
        # JNZ skips the terminal CALL and reaches the otherwise native suffix.
        raw = bytes.fromhex("7505") + self.call(0x5000, 0x1002) + self.GS
        assembly, log, status = render(raw.hex(), return_status=True)
        self.assertEqual(status, 2, log)
        self.assertFalse(assembly)

    def test_native_edge_does_not_pollute_alternate_live_successor(self):
        # Return-address bytes must not flow out of the native exit
        # into a suffix reached only by the branch that never executes CALL.
        raw = bytes.fromhex("7505") + self.call(0x5000, 0x1002)
        raw += bytes.fromhex("488b4424f8488b00c3")
        assembly, log, status = render(raw.hex(), return_status=True)
        self.assertEqual(status, 0, log)
        self.assertIn(b"loc_1007:", assembly)

    def test_control_and_hostcall_successors_remain_in_scope(self):
        for name in ("_raw_spin_lock", "ktime_get_ns"):
            with self.subTest(name=name):
                assembly, log, status = render(
                    (self.call(0x5000) + self.GS).hex(),
                    kernel_symbols={name: 0x5000},
                    return_status=True,
                )
                self.assertEqual(status, 2, log)
                self.assertFalse(assembly)

    def test_learned_callee_restores_return_scope_on_retranslation(self):
        raw = self.call(0x5000) + self.GS
        # A later version can return from this decoded callee. Admission must
        # reconsider the suffix instead of reusing the first version's verdict.
        assembly, log, status = render(
            "",
            regions=[(raw, 0x1000, [0x1000]), (b"\xc3", 0x5000, [0x5000])],
            return_status=True,
        )
        self.assertEqual(status, 2, log)
        self.assertFalse(assembly)

    def test_indirect_call_keeps_conservative_return_scope(self):
        assembly, log, status = render(
            (bytes.fromhex("ffd0") + self.GS).hex(), return_status=True
        )
        self.assertEqual(status, 2, log)
        self.assertFalse(assembly)

    def test_native_call_stack_write_is_still_checked(self):
        prefix = bytes.fromhex("48bc0830000000000000")
        assembly, log, status = render(
            (prefix + self.call(0x5000, 0x1000 + len(prefix)) + b"\xc3").hex(),
            symbols={0x3000: "__per_cpu_offset"},
            return_status=True,
        )
        self.assertEqual(status, 2, log)
        self.assertIn("IR memory access", log)
        self.assertFalse(assembly)


if __name__ == "__main__":
    unittest.main(verbosity=2)
