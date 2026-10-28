# API semantics implementation checkpoints, October 29

The documentation-first commit is `67361fee6440765e130385b2961246a41052b953`.
Its implementation matches the audited `6a7350291ebab8c50a43431561e11085098d628b`.
This is ongoing implementation evidence, not completion of the requested API work.

## Strict selected-waiter pin candidate

Candidate `658b918a05cb930d52ccf7307b8d44d54c6d6265` is retained on
`archive/mutex-proxy-strict-20261029`. It permits queued/head scheduling, requires
an origin pin acknowledgement before JIT, and cancels acknowledged unstarted
requests before NUMA-prefix rejoin. The 32-byte object, node geometry, two-word ABI,
1024/1024 policy, exact source/owner/ACK/frame obligations remain unchanged.

**Rejected for performance; not promoted to master.** A fresh baseline completed
60 KD nano timings and warmups: ten profiles at 1/8/20/32/36/60 workers. The candidate
then completed twelve matching mutex c01/c16 points and warmups. All have one
2-second observation, post256 and exact data/drain. Rates below use completed
operations divided by measured wall time, as the maintained reporter does.

| Body | Workers | Baseline Mops/s | Candidate Mops/s | Change |
| --- | ---: | ---: | ---: | ---: |
| c01 | 1 | 1.916 | 1.916 | 0.0% |
| c01 | 8 | 3.688 | 2.133 | -42.2% |
| c01 | 20 | 4.584 | 2.098 | -54.2% |
| c01 | 32 | 4.574 | 2.093 | -54.2% |
| c01 | 36 | 4.257 | 2.067 | -51.4% |
| c01 | 60 | 4.340 | 2.026 | -53.3% |
| c16 | 1 | 1.916 | 1.917 | 0.1% |
| c16 | 8 | 3.634 | 1.983 | -45.4% |
| c16 | 20 | 4.034 | 2.000 | -50.4% |
| c16 | 32 | 4.060 | 1.968 | -51.5% |
| c16 | 36 | 3.915 | 1.935 | -50.6% |
| c16 | 60 | 3.914 | 1.940 | -50.4% |

The uncontended point is stable; every measured contended point loses over 40%.
This is sufficient to reject the candidate, although one round does not estimate
variance. The extra executor-to-origin REQUEST/PINNED round trip is a code-based
explanation, not a separately profiled causal measurement. A proposed bounded
immediately-selected group needs explicit selection/cancellation accounting;
it must not restore a pin covering the entire published queue. Oversubscription
and rwsem fairness remain out of scope.

## Correctness evidence and failures

- Basic C checks and affected head, resource, clobber-restoration, terminal,
  policy and public mutex API fixtures passed. The new production-extraction
  pin fixture checks queued scheduling, pin acknowledgement, cancellation and
  reselection, same-CPU refusal, completion and physical acquisition; negative
  mutations fail. Two initial fixture runs failed because extraction/mutation
  expectations still encoded the old contract. Their logs remain retained.
- The live queued-producer probe performed 400,000 warmup acquisitions under
  contention, verified real gate/queue admission, scheduled a peer on the queued
  origin's CPU before release, completed all four protected effects and drained.
  The first collector overran the kernel ring and failed with `Broken pipe`;
  its original verdict remains failed. After the exact successful probe record,
  absence of probe tasks and source drain were checked, normal cleanup completed.
  The second run collected logs concurrently and passed with zero source modules,
  frames and writers and final idle. It proves queued scheduling, not JIT.
- Four-family basic checks then passed 1,600,000 operations each, matched returned
  JIT bodies and final retirement: spin 1,597,000; mutex 1,585,222; rwlock 30,298;
  rwsem 1,571,060. These are functional checks, not timing scores.

All execution used guest `7.0.0-38-kdlock1`, boot
`15dc5977-59d3-4471-a196-d71f03f450ed`, 64 pinned vCPUs, two 32-CPU NUMA nodes,
collector CPU 63 and the existing fixed 2.0 GHz host policy. The actual recovery
snapshot was verified. No kernel changes, reboot or real-world API runs occurred.
Timing remains exploratory under the existing auxiliary-worker policy.

