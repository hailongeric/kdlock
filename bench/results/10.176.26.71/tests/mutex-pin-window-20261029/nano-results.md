# Bounded waiter selection: same-boot nano comparison

Baseline `1c86d6d1a15d96d75c09504f1041772247707804`; candidate `6d95745d8e3c405a650e32efe04d54ffd2187cc7`.
Both ran on boot `677b7afa-5358-4ece-a650-5f4a4adecd55`.

All 36 requested points completed once: mutex c01/c16 and rwsem c01/c16 with 1%/20% writes, at 1/8/20/32/36/60 workers. Runner arguments match exactly except output paths: two seconds, post256, CPUs0..N-1, collector63, KD limits1024/1024. Workload/module/runner source bytes are unchanged.

**The candidate fails the performance gate and must not be promoted.** All ten contended mutex points lost 19.75–39.25% throughput. Uncontended mutex points stayed approximately flat. Correctness success does not override these losses.

| Family | Workload | Writes | Workers | Baseline Mops/s | Candidate Mops/s | Change |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| mutex | c01 | 100% | 1 | 1.916302 | 1.916837 | +0.03% |
| mutex | c01 | 100% | 8 | 3.678105 | 2.484585 | -32.45% |
| mutex | c01 | 100% | 20 | 4.590029 | 2.788218 | -39.25% |
| mutex | c01 | 100% | 32 | 4.486160 | 2.735999 | -39.01% |
| mutex | c01 | 100% | 36 | 4.209552 | 3.206593 | -23.83% |
| mutex | c01 | 100% | 60 | 4.335256 | 3.281210 | -24.31% |
| mutex | c16 | 100% | 1 | 1.916744 | 1.916477 | -0.01% |
| mutex | c16 | 100% | 8 | 3.548560 | 2.459460 | -30.69% |
| mutex | c16 | 100% | 20 | 4.227567 | 2.712740 | -35.83% |
| mutex | c16 | 100% | 32 | 4.188997 | 2.774264 | -33.77% |
| mutex | c16 | 100% | 36 | 3.853043 | 3.078917 | -20.09% |
| mutex | c16 | 100% | 60 | 3.946234 | 3.166728 | -19.75% |
| rwsem | c01 | 1% | 1 | 1.787590 | 1.787120 | -0.03% |
| rwsem | c01 | 1% | 8 | 11.595956 | 11.341421 | -2.20% |
| rwsem | c01 | 1% | 20 | 8.389572 | 7.842182 | -6.52% |
| rwsem | c01 | 1% | 32 | 8.397137 | 8.214292 | -2.18% |
| rwsem | c01 | 1% | 36 | 7.037000 | 7.077736 | +0.58% |
| rwsem | c01 | 1% | 60 | 7.346221 | 7.327383 | -0.26% |
| rwsem | c01 | 20% | 1 | 1.808877 | 1.808317 | -0.03% |
| rwsem | c01 | 20% | 8 | 5.976143 | 5.372054 | -10.11% |
| rwsem | c01 | 20% | 20 | 5.237910 | 5.270884 | +0.63% |
| rwsem | c01 | 20% | 32 | 5.111017 | 4.849260 | -5.12% |
| rwsem | c01 | 20% | 36 | 3.948307 | 3.817822 | -3.30% |
| rwsem | c01 | 20% | 60 | 3.639400 | 3.471117 | -4.62% |
| rwsem | c16 | 1% | 1 | 1.783111 | 1.782741 | -0.02% |
| rwsem | c16 | 1% | 8 | 10.405390 | 10.301022 | -1.00% |
| rwsem | c16 | 1% | 20 | 10.029305 | 10.874089 | +8.42% |
| rwsem | c16 | 1% | 32 | 10.946708 | 11.025996 | +0.72% |
| rwsem | c16 | 1% | 36 | 9.325963 | 9.351639 | +0.28% |
| rwsem | c16 | 1% | 60 | 10.058038 | 9.705957 | -3.50% |
| rwsem | c16 | 20% | 1 | 1.805172 | 1.805146 | -0.00% |
| rwsem | c16 | 20% | 8 | 3.910685 | 3.909272 | -0.04% |
| rwsem | c16 | 20% | 20 | 4.863255 | 4.412443 | -9.27% |
| rwsem | c16 | 20% | 32 | 4.694605 | 4.450523 | -5.20% |
| rwsem | c16 | 20% | 36 | 3.680834 | 3.485468 | -5.31% |
| rwsem | c16 | 20% | 60 | 3.582569 | 3.323260 | -7.24% |

Rwsem changes range -10.11% to +8.42%; individual signs vary. No pooled performance claim is made.

The earlier strict one-request candidate `658b918a05cb930d52ccf7307b8d44d54c6d6265` lost 42–54% in its own historical cohort. Those results remain separate; they are not the baseline here.

One observation per point supplies no repeat variance. Default summary `complete:false`/`expected_rounds:3` remains unchanged; every requested point has one valid round. Timing remains exploratory. No real-world API test ran.
