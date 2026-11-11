"""Private source-flow planning for the original UB-derived backend.

The caller supplies a finite, stable, already classified source graph. A lock
boundary identifies the source operation before its CALL or other effects, not
an instruction inside the lock implementation. Internal lock bookkeeping does
not belong to this graph as source lock operations.

Ordinary direct/indirect CALL and RET have explicit records. Call-target and
possible return relations remain distinct from ordinary successors; this pass
neither stages nor consumes source return words. The input assumes ordinary
matched source CALL/RET structure. An indirect CALL retains its unresolved
alternative even with observed ordinary targets; only known callee paths to RET
contribute return summaries. Changed return targets and other unmodeled transfer
effects remain outside this input contract. The pass cannot recognize APIs or
misclassified instructions or establish their pre-effect handling.

This pass neither decodes nor emits instructions. Its site identities and
records are provisional compiler data, not a machine-state or public adapter
ABI. Source/dependency identity and lifetime remain the caller's responsibility.
"""

from collections import deque
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class BoundaryKind(Enum):
    LOCK = "lock"
    UNLOCK = "unlock"
    MODE_CHANGE = "mode_change"
    SPECIAL_INSTRUCTION = "special_instruction"


@dataclass(frozen=True)
class SourceNode:
    """Known ordinary successors and an optional pre-instruction cut.

    A boundary's successors describe original source flow but are not followed
    by this fragment. An ordinary transfer may have both known alternatives
    and an unresolved alternative. Empty successors alone describe a supplied
    scope end; they never authorize synthesizing a source RET or root return.
    A truncated graph must retain the known next edge or mark unresolved flow,
    rather than use an empty successor list to imply source completion.
    indirect identifies a dynamic JMP with observed ordinary successors and an
    unresolved alternative. CALL and RET use their explicit records instead.
    """

    successors: tuple[int, ...] = ()
    boundary: BoundaryKind | None = None
    unresolved_successor: bool = False
    indirect: bool = False


@dataclass(frozen=True)
class SourceCall:
    """An ordinary source CALL and its own post-call instruction.

    target=None denotes an indirect CALL, whose observed_targets are known
    ordinary alternatives, not a replacement for its actual mutable operand.
    Its unknown alternative remains unresolved regardless of observed targets.
    A recognized source lock operation must instead be a SourceNode boundary
    at the operation site, before its CALL effects. Targets and return_site
    identify source instructions, not generated addresses or stack words.
    """

    target: int | None
    return_site: int
    observed_targets: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.observed_targets, tuple):
            raise TypeError("observed CALL targets must be an immutable tuple")
        if self.target is not None and self.observed_targets:
            raise ValueError("a direct CALL cannot also have observed indirect targets")

    @property
    def indirect(self) -> bool:
        return self.target is None

    @property
    def known_targets(self) -> tuple[int, ...]:
        if self.target is None:
            return self.observed_targets
        return (self.target,)


@dataclass(frozen=True)
class SourceReturn:
    """An explicit source RET; no actual return destination is inferred here."""


SourceInstruction = SourceNode | SourceCall | SourceReturn


class EdgeKind(Enum):
    ORDINARY = "ordinary"
    CALL_TARGET = "call_target"
    CALL_RETURN = "call_return"
    JUMP_TARGET = "jump_target"


@dataclass(frozen=True)
class SourceEdge:
    """A source-flow relation; source=None denotes a missing requested entry.

    CALL_RETURN is a possible continuation summary for its own call site, not
    an ordinary transfer or an emitted source CALL/RET effect.
    """

    source: int | None
    target: int
    kind: EdgeKind = EdgeKind.ORDINARY


@dataclass(frozen=True)
class PlannedBoundary:
    site: int
    kind: BoundaryKind


@dataclass(frozen=True)
class FragmentPlan:
    """Static alternatives, including exit edges into boundary/missing sites.

    Unresolved transfer sites remain in body_sites; membership alone is not an
    instruction-emission decision or proof of a completed source instruction.
    Return sites identify retained RET instructions, not completed returns.
    call_returns maps each retained CALL site to the subset of its known callee
    entries with modeled boundary-free routes to RET. It never authorizes a
    return from an unknown alternative or replaces the actual source RET.
    """

    body_sites: frozenset[int]
    edges: frozenset[SourceEdge]
    boundaries: tuple[PlannedBoundary, ...]
    missing_edges: frozenset[SourceEdge]
    unresolved_transfers: frozenset[int]
    return_sites: frozenset[int]
    call_returns: Mapping[int, frozenset[int]]


