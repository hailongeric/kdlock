# Baseline interpretation

KD already forms long batches in these nano workloads. The observed differences point toward the cost of servicing each returned body and the NUMA service policy, rather than generally short batches. This interpretation uses source and separate diagnostic observations; it does not establish a causal performance decomposition.

| Workers | Body | Completed bodies/batch | Total-cap exits | NUMA-boundary exits | Small FIFO batches | Remote returned JIT bodies |
|---:|:---|---:|---:|---:|---:|---:|
| 16 | Minimal pair | 1012.277 | 98.356% | 0% | 0% | 0% |
| 16 | 16 cache lines | 1016.915 | 98.926% | 0% | 0% | 0% |
| 32 | Minimal pair | 1020.642 | 99.655% | 0% | 0% | 0% |
| 32 | 16 cache lines | 1020.609 | 99.630% | 0% | 0% | 0% |
| 36 | Minimal pair | 929.390 | 90.723% | 0% | 90.878% | 8.454% |
| 36 | 16 cache lines | 968.848 | 94.591% | 0% | 94.641% | 8.553% |
| 60 | Minimal pair | 255.667 | 0.008% | 99.687% | 0.063% | 0.018% |
| 60 | 16 cache lines | 255.663 | 0.006% | 99.705% | 0.052% | 0.016% |

The [minimal](baseline-batch-bounded/mutex-minimal/README.md) and [locality](baseline-batch-bounded/mutex-locality/README.md) reports contain exact histograms and stop counts. All eight points have zero scan-budget exhaustion. “Remote” compares requester and executor nodes immediately before entry, counting only bodies that subsequently returned successfully. It does not identify whole-body CPU residency. Mean batch size includes all combiner entries, including any zero-body entries.

At 16 and 32 workers, all requesters are on one NUMA node. Almost every batch reaches the 1,024-body cap. This argues against insufficient batch length as the main explanation for KD's small-body disadvantage. Increasing the cap would reduce batch-end frequency, but these counters do not show that batch-end overhead dominates.

At 60 workers, the 32+28 requester split supports substantial deferred prefixes. The existing policy hands off at the 256-body locality boundary in almost every batch, while roughly 99.98% of returned JIT bodies start on an executor local to their requester. The measured mean of about 255.66 agrees with that boundary.

At 36 workers, the 32+4 split often invokes the small-prefix FIFO remainder: its share is 90.88–94.64%, and remote returned bodies account for 8.45–8.55%. The source permits mixed-node service after rejoining a small prefix; these observations are consistent with that policy contributing to the 36-worker behavior. The aggregate counters do not pair each remote body with its batch exit or isolate its throughput cost. NUMA-tail exits also occur in 9.09%/5.28% of the minimal/locality batches; four requesters on one node does not mean every executor sees only four remote requests.

The [flat profiles](baseline-record/mutex-minimal/README.md) contain substantial pinned waiting. Their coarse “waiter/OSQ” group also includes accounting and queue work, so it is not a pure polling fraction. Instruction-level attribution highlights owner checks/retirement and frame initialization as service-path candidates. A safe experiment should preserve exact owner, source, frame and unlock obligations while reducing redundant construction or improving already-valid prefetching. The minimal completion predicate has very little sampled weight and provides weaker evidence for a substantial gain.

[Profiling sensitivity](INSTRUMENTATION_EFFECTS.md) limits causal claims: at minimal/60, stat throughput is 0.216× the fresh Native control but 0.953× the KD control. At locality/36, Native completed-work Jain fairness changes from 0.4868 unprofiled to 0.9984 under stat. Counters describe that altered execution. Unprofiled candidate comparisons remain necessary.

The perf/control phases use `c438bb25`; bounded batch diagnostics use `b0d12ba8` with optional observation code enabled. These versions and instrumentation settings remain separate. The diagnostic-off `8b31c980` provider has the same instruction layout as the baseline, with five executable bytes changed solely by four logging line-number immediates; full executable-section hashes and full binary identities are therefore unequal. Raw byte and disassembly evidence is retained in `raw/bench/mutex-profile-20261026/analysis/diagnostic-off-code-identity.json`.
