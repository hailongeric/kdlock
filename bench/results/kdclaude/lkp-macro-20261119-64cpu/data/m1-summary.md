| workload | | 4 | 16 | 32 | 48 | 64 | delegated, handbacks, hb_region |
|---|---|---|---|---|---|---|---|
| pbe-ctl | native, ops/s | 7.651e+05 | 1.586e+05 | 7.449e+04 | 3.169e+04 | 2.28e+04 | |
| | off/native | 1.16 | 1.13 | 1.10 | 1.39 | 1.59 | |
| | on/native | 1.11 | 1.61 | 1.62 | 2.44 | 2.36 | 45346691, 11, 11 |
| sysbench-threads | native, events/s | 7913 | 6288 | 5919 | 5737 | 5252 | |
| | off/native | 1.06 | 1.10 | 1.04 | 1.04 | 1.00 | |
| | on/native | 1.05 | 1.01 | 0.98 | 1.02 | 0.97 | 1951291, 2154, 0 |
| filebench-varmail | native, ops/s | 5.775e+05 | 6.879e+05 | 6.772e+05 | 6.517e+05 | 6.049e+05 | |
| | off/native | 1.01 | 0.99 | 1.03 | 1.03 | 0.99 | |
| | on/native | 0.93 | 0.95 | 0.98 | 0.99 | 0.98 | 2384951, 6959, 381 |
| filebench-webserver | native, ops/s | 6.823e+05 | 7.095e+05 | 7.443e+05 | 7.181e+05 | 6.591e+05 | |
| | off/native | 0.96 | 1.00 | 0.99 | 1.01 | 0.99 | |
| | on/native | 1.00 | 1.04 | 1.10 | 0.98 | 0.99 | 3925032, 4679, 0 |
| fio-randwrite-shared | native, iops | 8.797e+05 | 9.441e+05 | 9.97e+05 | 8.425e+05 | 8.025e+05 | |
| | off/native | 0.82 | 0.86 | 0.90 | 0.89 | 0.87 | |
| | on/native | 0.78 | 0.81 | 0.79 | 0.85 | 0.86 | 170, 2264, 0 |
| vms-lru-file-mmap-read | native, KB/s | 9.126e+07 | 9.602e+07 | 1.063e+08 | 1.075e+08 | 1.005e+08 | |
| | off/native | 0.92 | 1.02 | 1.00 | 1.00 | 0.98 | |
| | on/native | 1.01 | 1.02 | 0.97 | 0.96 | 0.98 | 48, 0, 0 |
| dbench-ext4 | native, MB/s | 3623 | 8794 | 1.104e+04 | 1.232e+04 | 1.186e+04 | |
| | off/native | 0.98 | 0.95 | 1.01 | 0.97 | 0.98 | |
| | on/native | 0.99 | 0.90 | 0.93 | 0.92 | 0.93 | 0, 0, 0 |
| wis-brk1 | native, ops/s | 7.579e+05 | 6.792e+05 | 6.788e+05 | 4.576e+05 | 3.596e+05 | |
| | off/native | 1.11 | 1.07 | 1.06 | 1.65 | 2.19 | |
| | on/native | 1.08 | 1.07 | 1.06 | 1.09 | 1.72 | 3022374, 1389463, 242 |
| wis-mmap1 | native, ops/s | 2.774e+05 | 2.786e+05 | 2.366e+05 | 1.447e+05 | 1.226e+05 | |
| | off/native | 1.01 | 1.04 | 1.27 | 1.51 | 1.70 | |
| | on/native | 0.99 | 0.98 | 1.05 | 1.53 | 1.56 | 54, 12078, 0 |
| wisp-pread2 | native, ops/s | 3.206e+06 | 2.312e+06 | 2.247e+06 | 1.571e+06 | 1.55e+06 | |
| | off/native | 0.88 | 1.00 | 1.02 | 1.05 | 1.03 | |
| | on/native | 0.94 | 0.98 | 1.02 | 0.41 | 0.51 | 8909268, 1987378, 1766245 |
| sng-shm | native, bogo/s | 1240 | 3795 | 3848 | 3818 | 3486 | |
| | off/native | 0.99 | 1.21 | 1.22 | 1.23 | 1.14 | |
| | on/native | 0.99 | 0.97 | 1.28 | 1.33 | 1.52 | 53741863, 1265, 0 |
| vms-small-allocs | native, KB/s | 8.299e+06 | 2.46e+07 | 2.464e+07 | 2.071e+07 | 1.9e+07 | |
| | off/native | 1.00 | 0.99 | 1.01 | 1.05 | 1.06 | |
| | on/native | 1.00 | 1.06 | 1.37 | 1.91 | 2.61 | 23172619, 11, 11 |
| ub-execl | native, lps | 8603 | 2.902e+04 | 3.098e+04 | 2.811e+04 | 2.63e+04 | |
| | off/native | 1.00 | 0.98 | 0.99 | 1.03 | 0.98 | |
| | on/native | 0.97 | 0.88 | 1.13 | 1.46 | 1.66 | 92274381, 30, 30 |
| wis-fallocate1 | native, ops/s | 1.925e+06 | 2.171e+06 | 1.988e+06 | 1.201e+06 | 1.07e+06 | |
| | off/native | 0.99 | 1.10 | 1.12 | 1.22 | 1.24 | |
| | on/native | 0.99 | 1.08 | 1.12 | 1.64 | 1.81 | 92776835, 161, 0 |
| wis-open2 | native, ops/s | 2.09e+06 | 2.295e+06 | 2.143e+06 | 1.37e+06 | 1.282e+06 | |
| | off/native | 1.02 | 0.91 | 1.01 | 1.02 | 1.02 | |
| | on/native | 0.98 | 0.96 | 1.01 | 1.71 | 1.77 | 94900763, 0, 0 |
| sng-fd-abuse | native, bogo/s | 1.354e+07 | 5.387e+07 | 5.288e+07 | 5.308e+07 | 4.839e+07 | |
| | off/native | 1.10 | 1.00 | 1.06 | 1.05 | 1.05 | |
| | on/native | 1.15 | 0.97 | 1.51 | 1.50 | 1.61 | 47158817, 56, 0 |

below the bounds (off 0.93, on 0.90): fio-randwrite-shared off 4 0.82; fio-randwrite-shared on 4 0.78; fio-randwrite-shared off 16 0.86; fio-randwrite-shared on 16 0.81; fio-randwrite-shared off 32 0.90; fio-randwrite-shared on 32 0.79; fio-randwrite-shared off 48 0.89; fio-randwrite-shared on 48 0.85; fio-randwrite-shared off 64 0.87; fio-randwrite-shared on 64 0.86; vms-lru-file-mmap-read off 4 0.92; dbench-ext4 on 16 0.90; wisp-pread2 off 4 0.88; wisp-pread2 on 48 0.41; wisp-pread2 on 64 0.51; ub-execl on 16 0.88; wis-open2 off 16 0.91
