"""Caller-serialized cumulative learning for one exact retained source epoch.

This module composes copied feedback, immutable compiler input, discovery,
lowering and artifact export. It performs no transport, kernel operation, file
publication or source execution. Opaque immutable identity bytes must map the
actual retained kernel objects/receipts; equal labels do not establish a lease,
an update or an ACK. In particular a producer is durable metadata independent
of retired executable code, and fact identity includes its exact incarnation.

All retained histories have explicit caller limits. A capacity exception leaves
existing facts pending and makes no runtime admission decision. Callers serialize
these methods; new kernel facts can continue accumulating while a candidate is
constructed. Kernel allocation, persistence, polling and retry policy are
external; ordinary host objects are bounded by the supplied ledger limits.
"""

from dataclasses import dataclass
from enum import Enum

from .artifact import ImageArtifact, export_image
from .compiler import (
    CompilationPlan, DiscoveryLimits, ObservationOutcome,
    SourceSnapshot, compile_fragment_plan,
)
from .coverage import EmissionOutcome, EmissionReceipt
from .feedback import (
    FeedbackDisposition, RuntimeExit, TargetClassification, adapt_runtime_exit,
)
from .lowering import CodegenLimits, EntryMetadata, LoweredImage, lower_compilation
from .source_decode import MASK64


def _identity(value: bytes) -> None:
    if not isinstance(value, bytes) or not value:
        raise ValueError("identities must be explicit nonempty immutable bytes")


def _optional_identity(value: bytes | None) -> None:
    if value is not None:
        _identity(value)


def _word(value: int, *, positive: bool = False) -> None:
    if type(value) is not int or not (1 if positive else 0) <= value <= MASK64:
        raise ValueError("value must be an exact unsigned 64-bit integer")


@dataclass(frozen=True)
class LearningLimits:
    """Maximum retained history entries of each kind, with no numeric defaults.

    Memberships are finite products of these limits; original snapshot input is
    caller-supplied finite storage. Successful ACKs do not erase the history or
    remove already learned observations. No automatic eviction is performed.
    """

    records: int
    claims: int
    candidates: int
    publications: int
    acknowledgments: int

    def __post_init__(self) -> None:
        for value in (self.records, self.claims, self.candidates,
                      self.publications, self.acknowledgments):
            if type(value) is not int or value < 0:
                raise ValueError("learning limits must be explicit finite nonnegative integers")


class LearningCapacityError(ValueError):
    """Exact private bookkeeping stop; existing pending data stays intact."""

    def __init__(self, resource: str, limit: int, retained: int, requested: int):
        self.resource = resource
        self.limit = limit
        self.retained = retained
        self.requested = requested
        super().__init__(f"{resource}: limit={limit}, retained={retained}, requested={requested}")


@dataclass(frozen=True)
class EpochBinding:
    identity: bytes
    version: bytes
    configuration_identity: bytes
    load_identity: bytes
    current_task_gs_offset: int

    def __post_init__(self) -> None:
        for value in (self.identity, self.version, self.configuration_identity, self.load_identity):
            _identity(value)
        _word(self.current_task_gs_offset)


@dataclass(frozen=True)
class FactKey:
    """Exact reservation identity, never a reusable record address alone."""

    epoch_identity: bytes
    record_identity: bytes
    incarnation: int

    def __post_init__(self) -> None:
        _identity(self.epoch_identity)
        _identity(self.record_identity)
        _word(self.incarnation, positive=True)


@dataclass(frozen=True)
class LearningFact:
    """Copied immutable fact and its retained host construction provenance.

    producer is the actual host LoweredImage associated with the durable kernel
    producer/image identities. It is not a pointer into live executable storage.
    The caller retains that correspondence and exact epoch/configuration/load
    proof. Classification comes from the actual explicit ordinary/API classifier;
    failure to resolve an API is not an ordinary-target proof.
    """

    record_identity: bytes
    incarnation: int
    producer_identity: bytes
    image_identity: bytes
    epoch: EpochBinding
    producer: LoweredImage
    exit: RuntimeExit
    entry_result: int
    classification: TargetClassification

    def __post_init__(self) -> None:
        for value in (self.record_identity, self.producer_identity, self.image_identity):
            _identity(value)
        _word(self.incarnation, positive=True)
        if not isinstance(self.epoch, EpochBinding) or not isinstance(self.producer, LoweredImage):
            raise TypeError("fact requires its exact epoch and host producer metadata")
        if not isinstance(self.exit, RuntimeExit) or type(self.entry_result) is not int:
            raise TypeError("fact requires copied exit scalars and exact entry result")
        if not isinstance(self.classification, TargetClassification):
            raise TypeError("fact requires explicit captured target classification")

    @property
    def key(self) -> FactKey:
        return FactKey(self.epoch.identity, self.record_identity, self.incarnation)


