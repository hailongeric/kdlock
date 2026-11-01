# Four-lock Nano: source-backed diagnosis

This report distinguishes scored throughput, unscored profiles, code facts,
and remaining causal uncertainty. Numbers from different modes never share a
throughput aggregate. The baseline is
`87a3a41f1ba3746b7716e611541068bd3ab6e975`: its lock code is unchanged from
`7231ddf0963ff2cc730590c09cc81e7f96f93095`. Its additional commits concern
profiling and documentation. The first candidate,
`822036777ae5731f24c56cbf50751d6e075ed1e1`, includes rwlock reader-admission
groups, bounded OSQ predecessor observations, and an outlined rwsem read
slowpath with an early empty-drain-queue test. Grouping was withdrawn after
measured losses. The full-grid follow-up is
`1ba4cc6e59f5451eaecafcf1c3a36861d026e5d9`; it restores baseline rwlock/spin
production code. Separate component comparisons isolate the two remaining
changes. See [the result index](README.md) for acceptance and every version.

## What each workload measures

c01/c16 means one/sixteen separate 64-byte-aligned counters. Each writer
increments every counter; each reader checks equal values, including a repeated
first-counter load. w001/w020 means 1%/20% writes. Mutex and spin use 100%
exclusive updates. Bodies are identical across Native/TCLock/KD within a family.
The ten mutex/rwlock/rwsem profiles use bulk ioctl and 256 register-only post-work
rounds. The two additional spin profiles use their existing shell and 64 rounds.
There is no cross-family throughput ranking. See
`workload_modules/rwlock_bench/payload.h`, `post_work.h`, and
`workload_modules/spin_cacheline/post_work.h`.

The ordinary grid is 1,8,20,32,36,60 workers, plus equal-sized split-node
cohorts at 20 and 32. Same-node means CPUs 0..19 or 0..31. Split-node means
0..9 + 32..41 or 0..15 + 32..47. The 32-to-36 transition changes both population
and placement and is not, by itself, a NUMA experiment. The equal-N pairs
isolate the CPU-placement change more closely. Per-object physical-page
placement is not captured; remote events below cover the measured client,
not individually attributed data addresses.

## rwlock: admission transfers and shared reader counts

Code fact: the baseline task-reader slowpath withdraws its speculative count,
physically acquires the native spin gate, restores its read count, observes
writer release, and releases the gate. Its read body then runs locally.
`include/kd_rwlock.h::__kd_read_lock_pinned`,
`kernel_module/spin/nondelegated.inc::kd_spin_acquire_nondelegated_contended`
and `include/kd_spin_direct.h` implement this path. Every queued slow reader
performs this gate transfer. Readers also update a global count on both entry
and exit; separating that line from the gate avoids false sharing but does not
remove the count's true sharing.

Profile evidence at 20 workers: c16/w20 assigns 72.6% of KD worker cycle periods
to the native gate path on one node and 71.9% on split nodes. Another 13.0%/16.8%
is in the delegating spin wait path. For c16/w1, samples within `rb_read` cluster
around the reader count XADD and decrement. Instruction sampling can skid; these
are instruction neighborhoods, not precise latency measurements.

The split-node c16/w20 remote modified-line load counter records 3.37914 per KD
operation versus 0.42099 for TCLock. KD's same-node value is 0.00129. Locked
loads per operation remain about 3.50 in both KD placements. This is consistent
with increased cost per shared transfer rather than a many-fold increase in
atomic operation count. These counters cannot locate every transfer's address
or count every request for write ownership.

Source comparison: `tclock_backend/komb_rwlock.c::komb_read_lock_slowpath`
queues the short read-admission interval through `kombrw_spin_lock(READ_STATE)`.
Its combiner can service that interval; the application read body remains local.
KD's baseline uses non-combinable native nodes for the corresponding interval.
The profile, protocol difference and equal-N placement comparison identify
reader admission as a concrete optimization target; attribution of the exact
fraction of time to a particular cacheline is not established.

The candidate admits a bounded fully linked prefix under one physical gate,
credits exact reader counts before notifications, and lets original threads
execute their bodies. It stops at the terminal node, writers, ordinary spin
requests and incompatible saved contexts. It neither delegates read bodies nor
changes writer ownership or the interrupt-reader counted bypass.

