# Count accounting and functional coverage

Main and supplemental points are separate. All-phase totals below include
warmups, learning and functional points, and must not be attached to a single
median throughput. Counters are approximate event deltas, not ownership or
physical-batch-length evidence. TCLock execution counts are unavailable.

## Main campaign by phase

| Phase | Points | Offered | Delegated | Handback | Sessions | Plain stops | NUMA deferred |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| local-check | 27 | 0 | 0 | 0 | 0 | 0 | 0 |
| daemon-off-warmup | 18 | 0 | 0 | 0 | 0 | 0 | 0 |
| daemon-off | 18 | 0 | 0 | 0 | 0 | 0 | 0 |
| learning | 2 | 10,753,304 | 10,748,500 | 0 | 2,971 | 89 | 25,232 |
| phase-change | 8 | 5,939,861 | 5,937,105 | 0 | 1,613 | 10 | 12,799 |
| delegation-check | 9 | 3,546,944 | 3,434,454 | 111,370 | 112,408 | 1 | 809,251 |
| phase-check | 24 | 23,081,033 | 22,596,834 | 450,803 | 458,103 | 20,853 | 2,682,837 |
| rwlock-check | 24 | 28,660,648 | 28,223,151 | 429,608 | 437,219 | 0 | 2,721,567 |
| rwlock-mixed-check | 8 | 1,362,822 | 642,580 | 0 | 331,512 | 719,903 | 1,635 |
| three-way-warmup | 90 | 23,118,560 | 23,110,462 | 0 | 5,978 | 18 | 32,960 |
| three-way | 90 | 93,805,437 | 93,774,096 | 0 | 24,007 | 57 | 131,776 |
| outside-work-warmup | 48 | 10,484,656 | 10,481,645 | 0 | 2,623 | 3 | 21,152 |
| outside-work | 48 | 43,941,229 | 43,928,818 | 0 | 10,977 | 6 | 90,160 |
| numa-packed-warmup | 18 | 8,304,274 | 8,302,160 | 0 | 2,081 | 0 | 33,204 |
| numa-packed | 18 | 34,122,614 | 34,113,863 | 0 | 8,544 | 0 | 136,591 |
| numa-locality-warmup | 36 | 12,434,634 | 12,431,439 | 0 | 3,086 | 3 | 33,312 |
| numa-locality | 36 | 50,047,589 | 50,034,947 | 0 | 12,375 | 0 | 132,960 |
| policy-warmup | 108 | 15,760,125 | 15,550,544 | 0 | 12,000 | 203,338 | 37,445 |
| policy | 108 | 63,613,499 | 62,759,838 | 0 | 48,744 | 829,335 | 149,310 |
| forced-check | 3 | 3,631,320 | 3,630,392 | 0 | 911 | 0 | 7,888 |

## Main campaign by family

| Family | Points | Offered | Delegated | Handback | Sessions | Plain stops | NUMA deferred |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nest_spin | 11 | 6,209,607 | 6,194,120 | 0 | 1,822 | 13,904 | 14,479 |
| rwlock | 16 | 12,226,893 | 11,503,911 | 0 | 334,220 | 719,903 | 27,091 |
| rwlock_cl | 8 | 10,920,429 | 10,917,657 | 0 | 2,721 | 0 | 25,599 |
| rwlock_hb | 8 | 6,876,148 | 6,444,163 | 429,608 | 431,790 | 0 | 2,670,512 |
| spin | 664 | 375,957,102 | 374,803,809 | 0 | 135,910 | 1,032,859 | 844,789 |
| spin_cl | 4 | 5,822,303 | 5,818,309 | 0 | 1,706 | 539 | 12,310 |
| spin_hb | 11 | 5,377,843 | 5,037,449 | 335,826 | 337,569 | 2,658 | 2,124,649 |
| spin_hb_cl | 4 | 3,624,945 | 3,395,249 | 226,347 | 227,503 | 2,057 | 1,328,259 |
| spin_mixend | 4 | 5,593,279 | 5,586,161 | 0 | 1,911 | 1,696 | 12,391 |
| spin_raw | 11 | 0 | 0 | 0 | 0 | 0 | 0 |

