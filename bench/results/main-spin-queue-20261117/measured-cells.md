# Complete measured cells

This table retains all 114 measured cells from the kernel5 candidate. Mops/s is
median [minimum, maximum]; n is the actual number of repetitions. The post=0
outside-work cells have two repetitions; other cells have three. Count columns
sum those measured repetitions only. They do not include warmups or functional
checks. Full per-round rates/counts remain in [summary.json](evidence/summary.json)
and every point in [rates-and-counts.csv](evidence/rates-and-counts.csv).

O=offered, D=delegated, H=handback, S=sessions, P=stop_plain, N=numa_deferred.
These are approximate KD event deltas. Native rows have zero KD deltas; TCLock
rows say unavailable because KD statistics are not TCLock execution counts.
Neither the rate nor D/S is a qualified peak or a measured physical chain.

## daemon-off

| Policy | Backend | Workers | Lines | Post | First CPU | n | Mops/s median [min, max] | O | D | H | S | P | N |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| default | kd | 5 | 1 | 64 | 0 | 3 | 4.4213 [4.4209, 4.4237] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | native | 5 | 1 | 64 | 0 | 3 | 4.5320 [4.5318, 4.5375] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | kd | 8 | 1 | 64 | 0 | 3 | 4.4913 [4.4855, 4.4922] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | native | 8 | 1 | 64 | 0 | 3 | 4.5108 [4.5100, 4.5109] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | kd | 32 | 1 | 64 | 4 | 3 | 3.1866 [3.1652, 3.2156] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | native | 32 | 1 | 64 | 4 | 3 | 3.3840 [3.3547, 3.4677] | 0 | 0 | 0 | 0 | 0 | 0 |

## three-way

| Policy | Backend | Workers | Lines | Post | First CPU | n | Mops/s median [min, max] | O | D | H | S | P | N |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| default | kd | 1 | 1 | 64 | 0 | 3 | 9.4517 [9.4508, 9.4521] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | native | 1 | 1 | 64 | 0 | 3 | 9.4494 [9.4493, 9.4511] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | tclock | 1 | 1 | 64 | 0 | 3 | 9.4515 [9.4470, 9.4522] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| default | kd | 1 | 16 | 64 | 0 | 3 | 9.0754 [9.0729, 9.0770] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | native | 1 | 16 | 64 | 0 | 3 | 8.9583 [8.9582, 8.9594] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | tclock | 1 | 16 | 64 | 0 | 3 | 8.9003 [8.8974, 8.9023] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| default | kd | 5 | 1 | 64 | 0 | 3 | 4.4022 [4.4020, 4.4090] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | native | 5 | 1 | 64 | 0 | 3 | 4.5321 [4.5298, 4.5384] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | tclock | 5 | 1 | 64 | 0 | 3 | 3.2685 [3.2677, 3.2732] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| default | kd | 5 | 16 | 64 | 0 | 3 | 2.3595 [2.3578, 2.3651] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | native | 5 | 16 | 64 | 0 | 3 | 2.3446 [2.3441, 2.3474] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | tclock | 5 | 16 | 64 | 0 | 3 | 2.5325 [2.5216, 2.5387] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| default | kd | 8 | 1 | 64 | 0 | 3 | 5.3976 [5.3821, 5.4229] | 16,870,796 | 16,859,043 | 0 | 5,005 | 52 | 0 |
| default | native | 8 | 1 | 64 | 0 | 3 | 4.5070 [4.4970, 4.5103] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | tclock | 8 | 1 | 64 | 0 | 3 | 5.1467 [5.1402, 5.1551] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| default | kd | 8 | 16 | 64 | 0 | 3 | 4.1848 [4.1758, 4.1867] | 13,142,588 | 13,138,994 | 0 | 3,264 | 5 | 0 |
| default | native | 8 | 16 | 64 | 0 | 3 | 2.3487 [2.3420, 2.3501] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | tclock | 8 | 16 | 64 | 0 | 3 | 3.2045 [3.1955, 3.2137] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| default | kd | 16 | 1 | 64 | 0 | 3 | 5.7276 [5.6673, 5.7366] | 17,765,578 | 17,761,178 | 0 | 4,341 | 0 | 0 |
| default | native | 16 | 1 | 64 | 0 | 3 | 4.5305 [4.5269, 4.5402] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | tclock | 16 | 1 | 64 | 0 | 3 | 5.8153 [5.8150, 5.8193] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| default | kd | 16 | 16 | 64 | 0 | 3 | 4.1750 [4.1630, 4.1923] | 12,905,481 | 12,902,286 | 0 | 3,155 | 0 | 0 |
| default | native | 16 | 16 | 64 | 0 | 3 | 2.3129 [2.3090, 2.3154] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | tclock | 16 | 16 | 64 | 0 | 3 | 3.2290 [3.2224, 3.2404] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| default | kd | 32 | 1 | 64 | 4 | 3 | 6.1762 [6.1518, 6.2409] | 19,398,146 | 19,393,238 | 0 | 4,819 | 0 | 77,056 |
| default | native | 32 | 1 | 64 | 4 | 3 | 3.3772 [3.3259, 3.4435] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | tclock | 32 | 1 | 64 | 4 | 3 | 5.6282 [5.6267, 5.6325] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| default | kd | 32 | 16 | 64 | 4 | 3 | 4.4388 [4.3980, 4.5403] | 13,722,848 | 13,719,357 | 0 | 3,423 | 0 | 54,720 |
| default | native | 32 | 16 | 64 | 4 | 3 | 1.8260 [1.8078, 1.8743] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | tclock | 32 | 16 | 64 | 4 | 3 | 3.1370 [3.1322, 3.1397] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |

