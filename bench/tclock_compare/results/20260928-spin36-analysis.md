# 2026-09-28: 36-thread spin performance and attribution

Fresh measurements at `f98ec2d` reproduce the hash gap: KD peaks at **1.985 Mops/s**,
TCLock at **2.648 Mops/s**, so KD reaches **74.96%** of TCLock. The three-round
medians are 1.981 and 2.644 Mops/s. This is a workload-dependent gap: the same
36-thread one-cacheline control reaches **8.665 / 5.952 Mops/s**, favoring KD by 45.59%.

The best-supported explanation is the additional execution and request-handling
work in KD's translated hash path, combined with the cost of cross-node placement.
The experiments identify contributors; they do not assign an exact fraction of the
gap to individual instructions or remote-memory latency.

## Conditions and acceptance

All builds and executions used the existing recovery guest, `6.1.159-kdclobber2`,
Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. No production lock or kernel
changes were made. Host min/max frequencies remained 2500000 kHz; all 40 vCPUs
remained pinned to matching host CPUs. At 36 threads, workers use CPUs 0–35:
20 on node0 and 16 on node1. Collector CPU38 is outside the worker cohort.

NUMA-on, 1024-body limit, independent 1024 scan budget, prefetch=2 and ratio2 remain
the defaults. Every worker warms up for 48000 operations. Each performance session
runs for two seconds, selects the highest valid 300 ms window after 300 ms settling,
and retains whole-run throughput. Every configuration has three rounds; backend
order rotates. Rates below are Mops/s; spread is `(max-min)/median`.

**45 performance sessions and 30 separate diagnostic sessions passed** business,
context, progress, kernel-log and drain checks. Every contended KD session had
returned-body JIT evidence. The 305 frozen source hashes match across all ten phases;
the UBSAN control changes the private provider's build flag, not its source.
No unit suite was rerun because production code was unchanged. The guest is idle
with all benchmark modules unloaded; final host affinity/frequency checks match.

## Fresh 36-thread measurements

| Workload | Backend | Peak min / median / max | Spread | Whole min / median / max |
| --- | --- | --- | --- | --- |
| Hash | Linux | 1.636 / 1.924 / 2.623 | 51.29% | 1.588 / 1.652 / 1.905 |
| Hash | TCLock | 2.642 / 2.644 / 2.648 | 0.21% | 2.624 / 2.634 / 2.638 |
| Hash | KD | 1.977 / 1.981 / 1.985 | 0.37% | 1.971 / 1.973 / 1.977 |
| One cacheline | Linux | 9.442 / 13.023 / 13.211 | 28.94% | 4.616 / 6.074 / 11.756 |
| One cacheline | TCLock | 5.909 / 5.926 / 5.952 | 0.71% | 5.901 / 5.914 / 5.944 |
| One cacheline | KD | 8.551 / 8.655 / 8.665 | 1.32% | 8.532 / 8.632 / 8.650 |

At the selected hash peaks, amortized time per completed operation is 503.82 ns for
KD and 377.66 ns for TCLock, a 126.16 ns difference. These are inverse aggregate
throughputs, not individual acquisition latency or per-thread waiting time.
Linux's high and low samples remain in the table and raw evidence; they are not
discarded or interpreted as stable sustained performance.

KD's hash JIT share is 99.897%–99.899%. Session-end counters report zero
`jit_not_ready`, `native_fallback`, `jit_disabled` and outstanding waiters. Average
delegated bodies per combiner are 540–644 **including warmup**; these are not
measurement-window-only batch lengths. Delegation is active and batches are substantial.

All workers progress in the whole run and selected peak window. KD's node1 share
is 49.95%–50.01%, TCLock's 49.98%–49.99%; minimum completed operations per worker
are 97536 and 129024 respectively. There is no inactive node in this 36-thread result.
This observation does not establish a general starvation bound.

