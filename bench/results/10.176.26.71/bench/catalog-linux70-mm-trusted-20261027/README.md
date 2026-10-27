# Linux 7 single-round MM catalog

Configured host policy: 2.0 GHz. One plain two-second round per point; timing remains exploratory.
Private backing locks and actual shared-mm locking are separate suites. Kernel/boot/source identities remain in the phase receipts.

| Suite | Measured / planned | Attempted without qualified rate | Results |
| --- | ---: | ---: | --- |
| independent-mmap | 21 / 21 | 0 | [Table and chart](independent-mmap/README.md) |
| private-fault | 63 / 63 | 0 | [Table and chart](private-fault/README.md) |
| shared-mm | 0 / 42 | 0 | Pending |

[Phase and preservation receipts](phases.json). Failed and uncertain attempts are retained; no retries or repetition variance are inferred.
