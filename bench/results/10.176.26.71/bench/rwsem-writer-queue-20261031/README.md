# Local rwsem writer queue: correctness, nano and mmap1 results

The candidate does **not** pass the nano no-regression gate. Both fresh arms
completed and drained all 210 points, with strict host qualification, but the
candidate is lower at 95 whole-window coordinates, 95 peak coordinates and 101
coordinates on either metric. No coordinate is omitted or unscored. MM kernel
preparation, full build, installation and both scoped MM arms passed their
recorded validation. The 42-pair `mmap1` comparison has 20 gains/one loss for
threads and 15 gains/six losses for processes. At 20 threads the measured ratio
is 5.95×, while 60 processes regress 22.39%. Both performance gates remain false;
the candidate is unaccepted and has not been promoted. The ordinary kernel,
underlying source view and pool settings have been restored.

This report preserves the completed experiment. [Status](status.json), the complete
[210-coordinate CSV](nano/comparison/points.csv) and the original
[offline validation](nano/validation.json) retain separate completion,
qualification and acceptance fields. One sequential round per arm provides no
variance estimate or causal attribution; positive ratios do not establish a
general performance gain.

## Sources and scope

| Role | Exact identity |
| --- | --- |
| Fresh baseline | `f7a84065e84474380faa37eeadfdf534abd72a68` |
| Measured candidate | `1b6f256b13e8743aa1fd7bdc958cc82ae7726463` |
| Initial production change and failed fixture attempt | `7fa989c124810222042f9560d0e83a7dea197d2f` |
| Separate scope3 kernel recipe | `7814c61a0be20f5db3b9fb41b6079ef6d2938b5f` |
| Original baseline held-writer diagnostic | `f4f5f671859be780ee1e6749213aadff1bf518b7` |

The [design](../../../../../docs/design/rwsem_writer_queue.md) changes local
unprepared writers to acquire the physical mutex gate before their own phase
reservation, adds a scoped signal-aware local gate path, and reduces ordinary
reader entry work. Prepared objects retain their phase-first protocol. Reads
remain local; this is not MM-body delegation. The production runtime is unchanged
between the initial `7fa989c1` attempt and the measured `1b6f256b` candidate; the
intervening correction is limited to the live fixture and its documentation.

Both nano arms ran on boot `fa97b9f8-fefc-49b9-abc1-636861e64fc0`, release
`7.0.0-38-kdlock1`, Build ID `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`,
with `full (lazy)` preemption. The original kernel bundle SHA256 is
`1d65f61df1be4ab03e358b456d67165d5c9bdc3edd50cf8f15ad651281feca17`.
That ordinary kernel has the MM replacement disabled; these module checks and
nano measurements do not validate actual scope3 `mmap_lock` execution.

The fixed cohort used 64 guest CPUs split 32/32 across two NUMA nodes, worker
CPUs starting at 0, collector CPU63, fixed host 2GHz and an unchanged 131-task
QEMU cohort with 64 pool workers on CPU63. Both arms use the same frozen harness,
one round per point, 256 post-work rounds and mutex limits 1024/1024. Worker
counts are `1,2,3,4,5,6,7,8,12,16,20,24,28,32,36,40,44,48,52,56,60`.
The [cohort](provenance/nano-cohort.json) and separate
[baseline](nano/baseline/campaign.json) / [candidate](nano/candidate/campaign.json)
records retain source, topology, call-shell and endpoint identities. Historical
timings, Native and TCLock results are not pooled into this pair.

## Correctness before timing

The [baseline checks](correctness/baseline-checks/result.json) passed their
focused unit selection, local rwsem suite and local mutex suite. The initial
candidate [retained unit log](receipts/candidate/control/retained-check-0-unit.log)
records eight unit checks passed, zero failed, including 82 deterministic writer
queue scenarios. Separate linked-site and observation fixtures passed
[eight](receipts/candidate/control/retained-check-0-writer-sites.log) and
[five](receipts/candidate/control/retained-check-0-writer-observation.log) checks.
These unit results retain their original `7fa989c1` identity; they were not rerun
or relabelled as fresh `1b6f256b` executions.

