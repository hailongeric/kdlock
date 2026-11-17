# Local master spin investigation

Source is master 449078ff (base ebc78cb9); the separately committed six-entry
fixture is 1a93e408. The previous main results use a different spin protocol
and are not pooled here. Master already caches the delegating mode over the
empty lock-byte handoff window.

Only local QEMU on 380G10 is used, through identity-verified UNIX sockets.
The root and build disks are the existing kernel16 local disks; the two-disk
snapshot kdlock-kernel16-two-disk-smoke-20261116-01 was verified before loading.
No access to 10.176.26.71, changes to unrelated work, or deletion was performed.
Existing docs/BUILD_AND_TEST.md edits and kdclaude results remain untouched.

## Rejected candidate and limits

The default-off kd_spin_plain_pass policy permits bounded service past eligible
ordinary spin waiters. A waiter is eligible only in task context with IRQs on,
no active executor depth, and a delegable spin entry (not raw). It stays pinned
in WAIT, is passed at most once in its queued lifetime, and runs its own body
later. The next node must have a compatible continuation on the current NUMA
node. A shared window allows at most eight further queue operations, including
passes, under this grant; the overall batch bound still applies. Multiple
eligible nodes may be passed within that one window. Earlier deferred remote
nodes remain before them. This is not a wall-clock delay bound.

The sole head changes links using existing detach/splice operations. The
prefix is restored before promotion or handback. No ownership counters replace
the lock word, no source/packet lifetime checks are removed, and fast acquire
and unlock instructions are unchanged. See protocol-review.md for static
reasoning and unproven coverage. Runtime counters do not prove the full
physical chain length or all mixed raw/IRQ interleavings.

## Method

One boot, kernel 7.0.0-38-kdlocalspin3 #4, config SHA256
056d1931df7a760e0bdb62a087f59868f632748c04ad7f087c11ca314aaceca0,
GCC 12.3/binutils 2.38, 16 KiB task stacks, full (lazy) preemption.
40 vCPUs, two NUMA nodes of 20 CPUs and 32 GiB, one vCPU per host CPU.
Worker grids use CPUs starting at zero except 32 workers use balanced 4–35;
packed 0–31 is a separate control. Emulator/controller use CPUs 38–39.
Each timed cell has 250 ms warmup and 1,000 ms timing, three rotated rounds.
Post=64, 100% writes, lines=1/16 are standard; post=0 remains separate.

Native/KD/TCLock within this campaign share the same kernel, boot, CPU mapping,
module and controller. Policy values alternate order between rounds. Disabling
the new policy is a same-image control, not the exact old binary: it retains
the added branch, node field and compiled layout. The NUMA off/on control uses
plain-pass disabled. Record each rate with its exact KD counter deltas.
TCLock spin execution counters are unavailable in this backend; KD zero counts
on TCLock points do not establish an absence of TCLock delegation.

The signed entry fixture passed plain, IRQ, IRQ-save, IRQ-save-already-off,
BH and clobber contention: 60,000 operations per case, 30,000 per worker,
zero state/exclusion errors and normal unload. It ran before timing with
delegation off. The comparison additionally checks exact operation/write sums,
shared-data delta, progress of every worker, API checks, raw/nested/handback
and policy transitions. Full-suite and whole-kernel replacement are not claimed.

## Results

The first campaign completed 709 points with no failed count/state checks,
zero API failures, normal daemon exit and unload of all five comparison modules.
Parameters restored to adapt=Y, entry/exit=5/2, batch=4096, numa=Y,
plain-pass=N. There were no new kernel warnings. The full campaign (including
warmups and functional fixtures, not just timing) counted 484,774,048 delegated
bodies, 988,017 handbacks and 121 ordinary-waiter deferrals. Standard spin timing
cells have zero handbacks; the handback mechanism counts are separate.

The new plain-pass option has no established overall performance benefit:
32-worker short medians were 5.861 disabled and 5.723 enabled. Eight-worker
short medians were 5.408 and 5.434, with 47 ordinary deferrals in the three
enabled timing points. This is too small and inconsistent to justify changing
the default. The master implementation already has long sessions without it.

NUMA ordering is essential in this topology: KD at 32 workers was 5.719 with
ordering and 2.995 without for one line, 4.266 and 2.320 for 16 lines. This
matched control supports retaining NUMA ordering, not removing remote-node
selection to save its bookkeeping cost. The additional 176-point batch-limit campaign also completed in this same boot.


### Matched three-way results

Rates are median Mops/s over three measured repetitions; count columns are
KD deltas summed over those three repetitions, excluding warmups. Plain-pass
is off, NUMA order is on, batch=4096. These demonstrate the current master
protocol in the experimental binary, not a gain from the rejected change.
The same-image off control still contains inactive candidate code/layout.

| Lines | Workers | Native | KD | TCLock | KD delegated | KD handback |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 9.449 | 9.449 | 9.449 | 0 | 0 |
| 1 | 5 | 4.451 | 4.414 | 3.142 | 0 | 0 |
| 1 | 8 | 4.453 | 5.447 | 5.090 | 16,701,679 | 0 |
| 1 | 16 | 4.488 | 5.582 | 5.636 | 17,305,693 | 0 |
| 1 | 32 | 3.420 | 5.862 | 5.497 | 18,135,610 | 0 |
| 16 | 1 | 8.956 | 9.062 | 8.892 | 0 | 0 |
| 16 | 5 | 2.383 | 2.381 | 2.387 | 0 | 0 |
| 16 | 8 | 2.395 | 4.233 | 3.240 | 13,295,700 | 0 |
| 16 | 16 | 2.374 | 4.184 | 3.283 | 12,992,872 | 0 |
| 16 | 32 | 1.808 | 4.342 | 3.210 | 13,414,807 | 0 |

