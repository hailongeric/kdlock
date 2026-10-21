# Unlock-route paired timing follow-up, 2026-10-21

Status: **waiting for the unchanged host gate; no acceptance.** The completed
[correctness stage](../pipecap-unlock-20261021/README.md) and its sealed archives
remain immutable. The main agent is the only writer and VM executor; helpers
perform read-only source/evidence review and report no files touched.

Fresh ownership checks found clean `master` at `2fb3cf0`, no writable project
descriptors or Git lock, and the same idle recovery VM with its original 73
modules and boot `88449cfc-cea9-4647-a294-bc601e372146`. No kernel or host setting
changes are part of this follow-up.

Observation 0 at `10:53:29.631645 UTC` found 71 QEMU threads with correct pins
and the actual recovery snapshot present. The later lifetime capture at
`10:54:13.875169 UTC` found 67 threads and no workers. Those extra identities
exited before their activity accounting was captured; no departed activity or
historical interference can be reconstructed. This later diagnostic snapshot
does not repair the first rejected observation or qualify as a full timing gate.

Observations use bounded read-only commands, at least 60 seconds apart, with
longer backoff if the same gate continues to fail. Extra-worker lifetime,
scheduler and I/O evidence is collected when present. Sleeping snapshots or
zero observed tick deltas are not proof of no work. Earlier 100-, 74- and
68-thread failures remain intact.

When the full original gate passes, run exactly three serial pairs with the
validated derivative and fresh original OUTER control: OUTER/general,
general/OUTER, OUTER/general. Keep the original frozen provider, source/ELF
bindings, five workers on CPUs 0–4, collector 63, n16, two-second measurement,
48,000 plus one-second warmup, 300-ms peak/settle, 10-ms samples, and
`jit_timing=0`. Preserve actual mutex offset 32 modulo 64. Capture the immediate
post-run host endpoint outside the guest runner. All sessions and failed
attempts are retained; no replacement repetition is selected.

The four completed syscall correctness sessions remain separate. New rates
compare the whole unlock-route transformation, including 15 removed cookie
routing bytes and changed layout/control flow. Report every rate, paired ratio,
execution class and returned fraction, plus sample variance. Mixed execution
classes or fractions do not isolate provider-call overhead. All seven causal
regressions and acquisition latency remain unresolved. Concurrent local readers,
separate mmap/page-fault tasks and exclusion of unsupported TCLock bodies stay
unchanged.
