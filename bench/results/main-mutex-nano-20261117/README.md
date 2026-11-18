# Ordinary mutex nano on 380G10

With sixteen protected cache lines, KD exceeded both Native and TCLock in all three matched rounds at 6, 8, 16 and 32 workers. With one line, KD exceeded both at 8 workers. In the standard grid, KD trailed TCLock at 16 and 32 workers by 5.22% and 2.19% of TCLock throughput. The later exit-depth controls had closer one-line rates at 16 workers. The shortfall persisted while both backends executed millions of waiter sections. Keeping entry depth 3 and lowering exit depth from 2 to 1 improved the measured crossover cells by 15–17%. The highest worker counts showed small regressions with the same setting. [All rates, ranges, paired wins and execution counts](measured-cells.md)

## Matched comparisons

The rates below are medians of three repetitions, in millions of operations per second. Event counts sum those same repetitions. TCLock counts executed waiters when a batch returns. KD's counters record completed delegated sections and handbacks. Each protected operation increments one counter on each selected cache line. Every worker performs 256 iterations of private work after releasing the lock. [Worker and test bodies](../../kd_bench.c) · [Raw points](raw/points.jsonl)

| Workers | Lines | Native | KD | TCLock | KD delegated | KD handbacks | TCLock delegated |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 6 | 1 | 3.2553 | 3.2177 | 2.9781 | 313,089 | 0 | 5,192,536 |
| 6 | 16 | 1.9306 | 2.6920 | 2.1198 | 6,285,184 | 0 | 4,637,088 |
| 8 | 1 | 3.2567 | 3.7912 | 3.5925 | 7,604,764 | 0 | 9,878,793 |
| 8 | 16 | 1.9392 | 3.3600 | 2.6685 | 10,424,602 | 0 | 8,156,824 |
| 16 | 1 | 3.2639 | 4.5864 | 4.8390 | 13,983,485 | 0 | 14,688,722 |
| 16 | 16 | 1.9387 | 3.3786 | 2.7144 | 10,313,648 | 0 | 8,232,835 |
| 32 | 1 | 1.2943 | 4.6559 | 4.7600 | 14,593,620 | 0 | 15,023,670 |
| 32 | 16 | 0.9062 | 3.3751 | 2.6974 | 10,602,334 | 0 | 8,418,892 |

The lower-worker results expose a separate cost. At 1–4 workers, KD recorded zero offers, delegated completions and handbacks at both widths. At 2 workers KD was 2.91% below Native on one line and 6.87% below on sixteen, with 88,685 and 5,809,969 plain waits. At 3 workers it was 3.61% and 3.23% below Native, with more than five million plain waits at each width. These points exercised ordinary acquisition and queueing. At 1 worker on one line all three medians were within 0.05%. On sixteen lines KD was 2.25% below Native and TCLock's own three rates spanned 12.98% of its median. [Low-worker medians, ranges and events](measured-cells.md#standard-three-way-comparison)

