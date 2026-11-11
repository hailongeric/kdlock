"""Exact source API boundaries over retained instruction bytes.

The caller supplies a source-version-bound target table from its actual provider
and linked symbols. Names are diagnostic labels, never classifiers. Private KD
clobber entries retain typed operation handling. Ordinary Linux callable entries
are permanent pre-operation native frontiers, including signal/try/result APIs
whose native-local implementation may use the same KD physical gate.

This helper composes compiler input before candidate construction. It neither
loads symbols/text nor establishes runtime binding, source retention, context or
publication. The original decoder, compiler, UB backend and GS lowering remain
unchanged. Supply all relevant instruction starts under explicit finite bounds;
scanning a subset does not prove that other source contains no lock operation.
"""

from dataclasses import dataclass
from enum import Enum

from .compiler import SourceSite, SourceSnapshot
from .fragment import BoundaryKind, SourceCall
from .source_decode import DecodedInstruction, DecodedSource, SourceBytes, decode_source


MASK64 = (1 << 64) - 1
OPERATION_KINDS = frozenset((BoundaryKind.LOCK, BoundaryKind.UNLOCK, BoundaryKind.MODE_CHANGE))


class SourceEntryClass(Enum):
    KD_CLOBBER = "kd_clobber"
    NATIVE_LINUX = "native_linux"


@dataclass(frozen=True)
class SourceOperationTarget:
    address: int
    kind: BoundaryKind
    entry_class: SourceEntryClass
    symbol: str

    def __post_init__(self) -> None:
        if type(self.address) is not int or not 0 <= self.address <= MASK64:
            raise ValueError("operation target needs an exact unsigned 64-bit address")
        if not isinstance(self.entry_class, SourceEntryClass):
            raise TypeError("operation target needs an explicit entry class")
        allowed = (OPERATION_KINDS if self.entry_class is SourceEntryClass.KD_CLOBBER
                   else frozenset((BoundaryKind.SPECIAL_INSTRUCTION,)))
        if self.kind not in allowed:
            raise ValueError("KD entries need typed kinds; native entries require SPECIAL")
        if not isinstance(self.symbol, str) or not self.symbol or "\x00" in self.symbol:
            raise ValueError("operation target needs its caller-supplied symbol label")

    @property
    def boundary(self) -> BoundaryKind:
        return self.kind


@dataclass(frozen=True)
class SourceOperationTable:
    source_version: str
    entries: tuple[SourceOperationTarget, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_version, str) or not self.source_version:
            raise ValueError("operation table needs the exact source version")
        if not isinstance(self.entries, tuple) or not all(
                isinstance(entry, SourceOperationTarget) for entry in self.entries):
            raise TypeError("operation table entries must be an immutable tuple")
        addresses = {}
        for entry in self.entries:
            previous = addresses.setdefault(entry.address, entry)
            if (previous.kind, previous.entry_class) != (entry.kind, entry.entry_class):
                raise ValueError("aliased operation targets disagree on kind or entry class")


@dataclass(frozen=True)
class BoundaryScanLimits:
    instruction_sites: int
    decode_window_bytes: int
    target_entries: int

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 0 for value in (
                self.instruction_sites, self.decode_window_bytes, self.target_entries)):
            raise ValueError("boundary scan bounds must be explicit nonnegative integers")


@dataclass(frozen=True)
class SourceOperationCall:
    instruction: DecodedInstruction
    target: SourceOperationTarget

    @property
    def site(self) -> int:
        return self.instruction.site

    @property
    def next_site(self) -> int:
        return self.instruction.next_site

    @property
    def raw(self) -> bytes:
        return self.instruction.raw


@dataclass(frozen=True)
class SourceBoundaryScan:
    snapshot: SourceSnapshot
    table: SourceOperationTable
    instruction_sites: tuple[int, ...]
    calls: tuple[SourceOperationCall, ...]
    decoded: DecodedSource
    decode_window_bytes: int