## rwsem: reader OSQ and phase coordination

Code fact: prepared writers reserve an exact positive phase before mutex
publication and retain it through unlock ACK. Reads execute locally. A reader
first makes up to eight quick admission attempts, then joins an abortable OSQ;
only its head retries reader admission. A new writer cohort waits for an empty
reader OSQ. See `kernel_module/kd_rwsem.c::kd_down_read`,
`kd_rwsem_spin_read`, `kd_rwsem_reserve_delegate`, `kd_rwsem_delegate_enter`,
and `kd_rwsem_delegate_exit`.

At 20 same-node workers, c16/w20 samples assign 32.3% to `kd_mutex_osq_lock`,
29.2% to `kd_rwsem_delegate_enter`, 9.06% to `kd_down_read`, and 4.47% to
`__raw_callee_save___kvm_vcpu_is_preempted`. On split nodes the OSQ and writer
phase still dominate, with additional mutex waiting. Disassembly locates most
OSQ samples around PAUSE/recheck and most writer-entry samples around its phase
wait/retry. Queue-head transfer, shared count updates and phase changes remain
necessary even though reader bodies do not delegate.

TCLock uses a combined reader/writer count and a separate AQS admission gate:
`tclock_backend/komb_rwsem.c::komb_read_lock_slowpath` and its writer slowpath.
TCLock's `tclock_backend/aqs.c::shuffle_waiters` also groups admission waiters
by NUMA node. Its predecessor-notification loop in `aqs_spin_lock_slowpath` has
no PAUSE inside that loop (the PAUSE follows it); KD's abortable OSQ uses PAUSE
and checks scheduler/predecessor state while polling. KD's reader OSQ is FIFO
and has no such locality shuffling. These are verified protocol differences,
not interchangeable lock bodies or proof of each difference's isolated cost.
Changing queue ordering would require a separate fairness decision, which this
candidate does not make.

KD's exact phase reservation/ACK protocol is additional coordination. It cannot
be removed merely to reproduce TCLock throughput without an ownership design.
The available samples establish where KD spends time; they do not establish
that every observed loss is caused by one extra atomic operation.

For c16/w20 split nodes, KD records 0.12648 remote-DRAM loads per operation versus
0.04286 for TCLock. KD remote modified-line loads are 1.88334 versus TCLock's
2.07075, so saying KD always has more of that event would be false. Repeated
predecessor metadata/vCPU reads are an evidence-based candidate, not a proven
attribution of the DRAM counter. The candidate checks that predecessor on poll
1,65,129,... while preserving grant, local reschedule and applicable signal
checks on every poll. The bound is in polls, not elapsed wall time.

## Mutex and spin controls

The sampled mutex and spin paths mostly wait for their combiner; high waiter
cycle share alone is not evidence of an implementation defect. Increasing the
number of waiting CPUs increases aggregate wait cycles even when a single
combiner sustains useful throughput. Compare completed operations, returned
bodies and cross-node ratios before assigning a loss to JIT work.

Mutex's exact node publication/wait/physical acquisition is in
`kernel_module/mutex/waiter.inc`. The combiner scans at most 64 remote nodes,
serves local requests, and retains deferred nodes until service or physical
handoff (`kernel_module/mutex/combiner.inc`). Metadata, saved stacks and
notifications still move between CPUs even when payload ownership stays local.
The split-node c16 mutex counter is 0.05452 remote modified-line loads per KD
operation versus 0.00139 same-node, much smaller than mixed rwlock. It does not
measure actual batch lengths. The optional batch-observation provider did not
load because its 7,976-byte static per-CPU section exceeded reserved allocation;
no batch workload ran and no batch-length conclusion is drawn.

Spin's published physical waiter polls on its shadow stack with a PAUSE loop
in `kernel_module/spin/wait.inc`. Queue selection and NUMA deferral are in
`kernel_module/spin/queue.inc`; returned-body accounting and service are in
`kernel_module/spin/combiner.inc`. The 20-worker samples put roughly 85% in the
KD waiter path and about 3.5% in `run_combiner`; TCLock similarly spends most
aggregate cycles waiting. Spin's generic PMU observations do not individually
attribute remote ownership traffic. No measured KD-vs-TCLock loss should be
invented where the scored table shows KD ahead.

