"""Private source-flow planning for the original UB-derived backend.

The caller supplies a finite, stable, already classified source graph. A lock
boundary identifies the source operation before its CALL or other effects, not
an instruction inside the lock implementation. Internal lock bookkeeping does
not belong to this graph as source lock operations.

Ordinary direct CALL and RET have explicit records. Call-target and possible
return relations remain distinct from ordinary successors; this pass neither
stages nor consumes source return words. The input assumes ordinary matched
source CALL/RET structure. Indirect calls, changed return targets and other
unmodeled transfer effects remain outside this input contract. The pass cannot
recognize misclassified instructions or establish their pre-effect handling.

This pass neither decodes nor emits instructions. Its site identities and
records are provisional compiler data, not a machine-state or public adapter
ABI. Source/dependency identity and lifetime remain the caller's responsibility.
"""

from collections import deque
from dataclasses import dataclass
from enum import Enum
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
    rather than use an empty successor list to imply source completion. Direct
    CALL and RET must use their explicit records, not ordinary successors.
    """

    successors: tuple[int, ...] = ()
    boundary: BoundaryKind | None = None
    unresolved_successor: bool = False


@dataclass(frozen=True)
class SourceCall:
    """An ordinary direct source CALL and its own post-call instruction.

    A recognized source lock operation must instead be a SourceNode boundary
    at the operation site, before its CALL effects. The target and return site
    here identify source instructions, not generated addresses or stack words.
    """

    target: int
    return_site: int


@dataclass(frozen=True)
class SourceReturn:
    """An explicit source RET; no actual return destination is inferred here."""


SourceInstruction = SourceNode | SourceCall | SourceReturn


class EdgeKind(Enum):
    ORDINARY = "ordinary"
    CALL_TARGET = "call_target"
    CALL_RETURN = "call_return"


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
    """

    body_sites: frozenset[int]
    edges: frozenset[SourceEdge]
    boundaries: tuple[PlannedBoundary, ...]
    missing_edges: frozenset[SourceEdge]
    unresolved_transfers: frozenset[int]
    return_sites: frozenset[int]


def _returning_sites(graph: Mapping[int, SourceInstruction]) -> set[int]:
    """Find sites with a modeled boundary-free route to an explicit RET.

    This is the least fixed point over the supplied graph, not a semantic
    nonreturning-function proof. Empty scopes, missing targets and unresolved
    alternatives contribute no returning route. A CALL needs both a returning
    callee and a returning continuation to return from its own enclosing call.
    """

    returning: set[int] = set()
    dependents: dict[int, set[int]] = {}
    for site, node in graph.items():
        if isinstance(node, SourceReturn):
            returning.add(site)
            continue
        if isinstance(node, SourceCall):
            dependencies = (node.target, node.return_site)
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
                if node.target not in returning or node.return_site not in returning:
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

    A reached direct CALL retains its target relation. Its own continuation is
    retained only if that callee has a modeled boundary-free route to an explicit
    RET. An entirely cut or unresolved callee invents no returning alternative.
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
            successors = [SourceEdge(site, node.target, EdgeKind.CALL_TARGET)]
            if node.target in returning:
                successors.append(
                    SourceEdge(site, node.return_site, EdgeKind.CALL_RETURN)
                )
        else:
            if node.unresolved_successor:
                unresolved.add(site)
            successors = [SourceEdge(site, target) for target in node.successors]

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
    )