The [comparison data](comparison.json) preserves unrounded rates. Original guest
receipts and frozen sources remain at:

- `/root/kdlock-evidence/10.176.26.71/bench/api-semantics-baseline-20261029`
- `/root/kdlock-evidence/10.176.26.71/bench/mutex-proxy-pin-20261029`
- `/root/kdlock-evidence/10.176.26.71/tests/mutex-proxy-pin-20261029` (failed collector and cleanup)
- `/root/kdlock-evidence/10.176.26.71/tests/mutex-proxy-pin-20261029-r2`
- `/root/kdlock-evidence/10.176.26.71/tests/mutex-proxy-basic-20261029`

Host archives have been collected and checked as recorded below. The later API
checkpoints retain their own source identities and do not promote the rejected
pin candidate.


## Integrated API checkpoints

These are separate source generations from the strict pin candidate. They are
functional evidence, not new nano throughput results. The maintained published
mutex waiter remains pinned; bounded-selection policy is still pending.

| Frozen source | Implemented scope | Reported guest result |
| --- | --- | --- |
| `893c16b5e9eb8b53796e9c486d7ac22d75c5cc6c` | Ordinary public spin macros expose the unpinned clobber CALL; named DIRECT benchmark shells keep their inline prefix | Ten selected checks passed (`10 passed, 0 failed`). The surrounding shell receipt failed while assigning zsh's readonly `status`; preserve that wrapper failure separately from the explicit test totals. |
| `428e068ae2b084e98ed8ecbb47215586900fe702` | Local rwlock IRQ/BH/trylock APIs and interrupt-reader waiting-writer bypass | Two basic programs plus rwlock/context drivers passed: 4/4, including 105 context cases. The live IPI reader probe passed and drained; JIT bodies were zero. |
| `1b186f5d236155d4f30c32e3950e658039519ae7` | Unified rwsem API from `6099baf36d0888759cc6fd5bf15d252f382ebc6a`, plus shared RT/debug/lockdep configuration refusal | Two basic programs and five affected drivers passed: 7/7. Benchmark runner tests passed 25 and 12 cases. Live rwsem reported 17 API checks, 10 cancellation checks, 3 publication checks, successful downgrade and exact drain. |

The rwsem source preserves local downgrade for default ordinary and
callable/signal/try/cleanup writers. Quiescent explicit preparation enables the
same ordinary macro names to delegate under a no-downgrade/no-translated-nesting
contract. Reads remain local, and the generated MM backend retains local unlock
and downgrade without a loadable delegation dependency. The prepared benchmark
shell changed from OUTER/cookie to `public-prepared-direct-abi2`; historical timing
cannot qualify this shell.

The separate prepared rwsem instruction-exit run at `1b186f5d` completed and
drained all four phases. Every phase completed 1,400,000 writes and 20,000,000
reads. Cold warmup recorded 1,358,563 returned JIT bodies; cold measured execution
recorded 1,356,716. The hot phase recorded one native escape and post-ban execution
recorded zero JIT bodies. These observations qualify the probe's local-reader,
prepared-writer continuation and retirement scope, not fairness, performance
neutrality or actual MM delegation.

Guest receipts/logs:

- `/tmp/kdlock-spin-api-units-20261029.log`
- `/tmp/kdlock-rwlock-api-units-20261029.log`
- `/root/kdlock-evidence/10.176.26.71/tests/rwlock-api-20261029`
- `/tmp/kdlock-rwsem-api-units-20261029.log`
- `/tmp/kdlock-rwsem-api-runner-20261029.log`
- `/root/kdlock-evidence/10.176.26.71/tests/rwsem-api-20261029`
- `/tmp/kdlock-rwsem-api-jit-20261029.log`
- `/root/kdlock-evidence/10.176.26.71/tests/rwsem-api-jit-20261029`

The controller reported these results against the named frozen sources. Host raw
archives are retained as recorded below. The shared build contract explicitly refuses
`CONFIG_PREEMPT_RT`, `CONFIG_DEBUG_MUTEXES`, `CONFIG_DEBUG_LOCK_ALLOC` and
`CONFIG_LOCKDEP`; unsupported configurations are not pending integration targets.

