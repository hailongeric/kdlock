# Linux 7 completed benchmark coverage

**52 lock/API configurations and three MM suites are complete: 3,276 lock/API points plus 126 MM points, totaling 3,402 selected timed points.** Every selected coordinate has one 2-second round. These are separate frozen generations; this index joins coverage and links, not rates.

| Generation | Configurations | Points | Evidence |
| --- | ---: | ---: | --- |
| Checked-source lock/API |29|1,827|[Campaign](../catalog-linux70-20261027/README.md)|
| Trusted-source completed subset |22|1,386|[Aggregate audit](../catalog-linux70-trusted-20261028/AUDIT.md)|
| Prepared taskname20% |1|63|[Table/chart](../catalog-linux70-taskname-prepared-20261028/taskname-w20/README.md) · [Audit](../catalog-linux70-taskname-prepared-20261028/AUDIT.md)|

The fresh taskname cohort retained the same 20% measured mutation mix and restored the existing maximum-eight-wave preparation. All 21 KD coordinates returned a body during preparation and retained identical NORMAL publications across timing. Six timed points returned 99,339 bodies in total; fifteen executed locally with `NO_JIT`. The [strict 16-worker functional control](../../tests/taskname-w20-preparation-20261028/README.md) still failed its extra positive-JIT requirement; its successful preparation does not change that verdict.

| MM suite | Points | Results |
| --- | ---: | --- |
| Independent-mm Native control |21|[Table/chart](../catalog-linux70-mm-trusted-20261027/independent-mmap/README.md)|
| Private faults, three arms |63|[Table/chart](../catalog-linux70-mm-trusted-20261027/private-fault/README.md)|
| Shared-mm Native/KD modes |42|[Matched table/chart](../catalog-linux70-mm-shared-20261028/shared-mm/README.md)|

The private 84 and shared 42 points use their own campaign and kernel identities. The shared comparison uses the same enabled image and prepared binaries in two boot modes; Native was faster at all 21 worker counts. These observations do not establish improvement/parity for the MM milestone.

All timing remains exploratory: fixed 2.0 GHz host policy, allowed auxiliary workers on CPU63, one round and no repeat-based uncertainty estimate. The final [normal-kernel functional checkpoint](../../tests/linux70-normal-basic-20261028/README.md) and retained final idle receipt identify boot `15dc5977-59d3-4471-a196-d71f03f450ed`. Source leases, frame retirement, normal unload, publication checks and telemetry namespace checks remain intact.

Excluded attempts are preserved: the original checked taskname-w00 had two successful controls, one failed KD preparation and 60 unattempted points; the earlier trusted taskname-w20 had 23 successful points, one timed KD8 failure and 39 unattempted points. Neither partial cohort contributes to the 3,402 selected-point count. No failed point was overwritten, pooled or silently retried.

[Hash-bound selection and receipts](evidence.json)

