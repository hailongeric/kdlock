# Independent review of final main evidence

This was a read-only analysis of the completed final raw dataset and its
archive, performed from the main worktree. No VM access, builds, tests or
source edits were performed by this reviewer. The report prose was still
being finalized during this review; the findings below establish the raw
data, not a final prose review.

## Identity, completion and acceptance

* Archive size: 345,617 bytes; SHA256
  `81cc6ffe42c9bc1d6dc9f11469769fb75830b50ddc388bcc40565b151857712f`.
  All 50 regular archive members match the corresponding files under raw/
  byte-for-byte.
* Source: `18dad4a1c372d77a1155db671d56c148918344da`.
  Release: `7.0.0-38-kdlocalspin6`, build #2.
* Boot UUID: `fc8104fd-5e0c-406f-b93e-e7c6e6cabf6d`, matching the campaign
  identity, wrapper completion, entry fixture and cleanup receipts.
* All 413 points passed. Every point has positive elapsed time and progress
  by every worker, arrays of the expected worker count, exact worker sums
  matching aggregate operations/writes, zero mismatches and protected-data
  delta equal to writes times lines.
* All 413 rows record queue phase Y, phase wait 0 and NUMA Y. The initial
  and restored parameters match: adaptation Y, enter 5, exit 2, batch 4096,
  NUMA Y, NUMA-after 32, phase wait 0 and queue phase Y. The three forced
  checks temporarily use adaptation off as recorded by the frozen runner;
  they must remain separate from ordinary timed rows.
* Exactly four mixed rwlock rows use 16 counters and write_pct=20. Every
  worker in each row satisfies `0 < worker_writes < worker_ops`, independently
  checked from the recorded arrays. Their reader comparison loop is therefore
  exercised, unlike the older one-line mixed checks.
* The API log reports exactly 65 assertions and zero failures. The six-entry
  fixture has 60,000 operations per case, 30,000 per worker, zero errors,
  positive contention and inside=0, with normal unload.
* Wrapper rc=0; completion receipt present. Daemon rc=0, all five comparison
  modules unloaded normally, and modules-after contains only NLS. The full
  captured final dmesg has no BUG, WARNING, soft lockup, hard LOCKUP or Oops
  marker. This is captured cleanup evidence, not a later independent live
  idle inspection by this reviewer.

Point counts independently recomputed from points.jsonl:

| Group | Count |
| --- | ---: |
| Local checks | 27 |
| Daemon-off and warmup | 36 |
| Learning | 2 |
| Phase changes | 8 |
| Delegation checks | 9 |
| Phase checks | 12 |
| Mixed rwlock, sixteen counters | 4 |
| Three-way and warmup | 180 |
| Post=0 and warmup | 96 |
| Packed NUMA and warmup | 36 |
| Forced checks | 3 |
| **Total** | **413** |

## Recomputed three-way table

Rates below are medians of exactly three measured repetitions, rounds
0/1/2, with post=64. Delegated/handback columns sum only those three KD
measurements; warmups are excluded. 32-worker rows use CPUs 4..35 and smaller
rows start at CPU 0. All rates are Mops/s. Native and TCLock rows have zero
KD event deltas, which does not establish TCLock's own execution counts.

| Workers | Lines | Native | KD | TCLock | KD delegated | KD handback |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 9.450453 | 9.452678 | 9.451328 | 0 | 0 |
| 5 | 1 | 4.410024 | 4.387672 | 3.392692 | 0 | 0 |
| 8 | 1 | 4.475748 | 5.399894 | 5.178376 | 16,792,906 | 0 |
| 16 | 1 | 4.527185 | 5.709196 | 5.789914 | 17,633,577 | 0 |
| 32 | 1 | 3.377453 | 6.012163 | 5.661139 | 18,505,846 | 0 |
| 1 | 16 | 8.959669 | 9.079944 | 8.899980 | 0 | 0 |
| 5 | 16 | 2.385181 | 2.400781 | 2.673207 | 0 | 0 |
| 8 | 16 | 2.385229 | 4.211319 | 3.320505 | 13,164,980 | 0 |
| 16 | 16 | 2.390551 | 4.154222 | 3.354817 | 12,735,115 | 0 |
| 32 | 16 | 1.880262 | 4.353113 | 3.322040 | 13,479,127 | 0 |