All 991,781 main handbacks are `hb_frontier`: `spin_hb` 335,826,
`spin_hb_cl` 226,347 and `rwlock_hb` 429,608. Ordinary `spin`, `spin_mixend`,
`nest_spin`, `spin_cl`, `rwlock` and `rwlock_cl` have zero handbacks.
`spin_raw` has zero offered and delegated events; its execution does not
establish raw-spin delegation. No positive `hb_miss` or `hb_other` was observed.

## Supplemental rwlock consistency checks

This separately drained run has two all-write learning points and eight
mixed Native/KD checks with 16 values and 20% requested writes, at 8/32 workers
under queue phase 0/1. All workers completed positive reads and writes in each
mixed row. Every row has zero reader mismatches and exact worker/protected-data
totals. It is functional evidence, not a repeated performance comparison.

| Phase | Queue phase | Backend | Workers | Operations | Writes | Reads | Minimum worker writes | Minimum worker reads | Delegated | Handback | Sessions | Plain stops | NUMA deferred |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| learning | Y | kd | 8 | 1,722,356 | 1,722,356 | 0 | 206,656 | 0 | 1,236,458 | 0 | 310 | 0 | 0 |
| learning | Y | kd | 32 | 2,352,866 | 2,352,866 | 0 | 72,032 | 0 | 2,351,610 | 0 | 585 | 0 | 9,344 |
| rwlock-mixed-sixteen-check | N | native | 8 | 1,920,640 | 384,294 | 1,536,346 | 47,627 | 191,028 | 0 | 0 | 0 | 0 | 0 |
| rwlock-mixed-sixteen-check | N | kd | 8 | 2,120,457 | 424,541 | 1,695,916 | 52,112 | 207,715 | 154,997 | 0 | 75,526 | 159,125 | 0 |
| rwlock-mixed-sixteen-check | N | native | 32 | 1,162,132 | 232,555 | 929,577 | 6,257 | 25,310 | 0 | 0 | 0 | 0 | 0 |
| rwlock-mixed-sixteen-check | N | kd | 32 | 2,099,037 | 419,417 | 1,679,620 | 12,878 | 51,720 | 153,082 | 0 | 74,357 | 158,368 | 865 |
| rwlock-mixed-sixteen-check | Y | native | 8 | 1,906,279 | 381,425 | 1,524,854 | 47,439 | 190,025 | 0 | 0 | 0 | 0 | 0 |
| rwlock-mixed-sixteen-check | Y | kd | 8 | 2,139,513 | 428,418 | 1,711,095 | 52,709 | 210,006 | 157,190 | 0 | 76,560 | 159,838 | 0 |
| rwlock-mixed-sixteen-check | Y | native | 32 | 1,160,067 | 232,102 | 927,965 | 6,159 | 24,833 | 0 | 0 | 0 | 0 | 0 |
| rwlock-mixed-sixteen-check | Y | kd | 32 | 2,093,336 | 418,305 | 1,675,031 | 12,832 | 51,486 | 152,683 | 0 | 74,410 | 158,707 | 803 |

Supplement learning totals: offered 3,588,974; delegated 3,588,068;
handback 0; sessions 895; plain stops 0; NUMA deferred 9,344.
Supplement mixed totals: offered 1,254,752; delegated 617,952; handback 0;
sessions 300,853; plain stops 636,038; NUMA deferred 1,668.
The main lines=1 mixed rows are retained, but their empty reader comparison
loop cannot establish multi-value reader consistency.

The main API ioctl executed three times, each running the same 65 assertions;
the supplement executed it twice, each running those same 65 assertions.
All returned zero failures. These are repeated assertions, not 325 distinct
APIs, and they are single-task local-object checks rather than contended or
delegated IRQ/BH coverage.
