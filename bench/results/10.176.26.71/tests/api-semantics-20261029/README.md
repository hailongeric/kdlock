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

Host archive collection and later API candidates remain pending.
