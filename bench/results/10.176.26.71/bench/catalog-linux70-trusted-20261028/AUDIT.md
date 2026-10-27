# Completed-subset audit

All **22 complete workloads / 1,386 points** passed the retained source, binary, data, publication, retirement and host-evidence audits. The two offline watchers completed normally. This is exploratory single-round evidence; strict performance qualification remains false.

The separate `taskname-w20` attempt remains **STOPPED**: 23 published successful points, one timed KD/8-worker failure and 39 unattempted points. Its failed body recorded one JIT entry and zero returns. Its original artifacts and rates are unchanged; it has no completed-workload audit and is excluded from the totals below.

For the completed subset, KD has **214 RETURNED_JIT** and **248 successful local NO_JIT** points; entries and returns both total **755,527,522**. The eight xattr profiles deliberately use local readers and account for 168 of those NO_JIT points. Native and TCLock each have 462 successful control points.

Each workload has workers 1–8 and 12–60 by four, three arms, one 2-second round. Every retained completed session drained normally. Final health records the same `7.0.0-38-kdlock1` boot `15dc5977-59d3-4471-a196-d71f03f450ed`, unchanged module inventory/taint 12288 and no listed fault markers. These endpoint observations do not imply continuous log coverage.

[Aggregate evidence](aggregate-audit.json) · [Host summary](host-audit-summary.json) · [Original partial table](taskname-w20/README.md)

| Workload | Points | KD returned | KD local | Evidence |
| --- | ---: | ---: | ---: | --- |
| taskname-w00 | 63 | 18 | 3 | [Data/artifact audit](taskname-w00/audit.json) · [Host audit](taskname-w00/host-audit.json) |
| ofd-tail-n16 | 63 | 13 | 8 | [Data/artifact audit](ofd-tail-n16/audit.json) · [Host audit](ofd-tail-n16/host-audit.json) |
| ofd-tail-n128 | 63 | 13 | 8 | [Data/artifact audit](ofd-tail-n128/audit.json) · [Host audit](ofd-tail-n128/host-audit.json) |
| ofd-miss-n16 | 63 | 13 | 8 | [Data/artifact audit](ofd-miss-n16/audit.json) · [Host audit](ofd-miss-n16/host-audit.json) |
| ofd-miss-n128 | 63 | 13 | 8 | [Data/artifact audit](ofd-miss-n128/audit.json) · [Host audit](ofd-miss-n128/host-audit.json) |
| setfd-toggle-n16 | 63 | 13 | 8 | [Data/artifact audit](setfd-toggle-n16/audit.json) · [Host audit](setfd-toggle-n16/host-audit.json) |
| setfd-toggle-n512 | 63 | 13 | 8 | [Data/artifact audit](setfd-toggle-n512/audit.json) · [Host audit](setfd-toggle-n512/host-audit.json) |
| pipebytes-query-n16 | 63 | 18 | 3 | [Data/artifact audit](pipebytes-query-n16/audit.json) · [Host audit](pipebytes-query-n16/host-audit.json) |
| pipebytes-query-n128 | 63 | 19 | 2 | [Data/artifact audit](pipebytes-query-n128/audit.json) · [Host audit](pipebytes-query-n128/host-audit.json) |
| pipecap-query-n16 | 63 | 18 | 3 | [Data/artifact audit](pipecap-query-n16/audit.json) · [Host audit](pipecap-query-n16/host-audit.json) |
| seek-set-n16 | 63 | 18 | 3 | [Data/artifact audit](seek-set-n16/audit.json) · [Host audit](seek-set-n16/host-audit.json) |
| seek-end-n16 | 63 | 19 | 2 | [Data/artifact audit](seek-end-n16/audit.json) · [Host audit](seek-end-n16/host-audit.json) |
| utsname-host-n20 | 63 | 13 | 8 | [Data/artifact audit](utsname-host-n20/audit.json) · [Host audit](utsname-host-n20/host-audit.json) |
| utsname-domain-n20 | 63 | 13 | 8 | [Data/artifact audit](utsname-domain-n20/audit.json) · [Host audit](utsname-domain-n20/host-audit.json) |
| xattr-front-n16 | 63 | 0 | 21 | [Data/artifact audit](xattr-front-n16/audit.json) · [Host audit](xattr-front-n16/host-audit.json) |
| xattr-front-n128 | 63 | 0 | 21 | [Data/artifact audit](xattr-front-n128/audit.json) · [Host audit](xattr-front-n128/host-audit.json) |
| xattr-tail-n16 | 63 | 0 | 21 | [Data/artifact audit](xattr-tail-n16/audit.json) · [Host audit](xattr-tail-n16/host-audit.json) |
| xattr-tail-n128 | 63 | 0 | 21 | [Data/artifact audit](xattr-tail-n128/audit.json) · [Host audit](xattr-tail-n128/host-audit.json) |
| xattr-miss-n16 | 63 | 0 | 21 | [Data/artifact audit](xattr-miss-n16/audit.json) · [Host audit](xattr-miss-n16/host-audit.json) |
| xattr-miss-n128 | 63 | 0 | 21 | [Data/artifact audit](xattr-miss-n128/audit.json) · [Host audit](xattr-miss-n128/host-audit.json) |
| xattr-size-n16 | 63 | 0 | 21 | [Data/artifact audit](xattr-size-n16/audit.json) · [Host audit](xattr-size-n16/host-audit.json) |
| xattr-size-n128 | 63 | 0 | 21 | [Data/artifact audit](xattr-size-n128/audit.json) · [Host audit](xattr-size-n128/host-audit.json) |

The configured 2.0 GHz policies, sampled APERF/MPERF counters and endpoint CPU placement support the recorded exploratory conditions. They do not prove an exact effective frequency for every instruction. No rates are pooled across the original and any subsequently prepared taskname cohort.