The subsequent [candidate receipt](correctness/corrected-checks/result.json)
binds those unchanged unit inputs and records fresh corrected rwsem and local
mutex runs. The [baseline rwsem](correctness/prerequisites/baseline-rwsem-result.json)
and [candidate rwsem](correctness/prerequisites/candidate-rwsem-result.json)
both report 17 API checks, ten cancellation checks, one downgrade and three
publication checks, with zero errors and final idle. The candidate additionally
records three scoped gate-signal cases: three actual OSQ observations and three
retirements, two fatal cancellations, one interruptible cancellation and one
nonfatal wait. These are local lock semantics checks (`jit_bodies=0`).

Fresh four-family basic checks passed separately on both measured sources:
[baseline](receipts/baseline/control/basic-result.json) and
[candidate](receipts/candidate/control/basic-result.json). Spin, mutex, rwlock
and rwsem each completed 1,600,000 operations, with positive returned-JIT
completion and drain. These checks establish their recorded paths, not arbitrary
lock replacement or every nesting/context combination.

## Retained failures

1. The initial `7fa989c1` live rwsem attempt failed because its new fixture
   consumed one completion twice. Its [original failed receipt](correctness/candidate-checks/result.json)
   still says `passed=false`, `completed=false`, `drained=false`. The
   [inspection](correctness/candidate-failure-inspection.txt) and separate
   [normal retirement/unload receipt](correctness/drain/result.json) retain the
   failure and subsequent drain. The corrected fixture passed under `1b6f256b`;
   the earlier attempt does not become a pass.
2. The baseline nano guest controller returned zero and recorded
   `completed=true`, `idle=true`, `validated_points=210`, while the outer
   transport checked the default field `passed` and reported `step_passed=false`.
   Preserve the [original transport owner](transports/baseline-nano-run/owner.json),
   [actual guest owner](receipts/baseline/control/owner.json) and
   [explicit interpretation](transports/baseline-nano-transport-interpretation.json).
   A new [data-only builder](tools/kdlock-writer-queue-nano-spec-r2-20261031.py)
   sets `success_key=completed` for later run/archive specs. No measurement was
   repeated, no active input was modified, and the original wrapper status remains.
3. The initial scope3 [preparation](kernel/scope3-prepare/result.json) completed
   five focused checks, both source preparations and composition, then failed
   while copying the old configuration because the scope1 build-output bind had
   not been restored. The original `FAILED` receipt remains unchanged. The
   [bind restoration](kernel/scope1-build-bind.json) verifies the original
   configuration, and the separate [continuation](kernel/scope3-prepare-r2/result.json)
   binds all eight completed blocks and runs only the five remaining commands:
   configuration, Rust availability, `olddefconfig`, preparation and affected
   objects. It passed with unchanged recipe/source inputs; no source preparation
   or test was repeated. The later full build has its own receipt below.
4. Both subsequent reboot transports returned 255 and retained empty original
   fetched-result files: [scope3 Native request](kernel/scope3-native-request/step/owner.json)
   and [scope1 KD request](kernel/scope1-request/step/owner.json). Their outer
   receipts remain failed with unknown guest drain. Separate recovery records
   preserve the original owner hashes and fetch the already durable
   [Native request](kernel/scope3-native-request-recovered/step/result.json) and
   [scope1 request](kernel/scope1-request-recovered/step/result.json). Fresh boot
   captures below independently establish the new runtime identities; recovery
   does not rewrite either failed transport or imply another reboot request.


5. Candidate site capture failed before a live payload or timing because the
   original diagnostic allowed at most two schedule return sites while this
   linked kernel has three: `712`, `989`, and `1491`. The
   [failed owner](mm/diagnostics/mm-candidate-sites/step/result.json) and
   [log](mm/diagnostics/failed-sites/controller.log) remain failed. A separate
   [idle/disassembly receipt](mm/diagnostics/failed-sites/independent-idle.json)
   records subsequent idle and the actual linked listings. The corrected
   diagnostic preserves every exact return site and intermediate frame.
