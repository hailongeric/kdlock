# Fresh nano comparison: measured results

All 210 matched pairs passed offline validation and strict host qualification. Whole-interval losses: 120; peak losses: 120; either metric: 123. No points were unscored. The no-regression evidence gate failed; the candidate remains unaccepted.

Each profile has 21 worker counts and one round per point. Changes below compare 22d with f7; every negative counts, regardless of magnitude.

| Workload | Whole losses | Peak losses | Either | Worst whole change | Worst peak change |
| --- | ---: | ---: | ---: | --- | --- |
| mutex c01 w100 | 13/21 | 13/21 | 13/21 | -9.4774% at 5 | -9.1656% at 5 |
| mutex c16 w100 | 13/21 | 13/21 | 13/21 | -6.2220% at 16 | -6.1298% at 16 |
| rwsem c01 w1 | 9/21 | 9/21 | 9/21 | -8.2175% at 24 | -8.3806% at 24 |
| rwsem c01 w20 | 12/21 | 12/21 | 12/21 | -7.2489% at 12 | -7.1912% at 12 |
| rwsem c16 w1 | 15/21 | 14/21 | 15/21 | -4.2759% at 32 | -4.1159% at 32 |
| rwsem c16 w20 | 10/21 | 10/21 | 10/21 | -4.4914% at 4 | -4.5814% at 4 |
| rwlock c01 w1 | 11/21 | 12/21 | 12/21 | -15.9816% at 7 | -15.9976% at 7 |
| rwlock c01 w20 | 12/21 | 13/21 | 13/21 | -8.9956% at 16 | -8.8488% at 16 |
| rwlock c16 w1 | 14/21 | 14/21 | 15/21 | -9.0493% at 12 | -9.3674% at 12 |
| rwlock c16 w20 | 11/21 | 10/21 | 11/21 | -3.3317% at 16 | -3.1270% at 16 |

Selected worker counts; each cell is whole / peak change:

| Workload | 20 workers | 32 workers | 60 workers |
| --- | ---: | ---: | ---: |
| mutex c01 w100 | +1.6643% / +1.5358% | -0.3819% / -0.3364% | -2.2188% / -2.2830% |
| mutex c16 w100 | +0.0772% / +0.0125% | +2.2716% / +2.3068% | +2.7031% / +2.5155% |
| rwsem c01 w1 | -5.2534% / -5.3111% | +0.3005% / +0.5322% | +1.7067% / +1.6730% |
| rwsem c01 w20 | -0.2615% / -0.2048% | -0.5676% / -0.3815% | -0.8060% / -0.3637% |
| rwsem c16 w1 | +3.6020% / +3.6577% | -4.2759% / -4.1159% | -4.0295% / -4.1051% |
| rwsem c16 w20 | +2.8422% / +2.8251% | -1.0612% / -0.9716% | +2.1655% / +1.5957% |
| rwlock c01 w1 | -0.6390% / -0.6987% | -1.5737% / -1.8210% | -0.4057% / -0.5913% |
| rwlock c01 w20 | +2.8373% / +3.0238% | -1.5380% / -1.8683% | -0.8491% / -0.7462% |
| rwlock c16 w1 | +5.4744% / +5.2650% | -1.2841% / -1.3251% | -1.5438% / -1.5860% |
| rwlock c16 w20 | -0.8992% / -0.8591% | -1.5441% / -1.2318% | +3.4630% / +3.4824% |

Exact baseline/candidate whole and peak rates for these 30 points are in `key-points.csv`. The original 210-row CSV is unchanged in the validated comparison directory.

Execution classes:

- `NO_JIT -> NO_JIT`: 77 pairs; whole losses 39, peak losses 40, either 42.
- `RETURNED_JIT -> RETURNED_JIT`: 127 pairs; whole losses 78, peak losses 77, either 78.
- `RETURNED_JIT -> NO_JIT`: 2 pairs; whole losses 2, peak losses 2, either 2.
- `NO_JIT -> RETURNED_JIT`: 4 pairs; whole losses 1, peak losses 1, either 1.

The new helper is confined to killable writer admission. Ordinary/prepared nano writer paths do not directly call it, so this matrix is a regression check rather than a direct measurement of the proposed admission benefit. The signs are observed results; neither a parking fraction nor a causal explanation follows from these one-round sequential measurements. Full ELF hashes and JIT image comparisons are identity evidence only.
