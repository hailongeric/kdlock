"""Assemble only the existing LoweredImage artifact for a reserved code address.

This is the explicit publisher-side GNU cpp/as/ld/objcopy path. Calling it runs
build tools and is allowed only in the designated VM build context. Importing the
module builds nothing. Paths, include roots, environment, fresh work directory,
file/diagnostic/code/metadata extents and total tool time are caller inputs.
Failed work is retained in that private directory; no input is overwritten.

The final ELF must be x86_64 little-endian ET_EXEC, with the exact entry at the
reserved page-aligned code base, one nonempty allocated .text and no unresolved
symbols, dynamic structures or remaining relocations. The provider receives the
extracted exact .text bytes plus flat metadata from the SAME artifact. Neither
assembly nor these checks establish source equivalence, a text lease, executable
publication or coverage acknowledgment.
"""

from dataclasses import dataclass
import math
import os
from pathlib import Path
import re
import resource
import selectors
import signal
import struct
import subprocess
import sys
import time

from .compiler import IndirectKind
from .coverage import EmissionOutcome
from .learning import LearningCandidate
from .source_decode import MASK64


_U64 = struct.Struct("<Q")
_ELF = struct.Struct("<16sHHIQQQIHHHHHH")
_SECTION = struct.Struct("<IIQQQQIIQQ")
_SYMBOL = struct.Struct("<IBBHQQ")
_PROGRAM = struct.Struct("<IIQQQQQQ")


@dataclass(frozen=True)
class Toolchain:
    cpp: str
    assembler: str
    linker: str
    objcopy: str
    include_directories: tuple[str, ...]
    environment: tuple[tuple[str, str], ...]
    work_directory: str
    page_size: int

    def __post_init__(self) -> None:
        for value in (self.cpp, self.assembler, self.linker, self.objcopy, self.work_directory):
            if not isinstance(value, str) or not Path(value).is_absolute():
                raise ValueError("build tools and fresh work directory need explicit absolute paths")
        if (not isinstance(self.include_directories, tuple)
                or not all(isinstance(p, str) and Path(p).is_absolute() for p in self.include_directories)):
            raise ValueError("include roots must be an explicit immutable tuple of absolute paths")
        if (not isinstance(self.environment, tuple)
                or not all(isinstance(p, tuple) and len(p) == 2
                           and all(isinstance(v, str) for v in p) for p in self.environment)
                or len({p[0] for p in self.environment}) != len(self.environment)):
            raise ValueError("tool environment must be explicit unique string pairs")
        if type(self.page_size) is not int or self.page_size <= 0 or self.page_size & (self.page_size - 1):
            raise ValueError("provider page size must be an explicit positive power of two")


@dataclass(frozen=True)
class BuildLimits:
    intermediate_bytes: int
    elf_bytes: int
    machine_bytes: int
    metadata_bytes: int
    diagnostic_bytes: int
    total_seconds: float

    def __post_init__(self) -> None:
        for value in (self.intermediate_bytes, self.elf_bytes, self.machine_bytes,
                      self.metadata_bytes, self.diagnostic_bytes):
            if type(value) is not int or not 0 <= value < sys.maxsize:
                raise ValueError("build extents must be explicit finite host-sized quantities")
        if (type(self.total_seconds) not in (int, float)
                or not math.isfinite(self.total_seconds) or self.total_seconds <= 0):
            raise ValueError("total build-tool time must be an explicit finite positive quantity")


@dataclass(frozen=True)
class ToolReceipt:
    command: tuple[str, ...]
    returncode: int
    diagnostics: bytes


class BuildFailure(RuntimeError):
    def __init__(self, reason: str, command: tuple[str, ...], diagnostics: bytes):
        self.reason = reason
        self.command = command
        self.diagnostics = diagnostics
        super().__init__(reason)


@dataclass(frozen=True)
class BuiltImage:
    code_base: int
    machine_code: bytes
    flat_metadata: bytes
    tools: tuple[ToolReceipt, ...]
    work_directory: str


