"""Private source discovery, decoding and fragment planning for the UB backend.

The caller supplies one immutable, source-versioned byte snapshot and exact
operation metadata. This front end reads only that snapshot. It performs no
provider access, runtime source retention, code emission or publication and
selects no register/packet ABI. Ordinary matched direct CALL/RET remains the
planner's input contract; successful decoding proves no lowering support.

All resource limits are explicit caller inputs except the already selected
five-edge direct-CALL discovery default. Decode sites count distinct attempts,
including failed or unmodeled decoding. Submitted decoder-window bytes count
windows presented to the decoder, including overlapping bytes and failed
attempts; they are not unique source-cache bytes. CFG work counts popped
worklist edges, including the entry and redundant visits. These are discovery
limits, not runtime lock/call nesting limits or invocation exit attribution.
Finite snapshot validation is input preparation, outside these discovery
counters; no source-cache capacity or executable-image budget is selected.
"""

from collections import deque
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from .fragment import (
    BoundaryKind,
    EdgeKind,
    FragmentPlan,
    SourceCall,
    SourceEdge,
    SourceInstruction,
    SourceNode,
    plan_fragment,
)
from .source_decode import (
    MASK64,
    MAX_INSTRUCTION_BYTES,
    DecodeFailure,
    DecodedInstruction,
    DecodedSource,
    SourceBytes,
    UnmodeledTransfer,
    decode_source,
)


DEFAULT_DIRECT_CALL_EDGES = 5


def _address(value: int) -> None:
    if type(value) is not int or not 0 <= value <= MASK64:
        raise ValueError("source site must be an unsigned 64-bit address")