@dataclass(frozen=True)
class ConsumerClaim:
    """Snapshot of one actual kernel single-consumer claim, not a claim API.

    The claim/holder and every record reservation remain retained until actual
    claim_end. Identity must be fresh across reuse. Facts arriving later have
    different keys and cannot enter this frozen membership implicitly.
    """

    identity: bytes
    holder_identity: bytes
    epoch: EpochBinding
    records: tuple[LearningFact, ...]

    def __post_init__(self) -> None:
        _identity(self.identity)
        _identity(self.holder_identity)
        if not isinstance(self.epoch, EpochBinding):
            raise TypeError("claim needs the actual epoch even for an empty snapshot")
        if not isinstance(self.records, tuple) or not all(isinstance(f, LearningFact) for f in self.records):
            raise TypeError("claim needs an immutable tuple of copied facts")
        keys = tuple(f.key for f in self.records)
        if len(set(keys)) != len(keys):
            raise ValueError("claim contains the same exact record more than once")
        if any(f.epoch.identity != self.epoch.identity for f in self.records):
            raise ValueError("an actual consumer claim belongs to one exact epoch")


class MergeDisposition(Enum):
    MERGED = "ordinary_observation_in_cumulative_input"
    NON_OBSERVATION = "feedback_has_no_compiler_observation"
    ENTRY_NOT_SUCCESSFUL = "entry_result_has_no_successful_source_exit"
    FOREIGN_EPOCH = "fact_belongs_to_another_epoch"
    SOURCE_INPUT_MISMATCH = "source_version_configuration_load_or_bytes_differ"
    PRODUCER_IDENTITY_MISMATCH = "durable_producer_identity_was_reused"
    CLOSED_EPOCH_LATE = "fact_arrived_after_epoch_learning_closed"


@dataclass(frozen=True)
class RecordedFact:
    fact: LearningFact
    feedback: FeedbackDisposition
    merge: MergeDisposition


class FactIdentityConflict(ValueError):
    """Reject changed data without replacing the retained pending record."""

    def __init__(self, retained: LearningFact, incoming: LearningFact):
        self.retained = retained
        self.incoming = incoming
        super().__init__("an exact fact key was reused with different immutable data")


@dataclass(frozen=True)
class CandidateBinding:
    """Caller mapping to prepared descriptor/inputs, slot/base and update controls.

    update_identity maps the actual transaction object; update_owner_identity
    maps its exact owner token. Controls can be named before CLOSING; constructing
    a candidate never starts an update or retains executable storage.
    """

    identity: bytes
    slot_identity: bytes
    image_identity: bytes
    inputs_identity: bytes
    producer_identity: bytes
    update_identity: bytes
    update_owner_identity: bytes
    expected_old_image_identity: bytes | None

    def __post_init__(self) -> None:
        for value in (self.identity, self.slot_identity, self.image_identity,
                      self.inputs_identity, self.producer_identity,
                      self.update_identity, self.update_owner_identity):
            _identity(value)
        _optional_identity(self.expected_old_image_identity)
        if self.expected_old_image_identity == self.image_identity:
            raise ValueError("replacement candidate must differ from its expected old image")


@dataclass(frozen=True)
class CandidateFact:
    claim_identity: bytes
    key: FactKey
    recorded: RecordedFact
    planning: ObservationOutcome | None
    emission: EmissionOutcome | None


@dataclass(frozen=True)
class CandidateClaimInput:
    """Exact compiler-input records passed to one kernel publication ticket."""

    claim_identity: bytes
    claim_holder_identity: bytes
    keys: tuple[FactKey, ...]


