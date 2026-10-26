# Full selected catalog at fixed 2.0 GHz

One two-second observation per worker/backend point; 21 worker counts (1–8, then 12–60 by four). The selected plan has **61 lock/API configurations (3,843 points)** plus **three MM suites (126 points)**. Every workload has a table and chart backed by its replayed archive.

**Completed:** 3,830 valid measurements and 139 drained xattr preparation
failures account for all 3,969 planned points. No points were rerun or left
unattempted. All ten nano profiles passed their 630 measurements and warmups.
The [final audit](validation.json) verifies the archives, source/binary
identities, exact checks, 65 frequency streams and final recovery. The focused
VM checks passed two basic programs and 61 Python cases; MM preparation passed
18 split cases, eight client controls and nine negative-oracle checks.

[Cross-workload comparison](COMPARISON.md) · [Xattr preparation failures](XATTR_PREPARATION.md) · [MM results and interpretation](MM_INTERPRETATION.md)

The guest returned to `6.1.159-kdclobber2`, with the original 73 modules, zero
taint and idle state. All 64 host policies remain fixed at the requested
2.0 GHz with turbo disabled. Host APERF/MPERF samples with busy fraction greater
than 0.5 have an MPERF-weighted mean of 1,999.97 MHz; low-activity ratios and
sampling limits remain in the audit.

**EXPLORATORY:** strict host task-membership qualification remains failed. The host frequency target is 2.0 GHz minimum = maximum, performance governor and turbo disabled. Endpoint readbacks are bound in each audit; effective-frequency and final environment evidence are separate. One round supplies no repeat-variability estimate. Historical campaign rates are not pooled.

The ten nano profiles use padded c01/c16 counters with post256. Existing micro c01/c08, list16, RCUHT and API configurations retain their own bodies and call shells. MM uses separately recorded kernels/backends; the three suites do not represent generic page-fault or unchanged mmap1 coverage.