The same [hash payload](../../../workload_modules/spin_cacheline/hash_payload.h)
has 1024 64-byte buckets and 4096 64-byte nodes: about 320 KiB of payload storage.
Each source bucket is traversed, and some operations also traverse a destination
bucket and relink a node. Both backends record approximately 25% moves, 25% occupied
destinations and 50% misses; the throughput gap is not accompanied by a materially
different mix of these outcomes. No allocation or RCU service occurs in this critical section.

## Generated execution and request handling

Six new, separate profiles sample `cycles -F 499` during only the measured three-second
client and inherited workers. Translation and warmup are outside sampling. All have
zero lost samples and flat IP/TID/TIME/PERIOD records, without callchains. Attribution
uses each session's kallsyms, exact frozen ELF symbol extents and actual JIT ranges.
The existing kernel symbol-size index was reused only after matching the live Build ID;
the measurements themselves are new. Unknown IPs remain unresolved.

| Sampled region | Cycle-period weight per operation, min / median / max |
| --- | --- |
| KD generated image, including wrapper | 893 / 927 / 988 |
| KD `run_combiner` | 295 / 301 / 309 |
| TCLock native `sc_body_0` | 703 / 766 / 781 |
| TCLock `komb_spin_unlock` | 118 / 129 / 137 |
| TCLock `komb_context_switch` | 38 / 41 / 43 |

The generated-image median is about 21% above the native-body median. These are
sampled event-period weights, not isolated function timings or identical code
boundaries: KD's image includes its wrapper, while TCLock's body includes its caller
shell. The differences cannot be added into an exact wall-time decomposition.
Sampling also perturbs throughput: profiled KD peaks are 1.947–1.961 and TCLock
2.587–2.599, excluded from performance scoring.

The source and frozen disassembly show concrete extra work:

- The [KD direct caller](../../../include/kd_spin_direct.h) clobbers the working GPRs.
  Its compiler-generated hash caller spills source/destination keys, bucket indices
  and the statistics pointer onto the waiter's stack. TCLock's caller keeps these
  values in callee-saved registers, restored by its native stack-switch path.
- The KD source-chain loop expands from 12 source instructions to 15 generated
  instructions: a memory budget decrement, a limit branch, and a reload of virtual
  R11 from the register packet. The destination-chain iteration expands from 5 to 9
  instructions because it crosses two budgeted blocks. These costs repeat inside
  traversal, unlike the straight-line one-cacheline payload.
- Each request still passes [frame/image admission](../../../kernel_module/execution/wrapper_entry.inc),
  binding, COMPLETE validation and retirement in the
  [combiner](../../../kernel_module/spin/combiner.inc). Its hottest sampled regions
  include frame-state admission and dependent successor qualification. Those
  checks touch additional packet/header state beyond the hash data.

