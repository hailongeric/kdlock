# Five-worker pipecap causal investigation

This follows the completed `d48f4d2` checkpoint. The original observation of
0.3219× plain DIRECT/OUTER throughput and 2.8925× sampled operation-p95 remains
descriptive under a failed host endpoint. No cause or performance fix is assumed.
Only the main agent edits source and operates the VM. No parallel test or
interrupted in-flight run is permitted.

The original recovery VM is idle with boot
`b65f0205-c8f9-4385-8b13-039cbce243a6` and kernel `6.1.159-kdclobber2`.
The initial read-only host receipt at `2026-10-20T21:07:18.404192+00:00`
preserves a strict failure: 74 QEMU threads versus the original 67. PID,
command line, frequency policy, NUMA placement and pins match; the real
`before-mutex-kdonly-20261017T140354Z` snapshot is listed. No test started
from this receipt. Fresh strict admission is required before execution.

## Established facts and limits

The six plain KD pipecap records from the preceding latency stage all have
returned JIT bodies, but their proportions differ substantially. The final
whole-session logs, which also include warmup, report zero native continuations,
native unlock ACKs, delegation handoffs, nested acquisitions and frame failures.
These observations do not establish the time spent in queue waiting or prove
why the different execution mix arose. Earlier flat profiles are unsuitable
for a matched pipecap cause: their OUTER arm was NO_JIT while DIRECT returned
delegated bodies, and their clocks were not aligned with worker timestamps.

The actual API body reads `pipe->max_usage * PAGE_SIZE` under its selected
mutex and returns through the ordinary `F_GETPIPE_SZ` syscall. Every worker
retains its descriptor, and the existing collector requires exactly one
redirected call and the correct capacity result per completed operation.
Native and TCLock controls remain in the fixed plan. The restored mutex
lock/unlock, queue, local ownership and task-routing sources match `d21a1e3`;
later wrapper/native-exit changes are separate revisions and are not silently
substituted into the frozen original comparison.

## Fixed diagnostic plan

Use the original `mutex-public-20261020-r2` inputs and retained collectors:
collection `d21a1e3`, OUTER `752fec1`. Keep the original 64-vCPU/24-GiB VM,
two NUMA nodes, worker CPUs 0–4, collector 63, translation environment,
warmup, two-second duration, 300-ms peak windows and 10-ms progress sampling.
No provider, workload, client or translated source bytes change.

Three repeats × four original arms × four separate modes give 48 serial
sessions. Preserve original arm rotation and rotate mode order by repeat.

| Mode | Additional observation |
| --- | --- |
| plain | Original collector only |
| counts | Read existing KD counters twice at each joined-worker boundary |
| profile | Same counter reads plus 199-Hz flat cycles samples using CLOCK_MONOTONIC |
| timing | Same counter reads plus the original provider's inclusive `jit_timing=1` option |

Counter addresses are checked against the original ELF sections, object sizes,
live kallsyms and per-CPU offsets. Reads are narrow, read-only `/proc/kcore`
accesses outside worker intervals; a temporary device reference pins provider
storage. Equal repeated reads and the original entry/completion counters must
agree. None of these observations replaces ownership or drain records.
Timing deltas exclude warmup; inclusive phase intervals overlap and cannot be
summed as wall time. Resetting hotlock residuals are not lifetime counters.
Counter capture can age a warmed lock; profiling and global timing updates can
change contention and execution mix. Compare each mode separately, retain
class changes and do not subtract observer overhead.

Before live work, run both basic programs and directly affected diagnostic
tests in the original VM. Preserve strict preflight and immediate post-run
host checks. A separately identified host observer may record QEMU runtime,
placement and polling gaps on unused host CPU 62, with clock brackets and its
own overhead. Thread-count or runtime correlation alone cannot establish
interference causality. Preserve every failed attempt and unavailable field.

## Disposition

Implementation and validation are in progress. No diagnostic timing has run.
The seven mutex causes, shared-lock comparative acceptance, remaining nano
conclusions and real mmap/page-fault integration retain their documented
unresolved status. This stage proposes no production change. Only a demonstrated
cause can justify one, followed by exact-revision correctness checks and a
separate controlled A/B comparison against retained controls.