6. The first strict-diagnostic extraction failed because the package named its
   manifest `manifest.json`, while the extractor expected
   `diagnostic-manifest.json`. The [original extraction](mm/diagnostics/sites3-strict-extract/step/result.json)
   failed before creating its source directory or loading a module. The
   [packaging correction](mm/diagnostics/provenance/kdlock-strict-hold-return-sites-31d3bc28-20261031-r2.md)
   changes only that member name; source bytes and manifest stay identical. Its
   [separate extraction receipt](mm/diagnostics/sites3-strict-extract-r2/step/result.json)
   passed. This is not a source or kernel correction.
7. Candidate API validation under the 9d harness reached an obsolete assertion
   expecting a writer behind another writer on the rwsem phase queue. The new
   runtime correctly waits on the physical gate first. Preserve the
   [failed owner](mm/diagnostics/mm-candidate-api/step/result.json),
   [raw probe](mm/diagnostics/failed-api/run/probe.json) with 46 checks/one error,
   and [normal unload/idle receipt](mm/diagnostics/mm-candidate-api-drain/step/result.json).
   The replacement fixture checks the exact target task and singleton gate
   waiter under its wait lock, verifies cancellation while the holder still
   owns the gate, and retains phase/read-drain checks. The failure remains
   failed; the fresh result below has a separate source identity and output.

## Nano comparison

`c01` touches one cacheline; `c16` touches sixteen. `w1` and `w20` mean 1% and
20% writes; mutex cases are entirely exclusive. Every row below includes all
21 worker counts. Ratios are candidate/baseline; geometric means summarize the
retained measurements and do not override any negative point or acceptance gate.

| Lock/workload | Whole geometric ratio | Whole losses | Peak geometric ratio | Peak losses | Either losses |
| --- | ---: | ---: | ---: | ---: | ---: |
| mutex c01 w100 | 1.006253 | 5/21 | 1.006179 | 6/21 | 6/21 |
| mutex c16 w100 | 1.004600 | 9/21 | 1.004819 | 8/21 | 9/21 |
| rwsem c01 w1 | 0.991905 | 10/21 | 0.991245 | 9/21 | 10/21 |
| rwsem c01 w20 | 0.982782 | 13/21 | 0.983309 | 13/21 | 13/21 |
| rwsem c16 w1 | 1.005208 | 7/21 | 1.004563 | 7/21 | 7/21 |
| rwsem c16 w20 | 1.002089 | 8/21 | 1.002457 | 8/21 | 8/21 |
| rwlock c01 w1 | 1.006532 | 11/21 | 1.006697 | 11/21 | 12/21 |
| rwlock c01 w20 | 0.990437 | 11/21 | 0.989912 | 11/21 | 12/21 |
| rwlock c16 w1 | 1.003382 | 9/21 | 1.001853 | 11/21 | 12/21 |
| rwlock c16 w20 | 0.998902 | 12/21 | 0.998510 | 11/21 | 12/21 |

At 20 workers, the whole-window results are:

| Lock/workload | Baseline Mops/s | Candidate Mops/s | Change |
| --- | ---: | ---: | ---: |
| mutex c01 w100 | 4.420548 | 4.565608 | +3.2815% |
| mutex c16 w100 | 4.173101 | 4.189210 | +0.3860% |
| rwsem c01 w1 | 8.789420 | 7.961542 | -9.4190% |
| rwsem c01 w20 | 5.408385 | 5.097590 | -5.7465% |
| rwsem c16 w1 | 10.527400 | 10.809411 | +2.6788% |
| rwsem c16 w20 | 4.785795 | 4.808258 | +0.4694% |
| rwlock c01 w1 | 8.352942 | 8.524587 | +2.0549% |
| rwlock c01 w20 | 5.660596 | 5.503341 | -2.7781% |
| rwlock c16 w1 | 10.171558 | 10.249917 | +0.7704% |
| rwlock c16 w20 | 4.197168 | 4.191861 | -0.1264% |

