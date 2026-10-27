# Linux 7 single-round benchmark catalog

Kernel: `7.0.0-38-kdlock1`. Fixed host policy: 2.0 GHz. One timed round per coordinate.
Workers: 1–8, then 12–60 by four. Auxiliary QEMU workers stay on CPU63; timing is exploratory, with no repetition variance estimate.

Source policy: trusted kernel/module source; semantic safety admission is bypassed. This campaign keeps its own frozen input identities.

| Workload | Valid/planned | State | Table and chart |
| --- | ---: | --- | --- |
| taskname-w00 | 0/63 | STOPPED | Pending |

[Command plan](plan.json) · [Progress receipts](progress.json)
