# Four-lock Nano profiling and optimization

## Baseline and scope

Start from `7231ddf0963ff2cc730590c09cc81e7f96f93095` on an isolated branch.
Keep master and unrelated work unchanged. The previous master campaign measured
Native and KD, with no TCLock or spinlock points. Its rwlock c16 w1 geometric
mean was 4.26% below Native, with a 21.24% loss at 48 workers. These observations
select diagnostics; they do not establish a NUMA cause or a TCLock-relative loss.

Use the maintained TCLock port at upstream
`bbfb9f00a12af51dff6ca291cb9829a82960c2ef`. All four families are available.
Keep the original TCLock algorithms and record the port/build identity.

## Sequence

1. Update the existing diagnostic runner to use the Linux 7 identity contract,
   expose rwlock/rwsem alongside mutex, and accept explicit worker placement.
   Spin uses the existing spin comparison runner and its profiling support;
   its call shell is recorded separately. No lock optimization precedes profiles.
2. Verify the idle VM, recovery snapshot, disk reserve, guest and host placement,
   kernel identity, and profiling events. Run basic and directly affected checks
   in the VM. Freeze source and binaries for each campaign.
3. Collect unscored profiles for all four families with c01/c16 payloads. Mutex
   and spin are exclusive; rwlock/rwsem use 1% and 20% writes. Rwsem reads stay
   local. Compare KD and TCLock under identical inputs within each family.
4. Compare equal-sized cohorts at 20 and 32 workers: CPUs 0..N-1 versus half on
   node 0 and half on node 1. Add contiguous 1, 8, 36 and 60-worker timing points
   to expose uncontended cost and the ordinary grid's node boundary. Every scored
   point gets one round. Profile runs are separate, unscored observations.
5. Attribute sampled hot paths to exact source and emitted instructions. Use
   cycles/instructions, cache events, scheduling counts and existing lifetime/
   batch observations to distinguish work, polling, handoff and sleep. Generic
   cache misses cannot prove remote ownership transfers; state unavailable
   events explicitly. Do not derive a causal NUMA conclusion merely from 32 vs36.
6. Document the chosen change after profiling, implement it on the candidate,
   run basic plus affected correctness checks, and remeasure matching scenarios.
   Retain every positive, negative, failed and inconclusive point. Do not silently
   discard low scores or repeat points to obtain a preferred outcome.

## Measurement contract

Ordinary kernel: `7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`. Source edits and static review run
on 380G10; builds, tests, profiles and timing run only in VM 10.176.26.71.
Use 2-second timed points and one round, keeping warmup, body, post-work, compiler,
provider instrumentation and CPU placement identical within each comparison.
The ten rwlock/rwsem/mutex profiles use the existing bulk ioctl shell and 256
post-work rounds. The existing spin runner has its own recorded shell; do not
pool throughput across the two shells or present cross-family rankings.

Report whole-run operations/second, KD/TCLock ratios, split/same-node ratios,
and candidate/baseline ratios for each scenario. A NORMAL image alone is not
returned-body evidence. Preserve source ownership, completion and drain checks.
Hardware profiles can perturb throughput and never enter the scored tables.
One round describes the observed change, not its statistical uncertainty.

Keep 1024/1024 KD mutex policy and the spin 1024 total limit unless a later,
explicitly documented experiment changes them. Preserve Native API behavior,
reader locality, cancellation ordering and exact ownership/retirement records.
No fairness or oversubscription redesign is included. Promotion requires a
separate review of every measured regression; previous one-time exceptions do
not automatically apply to this candidate.
