"""Current runtime compilation; actual source CALL scanner reused from the fixture."""
import errno
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time

def command(arguments, timeout):
    result = subprocess.run(arguments, check=False, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=timeout,
                            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
    if result.returncode:
        raise RuntimeError(f"command failed {arguments!r}: {result.stdout.decode(errors='replace')}")
    return result.stdout


def symbol_size(module, symbol, nm, timeout):
    for line in command([nm, "-S", "--defined-only", str(module)], timeout).decode().splitlines():
        fields = line.split()
        if len(fields) == 4 and fields[3] == symbol:
            size = int(fields[1], 16)
            if not 0 < size <= 65536:
                raise ValueError(f"actual ELF size is outside fixture extent: {symbol}={size}")
            return size
    raise ValueError(f"actual module ELF has no sized symbol {symbol}")


def executable_elf_bytes(path, address, length):
    """Read an exact virtual span from one executable ELF64 load segment."""
    file_size = path.stat().st_size
    with path.open("rb") as source:
        raw = source.read(64)
        if len(raw) != 64:
            raise ValueError("kernel ELF header is truncated")
        header = struct.unpack("<16sHHIQQQIHHHHHH", raw)
        if (header[0][:6] != b"\x7fELF\x02\x01" or header[1:3] != (2, 62)
                or header[9] != 56 or not header[10]
                or header[5] + header[9] * header[10] > file_size):
            raise ValueError("kernel ELF executable load table differs")
        matches = []
        for index in range(header[10]):
            source.seek(header[5] + index * header[9])
            kind, flags, offset, virtual, _physical, extent, _memory, _alignment = struct.unpack(
                "<IIQQQQQQ", source.read(56))
            if kind == 1 and flags & 1 and virtual <= address and address + length <= virtual + extent:
                start = offset + address - virtual
                if start + length > file_size:
                    raise ValueError("kernel ELF source span exceeds its file")
                matches.append(start)
        if len(matches) != 1:
            raise ValueError("built-in source span lacks one exact executable ELF mapping")
        source.seek(matches[0])
        return source.read(length)


def scan_operation_calls(exported, objdump, directory, timeout):
    """Generic actual-byte CALL records, checked by the pinned source decoder.

    GNU disassembly supplies instruction starts even when a prefix before the
    first lock is outside the pinned decoder. Explicit printed prefixes remain
    part of the same instruction bytes and address. Every selected CALL is decoded
    at its ACTUAL source address and its target/length must agree. No opcode search,
    guessed wrapper length or application-specific lowering is used. Exported
    SPECIAL targets retain their native frontier before the CALL, using the
    same source-version-bound classifier as typed clobber entries.
    """
    from disassem.fragment import BoundaryKind, SourceCall
    from disassem.source_decode import SourceBytes, decode_source
    from disassem.source_boundaries import (
        BoundaryScanLimits, SourceEntryClass, SourceOperationTable,
        SourceOperationTarget, scan_source_boundaries,
    )

    api = {site.site: site.boundary for site in exported.snapshot.sites
           if site.boundary in (BoundaryKind.LOCK, BoundaryKind.UNLOCK, BoundaryKind.MODE_CHANGE,
                                BoundaryKind.QUERY, BoundaryKind.SPECIAL_INSTRUCTION)}
    calls, lock_roots, indirect = [], [], []
    prefixes = {"cs", "ds", "es", "fs", "gs", "ss", "data16", "addr32",
                "bnd", "notrack", "rep", "repe", "repz", "repne", "repnz"}
    rex_prefix = re.compile(r"rex(?:\.[WRXB]+)?")
    line_pattern = re.compile(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(\S+)(?:\s+(.*))?$")
    for index, region in enumerate(exported.snapshot.regions):
        binary = directory / f"source-{index}.bin"
        binary.write_bytes(region.data)
        listing = command([objdump, "-D", "-b", "binary", "-m", "i386:x86-64",
                           "--insn-width=16", f"--adjust-vma={region.start}", str(binary)], timeout)
        (directory / f"source-{index}.disassembly.txt").write_bytes(listing)
        for line in listing.decode("ascii", errors="strict").splitlines():
            match = line_pattern.match(line)
            if not match:
                continue
            words = [match[3], *(match[4].split() if match[4] else ())]
            # GNU may print an ordinary CALL as "cs cs cs call *%rax".
            # Skip only explicit prefix tokens, then require the CALL mnemonic;
            # a prefixed non-control instruction remains outside this scanner.
            while words and (words[0] in prefixes or rex_prefix.fullmatch(words[0])):
                words.pop(0)
            if not words or words[0] not in ("call", "callq"):
                continue
            site = int(match[1], 16)
            raw = bytes.fromhex(match[2])
            if not region.start <= site < region.end:
                raise ValueError("disassembler CALL escaped its exact supplied region")
            decoded = decode_source({site: SourceBytes(exported.snapshot.window(site))})
            record = decoded.instructions.get(site)
            node = decoded.graph.get(site)
            if (record is None or record.name.upper() != "CALL" or
                    not isinstance(node, SourceCall) or record.raw != raw or
                    node.return_site != record.next_site):
                raise ValueError(f"actual CALL has no matching pinned decode at {site:#x}")
            item = {"site": site, "length": record.length, "target": node.target,
                    "indirect": node.indirect, "raw_hex": record.raw.hex()}
            calls.append(item)
            if node.indirect:
                indirect.append(site)
            # The registered entry itself is authoritative. Its first CALL
            # is implementation code, not another W source operation/root.
            if site not in api and node.target in api:
                kind = api[node.target]
                # SPECIAL is a permanent native pre-operation frontier, not
                # a clobber operation or an observed ordinary callee.
                item["operation"] = "special" if kind is BoundaryKind.SPECIAL_INSTRUCTION else kind.value
                if kind is BoundaryKind.LOCK:
                    lock_roots.append(record.next_site)
    if not lock_roots:
        raise ValueError("no actual source CALL to the exported ordinary lock entry")
    # SOURCE already bounds regions/bytes/targets. Reuse the generic classifier
    # over this finite set of corroborated CALL starts, including coherent
    # overlapping regions, to retain conflicts and pre-CALL native semantics.
    call_sites = tuple(sorted({item["site"] for item in calls}))
    table = SourceOperationTable(exported.snapshot.version, tuple(
        SourceOperationTarget(address, kind,
            SourceEntryClass.NATIVE_LINUX if kind is BoundaryKind.SPECIAL_INSTRUCTION else SourceEntryClass.KD_CLOBBER,
            f"exported_target_{address:016x}")
        for address, kind in sorted(api.items())))
    classified = scan_source_boundaries(exported.snapshot, call_sites, table,
        BoundaryScanLimits(len(call_sites), 15 * len(call_sites), len(api)))
    return classified.snapshot, tuple(sorted(set(lock_roots))), tuple(calls), tuple(indirect)


class Compiler:
    """One finite source/export/publication/archive lifetime, outside timing."""

    def __init__(self, repo, output, gs_offset, builtin_start, builtin_bytes, writer_start):
        from disassem.session import FdTransport, SourceExportSession, ProducerCatalog
        from disassem.wire import WireLimits, SourceExportLimits
        from disassem.learning import LearningCoordinator, LearningLimits
        from protocol import DEVICE, BIND

        self.repo, self.output, self.gs_offset = Path(repo), Path(output), gs_offset
        self.output.mkdir()
        self.tools = {name: shutil.which(name) for name in ('objdump', 'cpp', 'as', 'ld', 'objcopy')}
        if not all(self.tools.values()):
            raise RuntimeError('required GNU tool absent')
        self.cycles, self.cycle_number, self.wire_bytes = [], 0, 0
        wire = self.output / 'wire'
        wire.mkdir()
        owner = self

        class Recorded(FdTransport):
            def _ioctl(self, flight):
                required = len(flight.request) + len(flight.output_buffer) + len(flight.header) + 4096
                if owner.wire_bytes + required > 256 * 1024 * 1024:
                    raise ValueError('wire evidence reservation exceeds the finite bound')
                owner.wire_bytes += required
                number = getattr(self, '_attempt', 0) + 1
                self._attempt = number
                directory = wire / f'{number:04d}'
                directory.mkdir()
                (directory / 'request.bin').write_bytes(flight.request)
                identity = dict(operation=int(flight.operation), sequence=flight.sequence,
                                output_capacity=len(flight.output_buffer))
                (directory / 'request.json').write_text(json.dumps(identity) + '\n')
                try:
                    result = super()._ioctl(flight)
                except BaseException as error:
                    (directory / 'observed-envelope.bin').write_bytes(bytes(flight.header))
                    (directory / 'observed-output.bin').write_bytes(bytes(flight.output_buffer))
                    (directory / 'error.txt').write_text(repr(error) + '\n')
                    raise
                (directory / 'returned-envelope.bin').write_bytes(bytes(flight.header))
                (directory / 'reply.bin').write_bytes(result.payload)
                (directory / 'result.json').write_text(json.dumps(dict(identity,
                    returned_sequence=result.sequence, status=result.status, reply_bytes=len(result.payload))) + '\n')
                return result

        self.limits = WireLimits(2 * 1024 * 1024, 4096, 256, 256, 512 * 1024)
        self.transport = Recorded.open('/dev/kd_nano_source', self.limits, 4 * 1024 * 1024 + 48)
        self.exported = self.drive(SourceExportSession(self.transport, SourceExportLimits(18, 64, 131072)))
        supplied = [r for r in self.exported.snapshot.regions
                    if r.start == builtin_start and r.data == builtin_bytes]
        if len(supplied) != 1:
            raise ValueError('retained return-thunk bytes differ from the pinned executable ELF')
        self.snapshot, roots, self.calls, indirect = scan_operation_calls(
            self.exported, self.tools['objdump'], self.output, 60)
        writers = [r for r in self.snapshot.regions if r.start == writer_start]
        if len(writers) != 1:
            raise ValueError('exact loaded writer symbol lacks one retained source region')
        writer = writers[0]
        writer_locks = [c for c in self.calls if c.get('operation') == 'lock'
                        and writer.start <= c['site'] < writer.end]
        writer_unlocks = [c for c in self.calls if c.get('operation') == 'unlock'
                          and writer.start <= c['site'] < writer.end]
        if len(writer_locks) != 1 or len(writer_unlocks) != 1:
            raise ValueError('writer must have exactly one actual lock CALL and one unlock CALL')
        self.entry = writer_locks[0]['site'] + writer_locks[0]['length']
        self.unlock = writer_unlocks[0]
        with open(DEVICE, 'rb', buffering=0) as device:
            fcntl.ioctl(device, BIND, struct.pack('=2Q', self.unlock['site'],
                                               self.unlock['site'] + self.unlock['length']))
        self.coordinator = LearningCoordinator(self.exported.epoch, self.snapshot,
            LearningLimits(4096, 32, 16, 16, 16))
        self.producers = ProducerCatalog(16, ())
        self.old = self.exported.expected_old_image_identity
        (self.output / 'source-export.bin').write_bytes(self.exported.raw_reply)
        self.metadata = dict(version=self.snapshot.version, entry=self.entry, calls=self.calls,
            indirect=indirect, unlock=self.unlock, gs_offset=gs_offset,
            regions=[dict(start=r.start, length=len(r.data)) for r in self.snapshot.regions],
            slot=self.exported.slot_identity, old=self.old)
        (self.output / 'source.json').write_text(json.dumps(self.metadata, indent=2) + '\n')

    @staticmethod
    def drive(workflow):
        from disassem.session import ChannelStatusError
        deadline = time.monotonic() + 120
        while workflow.phase.name != 'COMPLETE':
            try:
                workflow.advance()
            except ChannelStatusError as error:
                if error.status not in (-errno.EBUSY, -errno.EAGAIN):
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError('metadata wait ended; no drain is inferred') from error
                time.sleep(0.02)
        return workflow.result

    def cycle(self, *, force=False, claim_only=False):
        from disassem.compiler import DiscoveryLimits
        from disassem.image_builder import BuildLimits, GNUImageBuilder, Toolchain
        from disassem.learning import FactKey, MergeDisposition
        from disassem.lowering import CodegenLimits, EntryMetadata
        from disassem.session import FeedbackSession, SessionConfig, SessionPhase
        from disassem.wire import Operation, decode, token, token_word

        self.cycle_number += 1
        if self.cycle_number > 32:
            raise ValueError('finite cycle capacity exhausted before dispatch')
        directory = self.output / f'cycle-{self.cycle_number:02d}'
        directory.mkdir()
        builder = GNUImageBuilder(Toolchain(self.tools['cpp'], self.tools['as'], self.tools['ld'],
            self.tools['objcopy'], (str(self.repo / 'include'),), (('PATH', '/usr/bin:/bin'), ('LC_ALL', 'C')),
            str(directory / 'build'), os.sysconf('SC_PAGE_SIZE')),
            BuildLimits(2 * 1024 * 1024, 2 * 1024 * 1024, 128 * 1024, 256 * 1024, 256 * 1024, 120))
        session = FeedbackSession(self.transport, self.coordinator, self.producers, SessionConfig(
            self.exported.slot_identity, self.old, 0x1000 + self.cycle_number, 4096, self.entry,
            DiscoveryLimits(4096, 15 * 4096, 32768, 5),
            EntryMetadata('kd_nano_entry', tuple(sorted({c['site'] + c['length'] for c in self.calls
                if c.get('operation') in ('lock', 'unlock', 'mode_change', 'query')})), self.gs_offset),
            CodegenLimits(4096, 64 * 1024, 1000000)), builder)
        session.advance()
        session.advance()
        if session.phase is not SessionPhase.BUILD_START:
            raise AssertionError('claim did not reach the actual pre-build state')
        (directory / 'claim.bin').write_bytes(session.raw_reply)
        copied = decode(session.raw_reply, Operation.CLAIM, 3, 12, (self.limits.version_bytes,), self.limits)
        keys = {FactKey(self.exported.epoch.identity, token(row[0]), row[1]) for row in copied.rows}
        merged = any(s.recorded.fact.key in keys and s.recorded.merge is MergeDisposition.MERGED
                     for s in self.coordinator.facts())
        if claim_only or (not force and not merged):
            session.finish_pending()
        result = self.drive(session)
        if result.candidate is not None:
            artifact = result.candidate.artifact
            (directory / 'image.S').write_text(artifact.assembly)
            (directory / 'metadata.c').write_text(artifact.c_metadata)
            (directory / 'manifest.json').write_text(artifact.manifest_json)
            (directory / 'commit.bin').write_bytes(result.raw_commit)
            (directory / 'ack.bin').write_bytes(result.raw_ack)
            self.old = token_word(result.candidate.binding.image_identity)
        row = dict(claim_rows=len(result.claim.records), published=result.publication is not None,
                   acknowledged_keys=len(result.acknowledgment.keys) if result.acknowledgment else 0,
                   image=self.old)
        self.cycles.append(row)
        (directory / 'result.json').write_text(json.dumps(row, indent=2) + '\n')
        return row

    def close(self, module_sha256):
        from disassem.archive import ArchiveConfig, ShutdownSession
        archive = self.drive(ShutdownSession(self.transport, self.coordinator, self.producers,
            ArchiveConfig(0x2000, 4096, str(self.output / 'shutdown-archive.json'),
                          64 * 1024 * 1024, 0o600, (('module_sha256', module_sha256),
                          ('kernel_release', os.uname().release), ('evidence', 'nano-workload')))))
        self.transport.close()
        return dict(archive_sha256=archive.archive.identity.hex(), settled_keys=len(archive.settlement.keys),
                    compiler_cycles=self.cycles, source=self.metadata)