The worst whole-window coordinate is rwsem `c01 w1`, eight workers:
11.306312 to 8.988936 Mops/s (**−20.496300%**); peak throughput is lower by
20.491037%. Both executions are `NO_JIT`. Across all coordinates, baseline has
131 `RETURNED_JIT` and 79 `NO_JIT`; candidate has 133 and 77 respectively, with
zero `PARTIAL_JIT` in either arm. These are execution classifications, not a
count of delegated reads: rwsem reads always execute locally.

The full [CSV](nano/comparison/points.csv), [profile summary](nano/comparison/profiles.json)
and [20/32/60-worker records](nano/comparison/key-workers.json) retain every
positive and negative ratio, qualification and provider/workload hash.

## What the emitted code establishes

The [measured-provider inspection](provider/README.md) and
[exact pair receipt](provider/comparison.json) bind the actual archived ELFs.
The candidate `kd_down_read` entry shrinks from 820 bytes/194 instructions to
84 bytes/24 instructions and uses `LOCK INC`; the outlined suffix is 783 bytes.
This proves the intended emitted entry shape, not a measured throughput gain.

The ordinary `kd_local_lock_slow` body also changes, from 1717 bytes/432
instructions to 1504/389. Therefore the ordinary mutex path cannot be described
as wholly instruction-identical. Delegation slowpath and combiner raw bytes and
placement match, but five cold-target relocation addends shift; their resolved
targets are retained separately. Provider `.text` grows by 3,848 bytes, while
all ten matched workload modules have identical executable function inventories.
Physical NUMA placement, cache residency, branch frequency and parking costs
cannot be inferred from those bytes.

## CPU accounting and the next bounded comparison

The [accounting analysis](nano/accounting/README.md) reuses the same 420 sessions.
At rwsem `c01 w1`, eight workers, accounted CPU time is 16.000255 to 16.000392
seconds while completed operations fall from 22,728,960 to 18,070,528.
CPU divided by worker-wall time is 99.4897% in both arms; CPU nanoseconds per
operation rise from 703.959 to 885.441. This does not support a 20% off-CPU or
parking fraction as the main explanation for that loss. It does not prove that
no brief park, reschedule or wake occurred: there are no corresponding timed
event counters, and the CPU and wall intervals have different boundaries.

All 420 worker-wall CPU ratios are at least 98.98%. All translations finished
before timing, and 209 of 210 pairs have identical published source/JIT image
hashes; the sole different pair is the small positive mutex `c16`, one-worker
`NO_JIT` result. The [selected records](nano/accounting/selected.json) and
[all pair records](nano/accounting/pairs.json) retain these measurements and
their original archive linkage. Busy waiting, cache/coherence latency and
arbitration all consume CPU time, so this accounting cannot separate them.

The nano rwsem write shell explicitly prepares its object. Its positive
reservation, reader drain and physical-gate ordering remains; a prepared-state
assertion and shared drain compilation/layout changed. Consequently the new
unprepared gate-first admission is not directly exercised by that shell, even
at `NO_JIT` points. Local readers do execute the changed admission code.

The smallest proposed follow-up for the nano losses is to keep
the writer-queue change and restore only f7 reader admission and entry/slow-suffix
shape. If that ablation helps, atomic increment and outlining can be separated
in another candidate. This is a source-backed proposal, not an implemented or
measured fix. Neither increasing a spin/sleep threshold nor attributing the
loss to `LOCK INC` is justified by the current records. Keep the mutex/rwlock
controls and every negative coordinate in any subsequent comparison.

## MM comparison and retained scope

