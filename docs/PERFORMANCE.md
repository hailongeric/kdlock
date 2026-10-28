# Performance status

The [complete Linux 7 catalog](../bench/results/10.176.26.71/bench/catalog-linux70-complete-20261028/README.md)
contains **3,402 selected timed observations**. Every selected coordinate has
one two-second round at the requested fixed 2.0 GHz host policy. Timing remains
**exploratory; strict qualification is failed**. There are no repeat-based
uncertainty estimates, and no rates are pooled across frozen generations.

## Coverage and interpretation

| Cohort | Complete configurations | Points | Identity / evidence |
| --- | ---: | ---: | --- |
| Earlier checked-source lock/API | 29 | 1,827 | [Campaign](../bench/results/10.176.26.71/bench/catalog-linux70-20261027/README.md) |
| Trusted-source completed subset | 22 | 1,386 | [Audit](../bench/results/10.176.26.71/bench/catalog-linux70-trusted-20261028/AUDIT.md) |
| Trusted mixed taskname with restored preparation | 1 | 63 | [Prepared cohort](../bench/results/10.176.26.71/bench/catalog-linux70-taskname-prepared-20261028/README.md) |
| Separate MM suites | 3 suites | 126 | Private and actual shared-MM identities below |

The worker grid is `1..8,12..60`, stepping by four above eight, with Native,
TCLock and KD where implemented. Exact data/progress, image identity and normal
drain are distinct from host timing qualification. Configured frequency limits
and sampled APERF/MPERF support the recorded policy, not an exact effective
frequency at every instruction.

`RETURNED_JIT` requires actual returned generated-body evidence. Successful
`NO_JIT` records local KD execution; it can have a valid rate without proving
a delegation gain. `NORMAL` proves publication only. Failed preparation or
partial generated execution contributes no accepted throughput.

## Cross-NUMA rwsem reader cohorts

The [reader-cohort comparison](../bench/results/10.176.26.71/bench/rwsem-numa-20261028/README.md)
at `acc4dbc2e283` gives queued readers a turn before a new writer phase. At 60
workers with 20% writes and post256, KD c01 improved from 3.164 to 3.729 Mops/s
and c16 from 2.390 to 3.600; fresh TCLock controls reached 4.542 and 3.713,
leaving gaps of 17.9% and 3.0%. Each point has one round, so these are exploratory
observations without repeat variability estimates. Readers remain local, and
1024/1024 was already the baseline delegation policy. In separate instrumented
c01 samples, the shared OSQ function's profile share fell from 79.787% to 25.571%;
this does not identify its reader and writer callers separately. Existing
positive writer cohorts can still accept reservations.

## KD rwsem c01, 20% writes: queued reader admission

The [October 28 focused comparison](../bench/results/10.176.26.71/bench/rwsem-c01-w20-20261028/README.md)
measures c01, 20% writes and post256 on Linux 7 at 8/16/32/60 workers, with
three rounds and fresh TCLock controls for each source. All readers execute
locally. KD now makes eight short admission attempts before joining an abortable
queue whose head alone performs the longer shared-count polling stage.

At 16 and 32 workers, KD median rates changed from 4.225/3.174 to
5.028/5.062 Mops/s; all those runs had zero writer JIT execution. At 60 workers,
the implementation comparison is 1.875 to 3.139 Mops/s, with baseline returned
writer JIT and final local execution retained as distinct classes. Final TCLock
medians were 5.523/5.982/4.596 at 16/32/60. KD therefore still trails TCLock;
eight-worker cases retain a regression and mixed execution classes. This fixes
the observed within-node decline in the sampled 16–32 range, not every rwsem
performance limitation. The first queued-only candidate and all adverse samples
are preserved. Timing remains exploratory, separate from the catalog above and
from actual-MM performance.

## Current nano measurements

The [October 28 current-source round](../bench/results/10.176.26.71/bench/nano-current-20261028/README.md)
at `6d8c8be7` completed all ten c01/c16 post256 workloads on the full worker
grid: **630/630 timings and 630/630 warmups**, one repetition per point, with
Native/TCLock/KD and no real-world API runs. It includes KD mutex 1024/1024,
queued rwsem reader admission and the trusted-source translator policy.
The report provides every worker count, execution class and scaling chart.

At 60 workers, KD mutex c01/c16 reached 4.279/3.946 Mops/s versus TCLock's
2.588/1.665. Every rwsem and rwlock workload remained below TCLock there;
rwlock c16 with 1% writes also remained below Native. Rwsem c01 with 20% writes
was nearly flat at 4.932–5.137 Mops/s over 16–32 workers, then fell to 3.146
at 60. These are single observations with no repeat variability estimate;
they remain separate from the earlier catalog and focused repeated experiment.

## Earlier checked-source nano measurements

The following **Linux 7 checked-source cohort** uses the maintained c01/c16
padded-counter bodies, post256, mutex cap 1024 and locality boundary 768.
That recorded policy predates the October 28 user-selected KD default of
1024/1024; these measurements do not validate the new default.
These are 60-worker whole-run Mops/s, not medians or cross-version aggregates.
Each profile link contains the full curve, local points and adverse counts.

