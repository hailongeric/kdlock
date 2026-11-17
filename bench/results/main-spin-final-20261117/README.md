# Main spin default-enabled final validation on local 380G10

**Complete: all 413 points passed on one final boot, with normal cleanup.**
The six-entry fixture and one execution of 65 API assertions also passed.
This report validates main `18dad4a1c372d77a1155db671d56c148918344da`, with
`kd_spin_queue_phase=true` and `kd_spin_phase_wait=0`, in
`7.0.0-38-kdlocalspin6 #2`. Same-boot comparisons show higher KD throughput
than Native at 8/16/32 workers in the standard grid. The five-worker short
median remains 0.51% below Native; TCLock remains ahead for the five-worker
long and 16-worker short cells. All rates and matching proxy/handback counts
appear below, with complete ranges in [measured-cells.md](measured-cells.md).

Previous kernel5 controls remain separate evidence. No rate is pooled across
boots, kernels, source versions, placements or workload settings.

## Frozen source and build provenance

[main-final-identity.json](main-final-identity.json) records 131 main input
hashes and base commit `02e604d32fd0dfa1c563ec6d6e6c6138d3f4be19`. The final
source changes the queue-phase default to true and updates documentation;
queue-phase protocol logic is the same as the preceding candidate. Its source
overlay is `kernel/kd_core.c`. The [exact overlay archive](source/overlay.tar.gz)
and its [verified identity](source/overlay-identity.json) retain that input;
its core source hash and embedded 131-file identity match the frozen manifest.

The [preparation receipt](prepare-receipt.json) records 131 verified inputs,
32,049,561,600 available guest bytes, an independent `main-final-source` copy
of `main-queue-source`, and an independent `main-final-out` copy of the
verified queue candidate output. The build reuses old objects as inputs and
incrementally recompiles required objects. It is **not a fresh output or a
clean from-scratch build**. The [status captured while drafting](build-status-at-draft.json)
shows an earlier compilation-in-progress state. It is preserved alongside
the subsequent successful build receipts below.