def scan_source_boundaries(
    snapshot: SourceSnapshot, instruction_sites: tuple[int, ...],
    table: SourceOperationTable, limits: BoundaryScanLimits,
) -> SourceBoundaryScan:
    """Retain exact direct CALL bytes and add permanent source cuts.

    Direct near CALLs are recognized through the existing decoder's SourceCall
    record, including original prefixes and original instruction length. JMPs
    and unresolved indirect CALLs are not converted into direct CALL records.
    Entry cuts also cover an actual resolved indirect target reached later; its
    existing runtime classifier/forward recipe remains necessary.

    Every API entry and recognized CALL receives metadata. NATIVE_LINUX uses
    SPECIAL before the CALL, so no source CALL word is staged by this metadata
    cut. An entry cut is before its first source instruction, retaining any CALL
    word already staged by the ordinary dynamic route. No return is fabricated.

    decoded describes the raw scan, including failures/unmodeled transfers; it
    is not the newly classified planner graph. Compile the returned snapshot.
    The caller finishes this immutable classification before source admission
    or learning. Already supplied ordinary observations may not name these APIs
    or the newly classified CALL sites. Nothing silently drops such input.
    """
    if not isinstance(snapshot, SourceSnapshot) or not isinstance(table, SourceOperationTable):
        raise TypeError("boundary scan needs a source snapshot and exact target table")
    if not isinstance(limits, BoundaryScanLimits):
        raise TypeError("boundary scan needs explicit finite limits")
    if snapshot.version != table.source_version:
        raise ValueError("operation table belongs to another source version")
    if not isinstance(instruction_sites, tuple) or any(
            type(site) is not int or not 0 <= site <= MASK64 for site in instruction_sites):
        raise TypeError("instruction starts must be an immutable tuple of source addresses")
    if len(set(instruction_sites)) != len(instruction_sites):
        raise ValueError("instruction starts must be unique")
    if len(instruction_sites) > limits.instruction_sites or len(table.entries) > limits.target_entries:
        raise ValueError("boundary scan exceeds its caller-supplied site/target bound")

    targets = {}
    for entry in table.entries:
        targets.setdefault(entry.address, entry)
    supplied = {}
    window_bytes = 0
    for site in instruction_sites:
        raw = snapshot.window(site)
        if not raw:
            raise ValueError("requested instruction start has no retained source bytes")
        window_bytes += len(raw)
        if window_bytes > limits.decode_window_bytes:
            raise ValueError("boundary scan exceeds its caller-supplied decode-byte bound")
        supplied[site] = SourceBytes(raw)
    decoded = decode_source(supplied)
    metadata = {entry.site: entry for entry in snapshot.sites}

    def add(site: int, kind: BoundaryKind) -> None:
        previous = metadata.get(site)
        if previous is not None and (previous.unmodeled_transfer is not None or
                                     previous.boundary not in (None, kind)):
            raise ValueError("operation boundary conflicts with retained source metadata")
        metadata[site] = SourceSite(site, kind)

    for entry in targets.values():
        add(entry.address, entry.boundary)
    calls = []
    for site in sorted(decoded.instructions):
        # The registered entry cut is authoritative even if a thin API starts
        # with another CALL. That implementation CALL is not a new W operation.
        if site in targets:
            continue
        flow = decoded.graph.get(site)
        if not isinstance(flow, SourceCall) or flow.target not in targets:
            continue
        entry = targets[flow.target]
        instruction = decoded.instructions[site]
        if instruction.name.upper() not in ("CALL", "CALLQ"):
            raise ValueError("decoder CALL flow disagrees with its retained instruction")
        add(site, entry.boundary)
        calls.append(SourceOperationCall(instruction, entry))
    call_sites = {call.site for call in calls}
    if any(item.target in targets or item.site in targets or item.site in call_sites
           for item in snapshot.observed_targets):
        raise ValueError("ordinary observations conflict with exact source API boundaries")
    classified = SourceSnapshot(snapshot.version, snapshot.regions,
                                tuple(metadata[site] for site in sorted(metadata)),
                                snapshot.observed_targets)
    return SourceBoundaryScan(classified, table, instruction_sites, tuple(calls), decoded, window_bytes)