The separate scope3 preparation passed through the recorded continuation. Its
[full build](kernel/scope3-build-r2/result.json) subsequently completed
`bzImage` and `modules` with return code zero, no remaining command processes,
unchanged recipe/named source, and configuration SHA256
`4b25e919c4935ef17130dbcbf657e8c0f392d55b0715ac1f3dbf9a64a79aead1`.
The receipt binds the resulting image, `vmlinux`, module symbol table and other
build outputs. [Staging](kernel/scope3-stage/step/result.json),
[installation](kernel/scope3-install/step/result.json) and
[entry append](kernel/scope3-append/step/result.json) subsequently passed under
the [final installation configuration](provenance/kdlock-writer-queue-scope3-install-config-20261031.json).
Their receipts retain module/image correspondence and preservation of the
existing images and ordinary-kernel default.

| Verified boot | Boot ID | Build ID | MM backend |
| --- | --- | --- | --- |
| [scope3 Native](kernel/scope3-native-capture/step/result.json) | `0f19d2af-f3e4-4204-bb5d-a1d294afd731` | `0bdd45b1d7df96a0aaa1db9cd6f049ff08f75ebd` | `off` |
| [scope1 KD baseline](kernel/scope1-capture/step/result.json) | `971baf1a-f9b2-4689-9937-62ab79f4ade2` | `a17d565ee157601e030d1b3c77c13e63fa62c994` | `on` |
| [scope3 KD candidate](mm/diagnostics/scope3-kd-capture/step/result.json) | `aeec1214-6ea3-401f-9b68-d850e21f26ba` | `0bdd45b1d7df96a0aaa1db9cd6f049ff08f75ebd` | `on` |

These are separate boots from the nano cohort. The baseline uses its original
scope1 image and bundle; the read-only
[common source view](kernel/mm-baseline-bind/step/result.json) exposes the exact
`7814c61a` harness without relabelling the underlying runtime generation.
The [original MM configuration](provenance/mm-config-pending.json) uses unchanged
original application binaries, fresh six-case functional mapping and separate
strict held-writer `mmap`/`munmap` proof for both arms, then one 42-point grid each.
The policy is `mmap-functional-held-writer-v1`: incidental mapping observation
may be inconclusive, while the separate held interval requires the exact writer
chains and all nine malformed-observation checks per syscall. Its instrumented
held interval is correctness evidence, separate from scored application execution.

The baseline completed its nine recorded steps, including the 42-point grid and
immediate endpoint. Its [archive owner](mm/baseline/baseline-archive-control/owner.json),
[fetch receipt](mm/baseline/transfer.json) and
[descriptor review](provenance/kdlock-writer-queue-mm-baseline-descriptor-review-20261031.json)
retain the exact four compressed groups and all nine owner references. The
candidate subsequently completed its own 42-point grid and immediate endpoint.
Its [archive owner](mm/candidate/candidate-archive-control/owner.json) and
[fetch receipt](mm/candidate/transfer.json) retain five compressed groups,
including both failed diagnostic attempts. The
[paired validation](mm/comparison/validation.json) passed all 84 original score
logs, 42 coordinates, per-arm source bindings and strict host endpoints. The
[independent arithmetic review](mm/comparison/kdlock-writer-queue-mm-arithmetic-review-20261031.json)
recomputed all 84 logs and every ratio/sign without rerunning a workload.


The final candidate [configuration](mm/diagnostics/provenance/kdlock-writer-queue-mm-20261031.config-queue-proof.json)
uses diagnostic harness `de5e4f06a6d60e531a8b329d3c7f2c5335d5e707` and strict
companion `31d3bc28d55abcab3f8af379a0e57c6e80d7d399`. The baseline retains its
original 7814/f4f harness and all 42 measured scores. The
[exact diagnostic record](mm/diagnostics/provenance/kdlock-writer-queue-diagnostic-provenance-r2-20261031.json)
and [source-host verification](mm/diagnostics/provenance/kdlock-writer-queue-diagnostic-provenance-r2-20261031.build-receipt.json)
verify all 5,847 baseline, 5,848 intermediate and 5,850 final tracked paths
against Git. Only six return-site diagnostic paths and four API fixture paths
change; the strict companion changes three of its six files. The
[return-site](mm/diagnostics/source/return-site-diagnostic.patch),
[API queue](mm/diagnostics/source/api-queue-diagnostic.patch) and
[strict companion](mm/diagnostics/source/strict-companion.patch) diffs are
retained. Runtime, built kernel, scored runner, application binaries and
measurement policy are unchanged by these diagnostic revisions.

