# Linux 7 single-round benchmark catalog

Kernel: `7.0.0-38-kdlock1`. Fixed host policy: 2.0 GHz. One timed round per coordinate.
Workers: 1–8, then 12–60 by four. Auxiliary QEMU workers stay on CPU63; timing is exploratory, with no repetition variance estimate.

Source policy: trusted kernel/module source; semantic safety admission is bypassed. This campaign keeps its own frozen input identities.

| Workload | Valid/planned | State | Table and chart |
| --- | ---: | --- | --- |
| taskname-w00 | 63/63 | COMPLETE | [Results](taskname-w00/README.md) |
| taskname-w20 | 23/63 | STOPPED | [Results](taskname-w20/README.md) |
| ofd-tail-n16 | 63/63 | COMPLETE | [Results](ofd-tail-n16/README.md) |
| ofd-tail-n128 | 63/63 | COMPLETE | [Results](ofd-tail-n128/README.md) |
| ofd-miss-n16 | 63/63 | COMPLETE | [Results](ofd-miss-n16/README.md) |
| ofd-miss-n128 | 63/63 | COMPLETE | [Results](ofd-miss-n128/README.md) |
| setfd-toggle-n16 | 63/63 | COMPLETE | [Results](setfd-toggle-n16/README.md) |
| setfd-toggle-n512 | 63/63 | COMPLETE | [Results](setfd-toggle-n512/README.md) |
| pipebytes-query-n16 | 63/63 | COMPLETE | [Results](pipebytes-query-n16/README.md) |
| pipebytes-query-n128 | 63/63 | COMPLETE | [Results](pipebytes-query-n128/README.md) |
| pipecap-query-n16 | 63/63 | COMPLETE | [Results](pipecap-query-n16/README.md) |
| seek-set-n16 | 63/63 | COMPLETE | [Results](seek-set-n16/README.md) |
| seek-end-n16 | 63/63 | COMPLETE | [Results](seek-end-n16/README.md) |
| utsname-host-n20 | 63/63 | COMPLETE | [Results](utsname-host-n20/README.md) |
| utsname-domain-n20 | 63/63 | COMPLETE | [Results](utsname-domain-n20/README.md) |
| xattr-front-n16 | 63/63 | COMPLETE | [Results](xattr-front-n16/README.md) |
| xattr-front-n128 | 63/63 | COMPLETE | [Results](xattr-front-n128/README.md) |
| xattr-tail-n16 | 63/63 | COMPLETE | [Results](xattr-tail-n16/README.md) |
| xattr-tail-n128 | 63/63 | COMPLETE | [Results](xattr-tail-n128/README.md) |
| xattr-miss-n16 | 63/63 | COMPLETE | [Results](xattr-miss-n16/README.md) |
| xattr-miss-n128 | 63/63 | COMPLETE | [Results](xattr-miss-n128/README.md) |
| xattr-size-n16 | 63/63 | COMPLETE | [Results](xattr-size-n16/README.md) |
| xattr-size-n128 | 63/63 | COMPLETE | [Results](xattr-size-n128/README.md) |

[Command plan](plan.json) · [Progress receipts](progress.json)
