# Mutex profiling and controlled factors

The fresh unprofiled baseline compares Native and KD on the existing minimal pair/post4 and 16-cacheline/post64 bodies. Separate counter and sampling phases diagnose their execution. Every point has one observation; strict host timing qualification remains failed.

[Optimization findings and retained decisions](OPTIMIZATION.md) connects the profiles, workload factors and candidate comparisons. The maintained defaults remain cap1024 / NUMA boundary256.

| Phase | Frozen source | Measurements | Results |
|:---|:---|---:|:---|
| Unprofiled control | `c438bb25` | 12 | [Minimal pair](baseline-unprofiled/mutex-minimal/README.md), [16 cache lines](baseline-unprofiled/mutex-locality/README.md) |
| Perf stat | `c438bb25` | 12 diagnostic | [Minimal pair](baseline-stat/mutex-minimal/README.md), [16 cache lines](baseline-stat/mutex-locality/README.md) |
| Flat perf record | `c438bb25` | 12 diagnostic | [Minimal pair](baseline-record/mutex-minimal/README.md), [16 cache lines](baseline-record/mutex-locality/README.md) |
| Initial batch diagnostics | `8b31c980` | 0 | [Provider allocation failure](baseline-batch/README.md) |
| Initial post4 factor grid | `8b31c980` | 0 | [Workload build guard failure](factor-grid/factor-post4/README.md) |
| Bounded batch diagnostics | `b0d12ba8` | 8 diagnostic | [Minimal pair](baseline-batch-bounded/mutex-minimal/README.md), [16 cache lines](baseline-batch-bounded/mutex-locality/README.md) |
| Post4 factor grid | `b0d12ba8` | 18 | [1 cache line](factor-grid/factor2-post4/cacheline-c01/README.md), [4](factor-grid/factor2-post4/cacheline-c04/README.md), [16](factor-grid/factor2-post4/cacheline-c16/README.md) |
| Post64 factor grid | `b0d12ba8` | 18 | [1 cache line](factor-grid/factor2-post64/cacheline-c01/README.md), [4](factor-grid/factor2-post64/cacheline-c04/README.md), [16](factor-grid/factor2-post64/cacheline-c16/README.md) |
| Post256 factor grid | `b0d12ba8` | 18 | [1 cache line](factor-grid/factor2-post256/cacheline-c01/README.md), [4](factor-grid/factor2-post256/cacheline-c04/README.md), [16](factor-grid/factor2-post256/cacheline-c16/README.md) |
| Fresh control before frame change | `b0d12ba8` | 12 | [Minimal pair](control-b0/mutex-minimal/README.md), [16 cache lines](control-b0/mutex-locality/README.md) |
| Frame tag initialization trial | `96fc5e89` | 12 | [Minimal pair](frame-tags/mutex-minimal/README.md), [16 cache lines](frame-tags/mutex-locality/README.md) |
| Two-successor prefetch trial | `9ec2be09` | 12 | [Minimal pair](prefetch-two/mutex-minimal/README.md), [16 cache lines](prefetch-two/mutex-locality/README.md) |
| Policy control: cap1024 / boundary256 | `f61ddc1a` | 16 | [Minimal pair](policy-control/mutex-minimal/README.md), [16 cache lines](policy-control/mutex-locality/README.md) |
| Policy trial: cap4096 / boundary256 | `f61ddc1a` | 16 | [Minimal pair](policy-cap4096/mutex-minimal/README.md), [16 cache lines](policy-cap4096/mutex-locality/README.md) |
| Policy trial: cap1024 / boundary768 | `f61ddc1a` | 16 | [Minimal pair](policy-numa768/mutex-minimal/README.md), [16 cache lines](policy-numa768/mutex-locality/README.md) |
| Policy batch diagnostics: 1024 / 256 | `f61ddc1a` | 6 diagnostic | [Minimal pair](policy-batch-control/mutex-minimal/README.md), [16 cache lines](policy-batch-control/mutex-locality/README.md) |
| Policy batch diagnostics: 4096 / 256 | `f61ddc1a` | 6 diagnostic | [Minimal pair](policy-batch-cap4096/mutex-minimal/README.md), [16 cache lines](policy-batch-cap4096/mutex-locality/README.md) |
| Policy batch diagnostics: 1024 / 768 | `f61ddc1a` | 6 diagnostic | [Minimal pair](policy-batch-numa768/mutex-minimal/README.md), [16 cache lines](policy-batch-numa768/mutex-locality/README.md) |