| Lock/API workload | Measured | Failed / unrun | Results |
|:---|---:|---:|:---|
| `nano-mutex-throughput` | 63 | 0 / 0 | [Table and chart](nano-mutex-throughput/README.md) |
| `nano-mutex-locality` | 63 | 0 / 0 | [Table and chart](nano-mutex-locality/README.md) |
| `nano-rwsem-throughput-read` | 63 | 0 / 0 | [Table and chart](nano-rwsem-throughput-read/README.md) |
| `nano-rwsem-throughput-mixed` | 63 | 0 / 0 | [Table and chart](nano-rwsem-throughput-mixed/README.md) |
| `nano-rwsem-locality-read` | 63 | 0 / 0 | [Table and chart](nano-rwsem-locality-read/README.md) |
| `nano-rwsem-locality-mixed` | 63 | 0 / 0 | [Table and chart](nano-rwsem-locality-mixed/README.md) |
| `nano-rwlock-throughput-read` | 63 | 0 / 0 | [Table and chart](nano-rwlock-throughput-read/README.md) |
| `nano-rwlock-throughput-mixed` | 63 | 0 / 0 | [Table and chart](nano-rwlock-throughput-mixed/README.md) |
| `nano-rwlock-locality-read` | 63 | 0 / 0 | [Table and chart](nano-rwlock-locality-read/README.md) |
| `nano-rwlock-locality-mixed` | 63 | 0 / 0 | [Table and chart](nano-rwlock-locality-mixed/README.md) |
| `spin-c01` | 63 | 0 / 0 | [Table and chart](spin-c01/README.md) |
| `spin-c08` | 63 | 0 / 0 | [Table and chart](spin-c08/README.md) |
| `spin-rcuht` | 63 | 0 / 0 | [Table and chart](spin-rcuht/README.md) |
| `spin-list16` | 63 | 0 / 0 | [Table and chart](spin-list16/README.md) |
| `mutex-c01` | 63 | 0 / 0 | [Table and chart](mutex-c01/README.md) |
| `mutex-c08` | 63 | 0 / 0 | [Table and chart](mutex-c08/README.md) |
| `mutex-rcuht` | 63 | 0 / 0 | [Table and chart](mutex-rcuht/README.md) |
| `mutex-list16` | 63 | 0 / 0 | [Table and chart](mutex-list16/README.md) |
| `rwlock-c01-w01` | 63 | 0 / 0 | [Table and chart](rwlock-c01-w01/README.md) |
| `rwlock-c01-w20` | 63 | 0 / 0 | [Table and chart](rwlock-c01-w20/README.md) |
| `rwlock-c08-w01` | 63 | 0 / 0 | [Table and chart](rwlock-c08-w01/README.md) |
| `rwlock-c08-w20` | 63 | 0 / 0 | [Table and chart](rwlock-c08-w20/README.md) |
| `rwlock-rcuht-w01` | 63 | 0 / 0 | [Table and chart](rwlock-rcuht-w01/README.md) |
| `rwlock-rcuht-w20` | 63 | 0 / 0 | [Table and chart](rwlock-rcuht-w20/README.md) |
| `rwlock-list16-w01` | 63 | 0 / 0 | [Table and chart](rwlock-list16-w01/README.md) |
| `rwlock-list16-w20` | 63 | 0 / 0 | [Table and chart](rwlock-list16-w20/README.md) |
| `rwsem-c01-w01` | 63 | 0 / 0 | [Table and chart](rwsem-c01-w01/README.md) |
| `rwsem-c01-w20` | 63 | 0 / 0 | [Table and chart](rwsem-c01-w20/README.md) |
| `rwsem-c08-w01` | 63 | 0 / 0 | [Table and chart](rwsem-c08-w01/README.md) |
| `rwsem-c08-w20` | 63 | 0 / 0 | [Table and chart](rwsem-c08-w20/README.md) |
| `rwsem-rcuht-w01` | 63 | 0 / 0 | [Table and chart](rwsem-rcuht-w01/README.md) |
| `rwsem-rcuht-w20` | 63 | 0 / 0 | [Table and chart](rwsem-rcuht-w20/README.md) |
| `rwsem-list16-w01` | 63 | 0 / 0 | [Table and chart](rwsem-list16-w01/README.md) |
| `rwsem-list16-w20` | 63 | 0 / 0 | [Table and chart](rwsem-list16-w20/README.md) |
| `argbounds-w00` | 63 | 0 / 0 | [Table and chart](argbounds-w00/README.md) |
| `argbounds-w20` | 63 | 0 / 0 | [Table and chart](argbounds-w20/README.md) |
| `taskname-w00` | 63 | 0 / 0 | [Table and chart](taskname-w00/README.md) |
| `taskname-w20` | 63 | 0 / 0 | [Table and chart](taskname-w20/README.md) |
| `ofd-front-n16` | 63 | 0 / 0 | [Table and chart](ofd-front-n16/README.md) |
| `ofd-front-n128` | 63 | 0 / 0 | [Table and chart](ofd-front-n128/README.md) |
| `ofd-tail-n16` | 63 | 0 / 0 | [Table and chart](ofd-tail-n16/README.md) |
| `ofd-tail-n128` | 63 | 0 / 0 | [Table and chart](ofd-tail-n128/README.md) |
| `ofd-miss-n16` | 63 | 0 / 0 | [Table and chart](ofd-miss-n16/README.md) |
| `ofd-miss-n128` | 63 | 0 / 0 | [Table and chart](ofd-miss-n128/README.md) |
| `setfd-toggle-n16` | 63 | 0 / 0 | [Table and chart](setfd-toggle-n16/README.md) |
| `setfd-toggle-n512` | 63 | 0 / 0 | [Table and chart](setfd-toggle-n512/README.md) |
| `pipebytes-query-n16` | 63 | 0 / 0 | [Table and chart](pipebytes-query-n16/README.md) |
| `pipebytes-query-n128` | 63 | 0 / 0 | [Table and chart](pipebytes-query-n128/README.md) |
| `pipecap-query-n16` | 63 | 0 / 0 | [Table and chart](pipecap-query-n16/README.md) |
| `seek-set-n16` | 63 | 0 / 0 | [Table and chart](seek-set-n16/README.md) |
| `seek-end-n16` | 63 | 0 / 0 | [Table and chart](seek-end-n16/README.md) |
| `utsname-host-n20` | 63 | 0 / 0 | [Table and chart](utsname-host-n20/README.md) |
| `utsname-domain-n20` | 63 | 0 / 0 | [Table and chart](utsname-domain-n20/README.md) |
| `xattr-front-n16` | 42 | 21 / 0 | [Table and chart](xattr-front-n16/README.md) |
| `xattr-front-n128` | 43 | 20 / 0 | [Table and chart](xattr-front-n128/README.md) |
| `xattr-tail-n16` | 42 | 21 / 0 | [Table and chart](xattr-tail-n16/README.md) |
| `xattr-tail-n128` | 42 | 21 / 0 | [Table and chart](xattr-tail-n128/README.md) |
| `xattr-miss-n16` | 50 | 13 / 0 | [Table and chart](xattr-miss-n16/README.md) |
| `xattr-miss-n128` | 42 | 21 / 0 | [Table and chart](xattr-miss-n128/README.md) |
| `xattr-size-n16` | 60 | 3 / 0 | [Table and chart](xattr-size-n16/README.md) |
| `xattr-size-n128` | 44 | 19 / 0 | [Table and chart](xattr-size-n128/README.md) |

Published lock/API workloads: **61/61**; measured **3704/3,843**, failed **139**. Unpublished points are not counted as completed.

| Separate MM suite | Planned points | Results |
|:---|---:|:---|
| `mm-mmap` | 21 | [Table and chart](mm-mmap/README.md) |
| `mm-fault` | 63 | [Table and chart](mm-fault/README.md) |
| `mm-shared` | 42 | [Table and chart](mm-shared/README.md) |

[Per-workload 60-worker comparison](COMPARISON.md) · [Full dimensions and precision](comparison-60.csv). No cross-workload averages are used.
