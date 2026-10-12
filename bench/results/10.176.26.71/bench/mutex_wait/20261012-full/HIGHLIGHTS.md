# Derived comparison summaries

Every count is an equally weighted workload/count point, not an independent application. A win against both backends requires KD >= Native and KD >= TCLock. Strict wins require both median whole-run throughput and best warmed peak. Incomplete/rejected cohorts are excluded from the affected arm's wins and ratios, and remain in the complete tables. A complete comparison for the other KD arm remains scored.

| Cohort | KD policy | Complete/total | Whole wins | Peak wins | Strict wins |
| --- | --- | ---: | ---: | ---: | ---: |
| all-multithread | kd-spin | 651/651 | 540 | 527 | 519 |
| all-multithread | kd-blocking | 649/651 | 521 | 520 | 502 |
| mutex-multithread | kd-spin | 189/189 | 128 | 125 | 124 |
| mutex-multithread | kd-blocking | 189/189 | 123 | 121 | 119 |
| mutex-at-least-four | kd-spin | 171/171 | 120 | 117 | 117 |
| mutex-at-least-four | kd-blocking | 171/171 | 118 | 114 | 114 |
| mutex-16-through-60 | kd-spin | 108/108 | 87 | 84 | 84 |
| mutex-16-through-60 | kd-blocking | 108/108 | 85 | 81 | 81 |
| mutex-single-thread | kd-spin | 9/9 | 0 | 0 | 0 |
| mutex-single-thread | kd-blocking | 9/9 | 0 | 0 | 0 |
| spin-multithread | kd-spin | 168/168 | 124 | 118 | 113 |
| spin-multithread | kd-blocking | 166/168 | 115 | 112 | 104 |
| rwlock-multithread | kd-spin | 294/294 | 288 | 284 | 282 |
| rwlock-multithread | kd-blocking | 294/294 | 283 | 287 | 279 |
| api-multithread | kd-spin | 231/231 | 179 | 177 | 172 |
| api-multithread | kd-blocking | 231/231 | 171 | 173 | 164 |
| all-t01 | kd-spin | 31/31 | 17 | 14 | 14 |
| all-t01 | kd-blocking | 31/31 | 15 | 14 | 12 |
| mutex-t01 | kd-spin | 9/9 | 0 | 0 | 0 |
| mutex-t01 | kd-blocking | 9/9 | 0 | 0 | 0 |
| all-t04 | kd-spin | 31/31 | 22 | 21 | 21 |
| all-t04 | kd-blocking | 31/31 | 19 | 21 | 18 |
| mutex-t04 | kd-spin | 9/9 | 4 | 4 | 4 |
| mutex-t04 | kd-blocking | 9/9 | 4 | 4 | 4 |
| all-t08 | kd-spin | 31/31 | 22 | 21 | 21 |
| all-t08 | kd-blocking | 31/31 | 22 | 22 | 22 |
| mutex-t08 | kd-spin | 9/9 | 4 | 4 | 4 |
| mutex-t08 | kd-blocking | 9/9 | 4 | 4 | 4 |
| all-t16 | kd-spin | 31/31 | 26 | 26 | 26 |
| all-t16 | kd-blocking | 31/31 | 25 | 26 | 25 |
| mutex-t16 | kd-spin | 9/9 | 5 | 5 | 5 |
| mutex-t16 | kd-blocking | 9/9 | 5 | 5 | 5 |
| all-t32 | kd-spin | 31/31 | 28 | 27 | 27 |
| all-t32 | kd-blocking | 30/31 | 27 | 26 | 26 |
| mutex-t32 | kd-spin | 9/9 | 7 | 7 | 7 |
| mutex-t32 | kd-blocking | 9/9 | 7 | 7 | 7 |
| all-t36 | kd-spin | 31/31 | 28 | 27 | 27 |
| all-t36 | kd-blocking | 31/31 | 27 | 26 | 25 |
| mutex-t36 | kd-spin | 9/9 | 7 | 6 | 6 |
| mutex-t36 | kd-blocking | 9/9 | 6 | 5 | 5 |
| all-t60 | kd-spin | 31/31 | 30 | 30 | 29 |
| all-t60 | kd-blocking | 31/31 | 30 | 31 | 30 |
| mutex-t60 | kd-spin | 9/9 | 9 | 9 | 9 |
| mutex-t60 | kd-blocking | 9/9 | 9 | 9 | 9 |
| all-t64 | kd-spin | 31/31 | 29 | 26 | 26 |
| all-t64 | kd-blocking | 31/31 | 28 | 27 | 26 |
| mutex-t64 | kd-spin | 9/9 | 9 | 9 | 9 |
| mutex-t64 | kd-blocking | 9/9 | 9 | 9 | 9 |

## All subjects at 60 workers

