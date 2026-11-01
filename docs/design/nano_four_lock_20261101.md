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

## Initial check and profiler correction

At `925a15677ba5abaa78b1e9c1a9d3bf6d5a98fdf6`, all four basic lock checks
returned JIT bodies and drained. The basic unit programs and 21 focused profiler
assertions passed. The pilot then exposed a parser assumption: a thread can be
sampled before its worker-name setup, with spaces in its name. Accept the full
name before the numeric PID/TID fields and retain it in the non-worker bucket.
The pilot failure and raw samples remain separate from successful diagnostics;
no scored measurement had started. This correction changes observation only.

## Profile-driven candidate: consecutive rwlock reader admission

Cycle samples at 20 workers locate the largest rwlock cost in the local MCS
admission queue. In c16 w20 it accounts for 72.6% of worker sampled periods on
one node and 71.9% with ten workers on each node. Read-only bodies still run on
their original tasks; only a small fraction of writes return through JIT in
these mixed cases. These are diagnostic samples, not throughput scores.

The existing slow reader withdraws its speculative count, takes the spin gate,
adds its read count, observes writer release, and releases the gate. Every
queued reader currently transfers physical gate ownership through that sequence.
The inspected TCLock gate can combine its short reader-admission interval;
its user read body remains outside that interval. This difference motivates an
independent KD implementation using its existing native MCS queue.

Proposed change, limited to rwlock slow admission:

- A reader that already holds the gate first admits its own read, using the
  existing count and writer-release ordering. It may then credit consecutive,
  fully linked, compatible reader requests while it still owns that gate.
- Each credited reader receives one exact count increment before a release
  notification. Its original task observes that notification with acquire
  ordering, retires its own queue slot, and executes its own read body. It must
  neither increment twice nor release a gate it never physically owned.
- Keep the terminal node, writers, ordinary spin requests and incompatible
  saved contexts as ordinary queue-head handoffs. Never wait for an unfinished
  successor publication just to extend this group. Preserve FIFO order and the
  existing 1024 maximum; introduce no NUMA-local count cutoff.
- Use the unused eight bytes in the node header for the reader object pointer.
  Keep the 128-byte node stride and isolated notification cacheline. Clear the
  discriminator on other publications. Do not copy packets, create JIT frames,
  run reader bodies remotely, change writer admission, or alter reader unlock.
- Interrupt readers keep their existing counted bypass. Ordinary readers with
  incompatible IRQ/preemption state receive the original local admission path.
  One out-of-line slowpath symbol is needed by the inline public reader macro;
  it is an implementation helper, not another exported API family.

Acceptance requires actual-C queue fixtures for ordinary spin exclusion, mixed
reader/writer order, exact reader credits, terminal and delayed links, bounded
service, incompatible contexts and node reuse. Run the live rwlock and IRQ/BH
checks and all four basic checks before matching the one-round timing scenarios.
Rwsem, mutex and spin remain comparison controls for this first lock candidate.
An observed improvement must be established by uninstrumented before/after data.

The optional mutex batch-observation module failed to load: its 7,976-byte
static per-CPU section exceeded the available reserved module allocation.
The failure drained and no batch observation or scored point ran. Retain it as
unavailable evidence; supported cycle, scheduling and remote-memory counters
continue. This is a diagnostic-build limit, not an ownership or data failure.

## Profile-driven candidate: bounded predecessor observations

The c16 w20 rwsem same-node cycle profile assigns 32.3% to
`kd_mutex_osq_lock` and another 4.47% to
`__raw_callee_save___kvm_vcpu_is_preempted`. Disassembly places most OSQ samples
at its PAUSE/recheck loop, which currently decodes `node->prev->tail` and checks
the predecessor vCPU on every unsuccessful poll. The split-node PMU observation
also records 0.12648 remote-DRAM loads per KD operation versus 0.04286 for
TCLock. These whole-client counters do not attribute those loads to this exact
address; that attribution remains a hypothesis to measure, not a proven cause.

Keep grant, local `need_resched()` and applicable signal tests on every poll.
Check the predecessor vCPU immediately on the first unsuccessful poll and then
once every 64 polls, always resolving the current backlink at that observation.
This reduces repeated remote metadata reads and hypervisor calls. A newly
preempted predecessor can delay unlink by at most 63 intervening polls; the
local scheduler and signal response receive no such delay. Exact grant-before-
cancellation ordering, OSQ unlink, slot retirement and all lock ownership are
unchanged. No new shared state, sleeping policy or body delegation is introduced.

This independent change affects the shared optimistic queue used by rwsem
readers and local mutex admission; it does not change the rwlock gate algorithm.
Add deterministic actual-C checks for the polling interval, immediate local
reschedule/signal response, and a simultaneous grant. Run the existing OSQ
rollback/cancellation, local-mutex and rwsem live checks before timing. Keep
the full four-family comparison, including unchanged spin controls, and retain
any loss. The expected benefit remains unmeasured until that candidate runs.