def _limit(value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError("discovery limits must be nonnegative integers")


@dataclass(frozen=True)
class SourceRegion:
    """An immutable supplied byte interval, with no wrap across address zero."""

    start: int
    data: bytes

    def __post_init__(self) -> None:
        _address(self.start)
        if not isinstance(self.data, bytes) or not self.data:
            raise ValueError("a source region needs nonempty immutable bytes")
        if len(self.data) > MASK64 + 1 - self.start:
            raise ValueError("a source region cannot wrap the address space")

    @property
    def end(self) -> int:
        return self.start + len(self.data)


@dataclass(frozen=True)
class SourceSite:
    """Exact source-operation or unmodeled-transfer metadata at one site."""

    site: int
    boundary: BoundaryKind | None = None
    unmodeled_transfer: str | None = None

    def __post_init__(self) -> None:
        _address(self.site)
        if self.boundary is not None and not isinstance(self.boundary, BoundaryKind):
            raise TypeError("source boundary must have an exact BoundaryKind")
        if self.unmodeled_transfer is not None:
            if not isinstance(self.unmodeled_transfer, str) or not self.unmodeled_transfer:
                raise ValueError("unmodeled transfer needs a nonempty description")
            if self.boundary is not None:
                raise ValueError("source boundary and unmodeled transfer overlap")


@dataclass(frozen=True)
class SourceSnapshot:
    """Finite coherent compiler input, not a runtime source-lifetime lease.

    version names this fixed source/dependency snapshot. The caller must not
    reuse it for different source versions. Tuple/frozen records and immutable
    byte regions bind the actual input to the result regardless of external
    source changes. Overlapping regions must contain identical bytes. Gaps are
    never padded or silently read from elsewhere.
    """

    version: str
    regions: tuple[SourceRegion, ...]
    sites: tuple[SourceSite, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version:
            raise ValueError("source snapshot needs an explicit version identity")
        if not isinstance(self.regions, tuple) or not all(
            isinstance(region, SourceRegion) for region in self.regions
        ):
            raise TypeError("source regions must be a tuple of SourceRegion records")
        if not isinstance(self.sites, tuple) or not all(
            isinstance(site, SourceSite) for site in self.sites
        ):
            raise TypeError("source metadata must be a tuple of SourceSite records")
        regions = tuple(sorted(
            self.regions, key=lambda region: (region.start, region.end)
        ))
        active: list[SourceRegion] = []
        for region in regions:
            active = [previous for previous in active if previous.end > region.start]
            for previous in active:
                end = min(previous.end, region.end)
                first = previous.data[
                    region.start - previous.start:end - previous.start
                ]
                second = region.data[:end - region.start]
                if first != second:
                    raise ValueError("overlapping source regions disagree")
            active.append(region)
        seen: set[int] = set()
        for metadata in self.sites:
            if metadata.site in seen:
                raise ValueError("source site metadata must be unique")
            seen.add(metadata.site)
        object.__setattr__(self, "regions", regions)

    def window(self, site: int) -> bytes:
        """Return contiguous supplied bytes for one architectural instruction."""

        _address(site)
        cursor = site
        remaining = MAX_INSTRUCTION_BYTES
        pieces: list[bytes] = []
        while remaining and cursor <= MASK64:
            covering = [
                region for region in self.regions
                if region.start <= cursor < region.end
            ]
            if not covering:
                break
            region = max(covering, key=lambda candidate: candidate.end)
            count = min(region.end - cursor, remaining)
            offset = cursor - region.start
            pieces.append(region.data[offset:offset + count])
            cursor += count
            remaining -= count
        return b"".join(pieces)


@dataclass(frozen=True)
class DiscoveryLimits:
    """Caller-selected limits; zero explicitly refuses that resource's work.

    decode_sites counts attempted available-site decodes, including failures,
    not successful instruction records. Source-unavailable sites do not invoke
    the decoder. The submitted-window byte quantity is defined by this module.
    """

    decode_sites: int
    decode_window_bytes: int
    cfg_work_steps: int
    direct_call_edges: int = DEFAULT_DIRECT_CALL_EDGES

    def __post_init__(self) -> None:
        for value in (
            self.decode_sites,
            self.decode_window_bytes,
            self.cfg_work_steps,
            self.direct_call_edges,
        ):
            _limit(value)


class ResourceKind(Enum):
    DECODE_SITES = "decode_sites"
    DECODE_WINDOW_BYTES = "decode_window_bytes"
    CFG_WORK_STEPS = "cfg_work_steps"
    DIRECT_CALL_EDGES = "direct_call_edges"


@dataclass(frozen=True)
class ResourceStop:
    """A discovery attempt, not proof that a runtime path reached this edge.

    edge.target is the requested source site, not necessarily still absent.
    consumed is the quantity used before the attempt, required is its additional
    quantity, and limit is the selected bound. For DIRECT_CALL_EDGES these
    quantities describe that path, not a global edge total. A later independent
    route may supply the target; inspect missing_outcomes for edges still absent from the final plan.
    """

    resource: ResourceKind
    edge: SourceEdge
    direct_call_depth: int
    limit: int
    consumed: int
    required: int


@dataclass(frozen=True)
class DiscoveryConsumption:
    decode_sites: int
    decode_window_bytes: int
    cfg_work_steps: int


class MissingKind(Enum):
    """Final missing-site cause, not a semantic instruction-support decision.

    SOURCE_UNAVAILABLE means no supplied bytes at the requested site. Partial,
    incomplete or unsupported decoding is DECODE_FAILURE with available bytes
    retained; it proves neither invalid source nor a permanent capability stop.
    """

    SOURCE_UNAVAILABLE = "source_unavailable"
    DECODE_FAILURE = "decode_failure"
    UNMODELED_TRANSFER = "unmodeled_transfer"
    RESOURCE_BOUNDARY = "resource_boundary"


@dataclass(frozen=True)
class CompilationPlan:
    """Version-bound discovered source and its reachable fragment alternatives.

    Discovery can inspect an ordinary CALL's prospective continuation before
    the callee return summary is known. Only fragment retains it as a possible
    translated continuation after a modeled returning callee. Decode/resource
    outcomes on other discovered paths do not reject the whole entry. This
    result acknowledges neither emitted coverage nor a runtime handback recipe.
    """

    snapshot: SourceSnapshot
    entry: int
    limits: DiscoveryLimits
    decoded: DecodedSource
    fragment: FragmentPlan
    missing_source: frozenset[int]
    resource_stops: tuple[ResourceStop, ...]
    missing_outcomes: Mapping[SourceEdge, MissingKind]
    minimum_call_depth: Mapping[int, int]
    consumption: DiscoveryConsumption


@dataclass(frozen=True)
class _Pending:
    edge: SourceEdge
    direct_call_depth: int


def compile_fragment_plan(
    snapshot: SourceSnapshot, entry: int, limits: DiscoveryLimits
) -> CompilationPlan:
    """Discover within the supplied snapshot, decode and plan one source entry.

    Each available site is decoded at most once. A modeled site reached with
    fewer direct CALL edges is expanded again, so an earlier deeper visit
    cannot suppress a later shallower route. Branches and caller continuations
    keep their caller depth; only entering a direct callee adds an edge. The
    selected CALL bound limits discovery, not reuse of code already discovered
    through another route and not runtime nesting.

    Source boundaries have no outgoing discovery edges. Missing bytes, decode
    failures, unmodeled transfers and each actual resource refusal remain
    distinct. No result permits replay or advances any source state.
    """

    if not isinstance(snapshot, SourceSnapshot) or not isinstance(
        limits, DiscoveryLimits
    ):
        raise TypeError("compiler needs a SourceSnapshot and explicit DiscoveryLimits")
    _address(entry)
    metadata = {item.site: item for item in snapshot.sites}
    instructions: dict[int, DecodedInstruction] = {}
    graph: dict[int, SourceInstruction] = {}
    failures: dict[int, DecodeFailure] = {}
    unmodeled: dict[int, UnmodeledTransfer] = {}
    missing_source: set[int] = set()
    minimum_depth: dict[int, int] = {}
    stops: list[ResourceStop] = []
    pending = deque([_Pending(SourceEdge(None, entry), 0)])
    decode_sites = 0
    decode_window_bytes = 0
    cfg_work_steps = 0

    def stop(resource: ResourceKind, item: _Pending, limit: int,
             consumed: int, required: int) -> None:
        record = ResourceStop(
            resource, item.edge, item.direct_call_depth, limit, consumed, required
        )
        stops.append(record)

    while pending:
        if cfg_work_steps >= limits.cfg_work_steps:
            for item in pending:
                stop(ResourceKind.CFG_WORK_STEPS, item, limits.cfg_work_steps,
                     cfg_work_steps, 1)
            break
        item = pending.popleft()
        cfg_work_steps += 1
        site = item.edge.target
        depth = item.direct_call_depth
        if site in missing_source or site in failures or site in unmodeled:
            continue
        if site in graph:
            if minimum_depth[site] <= depth:
                continue
        else:
            raw = snapshot.window(site)
            if not raw:
                missing_source.add(site)
                continue
            if decode_sites >= limits.decode_sites:
                stop(ResourceKind.DECODE_SITES, item, limits.decode_sites,
                     decode_sites, 1)
                continue
            if decode_window_bytes + len(raw) > limits.decode_window_bytes:
                stop(ResourceKind.DECODE_WINDOW_BYTES, item,
                     limits.decode_window_bytes, decode_window_bytes, len(raw))
                continue
            classification = metadata.get(site)
            supplied = SourceBytes(
                raw,
                classification.boundary if classification is not None else None,
                classification.unmodeled_transfer if classification is not None else None,
            )
            decode_sites += 1
            decode_window_bytes += len(raw)
            result = decode_source({site: supplied})
            # Retain the decoder's actual objects, including prefix/backend
            # metadata; never reconstruct instructions from mnemonic/operands.
            instructions.update(result.instructions)
            graph.update(result.graph)
            failures.update(result.decode_failures)
            unmodeled.update(result.unmodeled_transfers)
            if site not in graph:
                continue
        minimum_depth[site] = depth
        node = graph[site]
        if isinstance(node, SourceNode):
            if node.boundary is not None:
                continue
            for target in node.successors:
                pending.append(_Pending(SourceEdge(site, target), depth))
        elif isinstance(node, SourceCall):
            target = _Pending(
                SourceEdge(site, node.target, EdgeKind.CALL_TARGET), depth + 1
            )
            if depth >= limits.direct_call_edges:
                stop(ResourceKind.DIRECT_CALL_EDGES, target,
                     limits.direct_call_edges, depth, 1)
            else:
                pending.append(target)
            pending.append(_Pending(
                SourceEdge(site, node.return_site, EdgeKind.CALL_RETURN), depth
            ))
        # An explicit RET has no synthesized discovery successor.

    decoded = DecodedSource(
        instructions=MappingProxyType(instructions),
        graph=MappingProxyType(graph),
        decode_failures=MappingProxyType(failures),
        unmodeled_transfers=MappingProxyType(unmodeled),
    )
    fragment = plan_fragment(decoded.graph, entry)
    resource_targets = {record.edge.target for record in stops}
    missing_outcomes: dict[SourceEdge, MissingKind] = {}
    for edge in fragment.missing_edges:
        if edge.target in failures:
            kind = MissingKind.DECODE_FAILURE
        elif edge.target in unmodeled:
            kind = MissingKind.UNMODELED_TRANSFER
        elif edge.target in missing_source:
            kind = MissingKind.SOURCE_UNAVAILABLE
        elif edge.target in resource_targets:
            kind = MissingKind.RESOURCE_BOUNDARY
        else:
            raise RuntimeError("missing planner edge has no discovery outcome")
        missing_outcomes[edge] = kind
    return CompilationPlan(
        snapshot=snapshot,
        entry=entry,
        limits=limits,
        decoded=decoded,
        fragment=fragment,
        missing_source=frozenset(missing_source),
        resource_stops=tuple(stops),
        missing_outcomes=MappingProxyType(missing_outcomes),
        minimum_call_depth=MappingProxyType(minimum_depth),
        consumption=DiscoveryConsumption(
            decode_sites, decode_window_bytes, cfg_work_steps
        ),
    )
