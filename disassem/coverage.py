"""Derive exact observation facts from one privately constructed image.

Input observations and decoded graph attachment are not emitted coverage. This
pass requires the source dispatch and ordinary target instruction to have been
emitted, with the exact typed dispatch relation between them. A target represented
only by an exit stub, source-operation boundary or failed lowering is not covered.

This is finite compiler output, not executable publication or a feedback ACK.
The publisher must bind this receipt to the actual coherent code/metadata it
commits before acknowledging precisely these observations. Later observations
and every uncovered input stay pending under the separately chosen C08 policy.
No ledger capacity, saturation, persistence or reclamation strategy is selected.
"""

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from .compiler import IndirectKind, ObservedTarget
from .lowering import LoweredImage


class EmissionOutcome(Enum):
    EMITTED = "source_dispatch_and_ordinary_target_emitted"
    SOURCE_NOT_EMITTED = "source_instruction_not_emitted"
    TARGET_NOT_EMITTED = "ordinary_target_instruction_not_emitted"
    DISPATCH_NOT_EMITTED = "exact_typed_dispatch_not_emitted"


@dataclass(frozen=True)
class EmissionReceipt:
    source_version: str
    entry_symbol: str
    emitted_observations: frozenset[ObservedTarget]
    outcomes: Mapping[ObservedTarget, EmissionOutcome]


def construct_emission_receipt(image: LoweredImage) -> EmissionReceipt:
    """Retain exact input dispositions without treating snapshot inclusion as ACK.

    EMITTED means the constructed assembly contains the dispatch and target,
    not that either ran or that the whole callee/root can return. A future
    publication receipt also needs its actual image/source/base/lifetime proof.
    """

    if not isinstance(image, LoweredImage):
        raise TypeError("emission receipt needs a constructed LoweredImage")
    if image.source_version != image.compilation.snapshot.version:
        raise ValueError("constructed image and input source versions differ")
    dispatches = {
        (transfer.source, transfer.target, kind)
        for transfer in image.transfers
        for kind in (
            (IndirectKind.CALL,) if transfer.kind == "indirect_call_target"
            else (IndirectKind.JUMP,) if transfer.kind == "indirect_jump_target"
            else ()
        )
    }
    outcomes: dict[ObservedTarget, EmissionOutcome] = {}
    for observed in image.compilation.snapshot.observed_targets:
        if observed.site not in image.emitted_sites:
            outcome = EmissionOutcome.SOURCE_NOT_EMITTED
        elif observed.target not in image.emitted_sites:
            outcome = EmissionOutcome.TARGET_NOT_EMITTED
        elif (observed.site, observed.target, observed.kind) not in dispatches:
            outcome = EmissionOutcome.DISPATCH_NOT_EMITTED
        else:
            outcome = EmissionOutcome.EMITTED
        outcomes[observed] = outcome
    emitted = frozenset(
        observed for observed, outcome in outcomes.items()
        if outcome is EmissionOutcome.EMITTED
    )
    return EmissionReceipt(
        image.source_version, image.entry.symbol, emitted,
        MappingProxyType(outcomes),
    )