Median whole-run Mops/s. At 64 workers, the last worker and collector share a physical core.

| Subject | Stock | Native | TCLock | KD spin | KD blocking |
| --- | ---: | ---: | ---: | ---: | ---: |
| mutex-cacheline-c01 | — | 3.764 | 3.155 | 5.052 | 4.932 |
| mutex-cacheline-c08 | — | 2.861 | 2.684 | 4.205 | 4.046 |
| mutex-cacheline-c16 | — | 2.724 | 2.193 | 4.120 | 3.844 |
| mutex-rcuht | — | 1.643 | 1.695 | 2.035 | 1.998 |
| ofd-tail-n128-v64 | 1.649 | 1.652 | 2.170 | 2.150 | 2.160 |
| ofd-tail-n16-v64 | 2.631 | 2.695 | 3.979 | 4.697 | 4.546 |
| pipebytes-query-n128-v64 | 1.910 | 2.043 | 2.188 | 2.746 | 2.691 |
| pipebytes-query-n16-v64 | 1.706 | 1.749 | 2.448 | 5.539 | 5.399 |
| pipecap-query-n16-v64 | 1.699 | 1.794 | 2.428 | 5.739 | 5.699 |
| rwlock-cacheline-c01-w01 | — | 13.949 | 15.125 | 16.765 | 16.905 |
| rwlock-cacheline-c01-w20 | — | 6.621 | 7.413 | 13.598 | 13.710 |
| rwlock-cacheline-c02-w01 | — | 13.408 | 14.498 | 16.789 | 17.107 |
| rwlock-cacheline-c02-w20 | — | 6.428 | 7.370 | 13.411 | 13.322 |
| rwlock-cacheline-c04-w01 | — | 13.418 | 15.013 | 16.398 | 16.410 |
| rwlock-cacheline-c04-w20 | — | 6.733 | 7.232 | 12.892 | 12.892 |
| rwlock-cacheline-c08-w01 | — | 13.520 | 14.556 | 15.972 | 15.695 |
| rwlock-cacheline-c08-w20 | — | 5.486 | 7.183 | 11.222 | 11.410 |
| rwlock-cacheline-c16-w01 | — | 11.779 | 14.758 | 15.050 | 14.881 |
| rwlock-cacheline-c16-w20 | — | 4.703 | 6.684 | 9.039 | 8.959 |
| rwlock-rcuht-w01 | — | 12.914 | 14.303 | 14.389 | 14.414 |
| rwlock-rcuht-w20 | — | 5.020 | 4.937 | 6.513 | 6.528 |
| seek-end-n16-v64 | 1.165 | 1.294 | 2.554 | 3.914 | 3.816 |
| seek-set-n16-v64 | 1.131 | 1.321 | 2.482 | 3.866 | 3.820 |
| setfd-toggle-n16-v64 | 2.428 | 2.461 | 4.929 | 5.252 | 5.243 |
| setfd-toggle-n512-v64 | 2.835 | 2.789 | 4.713 | 7.458 | 7.517 |
| spin-cacheline-c01 | — | 4.156 | 4.690 | 6.946 | 7.064 |
| spin-cacheline-c08 | — | 3.413 | 3.189 | 7.261 | 7.494 |
| spin-cacheline-c16 | — | 2.487 | 2.556 | 7.955 | 8.532 |
| spin-rcuht | — | 1.622 | 2.146 | 2.654 | 2.653 |
| utsname-domain-n20-v64 | 0.577 | 0.545 | 2.073 | 3.250 | 3.265 |
| utsname-host-n20-v64 | 0.546 | 0.477 | 2.692 | 3.406 | 3.293 |

## All subjects at 64 workers

Median whole-run Mops/s. At 64 workers, the last worker and collector share a physical core.

