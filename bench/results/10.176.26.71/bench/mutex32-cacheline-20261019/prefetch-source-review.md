# Prefetch trial source review

Static review of `de3058864a7155bac2b0c9bbfbb4af92e096a872`, relative to
candidate `76af84414bd4548e11f60c67ae7174ec63644496`, finds no protocol or
lifetime change. This is a source review on `380G10`; it makes no claim about
the emitted instructions or performance of the trial. The existing
[candidate ELF review](code-review-manual.md) covers the preceding candidate,
not the two new hints.

The commit changes only `kernel_module/mutex/combiner.inc` (SHA-256
`11da3d53aff1e61bb0d590b7121ab5ebd45e95d6156b65d3f7c089fbdb84c383`) and
the terminal fixture (SHA-256
`846501499763aec0fb1ff84b4c245c1da79082f835e94b7941f203934f175347`).

The first `prefetch(lock)` follows the batch's fairness/selection decision
and precedes successor-link processing, batch-field preparation and the
existing successor prefetch. This provides independent work between the
read hint and `kd_mutex_execute_cs`'s authoritative owner/phase checks. The
combiner still holds physical exclusion at this point. An earlier iteration
that released the outer lock follows the existing reacquire-and-return path,
rather than continuing this loop without ownership.

The second read hint immediately follows `kd_jit_clobber_call_v1(&call)`.
Completion classification, optional timing/witness handling and frame checks
can overlap the owner-line fetch. It does not assume that the wrapper returned
COMPLETE: FULL/refused returns still use the unchanged dispatcher. Neither
the return classification nor frame retirement uses information supplied by
the hint. Both authoritative owner probes, PICKUP rejection, phase checks and
all frame/routing checks remain in place.

Both hints target the lock object, not a waiter that may already have been
woken and reused. The enclosing original lock invocation remains live until
the combiner finishes its queue work and returns to its own acquisition.
That existing caller lifetime covers the object even across a detached outer
batch, including the period before the original request reacquires it.
Prefetch adds no allocation, reference, published pointer or cleanup step.

`prefetch` is a read hint, not `prefetchw`, a lock acquisition, a barrier or an
ownership record. The 32-byte object and native alignment, source lease,
node publication/retirement, exact counts, unlock ACKs and wrapper ABI are
unchanged. The terminal fixture's sole adjustment substitutes a no-op for the
hardware hint; all assertions and negative controls remain. The outer-progress
fixture already provided that substitution.

The intended benefit is latency overlap, not removal of the shared line or
its contention. With native alignment, the gate may occupy a different line
from the owner, so `prefetch(lock)` does not promise to fetch the gate in every
containing layout. A hint may arrive too late, be invalidated before use,
consume resources or cause additional coherence traffic. The frozen VM checks
and separately scored comparisons determine whether retaining it is useful;
source inspection cannot establish a throughput gain.
