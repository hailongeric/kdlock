# OUTER acquisition with general unlock diagnostic, 2026-10-21

Status: **implementation and focused correctness complete; timing blocked by
the unchanged host gate; no performance acceptance.** This is the control specified by the
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
headers. The fixture result is separate from the live owner/ACK and syscall
checks reported below.

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
would therefore compare the entire unlock-shell transformation, including changed
control flow and layout; it cannot isolate provider-only cycles.

`task-1` did not execute its tests: module insertion failed with a reserved
per-CPU allocation error for 7592 bytes. The logs and original module are
retained; inspection found no KD module resident. The planned single allocator
refresh uses the existing page-sized helper's normal allocation/free path and
unloads it before retrying the unchanged provider. This preparation is separate
from correctness and never counts as a test pass.

## Completed correctness and timing admission

`allocator-refresh-1` completed normal build/load/unload and preserved the failed
attempt byte-for-byte. `task-2` then passed both ownership orders, four real ACKs,
two deferred frees, and the three-worker × 4096-iteration registry stress with
three final deferred frees. Ordinary source retirement/unload completed and
the task registry was empty. Both attempts used the identical provider SHA256
`e892c5ee994d705d0b50444d19b4e06ac8faa7efcd10b8f41080908f511c3d46`.
This current-provider ACK probe remains distinct from the frozen provider used
by the workload derivative. The strengthened `elf-checks-2` receipt binds both
actual positive ELFs and all three rejection cases to their source/binary hashes.

`correctness-1`, runner revision `574545b`, completed all four serial sessions.
The joined correctness work has no timing/throughput measurement command.
Every worker progressed on its assigned CPU, the collector stayed on CPU 63,
the protected capacity result and call count matched, and generated images
remained stable. Every session retired to exactly state 2, zero modules, zero
frames and zero writers, then drained. The actual loaded mutex offset was
32 modulo 64 in all four sessions. No per-session kernel fault was detected.

| Session | Operations | Returned JIT bodies | Final drain |
| --- | ---: | ---: | --- |
| Original OUTER, 1 worker | 3,230,080 | 0 | Pass |
| OUTER/general unlock, 1 worker | 5,685,888 | 0 | Pass |
| Original OUTER, 16 workers | 5,100,544 | 5,068,444 | Pass |
| OUTER/general unlock, 16 workers | 6,476,544 | 6,427,903 | Pass |

The one-worker cases execute locally; both contended cases satisfy the required
returned-body check. These operation counts are correctness evidence, not a
performance comparison. They total 20,493,056 operations and 11,496,347 returned
bodies. Entry witnesses remain separately recorded from returned bodies.

`timing-1` was rejected **before its plan or any session started**. The fresh
host receipt at `10:39:29.126620 UTC` contained the original 67 task rows plus
worker TID `446191` on CPU 63. The immediate post-rejection receipt at
`10:39:32.746549 UTC` contained the same 68 rows. Recovery snapshot and pins
were verified. The original strict identity/count check was not relaxed, and
no repeated gate attempts were made to select a favorable observation.

Thus the planned three derivative/fresh-OUTER pairs remain **unrun**. There are
zero new timing samples, so paired rates, variance and confidence intervals
are unavailable. The earlier failed 100-thread endpoint and subsequent
74-thread observation remain unchanged evidence. All seven points remain
`UNRESOLVED_CAUSE`: c08 at 3/4/5 workers, pipebytes at 3/5, pipecap at 5, and rcuht
at 2. Acquisition latency also remains unresolved. A qualifying unchanged host
gate is still required before the six sessions can establish any new timing
evidence; changed execution mix must remain separate from matched-path cost.

The successful allocator preparation captured its kernel log. After review,
the maintained preparation script also captures kernel messages on exceptional
exit; that failure-path improvement was not exercised or used to alter the
completed `allocator-refresh-1/driver.py` evidence.

## Evidence preservation

Final health verification confirmed the same recovery boot and original 73
runtime modules, no project module/task or evidence writer, all 4,088 original
input hashes, all 336 retained collector hashes, the derivative manifest, and
the exact session retirements. The initial health-verifier process imported a
maintained helper before the frozen collector and was rejected by the collector
origin guard. Its script and failure log remain archived. The corrected,
separately named verifier checks the frozen files without importing a second
collector; the guard itself is unchanged. This was an evidence-check failure,
not another workload run.

The completed archive manifest is
[`archives-1/archives.json`](../../raw/bench/pipecap-unlock-20261021/archives-1/archives.json),
SHA256 `c665228f06d3c5cd6ba85fb62c4e7609d4f1cc4a4d8ac58d26c439d333317c10`.
The archiver confirmed unchanged input inventory and final guest idle. Archives
retain the frozen source fragments, binaries, generated images, complete logs,
host observations, supervisors, commands and exit statuses, including failures.

| Archive | Contents | SHA256 |
| --- | --- | --- |
| [checks.tar.gz](../../raw/bench/pipecap-unlock-20261021/archives-1/checks.tar.gz) | Basic/affected checks and frozen tested source | `ae8d73292dfc12e4f20d5b077af930021009fb87ca07d8f8f190f54f10650b1f` |
| [inputs.tar.gz](../../raw/bench/pipecap-unlock-20261021/archives-1/inputs.tar.gz) | Original/derivative input bindings, build and actual ELF audits | `ec5a6e5a288d0b27f64bf31b445d7ff422fa416ce0dc59dcd1ce50aa62a6d6b5` |
| [live.tar.gz](../../raw/bench/pipecap-unlock-20261021/archives-1/live.tar.gz) | Failed task load, allocator preparation, successful retry and four syscall sessions | `ce5ae77a6c5ff8ff1ddfa6ced15a144308232650c9f51491224ca72a0dfa8b4d` |
| [metadata.tar.gz](../../raw/bench/pipecap-unlock-20261021/archives-1/metadata.tar.gz) | Host receipts, rejected timing gate, final health and command records | `44039297d41e37fc8067f6ccf22f7c828045c3bbca38f7668933e3eedd7e4a8c` |

The source-host [inert review](review.py) passed **17,992 checks** with zero
issues; its [receipt](review.json) binds all four archives, Git/source and binary
identities, exact correctness totals and the absence of timing outputs. It
executes no archived program. Both helpers remained read-only and reported zero
files touched. No production locking change, kernel rebuild, reboot or
performance acceptance occurred in this stage.