At 32 workers the short-section KD median is 71.4% above Native and 6.6%
above TCLock; the long-section median is 140.1% and 35.3% above respectively.
At 5 workers short KD remains 0.84% below Native with zero delegated bodies;
its additional adaptive queue work remains a source-level explanation, not
an isolated cycle profile. At 16 workers short KD is slightly below TCLock.
Do not generalize these microbenchmarks to all real-world lock users.

### Plain-pass A/B (KD)

| Lines | Workers | Off Mops/s | On Mops/s | Off delegated | On delegated | On plain deferrals | Handback off/on |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 5 | 4.416 | 4.416 | 0 | 0 | 0 | 0 / 0 |
| 1 | 8 | 5.408 | 5.434 | 16,528,063 | 16,642,884 | 47 | 0 / 0 |
| 1 | 32 | 5.861 | 5.723 | 18,045,359 | 17,737,306 | 3 | 0 / 0 |
| 16 | 5 | 2.382 | 2.382 | 0 | 0 | 0 | 0 / 0 |
| 16 | 8 | 4.239 | 4.239 | 13,402,690 | 13,304,945 | 3 | 0 / 0 |
| 16 | 32 | 4.334 | 4.313 | 13,572,641 | 13,488,233 | 4 | 0 / 0 |

The rare deferral events do not support attributing the entire observed
32-thread difference to deferral. The lack of repeatable improvement and
extra inactive slow-path work do not justify retaining the feature. Candidate
449078ff is archived at `refs/archive/local-spin-plain-pass-20261117` and its
four code/documentation files were reverted in d331e177. The fixture stays.

### Batch size at 32 balanced workers (KD)

| Batch | 1-line Mops/s | Delegated | Handback | 16-line Mops/s | Delegated | Handback |
|---:|---:|---:|---:|---:|---:|---:|
| 1024 | 5.890 | 18,272,074 | 0 | 4.208 | 13,037,128 | 0 |
| 4096 | 5.979 | 18,329,233 | 0 | 4.259 | 13,345,415 | 0 |
| 8192 | 5.783 | 17,965,082 | 0 | 4.270 | 13,178,028 | 0 |
| 16384 | 5.830 | 17,985,111 | 0 | 4.291 | 13,580,480 | 0 |

The existing 4096 default is retained. Larger limits do not improve short
sections here; the 16-line median gain at 16384 is below 1% and ranges overlap,
while the allowed delay for a remote waiter increases. All accompanying
Native/TCLock points and ranges are in batch/evidence-master-batch/summary.json.

### Execution counts and coverage

The first 709-point campaign totals (all phases, including warmups) are
484,774,048 delegated bodies, 988,017 handbacks, 1,122,897 sessions,
1,673 plain stops, 7,227,082 NUMA deferrals and 121 ordinary deferrals.
Handbacks came from spin_hb (560,030) and spin_hb_cl (427,987); standard
spin timing handback counts are zero. Ordinary deferrals are split into
49 policy-check, 15 policy-warmup and 57 measured policy events.
The separate 176-point batch campaign totals 170,593,329 delegated bodies,
zero handbacks, 60,078 sessions and 927,545 NUMA deferrals.
These totals are not denominators for a single timing cell. Raw per-point
counts and operation totals are in points.jsonl and rates-and-counts.csv.

Each campaign passed 65 API checks as well as every exact-count point.
No new BUG/WARNING/soft-lockup/Oops occurred; daemon exit was zero and all
comparison modules unloaded normally. Fixed-grant deterministic mixed
ordinary/raw/IRQ ordering was not separately established. Passing the runtime
checks does not replace such a proof or validate arbitrary whole-kernel use.

## Final state and reproducibility

The VM remains in the measured boot 1d97be13-778d-4aed-b4ca-ee0d8e9f459d,
with its archived experimental image, plain-pass disabled and default
batch/NUMA settings restored. Master has reverted the candidate; the running
image is therefore explicitly not claimed to be a rebuilt post-revert master.
This keeps the completed same-boot evidence available for inspection. No
unrequested kernel/source deletion or rollback of unrelated work occurred.

Image SHA256: d72be853ea22915a355bb8f0b06933734a116d22f5e5b22ffcc128e22153d036.
The fixture and runtime hashes, source overlay identity, topology, recovery
check and compiler logs accompany this report. Existing TCLock objtool
naked-return/BP warnings are retained as limitations, not clean mitigation
coverage. The original kernel16 and earlier local images remain intact.

The source/output directory was reused only after old builds drained; the
previous candidate2 artifacts were copied first and its task-created build
and source links were preserved with -at-install suffix. Original kernel16
links were untouched. New tools or packages were not installed.

A new scratch output backend could not attach because this VM has no hotplug
support on the attempted PCIe/SATA buses. No guest disk was written through
it; the backend was removed and its empty host file retained. Completed
archives were instead exported in paced 16 KiB reads and verified by SHA256:

* main campaign: d053e8cb6a98777e544d093699c9abb65eb8654a6a2f1460fd9b2be06b056192
* batch controls: 972da424ec968e1a1ee35023c2b07388a196b0f5bef80aad2087686c7cfe5007

The 380G10-only access rule is also persisted in master AGENTS.md (7314c384).
Final-state.json records the final idle, module and parameter checks.
