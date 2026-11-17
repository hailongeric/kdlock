# Final KD event totals by phase and family

These sums include the indicated warmup, functional or timing phase. They
are not pooled throughput measurements and cannot explain a particular median.
All event counts are approximate. Per-point counts remain in the raw JSONL.

| Phase | Family | KD points | Offered | Delegated | Handback | Sessions | Plain stops | NUMA deferred |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| daemon-off | spin | 9 | 0 | 0 | 0 | 0 | 0 | 0 |
| daemon-off-warmup | spin | 9 | 0 | 0 | 0 | 0 | 0 | 0 |
| delegation-check | nest_spin | 3 | 1,763,754 | 1,763,319 | 0 | 434 | 0 | 5,392 |
| delegation-check | spin_hb | 3 | 1,776,693 | 1,665,033 | 111,000 | 111,595 | 1 | 800,741 |
| delegation-check | spin_raw | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| forced-check | spin | 3 | 3,455,152 | 3,454,282 | 0 | 858 | 0 | 7,040 |
| learning | spin | 2 | 11,051,807 | 11,046,679 | 0 | 3,058 | 50 | 26,526 |
| local-check | nest_spin | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| local-check | spin | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| local-check | spin_hb | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| local-check | spin_raw | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| numa-packed | spin | 6 | 33,789,502 | 33,780,882 | 0 | 8,437 | 0 | 134,891 |
| numa-packed-warmup | spin | 6 | 8,322,011 | 8,319,911 | 0 | 2,077 | 0 | 33,132 |
| outside-work | spin | 16 | 42,809,933 | 42,796,523 | 0 | 10,819 | 9 | 86,192 |
| outside-work-warmup | spin | 16 | 10,611,501 | 10,608,293 | 0 | 2,671 | 3 | 21,615 |
| phase-change | spin | 8 | 5,792,583 | 5,789,573 | 0 | 1,646 | 35 | 12,304 |
| phase-check | nest_spin | 2 | 4,351,534 | 4,350,440 | 0 | 1,073 | 0 | 8,784 |
| phase-check | spin_cl | 2 | 4,838,213 | 4,836,789 | 0 | 1,216 | 7 | 12,624 |
| phase-check | spin_hb | 2 | 3,618,334 | 3,391,009 | 226,066 | 227,208 | 0 | 1,335,910 |
| phase-check | spin_hb_cl | 2 | 3,210,794 | 3,009,028 | 200,601 | 201,649 | 1 | 1,324,104 |
| phase-check | spin_mixend | 2 | 5,289,876 | 5,282,607 | 0 | 2,064 | 33 | 11,359 |
| phase-check | spin_raw | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| rwlock-mixed-sixteen-check | rwlock | 2 | 479,723 | 236,036 | 0 | 114,977 | 243,464 | 785 |
| three-way | spin | 30 | 92,344,569 | 92,311,551 | 0 | 23,944 | 82 | 127,344 |
| three-way-warmup | spin | 30 | 22,876,778 | 22,868,284 | 0 | 5,979 | 31 | 32,208 |
