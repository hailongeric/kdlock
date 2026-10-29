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

The correction under development moves optional mode-2 storage to a single
preallocated dynamic per-CPU allocation, with module-lifetime cleanup and
serialization against the parameter getter. It must pass focused allocation,
cleanup, default-off and live diagnostic checks before interpreting counters.
Neither these diagnostics nor the earlier window candidates have closed the
mutex no-regression gate.

Both trees on boot `677b7afa-5358-4ece-a650-5f4a4adecd55` are preserved in four
archives. Their hashes and all 1,920 paths were
[verified offline](initial-archive-verification.json). Raw copies reside under
`bench/results/10.176.26.71/raw/tests/mutex-pin-diagnostics-20261029/`.
Guest roots are `tests/pin-diagnostics-20261029` and
`bench/pin-diagnostics-20261029` below `/root/kdlock-evidence/10.176.26.71/`.