@dataclass(frozen=True)
class LearningCandidate:
    binding: CandidateBinding
    epoch: EpochBinding
    claims: tuple[ConsumerClaim, ...]
    facts: tuple[CandidateFact, ...]
    claim_inputs: tuple[CandidateClaimInput, ...]
    compilation: CompilationPlan
    lowered: LoweredImage
    artifact: ImageArtifact


@dataclass(frozen=True)
class CommittedUpdateReceipt:
    """Copied evidence from an actual completed exact kernel update receipt.

    Construct only after actual try_commit success, pointer replacement and RCU
    grace, using its actual returned-old value. These fields are correlations,
    never a method for causing/proving kernel publication from host scalars.
    """

    identity: bytes
    slot_identity: bytes
    update_identity: bytes
    update_owner_identity: bytes
    expected_old_image_identity: bytes | None
    candidate_image_identity: bytes
    returned_old_image_identity: bytes | None

    def __post_init__(self) -> None:
        for value in (self.identity, self.slot_identity, self.update_identity,
                      self.update_owner_identity, self.candidate_image_identity):
            _identity(value)
        _optional_identity(self.expected_old_image_identity)
        _optional_identity(self.returned_old_image_identity)
        if self.returned_old_image_identity != self.expected_old_image_identity:
            raise ValueError("actual returned old image differs from the exact expected base")


@dataclass(frozen=True)
class PublicationReceipt:
    """One actual committed kernel feedback ticket for one included claim.

    emission must be the SAME artifact receipt object, whose generated C receipt
    was mapped to the actual ticket. claim and holder name that actual retained
    kernel claim. No published boolean or construction-only receipt suffices.
    """

    identity: bytes
    candidate: CandidateBinding
    epoch: EpochBinding
    claim_identity: bytes
    claim_holder_identity: bytes
    included_keys: tuple[FactKey, ...]
    emission: EmissionReceipt
    update: CommittedUpdateReceipt

    def __post_init__(self) -> None:
        for value in (self.identity, self.claim_identity, self.claim_holder_identity):
            _identity(value)
        if not isinstance(self.candidate, CandidateBinding) or not isinstance(self.epoch, EpochBinding):
            raise TypeError("publication requires exact candidate and source epoch")
        if not isinstance(self.emission, EmissionReceipt) or not isinstance(self.update, CommittedUpdateReceipt):
            raise TypeError("publication requires construction and actual committed-update receipts")
        if (not isinstance(self.included_keys, tuple)
                or not all(isinstance(k, FactKey) for k in self.included_keys)
                or len(set(self.included_keys)) != len(self.included_keys)):
            raise ValueError("publication needs an immutable unique included-key selection")
        if self.identity != self.update.identity:
            raise ValueError("publication identity must name the actual committed ticket receipt")


@dataclass(frozen=True)
class AckSelection:
    """Frozen intended ACK subset, with no acknowledgment side effect.

    Historical selection is retained after ACK/end; it is never permission to
    repeat a kernel ACK or use an ended claim.
    """

    publication_identity: bytes
    candidate_identity: bytes
    claim_identity: bytes
    claim_holder_identity: bytes
    keys: tuple[FactKey, ...]


@dataclass(frozen=True)
class AcknowledgmentReceipt:
    """Copied actual kernel ACK result, independently of code publication."""

    identity: bytes
    publication_identity: bytes
    claim_identity: bytes
    claim_holder_identity: bytes
    keys: tuple[FactKey, ...]

    def __post_init__(self) -> None:
        for value in (self.identity, self.publication_identity,
                      self.claim_identity, self.claim_holder_identity):
            _identity(value)
        if not isinstance(self.keys, tuple) or not all(isinstance(k, FactKey) for k in self.keys):
            raise TypeError("ACK requires an immutable tuple of exact record keys")
        if len(set(self.keys)) != len(self.keys):
            raise ValueError("ACK repeats an exact record key")


@dataclass(frozen=True)
class FactState:
    recorded: RecordedFact
    candidate_identities: tuple[bytes, ...]
    input_candidate_identities: tuple[bytes, ...]
    emitted_candidate_identities: tuple[bytes, ...]
    publication_identities: tuple[bytes, ...]
    acknowledgment_identities: tuple[bytes, ...]