| Selected workload | Generation | Table and chart |
| --- | --- | --- |
| nano-mutex-throughput | checked source | [Results](../catalog-linux70-20261027/nano-mutex-throughput/README.md) |
| nano-mutex-locality | checked source | [Results](../catalog-linux70-20261027/nano-mutex-locality/README.md) |
| nano-rwsem-throughput-read | checked source | [Results](../catalog-linux70-20261027/nano-rwsem-throughput-read/README.md) |
| nano-rwsem-throughput-mixed | checked source | [Results](../catalog-linux70-20261027/nano-rwsem-throughput-mixed/README.md) |
| nano-rwsem-locality-read | checked source | [Results](../catalog-linux70-20261027/nano-rwsem-locality-read/README.md) |
| nano-rwsem-locality-mixed | checked source | [Results](../catalog-linux70-20261027/nano-rwsem-locality-mixed/README.md) |
| nano-rwlock-throughput-read | checked source | [Results](../catalog-linux70-20261027/nano-rwlock-throughput-read/README.md) |
| nano-rwlock-throughput-mixed | checked source | [Results](../catalog-linux70-20261027/nano-rwlock-throughput-mixed/README.md) |
| nano-rwlock-locality-read | checked source | [Results](../catalog-linux70-20261027/nano-rwlock-locality-read/README.md) |
| nano-rwlock-locality-mixed | checked source | [Results](../catalog-linux70-20261027/nano-rwlock-locality-mixed/README.md) |
| spin-c01 | checked source | [Results](../catalog-linux70-20261027/spin-c01/README.md) |
| spin-c08 | checked source | [Results](../catalog-linux70-20261027/spin-c08/README.md) |
| spin-rcuht | checked source | [Results](../catalog-linux70-20261027/spin-rcuht/README.md) |
| rwlock-c01-w01 | checked source | [Results](../catalog-linux70-20261027/rwlock-c01-w01/README.md) |
| rwlock-c01-w20 | checked source | [Results](../catalog-linux70-20261027/rwlock-c01-w20/README.md) |
| rwlock-c08-w01 | checked source | [Results](../catalog-linux70-20261027/rwlock-c08-w01/README.md) |
| rwlock-c08-w20 | checked source | [Results](../catalog-linux70-20261027/rwlock-c08-w20/README.md) |
| rwlock-rcuht-w01 | checked source | [Results](../catalog-linux70-20261027/rwlock-rcuht-w01/README.md) |
| rwlock-rcuht-w20 | checked source | [Results](../catalog-linux70-20261027/rwlock-rcuht-w20/README.md) |
| rwsem-c01-w01 | checked source | [Results](../catalog-linux70-20261027/rwsem-c01-w01/README.md) |
| rwsem-c01-w20 | checked source | [Results](../catalog-linux70-20261027/rwsem-c01-w20/README.md) |
| rwsem-c08-w01 | checked source | [Results](../catalog-linux70-20261027/rwsem-c08-w01/README.md) |
| rwsem-c08-w20 | checked source | [Results](../catalog-linux70-20261027/rwsem-c08-w20/README.md) |
| rwsem-rcuht-w01 | checked source | [Results](../catalog-linux70-20261027/rwsem-rcuht-w01/README.md) |
| rwsem-rcuht-w20 | checked source | [Results](../catalog-linux70-20261027/rwsem-rcuht-w20/README.md) |
| argbounds-w00 | checked source | [Results](../catalog-linux70-20261027/argbounds-w00/README.md) |
| argbounds-w20 | checked source | [Results](../catalog-linux70-20261027/argbounds-w20/README.md) |
| ofd-front-n16 | checked source | [Results](../catalog-linux70-20261027/ofd-front-n16/README.md) |
| ofd-front-n128 | checked source | [Results](../catalog-linux70-20261027/ofd-front-n128/README.md) |
| taskname-w00 | trusted source | [Results](../catalog-linux70-trusted-20261028/taskname-w00/README.md) |
| ofd-tail-n16 | trusted source | [Results](../catalog-linux70-trusted-20261028/ofd-tail-n16/README.md) |
| ofd-tail-n128 | trusted source | [Results](../catalog-linux70-trusted-20261028/ofd-tail-n128/README.md) |
| ofd-miss-n16 | trusted source | [Results](../catalog-linux70-trusted-20261028/ofd-miss-n16/README.md) |
| ofd-miss-n128 | trusted source | [Results](../catalog-linux70-trusted-20261028/ofd-miss-n128/README.md) |
| setfd-toggle-n16 | trusted source | [Results](../catalog-linux70-trusted-20261028/setfd-toggle-n16/README.md) |
| setfd-toggle-n512 | trusted source | [Results](../catalog-linux70-trusted-20261028/setfd-toggle-n512/README.md) |
| pipebytes-query-n16 | trusted source | [Results](../catalog-linux70-trusted-20261028/pipebytes-query-n16/README.md) |
| pipebytes-query-n128 | trusted source | [Results](../catalog-linux70-trusted-20261028/pipebytes-query-n128/README.md) |
| pipecap-query-n16 | trusted source | [Results](../catalog-linux70-trusted-20261028/pipecap-query-n16/README.md) |
| seek-set-n16 | trusted source | [Results](../catalog-linux70-trusted-20261028/seek-set-n16/README.md) |
| seek-end-n16 | trusted source | [Results](../catalog-linux70-trusted-20261028/seek-end-n16/README.md) |
| utsname-host-n20 | trusted source | [Results](../catalog-linux70-trusted-20261028/utsname-host-n20/README.md) |
| utsname-domain-n20 | trusted source | [Results](../catalog-linux70-trusted-20261028/utsname-domain-n20/README.md) |
| xattr-front-n16 | trusted source | [Results](../catalog-linux70-trusted-20261028/xattr-front-n16/README.md) |
| xattr-front-n128 | trusted source | [Results](../catalog-linux70-trusted-20261028/xattr-front-n128/README.md) |
| xattr-tail-n16 | trusted source | [Results](../catalog-linux70-trusted-20261028/xattr-tail-n16/README.md) |
| xattr-tail-n128 | trusted source | [Results](../catalog-linux70-trusted-20261028/xattr-tail-n128/README.md) |
| xattr-miss-n16 | trusted source | [Results](../catalog-linux70-trusted-20261028/xattr-miss-n16/README.md) |
| xattr-miss-n128 | trusted source | [Results](../catalog-linux70-trusted-20261028/xattr-miss-n128/README.md) |
| xattr-size-n16 | trusted source | [Results](../catalog-linux70-trusted-20261028/xattr-size-n16/README.md) |
| xattr-size-n128 | trusted source | [Results](../catalog-linux70-trusted-20261028/xattr-size-n128/README.md) |
| taskname-w20 | trusted source; eight-wave preparation | [Results](../catalog-linux70-taskname-prepared-20261028/taskname-w20/README.md) |
