# Locality-256 source review

This independent static review covers commit
`752fec1e5cbb0d54144fa995987424afabf11b46`, relative to the shared-node/FIFO
candidate `f4d359d83e6b9ce54b4c4a10053f4e5c681ac204`. It reviews the production
combiner and terminal-fixture changes. No build, test, module, or VM command
was executed for this review; it makes no validation or performance claim.

The change retains the 64-node NUMA scan budget and 1024-body total cap. At
256 completed bodies, or earlier when the retained request has no successor
link, eight or more deferred requests trigger handoff. A smaller deferred
prefix is rejoined for execution under the current owner, with further NUMA
selection disabled for the rest of that batch. The shared OSQ/delegation pool,
32-byte mutex with 8-byte alignment, and separate membership lifetimes are
unchanged by this commit.

## Ordering and lifetime review

No ordering or retirement defect was found in the changed path. The loop saves
`next_node = curr_node` before checking the boundary. The large-prefix break
occurs before incrementing the execution count or executing that request.
The common exit rejoins the complete deferred prefix ahead of this still-live
request, then publishes HELD and wakes the new delegation head with a release
store. It neither retires the retained terminal tail nor permits a new publisher
to link into an already completed node.

This wake selects the next delegation head; it does not itself release the
physical mutex. The current physical owner still executes its own original
request and follows the existing unlock path. Small-prefix rejoin occurs before
execution and sets `numa_node = -1`, preserving FIFO service thereafter. Refusal,
native completion, early outer release, source leases, frame retirement, and
unlock ACKs retain their existing paths. No additional locks, reference counts,
hashes, or RCU mechanism are introduced.

## Fixture review

The source contains 20 terminal scenarios and 13 mutation controls. The changed
cases check eight deferred requests followed by exactly 256 completed bodies;
the 64-node scan limit; one- and seven-request prefixes rejoined after 256;
the unchanged total cap; refusal of the first rejoined request; and earlier
handoff on terminal-link exhaustion. For the 200-request all-remote case, nodes
0 through 63 are deferred, nodes 64 through 198 execute (135 bodies), and node
199 remains linked after the deferred prefix for handoff.

The controls cover a missing cohort bound, incorrect bounds of 128 and 512,
removed large-prefix handoff, continued NUMA bypass after rejoin, total-cap
overrun, and the pre-existing retirement, delayed-link, refusal-link, and gate
obligations. Static inspection found concrete failing assertions for these
changes and no extraction or declaration-order problem. This describes test
coverage and expected failures, not executed results.

## Limits and experiment rationale

The cohort bound limits selection bypass within a batch, not elapsed waiting
time or scheduler-independent starvation. Once the finite scan budget is
exhausted, executed requests need not be local; a deferred prefix can also span
multiple remote localities on systems with more than two NUMA nodes. Serial
fixture callbacks do not prove weak-memory behavior or real scheduling.

A 256-body trial is a conservative step from 128 before considering 512. The
longer FIFO candidate's larger observed batches did not translate into higher
throughput, so batch size alone cannot establish success. Any retained choice
requires separate VM evidence across pipe, c01, and seek, with source identities
kept distinct. This review does not attribute that earlier regression solely
to batching because the earlier candidate also changed OSQ storage.