def _same_fact(first: LearningFact, second: LearningFact) -> bool:
    # Do not invoke backend instruction equality or infer provenance from equal
    # assembly strings. The retained host producer association must be exact.
    return (
        first.key == second.key and first.producer_identity == second.producer_identity
        and first.image_identity == second.image_identity and first.epoch == second.epoch
        and first.producer is second.producer and first.exit == second.exit
        and first.entry_result == second.entry_result and first.classification is second.classification
    )


def _same_claim(first: ConsumerClaim, second: ConsumerClaim) -> bool:
    return (first.identity == second.identity and first.holder_identity == second.holder_identity
            and first.epoch == second.epoch
            and len(first.records) == len(second.records)
            and all(_same_fact(a, b) for a, b in zip(first.records, second.records)))


def candidate_input_keys(candidate: LearningCandidate, claim_identity: bytes) -> tuple[FactKey, ...]:
    """Map only these exact frozen keys to the kernel ticket included array.

    All claim records remain visible in candidate.facts, but late/invalid and
    nonobservation records must not be submitted merely because another record
    has the same emitted source/target pair. Uncovered MERGED inputs stay in this
    selection; the exact emission receipt later determines its ACK subset.
    """
    if not isinstance(candidate, LearningCandidate):
        raise TypeError("candidate input selection requires an actual LearningCandidate")
    for selection in candidate.claim_inputs:
        if selection.claim_identity == claim_identity:
            return selection.keys
    raise KeyError(claim_identity)


