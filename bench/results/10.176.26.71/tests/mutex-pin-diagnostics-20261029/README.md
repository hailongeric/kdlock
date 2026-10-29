# Optional pin diagnostics

The first diagnostic source is
`cb4972200adf37b91875d6fbf1371b2b4816ba9d`, integrating the optional observations
from `97fbe88e743a41acb2b55d5891e89df1d6e3bc90` onto the validated circular
window. It does not include the separate notification-prefetch candidate.
Diagnostics remain disabled in ordinary builds. Mode 2 observes selected-window
occupancy, requests, consumption, cancellation, FULL dispatches and ACK polling;
optional one-in-64 ordered-TSC samples include timestamp/fence overhead and the
first ACK load. Instrumented throughput is not a performance score.

Two basic unit programs and eight affected drivers passed (10/10), including
all 32 profile-runner cases. Default-off mutex and rwsem basic each completed
1,600,000 operations with final idle; returned JIT counts were 1,586,851 and
1,589,101. The [retained results](initial-results.json) distinguish these checks
from the attempted instrumented run.

The [default-off ELF audit](default-off-elf-audit.json) found the same `.text`
size, all 4,415 relocations and 7,600-byte per-CPU section as the circular-window
basic provider. Only two debug-print line-number immediates changed. The hot
combiner, unpin and ABI entry code was unchanged; no diagnostic helper or
sampling storage survived the default-off build.

The first c01/20-worker mode-2 attempt failed **before workload execution**:
`insmod` returned `Cannot allocate memory`, and the kernel reported that the
7,984-byte, 128-byte-aligned static per-CPU allocation could not fit the reserved
module chunk. The controller stopped; c01/36 workers and the sampled arm did
not run. This is a preparation failure, not a pass or a zero counter observation.
The module never entered its initializer. No project workers or modules remained,
and archive-time idle was verified. No reset or kernel change was required.

Correction `6b97a00f3dbcad12a2690732069dd2411c15c4cd`, integrated and tested as
`4a46795e3f052282a5a0593f4cb85cf8e5901a05`, moves optional mode-2 storage to
one preallocated dynamic per-CPU allocation. Module-lifetime cleanup is
serialized against the parameter getter. Basic plus directly affected
allocation/cleanup, batch diagnostic and resource checks passed (5/5).
The [corrected default-off ELF](corrected-default-off-elf-audit.json) matches
all 135,567 code bytes and all 4,415 relocations of the earlier default-off
provider exactly. Its ordinary per-CPU storage remains 7,600 bytes.

Both corrected mode-2 providers compiled and loaded; their static per-CPU
sections also remain [7,600 bytes](corrected-provider-audit.json). Counter-only
and one-in-64 TSC arms each ran c01/20 and c01/36 once for two seconds, post256,
CPUs0..N-1 and collector63. Every run had correct data, matching JIT entry/return
counts and exact drain. These are unscored diagnostic observations, not an
ordinary throughput comparison. [Full receipts](corrected-results.json) retain
source, modes, policy, before/after snapshots and deltas.

| Mode | Workers | Consumed selections | Full window | ACK checks that polled | Mean sampled ACK-region cycles |
| --- | ---: | ---: | ---: | ---: | ---: |
| Counters | 20 | 6,644,456 | 99.703% | 0.0353% | Not sampled |
| Counters | 36 | 7,003,487 | 99.122% | 0.0979% | Not sampled |
| Sampled | 20 | 6,516,428 | 99.702% | 0.0362% | 179.13 |
| Sampled | 36 | 6,984,963 | 99.120% | 0.0739% | 116.11 |

All four observations have **zero cancelled selections, FULL resumes and
nonempty pin drains**. Requested equals consumed, independently of the exact
returned-body and retirement checks. Repeated FULL fallback/cancellation is
therefore absent from these measured intervals. The rolling window remains
populated; increasing its size is not justified by frequent empty-window or
polling evidence here. An immediately satisfied ACK still requires a cacheline
load. Sampled regions include fences/timestamps and are neither pure ACK
latency nor an attributable percentage of total runtime.

Source inspection identifies another cost to test: steady refill fetches one
new request's metadata several nodes ahead of the existing immediate-successor
preheat. A narrowly scoped metadata-prefetch ablation is being reviewed. This
is an inference, not a demonstrated cache-miss explanation. Neither these
diagnostics nor the earlier window candidates close the no-regression gate.

Both trees on boot `677b7afa-5358-4ece-a650-5f4a4adecd55` are preserved in four
archives. Their hashes and all 1,920 paths were
[verified offline](initial-archive-verification.json). Raw copies reside under
`bench/results/10.176.26.71/raw/tests/mutex-pin-diagnostics-20261029/`.
Guest roots are `tests/pin-diagnostics-20261029` and
`bench/pin-diagnostics-20261029` below `/root/kdlock-evidence/10.176.26.71/`.
The corrected `tests/pin-diagnostics-r2-20261029` and
`bench/pin-diagnostics-r2-20261029` trees are retained separately in four more
archives, with all 1,621 paths [verified offline](corrected-archive-verification.json).
Their raw copies are in the `corrected/` subdirectory of the same raw root.
