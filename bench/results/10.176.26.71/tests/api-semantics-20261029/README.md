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

Host archive collection remains pending. The later API checkpoints below retain
their own source identities and do not promote the rejected pin candidate.


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
archive collection remains pending. The shared build contract explicitly refuses
`CONFIG_PREEMPT_RT`, `CONFIG_DEBUG_MUTEXES`, `CONFIG_DEBUG_LOCK_ALLOC` and
`CONFIG_LOCKDEP`; unsupported configurations are not pending integration targets.

## Mixed mutex-to-spin candidate

`ee7ace6684b5257ae08d82648e9e2dcb4ceb8986` adds a one-CAS exact-ticket service
for recognized unpinned spin CALLs in a delegated ABI2 mutex body. On a miss,
only an eligible root holding its sole outer mutex may transfer physical
ownership directly to its original waiter through PICKUP. The owner remains
nonzero, queue flags survive, source/frame state lives through physical unlock
ACK, and the former executor reacquires before running its own body. Other
owner chains retain borrowing.

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
The deterministic failed-CAS live transfer probe and matched timing remain
pending qualification. The
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

The matched 60-point nano comparison is running from frozen `5f96dd5c` at
`/root/kdlock-evidence/10.176.26.71/bench/api-semantics-candidate-20261029`.
No new timing verdict is available. Its inputs must remain frozen until the run
ends; the archived strict pin candidate remains unpromoted.