The 200 completed measurements (150 ordinary and 50 diagnostic) and their 200 warmups passed frozen-version offline oracle replay, exact payload/completion checks and source/frame drain checks. Four separate [frame functional sessions](frame-functional/README.md), with eight checked phases, passed without publishing rates. Each report links its archive and source/binary hash audit. Diagnostic reports retain `score_eligible=false`.

The [frame trial](frame-tags-vs-control-b0/README.md) and [prefetch trial](prefetch-two-vs-frame-tags/README.md) did not show a consistent throughput improvement across the measured coordinates. Both experiments remain archived; commit `d9d2b6fa` restored the baseline implementation before the policy trials. Their results remain separate, including the unfavorable observations.

The policy comparison holds source `f61ddc1a` fixed and builds each explicitly recorded cap/boundary setting separately: [larger total cap](policy-cap4096-vs-policy-control/README.md) and [later NUMA boundary](policy-numa768-vs-policy-control/README.md). Tables show raw Native and KD changes, completed-work fairness and returned-body share. Native variation is reported directly, not used to normalize a KD gain. These are one-round observations, with no repeat variability estimate. The focused policy validation receipts record seven repository unit drivers, ten nano unittest cases and two legacy provider unittest cases passed.

The [18-point policy batch comparison](policy-batch-comparison/README.md) confirms that cap4096 lengthens batches at 16/36 workers but leaves the 256-body boundary dominant at 60. Boundary768 increases 60-worker batches to about 762–764 bodies; at 36 it reduces remote returned-body share to about 3% while increasing NUMA-tail exits. The matching ordinary results favor boundary768 at 36/60 but regress at 16. These observations retain the default 1024/256 policy and support 768 only as an explicit experiment. Frozen ELF tags are checked against the recorded settings in all twelve ordinary/diagnostic profile builds.

The complete [54-point factor matrix](factor-grid/README.md) provides [matched KD/Native heatmaps](factor-grid/kd-over-native.png) and [absolute throughput heatmaps](factor-grid/absolute-throughput.png). Wider acquisition spacing often improves KD's relative result while its absolute rate remains similar or falls; the charts preserve both views.

[Baseline interpretation](BASELINE_INTERPRETATION.md) connects exact batch observations with the source policy. [Instrumentation sensitivity](INSTRUMENTATION_EFFECTS.md) compares the three separate modes against fresh controls. Their frozen source manifests and module executable sections match within each body. Profiling changes throughput and completed-work fairness substantially, so counter and sample attribution must be interpreted within that instrumented execution. The comparisons are individual observations, with no pooled averages or isolated overhead estimate.

Flat sample charts use conservative function groups. “KD waiter/OSQ paths (mixed)” includes polling, waiter accounting and queue bookkeeping. Raw IPs, module section bases, frozen ELF files and source attribution remain available in the analysis receipts. Generated image ranges, unknown samples and lost-event records are explicit.

The initial batch diagnostic module exceeded available reserved per-CPU allocation space and failed before initialization. No warmup or timing ran in that phase. A histogram-bounds fix and any subsequent factor or optimization measurements retain distinct source/stage identities.

The bounded retry observes roughly 1,012–1,021 completed bodies per combiner entry at 16/32 workers. At 36 workers, 90.88–94.64% of batches use the small-prefix FIFO remainder and 8.45–8.55% of returned JIT bodies began across requester/executor nodes. At 60 workers, batches average about 255.66 bodies and that remote share is about 0.02%. These observations describe the implemented NUMA boundaries; they do not isolate their throughput cost.

The campaign is complete. Raw archives, reproducible analysis scripts and detailed receipts are under `bench/results/10.176.26.71/raw/bench/mutex-profile-20261026/`. Failures and rejected candidates remain retained beside all successful observations.
