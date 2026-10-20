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

## First validation and retained failure

`checks-1` at `290b5bc` passed both basic programs and 26 directly affected
Python checks (comparison 13, observer 4, profile 2, diagnostic 7), dependency
validation and unchanged-source checks. A fresh host receipt at
`2026-10-20T21:23:49.950724+00:00` failed with 74 threads and started no test.
Natural retirement was observed without configuration changes. The next
receipt, `21:25:44.680642+00:00`, passed with the exact original 67-thread set.

`run-1` completed six valid, drained sessions. The seventh, OUTER/counts,
stopped before its measured workers started: the read-only counter tool
incorrectly assumed 48-bit kernel virtual addresses. Its ELF checks and
layout capture succeeded, but it rejected the first per-CPU address beginning
`0xff110003336...`. The session is `PREPARATION_FAILED`, with exact retirement;
an independent module/task check confirmed final idle. The immediate host
endpoint failed at `21:26:36.431066+00:00` with 76 versus 67 threads.

The retained live paging receipt reads `__pgtable_l5_enabled = 1` from the
unchanged kernel. The reader correction must derive 48/57-bit canonical bounds
from that active flag, while retaining the exact original ELF identities,
unique mapped extents, sizes, stable reads and all admission/ownership checks.
The failed original run and its six measurements remain separate. A corrected
revision requires basic and affected tests and a fresh strict gate.

## Corrected-reader validation

`checks-2` at `cbb5b63581784824e6d365b6d3219bb6048242b8` passed both
basic programs and all 27 affected Python checks (13 comparison, 4 host observer,
2 profile and 8 diagnostic checks). Dependency validation, frozen/current source
hashes and final idle passed. The added negative check requires the active
five-level flag before accepting its canonical addresses and still refuses
unmapped, short and ambiguous reads. No provider or workload binary changes.

The next diagnostic uses a new `run-2` output and the full fixed 48-session
plan. The first host observer must finish its planned 900 seconds before a
separately identified second observation begins. No run is interrupted.

## Disposition

The corrected reader passed validation; no successful counter/timing matrix
is available yet.
The seven mutex causes, shared-lock comparative acceptance, remaining nano
conclusions and real mmap/page-fault integration retain their documented
unresolved status. This stage proposes no production change. Only a demonstrated
cause can justify one, followed by exact-revision correctness checks and a
separate controlled A/B comparison against retained controls.
