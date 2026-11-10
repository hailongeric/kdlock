"""Private source discovery, decoding and fragment planning for the UB backend.

The caller supplies one immutable, source-versioned byte snapshot and exact
operation metadata. This front end reads only that snapshot. It performs no
provider access, runtime source retention, code emission or publication and
selects no register/packet ABI. Ordinary matched direct/indirect CALL/RET remains
the planner's input contract; successful decoding proves no lowering support.
Observed indirect targets add versioned ordinary alternatives without replacing
the actual decoded operand or treating observations as emitted coverage.

All resource limits are explicit caller inputs except the already selected
five-edge direct-CALL discovery default. Decode sites count distinct attempts,
including failed or unmodeled decoding. Submitted decoder-window bytes count
windows presented to the decoder, including overlapping bytes and failed
attempts; they are not unique source-cache bytes. CFG work counts popped
worklist edges, including every requested entry and redundant visits. These
are discovery limits, not runtime lock/call nesting or invocation exit attribution.
Only direct CALL edges consume the selected depth bound. Observed indirect CALL
targets keep the current direct-call depth and are bounded by the caller's
decode/window/CFG limits; no indirect depth default is introduced.
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


class IndirectKind(Enum):
    CALL = "call"
    JUMP = "jump"


@dataclass(frozen=True)
class ObservedTarget:
    """One source-versioned, ordinary indirect source/target observation.

    The caller must have classified this as an ordinary target rather than a
    source lock/unlock/mode operation. Observations cannot authorize crossing a
    source-operation boundary or rewrite a mutable decoded operand. Unknown
    targets still require runtime classification before source CALL effects;
    this record implements neither that bridge nor runtime feedback retention.
    """

    source_version: str
    site: int
    target: int
    kind: IndirectKind

    def __post_init__(self) -> None:
        if not isinstance(self.source_version, str) or not self.source_version:
            raise ValueError("an observed target needs an explicit source version")
        _address(self.site)
        _address(self.target)
        if not isinstance(self.kind, IndirectKind):
            raise TypeError("an observed target needs an exact IndirectKind")


@dataclass(frozen=True)
class SourceSnapshot:
    """Finite coherent compiler input, not a runtime source-lifetime lease.

    version names fixed source/dependency bytes and source-site metadata. The
    caller must not reuse it for a different source version or classification.
    Version-matched observations may accumulate without changing those inputs.
    Tuple/frozen records and immutable byte regions bind the actual input to
    the result regardless of external source changes. Overlapping regions must
    contain identical bytes. Gaps are
    never padded or silently read from elsewhere.
    """

    version: str
    regions: tuple[SourceRegion, ...]
    sites: tuple[SourceSite, ...] = ()
    observed_targets: tuple[ObservedTarget, ...] = ()

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
        if not isinstance(self.observed_targets, tuple) or not all(
            isinstance(target, ObservedTarget) for target in self.observed_targets
        ):
            raise TypeError("observations must be a tuple of ObservedTarget records")
        if any(target.source_version != self.version for target in self.observed_targets):
            raise ValueError("an observed target belongs to another source version")
        observations = tuple(sorted(
            set(self.observed_targets),
            key=lambda target: (target.site, target.kind.value, target.target),
        ))
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
        object.__setattr__(self, "observed_targets", observations)

    def with_observed_targets(
        self, additional: tuple[ObservedTarget, ...]
    ) -> "SourceSnapshot":
        """Accumulate finite version-matched observations without losing old ones.

        The immutable source bytes and source-operation metadata stay bound to
        this source version. This is compiler input composition, not a live
        publication, persistence, coverage ACK or capacity/saturation policy.
        """

        if not isinstance(additional, tuple):
            raise TypeError("additional observations must be an immutable tuple")
        return SourceSnapshot(
            self.version, self.regions, self.sites,
            self.observed_targets + additional,
        )

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
    route may supply the target; inspect missing_outcomes for edges still absent
    from the final plan.
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


class ObservationOutcome(Enum):
    """Input-observation disposition, never an emitted-coverage acknowledgment."""

    ATTACHED = "attached_to_decoded_graph"
    NOT_DISCOVERED = "source_site_not_discovered"
    SOURCE_UNAVAILABLE = "source_unavailable"
    DECODE_FAILURE = "decode_failure"
    UNMODELED_TRANSFER = "unmodeled_transfer"
    RESOURCE_BOUNDARY = "resource_boundary"
    SOURCE_BOUNDARY = "source_boundary"
    FLOW_MISMATCH = "decoded_flow_kind_mismatch"


@dataclass(frozen=True)
class CompilationPlan:
    """Version-bound discovered source and its reachable fragment alternatives.

    Discovery can inspect an ordinary CALL's prospective continuation before
    the callee return summary is known. Only fragment retains it as a possible
    translated continuation after a modeled returning callee. Decode/resource
    outcomes on other discovered paths do not reject the whole entry. This
    result acknowledges neither emitted coverage nor a runtime handback recipe.
    observation_outcomes distinguishes attachment to the decoded graph from
    observations not usable in this candidate; even ATTACHED may lie outside
    fragment.body_sites or point to a missing/resource-limited target.
    entry_fragments retains each independently planned root. fragment is their
    static union for one image's source labels; it adds no edge between roots.
    entry_sites includes the primary entry followed by the additional explicit
    roots. Discovery and later code-generation budgets remain shared.
    """

    snapshot: SourceSnapshot
    entry: int
    entry_sites: tuple[int, ...]
    entry_fragments: Mapping[int, FragmentPlan]
    limits: DiscoveryLimits
    decoded: DecodedSource
    fragment: FragmentPlan
    missing_source: frozenset[int]
    resource_stops: tuple[ResourceStop, ...]
    missing_outcomes: Mapping[SourceEdge, MissingKind]
    observation_outcomes: Mapping[ObservedTarget, ObservationOutcome]
    minimum_call_depth: Mapping[int, int]
    consumption: DiscoveryConsumption


def _merge_entry_fragments(plans: Mapping[int, FragmentPlan]) -> FragmentPlan:
    """Combine proven alternatives, retaining every cut and missing-root edge."""
    fragments = tuple(plans.values())
    if len(fragments) == 1:
        return fragments[0]
    boundaries = {}
    call_returns = {}
    for fragment in fragments:
        for boundary in fragment.boundaries:
            previous = boundaries.setdefault(boundary.site, boundary)
            if previous != boundary:
                raise RuntimeError("entry plans disagree on a source boundary")
        for site, targets in fragment.call_returns.items():
            previous = call_returns.setdefault(site, targets)
            if previous != targets:
                raise RuntimeError("entry plans disagree on a callee-return proof")
    return FragmentPlan(
        body_sites=frozenset().union(*(item.body_sites for item in fragments)),
        edges=frozenset().union(*(item.edges for item in fragments)),
        boundaries=tuple(boundaries[site] for site in sorted(boundaries)),
        missing_edges=frozenset().union(*(item.missing_edges for item in fragments)),
        unresolved_transfers=frozenset().union(*(item.unresolved_transfers for item in fragments)),
        return_sites=frozenset().union(*(item.return_sites for item in fragments)),
        call_returns=MappingProxyType(call_returns),
    )


@dataclass(frozen=True)
class _Pending:
    edge: SourceEdge
    direct_call_depth: int


def compile_fragment_plan(
    snapshot: SourceSnapshot, entry: int, limits: DiscoveryLimits, *,
    entry_sites: tuple[int, ...] | None = None,
) -> CompilationPlan:
    """Discover and independently plan explicit entries with one shared budget.

    Each available site is decoded at most once. A modeled site reached with
    fewer direct CALL edges is expanded again, so an earlier deeper visit
    cannot suppress a later shallower route. Branches and caller continuations
    keep their caller depth; only entering a direct callee adds an edge. Known
    observed indirect callees retain that depth and consume only the explicit
    decode/window/CFG resources. The selected direct-CALL bound limits discovery,
    not reuse of code already discovered through another route and not runtime
    nesting.

    entry_sites additionally names the image's explicit canonical reentries.
    The primary entry is processed first; each root starts at direct-CALL depth
    zero. Decode/window/CFG limits are shared across all roots, including their
    redundant visits. Each entry is planned independently over the same decoded
    graph, then static alternatives are combined without adding control edges.
    A separately requested continuation does not prove that its preceding CALL
    returns or permit traversal through a source-operation boundary.

    Source boundaries have no outgoing discovery edges. Missing bytes, decode
    failures, unmodeled transfers and each actual resource refusal remain
    distinct. Observations attach only to the matching decoded indirect kind,
    after exact boundary classification; they cannot learn away a source cut.
    No result permits replay or advances any source state.
    """

    if not isinstance(snapshot, SourceSnapshot) or not isinstance(
        limits, DiscoveryLimits
    ):
        raise TypeError("compiler needs a SourceSnapshot and explicit DiscoveryLimits")
    _address(entry)
    if entry_sites is None:
        roots = (entry,)
    else:
        if (not isinstance(entry_sites, tuple) or not entry_sites
                or len(set(entry_sites)) != len(entry_sites)):
            raise ValueError("discovery entries must be a nonempty unique tuple")
        for site in entry_sites:
            _address(site)
        roots = (entry,) + tuple(site for site in entry_sites if site != entry)
    metadata = {item.site: item for item in snapshot.sites}
    observations: dict[int, list[ObservedTarget]] = {}
    for observed in snapshot.observed_targets:
        observations.setdefault(observed.site, []).append(observed)
    attached: set[ObservedTarget] = set()
    instructions: dict[int, DecodedInstruction] = {}
    graph: dict[int, SourceInstruction] = {}
    failures: dict[int, DecodeFailure] = {}
    unmodeled: dict[int, UnmodeledTransfer] = {}
    missing_source: set[int] = set()
    minimum_depth: dict[int, int] = {}
    stops: list[ResourceStop] = []
    pending = deque(_Pending(SourceEdge(None, site), 0) for site in roots)
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
            node = graph[site]
            if isinstance(node, SourceCall) and node.indirect:
                selected = tuple(
                    observed for observed in observations.get(site, ())
                    if observed.kind is IndirectKind.CALL
                )
                graph[site] = SourceCall(
                    None, node.return_site,
                    tuple(observed.target for observed in selected),
                )
                attached.update(selected)
            elif (
                isinstance(node, SourceNode)
                and node.boundary is None and node.indirect
            ):
                selected = tuple(
                    observed for observed in observations.get(site, ())
                    if observed.kind is IndirectKind.JUMP
                )
                graph[site] = SourceNode(
                    tuple(observed.target for observed in selected),
                    unresolved_successor=True, indirect=True,
                )
                attached.update(selected)
        minimum_depth[site] = depth
        node = graph[site]
        if isinstance(node, SourceNode):
            if node.boundary is not None:
                continue
            kind = EdgeKind.JUMP_TARGET if node.indirect else EdgeKind.ORDINARY
            for target in node.successors:
                pending.append(_Pending(SourceEdge(site, target, kind), depth))
        elif isinstance(node, SourceCall):
            for callee in node.known_targets:
                target = _Pending(
                    SourceEdge(site, callee, EdgeKind.CALL_TARGET),
                    depth if node.indirect else depth + 1,
                )
                if not node.indirect and depth >= limits.direct_call_edges:
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
    entry_fragments = {site: plan_fragment(decoded.graph, site) for site in roots}
    fragment = _merge_entry_fragments(entry_fragments)
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
    observation_outcomes: dict[ObservedTarget, ObservationOutcome] = {}
    for observed in snapshot.observed_targets:
        site = observed.site
        if observed in attached:
            disposition = ObservationOutcome.ATTACHED
        elif site in graph:
            node = graph[site]
            disposition = (
                ObservationOutcome.SOURCE_BOUNDARY
                if isinstance(node, SourceNode) and node.boundary is not None
                else ObservationOutcome.FLOW_MISMATCH
            )
        elif site in failures:
            disposition = ObservationOutcome.DECODE_FAILURE
        elif site in unmodeled:
            disposition = ObservationOutcome.UNMODELED_TRANSFER
        elif site in missing_source:
            disposition = ObservationOutcome.SOURCE_UNAVAILABLE
        elif site in resource_targets:
            disposition = ObservationOutcome.RESOURCE_BOUNDARY
        else:
            disposition = ObservationOutcome.NOT_DISCOVERED
        observation_outcomes[observed] = disposition
    return CompilationPlan(
        snapshot=snapshot,
        entry=entry,
        entry_sites=roots,
        entry_fragments=MappingProxyType(entry_fragments),
        limits=limits,
        decoded=decoded,
        fragment=fragment,
        missing_source=frozenset(missing_source),
        resource_stops=tuple(stops),
        missing_outcomes=MappingProxyType(missing_outcomes),
        observation_outcomes=MappingProxyType(observation_outcomes),
        minimum_call_depth=MappingProxyType(minimum_depth),
        consumption=DiscoveryConsumption(
            decode_sites, decode_window_bytes, cfg_work_steps
        ),
    )