The [completed build result](build/result.json) reports rc=0 after
256.016 seconds. The [status receipt](build/status.json) records completed
`7.0.0-38-kdlocalspin6` image generation (#2), modules_prepare and
`LOCAL_BUILD_COMPLETE`. The [full build log](build/build.log) is retained.

* Kernel image SHA256:
  `36e0153ae0f05b0fd19b0266aec780f9b34bbad319d9a818de16a053249b2089`.
* [Exact config](build/config) SHA256:
  `1395ae1ff15c215ab680dbb5a4a8af074044cc7de35be82004ddf2647f01ca64`,
  matching the preceding queue candidate config.
* [Build review](build/review.json) verifies all 131 main inputs. Benchmark
  `.text` is `b2ef8124a52507b3f99e72136acffead24e85d4893841ad1763471b391a41eec`;
  TCLock spin `.text` is
  `55d113c7c1680a3d89430ebd88508f005d552cf5b42e6eb060288f77c145317f`.
  Both match their preceding queue candidate counterparts byte-for-byte.
* [Finalization](build/finalization.json) records seven signed modules and
  empty depmod diagnostics. [Signed artifact identities](build/signed-artifacts.json)
  include their signed/unsigned hashes and modinfo. No signing keys are copied.
* [Spin entry assembly](build/asm/kd_spin_lock.asm) and
  [queue slow-path assembly](build/asm/kd_q_lock_slow.asm) are retained with
  the exact build. Capturing assembly does not establish complete mitigation
  or runtime coverage.
* The [ready receipt](build/ready.json) records normal build drain, only NLS
  loaded and no recorded kernel warnings. Its UUID
  `50ac3f08-891c-4800-ba2c-4ce5580d256b` belongs to the preceding kernel5
  builder boot; it is **not** a boot receipt for kernel6.

The [export preflight](build/export-preflight.json) preserves a first attempt
that stopped before guestfish because its intended config destination already
existed. It copied zero files and overwrote no prior evidence. The corrected
export used the distinct `final.config` destination copied here as build/config.

The [final boot receipt](boot/boot-check.json) identifies
`7.0.0-38-kdlocalspin6 #2`, UUID `fc8104fd-5e0c-406f-b93e-e7c6e6cabf6d`,
40 online CPUs, `full (lazy)` preemption, tracer `nop`, initial taint 4096 and
only NLS loaded. Its config hash matches the build. Eight startup jobs were
still present at this early observation; this is **not an idle receipt**.
The later entry checker completed its startup-idle gate and passed the six
cases recorded below. The early boot receipt is retained unchanged.

The [pinning receipt](host/pinning.json) records local QEMU PID 3898702 and
vCPU i pinned to host CPU i for i=0..39, together with the attached disks:

* Root: `/home/eric/vm/qemu-disks/kdlock-kernel16-fresh-20261114/root.qcow2`.
* Build: `/home/eric/vm/qemu-disks/kdlock-kernel16-materials-20261115/builds-current.qcow2`.

The [recovery receipt](host/recovery-before-run.json) confirms
`kdlock-kernel16-two-disk-smoke-20261116-01` on both attached disks. The
[host preflight](host/preflight.json) identifies 380G10 and
92,130,824,192 available host bytes. Its worker CPU 0..35 policies all have
minimum=maximum 2,500,000 kHz. Instantaneous readings nevertheless include
lower values, so this receipt does not measure actual frequency through each
interval. CPU 38 has that same fixed policy; CPUs 36, 37 and 39 have a
1,000,000..3,000,000 kHz policy. Do not generalize worker policy to all
controller/emulator CPUs or infer cross-boot frequency constancy.

The completed runner also checked guest disk serials `kd16-root` and
`kd16-builds-current`. Its [topology capture](raw/evidence-main-final/topology.txt)
shows two 20-CPU NUMA nodes: CPUs 0..19 on node 0 and 20..39 on node 1. The
standard 32-worker grid therefore places 16 workers on each node using CPUs
4..35. The packed control uses 20+12 workers on CPUs 0..31. This report author
used only main source and exported host evidence; live operations were
performed by the coordinating local-VM session.

| Stage | Completed evidence |
| --- | --- |
| Main source identity and isolated preparation | Recorded in the linked identity and preparation receipt |
| Kernel and module build, signing, input/config/text review | Passed; exact build and artifact receipts attached |
| Boot identity, actual QEMU host/disks, pinning and recovery | Recorded for final boot, with topology capture and final idle receipt |
| Signed six-entry fixture | All six cases passed with exact counts and normal unload on the final boot |
| One API ioctl with 65 assertions | Zero failed checks |
| 413-point same-boot campaign | rc=0, exactly 413 points, zero failed points |
| Per-worker mixed read/write postcollection check | Four rows; all 80 workers performed reads and writes |
| Module/daemon cleanup and restored parameters | Daemon rc=0, all five modules unloaded, parameters restored, independent idle receipt passed |

## Completed entry checks and campaign

The [entry result](checks/entry-check.json) reports six passed cases and
normal module unload on final boot `fc8104fd-5e0c-406f-b93e-e7c6e6cabf6d`.
Each case completed exactly 60,000 operations, split 30,000 per worker, with
zero errors and nobody inside at the end.

| Entry case | Total | Worker 0 | Worker 1 | Errors | Contended | Inside at end |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| plain | 60,000 | 30,000 | 30,000 | 0 | 7,986 | 0 |
| irq | 60,000 | 30,000 | 30,000 | 0 | 6,928 | 0 |
| irqsave | 60,000 | 30,000 | 30,000 | 0 | 2,419 | 0 |
| irqsave-disabled | 60,000 | 30,000 | 30,000 | 0 | 3,887 | 0 |
| bh | 60,000 | 30,000 | 30,000 | 0 | 7,929 | 0 |
| clobber | 60,000 | 30,000 | 30,000 | 0 | 6,661 | 0 |

The [campaign start receipt](runtime/comparison-start.json) records PID 969
and runner SHA256
`453df7f13f223b0aa7e3df976b7cb806b26fd686b7f498c777ef0c99829be489`.
The [final result](raw/run-main-final-result.json) reports rc=0 after
265.452 seconds including setup, measurements and cleanup, on the same
boot as the entry checks. The [collection receipt](runtime/collection.json)
confirms exactly 413 points, zero failed points and 66 measured cells. The
[raw API result](raw/evidence-main-final/api.json) reports zero failed checks.
The [completion marker](raw/evidence-main-final/measurements-complete.json),
[cleanup receipt](raw/evidence-main-final/cleanup.json) and
[independent final state](runtime/final-state.json) are all retained.

## Protocol and review scope

A phase hint remains in the spin-class word while the queue remains live.
The current holder byte is authoritative. Only its empty window may consult
the phase plus a nonzero tail; the hint does not grant ownership. Final tail
retirement clears tail and hint together. Pending undo changes only the pending
bit, and last-head acquisition retries the full holder/pending wait after a
failed CAS while the observed tail remains itself. A pending-only word change
therefore cannot imply a successor that will never enqueue.

There is no per-address history, arbitrary observed-node lookup or polling in
the default admission path. The uncontended CAS and byte-store unlock source
paths remain unchanged. The spin-class helpers also serve raw/internal queues
and rwlock gates. Their separate sleepable protocol keeps its original flag
handling. The final emitted assembly is retained with the build receipts.
These source-level statements are not exhaustive runtime context coverage.

[queue-phase-review.md](queue-phase-review.md) preserves the static review
written before the queue candidate commit. Its statements that the candidate
was uncommitted and default-off describe that earlier stage. The current
final source is committed and default-on. The earlier
[phase-wait review](phase-wait-review.md) describes the bounded polling
experiment, whose default stays zero. Neither review is a build or runtime
receipt. Static invariants do not establish exhaustive coverage of pending,
append, drain/reuse, option-disable or nested-context interleavings.

## Executed final campaign

[run-final.py](run-final.py) is the frozen executed runner;
[collect-final.py](collect-final.py) checked and packaged completed evidence
in the guest. This report author reviewed the exported data without rerunning
benchmarks or collection.
[final-runner-review.md](final-runner-review.md) records their final-specific
static scope. The earlier [queue runner review](queue-runner-review.md) is
retained for accounting and methodology; its 741-point campaign and three API
invocations belong to the previous runner, not this one.

The final runner requires the exact release, source identity, expected disk
serials, no comparison modules loaded, normal initial taint and inactive
tracing. It verifies the compiled queue-phase default is enabled and polling
is zero before writing the same effective values. It records the initial and
effective parameters and the boot UUID, and checks that UUID again at campaign
completion. Cleanup restored the initial parameters, independently confirmed
by the final state receipt. Initial and standard-grid parameters were
`kd_adapt=Y`, enter=5, exit=2, batch=4096, `kd_numa=Y`, NUMA-after=32,
queue-phase=Y and phase-wait=0. The forced checks temporarily used
`kd_adapt=0` and restored it afterward.

The 413 completed points include warmups, learning and functional checks:

| Point group | Completed count | Scope |
| --- | ---: | --- |
| Local checks | 27 | Three spin backends at 1/2/5/8/32 workers; Native/KD nested, raw and handback families at 2/8 |
| Daemon-off grid and warmups | 36 | Native/KD, 5/8/32 workers, one line, three repetitions |
| Learning and phase changes | 10 | Two learning points and eight depth-change points |
| Delegation and phase checks | 21 | Nested/raw/handback families and clobber/mixed-end entry variants |
| Mixed rwlock checks | 4 | Native/KD, 8/32 workers, 16 lines, write_pct=20 |
| Three-way grid and warmups | 180 | Native/KD/TCLock, 1/5/8/16/32 workers, 1/16 lines, post=64, three repetitions |
| Outside-work grid and warmups | 96 | Native/KD/TCLock, 1/5/8/32 workers, 1/16 lines, post=0, two repetitions |
| Packed NUMA grid and warmups | 36 | Native/KD/TCLock, 32 workers, CPUs 0..31, 1/16 lines, three repetitions |
| Forced-adaptation checks | 3 | KD, 2/8/32 workers |
| **Total** | **413** | API ioctl and separate entry fixture are not points |

Timed points use 250 ms warmup and nominal 1,000 ms measurements, with the
returned actual elapsed time as denominator. Backend order rotates between
repetitions. Default 32-worker points use CPUs 4..35; smaller grids start at
CPU 0. The controller uses CPUs 38..39. The final topology, pinning,
frequency-policy and preemption receipts above apply to this boot. All
backends share the same stop convention: the elapsed clock stops when stop
is published, then in-flight workers drain before return. Their completed
operations enter the numerator while drain time is excluded. See the static
runner review for the limits of this convention.

The API ioctl executes 65 single-task assertions: 16 spin, seven raw/arch
spin, 14 rwlock, eight mutex, eight ww_mutex and 12 rwsem. The separate signed
entry fixture covered plain, irq, irqsave, initially-disabled
irqsave, bh and clobber entries with two task-context workers. Its atomic
inside detector, exact 30,000 operations per worker and context checks are
stronger exclusion evidence than nano totals alone, but do not establish
arbitrary interrupt-handler or delegated IRQ/BH/nesting coverage.

Every nano point passed positive elapsed time, progress by every worker,
matching worker/aggregate operations and writes, zero reader mismatches, and
protected-data delta equal to writes times lines. The four mixed rwlock points
used 16 lines so reader comparisons were nonempty. Collection verified
exactly 413 total points, exactly four mixed rows, and
`0 < worker_writes < worker_ops` for every worker in those four points. Passing
totals alone cannot satisfy that mixed-access condition. The initial
[collector before explicit count assertions](collect-final-before-count-check.py)
is preserved separately; the current collector also selects only the seven
actual final module build logs for its archive. The earlier collector version
was prepared before collection; its missing exact-count assertions were
corrected in the executed collector, without modifying benchmark inputs.

## Final same-boot throughput and remaining gaps

The standard grid uses queue-phase=Y, phase-wait=0, NUMA ordering enabled,
post=64 and three measured repetitions per cell. Rates are Mops/s medians.
KD event columns sum exactly those three measured repetitions, excluding
warmups. Native KD deltas are zero. TCLock proxy/handback counts are
unavailable; zero sampled KD counters on TCLock rows do not describe its
execution. Every range, n, per-round rate and count is retained in
[measured-cells.md](measured-cells.md), [summary.json](raw/evidence-main-final/summary.json)
and [rates-and-counts.csv](raw/evidence-main-final/rates-and-counts.csv).

| Workers | Lines | Native | KD | TCLock | KD vs Native | KD delegated | KD handback | KD plain stops | KD NUMA deferred |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 9.4505 | 9.4527 | 9.4513 | +0.02% | 0 | 0 | 0 | 0 |
| 1 | 16 | 8.9597 | 9.0799 | 8.9000 | +1.34% | 0 | 0 | 0 | 0 |
| 5 | 1 | 4.4100 | 4.3877 | 3.3927 | -0.51% | 0 | 0 | 0 | 0 |
| 5 | 16 | 2.3852 | 2.4008 | 2.6732 | +0.65% | 0 | 0 | 0 | 0 |
| 8 | 1 | 4.4757 | 5.3999 | 5.1784 | +20.65% | 16,792,906 | 0 | 69 | 0 |
| 8 | 16 | 2.3852 | 4.2113 | 3.3205 | +76.56% | 13,164,980 | 0 | 3 | 0 |
| 16 | 1 | 4.5272 | 5.7092 | 5.7899 | +26.11% | 17,633,577 | 0 | 3 | 0 |
| 16 | 16 | 2.3906 | 4.1542 | 3.3548 | +73.78% | 12,735,115 | 0 | 2 | 0 |
| 32 | 1 | 3.3775 | 6.0122 | 5.6611 | +78.01% | 18,505,846 | 0 | 0 | 73,488 |
| 32 | 16 | 1.8803 | 4.3531 | 3.3220 | +131.52% | 13,479,127 | 0 | 5 | 53,856 |

The uncontended standard short cell is close to Native and offers no KD
requests. Five-worker cells also have zero offered/delegated/handback events.
The short five-worker median is 0.51% below Native, with overlapping observed
ranges; three repetitions do not establish statistical parity. Its long
cell remains about 10.19% below TCLock. The 16-worker short median remains
about 1.39% below TCLock. No profile was collected, so this report does not
attribute those residual differences to a measured cycle breakdown.

At 32 balanced workers, ordinary short/long cells recorded zero/five plain
stops, respectively, alongside millions of delegated completions. These
events support that ordinary waiters seldom ended the measured batches in
this run. They do not measure physical batch length or prove every possible
queue transition. The final kernel has no queue-phase off/on control:
the controlled mechanism comparison is the preceding kernel5 experiment,
retained separately below.

Separate controls remain visible; they are not pooled with the standard grid.
Daemon-off and packed rows have n=3; post=0 rows have n=2. D/H columns sum
the measured repetitions for the displayed KD cell; TCLock counts remain
unavailable. All other control cells and ranges are in measured-cells.md.

| Control | Workers | Lines | Native | KD | TCLock | KD delegated | KD handback |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| daemon-off | 5 | 1 | 4.4095 | 4.4017 | not run | 0 | 0 |
| daemon-off | 8 | 1 | 4.4719 | 4.4485 | not run | 0 | 0 |
| daemon-off | 32 | 1 | 3.4007 | 3.2349 | not run | 0 | 0 |
| outside-work | 5 | 16 | 2.3155 | 2.3196 | 2.7135 | 0 | 0 |
| outside-work | 8 | 1 | 4.4133 | 5.3344 | 5.4425 | 11,017,952 | 0 |
| outside-work | 32 | 1 | 3.3704 | 6.1149 | 5.7712 | 12,360,774 | 0 |
| outside-work | 32 | 16 | 1.7870 | 4.6445 | 3.3344 | 9,337,419 | 0 |
| numa-packed | 32 | 1 | 3.2662 | 6.1412 | 5.6119 | 19,308,067 | 0 |
| numa-packed | 32 | 16 | 1.8608 | 4.6760 | 3.2721 | 14,472,815 | 0 |

The post=0 control retains a TCLock advantage at eight workers/one line
(KD about 1.98% lower) and at five workers/16 lines (KD about 14.51% lower).
The daemon-off 32-worker KD median is about 4.88% below Native. These are
remaining limitations, not omitted or reclassified failures. Packed versus
balanced placement changes CPU membership and locality; the resulting rates
are separate placement evidence, not an isolated change of one protocol bit.

## Mixed access and proxy/handback accounting

All four mixed rwlock rows passed exact sums and zero reader mismatches.
Every one of their 80 workers performed at least one read and one write.
Minimum reads and writes below are minima over individual workers, not sums.
D/H are the event deltas of that single functional point, not timing-grid
counters. The point duration was nominally 500 ms.

| Backend | Workers | Total ops | Total writes | Min worker reads | Min worker writes | Mismatches | KD delegated | KD handback |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| native | 8 | 1,891,332 | 378,273 | 187,158 | 46,909 | 0 | 0 | 0 |
| native | 32 | 1,141,478 | 228,328 | 24,566 | 6,093 | 0 | 0 | 0 |
| kd | 8 | 1,982,604 | 396,970 | 195,206 | 48,963 | 0 | 88,478 | 0 |
| kd | 32 | 2,029,404 | 405,608 | 49,582 | 12,346 | 0 | 147,558 | 0 |

Across the entire campaign, including functional, learning and warmup points,
KD recorded **255,510,239 delegated completions and 537,667 handbacks**.
These campaign-wide totals do not explain a particular measured rate.
All handbacks were in explicit handback families: `spin_hb` 337,066 and
`spin_hb_cl` 200,601. Ordinary `spin` had zero handbacks across every phase,
including all timed grids. [event-counts.md](event-counts.md) retains each
phase/family total so functional handback activity is not mixed into
ordinary spin throughput.

Offered, sessions, plain-stop and NUMA-deferred counts are approximate events.
They are not ownership records or measured physical batch lengths; dividing
delegated by sessions does not establish a physical chain. All-write nano
totals are an accounting oracle, not a universal exclusion proof. The separate
entry fixture adds an inside detector and context checks for its stated scope.
No profile, arbitrary interrupt-handler coverage or unchanged-application
syscall-path performance is claimed. These are kernel-thread nano bodies.

## Cleanup, recovery and retained evidence

The [cleanup receipt](raw/evidence-main-final/cleanup.json) records daemon rc=0
and normal unload of `kd_bench` plus all four TCLock backend modules. The
[modules-after capture](raw/evidence-main-final/modules-after.txt) contains
only NLS. Original parameters were restored, including queue-phase=Y and
phase-wait=0. The [independent final state](runtime/final-state.json) confirms
the same kernel6 boot, no active test processes, no startup jobs, delegation=0,
unchanged taint 4096 and no recorded warnings. It reports 32,040,488,960 guest
free bytes, and installed build/source links into the independent final
directories. No force unload was used.

The [post-run recovery receipt](host/recovery-after-run.json) confirms the
same existing two-disk recovery snapshot remains present. The
[dmesg before](raw/evidence-main-final/dmesg-before.txt) and
[dmesg after](raw/evidence-main-final/dmesg-after.txt) are retained, as are
learning output, dry-run output, per-point data, module logs and all
entry/start/build receipts. Partial earlier build status and the zero-copy
export destination collision remain in this report.

The [export archive](runtime/evidence.tar.gz) is 345,617 bytes, SHA256
`81cc6ffe42c9bc1d6dc9f11469769fb75830b50ddc388bcc40565b151857712f`.
Its [archive identity](runtime/archive-identity.json) records extraction of
regular files/directories only under raw/, with no existing file overwritten.
Eight already-frozen source/runner/build files matched byte-for-byte before
extraction. The [offline data review](runtime/offline-data-review.json)
reconciles all point totals, mixed access, measured-cell medians/counts and
boot/cleanup identities without rerunning the workload. A separate
[independent raw-data review](final-independent-review.md) verified all 50
regular archive members, recomputed rates and counts, and retained the same
coverage limits. That review addresses raw data, not approval of this prose.

[evidence-index.md](evidence-index.md) links every retained file.
[SHA256SUMS](SHA256SUMS) covers the report and evidence files except itself.
[copied-inputs.json](copied-inputs.json) records source paths and hashes for
the separately copied host inputs. The committed source identity and build
hashes remain fixed even though this final report is written afterward.

## Previous queue candidate evidence, kept separate

The [completed kernel5 queue report](../main-spin-queue-20261117/README.md)
records 741 primary points and ten supplemental points with zero failed points
and normal cleanup. Its source is `02e604d32fd0dfa1c563ec6d6e6c6138d3f4be19`,
release `7.0.0-38-kdlocalspin5`, boot
`50ac3f08-891c-4800-ba2c-4ce5580d256b`. Queue-phase defaults were false in that
binary; the runner selected runtime values. Those same-boot controls motivated
the new compiled default. They are not pooled with kernel6 or the older polling
experiment.

The following short-cell KD rates are medians of three measured repetitions
in kernel5. Delegated/handback columns sum those same three measured points,
not warmups. All rows use post=64 and one line.

| Prior control | Workers | Value | KD Mops/s | KD delegated | KD handback |
| --- | ---: | ---: | ---: | ---: | ---: |
| Queue phase | 5 | 0 | 4.4018 | 0 | 0 |
| Queue phase | 5 | 1 | 4.3993 | 0 | 0 |
| Queue phase | 32 | 0 | 3.1626 | 57 | 0 |
| Queue phase | 32 | 1 | 6.2110 | 19,096,518 | 0 |
| NUMA ordering, queue phase=1 | 32 | 0 | 3.0469 | 9,532,439 | 0 |
| NUMA ordering, queue phase=1 | 32 | 1 | 6.3363 | 19,448,187 | 0 |

The five-worker phase control changed by approximately -0.06%, without the
polling experiment's large regression. It does not establish parity with
Native: the separate ordinary kernel5 five-worker short grid was KD 4.4022
versus Native 4.5321 Mops/s (-2.87%), with zero KD delegated and handback events.
In that ordinary grid the 16-worker short cell was KD 5.7276 versus TCLock
5.8153 Mops/s (KD about 1.51% lower), with 17,761,178 KD delegated and zero KD
handback events across three measurements. TCLock execution counters were
unavailable. These are earlier-image results; final-image gaps are reported above.
