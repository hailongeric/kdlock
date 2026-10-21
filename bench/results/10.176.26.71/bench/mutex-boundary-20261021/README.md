# Setup and measurement-boundary feasibility, 2026-10-21

Status: focused diagnostic in progress; no timing or acceptance authorized by
this diagnostic. Fresh checks on clean `98f9ea9` found no competing repository
writer and the same drained recovery VM, boot
`88449cfc-cea9-4647-a294-bc601e372146`, kernel `6.1.159-kdclobber2`, 73 original
runtime modules. Main agent alone writes and executes VM work; helpers review
read-only. Recovery artifacts and all earlier evidence remain intact.

The preceding [phase controls](../qemu-workers-20261021/README.md) establish that
all six observed extra workers existed before the measured command, not their
cause or absence of interference. This stage asks whether the established
control connection can retain a prepared session while host workers naturally
retire, then pass the unchanged full gate without fresh guest SSH/setup.

The first probe keeps original frozen OUTER/provider/client/translator bytes,
ordinary preparation and exactly one original five-worker warmup. It then
observes the full original gate at spaced, bounded points while the client is
quiescent. No timed command will be sent. The same held client/source/provider
must pass publication, counter stability, business and exact retirement checks.
Refusal or failure remains evidence, not a pass.

A post-warmup wait changes elapsed time since hotlock sampling, cache residency
and scheduling history. Hotlock heat is sampled on contention, not reset by a
wall-clock timer; idle time can affect the next comparison. Rewarming would be
an additional workload and may recreate host activity. Therefore this probe
does not preserve the previous timing preparation contract and cannot produce
comparable rates, even if the full boundary gate passes. It measures feasibility
and preserves an explicit changed-contract label.

Use one persistent guest connection and one persistent read-only host observer.
Host accounting samples are spaced five seconds apart; full-gate captures use
bounded 0/15/30/60/120-second observation points. Record capture CPU/wall cost,
causal reply brackets, worker TID/start ticks and missing tails. Snapshot queries
and guest validation themselves are observations, not proof of zero overhead.
All original gate conditions remain required; a count of 67 alone is insufficient.

All seven regression causes and acquisition latency remain unresolved. The
unlock derivative remains the whole routing/control-flow transformation,
including removed native cookie bytes and changed generated code. Earlier six
paired results remain unaccepted; complete-operation p95 is separate. Readers
remain local/concurrent, mmap and page-fault tasks separate, and unsupported
TCLock comparisons excluded.
