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

Before launching, inspection against the retained client's actual JSON found
a second diagnostic mismatch: worker timestamps are named `active_started_ns`,
not `started_ns`. The boundary verifier now checks the original enclosing and
per-worker intervals, including reversed and overlapping observations. This
correction passed `checks-3` at `6c90e7adbae6e3e4ba19ff01c1803e6969b1fff7`: both
basic programs, all 28 affected Python checks, dependencies, unchanged source
and final idle. This is the diagnostic source revision selected for `run-2`.

The next diagnostic uses a new `run-2` output and the full fixed 48-session
plan. The first host observer must finish its planned 900 seconds before a
separately identified second observation begins. No run is interrupted.

## Corrected diagnostic completion

`run-2` at `6c90e7a` completed all 48 fixed sessions with final idle. Its
fresh preflight at `2026-10-20T21:40:12.817266+00:00` first failed at 73 threads
and started no run. After natural retirement, `21:41:08.201163+00:00` passed
the exact original 67-thread set. The immediate endpoint at
`21:45:31.890155+00:00` failed at 95 threads; pins and snapshot still matched.
This endpoint failure prevents performance acceptance. No production change
was made. Independent archive and arithmetic review is in progress.

The first archive review retained 79,776 checks and 90 scope errors: it
incorrectly expected every commit-manifest entry to be copied into each test
snapshot. The runner explicitly freezes 486 build/test sources; 27 Markdown
files, the captured GRUB policy and two unused admission fixtures are bound by
the 516-entry Git manifest. The corrected review checks both exact sets and
all Git hashes, and retains the first review and its source separately.

## Findings from run-2

All 48 sessions passed their original API result, CPU placement, progress and
cleanup oracles. All 24 KD sessions retired with exactly
`state=2, modules=0, writers=0, frames=0`. The later independent VM health check
confirmed idle, unchanged hashes for 4,088 original input files and 336 retained
collector files, and no matched faults in the per-session kernel logs. Both KD
objects kept their original 32-byte cacheline offset. Native and TCLock remained
in every rotated round. The workloads perform the same original capacity read
and check every returned syscall value; the lock call shells intentionally differ.

The following plain results are three separate repetitions, in million operations
per second. Spread is `(maximum − minimum) / median`; CV uses sample standard
deviation. Three repetitions do not establish significance. These are descriptive
results under the failed endpoint, with the separate host observer present.

| Original arm | Median Mops/s | Min–max Mops/s | Spread | CV |
| --- | ---: | ---: | ---: | ---: |
| Linux Native | 4.22845 | 4.18514–5.19558 | 23.90% | 12.59% |
| TCLock | 2.19324 | 2.18682–2.39492 | 9.49% | 5.24% |
| OUTER | 16.05359 | 7.57175–16.38914 | 54.92% | 37.46% |
| DIRECT | 4.86829 | 4.65676–5.45307 | 16.36% | 8.26% |

The plain median DIRECT/OUTER ratio is **0.30325**, with paired ratios
0.29704, 0.29008 and 0.72019. All six plain KD sessions returned JIT bodies,
but their mixes differ: OUTER returns approximately 0.10–1.98% through JIT;
DIRECT returns 10.77–13.41%. The nominal execution-class match therefore does
not establish identical paths or service demand. This collection adds no new
p95 or acquisition-only latency measurement; the previous 2.8925× sampled
operation-p95 ratio remains evidence from its separately identified latency stage.

### Queue, ownership and ACK observations

The six counter-mode KD sessions also all returned JIT bodies. DIRECT's delegation
queue entries cover 12.02–19.16% of completed operations; OUTER's cover
0.11–4.97%. `origin_acquires` counts gate-owned physical acquisitions, not all
local mutex acquisitions, so it must not be used as a total ownership ledger.
All 18 observed KD sessions have zero deltas for native continuation starts,
completions and native unlock ACKs, delegation handoffs, nested acquisitions,
JIT-not-ready/failure, frame failure, task allocation failure, node overflow and
context-busy refusal. Native continuation ACK waiting is consequently not an
executed explanation in these measured intervals. These observations do not
replace exact retirement or establish correctness for unexecuted branches.

All 12 profiles have zero reported sample loss, valid period arithmetic and the
expected five-worker cohort. Explicit `--clockid mono` permits checking samples
against the client's original `CLOCK_MONOTONIC` worker intervals. Provider ranges
are bound to the original ELF hashes. DIRECT's lock entry accounts for
40.48–42.88% of sampled worker event weight, physical mutex functions for
14.04–14.35%, and queue functions for 12.69–15.75%. Exact task-identity helpers
account for 0.95–1.78%, and direct unlock routing for 0.10–0.25%.

