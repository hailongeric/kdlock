# Linux 7 single-round benchmark catalog

Kernel: `7.0.0-38-kdlock1`. Fixed host policy: 2.0 GHz. One timed round per coordinate.
Workers: 1–8, then 12–60 by four. Auxiliary QEMU workers stay on CPU63; timing is exploratory, with no repetition variance estimate.

| Workload | Valid/planned | State | Table and chart |
| --- | ---: | --- | --- |
| nano-mutex-throughput | 63/63 | COMPLETE | [Results](nano-mutex-throughput/README.md) |
| nano-mutex-locality | 63/63 | COMPLETE | [Results](nano-mutex-locality/README.md) |
| nano-rwsem-throughput-read | 63/63 | COMPLETE | [Results](nano-rwsem-throughput-read/README.md) |
| nano-rwsem-throughput-mixed | 63/63 | COMPLETE | [Results](nano-rwsem-throughput-mixed/README.md) |
| nano-rwsem-locality-read | 63/63 | COMPLETE | [Results](nano-rwsem-locality-read/README.md) |
| nano-rwsem-locality-mixed | 63/63 | COMPLETE | [Results](nano-rwsem-locality-mixed/README.md) |
| nano-rwlock-throughput-read | 63/63 | COMPLETE | [Results](nano-rwlock-throughput-read/README.md) |
| nano-rwlock-throughput-mixed | 63/63 | COMPLETE | [Results](nano-rwlock-throughput-mixed/README.md) |
| nano-rwlock-locality-read | 63/63 | COMPLETE | [Results](nano-rwlock-locality-read/README.md) |
| nano-rwlock-locality-mixed | 63/63 | COMPLETE | [Results](nano-rwlock-locality-mixed/README.md) |
| spin-c01 | 63/63 | COMPLETE | [Results](spin-c01/README.md) |
| spin-c08 | 63/63 | COMPLETE | [Results](spin-c08/README.md) |
| spin-rcuht | 63/63 | COMPLETE | [Results](spin-rcuht/README.md) |
| rwlock-c01-w01 | 63/63 | COMPLETE | [Results](rwlock-c01-w01/README.md) |
| rwlock-c01-w20 | 63/63 | COMPLETE | [Results](rwlock-c01-w20/README.md) |
| rwlock-c08-w01 | 63/63 | COMPLETE | [Results](rwlock-c08-w01/README.md) |
| rwlock-c08-w20 | 63/63 | COMPLETE | [Results](rwlock-c08-w20/README.md) |
| rwlock-rcuht-w01 | 63/63 | COMPLETE | [Results](rwlock-rcuht-w01/README.md) |
| rwlock-rcuht-w20 | 63/63 | COMPLETE | [Results](rwlock-rcuht-w20/README.md) |
| rwsem-c01-w01 | 63/63 | COMPLETE | [Results](rwsem-c01-w01/README.md) |
| rwsem-c01-w20 | 63/63 | COMPLETE | [Results](rwsem-c01-w20/README.md) |
| rwsem-c08-w01 | 63/63 | COMPLETE | [Results](rwsem-c08-w01/README.md) |
| rwsem-c08-w20 | 63/63 | COMPLETE | [Results](rwsem-c08-w20/README.md) |
| rwsem-rcuht-w01 | 63/63 | COMPLETE | [Results](rwsem-rcuht-w01/README.md) |
| rwsem-rcuht-w20 | 63/63 | COMPLETE | [Results](rwsem-rcuht-w20/README.md) |
| argbounds-w00 | 63/63 | COMPLETE | [Results](argbounds-w00/README.md) |
| argbounds-w20 | 63/63 | COMPLETE | [Results](argbounds-w20/README.md) |
| taskname-w00 | 2/63 | STOPPED | [Results](taskname-w00/README.md) |
| ofd-front-n16 | 63/63 | COMPLETE | [Results](ofd-front-n16/README.md) |
| ofd-front-n128 | 63/63 | COMPLETE | [Results](ofd-front-n128/README.md) |

[Command plan](plan.json) · [Progress receipts](progress.json)

This source generation was paused at a drained workload boundary after 29
complete matrices (1,827 timed measurements), plus the separately retained
partial taskname attempt. Those measurements used the earlier checked source
policy. The later trusted-source translator is validated separately in the
[ordinary-translation record](../../tests/ordinary-string-translation-20261027/README.md).
Remaining workloads will use a new campaign and frozen source identity; rates
from these source policies must not be pooled.