The old 768 count cutoff is absent: `include/kd_mutex.h` defines total/local
limits 1024/1024; `kernel_module/spin/state.inc` defines total 1024. Runtime
provider policy receipts must agree. Terminal, context and finite NUMA-scan
boundaries still exist, so equal numeric limits do not imply an unlimited batch.

## Scheduling evidence and limits

At 20 workers, each sampled run accounts for approximately 40 CPU-seconds in a
2-second interval. Summed worker CPU time is approximately 100% of summed active
wall intervals for all four families on both placements. Small values above
100% reflect measurement boundaries. rwsem split c16/w20 shows more client
context switches (KD706 versus TCLock450), but worker utilization remains about
99.985%. The inherited counter includes the collector and startup; it is not a
worker-park count. These observations reject substantial sleeping time as the
main explanation for these sampled losses, while not claiming that no waiter
ever sleeps.

`mem_load_l3_miss_retired.remote_hitm`, `remote_dram`, and
`mem_inst_retired.lock_loads` ran without multiplexing in the recorded probes.
`ocr.demand_rfo.l3_hit.snoop_hitm` was unavailable in this VM. All cycle and PMU
runs are diagnostic, unscored, and retained separately from the one-round
throughput tables. A single score does not estimate run-to-run uncertainty;
small negatives must remain visible without being described as a proven cause.

## Uncontended rwsem and 60-worker evidence

The four single-worker rwsem points are 5.6–7.0% below TCLock. Contended OSQ
waiting cannot explain that result. In c01/w1, KD read entry accounts for 3.42%
of sampled worker cycles and its release plus outlined fragment for 3.78%; the
TCLock counterparts account for 1.65% and 2.36%. Baseline disassembly shows five
callee-register saves and a 56-byte local frame on ordinary read entry, even
when its first attempt succeeds. KD's final-reader release reads IRQ/preempt
state before finding that no writer is queued. These are verified unnecessary
fast-success costs; samples alone do not assign every percentage of the loss.

The candidate outlines only the failed read-entry path and tests drain-queue
presence before caller context after the same ordered decrement. It retains
eight total probes, PAUSE order, scheduler checks and the existing wake helper.
The candidate changes generated code placement; it does not weaken read or
writer semantics.

At 60 workers, baseline rwlock c16/w20 spends 78.21% in its native admission
path and 17.78% in delegated waiting. Its c16/w1 counterpart spends 58.94% in
native admission and 28.08% in `rb_read`. Rwsem c01/w20 spends 36.55% in writer
phase entry, 36.18% in OSQ, 8.47% in mutex waiting and 5.32% in the vCPU check.
Rwsem c16/w20 gives 34.40%, 36.05%, 12.04% and 5.28% respectively. These profiles
support the same admission/coordination targets at larger populations.

The 8-worker same-node c16/w1 rwsem score is 9.15% below TCLock. KD's diagnostic
places 18.92% in read entry, 9.37% in OSQ, 9.67% in read release and its fragment,
and 56.31% in common post-work. TCLock distributes 28.26%, 13.27%, 11.72%, and
42.53% across the analogous work. Different relative shares and profiled
throughput do not isolate a single cause for that one score. The before/after
score is retained rather than declaring every small or isolated loss explained.

## Source locations at `822036777ae5731f24c56cbf50751d6e075ed1e1`

- `include/kd_rwlock.h:59`: task-reader fast/slow split and interrupt bypass.
- `kernel_module/spin/nondelegated.inc:50`: bounded exact reader credits.
- `kernel_module/spin/nondelegated.inc:195`: local reader slow admission.
- `kernel_module/kd_mutex_osq.c:98`: predecessor-observation interval.
- `kernel_module/kd_rwsem.c:88`: ordered reader decrement and wake conditions.
- `kernel_module/kd_rwsem.c:142`: reader OSQ and final-unlink phase wake.
- `kernel_module/kd_rwsem.c:181`: outlined reader slowpath; entry at line 201.
- `kernel_module/kd_rwsem.c:406`: exact prepared-writer reservation and phase.
- `kernel_module/mutex/combiner.inc:478`: bounded NUMA scan; line 510 deferred handoff.
- `include/kd_mutex.h:22`: 1024 total / 1024 local count defaults.
- `kernel_module/spin/context.inc`: actual saved/executor context compatibility.
- `tclock_backend/komb_rwlock.c::komb_read_lock_slowpath`: combined read admission.
- `tclock_backend/komb_rwsem.c::komb_read_lock_slowpath`: AQS admission.
- `tclock_backend/aqs.c::shuffle_waiters`: NUMA grouping in the comparison port.

