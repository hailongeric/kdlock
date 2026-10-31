# Fresh nano accounting: f7 versus 1b

The candidate remains unaccepted: the finalized strict-host comparison retains
95 whole-run losses, 95 peak losses and 101 points losing either metric out of
210. This note analyzes the existing 420 sessions; it adds no measurement and
does not discard small losses or `NO_JIT` points. Baseline is
`f7a84065e84474380faa37eeadfdf534abd72a68`; candidate is
`1b6f256b13e8743aa1fd7bdc958cc82ae7726463`.

At the worst rwsem point, CPU consumption is essentially unchanged while useful
operation count falls. The evidence does not support a 20% off-CPU/parking
fraction as the main explanation. It also does not prove that no brief park,
reschedule or wake occurred: these sessions contain no event counters for them.

| Point | Whole / peak change | Baseline / candidate CPU ÷ worker-wall | Baseline / candidate completed operations | Execution |
| --- | ---: | ---: | ---: | --- |
| mutex c01 w100, 5 workers | −8.1485% / −8.2488% | 99.4953% / 99.4980% | 6,354,944 / 5,837,056 | returned JIT in both |
| rwsem c01 w1, 8 workers | −20.4963% / −20.4910% | 99.4897% / 99.4897% | 22,728,960 / 18,070,528 | NO_JIT in both |
| rwlock c16 w1, 16 workers | −11.4308% / −11.6550% | 99.4821% / 99.7651% | 21,035,520 / 18,577,664 | NO_JIT in both |

CPU ÷ worker-wall is `sum(worker.cpu_ns) / (workers × measure.wall_ns)`.
The client measures each thread's CPU time around its RUN ioctl; whole wall
starts before CONFIG/Event release and ends after joins/collector completion.
The ~0.5% gap is not a measured parking fraction. Dividing by the narrower sum
of recorded in-kernel active spans gives about 100.009–100.012% at these points,
which exposes the slightly different capture/accounting boundaries. Neither
ratio is capped or interpreted as exact scheduler tracing.

For rwsem n8, CPU time is 16.000255 → 16.000392 seconds over 2.010289 → 2.010308
seconds whole wall. Every worker consumes approximately two CPU seconds.
CPU nanoseconds per completed operation increase from 703.959 to 885.441.
Kernel start spread changes only 224.691 → 232.184 microseconds; the latest
kernel entry is 363.753 → 381.437 microseconds after the shared start. This
startup change is far too small in elapsed magnitude to explain the measured
operation deficit by itself. All eight workers lose operation count, rather
than one absent worker accounting for the loss. Their operation-count coefficient
of variation changes from 0.001025 to 0.021704.

The fixed 384,000-operation rwsem n8 warmup takes 34.882 → 43.954 ms, a 20.639%
rate decline in the same direction. Mutex n5 warmup declines 9.970%; rwlock n16
warmup declines 6.640%. Warmup has a different fixed-operation interval and
fresh worker cohort; these are context, not extra scored rounds or independent
statistical repetitions. [selected.json](selected.json) retains exact workers,
CPU counts, warmup fields and quiescent snapshots for these six sessions.

The loss is not a monotonic worker-count threshold. Rwsem c01 w1 changes
+2.732%, −20.496%, +3.225%, −9.843% and −9.419% at 7/8/12/16/20 workers.
At 32/36/40/60 it changes −0.649%, +2.718%, +5.423% and −1.347%.
Crossing CPU31→32 therefore does not cause a universal drop in this pair.
Across all ten profiles, either-metric loss counts are 38/80 at 1–8 workers,
26/60 at 12–32, and 37/70 at 36–60. The largest loss at n8 coexists with a
+0.264% median whole-run change across its ten profiles. The rwlock control
changes +16.038% at n12 and −11.431% at n16; the mutex control changes
−8.148% at n5 and +6.338% at n6. These mixed patterns keep environmental and
contention-state hypotheses open without labeling any recorded negative noise.