The retained disassembly places the hottest entry offsets at the owner test
(`+0x38`, 31.20–32.82%) and bounded probe-loop decrement (`+0x68`, 4.83–5.41%).
The queue hot offset `__kd_mutex_lock_slowpath+0xe3` reads the published waiter's
completion/lock byte. These locations identify observed polling work; flat,
skidding cycle samples are not instruction durations, owner-held time or a
causal allocation of the throughput loss. OUTER has no returned JIT in profile
repeat 0, so that pair remains a class mismatch. The other two pairs still have
different delegated proportions.

### Observed mixes differ across instrumentation modes

Counter captures take roughly 3–7 ms at each joined boundary, entirely outside
worker timing, and can age the warmed state. The counter-mode OUTER rate spans
6.90–17.96 Mops/s, with 146.88% spread. It cannot supply a stable subtraction
for a fixed counter-reader cost. All per-mode ranges, CVs, paired ratios and
class changes are retained in `review-2/`.

DIRECT's timing/plain paired throughput ratio is 0.42559–0.48123, median
0.47735, while its returned-JIT fraction becomes **98.32–98.59%**. OUTER has
zero JIT in two timing repetitions and 59.95% in the third. The clock/atomic instrumented runs therefore have substantially different
service mixes. The timing-mode
DIRECT queue mean is 770–835 ns, inclusive dispatch 184–189 ns and wrapper
31.05–31.52 ns; the one executing OUTER timing repetition records 747, 181 and
31.69 ns respectively. These overlapping, instrumented intervals must not be
summed, subtracted from plain measurements or presented as plain-run costs.

## Host-observer limits

The second observer finished its scheduled 900 seconds without interruption:
17,964 samples, zero placement failures, and 13.54% of one CPU in observer CPU
time, pinned to host CPU 62. It observed 68–95 QEMU threads during the projected
measurement windows, despite the exact 67-thread preflight. All sampled service
threads remained pinned to CPU 63. Median read duration was 6.20 ms and the
maximum between-sample gap was 46.93 ms. Short-lived threads can be missed.
The before/after SSH clock envelope is 810.49 ms wide; projections explicitly
assume intervening offsets stay within those endpoint bounds.

Observed additional-service runtime within the common interiors sums to
71.31 ms across the 48 measurements; the largest overlapping-window observed
delta is 20.67 ms. These values exclude unobserved births/exits and cannot bound
all host activity or prove a throughput effect. Scheduler statistics were
already disabled, so runqueue delay remains unmeasured. No scheduler setting
was changed. The first, failed run has its own 17,965-sample observer, stream,
clock brackets and [summary](host-observation-1-summary.json). The corrected
run's [summary](host-observation-2-summary.json) retains every projected session
and its uncertainty; neither summary overrides a failed endpoint.

## Evidence and disposition

The corrected [archive review](review-2/review.json) passes **81,150 checks**,
including all 54 completed sessions across the separate failed and corrected
runs, 27 exact retirements, independent sample-window arithmetic and 18 counter
snapshot pairs. Its first scope-error report remains in `review-1/`.
[Profile analysis](profile-analysis-1.json) and [ELF bindings](profile-elf-bindings.json)
retain exact sample, module and disassembly identities. The [archive manifest](archives.json)
locates five VM archives: checks, failed run, completed run, host receipts and
metadata. Raw copies reside under
`bench/results/10.176.26.71/raw/bench/pipecap-causal-20261021/`, with separately
hashed host-observer streams and clock brackets. The original comparison,
latency follow-up, failed diagnostic and corrected diagnostic are never pooled.

This stage narrows pipecap to substantially different local/delegated mixes
and observed owner/queue polling. It **does not establish the initiating cause**.
A longer physical-owner interval around DIRECT's general return/unlock route is
a hypothesis, not a demonstrated fix target. Host interference remains uncertain:
extra QEMU threads, their runtime and correlation alone cannot prove causation;
disabled scheduler statistics leave runqueue wait unmeasured. No host settings,
kernel settings, provider instructions, admission rules or production protocol
were changed, and no candidate performance fix was introduced.

All seven original regression causes remain explicitly **unresolved**: c08 at
3/4/5 workers, pipebytes at 3/5, pipecap at 5 and RCUHT at 2. Their completed
controlled reruns and latency results remain in the
[previous stage](../mutex-latency-20261021/README.md); this stage adds focused
pipecap evidence. The c08-t02 and pipebytes-t04 class gaps remain open.
The [rwlock continuation](../nano-rwlock-diagnosis-20261021/README.md) has complete
remaining-case coverage but retains ten strict NO_JIT failures and the observed
first-follower refusal mechanism. [Shared-lock parity](../shared-lock-followup-20261020/README.md)
and [real mmap/fault integration](../../tests/mmap-fault-followup-20261020/README.md)
remain unresolved at their recorded blockers. Whole-kernel replacement,
RT/ww_mutex, lockdep and oversubscription remain separately unvalidated.

Performance acceptance remains **OPEN**. Any production intervention requires a
demonstrated cause and exact-revision correctness checks followed by serial A/B
runs against the retained controls. No check is waived by the narrowed diagnosis.
