# Final measured cells

All rows belong to main `18dad4a1`, kernel `7.0.0-38-kdlocalspin6`, boot
`fc8104fd-5e0c-406f-b93e-e7c6e6cabf6d`. Rates are Mops/s medians; ranges are the
minimum and maximum of the measured repetitions. n excludes warmups. With
n=2 the median is the arithmetic midpoint. All rows passed accounting checks.

D, H, offered, sessions, plain and NUMA are summed KD event deltas over those
same measured repetitions. They are approximate events, not ownership or
physical batch-length measurements. Native rows record zero KD activity.
TCLock execution counters are unavailable; its zero sampled KD deltas are
preserved in raw JSON/CSV but shown as unavailable here.

Each per-round rate and counter set is retained in
[summary.json](raw/evidence-main-final/summary.json), and every point, including
warmups and functional checks, is in [points.jsonl](raw/evidence-main-final/points.jsonl)
and [rates-and-counts.csv](raw/evidence-main-final/rates-and-counts.csv).

## three-way

| Backend | Workers | Lines | Post | First CPU | n | Median | Min..max | D | H | Offered | Sessions | Plain | NUMA |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| native | 1 | 1 | 64 | 0 | 3 | 9.4505 | 9.4499..9.4509 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 1 | 1 | 64 | 0 | 3 | 9.4527 | 9.4484..9.4530 | 0 | 0 | 0 | 0 | 0 | 0 |
| tclock | 1 | 1 | 64 | 0 | 3 | 9.4513 | 9.4510..9.4525 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| native | 1 | 16 | 64 | 0 | 3 | 8.9597 | 8.9577..8.9604 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 1 | 16 | 64 | 0 | 3 | 9.0799 | 9.0776..9.0808 | 0 | 0 | 0 | 0 | 0 | 0 |
| tclock | 1 | 16 | 64 | 0 | 3 | 8.9000 | 8.8313..8.9042 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| native | 5 | 1 | 64 | 0 | 3 | 4.4100 | 4.3838..4.4126 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 5 | 1 | 64 | 0 | 3 | 4.3877 | 4.3469..4.3980 | 0 | 0 | 0 | 0 | 0 | 0 |
| tclock | 5 | 1 | 64 | 0 | 3 | 3.3927 | 3.3913..3.3957 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| native | 5 | 16 | 64 | 0 | 3 | 2.3852 | 2.3839..2.3920 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 5 | 16 | 64 | 0 | 3 | 2.4008 | 2.4006..2.4034 | 0 | 0 | 0 | 0 | 0 | 0 |
| tclock | 5 | 16 | 64 | 0 | 3 | 2.6732 | 2.6669..2.6778 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| native | 8 | 1 | 64 | 0 | 3 | 4.4757 | 4.4574..4.4762 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 8 | 1 | 64 | 0 | 3 | 5.3999 | 5.3920..5.4025 | 16,792,906 | 0 | 16,806,560 | 5,268 | 69 | 0 |
| tclock | 8 | 1 | 64 | 0 | 3 | 5.1784 | 5.1519..5.1951 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| native | 8 | 16 | 64 | 0 | 3 | 2.3852 | 2.3850..2.3906 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 8 | 16 | 64 | 0 | 3 | 4.2113 | 4.2000..4.2373 | 13,164,980 | 0 | 13,168,716 | 3,283 | 3 | 0 |
| tclock | 8 | 16 | 64 | 0 | 3 | 3.3205 | 3.2926..3.3217 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| native | 16 | 1 | 64 | 0 | 3 | 4.5272 | 4.4944..4.5436 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 16 | 1 | 64 | 0 | 3 | 5.7092 | 5.6550..5.7311 | 17,633,577 | 0 | 17,637,944 | 4,313 | 3 | 0 |
| tclock | 16 | 1 | 64 | 0 | 3 | 5.7899 | 5.7879..5.7981 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| native | 16 | 16 | 64 | 0 | 3 | 2.3906 | 2.3831..2.3930 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 16 | 16 | 64 | 0 | 3 | 4.1542 | 4.1391..4.1694 | 12,735,115 | 0 | 12,738,276 | 3,114 | 2 | 0 |
| tclock | 16 | 16 | 64 | 0 | 3 | 3.3548 | 3.3206..3.3670 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| native | 32 | 1 | 64 | 4 | 3 | 3.3775 | 3.3125..3.4057 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 32 | 1 | 64 | 4 | 3 | 6.0122 | 5.7885..6.1049 | 18,505,846 | 0 | 18,510,502 | 4,596 | 0 | 73,488 |
| tclock | 32 | 1 | 64 | 4 | 3 | 5.6611 | 5.6559..5.6652 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| native | 32 | 16 | 64 | 4 | 3 | 1.8803 | 1.8387..1.9023 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 32 | 16 | 64 | 4 | 3 | 4.3531 | 4.3061..4.4808 | 13,479,127 | 0 | 13,482,571 | 3,370 | 5 | 53,856 |
| tclock | 32 | 16 | 64 | 4 | 3 | 3.3220 | 3.3082..3.3285 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |

## daemon-off

