"""Context admission symbols cases, collected only by test_context_policy."""
import contextlib
from fnmatch import fnmatchcase
import io
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, mock_open, patch
from test_jit_diagnostics import TEST_LOCK_SYMBOLS, render, translator
context_policy = translator.context_policy
from context_case_support import ContextCaseSupport


class ContextSymbolsCases(ContextCaseSupport):
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
                    translator.dis_assem(0, 0x1000, "spin", trusted_source=False)
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
                    translator.dis_assem(0, 0x1000, "spin", trusted_source=False)
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
                        translator.dis_assem(0, 0x1000, kind, trusted_source=False)
                loader.assert_not_called()
                read.assert_not_called()
                self.assertEqual(list(Path("asm").iterdir()), [])
            finally:
                os.chdir(previous)


    def test_control_symbol_failures_are_cli_errors_not_native_only_verdicts(self):
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
        # The trusted CLI still needs exact lock/control routing identities.
        # Context-sensitive symbol discovery is now checked-mode-only above.
        incomplete_locks = "".join(locks.splitlines(keepends=True)[:-1])
        for contents in ("", incomplete_locks):
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
            "kd_spin_lock_irqsave",
            "kd_spin_unlock_irqrestore",
            "__kd_spin_lock_irqsave",
            "__kd_spin_unlock_irqrestore",
            "kd_spin_lock_irq",
            "kd_spin_unlock_irq",
            "kd_spin_lock_bh",
            "kd_spin_unlock_bh",
            "__kd_spin_lock_bh",
            "__kd_spin_unlock_bh",
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
        for name in (
            "_raw_spin_lock_irqsave", "_raw_spin_unlock_bh",
            "__kd_spin_lock_irqsave", "__kd_spin_unlock_irqrestore",
            "kd_spin_lock_irq", "kd_spin_unlock_irq",
            "kd_spin_lock_bh", "kd_spin_unlock_bh",
        ):
            contents = f"9000 T schedule\n3000 T {name}\n"
            with patch("builtins.open", mock_open(read_data=contents)):
                symbols = context_policy.load_context_symbols()
            for raw in ("e8fb1f0000c3", "e9fb1f0000", "48c7c000300000c3"):
                with self.subTest(name=name, raw=raw):
                    log = self.assert_rejected(raw, symbols=symbols)
                    self.assertIn(name, log)
                    self.assertIn('rip="0x1000"', log)


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


    def test_symbol_families_and_compiler_clones(self):
        for name in (
            "__schedule.isra.0",
            "mutex_lock",
            "mutex_unlock",
            "__mutex_lock_slowpath",
            "atomic_dec_and_mutex_lock",
            "atomic_dec_and_mutex_lock.isra.0",
            "kd_down_read",
            "kd_up_write",
            "kd_downgrade_write",
            "kd_rwsem_init.constprop.0",
            "__init_rwsem",
            "down_read",
            "down_write_nested",
            "up_read_non_owner",
            "rwsem_wake.isra.0",
            "rcu_read_unlock",
            "synchronize_rcu_expedited",
            "local_bh_enable",
            "migrate_disable",
            "__per_cpu_offset",
        ):
            self.assertTrue(context_policy.is_context_symbol(name), name)
        for name in (
            "kd_mutex_local_lock",
            "kd_mutex_local_unlock",
            "_raw_spin_unlock",
            "kd_spin_lock_legacy",
            "kd_spin_unlock_legacy",
            "kd_spin_lock_clobber_v1",
            "kd_spin_unlock_clobber_v1",
            "kd_spin_lock_pinned_clobber_v1",
            "kd_spin_direct_native_unlock",
            "ktime_get",
            "kd_resume_native_probe",
            "down_reader",
            "down_readiness",
            "up_writer",
            "my_rwsem_helper",
            "up_threshold_show",
            "down_threshold_store",
            "net_rwsem",
            "pernet_ops_rwsem",
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

    def test_rwsem_apis_are_context_boundaries(self):
        names = (
            "init_rwsem", "__init_rwsem", "rwsem_is_locked", "rwsem_is_contended",
            "rwsem_mark_wake", "rwsem_spin_on_owner", "__rwsem_do_wake",
            "rwsem_down_read_slowpath", "rwsem_down_write_slowpath",
            "down_read", "down_read_interruptible", "down_read_killable",
            "down_read_trylock", "down_read_nested", "down_read_non_owner",
            "__down_read", "__down_read_trylock", "up_read", "up_read_non_owner",
            "__up_read", "down_write", "down_write_killable", "down_write_trylock",
            "down_write_nested", "down_write_killable_nested",
            "__down_write", "__down_write_killable", "up_write", "__up_write",
            "downgrade_write", "__downgrade_write",
            "percpu_init_rwsem", "__percpu_init_rwsem", "percpu_free_rwsem",
            "__percpu_down_read", "percpu_down_write", "percpu_up_read",
            "percpu_up_write", "__percpu_rwsem_trylock", "percpu_rwsem_wait",
            "percpu_rwsem_wake_function",
            "kd_rwsem_init", "kd_rwsem_is_idle",
            "kd_rwsem_delegate_enter", "kd_rwsem_delegate_exit",
            "kd_down_read", "kd_down_read_interruptible", "kd_down_read_killable",
            "kd_down_read_trylock", "kd_up_read", "kd_down_write",
            "kd_down_write_interruptible", "kd_down_write_killable",
            "kd_down_write_trylock", "kd_up_write", "kd_downgrade_write",
        )
        for name in names:
            for suffix in ("", ".isra.0"):
                symbol = name + suffix
                text = f"3000 T {symbol} [kdlock_km]\n3100 T ordinary [kdlock_km]\n"
                with patch("builtins.open", mock_open(read_data=text)):
                    symbols = context_policy.load_context_symbols()
                self.assertEqual(symbols.resolve(0x3008), symbol)
                for kind in ("spin", "mutex"):
                    # Reject both direct and interior tail calls before codegen;
                    # neither can become a CALL-miss helper or nested endpoint.
                    for raw in ("e8fb1f0000c3", "e903200000"):
                        with self.subTest(symbol=symbol, kind=kind, raw=raw):
                            log = self.assert_rejected(raw, lock_kind=kind, symbols=symbols)
                            self.assertIn(symbol, log)

    def test_late_helper_with_rwsem_rejects_enclosing_entry(self):
        caller = "e8fb0f0000c3"
        for kind in ("spin", "mutex"):
            for name in ("down_read_killable", "up_read_non_owner", "downgrade_write",
                         "rwsem_down_write_slowpath", "percpu_down_write",
                         "kd_down_write_killable"):
                with self.subTest(kind=kind, symbol=name):
                    log = self.assert_rejected(caller, lock_kind=kind,
                        regions=[(bytes.fromhex(caller), 0x1000, [0x1000]),
                                 (bytes.fromhex("e8fb0f0000c3"), 0x2000, [0x2000])],
                        symbols={0x3000: name})
                    self.assertIn('entry="0x1000"', log)
                    self.assertIn('rip="0x2000"', log)

    def test_rwsem_after_outer_unlock_is_outside_emitted_episode(self):
        assembly, log, status = render(
            "e8fb4f0000e8f61f0000c3",
            kernel_symbols={"_raw_spin_unlock": 0x6000},
            symbols={0x3000: "down_write"},
            return_status=True,
        )
        self.assertEqual(status, 0, log)
        self.assertNotIn(b"loc_1005:", assembly)
