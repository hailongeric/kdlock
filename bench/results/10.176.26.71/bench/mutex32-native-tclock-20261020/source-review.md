# Static protocol and collection review

The collection retains the production implementation from
`752fec1e5cbb0d54144fa995987424afabf11b46`. The later collection revision changes
documentation and evidence helpers; exact source manifests and the archive audit
must establish that production identity. This review does not substitute for
VM builds, tests, workload outcomes, or archive verification.

## Physical ownership and node lifetimes

The mutex remains 32 bytes with native 8-byte alignment. Its owner, sleeping
wait lock/ring, OSQ tail, delegation phase and delegation tail are embedded.
Four preallocated 320-byte, 64-byte-aligned slots per CPU contain the saved
request, exact waiter record, packet and a separate 24-byte OSQ subrecord.
Both queue tails encode CPU/slot identities directly; their links and
notifications remain independent.

An initial delegation head explicitly lends its reservation for optimistic
physical acquisition. Ordinary physical spinners reserve a temporary slot.
Cancellation or unlock finishes the OSQ unlink/handoff before marking that
membership IDLE; temporary release precedes any scheduling. Borrowed nodes keep
their delegation reservation, packet and count record through physical sleeping
acquisition. Exhaustion uses the existing sleeping path. OSQ grant does not
grant physical mutex ownership. The actual owner-word acquisition, gate phase,
source leases, execution frames, admission checks and unlock ACKs remain exact.

NUMA selection has a finite 64-node scan budget. At 256 bodies, or earlier
terminal-link exhaustion, eight or more deferred requests receive the next
queue-head handoff after rejoining the complete prefix. That wake does not
itself release the physical mutex. Smaller prefixes are serviced by the current
owner, then further selection is FIFO. The total batch cap remains 1024.
Refusal, native completion, delayed-link retirement and early outer release
keep their independent boundaries. The cohort bound limits selection bypass,
not elapsed wait time; scan exhaustion can leave nonlocal requests in a cohort.

## Workload and evidence boundaries

The seven collections are c01/post64, c08/post64, exclusive-update RCUHT,
SEEK_SET n16, SEEK_END n16, pipebytes/query n16 and pipecap/query n16. All use
fresh Native, TCLock and KD arms with nine recorded worker counts and three
repetitions. Native uses Linux mutex exclusion; TCLock and KD use their own
objects and protocols. The controlled API objects have no independently running
unconverted consumers. This does not establish whole-kernel replacement.

Synthetic `jit_bodies` witnesses generated-body entry only. Its legacy PASS
label is not a returned-completion count. Real API probes separately count
matching returned bodies, preserving returned, partial and no-entry classes.
TCLock's own delegation observations have separate semantics and are not KD JIT
evidence. Source hashes bind the unchanged historical metadata labels to the
current implementation; old receipts are not relabelled.

`run-checks.py` freezes all inputs needed by the two basic programs, provider
and daemon builds, and the four selected benchmark test programs. It verifies
frozen/current hashes and idle state around each command. This is the directly
affected benchmark/documentation scope, not a fresh rerun of earlier protocol
fixtures or live probes.

`run-matrix.py` delegates per-collection source/binary freezing to the maintained
runners. It requires the complete backend/worker/repetition inventory and final
drain. The only accepted nonzero collection exit is the original, explicitly
enumerated set of drained synthetic NO_JIT rejections whose data oracle passed.
Their failure verdicts and unscored status remain intact. Other failures and
timeouts stop collection without inferring drain or forcing cleanup. Exact
cross-collection source binding remains an independent finalization/audit duty.

## Review limits

Static inspection found no new queue-lifetime or collector-acceptance defect.
The benchmark helpers do not alter production protocol or execution probes.
Nine worker counts are a focused grid; backend-order rotation does not make
sequential workload blocks randomized paired trials. Three-repetition ranges
are descriptive, not confidence intervals. Different KD execution classes must
remain separate in tables and plots, including gaps between their scaling lines.
No throughput, parity, full-suite, weak-memory or scheduler-fairness conclusion
follows from this source review.
