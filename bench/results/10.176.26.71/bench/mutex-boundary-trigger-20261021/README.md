# Accounting-triggered full boundary capture, 2026-10-21

Status: focused no-timing follow-up in progress. Fresh checks on clean
`824c6a1` found no repository writer or index lock; the same recovery VM was
drained with boot `88449cfc-cea9-4647-a294-bc601e372146`, kernel
`6.1.159-kdclobber2` and the original 73 modules. The main agent remains the
sole writer and VM executor; helpers review read-only.

The [previous bounded hold](../mutex-boundary-20261021/README.md) retained its
five full-capture refusals (75/75/70/68/68) despite eleven intervening accounting
scans with the original exact 67 identities. This follow-up asks whether a full
capture promptly requested from such a scan can pass while the prepared guest
state remains retained. The accounting scan is only a trigger. The unchanged
full host comparison and fresh guest comparison decide feasibility.

Keep one original warmup, the frozen provider/client/workload, one guest
connection and one observer connection. The guest runner and bounded hold
protocol are unchanged. A specified initial accounting scan anchors the original
67 TID/start-tick pairs. Only complete, matching before/after identities with
exact original TIDs/names/affinities and scans begun after the held marker can
trigger. Local queue residence must be at most two seconds; a separate check
requires host capture start within two seconds of host scan start. Different
clock domains are never subtracted from one another.

Observe at the existing five-second cadence. Permit at most four candidate
captures before 95 seconds, with at least 15 seconds after a refused capture
reply before another candidate. Reserve the 25-second request budget before
one unconditional terminal capture at 120 seconds. The full capture's existing
15-second internal deadline and guest's 210-second hold timeout remain in
force. Every candidate, refusal, error and actual request/reply bracket is
retained. Stale samples cannot qualify as prompt triggers even if the independent
full comparison passes. Coordination/state uncertainty retains resources;
verified safe completion uses normal unbind, retirement and drain.

No timed client command is permitted. Waiting after warmup changes admission
clock history and cache/scheduling conditions; any full pass proves only this
observed retained-boundary feasibility. It does not establish continuous
quiescence, original timing parity, variance or a performance gain. Account for
observer/capture overhead, non-atomic reads, missed lifetimes and departed tails.
All seven mutex regressions and acquisition latency remain unresolved;
complete-operation p95 is separate. Readers remain local/concurrent, mmap and
page fault remain separate, and unsupported TCLock bodies remain excluded.