At 4 workers on sixteen lines, TCLock served 2,850,217 waiters over returned batches and KD served zero. At 5 workers KD served only 7,825 and still trailed TCLock by 3.24%. By 6 workers, KD served 75.4% of its measured sixteen-line operations and 3.1% of its one-line operations. At 16 and 32 workers the one-line TCLock lead persisted with KD serving more than 99.8% of its operations. The phase counters establish when delegation occurred. They do not measure the duration of a physical hold, each transfer’s latency, or cache misses. [Standard cells](measured-cells.md#standard-three-way-comparison) · [Provider accounting](../../../tclock_backend/mutex/combiner.inc)

## Sleepable entry threshold

The controlled block rotated KD with `kd_deleg_enter_sleep` at 2, 3 and 5, alongside fresh Native and TCLock references. The threshold counts waiters *behind* the queue head. The test kept exit depth 2 and the KD batch limit 4096. Each result below compares against threshold 3 in the same block. [Matched control rates and counts](measured-cells.md#matched-sleepable-entry-thresholds) · [Admission and exit policy](../../../kernel/kd_core.c)

- At 5 workers on sixteen lines, lowering the threshold to 2 improved all three rounds, from 1.9826 to 2.0131 Mops/s (+1.53%). Delegated completions rose from 7,217 to 455,801 with zero handbacks in both settings. TCLock still reached 2.0476 Mops/s with 3,883,406 delegated completions. On one line at 5 workers the same change lost all three rounds (−0.24%), despite delegated completions rising from 3,688 to 107,681, again with zero handbacks.
- At 32 workers on sixteen lines, threshold 2 had a 6.20% higher median and won only one of three matched rounds. The observed ranges overlapped, spanning 8.14% of the median at 2 and 9.84% at 3. There were 10,720,402 and 10,648,492 delegated completions, respectively, with zero handbacks. This cell gives insufficient evidence of a repeatable gain.
- Threshold 5 gained 0.01% in all three rounds at 4 workers on one line, where both settings recorded zero delegated completions and zero handbacks. It lost 0.47% in all three rounds at 8 workers on one line, where threshold 5 recorded 6,865,793 delegated completions and threshold 3 recorded 7,369,575, both with zero handbacks. Across eight controls per candidate, each alternative won all rounds in one cell and lost all rounds in one.

## Exit depth at the delegation crossover

With mutex entry depth fixed at 3, lowering `kd_deleg_exit` from 2 to 1 lets the combiner retain delegation with one successor behind it. This change gave the largest repeatable gain in this run. Each comparison below uses three rounds from the exit-depth block. Native and TCLock controls rotated through the same block. [Matched rates, round ranges and execution counts](exit-threshold.md)

| Workers | Lines | Native | TCLock | KD exit 2 | KD exit 1 | Change | Mode exits at 2 → 1 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 6 | 16 | 1.994 | 2.139 | 2.684 | 3.087 | +15.0% | 15,393 → 1,726 |
| 8 | 1 | 3.363 | 3.548 | 3.785 | 4.428 | +17.0% | 18,912 → 683 |

Both improvements held in all three paired rounds. Delegated completions rose from 5,886,635 to 9,346,704 at 6 workers and from 5,802,969 to 13,393,530 at 8 workers. KD recorded zero handbacks at both exit depths in every ordinary measured cell. Across the other cells, exit depth 1 lost all three rounds at 16 workers on one line (−1.4%) and at 32 workers on sixteen lines (−1.9%). Those two settings already had at most thirteen mode exits across all three rounds at either depth. These observations support using the lower exit threshold for an isolated workload that repeatedly loses delegation near the crossover. The shared default remains 2. The experiment measured aggregate throughput and worker progress. Tail latency and other lock families require separate measurements. [Full exit-depth results](exit-threshold.md)

## Functional evidence

The API check passed, including the ordinary mutex assertions. The ordinary nano work recorded zero KD handbacks in all timed cells. A separate `mix` body checks task identity across the critical section and exercises an indirect call, yielding and nested acquisition. At 8 workers it recorded 1,079,114 delegated completions and 72,143 handbacks. At 32 workers it recorded 1,689,169 and 112,653. Of the total 184,796 handbacks, the counters classified 184,534 as frontiers and 262 as misses. Every worker progressed and the protected totals matched. [API receipt](raw/api.json) · [Functional counters](raw/checks.json) · [Test body](../../kd_bench.c)

The `mutex_cl` fixture resolved to ordinary entry behavior on this build, which disables `CONFIG_KDLOCK_CLOBBER_ENTRY`. At 8 and 32 workers together it recorded 4,769,389 delegated completions, zero handbacks and zero compact offers or completions. Compact-state execution requires a different build. [Configuration](../main-spin-final-20261117/build/config) · [Entry selection](../../../include/kdlock/kd_api.h) · [Checks](raw/checks.json)

## Configuration and verification

The campaign ran on the local 380G10 QEMU guest, using kernel `7.0.0-38-kdlocalspin6` build #2, frozen main source `18dad4a1c372d77a1155db671d56c148918344da`, and boot `fc8104fd-5e0c-406f-b93e-e7c6e6cabf6d`. The controller used CPUs 38–39. Each worker had its own CPU. Counts through 16 used node 0 starting from CPU 0. The 32-worker placement used CPUs 4–35, split equally between the two 20-CPU NUMA nodes. The host recorded 2.5 GHz minimum and maximum frequency-policy bounds on every worker CPU and one-to-one vCPU pinning. Actual per-point frequencies were unmeasured. Guest preemption was `full (lazy)`, with `kd_api=0` and `kd_mm=N`. [Host and recovery snapshot](raw/host.json) · [Local disks and QEMU command](raw/local-endpoint.json) · [Guest topology](raw/topology.txt) · [Kernel identity and parameters](raw/identity.json)

The three backend-specific functions performed identical protected increments in the same benchmark module, with matched placement, warmup duration (250 ms) and nominal measurement duration (1,000 ms). Backend order rotated by round and worker count. The elapsed interval ends when the guest publishes stop. An in-flight operation may complete during drain and contribute to the numerator. The all-write nano checks validate progress and the protected counter sum. There is no reader comparison in those cells. KD and TCLock provider counters were sampled around each ioctl outside the worker loop, with the TCLock mutex bound as the provider’s diagnostic target. Its batch parameter was 1024. [Guest runner](run.py) · [Mutex provider and target](raw/mutex-provider.json)

The host rechecked all 571 raw records. The ordinary campaign contains 162 standard measured points and 120 measured threshold points, each with its own warmup. One learning point and six functional points account for the remaining seven. Every point had positive elapsed time, progress by every worker, agreement between worker and aggregate counts, and a protected-data delta equal to writes times lines. The measured rate agreed with operations divided by returned elapsed time. Every expected backend, setting and round was present. Native and TCLock points recorded zero activity in the global KD counters. The campaign completed with the original boot, kernel parameters, loaded module set and taint value restored, and the daemon exited with status zero. [Validation receipt](validation.json) · [Completion](raw/result.json) · [Cleanup](raw/cleanup.json)

The 131 frozen source input hashes agree with this checkout. The benchmark and four TCLock provider module hashes agree with the signed-artifact record reused from the same kernel build. The full guest archive occupies 260,799 bytes and has SHA-256 `dd70c3b0258dd36170c0d80244af02d7b1c59e20d128f0b369e4034417aa2693`. It includes startup and cleanup logs, daemon messages, dry-run disassembly, the exact runner and raw records. The host checked its 31 regular files against the extracted copies. Running `python3 analyze.py raw` from this directory regenerates the tables using the collected rows. [Complete archive](raw/main-mutex-nano01.tar.gz) · [Collection](raw/collection.txt) · [Measured inputs](raw/verified-inputs.json) · [Source manifest](../main-spin-final-20261117/main-final-identity.json) · [Signed artifacts](../main-spin-final-20261117/build/signed-artifacts.json)

## Sampling

With delegation disabled, a separate CPU-clock profile attributed 441 of 1,827 three-worker KD samples to `kd_wait_sleepable`. At five workers the share was 1,780 of 3,040. The matched binary places the three-worker hot instructions near queue insertion and lock acquisition. At five workers, two instructions in the waiter’s own node polling loop accounted for 1,201 samples. No profiled interval contributed a throughput point. [Sampling method, instruction locations and denominators](sampling.md)

After the final run, the controller verified the original boot, idle guest, restored parameters, initial module set and clean warning log. The two attached disks still held the recovery snapshot. [Final guest](raw/final-guest.json) · [Final host and snapshot](raw/final-host.json)