The three-way measured KD totals are delegated=92,311,551, handback=0,
sessions=23,944, stop_plain=82 and numa_deferred=127,344. These counts cover
30 measured KD rows; they are not the counts of any single median-rate row.

All three-way, daemon-off and packed cells have three measured repetitions;
all post=0 cells have two. No mismatched repetitions were found. The final
32-worker short KD range is 5.788464..6.104874 Mops/s. The five-worker short
KD range is 4.346921..4.398018 versus Native 4.383766..4.412635, so its small
median gap must not be described as a statistically established universal
slowdown.

## Gains and remaining gaps in this boot

Ratios use medians from matched cells only:

| Cell | KD relative to comparison | KD delegated | KD handback |
| --- | ---: | ---: | ---: |
| Post=64, 8 workers, 1 line, versus Native | +20.64786% | 16,792,906 | 0 |
| Post=64, 8 workers, 1 line, versus TCLock | +4.27774% | 16,792,906 | 0 |
| Post=64, 32 workers, 1 line, versus Native | +78.00880% | 18,505,846 | 0 |
| Post=64, 32 workers, 1 line, versus TCLock | +6.20058% | 18,505,846 | 0 |
| Post=64, 5 workers, 1 line, versus Native | -0.50684% | 0 | 0 |
| Post=64, 5 workers, 16 lines, versus TCLock | -10.19100% | 0 | 0 |
| Post=64, 16 workers, 1 line, versus TCLock | -1.39412% | 17,633,577 | 0 |
| Post=0, 8 workers, 1 line, versus TCLock | -1.98469% | 11,017,952 | 0 |
| Post=0, 5 workers, 16 lines, versus TCLock | -14.51444% | 0 | 0 |
| Daemon-off, 32 workers, 1 line, versus Native | -4.87529% | 0 | 0 |

The preceding kernel5 policy comparison explains the choice of default, but
its rates cannot be pooled with this final kernel6 boot. No kernel6 on/off
policy comparison was run by this final runner. The results do not establish
parity with every backend in every cell.

## Counter totals and mixed-access rows

Across all 413 rows, including warmups and functional checks, the totals are
delegated=255,510,239, handback=537,667, sessions=719,705,
stop_plain=243,716 and numa_deferred=3,980,951. No Native or TCLock point has
a nonzero KD delegated or handback delta in this dataset.

| Family, all phases | Delegated | Handback |
| --- | ---: | ---: |
| spin | 230,975,978 | 0 |
| nest_spin | 6,113,759 | 0 |
| spin_raw | 0 | 0 |
| spin_hb | 5,056,042 | 337,066 |
| spin_cl | 4,836,789 | 0 |
| spin_hb_cl | 3,009,028 | 200,601 |
| spin_mixend | 5,282,607 | 0 |
| rwlock | 236,036 | 0 |

| Mixed rwlock row | Reads | Writes | Delegated | Handback |
| --- | ---: | ---: | ---: | ---: |
| Native, 8 workers | 1,513,059 | 378,273 | 0 | 0 |
| Native, 32 workers | 913,150 | 228,328 | 0 | 0 |
| KD, 8 workers | 1,585,634 | 396,970 | 88,478 | 0 |
| KD, 32 workers | 1,623,796 | 405,608 | 147,558 | 0 |

These are approximate KD event deltas, not ownership proofs, unique-request
counts or measured physical batch lengths. The entry fixture supplies a
separate two-worker overlap detector; nano accounting alone is not universal
exclusion proof. API and fixture coverage do not establish arbitrary
delegated IRQ/BH or nested-context correctness. This is kernel-thread nano
evidence, not unchanged-application syscall-path validation, and no profile
was collected.