The [focused return-site checks](mm/diagnostics/sites3-checks/step/result.json)
passed five decoder and eight actual-C cases on the original 9d generation.
The [baseline replay](mm/diagnostics/sites3-baseline-replay/step/result.json)
keeps that same 9d identity: it checks all three retained positive raw chains
through the unchanged Python proof, and the two fully captured strict
observations through both actual C classifiers. The mapping observation's
full proc text was not retained after the diagnostic log limit, so no C replay
is claimed for it. The API-only successor retains every input used by those
checks byte-for-byte. Replay idle covers its own children; the later ordinary
[source unbind](mm/diagnostics/mm-candidate-sites3-unbind/result.json) separately
records global idle and restoration of the underlying source view.

The fresh de5e [API owner](mm/diagnostics/mm-candidate-api-queue-proof/step/result.json)
and [runner result](mm/diagnostics/mm-candidate-api-queue-proof/actual-result.json)
record 218 checks, zero errors, three cancellation checks, and one each of
downgrade, transfer, IRQ and destruction. Its queue-observation fields bind the
test-only waiter layout to the captured, unchanged local-gate source. This
validates the new candidate predicate without relabelling the baseline's
original phase-first assertion. The per-arm archive/analyzer revision checks
the failed API snapshot against 9d and successful snapshots against their own
final manifests; failed paths cannot alias successful logical owners.


## Measured mmap1 results

The score is completed `mmap`/`munmap` pairs divided by the upstream nominal two
seconds: six warmup samples precede two scored samples. It is not divided by the
approximately eight-second process lifetime. The original executables and
scored runner are unchanged. Each coordinate has one round per arm, so these
observed differences have no run-to-run variance estimate.

| Model | Gains | Losses | Geometric mean of 21 ratios | Worst coordinate |
| --- | ---: | ---: | ---: | --- |
| Threads, shared mm | 20 | 1 | 5.591585× | 1 worker: −0.510627% |
| Processes, separate mms | 15 | 6 | 0.996726× | 60 workers: −22.385920% |

The means are separate per model; they do not cancel regressions or establish
acceptance. [All thread rows](mm/comparison/threads.csv),
[all process rows](mm/comparison/processes.csv), the
[original 84 point records](mm/comparison/points.json), and
[all seven losses](mm/comparison/observed-losses.json) remain available.

| Model | Workers | Baseline pairs/s | Candidate pairs/s | Ratio | Change |
| --- | ---: | ---: | ---: | ---: | ---: |
| threads | 20 | 36,661.0 | 218,116.5 | 5.949551× | +494.955129% |
| threads | 32 | 24,643.5 | 196,922.0 | 7.990829× | +699.082922% |
| threads | 60 | 6,566.5 | 123,637.5 | 18.828524× | +1782.852357% |
| processes | 20 | 1,817,661.0 | 1,818,512.5 | 1.000468× | +0.046846% |
| processes | 32 | 1,786,761.0 | 1,802,037.5 | 1.008550× | +0.854983% |
| processes | 60 | 1,577,534.0 | 1,224,388.5 | 0.776141× | -22.385920% |

Every negative coordinate is retained:

| Model | Workers | Baseline pairs/s | Candidate pairs/s | Change |
| --- | ---: | ---: | ---: | ---: |
| threads | 1 | 288,860.5 | 287,385.5 | -0.510627% |
| processes | 8 | 1,750,584.5 | 1,710,457.5 | -2.292206% |
| processes | 16 | 1,846,878.0 | 1,845,012.0 | -0.101035% |
| processes | 24 | 1,807,459.5 | 1,794,661.0 | -0.708093% |
| processes | 28 | 1,805,924.5 | 1,793,176.0 | -0.705927% |
| processes | 40 | 1,415,044.0 | 1,412,753.5 | -0.161868% |
| processes | 60 | 1,577,534.0 | 1,224,388.5 | -22.385920% |

