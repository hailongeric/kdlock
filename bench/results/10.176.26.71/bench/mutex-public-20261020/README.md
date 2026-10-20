# Unified public mutex: full worker-grid comparison

All **1,764 sessions completed correctly and drained**. Public DIRECT retains
seven losses against frozen pre-unification OUTER that exceed 5% even when
comparing the public arm's best repetition with OUTER's worst repetition.
The largest median loss is **40.23% for pipe capacity at five workers**.
Performance acceptance remains **open**. The 5% throughput and 10% p95 allowances
were provisional coordinator proposals, not user-approved acceptance thresholds.
Operation latency was not sampled; inverse throughput is not p95 latency.

This result measures collection revision `d21a1e3`, retained by
`archive/mutex-public-measured-20261020`. It must not be attributed to the later
`9a0fdd4` continuation implementation or any subsequent correction. The public
API implementation began at `e25c338`; the frozen OUTER inputs came from the
separate [32-byte comparison](../mutex32-native-tclock-20261020/README.md).
That input collection used `bd9d4ce205512fd34dc00044e3ad238f985d4b6d`, with production
revision `752fec1e5cbb0d54144fa995987424afabf11b46`.

## Preserved regressions and variation

Rates below are full-run median Mops/s, with observed minimum–maximum ranges
over three same-class repetitions. These ranges are descriptive, not confidence
intervals or statistical significance claims.

| Workload | Workers | Class | Public median [range] | OUTER median [range] | Public / OUTER | Median loss |
| --- | ---: | --- | --- | --- | ---: | ---: |
| c08/post64 | 3 | WITNESSED_JIT | 6.388 [6.132–6.950] | 7.862 [7.317–10.069] | 0.812460 | 18.75% |
| c08/post64 | 4 | WITNESSED_JIT | 4.852 [4.216–5.242] | 6.867 [6.850–7.265] | 0.706642 | 29.34% |
| c08/post64 | 5 | WITNESSED_JIT | 4.271 [4.139–4.287] | 5.413 [5.185–5.771] | 0.789000 | 21.10% |
| Pipe bytes n16 | 3 | NO_JIT | 10.100 [9.912–10.214] | 12.016 [11.691–12.191] | 0.840544 | 15.95% |
| Pipe bytes n16 | 5 | RETURNED_JIT | 4.366 [4.323–4.500] | 4.995 [4.935–4.996] | 0.874075 | 12.59% |
| Pipe capacity n16 | 5 | RETURNED_JIT | 4.678 [4.452–5.255] | 7.828 [7.776–11.643] | 0.597685 | 40.23% |
| RCUHT | 2 | WITNESSED_JIT | 5.058 [5.020–5.070] | 5.502 [5.476–5.641] | 0.919323 | 8.07% |

c08/three workers only narrowly clears this descriptive separation: public best
is 5.009963% below OUTER worst. Keep this sensitivity visible in reruns.
Fifteen additional public/OUTER median losses exceed 5% without that separation.
The [complete groups](comparison-table.md), [summary](summary.json) and
[comparisons](comparisons.json) retain these losses and all observed variation.

| Comparator | Median ratio ≥0.95 | Loss separated at 5% across observed ranges | Other median ratio <0.95 | Incomplete class comparisons |
| --- | ---: | ---: | ---: | ---: |
| Frozen OUTER | 122 | 7 | 15 | 4 |
| Fresh Linux Native | 101 | 38 | 7 | 2 |
| Fresh TCLock | 140 | 3 | 3 | 2 |

Every one-, eight- and sixty-worker public/OUTER median ratio meets the
provisional 0.95 screen. That does not establish full-grid parity or make the
unified mutex performance-viable.

Incomplete comparisons are preserved rather than pooled:

- c08/two workers: OUTER has one NO_JIT and two WITNESSED_JIT repetitions;
  public has three WITNESSED_JIT repetitions.
- Pipe bytes/four workers: OUTER has three NO_JIT repetitions, public three
  RETURNED_JIT repetitions. Their execution classes differ.
- Pipe capacity/four workers: public has two NO_JIT and one RETURNED_JIT
  repetition; OUTER has three NO_JIT repetitions. Neither public class provides
  three repeats against any comparator.

There are 590 summary groups, of which 586 have complete class triplets:
32 NO_JIT groups, 294 NOT_APPLICABLE control groups, 118 WITNESSED_JIT groups
and 146 RETURNED_JIT groups. A synthetic witness establishes generated entry,
not returned body completion. RETURNED_JIT establishes positive matched returns,
not that all operations delegated. NORMAL publication alone proves neither.

## Work and measurement identity

