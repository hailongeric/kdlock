# Linux 7 shared-MM single-round campaign

All **42 selected shared-MM points** completed and drained: Native and KD at
1–8 workers and 12–60 in steps of four, one plain two-second round per point.
Both modes use the same `7.0.0-38-kdmm1` image, configuration, source and prepared
client/payload binaries. Fresh same-boot correctness receipts precede each grid.
Host policy was fixed at 2GHz; timing remains exploratory, with no repeat-based
variance estimate.

| Selected suite | Completed / planned | Attempted without a qualified rate | Results |
| --- | ---: | ---: | --- |
| Actual shared-mm mmap/munmap | 42 / 42 | 0 | [Matched table and charts](shared-mm/README.md) |

Native was faster at all 21 matched worker counts in this run. At one worker,
Native measured 0.373048 Mops/s and KD 0.365013; at sixty workers, Native measured
0.154433 and KD 0.006731. These observations do not identify a cause or establish
a universal performance ordering. Native MM bodies run on their original task;
this suite performs no body delegation.

**The 84 private-MM points are not selected in this campaign.** They completed
in the separate [original private-MM campaign](../catalog-linux70-mm-trusted-20261027/README.md)
and are neither repeated nor imported here. See [SCOPE.md](SCOPE.md) for the
source-generation and kernel boundaries.

[Phase and preservation receipts](phases.json) retain the final 16 phases.
The [kernel checkpoint](../../tests/linux70-kdmm1-20261027/README.md) links the
independent audits and preserves the earlier failed mapping attempt and separate
diagnostic. [Native table](shared-native/README.md) and [KD table](shared-kd/README.md)
retain every point and its raw receipt. Strict timing qualification remains false.