## What the candidate profiles changed

At 20 workers, rwlock c16/w20 shifts sampled worker cycles from the original
native gate path (72.6% same-node / 71.9% split-node) toward the new reader
admission helper (56.95% / 53.98%) and delegated waiting (28.84% / 32.12%).
This is a redistribution of sampled time, not proof of a throughput gain.
Split-node remote modified-line loads fall from 3.37914 to 2.72569 per operation,
while locked loads rise from 3.49894 to 3.92596. Same-node locked loads rise
from 3.50756 to 4.21283. Lower transfer count for one event therefore does not
make the entire admission protocol cheaper.

For rwsem c16/w20, split-node remote modified-line loads fall from 1.88334 to
1.81300 per operation, but remote-DRAM loads rise from 0.12648 to 0.14093.
The hypothesis that spacing predecessor checks would reduce the whole-client
remote-DRAM count is not supported by this diagnostic. At 60 workers the vCPU
helper is no longer among the dominant paths, while OSQ polling remains the
largest sampled path (44.67% for c16/w20). Avoiding a repeated helper call does
not remove queue handoff or reader/writer phase coordination.

The rwsem single-worker c01/w1 profile now assigns 2.48% to read entry and
2.60% to release plus its fragment, versus baseline 3.42% and 3.78%. Static
candidate disassembly confirms one callee-register save on ordinary read entry,
versus five and the 56-byte local frame in the baseline. The separate scored
numbers determine the actual throughput effect.

Spin's retained flat worker summaries cover its whole measured-client interval,
with preparation/warmup excluded. They do not apply the settled full-cohort
filter used by `bench/nano/profile.py` for the other three families. This
observation boundary is another reason not to compare cycle percentages across
families. Same-node c16 KD assigns 85.64% to its waiting path, versus 90.95% for
TCLock; split-node gives 85.74% and 94.56%, respectively.

Reader grouping also changes which arrivals reach the native queue-head heat
qualification. A credited reader takes the `KD_NATIVE_READ_GRANTED` return
before `kd_spin_qualify_native_queue`; a physical queue head runs that
qualification. This is a verified path difference. Returned-write counts in
the scored records must be examined alongside gains and losses. Whether this
advisory selection difference accounts for a particular throughput loss is
not isolated by the current measurements; treating it as proven would exceed
the evidence. The reader-credit correctness result does not imply profitable
writer delegation for every resulting queue shape.

## Withdrawn grouping and isolated follow-up

The complete grouping-candidate grid contains 23.48% loss for rwlock c16/w1
at split 32 workers and 17.11% loss at split 20 workers. Its per-workload
geometric mean changes span -11.57% to -1.80% for the four rwlock profiles.
These losses reject grouping despite the approximately 5.6% c16/w20 split-node
gain. The follow-up restores production rwlock/spin admission bytes exactly to
baseline while retaining rwsem reader code placement and OSQ predecessor spacing.
The baseline native-spin fixture also needed its already-used `proxy_context`
field restored in the minimal declaration; the compile failure is retained.

The follow-up's measured source is
`1ba4cc6e59f5451eaecafcf1c3a36861d026e5d9`. Its focused correctness checks
passed. At 60 workers, restored rwlock c16/w20 again assigns 78.22% to the native
admission path and 17.53% to delegated waiting, close to the original profile.
This confirms the profiled bottleneck remains; reverting a losing experiment
does not solve the original TCLock or NUMA gap.

The first candidate also loses 28.88% on rwsem c01/w1 at eight workers. Both
baseline and candidate record zero returned JIT bodies at that point. Each
worker uses approximately two CPU-seconds during the two-second interval, and
completed-operation variation across workers is small (coefficient of variation
2.38% before, 0.96% after). There is no evidence that delegated-body execution,
substantial parking, or a single starved worker explains the loss.

