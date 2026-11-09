"""Private source-flow planning for the original UB-derived backend.

The caller supplies a finite, stable, already classified source graph. A lock
boundary identifies the source operation before its CALL or other effects, not
an instruction inside the lock implementation. Internal lock bookkeeping does
not belong to this graph as source lock operations.

Ordinary CALL/RET body nodes are outside this pass's input contract until their
separate handling exists. The caller must not encode them as ordinary scope
ends or invent fallthrough edges. This pass cannot recognize such misclassified
inputs or establish their pre-effect handling.

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
    """Known intraprocedural successors and an optional pre-instruction cut.

    A boundary's successors describe original source flow but are not followed
    by this fragment. An ordinary transfer may have both known alternatives
    and an unresolved alternative. Empty successors alone describe a supplied
    scope end; they never authorize synthesizing a source RET or root return.
    A truncated graph must retain the known next edge or mark unresolved flow,
    rather than use an empty successor list to imply source completion.
    """

    successors: tuple[int, ...] = ()
    boundary: BoundaryKind | None = None
    unresolved_successor: bool = False


@dataclass(frozen=True)
class SourceEdge:
    """A known source edge; source=None denotes a missing requested entry."""

    source: int | None
    target: int


@dataclass(frozen=True)
class PlannedBoundary:
    site: int
    kind: BoundaryKind


@dataclass(frozen=True)
class FragmentPlan:
    """Static alternatives, including exit edges into boundary/missing sites.

    Unresolved transfer sites remain in body_sites; membership alone is not an
    instruction-emission decision or proof of a completed source instruction.
    """

    body_sites: frozenset[int]
    edges: frozenset[SourceEdge]
    boundaries: tuple[PlannedBoundary, ...]
    missing_edges: frozenset[SourceEdge]
    unresolved_transfers: frozenset[int]


def plan_fragment(graph: Mapping[int, SourceNode], entry: int) -> FragmentPlan:
    """Retain reachable source flow without crossing a classified boundary.

    Boundary sites are excluded from body_sites and have no outgoing planned
    edges. Safe alternatives can still reach a shared join independently. All
    incoming edges to missing ordinary sites are reported, even when they name
    the same target. Unknown dynamic destinations retain their transfer site
    in unresolved_transfers; no destination is invented.

    The result describes static alternatives, not which path ran or a complete
    handback recipe. Machine state, operation phase, actual CALL/RET effects and
    grant authority still need their chosen adapter/lock contracts. CALL-return
    summary construction is not implemented here: callers must not flatten an
    ordinary CALL into an unproved fallthrough edge. This pass adds no discovery
    budget and does not read source text or mutate the supplied graph.
    """

    pending = deque([SourceEdge(None, entry)])
    visited: set[int] = set()
    body: set[int] = set()
    edges: set[SourceEdge] = set()
    boundaries: list[PlannedBoundary] = []
    missing: set[SourceEdge] = set()
    unresolved: set[int] = set()

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

        if node.boundary is not None:
            boundaries.append(PlannedBoundary(site, node.boundary))
            continue

        body.add(site)
        if node.unresolved_successor:
            unresolved.add(site)

        for target in node.successors:
            edge = SourceEdge(site, target)
            edges.add(edge)
            pending.append(edge)

    return FragmentPlan(
        body_sites=frozenset(body),
        edges=frozenset(edges),
        boundaries=tuple(boundaries),
        missing_edges=frozenset(missing),
        unresolved_transfers=frozenset(unresolved),
    )