def _returning_sites(graph: Mapping[int, SourceInstruction]) -> set[int]:
    """Find sites with a modeled boundary-free route to an explicit RET.

    This is the least fixed point over the supplied graph, not a semantic
    nonreturning-function proof. Empty scopes, missing targets and unresolved
    alternatives contribute no returning route. A CALL needs at least one
    known returning callee and a returning continuation to return from its own
    enclosing call. The indirect unknown alternative cannot seed this set.
    """

    returning: set[int] = set()
    dependents: dict[int, set[int]] = {}
    for site, node in graph.items():
        if isinstance(node, SourceReturn):
            returning.add(site)
            continue
        if isinstance(node, SourceCall):
            dependencies = (*node.known_targets, node.return_site)
        elif node.boundary is None:
            dependencies = node.successors
        else:
            continue
        for target in dependencies:
            dependents.setdefault(target, set()).add(site)

    pending = deque(returning)
    while pending:
        target = pending.popleft()
        for site in dependents.get(target, ()):
            if site in returning:
                continue
            node = graph[site]
            if isinstance(node, SourceCall):
                if node.return_site not in returning or not any(
                    target in returning for target in node.known_targets
                ):
                    continue
            # A notified ordinary predecessor already has one returning edge.
            # Each site becomes returning once; recursion alone cannot seed it.
            returning.add(site)
            pending.append(site)
    return returning


def plan_fragment(graph: Mapping[int, SourceInstruction], entry: int) -> FragmentPlan:
    """Retain reachable source flow without crossing a classified boundary.

    Boundary sites are excluded from body_sites and have no outgoing planned
    edges. Safe alternatives can still reach a shared join independently. All
    incoming edges to missing sites are reported, even when they name the same
    target. Unknown dynamic destinations retain their transfer site in
    unresolved_transfers; no destination is invented.

    A reached CALL retains its known target relations. Its own continuation is
    retained only if at least one known callee has a modeled boundary-free route
    to an explicit RET; call_returns records exactly those known alternatives.
    An entirely cut or unresolved callee invents no returning alternative.
    RET sites never gain synthetic edges to every caller. Discovery is finite
    over the supplied graph; no CALL-discovery or runtime nesting budget is set.

    The result describes static alternatives, not which path ran or a complete
    handback recipe. Machine state, operation phase, actual CALL/RET effects and
    grant authority still need their chosen adapter/lock contracts. This pass
    does not read source text or mutate the supplied graph.
    """

    returning = _returning_sites(graph)
    pending = deque([SourceEdge(None, entry)])
    visited: set[int] = set()
    body: set[int] = set()
    edges: set[SourceEdge] = set()
    boundaries: list[PlannedBoundary] = []
    missing: set[SourceEdge] = set()
    unresolved: set[int] = set()
    returns: set[int] = set()
    call_returns: dict[int, frozenset[int]] = {}

    while pending:
        incoming = pending.popleft()
        node = graph.get(incoming.target)
        if node is None:
            # Check each edge before deduplicating sites: several alternatives
            # can share an as-yet untranslated target.
            missing.add(incoming)
            continue

        site = incoming.target
        if site in visited:
            continue
        visited.add(site)

        if isinstance(node, SourceNode) and node.boundary is not None:
            boundaries.append(PlannedBoundary(site, node.boundary))
            continue

        body.add(site)
        if isinstance(node, SourceReturn):
            returns.add(site)
            continue
        if isinstance(node, SourceCall):
            if node.indirect:
                unresolved.add(site)
            successors = [
                SourceEdge(site, target, EdgeKind.CALL_TARGET)
                for target in node.known_targets
            ]
            call_returns[site] = frozenset(
                target for target in node.known_targets if target in returning
            )
            if call_returns[site]:
                successors.append(
                    SourceEdge(site, node.return_site, EdgeKind.CALL_RETURN)
                )
        else:
            if node.unresolved_successor:
                unresolved.add(site)
            kind = EdgeKind.JUMP_TARGET if node.indirect else EdgeKind.ORDINARY
            successors = [
                SourceEdge(site, target, kind) for target in node.successors
            ]

        for edge in successors:
            edges.add(edge)
            pending.append(edge)

    return FragmentPlan(
        body_sites=frozenset(body),
        edges=frozenset(edges),
        boundaries=tuple(boundaries),
        missing_edges=frozenset(missing),
        unresolved_transfers=frozenset(unresolved),
        return_sites=frozenset(returns),
        call_returns=MappingProxyType(call_returns),
    )
