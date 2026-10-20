# Rwlock execution admission and QEMU thread diagnosis

Status: active, continuing from clean source `d58f7cf`. The previous collection
and archives did not complete the unresolved engineering goals. The source host
reports hostname `380G10`; the same recovery VM and boot remain in use. Extended
module/task/evidence-writer checks on 2026-10-21 confirmed no active run before
this stage began. The main agent remains the sole writer and VM test executor.

The first targets are the strict `list-n16-kdlock-w020-t08-r00` failure and
the original 83/86-versus-67 host endpoint failures. Their data, images,
retirements, receipts and complete archives remain unchanged in the
[prior report](../nano-list-followup-20261020/README.md).
The original 69-case rwlock coverage gap is now closed, with ten strict
failures retained. The seven mutex regressions, p95 measurement and overhead,
shared-family acceptance and real mmap/fault integration remain required work.
Diagnostic instrumentation and its overhead are identified separately from
acceptance results.

The initial host hypothesis comes from the
[QEMU 8.2.2 thread-pool source](https://raw.githubusercontent.com/qemu/qemu/v8.2.2/util/thread-pool.c):
its disk-I/O pool creates threads named `worker`, inherits main-loop affinity,
and allows idle workers above the minimum to exit after ten seconds.
This matches properties of the retained observations but does not yet bind
those workers to the running binary or establish their effect during timing.
A read-only process/I/O capture will identify the installed executable and
configuration before a bounded, separately labelled causal diagnostic.

For rwlock, publication success is already established. The next provider
diagnostic must distinguish CPU ratio/time gates, native queue-prefix vetoes
and per-lock heat during warmup and the measured phase. It must preserve the
existing branches, ownership and strict returned-JIT requirement. No failed
case will be repeated merely to obtain a favorable execution class.

## Host I/O diagnostics

`host-inventory-1` binds the running PID 257489 to installed
`qemu-system-x86` package `1:8.2.2+ds-0ubuntu1.18` and executable SHA-256
`8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854`.
Its raw command-line hash is
`08a7ad4ddad7da7d6437c5ebcc2987894c2e69b1cd8abd31db0bd491f30ce917`.
Both existing qcow2 drives use writeback cache; no named IOThreads or explicit
aio/pool override were reported. The first snapshot has 68 threads, including
one `worker` pinned to CPU 63, with recent system-disk I/O while KD is idle.

Two serial diagnostic arms, `ram-1` and `disk-1`, each created and verified
33,554,432 bytes with eight CPU-pinned workers, fsync, and a 12-second setup
settle interval. All files remain in their new VM directories. No KD module or
lock workload ran concurrently. These are I/O stimuli, not throughput samples.
The [summary](io-summary.json) retains per-worker host I/O and block counters.
RAM endpoints had 67/68/68 QEMU threads; ext4 endpoints had 71/72/72.
Extra workers had positive write-byte counters. System-disk writes increased
even during the RAM control and both subsequent 12-second observation intervals.
The ext4 arm added 34,648,064 block-layer bytes between its before/after receipts.
Thus ordinary root-disk activity is a demonstrated source of worker I/O, but
these observations do not identify the exact producers or activity in historical
timing intervals. The background writes confound a simple RAM-versus-disk
attribution. The earlier strict 83/86-thread failures remain unchanged.
The [raw index](raw-index.json) binds every full host capture and stderr file
to its retained local path and the 268,489-byte archive, SHA-256
`0ad70baada318e865e8d84d0457c65db318f76d030f92ca893530cedda460e23`.

## Planned rwlock diagnostic and coverage

The provider-only observation patch adds 35 preallocated per-CPU fields, read
at drained phase boundaries. It retains every threshold, native queue-prefix
branch, ownership record, image, ACK and retirement check. The production
provider and workload binaries remain frozen. Its additional instructions and
changed layout are diagnostic overhead, not an accepted optimization.

The fixed diagnostic plan contains three original/observed pairs at eight
workers and three at sixty, alternating arm order. Every arm reuses the
original caller, daemon, translator, guard and collector. The original provider
is reused byte-for-byte; only the observed provider is rebuilt in a new tree.
All cases retain the two-second duration, original warmup, mix, sampling,
CPU placement and strict returned-JIT requirement. Separate phase counters
must classify all root entries, lock records and queue checks completely.

The subsequent coverage plan contains exactly the original 69 unstarted
rwlock cases, with unchanged binaries and arguments. The runner retains a
strict `NO_JIT` failure and may proceed only after verified complete drain and
exact source retirement. Every other error stops the sequence. Completing
coverage does not convert a failed case into a pass; overall success still
requires every planned case to pass. Both plans retain the strict 67-thread
host admission check and require fresh recovery-snapshot confirmation.
The completed checks and both live plans are reported below.

`admission-1` preparation failed before compilation: the Makefile hunk described
production context and omitted the original benchmark overlay's `kd_bench.o`.
The zero-fuzz application correctly rejected that hunk; all other hunks applied.
No module was built or loaded and no case ran. The partial tree and rejection
are retained. The corrected hunk includes that existing object; preparation
must use a new `admission-2` directory rather than rewriting the failed input.
That manual context correction also failed at the Makefile hunk, again before
compilation or any measurement. The complete hunk is now regenerated from the
observed provider's actual Makefile, with its original balanced context.
Both failed preparations remain intact; the next bundle is `admission-3`.
`checks-1` passed dependency validation, both basic programs and all four
selected drivers (hot-lock sampling, rwlock, native MCS path and spin ownership).

## First admission diagnostic: completed, strict failures retained

`admission-3` built the isolated provider and completed all 12 planned sessions.
All business checks passed and every session retired exactly
`state=2, modules=writers=frames=0`. All six eight-worker sessions remain strict
`NO_JIT` failures; all six sixty-worker sessions returned complete bodies.
The original and observed providers returned 16,886 and 17,747 bodies respectively.
The total measured work was 171,862,784 operations. No threshold was changed.

The three observed eight-worker measurements recorded 8,024 CPU checks:
45 ratio refusals, zero CPU-time refusals and 7,979 CPU-hot outcomes.
Native queue heads then performed 7,944 prefix checks: 5,318 stopped at a short
captured prefix, 2,556 observed no held gate, one observed a missing link, and
only 69 passed. These vetoes repeatedly cool CPU admission and reset lock heat.
All 73 per-lock time samples passed. Nevertheless, 19,699 hot clobber entries
did reach the delegated slowpath without a single combiner starting. Thus heat
and prefix observations alone do not close the diagnosis: the next isolated
extension observes continuation capacity and the unchanged initial combiner
conditions, including the required consecutive combinable nodes. The original
loaded image is byte-for-byte correct; NORMAL publication remains distinct
from returned execution.

Counter overhead was measured through fixed matched runs, not subtracted from
acceptance results. Whole-run rates use completed operations divided by the
recorded `wall_ns`, including the full recorded interval:

| Workers | Provider | Median Mops/s | Range Mops/s | Spread | Sample CV |
| ---: | --- | ---: | ---: | ---: | ---: |
| 8 | Original | 8.233 | 7.037–9.076 | 24.76% | 12.62% |
| 8 | Observed | 9.065 | 8.069–9.234 | 12.86% | 7.16% |
| 60 | Original | 5.845 | 5.557–5.857 | 5.14% | 2.96% |
| 60 | Observed | 5.849 | 5.810–5.884 | 1.28% | 0.64% |

Observed medians are 10.10% and 0.055% higher. These overlapping ranges and
three repetitions do not establish a gain or zero instrumentation cost.
Counter instructions, code layout, admission mix and background I/O can all
affect the result. Eight-worker measurements remain failed tests, used here
only to describe diagnostic behavior.

The [complete archive manifest](admission-3/archives.json) has SHA-256
`165afed66f8f81dc328514f479a319198b1fb95d2642ada0dc1325d89b36b048`.
The [inert review](admission-3/offline-review.json) passed 59,561 evidence checks
covering source reconstruction, unchanged inputs, worker/business arithmetic,
phase counter identities, loaded images and retirement. It retains the sole
endpoint discrepancy: 72 versus 67 host threads. Overall strict success is
false. The 75-thread preflight rejection is preserved in [its receipt](preflight-1.json).
A first archive attempt refused because a copied command receipt was newer
than the original health receipt; [that refusal](admission-3/archive-refusal.json)
remains intact. A fresh idle check after metadata attachment authorized the
separate successful archive, without backdating or changing the old health.

The [guest I/O observation](guest-io-1.json) sampled 12.066 seconds of idle
process metadata. `jbd2/sda1-8` accounted for 32,768 disk-write bytes;
`multipathd` issued 208 bytes of writes with no accounted block writes.
There were no new/exited processes or access errors. Deferred journal/writeback
activity does not identify the original file writer or the historical timing
effect, so this evidence does not clear any failed host endpoint.

## Original remaining coverage

`remaining-1` completed all 69 previously unstarted cases with unchanged frozen
binaries: **59 strict successes and 10 strict NO_JIT failures**, all drained.
This closes the missing-case coverage gap. It does not resolve the original
failure or convert any of these ten cases into passes. The immediate host
endpoint contains 76 threads versus the required 67. A preceding 68-thread
preflight rejection and the successful fresh 67-thread receipt are preserved.
The [archive manifest](remaining-1/archives.json) has SHA-256
`0a331dce9b46915433672fc19d3ea1d47d5975d22b51b88166f60063ce5f72ac`.
Raw archives remain under
`raw/bench/nano-rwlock-diagnosis-20261021/remaining-1/archives/`.
The [independent review](remaining-1/offline-review.json) passed 12,155
evidence-integrity checks over 2,243 files and 47 symlinks. All 23 KD sessions
retired exactly; measured entries/completions match at 161,561. The 69 sessions
completed 451,947,520 operations (361,558,082 reads and 90,389,438 writes).
No retained kernel fault matches were found.

All twelve sixty-worker KD sessions passed the returned-body requirement.
At eight workers, ten of eleven KD sessions failed it; plain n16 repeat 2
returned seven bodies. Its single positive sample is kept separate from
repeat 1's zero-body result and the earlier run's repeat 0. No eight-worker
KD point has three successful, same-class repetitions here.

The [groups](remaining-1/groups.csv) retain every class, repetition, range,
spread and sample CV. The [comparisons](remaining-1/comparisons.csv) describe
only complete three-repeat groups. Among the four eligible sixty-worker
points, the two n16 variants meet observed median-whole/best-peak parity
against both controls. Both n128 variants miss it:

| Variant, 60 workers | Control | Median whole ratio | Best peak ratio |
| --- | --- | ---: | ---: |
| Plain, 128 nodes | Native | 0.9262 | 0.9327 |
| Plain, 128 nodes | TCLock | 0.3396 | 0.3388 |
| Prefetch, 128 nodes | Native | 0.8892 | 0.9007 |
| Prefetch, 128 nodes | TCLock | 0.3353 | 0.3417 |

Each miss also has separated whole-run ranges below 95% of its control.
Maximum three-repeat whole-rate spreads `(max/min−1)×100` are 7.25% for KD
(sample CV 3.91%), 9.49% for Native (4.53%) and 7.42% for TCLock (4.05%).
These are descriptive results under a failed host endpoint. They are not
pooled with the earlier three cases or either instrumented provider, and
they do not establish acceptance.

## Initial combiner diagnostic extension

The second fixed plan, `admission-4`, keeps the same twelve original/observed
pairs and all original arguments. The private provider extends its 35 fields
to 50, observing pending/queue routing, ticket and continuation capacity,
single/multiple queue heads, and every initial combiner outcome. The original
condition and its source-lease acquisition stay unchanged. Refusal counters
classify immutable node kinds without acquiring a source lease a second time.
The runner requires every combiner call to have exactly one recorded outcome.
This diagnostic is intended to explain the 19,699 ready slowpath entries
that the first instrumented run could not classify. Its new instructions and
layout have separate matched controls; no admission policy is changed.

`checks-2` passed dependencies, both basic programs and all four selected
drivers. Its [inert source check](checks-2/offline-review.json) binds 270
files to `c0bbefd`. The isolated provider built successfully in the VM.
The first preflight at 19:22:24.324271 UTC had 71 threads and admitted no
session. The next receipt at 19:23:16.009039 UTC had exactly 67, with the same
pins, policy and real recovery snapshot. Both receipts are archived.

All twelve sessions completed with correct business effects and exact
retirement. All six eight-worker sessions remain strict NO_JIT failures;
all six sixty-worker sessions passed. Original/observed returned-body totals
are 10,362/18,377, with 174,980,608 measured operations overall.
The immediate host endpoint at 19:24:56.707128 UTC fails at 74 versus 67 threads.

The [counter totals](admission-4/admission-totals.json) close the later-branch
question in this instrumented reproduction. At eight workers:

- 8,711 CPU boundaries produced 8,694 hot outcomes, 17 ratio refusals and zero
  time refusals. Only 69 of 8,672 native queue-prefix checks passed; 5,831
  stopped at a short prefix, 2,771 observed an unheld gate, and one lacked a link.
- All 30 per-lock time samples passed. Of 44,894 clobber entries, 34,453
  remained cold and 10,441 reached a ready delegated queue.
- All 10,441 reached a multi-node queue head and called the combiner helper.
  Every call refused because its **first follower was non-combinable**.
  `combiner_native_current` names the helper's first follower: the original
  acquiring head passes `next_node` to `run_combiner()`. It does not mean that
  the acquiring writer's own continuation had a native kind.
- There were no ticket, node/frame-capacity or image-readiness refusals.
  The source-lease condition was short-circuited by the follower-kind refusal,
  so zero source-lease refusals do not establish that a lease was attempted.

Native reader gate requests and cold writers publish non-combinable nodes.
The counters identify the node kind, not the reader/writer identity of each
follower. Combining across one of these nodes would violate the existing
queue contract. At sixty workers the same observed provider admitted 14,565
combiner calls and returned 18,377 bodies during measurement. These observations
explain reproduced admission behavior without changing policy. They do not
retroactively identify every decision in the uninstrumented historical failure,
guarantee JIT at eight workers, or repair any failed test.

| Workers | Provider | Median Mops/s | Range Mops/s | Spread / median | Sample CV |
| ---: | --- | ---: | ---: | ---: | ---: |
| 8 | Original | 8.764 | 6.757–8.809 | 23.41% | 14.45% |
| 8 | Observed | 9.282 | 9.271–9.303 | 0.35% | 0.18% |
| 60 | Original | 5.726 | 5.576–5.949 | 6.51% | 3.26% |
| 60 | Observed | 5.880 | 5.870–5.883 | 0.22% | 0.11% |

The observed/original median ratios are 1.0591 and 1.0269. These measure the
combined effects of diagnostic instructions, layout, admission mix and noise;
they neither isolate counter cost nor establish an optimization gain.
All eight-worker rows remain failed tests.

The [archive manifest](admission-4/archives.json) has SHA-256
`69982055d7e65913d8d0e8ddd54b150a2befc2bdd47664dc10cb3b3b87ee5ba7`.
The [inert review](admission-4/offline-review.json) passes 83,603 integrity checks
over 711 files and 25 symlinks, including every phase classification, loaded
image, original-input hash, business result and exact retirement. Raw files
remain under `raw/bench/nano-rwlock-diagnosis-20261021/admission-4/archives/`.
Strict run success and the host endpoint remain false. No VM test is in flight.