[pairs.json](pairs.json) contains every matched point and occupancy pair;
[key-workers.json](key-workers.json) includes all ten profiles at 20/32/36/60.
All 420 worker-wall occupancy values are at least 98.98%. The losses therefore
primarily appear as reduced progress per accounted CPU time, within this
accounting's limits. Cache/coherence latency, arbitration and busy waiting all
consume CPU time; the current records cannot distinguish them.

Source/runtime evidence narrows the interpretation further:

- `bench/rwlock_compare/session.py:167` finishes publication, stops the translator
  and runs a separate warmup before `measure`. All 420 retained translation end
  times precede measurement. Runtime `NO_JIT` is not proof translation was late
  or absent. Both selected NO_JIT losses had published images.
- 209/210 point pairs have identical published source/JIT image hashes. The only
  difference is mutex c16 n1, a +0.0151% NO_JIT point. All three selected loss
  points have identical published images. Execution classes match at 206/210
  points; the four changed classes are retained separately in the full data.
- `workload_modules/rwlock_bench/direct_rwsem.h:52` explicitly prepares ordinary
  macro writers. `kernel_module/kd_rwsem_api.c:31` routes them through positive
  delegation admission. The positive-reservation → reader-drain → physical-gate ordering remains.
  A prepared-state assertion and shared drain compilation/layout changed, so
  this is an ordering claim, not byte identity. The new unprepared gate-first
  writer admission is not directly exercised by these nano write shells, even
  when no JIT body returns.
  Local readers do execute the changed reader admission code; they never delegate.
- `direct_rwsem.h:62` exposes current readers and current idle state, not reader
  OSQ, phase-wake or park events. Mutex snapshots similarly expose quiescence.
  Selected snapshots have `active=cnts=gate=0`. Translator voluntary/involuntary
  switch fields describe preparation, not timed lock waiters.
- The actual measured ELF review confirms reader `LOCK INC` and the outlined
  suffix: `kd_down_read` 820→84 bytes, with a new 783-byte slow suffix. It also
  confirms that all ten matched workload executable-section/function inventories
  are unchanged. The mutex control is not wholly byte-stable: shared local mutex
  slow code changes, while delegation slowpath/combiner bytes and resolved cold
  targets retain their behavior. Ordinary OSQ has a swapped equality-CMP operand
  encoding. The nondelegated spin controls have exact bytes/relocations. See the
  separately retained provider note and facts; ELF differences are not a causal
  attribution to the score.
- Virtual lock addresses are identical within each selected pair. These receipts
  do not record physical page/PFN or module data NUMA residency. Equal virtual
  addresses and workload code do not establish equal physical placement.

A bounded next discrimination, if root chooses another candidate after current
MM results, is to keep writer-queue changes fixed and first restore the f7 reader admission
and entry/slow-suffix shape alone. If that bounded ablation helps, separate the
atomic increment from outlining in a later candidate. This directly targets the path
exercised by the worst rwsem NO_JIT loss. The data do not justify increasing a
sleep/spin threshold to fix this nano loss, nor do they identify `LOCK INC` as
its cause. Retain the mutex/rwlock controls and the full one-round grid; a profile
geometric mean or improvement at one count cannot erase the other losses.

The reproducible offline reader is
`/tmp/kdlock-writer-queue-nano-accounting-20261031.py`, SHA
`895c8522c926f7fba6490e76fd2bc23dcc528f80bb073082d9bd44a7360772f7`.
It verifies all 20 original compressed group hashes and exact stored hashes of
session/measure/warmup JSONs. [group-proof.json](group-proof.json) and
[validation.json](validation.json) retain this linkage. Full raw originals remain
in the finalized source-host archives; `raw-selected/` contains exact copies of
the three selected sessions per arm. No source edits, VM actions, reruns or
workload execution occurred. One sequential round cannot establish variance,
continuous host isolation or causal mechanism; acceptance remains false.