def _words(values) -> bytes:
    if any(type(v) is not int or not 0 <= v <= MASK64 for v in values):
        raise ValueError("flat image metadata word exceeds the private ABI")
    return b"".join(_U64.pack(v) for v in values)


def flat_metadata(candidate: LearningCandidate, byte_limit: int) -> bytes:
    """Exact compiled_image ABI1 tables, without padding or pointer guesses."""
    artifact = candidate.artifact
    image = candidate.lowered
    outcomes = tuple(sorted(artifact.receipt.outcomes.items(),
                            key=lambda pair: (pair[0].site, pair[0].kind.value, pair[0].target)))
    size = (9 * _U64.size + len(artifact.source_version_bytes)
            + len(artifact.entry_sites) * _U64.size
            + sum(4 * _U64.size + len(site.raw) for site in artifact.source_sites)
            + len(outcomes) * 4 * _U64.size)
    if type(byte_limit) is not int or byte_limit < 0 or size > byte_limit:
        raise ValueError("flat metadata exceeds the explicit byte extent")
    kinds = {"KD_JIT_SITE_CALL": 0, "KD_JIT_SITE_JUMP": 1, "KD_JIT_SITE_OTHER": 2}
    emissions = {EmissionOutcome.EMITTED: 0, EmissionOutcome.SOURCE_NOT_EMITTED: 1,
                 EmissionOutcome.TARGET_NOT_EMITTED: 2, EmissionOutcome.DISPATCH_NOT_EMITTED: 3}
    chunks = [_words((1, image.abi_version, image.packet_size, image.io_size,
                      image.entry.current_task_gs_offset, len(artifact.entry_sites),
                      len(artifact.source_sites), len(outcomes), len(artifact.source_version_bytes))),
              artifact.source_version_bytes, _words(artifact.entry_sites)]
    for site in artifact.source_sites:
        chunks.extend((_words((site.ip, site.next_ip, kinds[site.kind], len(site.raw))), site.raw))
    for observed, outcome in outcomes:
        chunks.append(_words((observed.site, observed.target,
                              0 if observed.kind is IndirectKind.CALL else 1, emissions[outcome])))
    return b"".join(chunks)


def _read(path: Path, limit: int) -> bytes:
    if path.stat().st_size > limit:
        raise ValueError(f"{path.name} exceeds its explicit file-byte extent")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"{path.name} changed beyond its explicit file-byte extent")
    return data


def _table(data: bytes, offset: int, count: int, stride: int):
    if stride <= 0 or offset > len(data) or count > (len(data) - offset) // stride:
        raise ValueError("ELF table exceeds actual retained file bytes")
    return (offset + index * stride for index in range(count))


def _string(table: bytes, offset: int) -> bytes:
    if offset >= len(table):
        raise ValueError("ELF name lies outside its string table")
    end = table.find(b"\0", offset)
    if end < 0:
        raise ValueError("ELF name lacks a bounded terminating byte")
    return table[offset:end]