| Profile | Native | TCLock | KD | KD / Native | KD / TCLock | KD execution at 60 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| [mutex-locality](../bench/results/10.176.26.71/bench/catalog-linux70-20261027/nano-mutex-locality/README.md) | 1.539 | 1.724 | 4.140 | 2.691× | 2.402× | RETURNED_JIT |
| [mutex-throughput](../bench/results/10.176.26.71/bench/catalog-linux70-20261027/nano-mutex-throughput/README.md) | 1.734 | 2.588 | 4.485 | 2.586× | 1.733× | RETURNED_JIT |
| [rwlock-locality-mixed](../bench/results/10.176.26.71/bench/catalog-linux70-20261027/nano-rwlock-locality-mixed/README.md) | 2.366 | 3.972 | 2.418 | 1.022× | 0.609× | RETURNED_JIT |
| [rwlock-locality-read](../bench/results/10.176.26.71/bench/catalog-linux70-20261027/nano-rwlock-locality-read/README.md) | 9.316 | 11.011 | 8.340 | 0.895× | 0.757× | RETURNED_JIT |
| [rwlock-throughput-mixed](../bench/results/10.176.26.71/bench/catalog-linux70-20261027/nano-rwlock-throughput-mixed/README.md) | 3.208 | 4.133 | 3.588 | 1.119× | 0.868× | RETURNED_JIT |
| [rwlock-throughput-read](../bench/results/10.176.26.71/bench/catalog-linux70-20261027/nano-rwlock-throughput-read/README.md) | 6.903 | 7.832 | 7.472 | 1.082× | 0.954× | RETURNED_JIT |
| [rwsem-locality-mixed](../bench/results/10.176.26.71/bench/catalog-linux70-20261027/nano-rwsem-locality-mixed/README.md) | 1.088 | 3.775 | 1.910 | 1.755× | 0.506× | RETURNED_JIT |
| [rwsem-locality-read](../bench/results/10.176.26.71/bench/catalog-linux70-20261027/nano-rwsem-locality-read/README.md) | 2.355 | 10.261 | 6.332 | 2.688× | 0.617× | NO_JIT |
| [rwsem-throughput-mixed](../bench/results/10.176.26.71/bench/catalog-linux70-20261027/nano-rwsem-throughput-mixed/README.md) | 1.168 | 4.726 | 1.803 | 1.544× | 0.382× | RETURNED_JIT |
| [rwsem-throughput-read](../bench/results/10.176.26.71/bench/catalog-linux70-20261027/nano-rwsem-throughput-read/README.md) | 2.737 | 7.764 | 5.652 | 2.066× | 0.728× | NO_JIT |

Both mutex profiles exceed Native and TCLock at 60 workers. All four rwsem
profiles exceed Native there but remain below TCLock; the two reader-heavy
profiles are local `NO_JIT`, so those gains do not establish delegation gains.
The rwlock locality/read profile loses to Native at 60 workers, and all four
rwlock profiles remain below TCLock there. Favorable high-count results do not
remove low-count costs or establish a universal optimum.

These observations combine the lock algorithm, compiler call shell, post-work
and contention pattern. They do not isolate cache, batching or NUMA causes.
The earlier factor/boundary studies retain their own source and frequency
identities in [historical evidence](history/README.md).

## Trusted-source API measurements

The [22-workload audit](../bench/results/10.176.26.71/bench/catalog-linux70-trusted-20261028/AUDIT.md)
records 214 KD returned-JIT points and 248 successful local points. The eight
Linux 7 xattr profiles contribute 168 local points by design: they use shared
rb-tree readers, not the historical exclusive spin/helper protocol.

The separate [prepared mixed-taskname curve](../bench/results/10.176.26.71/bench/catalog-linux70-taskname-prepared-20261028/taskname-w20/README.md)
completed 63 points. Six KD points returned 99,339 generated bodies in total;
fifteen completed locally. Every KD coordinate completed returned-body learning
before timing and retained the same NORMAL publication, but that did not force
delegation during measurement.

The original mixed-taskname partial attempt retains 23 valid points, one failed
KD8 timing and 39 unrun points. The strict unscored 16-worker `--require-jit`
control remains failed because its measured interval returned no JIT body.
Neither result is overwritten by the prepared timed curve. [Validation](VALIDATION.md)
links the exact boundaries and failed receipts.

## Separate mmap and page-fault measurements

The [private-MM campaign](../bench/results/10.176.26.71/bench/catalog-linux70-mm-trusted-20261027/README.md)
completed 21 Native independent-mm mappings and 63 Native/TCLock/KD private-backing
fault cycles on `kdlock1`. The actual kernel mmap lock remains Native in both
suites; their backing-reader results cannot establish actual-MM improvement.

The [shared-MM comparison](../bench/results/10.176.26.71/bench/catalog-linux70-mm-shared-20261028/shared-mm/README.md)
uses the same enabled `7.0.0-38-kdmm1` image/configuration and prepared binaries in
two explicit modes. Native measured higher throughput at **all 21 worker counts**.
Whole-run complete mmap/munmap pairs per second are:

| Workers | Native | KD | KD / Native |
| ---: | ---: | ---: | ---: |
| 1 | 373,048 | 365,013 | 0.9785× |
| 16 | 295,099 | 44,061 | 0.1493× |
| 60 | 154,433 | 6,731 | 0.0436× |

The one-worker deficit is 2.15%, without a repeat-variability estimate. These
local-lock-backend rates do not measure MM-body JIT delegation. No profiling-based
cause or accepted Linux 7 optimization is established. The scoped MM improvement
or parity gate remains unmet; exact `mmap1` and generic actual-backend fault
throughput remain future work.

## Historical evidence

Older mutex layouts, queue policies, string services, Linux 6.1 curves and stopped
three-repeat campaign plans retain their original results and failures. The
[history index](history/README.md) links their result records and the fixed full
performance narrative before this cleanup. They are not current support,
current-kernel comparisons or instructions to resume retired adaptation.