Seven workloads × four arms × 21 worker points × three repeats = 1,764 sessions.
Workers are 1–8 and 12–60 in steps of four. Arms are frozen OUTER, public DIRECT,
fresh Linux Native and fresh TCLock. Synthetic workloads update one/eight
cachelines or use the existing preallocated RCUHT payload. API workloads use
SEEK_SET, SEEK_END, pipe-byte queries and pipe capacity, each with n16.
The original comparison guide describes their data and business oracles.
This controlled adapter experiment does not replace the whole kernel's mutexes.

Each full measurement lasts two seconds. Warmup uses at least 48,000 operations;
API warmup additionally lasts at least one second. Peak evidence uses a 300 ms
window after 300 ms settling with 10 ms samples, separately from full-run rates.
Post work is 64, entry ratio is 2, prefetch is 2, NUMA is on, the total batch
limit is 1024 and benchmark provider UBSAN is off. Caller shells remain explicit:
OUTER uses a local acquisition cookie; public DIRECT uses the provider ledger.

The recovery guest has 64 vCPUs and 24 GiB RAM, NUMA nodes 0–31 and 32–63,
workers pinned to CPU prefixes and collector CPU 63. Kernel release is
`6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, boot ID
`b65f0205-c8f9-4385-8b13-039cbce243a6`.
[Host before](host-matrix-before.json) and [host after](host-matrix-after.json)
retain actual CPU placement, policy and the listed recovery snapshot.
No kernel change or reboot was performed.

Collection ran from 2026-10-20 06:42:05.897514 UTC to 10:00:42.170009 UTC.
All original ordering and commands remain in the raw matrix. The runs are not
randomized causal experiments. No PMU diagnosis or per-operation latency was
performed, and these measurements alone do not identify the cause of a loss.

## Preservation and independent review

The VM round is
`/root/kdlock-evidence/10.176.26.71/bench/mutex-public-20261020-r2`.
Five archives are retained there with the `-archives` suffix and locally at
`bench/results/10.176.26.71/raw/bench/mutex-public-20261020-r2/`.
[Archive metadata](archives.json) records exact archive hashes and inventory
identity. [Frozen inputs](frozen-inputs.json) and
[OUTER copy provenance](baseline-copy-provenance.json) bind source and binaries.

| Archive | Bytes | SHA-256 |
| --- | ---: | --- |
| current.tar.gz | 22030236 | `181f67bfe82051df238b5cc8f01e9f69e589bd4b6f59f51c192faf04bb1cd5f7` |
| baseline.tar.gz | 14805626 | `fc5575e3db84cde56b63a0d2fc2278679e696c68769ec938e10467e86dd66f70` |
| matrix.tar.gz | 89628054 | `96b2bf42cb880c0e6149d1eea1544fb2684e330866d2ba70dd30be24991d625d` |
| harness.tar.gz | 710479 | `ecf07873b783ea3ca2340f794a2570b3692ad1d58469694efa54820ff75813bb` |
| metadata.tar.gz | 893584 | `7373c14740bf6aa6a7e624046b4c7cbf4251107be3778cdc68b736f94374ba5b` |

The independent source-host [audit receipt](offline-review.json) records
**1,986,358 checks and zero issues**. It reads archives as inert data, validates
68,976 members and link targets, verifies source/binary/harness identities,
reconstructs all 1,764 selected peak windows, and recomputes 590 groups and
444 comparisons. It does not execute archived code. Its
[script](offline-review.py) uses the separately retained
[archive helper](../mutex32-native-tclock-20261020/offline-review.py).
[Final health](health.json) records independent idle, all 4,424 frozen inputs
unchanged and no matched faults in 1,764 per-session kernel logs.

The [harness validation](../../tests/mutex-api-compare-harness-20261020/README.md)
preserves the first preparation failure, executable-copy correction and
16 successful smoke sessions. No failed attempt was replaced by a pass label.

## Open follow-up

The subsequent [correctness validation](../../tests/native-continuation-20261020/README.md)
completed its selected cases. The separate
[controlled replay](../mutex-public-regressions-20261020/README.md) then completed
120 valid, drained sessions for all seven losses and three class-gap points
using these original inputs on the same VM. It reproduced four separated
losses; two had overlapping ranges and one fell below the provisional screen.
The original matrix, numeric results and source identities above remain
unchanged. No later implementation revision is pooled into either collection.

Only evidence-supported focused changes should follow diagnosis, with affected
correctness and performance checks rerun serially. The source of these losses,
two remaining class gaps and p95 latency remain unresolved. The replay also
retains a post-run host worker-thread discrepancy as an unresolved timing
confounder. Other full-grid losses were outside the focused rerun. No performance
acceptance follows from the sixty-worker results alone.