def _text_from_elf(data: bytes, base: int, capacity: int, entry: str) -> bytes:
    if len(data) < _ELF.size:
        raise ValueError("linked image has no complete ELF64 header")
    (ident, kind, machine, version, entry_ip, phoff, shoff, _flags, ehsize,
     phsize, phnum, shsize, shnum, shnames) = _ELF.unpack_from(data)
    if (ident[:7] != b"\x7fELF\x02\x01\x01" or kind != 2 or machine != 62 or version != 1
            or entry_ip != base or ehsize != _ELF.size or shsize != _SECTION.size
            or not shnum or shnames >= shnum or phnum == 0xFFFF
            or (phnum and phsize != _PROGRAM.size)):
        raise ValueError("linked image ELF target, exact entry or table layout differs")
    sections = tuple(_SECTION.unpack_from(data, offset)
                     for offset in _table(data, shoff, shnum, shsize))
    names_header = sections[shnames]
    if names_header[1] != 3:
        raise ValueError("linked image lacks its actual section-name string table")

    def contents(section):
        offset, size = section[4], section[5]
        if offset > len(data) or size > len(data) - offset:
            raise ValueError("ELF section exceeds actual retained bytes")
        return data[offset:offset + size]

    names = contents(names_header)
    text = None
    text_index = None
    for index, section in enumerate(sections):
        name = _string(names, section[0])
        section_kind, flags, address, size = section[1], section[2], section[3], section[5]
        if section_kind in (6, 11) or (section_kind in (4, 9) and size):
            raise ValueError("linked image retains dynamic data or relocations")
        if flags & 2:
            if (name != b".text" or text is not None or section_kind != 1
                    or flags & 1 or not flags & 4 or address != base or not 0 < size <= capacity):
                raise ValueError("linked image has extra allocated sections or an invalid exact .text")
            text, text_index = contents(section), index
    if text is None:
        raise ValueError("linked image has no nonempty allocated text")
    found_entry = False
    for section in sections:
        if section[1] != 2:
            continue
        if section[9] != _SYMBOL.size or section[5] % _SYMBOL.size or section[6] >= len(sections):
            raise ValueError("linked image symbol table has another layout")
        strings_header = sections[section[6]]
        if strings_header[1] != 3:
            raise ValueError("ELF symbols have no actual string table")
        strings, symbols = contents(strings_header), contents(section)
        for offset in range(0, len(symbols), _SYMBOL.size):
            name_offset, info, _other, symbol_section, value, size = _SYMBOL.unpack_from(symbols, offset)
            name = _string(strings, name_offset)
            if name and symbol_section == 0:
                raise ValueError("linked image retains an external unresolved symbol")
            if name == entry.encode("ascii", errors="strict"):
                if found_entry or symbol_section != text_index or value != base or not 0 < size <= len(text) or (info & 15) != 2:
                    raise ValueError("actual entry symbol is not the exact text-start function")
                found_entry = True
    if not found_entry:
        raise ValueError("linked image lacks the actual complete entry symbol")
    for offset in _table(data, phoff, phnum, phsize if phnum else _PROGRAM.size):
        program = _PROGRAM.unpack_from(data, offset)
        if program[0] in (2, 3) or (program[0] == 1 and program[1] & 2):
            raise ValueError("linked image needs dynamic loading or writable allocated segments")
    return text