| Backend | Workers | Lines | Post | First CPU | n | Median | Min..max | D | H | Offered | Sessions | Plain | NUMA |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| native | 5 | 1 | 64 | 0 | 3 | 4.4095 | 4.4081..4.4137 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 5 | 1 | 64 | 0 | 3 | 4.4017 | 4.4012..4.4037 | 0 | 0 | 0 | 0 | 0 | 0 |
| native | 8 | 1 | 64 | 0 | 3 | 4.4719 | 4.4631..4.4783 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 8 | 1 | 64 | 0 | 3 | 4.4485 | 4.4427..4.4532 | 0 | 0 | 0 | 0 | 0 | 0 |
| native | 32 | 1 | 64 | 4 | 3 | 3.4007 | 3.2642..3.4420 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 32 | 1 | 64 | 4 | 3 | 3.2349 | 3.1759..3.2396 | 0 | 0 | 0 | 0 | 0 | 0 |

## outside-work

| Backend | Workers | Lines | Post | First CPU | n | Median | Min..max | D | H | Offered | Sessions | Plain | NUMA |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| native | 1 | 1 | 0 | 0 | 2 | 27.0791 | 27.0694..27.0889 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 1 | 1 | 0 | 0 | 2 | 29.0389 | 29.0202..29.0575 | 0 | 0 | 0 | 0 | 0 | 0 |
| tclock | 1 | 1 | 0 | 0 | 2 | 26.1851 | 26.1628..26.2075 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| native | 1 | 16 | 0 | 0 | 2 | 19.8848 | 19.8829..19.8868 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 1 | 16 | 0 | 0 | 2 | 20.7225 | 20.7216..20.7233 | 0 | 0 | 0 | 0 | 0 | 0 |
| tclock | 1 | 16 | 0 | 0 | 2 | 19.7358 | 19.6992..19.7724 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| native | 5 | 1 | 0 | 0 | 2 | 4.3024 | 4.2994..4.3055 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 5 | 1 | 0 | 0 | 2 | 4.3470 | 4.3426..4.3513 | 0 | 0 | 0 | 0 | 0 | 0 |
| tclock | 5 | 1 | 0 | 0 | 2 | 3.4927 | 3.4890..3.4964 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| native | 5 | 16 | 0 | 0 | 2 | 2.3155 | 2.3139..2.3171 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 5 | 16 | 0 | 0 | 2 | 2.3196 | 2.3192..2.3200 | 0 | 0 | 0 | 0 | 0 | 0 |
| tclock | 5 | 16 | 0 | 0 | 2 | 2.7135 | 2.7102..2.7168 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| native | 8 | 1 | 0 | 0 | 2 | 4.4133 | 4.4103..4.4163 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 8 | 1 | 0 | 0 | 2 | 5.3344 | 5.3192..5.3496 | 11,017,952 | 0 | 11,023,201 | 2,947 | 8 | 0 |
| tclock | 8 | 1 | 0 | 0 | 2 | 5.4425 | 5.4334..5.4515 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| native | 8 | 16 | 0 | 0 | 2 | 2.3430 | 2.3421..2.3439 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 8 | 16 | 0 | 0 | 2 | 4.7578 | 4.7333..4.7824 | 10,080,378 | 0 | 10,083,001 | 2,481 | 1 | 0 |
| tclock | 8 | 16 | 0 | 0 | 2 | 3.3139 | 3.3050..3.3228 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| native | 32 | 1 | 0 | 4 | 2 | 3.3704 | 3.2962..3.4446 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 32 | 1 | 0 | 4 | 2 | 6.1149 | 6.0761..6.1536 | 12,360,774 | 0 | 12,363,914 | 3,072 | 0 | 49,120 |
| tclock | 32 | 1 | 0 | 4 | 2 | 5.7712 | 5.7668..5.7757 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| native | 32 | 16 | 0 | 4 | 2 | 1.7870 | 1.7520..1.8220 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 32 | 16 | 0 | 4 | 2 | 4.6445 | 4.5785..4.7105 | 9,337,419 | 0 | 9,339,817 | 2,319 | 0 | 37,072 |
| tclock | 32 | 16 | 0 | 4 | 2 | 3.3344 | 3.3127..3.3560 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |

## numa-packed

| Backend | Workers | Lines | Post | First CPU | n | Median | Min..max | D | H | Offered | Sessions | Plain | NUMA |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| native | 32 | 1 | 64 | 0 | 3 | 3.2662 | 3.1823..3.3050 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 32 | 1 | 64 | 0 | 3 | 6.1412 | 6.1181..6.3590 | 19,308,067 | 0 | 19,312,957 | 4,799 | 0 | 76,727 |
| tclock | 32 | 1 | 64 | 0 | 3 | 5.6119 | 5.6052..5.6199 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| native | 32 | 16 | 64 | 0 | 3 | 1.8608 | 1.8527..1.8779 | 0 | 0 | 0 | 0 | 0 | 0 |
| kd | 32 | 16 | 64 | 0 | 3 | 4.6760 | 4.5347..4.7286 | 14,472,815 | 0 | 14,476,545 | 3,638 | 0 | 58,164 |
| tclock | 32 | 16 | 64 | 0 | 3 | 3.2721 | 3.2688..3.2926 | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