## outside-work

| Policy | Backend | Workers | Lines | Post | First CPU | n | Mops/s median [min, max] | O | D | H | S | P | N |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| default | kd | 1 | 1 | 0 | 0 | 2 | 29.0197 [29.0175, 29.0218] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | native | 1 | 1 | 0 | 0 | 2 | 27.0786 [27.0630, 27.0941] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | tclock | 1 | 1 | 0 | 0 | 2 | 26.2048 [26.1831, 26.2265] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| default | kd | 1 | 16 | 0 | 0 | 2 | 20.7267 [20.7243, 20.7292] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | native | 1 | 16 | 0 | 0 | 2 | 19.8837 [19.8799, 19.8874] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | tclock | 1 | 16 | 0 | 0 | 2 | 19.7177 [19.6498, 19.7856] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| default | kd | 5 | 1 | 0 | 0 | 2 | 4.3322 [4.3299, 4.3345] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | native | 5 | 1 | 0 | 0 | 2 | 4.3055 [4.3018, 4.3092] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | tclock | 5 | 1 | 0 | 0 | 2 | 3.3494 [3.3487, 3.3501] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| default | kd | 5 | 16 | 0 | 0 | 2 | 2.2823 [2.2804, 2.2841] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | native | 5 | 16 | 0 | 0 | 2 | 2.2915 [2.2896, 2.2933] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | tclock | 5 | 16 | 0 | 0 | 2 | 2.5913 [2.5907, 2.5920] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| default | kd | 8 | 1 | 0 | 0 | 2 | 5.2919 [5.2530, 5.3307] | 11,110,789 | 11,106,852 | 0 | 2,836 | 5 | 0 |
| default | native | 8 | 1 | 0 | 0 | 2 | 4.3607 [4.3601, 4.3612] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | tclock | 8 | 1 | 0 | 0 | 2 | 5.4203 [5.4121, 5.4285] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| default | kd | 8 | 16 | 0 | 0 | 2 | 4.7889 [4.7478, 4.8301] | 10,119,202 | 10,116,524 | 0 | 2,502 | 1 | 0 |
| default | native | 8 | 16 | 0 | 0 | 2 | 2.2957 [2.2942, 2.2971] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | tclock | 8 | 16 | 0 | 0 | 2 | 3.2110 [3.2097, 3.2124] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| default | kd | 32 | 1 | 0 | 4 | 2 | 6.2950 [6.2731, 6.3169] | 12,765,741 | 12,762,521 | 0 | 3,156 | 0 | 50,464 |
| default | native | 32 | 1 | 0 | 4 | 2 | 3.3760 [3.3667, 3.3852] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | tclock | 32 | 1 | 0 | 4 | 2 | 5.7171 [5.7164, 5.7179] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| default | kd | 32 | 16 | 0 | 4 | 2 | 4.7064 [4.7054, 4.7075] | 9,945,497 | 9,942,921 | 0 | 2,483 | 0 | 39,696 |
| default | native | 32 | 16 | 0 | 4 | 2 | 1.7556 [1.7455, 1.7657] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | tclock | 32 | 16 | 0 | 4 | 2 | 3.1096 [3.0901, 3.1291] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |

## numa-packed

| Policy | Backend | Workers | Lines | Post | First CPU | n | Mops/s median [min, max] | O | D | H | S | P | N |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| default | kd | 32 | 1 | 64 | 0 | 3 | 6.3501 [6.3088, 6.3660] | 19,747,953 | 19,742,937 | 0 | 4,914 | 0 | 78,572 |
| default | native | 32 | 1 | 64 | 0 | 3 | 3.3425 [3.3298, 3.3685] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | tclock | 32 | 1 | 64 | 0 | 3 | 5.6097 [5.6045, 5.6213] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| default | kd | 32 | 16 | 64 | 0 | 3 | 4.6297 [4.6180, 4.6359] | 14,374,661 | 14,370,926 | 0 | 3,630 | 0 | 58,019 |
| default | native | 32 | 16 | 64 | 0 | 3 | 1.7953 [1.7754, 1.8094] | 0 | 0 | 0 | 0 | 0 | 0 |
| default | tclock | 32 | 16 | 64 | 0 | 3 | 3.1224 [3.1155, 3.1380] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |

## numa-locality

| Policy | Backend | Workers | Lines | Post | First CPU | n | Mops/s median [min, max] | O | D | H | S | P | N |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| kd_numa=0 | kd | 32 | 1 | 64 | 4 | 3 | 3.0469 [3.0413, 3.0474] | 9,534,820 | 9,532,439 | 0 | 2,331 | 0 | 0 |
| kd_numa=0 | native | 32 | 1 | 64 | 4 | 3 | 3.3812 [3.3738, 3.3960] | 0 | 0 | 0 | 0 | 0 | 0 |
| kd_numa=0 | tclock | 32 | 1 | 64 | 4 | 3 | 5.6185 [5.5918, 5.6234] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| kd_numa=0 | kd | 32 | 16 | 64 | 4 | 3 | 2.2891 [2.2840, 2.3059] | 7,060,054 | 7,058,256 | 0 | 1,728 | 0 | 0 |
| kd_numa=0 | native | 32 | 16 | 64 | 4 | 3 | 1.7841 [1.7820, 1.7872] | 0 | 0 | 0 | 0 | 0 | 0 |
| kd_numa=0 | tclock | 32 | 16 | 64 | 4 | 3 | 3.1078 [3.1028, 3.1097] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| kd_numa=1 | kd | 32 | 1 | 64 | 4 | 3 | 6.3363 [6.1276, 6.3788] | 19,453,084 | 19,448,187 | 0 | 4,826 | 0 | 77,168 |
| kd_numa=1 | native | 32 | 1 | 64 | 4 | 3 | 3.4250 [3.3222, 3.5726] | 0 | 0 | 0 | 0 | 0 | 0 |
| kd_numa=1 | tclock | 32 | 1 | 64 | 4 | 3 | 5.6185 [5.6111, 5.6256] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| kd_numa=1 | kd | 32 | 16 | 64 | 4 | 3 | 4.4573 [4.4079, 4.6044] | 13,999,631 | 13,996,065 | 0 | 3,490 | 0 | 55,792 |
| kd_numa=1 | native | 32 | 16 | 64 | 4 | 3 | 1.7997 [1.7637, 1.8052] | 0 | 0 | 0 | 0 | 0 | 0 |
| kd_numa=1 | tclock | 32 | 16 | 64 | 4 | 3 | 3.1017 [3.0910, 3.1174] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |

## policy

| Policy | Backend | Workers | Lines | Post | First CPU | n | Mops/s median [min, max] | O | D | H | S | P | N |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| kd_spin_queue_phase=0 | kd | 5 | 1 | 64 | 0 | 3 | 4.4018 [4.3966, 4.4073] | 0 | 0 | 0 | 0 | 0 | 0 |
| kd_spin_queue_phase=0 | native | 5 | 1 | 64 | 0 | 3 | 4.5329 [4.5315, 4.5341] | 0 | 0 | 0 | 0 | 0 | 0 |
| kd_spin_queue_phase=0 | tclock | 5 | 1 | 64 | 0 | 3 | 3.2591 [3.2579, 3.2610] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| kd_spin_queue_phase=0 | kd | 5 | 16 | 64 | 0 | 3 | 2.3591 [2.2746, 2.3601] | 0 | 0 | 0 | 0 | 0 | 0 |
| kd_spin_queue_phase=0 | native | 5 | 16 | 64 | 0 | 3 | 2.3405 [2.2565, 2.3421] | 0 | 0 | 0 | 0 | 0 | 0 |
| kd_spin_queue_phase=0 | tclock | 5 | 16 | 64 | 0 | 3 | 2.5346 [2.4009, 2.5432] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| kd_spin_queue_phase=0 | kd | 8 | 1 | 64 | 0 | 3 | 4.4529 [4.4415, 4.4532] | 2,288 | 14 | 0 | 14 | 2,274 | 0 |
| kd_spin_queue_phase=0 | native | 8 | 1 | 64 | 0 | 3 | 4.5054 [4.4967, 4.5074] | 0 | 0 | 0 | 0 | 0 | 0 |
| kd_spin_queue_phase=0 | tclock | 8 | 1 | 64 | 0 | 3 | 5.1375 [5.1274, 5.1415] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| kd_spin_queue_phase=0 | kd | 8 | 16 | 64 | 0 | 3 | 2.3789 [2.3226, 2.3797] | 383,451 | 24,168 | 0 | 22,413 | 359,275 | 0 |
| kd_spin_queue_phase=0 | native | 8 | 16 | 64 | 0 | 3 | 2.3432 [2.2883, 2.3440] | 0 | 0 | 0 | 0 | 0 | 0 |
| kd_spin_queue_phase=0 | tclock | 8 | 16 | 64 | 0 | 3 | 3.1933 [3.1310, 3.2112] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| kd_spin_queue_phase=0 | kd | 32 | 1 | 64 | 4 | 3 | 3.1626 [3.1598, 3.3602] | 1,850 | 57 | 0 | 54 | 1,792 | 21 |
| kd_spin_queue_phase=0 | native | 32 | 1 | 64 | 4 | 3 | 3.3778 [3.3739, 3.3815] | 0 | 0 | 0 | 0 | 0 | 0 |
| kd_spin_queue_phase=0 | tclock | 32 | 1 | 64 | 4 | 3 | 5.6030 [5.5077, 5.6319] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| kd_spin_queue_phase=0 | kd | 32 | 16 | 64 | 4 | 3 | 1.8171 [1.8109, 1.8274] | 476,225 | 10,279 | 0 | 9,759 | 465,942 | 18,809 |
| kd_spin_queue_phase=0 | native | 32 | 16 | 64 | 4 | 3 | 1.8129 [1.8004, 1.8198] | 0 | 0 | 0 | 0 | 0 | 0 |
| kd_spin_queue_phase=0 | tclock | 32 | 16 | 64 | 4 | 3 | 3.1238 [3.1067, 3.1303] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| kd_spin_queue_phase=1 | kd | 5 | 1 | 64 | 0 | 3 | 4.3993 [4.3986, 4.3994] | 0 | 0 | 0 | 0 | 0 | 0 |
| kd_spin_queue_phase=1 | native | 5 | 1 | 64 | 0 | 3 | 4.5314 [4.5291, 4.5342] | 0 | 0 | 0 | 0 | 0 | 0 |
| kd_spin_queue_phase=1 | tclock | 5 | 1 | 64 | 0 | 3 | 3.2624 [3.2380, 3.2702] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| kd_spin_queue_phase=1 | kd | 5 | 16 | 64 | 0 | 3 | 2.3592 [2.2678, 2.3605] | 0 | 0 | 0 | 0 | 0 | 0 |
| kd_spin_queue_phase=1 | native | 5 | 16 | 64 | 0 | 3 | 2.3409 [2.2617, 2.3440] | 0 | 0 | 0 | 0 | 0 | 0 |
| kd_spin_queue_phase=1 | tclock | 5 | 16 | 64 | 0 | 3 | 2.5359 [2.3946, 2.5412] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| kd_spin_queue_phase=1 | kd | 8 | 1 | 64 | 0 | 3 | 5.4063 [5.4006, 5.4084] | 16,817,446 | 16,805,256 | 0 | 5,076 | 47 | 0 |
| kd_spin_queue_phase=1 | native | 8 | 1 | 64 | 0 | 3 | 4.5057 [4.4904, 4.5080] | 0 | 0 | 0 | 0 | 0 | 0 |
| kd_spin_queue_phase=1 | tclock | 8 | 1 | 64 | 0 | 3 | 5.1328 [5.1247, 5.1353] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| kd_spin_queue_phase=1 | kd | 8 | 16 | 64 | 0 | 3 | 4.1872 [4.1208, 4.1982] | 13,012,393 | 13,008,553 | 0 | 3,268 | 5 | 0 |
| kd_spin_queue_phase=1 | native | 8 | 16 | 64 | 0 | 3 | 2.3403 [2.2924, 2.3458] | 0 | 0 | 0 | 0 | 0 | 0 |
| kd_spin_queue_phase=1 | tclock | 8 | 16 | 64 | 0 | 3 | 3.1802 [3.1368, 3.1917] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| kd_spin_queue_phase=1 | kd | 32 | 1 | 64 | 4 | 3 | 6.2110 [5.8703, 6.3717] | 19,101,336 | 19,096,518 | 0 | 4,730 | 0 | 75,648 |
| kd_spin_queue_phase=1 | native | 32 | 1 | 64 | 4 | 3 | 3.3550 [3.2383, 3.4053] | 0 | 0 | 0 | 0 | 0 | 0 |
| kd_spin_queue_phase=1 | tclock | 32 | 1 | 64 | 4 | 3 | 5.6047 [5.5970, 5.6275] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| kd_spin_queue_phase=1 | kd | 32 | 16 | 64 | 4 | 3 | 4.4644 [4.4403, 4.6921] | 13,818,510 | 13,814,993 | 0 | 3,430 | 0 | 54,832 |
| kd_spin_queue_phase=1 | native | 32 | 16 | 64 | 4 | 3 | 1.8015 [1.7883, 1.8217] | 0 | 0 | 0 | 0 | 0 | 0 |
| kd_spin_queue_phase=1 | tclock | 32 | 16 | 64 | 4 | 3 | 3.1155 [3.0306, 3.1199] | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