| Subject | Stock | Native | TCLock | KD spin | KD blocking |
| --- | ---: | ---: | ---: | ---: | ---: |
| mutex-cacheline-c01 | — | 3.387 | 3.345 | 4.987 | 4.868 |
| mutex-cacheline-c08 | — | 2.624 | 2.749 | 4.127 | 3.934 |
| mutex-cacheline-c16 | — | 2.406 | 2.175 | 4.026 | 3.843 |
| mutex-rcuht | — | 1.542 | 1.674 | 2.015 | 1.983 |
| ofd-tail-n128-v64 | 1.759 | 1.756 | 2.171 | 2.228 | 2.139 |
| ofd-tail-n16-v64 | 2.702 | 2.752 | 3.968 | 4.442 | 4.627 |
| pipebytes-query-n128-v64 | 1.831 | 1.908 | 2.175 | 2.715 | 2.667 |
| pipebytes-query-n16-v64 | 1.573 | 1.722 | 2.473 | 5.403 | 5.262 |
| pipecap-query-n16-v64 | 1.589 | 1.716 | 2.540 | 5.686 | 5.599 |
| rwlock-cacheline-c01-w01 | — | 14.248 | 15.198 | 17.412 | 17.191 |
| rwlock-cacheline-c01-w20 | — | 7.998 | 7.362 | 14.765 | 15.032 |
| rwlock-cacheline-c02-w01 | — | 13.945 | 14.304 | 17.369 | 17.181 |
| rwlock-cacheline-c02-w20 | — | 8.263 | 7.270 | 14.608 | 15.191 |
| rwlock-cacheline-c04-w01 | — | 14.434 | 15.067 | 17.038 | 16.883 |
| rwlock-cacheline-c04-w20 | — | 8.203 | 7.245 | 14.204 | 14.853 |
| rwlock-cacheline-c08-w01 | — | 13.670 | 15.081 | 16.361 | 16.077 |
| rwlock-cacheline-c08-w20 | — | 7.100 | 7.199 | 12.205 | 13.482 |
| rwlock-cacheline-c16-w01 | — | 12.279 | 14.351 | 15.643 | 15.383 |
| rwlock-cacheline-c16-w20 | — | 6.168 | 6.622 | 9.712 | 10.178 |
| rwlock-rcuht-w01 | — | 13.032 | 14.759 | 14.100 | 14.494 |
| rwlock-rcuht-w20 | — | 5.233 | 4.928 | 6.573 | 6.586 |
| seek-end-n16-v64 | 1.122 | 1.319 | 2.470 | 3.828 | 3.778 |
| seek-set-n16-v64 | 1.124 | 1.313 | 2.505 | 3.850 | 3.768 |
| setfd-toggle-n16-v64 | 2.547 | 2.570 | 4.859 | 5.468 | 5.474 |
| setfd-toggle-n512-v64 | 2.511 | 2.893 | 4.713 | 7.564 | 7.606 |
| spin-cacheline-c01 | — | 3.806 | 4.747 | 6.932 | 6.936 |
| spin-cacheline-c08 | — | 3.421 | 3.150 | 7.320 | 7.540 |
| spin-cacheline-c16 | — | 2.251 | 2.530 | 8.111 | 8.387 |
| spin-rcuht | — | 1.572 | 2.136 | 2.639 | 2.638 |
| utsname-domain-n20-v64 | 0.577 | 0.550 | 2.278 | 3.195 | 3.169 |
| utsname-host-n20-v64 | 0.568 | 0.584 | 2.291 | 2.082 | 2.097 |

## Largest mutex blocking losses against spin

Multithreaded cases sorted by median whole-run blocking/spin ratio; all original samples remain scored.

| Subject | Workers | Blocking/spin whole | Blocking/spin peak |
| --- | ---: | ---: | ---: |
| mutex-cacheline-c01 | 2 | 0.699× | 1.074× |
| mutex-cacheline-c08 | 2 | 0.727× | 0.702× |
| mutex-cacheline-c16 | 2 | 0.799× | 0.865× |
| mutex-cacheline-c01 | 4 | 0.867× | 0.869× |
| mutex-cacheline-c08 | 4 | 0.890× | 1.098× |
| pipebytes-query-n16-v64 | 5 | 0.894× | 0.892× |
| mutex-cacheline-c16 | 8 | 0.898× | 0.863× |
| seek-end-n16-v64 | 8 | 0.902× | 0.937× |
| mutex-cacheline-c16 | 44 | 0.910× | 0.934× |
| mutex-cacheline-c16 | 4 | 0.913× | 0.829× |
| mutex-cacheline-c16 | 52 | 0.923× | 0.929× |
| mutex-cacheline-c16 | 16 | 0.923× | 0.935× |
| seek-set-n16-v64 | 20 | 0.927× | 0.941× |
| mutex-rcuht | 3 | 0.932× | 0.943× |
| mutex-cacheline-c16 | 60 | 0.933× | 0.940× |
| mutex-cacheline-c08 | 5 | 0.937× | 0.822× |
| seek-end-n16-v64 | 2 | 0.938× | 0.896× |
| pipecap-query-n16-v64 | 5 | 0.939× | 0.988× |
| mutex-cacheline-c08 | 12 | 0.939× | 0.925× |
| mutex-cacheline-c08 | 3 | 0.941× | 0.840× |

## Retained exclusions

These sessions remain in the raw evidence and samples. Their measured rates are unscored; an affected three-round cohort is incomplete. Repeat numbers are zero-based.

| Subject | Workers | Backend | Repeat | Status | JIT bodies | Drained |
| --- | ---: | --- | ---: | --- | ---: | --- |
| spin-cacheline-c01 | 20 | kd-blocking | 2 | NO_JIT | 0 | True |
| spin-cacheline-c01 | 32 | kd-blocking | 1 | NO_JIT | 0 | True |
