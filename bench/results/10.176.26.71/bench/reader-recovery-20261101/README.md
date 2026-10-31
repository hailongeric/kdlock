# Reader restoration: fresh Nano evidence and pending MM comparison

The isolated reader-restoration candidate remains **unaccepted**. All three
Nano arms completed and drained 210 points each, with one measurement per point
and full archived-data validation. The MM comparison is still pending; these
Nano results do not establish recovery of the known 60-process mmap1 loss.

The exact promoted provider is `1b6f256b13e8743aa1fd7bdc958cc82ae7726463`, merged
as `e0f9696cf7ba6268bbbfa5131a9ee881f6553809` under the documented one-time
[exception](../../../../../docs/design/writer_recovery_20261101.md).
The fresh Nano promoted arm measures that merge with identical provider bytes.
The candidate is `66c68c17457c0ae60d09ff1f3d89b5fff16a500c`; the fresh reference
is `f7a84065e84474380faa37eeadfdf534abd72a68`. The candidate restores the ordered
returning reader increment and original eight-probe read entry. Writer ownership,
phase/drain polling, cancellation, rollback and downgrade code remain unchanged.

## Comparison and acceptance

The future minor-loss policy requires every workload geometric mean to lose at
most 2%, and every point to lose at most 10%, separately for whole and qualified
peak throughput. The earlier -20.50% exception does not apply to this candidate.
`c01` means one cacheline, `c16` sixteen; `w1` and `w20` are 1% and 20% writes.
Every table entry includes all 21 worker counts, including NO_JIT points.
One sequential round provides no variance estimate or causal attribution.

| Lock / workload | Whole vs promoted | Peak vs promoted | Whole vs f7a84065 | Peak vs f7a84065 |
| --- | ---: | ---: | ---: | ---: |
| mutex c01 w100 | -0.908% | -0.908% | -0.890% | -0.905% |
| mutex c16 w100 | +1.026% | +1.013% | +1.150% | +1.178% |
| rwsem c01 w1 | +3.388% | +3.379% | +0.103% | +0.096% |
| rwsem c01 w20 | +1.960% | +1.910% | -0.142% | -0.126% |
| rwsem c16 w1 | +0.151% | +0.217% | +0.171% | +0.205% |
| rwsem c16 w20 | +0.404% | +0.366% | +0.775% | +0.758% |
| rwlock c01 w1 | +0.779% | +0.531% | -1.499% | -1.431% |
| rwlock c01 w20 | -0.110% | -0.094% | -0.025% | -0.112% |
| rwlock c16 w1 | -0.456% | -0.537% | -0.529% | -0.563% |
| rwlock c16 w20 | +0.415% | +0.258% | -0.248% | -0.146% |

Against the promoted version: workload-mean gate **True**, point gate **False**. Against the fresh f7a84065 reference: workload-mean gate **True**, point gate **False**.

All matched scores and losses are retained in the
[recovery/promoted comparison](nano/comparison/recovery-versus-promoted/points.csv),
[recovery/reference comparison](nano/comparison/recovery-versus-reference/points.csv)
and [promoted/reference comparison](nano/comparison/promoted-versus-reference/points.csv).
The [machine-readable summaries](nano/comparison-summary.json) retain separate
qualification, point, workload-mean and acceptance fields. Historical October 31
scores are not pooled into these comparisons.

The complete point grids are also shown in the [promoted comparison figure](figures/nano-recovery-versus-promoted.png) and [reference comparison figure](figures/nano-recovery-versus-reference.png). Both include every point and label losses beyond 10%.

The [four-worker mutex c01 inspection](nano/mutex-c01-n04/README.md) retains the
new outlier, worker CPU totals, raw records and static function-byte comparison.
It does not establish a parking cause or justify dropping that point.

## Correctness and measurement identity

The candidate passed eight basic/affected unit checks, including 21 deterministic
reader-count scenarios and 82 writer-queue scenarios with mutation controls.
Live local rwsem and mutex checks passed separately. Four-family basic checks
completed 1,600,000 operations per family with returned-JIT completion and drain.
The [candidate](correctness/recovery), [promoted](correctness/promoted) and
[reference](correctness/reference) receipts preserve their actual source identity.
Intentional failing inputs in unit logs are negative controls, not omitted tests.

All Nano arms used ordinary boot `8e8525e4-8024-48e8-8578-05efad0caf3e`,
`7.0.0-38-kdlock1`, Build ID `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`,
64 guest CPUs split 32/32 across NUMA nodes, worker CPUs starting at zero,
collector CPU63 and fixed host 2GHz. The active 131-task QEMU cohort and host
endpoints are retained per arm. The worker grid is 1..8 and 12..60 by four.
The post-work setting is 256; KD mutex limits remain 1024/1024.
No kernel build or MM timing overlapped Nano timing. The ordinary development
kernel has actual-MM replacement disabled; Nano does not validate the scoped
MM kernel. Source edits and offline archive inspection ran on 380G10;
compilation, fixtures and timing ran only in the VM.

Compressed raw archives, prerequisites and original controls are retained at
`bench/results/10.176.26.71/raw/bench/reader-recovery-20261101/` on 380G10.
Per-arm copy records bind every retained file to its original bytes. The
redundant transport container remains at its original temporary location.
No original evidence was deleted or rewritten. The [MM investigation](mm-investigation.md)
separates source findings, inference and unresolved attribution.

## MM preparation continuation

The `aeec505307fc01354bc3e660b7a64d0b279b7111` preparation failed the existing
all-profile writer-receipt test before composition. Documentation commit
`dbb724f2` and routing fix `9f9fb90e9de861fddeb498e068c0c31122919337` add the
missing explicit `kdscope4-native` / `kdscope4-kd` shared-MM routing. The frozen
corrected recipe passed the writer observation/return-site tests and all five
preparation unit groups, including that original failing assertion.

The next preparation completed composition but stopped before configuration or
compilation: the expected source-difference list omitted generated
`kd_mmap_mutex.h` and `kd_mmap_regs.h`. Their differences from scope1 reflect
existing continuation metadata in `include/kd_mutex.h` and `include/kd_regs.h`;
those source headers are identical between the promoted and recovery recipes.
The recovery recipe differs from the promoted recipe in `kd_rwsem.c` reader
entry, as intended. No MM body change is added by this correction.

Continue from the completed composition only after verifying its exact receipt,
all named source hashes, original preparation/configuration/recipe identities,
all successful unit/composition logs and absence of child processes. Add the
two reviewed header paths to the explicit six-file delta, then configure and
build into the still-absent output directory. Use new preparation/build records;
the two earlier failed preparations remain failed. No Nano point is repeated.
MM timing and recovery of the 60-process loss remain unverified.