The strong shared-mm improvement is consistent with moving local writer
serialization into the owner-aware gate/OSQ path, instead of waiting on
`phase_wait` before reaching that gate. This remains a source-backed
interpretation, not an isolated causal measurement: the candidate also changes reader entry and compiled layout.
The process control exposes a separate unresolved loss at 60 workers.

[Whole-lifetime CPU accounting](mm/cpu-accounting/validation.json) validates all
84 original receipts. At 20 shared-mm threads, CPU divided by elapsed time and
configured workers rises from 37.839% to 98.639%; at 32 it rises from 44.712% to
98.344%, and at 60 from 47.868% to 98.210%. This supports a larger running
fraction over the complete approximately eight-second application lifetime.
That interval includes all six warmups, the collector and reaped workers; it
does not measure the exact two-second scored interval or count parking events.

At 60 processes, [original baseline samples](mm/processes60/baseline-upstream.log)
are 1,578,258 and 1,576,810 pairs, versus
[candidate samples](mm/processes60/candidate-upstream.log) of 1,224,791 and
1,223,986. All six warmup totals show a similar difference. Whole-lifetime
elapsed time is 8.106623 versus 8.103824 seconds, and accounted CPU is 478.622046
versus 478.813879 seconds: worker-normalized occupancy stays 98.401% versus
98.475%. The retained loss is not explained by a comparable 22% off-CPU fraction.

The baseline's reported min/max values are strongly skewed: 16,713/291,499 and
16,803/289,074. The candidate reports 20,162/20,825 and 19,974/21,162. These
aggregate extrema do not identify which workers produced them, and there are
no per-worker vectors or spin/park/OSQ event counters. The data therefore do
not assign the loss to reader code, sleeping, a particular CPU, NUMA placement,
or another source-level cause. The exact
[selected receipts and provenance](mm/processes60/provenance.json) remain
unchanged.

The next proposed reader-only ablation would retain the writer queue and
restore f7 reader entry to investigate the nano losses. The 60-process skew
needs a separate bounded investigation; the reader ablation is not a claimed
explanation for it. Neither investigation has run in this experiment.

MM critical sections stay on their original task, and reads never delegate.
General CALL fallback, incomplete queued role exchange and queue-wide waiter
pinning remain separate existing limits; this experiment does not complete
those requests. Oversubscription redesign and rwsem fairness are not claimed.
The final [source unbind](restoration/mm-candidate-queue-proof-unbind/result.json)
restored the underlying checkout. The ordinary-kernel reboot's
[original transport](restoration/scope3-normal-request/step/owner.json) returned
255 and retained an empty result fetch. A separate
[recovered durable request](restoration/scope3-normal-request-recovered/step/result.json)
and [new boot verification](restoration/scope3-normal-verify/step/result.json)
establish one reboot and boot `8e8525e4-8024-48e8-8578-05efad0caf3e`,
`7.0.0-38-kdlock1`, unchanged Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, and final idle. The original transport
failure was not rewritten. The [pool restoration](restoration/pool-restore/result.json)
restored min/max/batch settings to `0/64/0`; it explicitly did not restore the
old task map. The existing QOM object remains and workers may retire naturally.
The candidate remains isolated and unaccepted.

## Evidence and reproduction

[Evidence manifest](evidence-manifest.json) gives each copied file's original
absolute path, SHA256 and byte count; captured files were copied without
normalization. Large raw archives, ELF files and full host captures remain at
their recorded source-host paths. Both original compressed archive indexes and
fetch receipts are retained under `receipts/`; no archive was regenerated for
this report. The source-host [analysis tools](tools/nano-offline/README.md),
[input manifest](nano/inputs.json) and validation retain the exact offline
reproduction inputs. Reproduction reads archived bytes and does not run tests
or measurements.

The [progress snapshot](provenance/progress-snapshot.json) is copied historical
orchestration state and includes earlier pending notes. Final evidence status
for this report is [status.json](status.json); original receipts are never
rewritten to remove their former pending or failed fields.
