# Per-workload comparison at 60 workers

Each row is one separately identified workload. Rates are whole-run Mops/s at 60 workers from one audited observation per backend. **No workload averages, pooled source versions or repeat means.** Strict timing qualification remains failed; host frequency target is 2.0 GHz. Ratios are descriptive, not statistical superiority or latency claims. Pending/missing/failed or score-ineligible points have no ratio.

[Full dimensions, identities and precision](comparison-60.csv). Every plotted/table rate was matched against its per-workload audit. Original source/kernel/call-shell distinctions remain in those reports. Only completed-backend archive-audited MM rows enter this comparison; a partial MM table can be newer.

| Workload | Setting | Native | TCLock | KD | KD / Native | KD / TCLock | KD execution | Audited measured / planned |
|:---|:---|---:|---:|---:|---:|---:|:---|---:|
| [nano-mutex-throughput](nano-mutex-throughput/README.md) | mutex; c1; w100; post256 | 1.610 | 2.634 | 4.863 | 3.020× | 1.846× | RETURNED_JIT | 63 / 63 |
| [nano-mutex-locality](nano-mutex-locality/README.md) | mutex; c16; w100; post256 | 1.448 | 1.806 | 3.871 | 2.674× | 2.143× | RETURNED_JIT | 63 / 63 |
| [nano-rwsem-throughput-read](nano-rwsem-throughput-read/README.md) | rwsem; c1; w1; post256 | 3.165 | 7.941 | 5.788 | 1.829× | 0.729× | NO_JIT | 63 / 63 |
| [nano-rwsem-throughput-mixed](nano-rwsem-throughput-mixed/README.md) | rwsem; c1; w20; post256 | 1.255 | 4.767 | 1.812 | 1.444× | 0.380× | RETURNED_JIT | 63 / 63 |
| [nano-rwsem-locality-read](nano-rwsem-locality-read/README.md) | rwsem; c16; w1; post256 | 2.588 | 9.896 | 6.583 | 2.543× | 0.665× | NO_JIT | 63 / 63 |
| [nano-rwsem-locality-mixed](nano-rwsem-locality-mixed/README.md) | rwsem; c16; w20; post256 | 1.175 | 3.811 | 1.775 | 1.510× | 0.466× | RETURNED_JIT | 63 / 63 |
| [nano-rwlock-throughput-read](nano-rwlock-throughput-read/README.md) | rwlock; c1; w1; post256 | 6.932 | 7.859 | 7.639 | 1.102× | 0.972× | RETURNED_JIT | 63 / 63 |
| [nano-rwlock-throughput-mixed](nano-rwlock-throughput-mixed/README.md) | rwlock; c1; w20; post256 | 3.055 | 4.325 | 3.560 | 1.165× | 0.823× | RETURNED_JIT | 63 / 63 |
| [nano-rwlock-locality-read](nano-rwlock-locality-read/README.md) | rwlock; c16; w1; post256 | 9.075 | 10.166 | 8.374 | 0.923× | 0.824× | RETURNED_JIT | 63 / 63 |
| [nano-rwlock-locality-mixed](nano-rwlock-locality-mixed/README.md) | rwlock; c16; w20; post256 | 2.415 | 3.920 | 2.425 | 1.004× | 0.619× | RETURNED_JIT | 63 / 63 |
| [spin-c01](spin-c01/README.md) | spin; c1; w100; post64 | 4.399 | 3.987 | 7.796 | 1.772× | 1.955× | RETURNED_JIT | 63 / 63 |
| [spin-c08](spin-c08/README.md) | spin; c8; w100; post64 | 3.141 | 3.139 | 7.688 | 2.447× | 2.449× | RETURNED_JIT | 63 / 63 |
| [spin-rcuht](spin-rcuht/README.md) | spin; rcuht; w100; post64 | 1.512 | 2.007 | 2.330 | 1.541× | 1.161× | RETURNED_JIT | 63 / 63 |
| [spin-list16](spin-list16/README.md) | spin; list16; w100; post64 | 0.922 | 3.423 | 7.003 | 7.592× | 2.046× | RETURNED_JIT | 63 / 63 |
| [mutex-c01](mutex-c01/README.md) | mutex; c1; w100; post64 | 3.698 | 2.730 | 4.943 | 1.337× | 1.811× | RETURNED_JIT | 63 / 63 |
| [mutex-c08](mutex-c08/README.md) | mutex; c8; w100; post64 | 3.218 | 2.353 | 4.070 | 1.265× | 1.730× | RETURNED_JIT | 63 / 63 |
| [mutex-rcuht](mutex-rcuht/README.md) | mutex; rcuht; w100; post64 | 2.080 | 1.544 | 2.095 | 1.007× | 1.357× | RETURNED_JIT | 63 / 63 |
| [mutex-list16](mutex-list16/README.md) | mutex; list16; w100; post64 | 2.115 | 2.303 | 4.196 | 1.983× | 1.822× | RETURNED_JIT | 63 / 63 |
| [rwlock-c01-w01](rwlock-c01-w01/README.md) | rwlock; c1; w1; post4 | 11.253 | 8.782 | 12.204 | 1.085× | 1.390× | RETURNED_JIT | 63 / 63 |
| [rwlock-c01-w20](rwlock-c01-w20/README.md) | rwlock; c1; w20; post4 | 4.596 | 5.201 | 9.465 | 2.059× | 1.820× | NO_JIT | 63 / 63 |
| [rwlock-c08-w01](rwlock-c08-w01/README.md) | rwlock; c8; w1; post4 | 10.339 | 10.624 | 11.641 | 1.126× | 1.096× | RETURNED_JIT | 63 / 63 |
| [rwlock-c08-w20](rwlock-c08-w20/README.md) | rwlock; c8; w20; post4 | 3.716 | 5.195 | 8.138 | 2.190× | 1.566× | RETURNED_JIT | 63 / 63 |
| [rwlock-rcuht-w01](rwlock-rcuht-w01/README.md) | rwlock; rcuht; w1; post4 | 10.659 | 10.575 | 10.819 | 1.015× | 1.023× | RETURNED_JIT | 63 / 63 |
| [rwlock-rcuht-w20](rwlock-rcuht-w20/README.md) | rwlock; rcuht; w20; post4 | 3.903 | 4.134 | 5.372 | 1.377× | 1.299× | RETURNED_JIT | 63 / 63 |
| [rwlock-list16-w01](rwlock-list16-w01/README.md) | rwlock; list16; w1; post4 | 8.181 | 8.063 | 10.274 | 1.256× | 1.274× | RETURNED_JIT | 63 / 63 |
| [rwlock-list16-w20](rwlock-list16-w20/README.md) | rwlock; list16; w20; post4 | 2.182 | 3.440 | 4.465 | 2.046× | 1.298× | RETURNED_JIT | 63 / 63 |
| [rwsem-c01-w01](rwsem-c01-w01/README.md) | rwsem; c1; w1; post4 | 2.830 | 12.987 | 6.731 | 2.378× | 0.518× | NO_JIT | 63 / 63 |
| [rwsem-c01-w20](rwsem-c01-w20/README.md) | rwsem; c1; w20; post4 | 2.709 | 6.917 | 1.935 | 0.714× | 0.280× | RETURNED_JIT | 63 / 63 |
| [rwsem-c08-w01](rwsem-c08-w01/README.md) | rwsem; c8; w1; post4 | 2.634 | 12.531 | 7.205 | 2.736× | 0.575× | NO_JIT | 63 / 63 |
| [rwsem-c08-w20](rwsem-c08-w20/README.md) | rwsem; c8; w20; post4 | 2.727 | 6.216 | 2.059 | 0.755× | 0.331× | RETURNED_JIT | 63 / 63 |
| [rwsem-rcuht-w01](rwsem-rcuht-w01/README.md) | rwsem; rcuht; w1; post4 | 2.715 | 12.481 | 6.102 | 2.248× | 0.489× | NO_JIT | 63 / 63 |
| [rwsem-rcuht-w20](rwsem-rcuht-w20/README.md) | rwsem; rcuht; w20; post4 | 1.504 | 4.686 | 1.935 | 1.287× | 0.413× | RETURNED_JIT | 63 / 63 |
| [rwsem-list16-w01](rwsem-list16-w01/README.md) | rwsem; list16; w1; post4 | 2.516 | 9.787 | 6.127 | 2.435× | 0.626× | NO_JIT | 63 / 63 |
| [rwsem-list16-w20](rwsem-list16-w20/README.md) | rwsem; list16; w20; post4 | 3.381 | 4.605 | 1.806 | 0.534× | 0.392× | RETURNED_JIT | 63 / 63 |
| [argbounds-w00](argbounds-w00/README.md) | spin; argbounds; w0; post4 | 3.702 | 4.402 | 2.808 | 0.758× | 0.638× | RETURNED_JIT | 63 / 63 |
| [argbounds-w20](argbounds-w20/README.md) | spin; argbounds; w20; post4 | 3.588 | 4.222 | 3.058 | 0.852× | 0.724× | NO_JIT | 63 / 63 |
| [taskname-w00](taskname-w00/README.md) | spin; taskname; w0; post4 | 3.687 | 4.380 | 4.185 | 1.135× | 0.956× | RETURNED_JIT | 63 / 63 |
| [taskname-w20](taskname-w20/README.md) | spin; taskname; w20; post4 | 3.721 | 4.268 | 2.954 | 0.794× | 0.692× | RETURNED_JIT | 63 / 63 |
| [ofd-front-n16](ofd-front-n16/README.md) | spin; front; n16 | 2.597 | 3.779 | 3.234 | 1.245× | 0.856× | RETURNED_JIT | 63 / 63 |
| [ofd-front-n128](ofd-front-n128/README.md) | spin; front; n128 | 2.739 | 3.888 | 3.249 | 1.186× | 0.836× | RETURNED_JIT | 63 / 63 |
| [ofd-tail-n16](ofd-tail-n16/README.md) | spin; tail; n16 | 2.643 | 3.730 | 3.940 | 1.491× | 1.056× | RETURNED_JIT | 63 / 63 |
| [ofd-tail-n128](ofd-tail-n128/README.md) | spin; tail; n128 | 1.579 | 1.779 | 1.881 | 1.191× | 1.057× | RETURNED_JIT | 63 / 63 |
| [ofd-miss-n16](ofd-miss-n16/README.md) | spin; miss; n16 | 2.599 | 3.200 | 3.850 | 1.482× | 1.203× | RETURNED_JIT | 63 / 63 |
| [ofd-miss-n128](ofd-miss-n128/README.md) | spin; miss; n128 | 1.523 | 1.714 | 1.854 | 1.217× | 1.081× | RETURNED_JIT | 63 / 63 |
| [setfd-toggle-n16](setfd-toggle-n16/README.md) | spin; toggle; n16 | 2.291 | 4.351 | 4.670 | 2.038× | 1.073× | RETURNED_JIT | 63 / 63 |
| [setfd-toggle-n512](setfd-toggle-n512/README.md) | spin; toggle; n512 | 2.727 | 4.349 | 6.394 | 2.345× | 1.470× | RETURNED_JIT | 63 / 63 |
| [pipebytes-query-n16](pipebytes-query-n16/README.md) | mutex; query; n16 | 2.143 | 2.024 | 4.819 | 2.248× | 2.381× | RETURNED_JIT | 63 / 63 |
| [pipebytes-query-n128](pipebytes-query-n128/README.md) | mutex; query; n128 | 2.844 | 1.816 | 3.212 | 1.129× | 1.768× | RETURNED_JIT | 63 / 63 |
| [pipecap-query-n16](pipecap-query-n16/README.md) | mutex; query; n16 | 2.137 | 2.067 | 4.976 | 2.328× | 2.407× | RETURNED_JIT | 63 / 63 |
| [seek-set-n16](seek-set-n16/README.md) | mutex; set; n16 | 1.391 | 2.027 | 4.009 | 2.882× | 1.978× | RETURNED_JIT | 63 / 63 |
| [seek-end-n16](seek-end-n16/README.md) | mutex; end; n16 | 1.435 | 2.085 | 3.994 | 2.783× | 1.916× | RETURNED_JIT | 63 / 63 |
| [utsname-host-n20](utsname-host-n20/README.md) | rwlock; host; n20 | 0.882 | 2.806 | 3.059 | 3.468× | 1.090× | RETURNED_JIT | 63 / 63 |
| [utsname-domain-n20](utsname-domain-n20/README.md) | rwlock; domain; n20 | 1.128 | 2.899 | 2.979 | 2.640× | 1.028× | RETURNED_JIT | 63 / 63 |
| [xattr-front-n16](xattr-front-n16/README.md) | spin; front; n16 | 2.648 | 3.423 | — | — | — | PREPARATION_FAILED | 42 / 63 |
| [xattr-front-n128](xattr-front-n128/README.md) | spin; front; n128 | 2.669 | 3.461 | — | — | — | PREPARATION_FAILED | 43 / 63 |
| [xattr-tail-n16](xattr-tail-n16/README.md) | spin; tail; n16 | 1.876 | 2.026 | — | — | — | PREPARATION_FAILED | 42 / 63 |
| [xattr-tail-n128](xattr-tail-n128/README.md) | spin; tail; n128 | 0.429 | 0.468 | — | — | — | PREPARATION_FAILED | 42 / 63 |
| [xattr-miss-n16](xattr-miss-n16/README.md) | spin; miss; n16 | 1.649 | 2.156 | — | — | — | PREPARATION_FAILED | 50 / 63 |
| [xattr-miss-n128](xattr-miss-n128/README.md) | spin; miss; n128 | 0.447 | 0.476 | — | — | — | PREPARATION_FAILED | 42 / 63 |
| [xattr-size-n16](xattr-size-n16/README.md) | spin; size; n16 | 1.963 | 2.119 | 1.910 | 0.973× | 0.901× | RETURNED_JIT | 60 / 63 |
| [xattr-size-n128](xattr-size-n128/README.md) | spin; size; n128 | 0.441 | 0.474 | — | — | — | PREPARATION_FAILED | 44 / 63 |
| [mm-mmap](mm-mmap/README.md) | independent-mm mmap/munmap, untouched mapping | 0.439 | — | — | — | — | UNMEASURED | 21 / 21 |
| [mm-fault](mm-fault/README.md) | private-backing MADV_DONTNEED plus checked CPU read | 4.807 | 5.608 | 5.636 | 1.173× | 1.005× | LOCAL_MM_CONTRACT | 63 / 63 |
| [mm-shared](mm-shared/README.md) | shared-mm mmap/munmap, untouched 4 KiB device mapping | 0.133 | — | 0.006 | 0.048× | — | LOCAL_MM_CONTRACT | 42 / 42 |

NO_JIT gains do not establish delegation. LOCAL_MM_CONTRACT identifies locally executed native MM/backing bodies; it is not a sampled JIT verdict. The shared-mm installed kernel retains its historical implementation identity, distinct from the current controller source. No peak-to-whole or cross-workload normalization is used.