class GNUImageBuilder:
    """Finite synchronous VM build operation in fresh private publisher storage.

    The caller supplies a process suitable for POSIX subprocess pre-exec resource
    setup and preserves source/toolchain/include identities. RLIMIT_FSIZE bounds
    each generated file; diagnostic pipes are read under their own exact bound.
    Total tool time covers all four tools. No shell or source binary is run.
    """

    def __init__(self, toolchain: Toolchain, limits: BuildLimits):
        if not isinstance(toolchain, Toolchain) or not isinstance(limits, BuildLimits):
            raise TypeError("builder needs explicit toolchain and all resource bounds")
        self.toolchain = toolchain
        self.limits = limits

    def _run(self, command: tuple[str, ...], directory: Path, deadline: float) -> ToolReceipt:
        limits = self.limits
        hard = resource.getrlimit(resource.RLIMIT_FSIZE)[1]
        if hard != resource.RLIM_INFINITY and limits.intermediate_bytes > hard:
            raise ValueError("requested file bound exceeds the inherited hard file limit")

        def file_bound():
            resource.setrlimit(resource.RLIMIT_FSIZE, (limits.intermediate_bytes, hard))

        process = subprocess.Popen(command, cwd=directory, env=dict(self.toolchain.environment),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   start_new_session=True, preexec_fn=file_bound)
        diagnostics = bytearray()
        selector = selectors.DefaultSelector()
        try:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise BuildFailure("explicit total build-tool time reached", command, bytes(diagnostics))
                events = selector.select(remaining)
                if not events:
                    raise BuildFailure("explicit total build-tool time reached", command, bytes(diagnostics))
                data = os.read(process.stdout.fileno(), limits.diagnostic_bytes - len(diagnostics) + 1)
                if not data:
                    selector.unregister(process.stdout)
                elif len(diagnostics) + len(data) > limits.diagnostic_bytes:
                    diagnostics.extend(data[:limits.diagnostic_bytes - len(diagnostics)])
                    raise BuildFailure("explicit diagnostic-byte limit reached", command, bytes(diagnostics))
                else:
                    diagnostics.extend(data)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BuildFailure("explicit total build-tool time reached", command, bytes(diagnostics))
            try:
                result = process.wait(timeout=remaining)
            except subprocess.TimeoutExpired as error:
                raise BuildFailure("explicit total build-tool time reached", command, bytes(diagnostics)) from error
            if result:
                raise BuildFailure(f"build tool returned {result}", command, bytes(diagnostics))
            return ToolReceipt(command, result, bytes(diagnostics))
        finally:
            selector.close()
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                # A failure to reap is an unresolved child, never a build pass.
                process.wait(timeout=limits.total_seconds)
            process.stdout.close()

    def build(self, candidate: LearningCandidate, code_base: int, code_capacity: int) -> BuiltImage:
        if not isinstance(candidate, LearningCandidate):
            raise TypeError("builder consumes only the existing exact learning candidate")
        tools, limits = self.toolchain, self.limits
        if (type(code_base) is not int or type(code_capacity) is not int
                or code_base <= 0 or code_capacity <= 0 or code_base > MASK64
                or code_base % tools.page_size or code_capacity % tools.page_size
                or code_capacity > MASK64 + 1 - code_base):
            raise ValueError("reserved code extent must be exact page-aligned nonwrapping storage")
        symbol = candidate.artifact.entry_symbol
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", symbol):
            raise ValueError("entry symbol cannot form an exact linker entry")
        source = candidate.artifact.assembly.encode("utf-8", errors="strict")
        metadata = flat_metadata(candidate, limits.metadata_bytes)
        if len(source) > limits.intermediate_bytes:
            raise ValueError("original assembly exceeds the explicit intermediate-file extent")
        directory = Path(tools.work_directory)
        directory.mkdir(parents=False, exist_ok=False)
        assembly, preprocessed = directory / "image.S", directory / "image.s"
        obj, elf, binary, script = (directory / name for name in ("image.o", "image.elf", "image.bin", "image.ld"))
        assembly.write_bytes(source)
        linker_script = (f"ENTRY({symbol})\nSECTIONS {{ .text 0x{code_base:x} : {{ *(.text) }} "
                         "/DISCARD/ : { *(.note.GNU-stack) } }\n").encode("ascii")
        if len(linker_script) > limits.intermediate_bytes:
            raise ValueError("linker description exceeds the explicit intermediate-file extent")
        script.write_bytes(linker_script)
        commands = (
            (tools.cpp, "-P", "-x", "assembler-with-cpp", "-D__ASSEMBLER__",
             *(part for include in tools.include_directories for part in ("-I", include)),
             str(assembly), "-o", str(preprocessed)),
            (tools.assembler, "--64", "-o", str(obj), str(preprocessed)),
            (tools.linker, "-m", "elf_x86_64", "--no-undefined", "-T", str(script), "-o", str(elf), str(obj)),
            (tools.objcopy, "-O", "binary", "--only-section=.text", str(elf), str(binary)),
        )
        deadline = time.monotonic() + limits.total_seconds
        receipts = []
        for index, command in enumerate(commands):
            receipts.append(self._run(command, directory, deadline))
            if index == 2:
                linked = _read(elf, min(limits.elf_bytes, limits.intermediate_bytes))
                text = _text_from_elf(linked, code_base, min(code_capacity, limits.machine_bytes), symbol)
        machine = _read(binary, min(code_capacity, limits.machine_bytes, limits.intermediate_bytes))
        if machine != text:
            raise ValueError("objcopy output differs from the validated exact linked text")
        return BuiltImage(code_base, machine, metadata, tuple(receipts), str(directory))
