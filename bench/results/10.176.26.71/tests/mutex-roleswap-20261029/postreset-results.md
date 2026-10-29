# Corrected role exchange: post-reset results

The isolated source is `1c86d6d1a15d96d75c09504f1041772247707804`, on Linux
`7.0.0-38-kdlock1`, boot `677b7afa-5358-4ece-a650-5f4a4adecd55`. The
[main record](README.md) preserves the earlier failure, correction and approved
recovery. The candidate has not been promoted to `master`.

Two basic unit programs and nine directly affected drivers passed. The live
basic check passed all four families at 1,600,000 operations each, with final
idle and returned JIT bodies: spin 1,597,733; mutex 1,589,086; rwlock 29,732;
rwsem 1,589,610. All five role cases passed and drained, including the formerly
failing `w-early-mutex`. Each retained zero thefts and exact source retirement.

The nano round completed 60 requested single observations: 12 mutex, 24 rwlock
and 24 rwsem. Each used two seconds, post256, collector CPU 63, workers
`0..N-1`, and KD mutex limits 1024/1024. Workloads were c01/c16 (one/sixteen
cachelines), rwlock/rwsem writes 1%/20%, and workers 1/8/20/32/36/60.
No real-world API benchmark ran.

The table gives selected whole-run rates in Mops/s. Historical baseline
`67361fee6440765e130385b2961246a41052b953` and API candidate
`5f96dd5c42a27583aef679554f31e41bcafef793` ran on boot
`15dc5977-59d3-4471-a196-d71f03f450ed`. These are descriptive cross-boot
comparisons, not a causal or no-regression verdict.

| Family | Workload | Writes | Workers | Baseline | API candidate | Corrected role exchange | vs baseline |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| mutex | c01 | 100% | 20 | 4.583610 | 4.532491 | 4.590029 | +0.14% |
| mutex | c01 | 100% | 60 | 4.339713 | 4.345805 | 4.335256 | -0.10% |
| mutex | c16 | 100% | 8 | 3.634284 | 3.636725 | 3.548560 | -2.36% |
| mutex | c16 | 100% | 36 | 3.915062 | 3.972206 | 3.853043 | -1.58% |
| rwlock | c01 | 1% | 8 | 9.316989 | 7.977198 | 8.735599 | -6.24% |
| rwlock | c01 | 1% | 20 | 8.997735 | 8.366597 | 8.606521 | -4.35% |
| rwlock | c16 | 1% | 8 | 10.834296 | 11.282957 | 8.681424 | -19.87% |
| rwsem | c01 | 1% | 20 | 8.734873 | 8.933170 | 8.389572 | -3.95% |
| rwsem | c01 | 1% | 36 | 7.448045 | 6.878000 | 7.037000 | -5.52% |
| rwsem | c16 | 1% | 20 | 10.817592 | 9.916495 | 10.029305 | -7.29% |

Rwlock c16/1% at eight workers is the largest observed loss and reports
`NO_JIT`; no measured cause is established. An [offline ELF comparison](rwlock-elf-comparison.json)
verified that c01/c16 `rb_read`, `rb_write` and `rb_run` have identical bytes,
relative offsets, sizes and relocations at `5f96dd5c` and `1c86d6d1`. The c16/t8
code entry was unchanged, while runtime lock data moved with the same page
offset/alignment. Physical data placement was not measured. Thus a payload
instruction/layout change does not explain this new loss; runtime/provider
effects remain unresolved. The earlier rwlock c01 losses also remain open. Rwsem's original baseline used a different call shell from the
ordinary prepared DIRECT API, so those deltas also include that interface
change. No source generations, boots, call shells or observations are pooled.

The [compact JSON](postreset-comparison.json) includes all 60 rates, source/boot
identities, input hashes, exact basic/role-case results and the separate
`d9b2c57f6c2cf71019c1faea8711dc88425e33c7` comparison. Each requested point
has `valid_rounds: 1`; the runner's default `complete: false` and
`expected_rounds: 3` fields are preserved. One round gives no repeat variance.
Summary eligibility and NORMAL publication do not establish returned JIT
execution or strict timing qualification. Performance acceptance remains open.

The four completed evidence trees were archived after verified idle.
[Offline verification](postfix-archive-verification.json) confirms all eight
compressed hashes and the complete 10,025-path inventories. Raw copies are in
`bench/results/10.176.26.71/raw/tests/mutex-roleswap-20261029/postfix-archives/`.
