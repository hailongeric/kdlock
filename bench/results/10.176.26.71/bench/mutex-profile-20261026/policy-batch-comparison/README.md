# Policy effects on observed batches

The three diagnostic stages use identical frozen source bytes and different explicitly compiled policies. Each point is one observation, with no perf process; all are `score_eligible=false`. These data describe the instrumented chain behavior, separately from the ordinary throughput comparisons.

| Body | Workers | Cap / boundary | Completed bodies/batch | Remote returned JIT | Small FIFO batches | Total-cap exits | NUMA-boundary exits | NUMA-tail exits |
|:---|---:|:---|---:|---:|---:|---:|---:|---:|
| mutex-minimal | 16 | 1024 / 256 | 1015.722 | 0.000% | 0.00% | 98.90% | 0.00% | 0.00% |
| mutex-minimal | 16 | 4096 / 256 | 3994.892 | 0.000% | 0.00% | 96.84% | 0.00% | 0.00% |
| mutex-minimal | 16 | 1024 / 768 | 1018.008 | 0.000% | 0.00% | 99.21% | 0.00% | 0.00% |
| mutex-minimal | 36 | 1024 / 256 | 928.382 | 8.473% | 90.65% | 90.62% | 0.00% | 9.23% |
| mutex-minimal | 36 | 4096 / 256 | 3662.734 | 10.340% | 89.47% | 89.38% | 0.00% | 10.09% |
| mutex-minimal | 36 | 1024 / 768 | 842.177 | 2.969% | 82.21% | 82.17% | 0.00% | 17.73% |
| mutex-minimal | 60 | 1024 / 256 | 255.799 | 0.022% | 0.05% | 0.02% | 99.68% | 0.27% |
| mutex-minimal | 60 | 4096 / 256 | 255.752 | 0.035% | 0.04% | 0.00% | 99.69% | 0.26% |
| mutex-minimal | 60 | 1024 / 768 | 762.490 | 0.009% | 0.17% | 0.01% | 98.75% | 0.96% |
| mutex-locality | 16 | 1024 / 256 | 1013.232 | 0.000% | 0.00% | 98.53% | 0.00% | 0.00% |
| mutex-locality | 16 | 4096 / 256 | 3948.955 | 0.000% | 0.00% | 94.67% | 0.00% | 0.00% |
| mutex-locality | 16 | 1024 / 768 | 1014.193 | 0.000% | 0.00% | 98.72% | 0.00% | 0.00% |
| mutex-locality | 36 | 1024 / 256 | 978.353 | 8.551% | 95.56% | 95.52% | 0.00% | 4.24% |
| mutex-locality | 36 | 4096 / 256 | 3643.472 | 10.464% | 89.62% | 88.88% | 0.00% | 9.94% |
| mutex-locality | 36 | 1024 / 768 | 892.314 | 3.055% | 87.20% | 87.07% | 0.00% | 12.49% |
| mutex-locality | 60 | 1024 / 256 | 255.592 | 0.023% | 0.09% | 0.01% | 99.68% | 0.19% |
| mutex-locality | 60 | 4096 / 256 | 255.793 | 0.031% | 0.03% | 0.00% | 99.71% | 0.21% |
| mutex-locality | 60 | 1024 / 768 | 764.344 | 0.015% | 0.22% | 0.03% | 99.12% | 0.64% |

[Full-precision table](table.csv) · [Policy, source and input audit](audit.json)

At 16 workers, raising the total cap changes mean batch size from about 1,013–1,016 to 3,949–3,995. At 36 workers it changes roughly 928–978 to 3,643–3,663 and increases the remote returned-body share from 8.47–8.55% to 10.34–10.46%. At 60 workers the separate 256-body NUMA boundary still dominates, so the higher cap leaves mean batch size near 256. This is consistent with the small ordinary throughput changes at 60; larger batches at other counts do not by themselves establish a gain.

Moving the NUMA boundary to 768 raises the 60-worker mean from about 256 to 762–764, with 98.75–99.12% of batches ending at that boundary and remote returned-body share still below 0.02%. At 36 workers the mean instead falls from 928–978 to 842–892: the remote returned-body share falls from about 8.5% to 3.0%, and NUMA-tail exits increase. The policy therefore changes locality and termination mix as well as batch length. Its separate ordinary runs show KD increases of 8.41–15.95% at 36 workers and 9.40–14.10% at 60, but both 16-worker bodies regress. The diagnostic one-node 16-worker means remain near the 1024 total cap. These observations support further targeted study of the boundary; they do not isolate its cost or justify changing the default after one round.

Mean batch size includes zero-completion combiner entries and completed native continuations. Remote means the requester node differs from the executor node immediately before a successful JIT body; it does not describe memory placement or migration during a sleepable body. Small-FIFO use is an overlapping batch attribute, not an additional mutually exclusive exit reason. Only selected exit reasons appear above; the per-stage tables retain every exit and histogram bin. No stage observed exhausted scans.

Each stage passed the exact archived oracle and policy-aware validator, complete source/frame drain, and returned-body identity checks. Additional offline checks constrain attempts by batches times cap and completed work by the cap-clipped histogram upper sum, including pre/post snapshots. These are aggregate consistency checks, not a substitute for exact ownership records. The separate ordinary comparisons are [cap4096](../policy-cap4096-vs-policy-control/README.md) and [NUMA768](../policy-numa768-vs-policy-control/README.md); diagnostic rates are not pooled with them.
