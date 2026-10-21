# OUTER acquisition with general unlock diagnostic, 2026-10-21

Status: **implementation and correctness validation in progress; no performance
acceptance.** This is the focused control specified by the
[previous evidence review](../mutex-causal-boundary-20261021/README.md).

The main agent is the sole writer and VM executor. Fresh inspection found a
clean `master` at `0f38cf3`, no writable project file descriptors or Git lock,
and the same idle VM on `6.1.159-kdclobber2`, boot
`88449cfc-cea9-4647-a294-bc601e372146`, with its original 73 modules. Both helpers
are read-only and have touched no files. The recovery path and completed
organization/kernel-integration work remain preserved.

## Fixed host observation

Three read-only QEMU snapshots, separated by ten seconds, recorded 73, 72 and
71 tasks at `10:11:03.965592`, `10:11:14.465284` and `10:11:24.919213 UTC`.
Workers exited naturally while other worker identities accumulated CPU/I/O
activity; all observed extra workers were pinned to CPU 63. This fixed
observation was not extended until a favorable count appeared. It changes
neither the failed historical 100-thread endpoint nor the later 74-thread
observation. Missing historical interference cannot be reconstructed.

Raw receipts are under
[`raw/bench/pipecap-unlock-20261021`](../../raw/bench/pipecap-unlock-20261021/).
Lifetime identity requires matching TID and start ticks in the retained raw
stat reads. Differences cover only surviving observed tasks and omit missed
births/deaths and departed tails. Sleeping snapshots do not imply inactivity
between reads. No settings, affinities, tracing or unknown processes changed.

## Diagnostic identity and correctness gates

The derivative changes exactly one macro in the frozen baseline pipecap source:
`KD_MUTEX_OUTER_UNLOCK(&kd_lock, cookie)` becomes
`KD_MUTEX_DIRECT_UNLOCK(&kd_lock)`. The OUTER acquisition macro, including its
source cookie writes, remains unchanged. The compiler removes the unused
route-result copy; both actual capture sequences preserve ABI2. The original
bundle and artifacts are immutable.
The builder retains the original provider, headers, daemon, translator, client,
body, n16 and placement. Existing retained symbol metadata is checked against
the exact original provider's CRC words; no rebuilt provider may be loaded.
The actual workload ELF must pass control-call/capture, import, symbol-version
and mutex-object placement checks before live use. Compiler spill/layout changes
are retained as diagnostic differences, not interpreted as instruction timing.

Before timing, run both basic programs and the affected resource, actual macro,
task-cache, gate-state, clobber-return and remote-owner/ACK tests serially in the
VM. Additional cases exercise physical ownership after scheduler restoration,
unrelated live/borrowed ownership and the actual native matcher. Existing checks
for gate release ordering, generated COMPLETE/FULL returns, node retirement and
ACK ordering remain. A substitute fixture is not evidence of live concurrency.
Then require derivative syscall correctness, returned-body evidence and exact
source retirement in the existing VM. Preserve every failure and its source.

Only successful correctness and a fresh unchanged 67-thread environment gate
permit the planned six timing sessions: three derivative repetitions paired
with three fresh original OUTER controls, alternating pair order. Keep the
original two-second duration, warmup, collection settings and `jit_timing=0`.
No owner polling, in-lock clocks or boundary-counter pauses are added. Inspect
execution class and returned fraction separately; no mixed-path rate is a
matched-path overhead result. A changed delegation mix may establish sufficiency
of this unlock shell under the observed conditions, not a production fix.

All seven mutex causes remain unresolved. Complete-operation p95 remains
separate from unresolved acquisition latency. Concurrent local readers,
separate mmap/page-fault tasks and exclusion of unsupported TCLock MM bodies
remain unchanged.

## Implementation and basic validation

`b513663` adds the isolated workload builder and affected ownership/ABI fixtures;
`820b251` adds the serial correctness/timing driver and actual-ELF rejection
checks. Neither changes the production protocol. `checks-1` passed both basic
programs and all six selected drivers in the VM. Both unlock variants also
passed the actual macro/generated-code checks against the frozen original
headers. The fixture result is separate from the pending live owner/ACK and
syscall checks.

`inputs-1` built successfully with manifest SHA256
`daf7f77beda2704d9cc56291f9864489f733c844f6188cd6c8198480539badae`.
Only the planned workload macro and its binary change; original provider,
headers, translator and client remain fixed. Both actual ELFs pass the audit,
and three corrupted copies are rejected: wrong hot RIP, wrong mutex size, and
damaged unlock capture. No corrupted ELF was loaded. The full caller body
changes from 203 to 188 bytes; business-body assembly inspection is separate
from these structural checks. Actual loaded cacheline placement remains a live
gate, because section-relative placement alone is insufficient.

The host observation before the live task probe at `10:31:13.461481 UTC` found
76 threads, with verified pins and the recovery snapshot still present. This
does not qualify for timing; correctness can proceed independently. A later
timing attempt still requires a fresh strict 67-thread comparison. Read-only
review also caught a missing fixed-hash check for the original three environment
receipts in the new runner; it is restored before any live syscall session.

Read-only assembly review found byte-identical business computation at
`0x13c–0x151`, unchanged stack frame and spills, and unchanged acquisition probes
apart from branch displacements. The 15 removed bytes are the cookie test/branch
(5), route-result copy (3), and local-unlock call/return jump (7). This diagnostic
therefore measures the entire unlock-shell transformation, including changed
control flow and layout; it cannot isolate provider-only cycles.

`task-1` did not execute its tests: module insertion failed with a reserved
per-CPU allocation error for 7592 bytes. The logs and original module are
retained; inspection found no KD module resident. The planned single allocator
refresh uses the existing page-sized helper's normal allocation/free path and
unloads it before retrying the unchanged provider. This preparation is separate
from correctness and never counts as a test pass.