class LearningCoordinator:
    """One finite epoch ledger. All methods require caller serialization.

    No method enables/disables runtime JIT/delegation or waits for translation.
    Claims and actual publisher/ACK controls stay externally retained while used.
    An epoch can close learning without redirecting its pending/late facts into
    a new version. Existing candidates can still reconcile their exact receipts.
    """

    def __init__(self, epoch: EpochBinding, snapshot: SourceSnapshot, limits: LearningLimits):
        if not isinstance(epoch, EpochBinding) or not isinstance(snapshot, SourceSnapshot):
            raise TypeError("learning requires one exact epoch and source snapshot")
        if not isinstance(limits, LearningLimits):
            raise TypeError("retained history limits must be explicit")
        if snapshot.version.encode("utf-8", errors="strict") != epoch.version:
            raise ValueError("snapshot and exact epoch version differ")
        self._epoch = epoch
        self._snapshot = snapshot
        self._limits = limits
        self._closed = False
        self._records: dict[FactKey, RecordedFact] = {}
        self._claims: dict[bytes, ConsumerClaim] = {}
        self._active_claims: dict[FactKey, bytes] = {}
        self._ended_claims: set[bytes] = set()
        self._producers: dict[bytes, LearningFact] = {}
        self._candidates: dict[bytes, LearningCandidate] = {}
        self._publications: dict[bytes, PublicationReceipt] = {}
        self._acknowledgments: dict[bytes, AcknowledgmentReceipt] = {}
        self._acked: dict[FactKey, bytes] = {}
        self._publication_acks: dict[bytes, bytes] = {}

    @property
    def epoch(self) -> EpochBinding:
        return self._epoch

    @property
    def snapshot(self) -> SourceSnapshot:
        return self._snapshot

    @property
    def closed(self) -> bool:
        return self._closed

    def close_epoch(self) -> None:
        """Stop future merges/construction; preserve every old pending record."""
        self._closed = True

    def _capacity(self, resource: str, retained: int, requested: int) -> None:
        limit = getattr(self._limits, resource)
        if retained + requested > limit:
            raise LearningCapacityError(resource, limit, retained, requested)

    def _merge_disposition(self, fact: LearningFact, feedback: FeedbackDisposition,
                           producers: dict[bytes, LearningFact]) -> MergeDisposition:
        for candidate in self._candidates.values():
            if candidate.binding.producer_identity == fact.producer_identity and (
                candidate.lowered is not fact.producer
                or candidate.binding.image_identity != fact.image_identity
                or candidate.epoch != fact.epoch
            ):
                return MergeDisposition.PRODUCER_IDENTITY_MISMATCH
        previous = producers.get(fact.producer_identity)
        if previous is not None and (
            previous.producer is not fact.producer or previous.image_identity != fact.image_identity
            or previous.epoch != fact.epoch
        ):
            return MergeDisposition.PRODUCER_IDENTITY_MISMATCH
        if fact.epoch.identity != self._epoch.identity:
            return MergeDisposition.FOREIGN_EPOCH
        source = fact.producer.compilation.snapshot
        if (fact.epoch != self._epoch or source.version != self._snapshot.version
                or source.sites != self._snapshot.sites
                or fact.producer.entry.current_task_gs_offset != self._epoch.current_task_gs_offset):
            return MergeDisposition.SOURCE_INPUT_MISMATCH
        try:
            # Check shared supplied bytes; do not add source regions or silently
            # fill gaps in the coordinator's finite caller-supplied snapshot.
            SourceSnapshot(self._snapshot.version, self._snapshot.regions + source.regions,
                           self._snapshot.sites)
        except ValueError:
            return MergeDisposition.SOURCE_INPUT_MISMATCH
        if self._closed:
            return MergeDisposition.CLOSED_EPOCH_LATE
        if fact.entry_result != 0:
            return MergeDisposition.ENTRY_NOT_SUCCESSFUL
        if feedback.observation is None:
            return MergeDisposition.NON_OBSERVATION
        return MergeDisposition.MERGED

    def record_claim(self, claim: ConsumerClaim) -> tuple[RecordedFact, ...]:
        """Retain actual claim membership, then cumulatively merge before build.

        All checks precede mutation. Identity conflicts preserve the old record
        and return both immutable facts in FactIdentityConflict. Semantically
        invalid, nonobservation, foreign and late facts are normal retained data.
        """
        if not isinstance(claim, ConsumerClaim):
            raise TypeError("recording requires an actual copied consumer claim")
        previous_claim = self._claims.get(claim.identity)
        if previous_claim is not None:
            if not _same_claim(previous_claim, claim):
                raise ValueError("claim identity was reused with different immutable membership")
            return tuple(self._records[f.key] for f in claim.records)
        new = tuple(f for f in claim.records if f.key not in self._records)
        self._capacity("claims", len(self._claims), 1)
        self._capacity("records", len(self._records), len(new))
        for fact in claim.records:
            old = self._records.get(fact.key)
            if old is not None and not _same_fact(old.fact, fact):
                raise FactIdentityConflict(old.fact, fact)
            if fact.key in self._active_claims or fact.key in self._acked:
                raise ValueError("record is already actively claimed or acknowledged")
        producers = dict(self._producers)
        additions: dict[FactKey, RecordedFact] = {}
        observations = []
        for fact in new:
            feedback = adapt_runtime_exit(fact.exit, fact.producer, fact.epoch.version, fact.classification)
            merge = self._merge_disposition(fact, feedback, producers)
            additions[fact.key] = RecordedFact(fact, feedback, merge)
            producers.setdefault(fact.producer_identity, fact)
            if merge is MergeDisposition.MERGED:
                observations.append(feedback.observation)
        snapshot = self._snapshot.with_observed_targets(tuple(observations))
        self._records.update(additions)
        self._producers = producers
        self._snapshot = snapshot
        self._claims[claim.identity] = claim
        for fact in claim.records:
            self._active_claims[fact.key] = claim.identity
        return tuple(self._records[f.key] for f in claim.records)

    def end_claim(self, claim_identity: bytes, holder_identity: bytes) -> None:
        """Record actual completed kernel claim_end; do not perform it here.

        Unacknowledged exact records remain pending and can be claimed again
        under a fresh claim identity. Historical candidates/claims remain frozen.
        """
        claim = self._claims[claim_identity]
        if claim.holder_identity != holder_identity:
            raise ValueError("claim_end holder differs from the exact claim")
        if claim_identity in self._ended_claims:
            return
        for fact in claim.records:
            if self._active_claims.get(fact.key) != claim_identity:
                raise ValueError("claim no longer owns an exact included reservation")
        for fact in claim.records:
            del self._active_claims[fact.key]
        self._ended_claims.add(claim_identity)

    def construct_candidate(
        self, binding: CandidateBinding, claim_identities: tuple[bytes, ...], *,
        entry: int, discovery_limits: DiscoveryLimits, entry_metadata: EntryMetadata,
        codegen_limits: CodegenLimits, descriptor_symbol: str,
        source_identity_symbol: str, feedback_producer_symbol: str,
    ) -> LearningCandidate:
        """Run discovery -> plan -> lower -> export on cumulative merged input.

        Budgets are caller inputs; DiscoveryLimits retains its selected default
        of five direct CALL discovery edges. No indirect-depth cap is added.
        Construction errors leave claims/facts/input intact and issue no ACK.
        Caller mapping of binding to the eventual loaded descriptor/inputs and
        generated receipt is required before an actual publication receipt.
        """
        if self._closed:
            raise ValueError("cannot construct a new candidate for a closed epoch")
        if not isinstance(binding, CandidateBinding) or binding.identity in self._candidates:
            raise ValueError("candidate requires a fresh exact binding")
        if not isinstance(claim_identities, tuple) or len(set(claim_identities)) != len(claim_identities):
            raise ValueError("candidate claim identities must be an exact unique tuple")
        self._capacity("candidates", len(self._candidates), 1)
        claims = tuple(self._claims[identity] for identity in claim_identities)
        for claim in claims:
            if claim.identity in self._ended_claims or claim.epoch != self._epoch:
                raise ValueError("candidate needs a still-retained claim from this exact epoch")
        if any(c.binding.producer_identity == binding.producer_identity
               for c in self._candidates.values()):
            raise ValueError("candidate durable producer identity was reused")
        if binding.producer_identity in self._producers:
            raise ValueError("candidate producer identity already names retained feedback metadata")
        if entry_metadata.current_task_gs_offset != self._epoch.current_task_gs_offset:
            raise ValueError("candidate GS input differs from its exact epoch")
        snapshot = self._snapshot
        plan = compile_fragment_plan(snapshot, entry, discovery_limits)
        lowered = lower_compilation(plan, entry_metadata, codegen_limits)
        artifact = export_image(lowered, descriptor_symbol=descriptor_symbol,
                                source_identity_symbol=source_identity_symbol,
                                feedback_producer_symbol=feedback_producer_symbol)
        facts = []
        for claim in claims:
            for fact in claim.records:
                recorded = self._records[fact.key]
                observation = (recorded.feedback.observation
                               if recorded.merge is MergeDisposition.MERGED else None)
                facts.append(CandidateFact(
                    claim.identity, fact.key, recorded,
                    plan.observation_outcomes.get(observation),
                    artifact.receipt.outcomes.get(observation),
                ))
        inputs = tuple(CandidateClaimInput(
            claim.identity, claim.holder_identity,
            tuple(item.key for item in facts if item.claim_identity == claim.identity
                  and item.recorded.merge is MergeDisposition.MERGED),
        ) for claim in claims)
        candidate = LearningCandidate(binding, self._epoch, claims, tuple(facts),
                                      inputs, plan, lowered, artifact)
        self._candidates[binding.identity] = candidate
        return candidate

    def record_publication(self, receipt: PublicationReceipt) -> AckSelection:
        """Reconcile actual COMMITTED evidence; this performs NO acknowledgment."""
        if not isinstance(receipt, PublicationReceipt):
            raise TypeError("actual publication requires its exact typed receipt")
        previous = self._publications.get(receipt.identity)
        if previous is not None:
            if previous is not receipt:
                raise ValueError("publication identity was reused for another receipt object")
            return self.ack_selection(receipt.identity)
        candidate = self._candidates[receipt.candidate.identity]
        if receipt.candidate != candidate.binding or receipt.epoch != candidate.epoch:
            raise ValueError("publication descriptor/inputs/producer/source binding differs")
        if receipt.emission is not candidate.artifact.receipt:
            raise ValueError("publication lacks this exact candidate artifact receipt")
        update = receipt.update
        if (update.update_identity != candidate.binding.update_identity
                or update.update_owner_identity != candidate.binding.update_owner_identity
                or update.slot_identity != candidate.binding.slot_identity
                or update.expected_old_image_identity != candidate.binding.expected_old_image_identity
                or update.candidate_image_identity != candidate.binding.image_identity):
            raise ValueError("actual slot/update old/new identities differ from prepared candidate")
        claim = self._claims[receipt.claim_identity]
        if (not any(c is claim for c in candidate.claims)
                or claim.holder_identity != receipt.claim_holder_identity
                or claim.identity in self._ended_claims):
            raise ValueError("publication ticket differs from an exact retained included claim")
        if receipt.included_keys != candidate_input_keys(candidate, claim.identity):
            raise ValueError("publication included records differ from frozen merged candidate input")
        self._capacity("publications", len(self._publications), 1)
        self._publications[receipt.identity] = receipt
        return self.ack_selection(receipt.identity)

    def ack_selection(self, publication_identity: bytes) -> AckSelection:
        """Return this ticket's frozen exact included-and-emitted ACK subset."""
        publication = self._publications[publication_identity]
        candidate = self._candidates[publication.candidate.identity]
        keys = tuple(
            item.key for item in candidate.facts
            if item.claim_identity == publication.claim_identity
            and item.key in publication.included_keys
            and item.recorded.merge is MergeDisposition.MERGED
            and item.recorded.feedback.observation in publication.emission.emitted_observations
            and item.emission is EmissionOutcome.EMITTED
        )
        return AckSelection(publication.identity, candidate.binding.identity,
                            publication.claim_identity, publication.claim_holder_identity, keys)

    def confirm_ack(self, receipt: AcknowledgmentReceipt) -> tuple[FactKey, ...]:
        """Record only keys returned by the actual kernel ACK, never all inputs."""
        if not isinstance(receipt, AcknowledgmentReceipt):
            raise TypeError("acknowledgment requires an actual typed ACK receipt")
        previous = self._acknowledgments.get(receipt.identity)
        if previous is not None:
            if previous != receipt:
                raise ValueError("ACK identity was reused with another immutable result")
            return previous.keys
        if receipt.publication_identity in self._publication_acks:
            raise ValueError("publication already has a different actual ACK receipt")
        selection = self.ack_selection(receipt.publication_identity)
        if (receipt.claim_identity != selection.claim_identity
                or receipt.claim_holder_identity != selection.claim_holder_identity
                or receipt.claim_identity in self._ended_claims):
            raise ValueError("ACK publication/claim/holder association differs")
        eligible = set(selection.keys)
        if set(receipt.keys) != eligible:
            raise ValueError("ACK differs from the exact atomic included-and-emitted subset")
        for key in receipt.keys:
            if self._active_claims.get(key) != receipt.claim_identity or key in self._acked:
                raise ValueError("ACK claim no longer owns an unacknowledged exact reservation")
        self._capacity("acknowledgments", len(self._acknowledgments), 1)
        self._acknowledgments[receipt.identity] = receipt
        self._publication_acks[receipt.publication_identity] = receipt.identity
        for key in receipt.keys:
            self._acked[key] = receipt.identity
        return receipt.keys

    def pending_keys(self) -> tuple[FactKey, ...]:
        """All unacknowledged records, including invalid/nonobservation/late data."""
        return tuple(key for key in self._records if key not in self._acked)

    def facts(self) -> tuple[FactState, ...]:
        """Immutable separate recorded/merged/candidate/emitted/published/ACK views."""
        states = []
        for key, recorded in self._records.items():
            included = tuple(candidate for candidate in self._candidates.values()
                             if any(item.key == key for item in candidate.facts))
            inputs = tuple(candidate.binding.identity for candidate in included
                           if any(key in selection.keys for selection in candidate.claim_inputs))
            emitted = tuple(candidate.binding.identity for candidate in included
                            if any(item.key == key and item.emission is EmissionOutcome.EMITTED
                                   for item in candidate.facts))
            included_ids = {candidate.binding.identity for candidate in included}
            publications = tuple(
                receipt.identity for receipt in self._publications.values()
                if key in receipt.included_keys and receipt.candidate.identity in included_ids
            )
            acknowledgments = (self._acked[key],) if key in self._acked else ()
            states.append(FactState(recorded, tuple(c.binding.identity for c in included),
                                    inputs, emitted, publications, acknowledgments))
        return tuple(states)