## Mixed mutex-to-spin candidate

`ee7ace6684b5257ae08d82648e9e2dcb4ceb8986` adds a one-CAS exact-ticket service
for recognized unpinned spin CALLs in a delegated ABI2 mutex body. On a miss,
only an eligible root holding its sole outer mutex may transfer physical
ownership directly to its original waiter through PICKUP. The owner remains
nonzero, queue flags survive, source/frame state lives through physical unlock
ACK, and the former executor reacquires before running its own body. Other
owner chains retain borrowing. This is a partial implementation of the requested
role exchange: the former combiner C waits for the original waiter W's physical
unlock ACK and then reacquires without
republishing its original request for delegation. W resumes its native suffix,
not a new combiner loop. Immediate queued role exchange remains unimplemented;
validating the owner handoff alone does not complete that requirement.

These transitions are verified by static source inspection and affected
production-code fixtures. Initial mixed units recorded eight passes and two
fixture failures (source-header lookup and missing new atomic/BUG substitutes);
the corrected two-driver rerun passed 2/2 at
`5f96dd5c42a27583aef679554f31e41bcafef793`. Preserve the original
failed verdicts. The actual ticket, owner-exchange, remote ACK and wrapper
fixtures use deterministic scheduler/queue substitutes, not live transfer.
The mixed public-spin instruction-exit run at that source passed and drained
all four phases, each with 1,600,000 operations. Cold warmup recorded 1,537,032
JIT bodies, cold execution 1,592,691, hot execution one native escape and post-ban
execution zero JIT bodies. A separate public-spin runner suite passed 5/5.
The first deterministic failed-CAS live transfer attempt failed during setup as
recorded below; the corrected owner-handoff probe passed. Full queued role
exchange and timing qualification remain pending. The
optional mixed instruction-exit probe serializes every inner-spin user with
the outer mutex and therefore cannot prove the contended transfer path. No
whole-kernel replacement, arbitrary nesting, long-chain transfer or performance
gain follows from this candidate. The [ownership guide](../../../../../docs/design/locking.md#53-nested-ab-and-native-continuation)
records the source paths, pin/ACK obligations and finite chain limits.


Mixed candidate guest receipts/logs:

- `/tmp/kdlock-mixed-api-units-20261029.log` (8 passes, 2 retained fixture failures)
- `/tmp/kdlock-mixed-api-units-r2-20261029.log` (corrected 2-driver rerun)
- `/tmp/kdlock-spin-public-runner-20261029.log`
- `/root/kdlock-evidence/10.176.26.71/tests/mutex-spin-jit-20261029`

The four-family basic run at
`/root/kdlock-evidence/10.176.26.71/tests/api-basic-20261029` completed and passed
at `5f96dd5c`, with final idle. Each family completed 1,600,000 operations;
returned JIT bodies were spin 1,597,626, mutex 1,587,239, rwlock 24,210 and rwsem
1,588,877. These are correctness/retirement counts, not throughput scores.

## Completed API candidate comparison

The 60-point KD nano comparison completed from frozen
`5f96dd5c42a27583aef679554f31e41bcafef793`, against baseline
`67361fee6440765e130385b2961246a41052b953`. Ten workload blocks returned zero,
with complete data and drain receipts. Each point has one two-second observation,
post256 and the same 1024/1024 mutex policy. No real-world API ran. The comparison
does not include spin; public-spin timing remains a separate gate.

The [unrounded comparison](api-candidate-comparison.json) preserves all 60 rates,
their writer JIT counts and the original runner identifiers. Its shell fields
are null; they do not establish equal call shells. Source inspection identifies
the changed rwsem shell as `public-prepared-direct-abi2`, replacing OUTER/cookie.
The table shows observed candidate-minus-baseline percentage changes, not
repeat-qualified gains or a performance-neutrality verdict.

| Family / body / writes | 1 worker | 8 | 20 | 32 | 36 | 60 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Mutex c01, 100% | +0.02% | -1.01% | -1.12% | -1.60% | +1.72% | +0.14% |
| Mutex c16, 100% | +0.02% | +0.07% | +1.67% | +2.30% | +1.46% | +4.81% |
| Rwsem c01, 1% | +0.00% | +0.55% | +2.27% | -8.77% | -7.65% | -0.53% |
| Rwsem c01, 20% | -0.04% | +1.06% | +7.95% | +5.43% | -6.44% | -2.36% |
| Rwsem c16, 1% | -0.02% | +3.72% | -8.33% | -2.01% | -1.50% | -2.71% |
| Rwsem c16, 20% | -0.04% | -3.62% | +3.66% | -0.29% | -0.22% | +2.02% |
| Rwlock c01, 1% | -0.02% | -14.38% | -7.01% | +3.78% | -1.94% | +1.17% |
| Rwlock c01, 20% | -0.07% | -0.99% | -1.07% | -1.02% | -4.44% | -1.15% |
| Rwlock c16, 1% | +0.03% | +4.14% | -0.59% | -2.64% | +1.63% | +0.37% |
| Rwlock c16, 20% | +0.02% | -0.71% | +3.04% | +0.01% | +0.59% | +2.55% |

The largest observed rwlock loss is c01/1% at eight workers, from 9.316989 to
7.977198 Mops/s. Rwsem also has losses requiring investigation. A separate
44-observation matched recheck completed from frozen old/new inputs at
`/root/kdlock-evidence/10.176.26.71/bench/api-semantics-recheck-20261029`.
It does not change the maintained source. Its separate results are recorded below.
The isolated local-unlock candidate `667cb8f4` is not integrated or measured by
this comparison; full queued role exchange is still separate implementation work.
The rejected strict pin candidate remains unpromoted.

Original comparison receipts:

- `/root/kdlock-evidence/10.176.26.71/bench/api-semantics-baseline-20261029`
- `/root/kdlock-evidence/10.176.26.71/bench/api-semantics-candidate-20261029`

### Rwlock emitted-code inspection

Read-only host `nm`, `objdump` and ELF byte comparisons used the frozen baseline
and candidate c01/c16 modules. The [emitted-code record](rwlock-emitted-comparison.json)
retains their SHA-256 identities, symbol positions and differing offsets. No
host build or execution was performed.

- `rb_write` is byte-for-byte identical for both bodies: c01 at `0x10`, size
  `0x183`; c16 at `0x10`, size `0x294`.
- c01 `rb_read` starts at `0x1b0` in both modules. Its first `0x69` bytes are
  identical, covering the ordinary uncontended acquire/body/unlock path. Size
  grows from `0xda` to `0xf7`; new work starts at the writer-bit slow path.
- c16 `rb_read` starts at `0x2c0`. Its ordinary uncontended instructions are
  unchanged; the first byte difference at relative `0x161` is the displacement
  of the existing preempt-schedule branch. The slow block at relative `0x18c`
  gains the interrupt check. Total size grows from `0x229` to `0x249`.
- An ordinary contended task reader gains a GS `__preempt_count` load, mask and
  conditional branch before the existing speculative-reader rollback. The old
  zeroing XOR is eliminated. The new IRQ-reader loop is not taken by benchmark
  task workers. There is no added uncontended-path check or helper CALL.
- `rb_run` remains size `0x11c2`; only bytes at relative `0x1ea` and `0x1016`
  differ, both direct-call displacements for `rb_write`/`rb_read`. Reader growth
  shifts its start by 32 bytes: c01 `0x2a0` to `0x2c0`, c16 `0x500` to `0x520`.
  Thus the worker-loop placement relative to 64-byte boundaries changes in
  opposite directions. Lock/value/progress `.bss` symbol offsets are unchanged.

This verifies a bounded added contended-reader path and changed code placement.
It does not measure their individual costs or explain the observed 14.38% loss.
Matched observations are needed before attributing the loss to layout,
contention or run variation; the completed follow-up below still does not
isolate those causes.

### Completed matched follow-up

The [unrounded recheck](api-recheck-comparison.json) contains 20 rwsem and two
rwlock coordinates for each source: 44 observations, each two seconds, post256,
one round and the existing placement/instrumentation policy. All four blocks
returned zero. The original and follow-up rounds remain separate.

| Family / body / writes | 8 workers | 20 | 32 | 36 | 60 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rwsem c01, 1% | +1.74% | -7.54% | -2.65% | +1.35% | -0.59% |
| Rwsem c01, 20% | +10.06% | +0.53% | +3.43% | -1.28% | +2.08% |
| Rwsem c16, 1% | -1.80% | -1.79% | -0.86% | +6.45% | +1.57% |
| Rwsem c16, 20% | +0.06% | -1.82% | -0.06% | +2.56% | +0.37% |
| Rwlock c01, 1% | -4.14% | -6.12% | — | — | — |

The two rwlock losses persisted: 9.639161 to 9.240310 Mops/s at eight workers,
and 8.968762 to 8.420128 at twenty. Rwsem changed signs at several coordinates;
its c01/1% twenty-worker point lost 7.54% in this round. These data do not close
the no-regression gate. Neither one round nor differing old/new rwsem call
shells permit a general performance-neutrality claim.

## Passed live owner handoff

After the staging fix at `20baf5c2`, the probe at
`/root/kdlock-evidence/10.176.26.71/tests/mixed-transfer-20261029-r2` passed.
Six focused runner checks passed before the live run. The
[compact proof](mixed-transfer-r2-proof.json) preserves kernel identity, exact
effects, owner tokens, native totals and source retirement.

Two real warmup rounds performed 500,000 acquisitions. Cached CPU eligibility
was 11 after the first and 31 after the second; the armed G/C/W checks were 13.
The probe observed C owning A before the failed B CAS and W owning A afterwards.
All five tasks returned with balanced state. Prefix, suffix and C's later own
body each executed once; C owned A for its own body. There were 10,006 competing
trylock attempts and zero acquisitions. The forced partial JIT entry count was
one, with zero returned-JIT completions, as expected for native continuation.
Native totals were `started=1 completed=1 unlocks=1`; final owner, gate, tail,
B word, waiter count and active callers were zero, with zero failures.
Source retirement reported zero modules, frames and writers.

An initial controller-affinity launch excluded CPUs 0–4 and was refused before
output creation or module work; its log remains
`/tmp/kdlock-mixed-transfer-20261029-r2.log`. The successful full-affinity launch
is `/tmp/kdlock-mixed-transfer-20261029-r2-live.log`. The older setup failure
below remains failed. The successful probe validates physical handoff, retained
unlock ACK and C's later reacquisition. It does not validate queued role exchange,
multiple-owner chains or performance. New recheck/probe archives are pending;
the original thirteen-tree archive receipt below has its original scope.

## Failed live owner-handoff setup

The `40353f4f` live probe attempt at
`/root/kdlock-evidence/10.176.26.71/tests/mixed-transfer-20261029` retained
`TIMEOUT` with `retain workers: combiner-queued`. Local owner G left the delegation
gate FREE, so C claimed ACQUIRING through the node-less direct route. The setup's
required `waiters == 1` state could not occur. W never started its ioctl and later
exited the userspace barrier. The failed-CAS owner-handoff path was not exercised;
this is neither a transfer pass nor evidence of a reproduced transfer failure.

After all entered roles completed, ready/entered/done masks were 23 and active,
owner, gate, tail, inner B and waiters were zero. The first cleanup assertion
incorrectly required zero source writers before stopping the idle daemon; it
failed without mutation. Correctly ordered normal cleanup then verified all
caller PIDs absent, zero frames, stopped the exact daemon, obtained source retire
`{state: 2, modules: 0, frames: 0, writers: 0}`, and normally removed source and
provider modules. The original timeout remains failed. Exact receipts are
`failure.json` and `cleanup.json` in that evidence directory and its host archive.
Neither this setup nor the serializing mixed JIT probe qualifies immediate
queued role exchange.

## Host archive preservation

Thirteen evidence trees, comprising 26 tar archives, are retained under
`bench/results/10.176.26.71/raw/tests/api-semantics-20261029/`. The
[offline verification receipt](archive-verification.json) records completed
compressed-hash and complete path/type/size/mode/owner/link inventory checks on
`380G10`, without extraction or guest execution. It includes both comparison
trees, strict-pin runs/failures, API/basic/JIT runs and the failed transfer setup.
Archive integrity and archive-time idle do not change any original test verdict.
