# Seven original regressions: separate controlled rerun

Full-run Mops/s: median [minimum–maximum] across three same-class repeats. Ratios are public DIRECT / frozen OUTER. No source revisions or collections are pooled.

| Point | Class | Original ratio | Replay public | Replay OUTER | Replay ratio | Replay median loss | Finding |
| --- | --- | ---: | --- | --- | ---: | ---: | --- |
| c08/t3 | WITNESSED_JIT | 0.812460 | 5.364 [5.297–6.850] | 7.865 [6.350–9.606] | 0.681982 | 31.80% | Median loss; overlapping ranges |
| c08/t4 | WITNESSED_JIT | 0.706642 | 4.775 [4.691–4.823] | 8.946 [7.013–9.437] | 0.533785 | 46.62% | Separated loss reproduced |
| c08/t5 | WITNESSED_JIT | 0.789000 | 4.012 [3.826–4.347] | 5.251 [5.177–5.764] | 0.764036 | 23.60% | Separated loss reproduced |
| pipebytes/t3 | NO_JIT | 0.840544 | 11.144 [11.113–11.545] | 11.522 [11.424–12.075] | 0.967176 | 3.28% | Below provisional 5% screen |
| pipebytes/t5 | RETURNED_JIT | 0.874075 | 4.922 [4.404–5.078] | 5.353 [4.637–5.717] | 0.919470 | 8.05% | Median loss; overlapping ranges |
| pipecap/t5 | RETURNED_JIT | 0.597685 | 5.393 [5.231–5.436] | 7.208 [6.880–9.023] | 0.748197 | 25.18% | Separated loss reproduced |
| rcuht/t2 | WITNESSED_JIT | 0.919323 | 5.044 [3.997–5.212] | 5.682 [5.616–5.692] | 0.887614 | 11.24% | Separated loss reproduced |

All seven remain **unresolved for acceptance**: a causal correction has not been measured, three repetitions do not establish statistical significance, and p95 latency is unmeasured. The below-screen result is not proof that the original loss is fixed.

The largest replay public/OUTER spreads among these seven are 28.95%/41.39% (c08/t3). The same-round paired-ratio ranges and every original/replay/control repetition are retained in `investigation.json` and `per-repeat.csv`.

| Original class gap | Replay classes | Result |
| --- | --- | --- |
| c08/t2 | Public 3 NO_JIT; OUTER 1 NO_JIT + 2 WITNESSED_JIT | Still incomparable; do not pool classes. |
| pipebytes/t4 | Public 3 RETURNED_JIT; OUTER 3 NO_JIT | Still incomparable. |
| pipecap/t4 | Both 3 NO_JIT | Now comparable in this rerun; ratio 0.939063, 6.09% median loss, overlapping ranges. Original mixed-class result remains unchanged. |