The hottest generated-image bins lie next to bucket and chain-node loads; TCLock's
native body is also hottest around the corresponding traversal. This supports
investigating the interaction between extra control/packet traffic and dependent
payload loads, rather than assigning all extra time to an individual budget instruction.
Unqualified cycle samples permit arbitrary IP skid according to the
[Linux perf documentation](https://raw.githubusercontent.com/torvalds/linux/v6.1/tools/perf/Documentation/perf-list.txt).
They do not establish the latency, NUMA source or cache level of a particular load.

About 94.33%–94.78% of KD worker sample weight and 94.95%–94.99% of TCLock's is in
their waiting functions; the dominant offsets resolve to the notification polling
loops. Most workers wait while a combiner serializes the protected work. That large
percentage is not evidence that removing PAUSE would improve the critical path.
Unresolved weight is retained, about 0.73%–1.25% across these profiles.

## Independent hardware counters

Each event is measured separately, three rounds per backend, with three-second
measurements: 24 diagnostic sessions. Every event has a positive count/runtime and
100% running time, with no multiplex scaling. The counters cover the measured client
and all inherited workers, including waiting; they are not isolated JIT-body counts.

| Event per completed operation | TCLock min / median / max | KD min / median / max | KD / TCLock medians |
| --- | --- | --- | --- |
| Cycles | 34205 / 34341 / 34372 | 45520 / 45665 / 45782 | 1.330 |
| Instructions | 2426 / 2431 / 2444 | 4190 / 4196 / 4202 | 1.726 |
| Generic cache misses | 3.597 / 3.611 / 3.641 | 3.487 / 3.490 / 3.538 | 0.967 |
| L1 data-load misses | 36.315 / 36.442 / 36.455 | 42.714 / 42.915 / 43.127 | 1.178 |

KD does more aggregate instruction work and incurs more L1 data-load misses per
completed operation, consistent with its larger execution/packet path. Total cycle
and instruction counts also increase when waiters spend longer waiting, so they
cannot alone identify the cause of the lower throughput. The generic cache-miss
count is slightly lower for KD; there is no evidence here for a higher total generic
miss count explaining the gap. These events do not distinguish remote DRAM from
cache-to-cache transfers, and no precise load-latency measurement was collected.

## NUMA placement and instrumentation controls

At a fixed 16 workers, compare CPUs 0–15 on node0 with CPUs 0–7,20–27 split 8+8.
Both retain NUMA-on queue grouping and identical measurement settings.

| Placement | Backend | Peak min / median / max | Spread | Whole min / median / max |
| --- | --- | --- | --- | --- |
| Node0, 16 workers | Linux | 2.924 / 3.550 / 3.664 | 20.87% | 2.914 / 3.001 / 3.043 |
| Node0, 16 workers | TCLock | 4.668 / 4.676 / 4.689 | 0.44% | 4.652 / 4.652 / 4.675 |
| Node0, 16 workers | KD | 3.789 / 3.791 / 3.795 | 0.16% | 3.773 / 3.781 / 3.782 |
| Split 8+8 | Linux | 1.630 / 1.634 / 1.658 | 1.72% | 1.623 / 1.629 / 1.650 |
| Split 8+8 | TCLock | 2.646 / 2.662 / 2.675 | 1.10% | 2.640 / 2.652 / 2.664 |
| Split 8+8 | KD | 1.999 / 2.000 / 2.003 | 0.21% | 1.994 / 1.995 / 1.996 |

Splitting the same cohort reduces KD's median by **47.24%** and TCLock's by **43.08%**.
KD/TCLock peak falls from 80.93% within one node to 74.89% across nodes. Thus placement
has a large effect on both, and KD already has a substantial gap locally. The test
changes worker placement and resulting access/sharing patterns; it does not isolate
the exact number or cost of remote transfers. Shared payload ownership and waiter
state moving between executing CPUs are plausible mechanisms supported by the code.
Spin continuation/polling storage already uses `vzalloc_node(cpu_to_node(i))` and
cache-line coloring; this is not an experiment with all waiter storage deliberately
allocated on the loader's node. Physical allocation fallback was not measured.

TCLock's backend disables UBSAN, whereas the default KD provider inherits the kernel
setting. A separate 36-thread hash build disables only the private KD provider's
compiler instrumentation, retaining its explicit protocol checks:

| Backend, UBSAN control | Peak min / median / max | Spread | Whole min / median / max |
| --- | --- | --- | --- |
| Linux | 1.610 / 1.615 / 1.851 | 14.92% | 1.595 / 1.607 / 1.688 |
| TCLock | 2.639 / 2.643 / 2.647 | 0.28% | 2.628 / 2.629 / 2.634 |
| KD provider UBSAN off | 2.056 / 2.057 / 2.059 | 0.16% | 2.048 / 2.051 / 2.053 |

KD improves 3.81% in median and 3.74% in peak, reaching 77.80% of the simultaneous
TCLock peak. Instrumentation/build layout contributes, but disabling it leaves a
large gap. This control is not merged into the default score or treated as a code
optimization. Later placement controls rebuild the default kernel-UBSAN provider.

## Interpretation and remaining attribution

The hash workload exposes costs that the small straight-line payload does not:
dependent traversal over a larger data set, spilled caller inputs, generated block
budgets and register-packet accesses, plus per-request admission/retirement. Fresh
profiles locate extra event weight in that execution path. NUMA placement worsens
both implementations and modestly widens the relative gap. UBSAN has a smaller,
measured effect. These findings are consistent with the workload-specific result;
they do not prove that one instruction or one memory access explains all 25%.

JIT coverage, business results and worker participation are healthy in this run.
The 2172-byte generated hash image has no MFENCE/LFENCE/SFENCE or LOCK-prefixed
instruction; there is no per-body hardware fence to remove. External queue/ticket
atomics and publication/ownership ordering remain part of the lock protocol.

Further optimization should isolate repeated budget/packet work and the sampled
frame/successor accesses while preserving bounded execution, source lifetime and
owner/ACK rules. The earlier register-residency and broad-prefetch experiments
[did not give a repeatable win](https://github.com/hailongeric/kdlock/blob/e533214/bench/tclock_compare/results/20260927-hash36-profile.md); static instruction
counts alone do not justify repeating them or claiming a speedup. Precise memory
attribution would be needed before selecting a change specifically for remote
load latency. The 90% hash target remains unmet.

## Reproduction and preserved evidence

After the usual [recovery checks](../../../docs/AGENTS.md), the main guest command is:

```sh
taskset -c 0-35 python3 bench/tclock_compare/run.py \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --workload rcuht --threads 36 --backends native tclock kdlock \
  --repeats 3 --duration-ms 2000 --peak-window-ms 300 --collector-cpu 38 \
  --numa on --kd-batch-size 1024 --spin-prefetch 2 \
  --kd-provider-ubsan kernel --output "$OUT"
```

The one-cacheline control uses `--workload cacheline --cachelines 1`; the UBSAN control
uses `--kd-provider-ubsan off`. Placement controls use `--threads 16 --cpus 0-15` or
`--threads 16 --cpus 0-7,20-27`. Diagnostic drivers and their exact commands are frozen
in their archives; all diagnostic records have `performance_result=false` and are
excluded from the benchmark tables. No failed live session was discarded.

Guest directories are `/root/kdlock-evidence/numa-20260928-spin36-analysis-PHASE`.
Host evidence is under `bench/.tmp/spin36-analysis-20260928/`, including raw frozen
inputs, binaries, logs, records and read-only analysis scripts. These large artifacts
are local evidence and do not travel with a Git checkout.

| Archive | Phases / sessions | SHA256 |
| --- | --- | --- |
| `hash.tar.gz` | hash, 9 | `ab7121f61867e109a4b51de6f46486d3b5f336316f6b9a2a506d38ec241829c4` |
| `cacheline.tar.gz` | cacheline, 9 | `f2bf0e889c4357c4140142ee39730c4913a88878a2dc753c0ab47b90885cd760` |
| `profile.tar.gz` | cycles profiles, 6 | `49c5117e802726e24110525eac5cfce1e5215d328b139fda7f0540beed97e3a8` |
| `pmu.tar.gz` | four separate events, 24 | `2c0e36d5a8009971663402a9517647b207e27af4adbef2dd6378c90659c7985a` |
| `controls.tar.gz` | UBSAN-off / local16 / split16, 27 | `d3c38ea8e9edf36c1d3df180e79de3e5a57f9a66e947fbd393af193944d07494` |
| `analysis.tar.gz` | Offline audits, disassembly, drivers and host checks | `d3708b0e1a0210218f4d0c208a9c400af1472bb30a7b20dcb754e91d5195a037` |

`measurement-audit.json`, `profile-attribution.json` and `pmu-analysis.json` retain
unrounded values, all rounds, node shares and per-symbol attribution. All five
measurement phases passed the independent read-only audit.
