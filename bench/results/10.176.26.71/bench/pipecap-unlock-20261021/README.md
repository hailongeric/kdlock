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
`KD_MUTEX_DIRECT_UNLOCK(&kd_lock)`. OUTER acquisition, cookie writes and ABI2
continuation remain unchanged. The original bundle and artifacts are immutable.
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