The follow-up profile of this exact workload/count assigns 25.31% to ordinary
read entry, 19.46% to ordinary read release, 6.30% to OSQ and 4.25% to the outlined
read slowpath. For c16/w1 at the same count, the corresponding shares are 17.56%,
6.97%, 10.30% and 4.49%. The ordinary path contains the shared reader-count RMWs;
this observation selects local reader coordination for further attribution.
It does not isolate whether the original single-score loss comes from changed
instruction placement, the altered polling cadence, or their effect on arrival
patterns. The separately retained component comparisons narrow the implementation
changes associated with this loss; per-address memory samples and first-probe
success/rollback counts are still needed for an instruction-level cause.
Do not use the favorable c16/w20 aggregate to conceal this point.

## Attribution boundaries for individual regressions

The result index and regression map enumerate every negative score. A hot path
is a measured bottleneck; it does not assign every percent of a one-round score
to one instruction. In particular, the sub-percent uncontended mutex/rwlock
losses against TCLock are unresolved at this measurement precision. Spin has
no observed baseline loss against TCLock. Its small split-node penalties have
queue/notification traffic as a source-backed mechanism, without address-level
PMU attribution. They must not be described as a measured parking defect.

Mixed rwlock losses at larger populations and split-node placements share the
profiled native-reader gate and global reader-count path. Mixed rwsem losses
share the OSQ and exact phase/ACK coordination; its single-worker loss instead
comes with an unnecessarily large fast-entry frame and final-reader context
checks. The reader-heavy eight-worker rwsem candidate loss remains a separate
case; component comparisons test which retained edit correlates with it.
Unchanged spin/rwlock controls also have negative before/after observations.
Their production bytes are equal, so direct changed-lock attribution would be
false; single-round timing and changed module layout are not isolated here.

No change to the payload, write fraction, post-work, instrumentation or scoring
was used to manufacture an optimization. The benchmark changes add Linux 7
identity checks, explicit placement and all-family profiling. Their useful
result is a valid equal-population NUMA comparison, not an application speedup.

The full follow-up also records zero returned JIT bodies at eight-worker c01/w1,
16.0016 summed worker CPU-seconds in approximately 16 summed active wall-seconds,
and a 1.69% coefficient of variation in worker completions. Its lower throughput
therefore accompanies continuously running, reasonably balanced workers. The
three versions are tabulated in `rwsem-c01-w001-t08-workers.csv`; all-family
unscored scheduling observations are in `worker-utilization.csv`.


## Component result: partial benefit, unresolved reader-heavy loss

The [component comparison](COMPONENTS.md) ties the single-worker rwsem recovery
to reader-entry shaping (+7.17% alone), and shows a split-node c16/w20 benefit
for bounded OSQ polling (+6.08% alone). Reader-entry alone loses 7.98% in that
split case. At eight-worker c01/w1, both isolated versions still lose roughly
30% against the original baseline. Thus removing either component is not a
verified recovery of that point. All eight-worker versions have zero returned
JIT bodies, near-full worker CPU use and balanced completions. The exact
instruction/arrival-pattern cause remains unresolved; this report does not
label a statistical explanation as proven from one round.

The source workload already spaces writes and offsets workers:
`workload_modules/rwlock_bench/module.c:68` starts at `(worker * 17) % 100`,
and line 84 advances the mix by the requested percentage. The runner records
`evenly_spaced_worker_phase17`. A claim that all workers simply start with an
identical write phase would be incorrect. No workload mix or payload was changed.

Follow-up `1ba4cc6e59f5451eaecafcf1c3a36861d026e5d9` improves rwsem c16/w1
and c16/w20 geometric means by 6.08% and 7.90%, but contains 35 negative
observations, including the 21.90% c01/w1 eight-worker loss. Its production
rwlock/spin paths are the restored baseline; their remaining negative scores
cannot be assigned directly to an altered lock algorithm. All full grids,
component results, controls and failed setups remain available. Performance
acceptance remains open, with no promotion. [Next steps](NEXT_STEPS.md) identify
the missing observations needed to reduce that uncertainty.
