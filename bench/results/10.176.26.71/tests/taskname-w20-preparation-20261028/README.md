# Taskname preparation checkpoint

The three-arm, 16-worker functional attempt remains **FAILED / NO_JIT** because KD recorded no returned body during its measured fixed-iteration phase. Native, TCLock and KD each completed 1,600,000 correct operations, including 320,000 writes; all three sessions drained normally. This was unscored validation, not a benchmark result.

Preparation itself did run. KD used the unchanged eight-worker learning cohort and completed three waves with JIT entry/return counts **1/0, 1/0, 266/266**. The last wave retained a NORMAL publication. Warmup then added six entries and six returns. The ordinary image expanded from 1,302 to 8,259 to 33,830 assembly bytes and contains the decoded `strnlen` and `sized_strscpy` blocks at `0xffffffff826c4f80` and `0xffffffff826c5650`.

The final publication was identical before and after measurement, with zero open writers or frames. Counters stayed at 274 entries / 272 returns, so the measured delta was **0/0**. This is local execution after successful observed preparation, distinct from the original timed KD8 CALL-miss failure. The retained evidence does not identify the precise per-CPU heat or queue decision that selected local service. Preparation does not guarantee delegation on every later coordinate.

[Hash-bound evidence](evidence.json) verifies 282 source files, seven binaries, all three publication versions and the original failed verdict. The independent endpoint retained the same boot, kernel, module inventory and taint; retirement recorded zero frames, modules and writers. No threshold, acceptance predicate or failed result was changed.

The separate `catalog-linux70-taskname-prepared-20261028` cohort measures all 63 points afresh under the existing timed policy, which records successful local NO_JIT separately from RETURNED_JIT. The original `catalog-linux70-trusted-20261028` taskname-w20 partial attempt remains immutable and is not pooled with the new cohort.
