# Where ordinary mutex workers spent CPU time

At three workers, the unprofiled one-line grid put KD 3.61% below Native, with zero offers, delegated completions and handbacks. The samples place KD workers in ordinary mutex acquisition, particularly queue insertion, lock-byte acquisition and inspecting the owner. The data identify places to investigate but do not establish how much of the timing gap any one operation caused. At five workers, polling an individual waiter's queue node accounts for 1,201 of 3,040 KD worker samples (39.5%) in this delegation-off profile. [Unprofiled throughput and counters](measured-cells.md#standard-three-way-comparison) · [Matched instruction addresses](raw/profile-addresses.json)

## Sampling and attribution

On release `7.0.0-38-kdlocalspin6`, boot `fc8104fd-5e0c-406f-b93e-e7c6e6cabf6d`, perf 7.0.14 sampled kernel CPU time at 199 Hz. Each point used one 3,000 ms recording after a 300 ms warmup. The workers incremented one protected line and ran 256 register-only iterations between operations. Three workers occupied guest CPUs 0–2 and five workers occupied CPUs 0–4. The controller and worker identity observer occupied CPUs 38 and 39. The four points ran in the order Native 3, KD 3, KD 5, Native 5, with delegation off throughout. The signed benchmark and provider modules matched the recorded build. The live kernel and the symbolized `vmlinux` shared build ID `7a0b931c3fd02792c24a0ced99af882727b6d151`. [Successful guest archive](raw/main-mutex-profile02.tar.gz)

During each measured ioctl the observer recorded each worker’s live thread name, TID, start time and affinity. The analysis joined samples to those TIDs and checked every worker sample’s CPU. Every recording reconciled with its raw sample count. There were zero lost records, unparsed samples or samples on the wrong CPU. For benchmark-module addresses missing a perf symbol, the analysis checked the live symbol start and exact ELF symbol size. Unresolved samples are included in every worker denominator. The archive contains the worker observations, decoded samples, reports, counters and full symbol counts. [Successful guest archive](raw/main-mutex-profile02.tar.gz)

| Recording | All tested-CPU samples | Worker samples | Per-worker sample counts in CPU order | Worker samples resolved by benchmark ELF | Unresolved worker samples |
| --- | ---: | ---: | --- | ---: | ---: |
| Native 3 | 1,881 | 1,819 | 606, 606, 607 | 858 | 2 |
| KD 3 | 1,884 | 1,827 | 609, 609, 609 | 902 | 3 |
| Native 5 | 3,150 | 3,044 | 609, 609, 609, 609, 608 | 765 | 2 |
| KD 5 | 3,140 | 3,040 | 608, 608, 608, 608, 608 | 761 | 1 |

## Sampled functions and instructions

Each cell lists samples and percentage of that recording’s worker samples. The benchmark worker function includes the register-only work between acquisitions. Functions shown are flat instruction-pointer samples. Other functions and unresolved samples remain in the denominator. [Full counts and decoded samples](raw/main-mutex-profile02.tar.gz)

| KD symbol | Three workers | Five workers | Native symbol | Three workers | Five workers |
| --- | ---: | ---: | --- | ---: | ---: |
| `worker_fn` | 831 (45.5%) | 702 (23.1%) | `worker_fn` | 812 (44.6%) | 716 (23.5%) |
| `kd_wait_sleepable` | 441 (24.1%) | 1,780 (58.6%) | `__mutex_lock.constprop.0` | 276 (15.2%) | 311 (10.2%) |
| `kd_mutex_can_spin` | 105 (5.7%) | 63 (2.1%) | `mutex_spin_on_owner` | 163 (9.0%) | 202 (6.6%) |
| `kd_mutex_unlock` | 232 (12.7%) | 266 (8.8%) | `mutex_unlock` | 261 (14.3%) | 231 (7.6%) |
| `kd_mutex_lock` | 119 (6.5%) | 138 (4.5%) | `mutex_lock` | 148 (8.1%) | 137 (4.5%) |
| `kmutex_w` | 71 (3.9%) | 59 (1.9%) | `nmutex_w` | 46 (2.5%) | 49 (1.6%) |
| `kd_mutex_lock_slow` | 18 (1.0%) | 11 (0.4%) | `osq_lock` | 71 (3.9%) | 1,146 (37.6%) |

With three workers, 125 KD samples fell on `kd_wait_sleepable+0x359`, the test immediately after the lock-byte `cmpxchg`. Another 77 fell on the lock-byte check at `+0x350`, and 86 on the test after the queue-tail exchange at `+0x102`. In `kd_mutex_can_spin+0x13`, 84 samples fell immediately after loading the owner pointer. Native had 114 samples at `mutex_spin_on_owner+0x26` after an owner-word load, 88 at `__mutex_lock.constprop.0+0x686` after the owner-word compare-exchange, and 52 at `osq_lock+0x40` after its queue-tail exchange. A sample following a locked instruction cannot identify its outcome or measure its latency. [Exact IPs and surrounding assembly](raw/profile-addresses.json)

With five workers, KD had 857 samples at `kd_wait_sleepable+0x178` and 344 at `+0x17c`, the waiter's node-state load and following loop-counter increment. Native had 623 at `osq_lock+0xa0` and 189 at `+0xa3`, its node-state load and test (26.7% combined). Native also had 210 at `osq_lock+0x8e` in the sequence that reads the predecessor's CPU and invokes the virtual-CPU state check. These concentrations show where workers waited. The event reports on-CPU locations and supplies no cache-line transfers, blocked durations or per-operation cycle costs. [Exact IPs and surrounding assembly](raw/profile-addresses.json)

The profiled KD points recorded 6,158,441 plain waits and 15 parks at three workers, then 4,507,549 plain waits and 37 parks at five. Offers, delegated completions, handbacks and sessions were all zero. The three-worker result supports comparing the ordinary queue and grant path in a matched experiment before attributing the throughput difference to delegation policy. The five-worker profile describes forced local execution. A separate run would be needed to attribute samples with delegation enabled. This collection covered one line, one recording per backend and worker count, and two backends. The sixteen-line grid, TCLock and other worker counts have no corresponding CPU-time profile here. [Profiled work and counter deltas](raw/main-mutex-profile02.tar.gz) · [Unprofiled grid](measured-cells.md)

## First recording and recovery

The first Native three-worker attempt captured 1,866 samples with zero lost records. Perf labeled 1,806 as `kthreadd` and 60 as `swapper`. Filtering by the expected worker names returned zero worker samples. The runner ended with status 1 and unloaded all five modules normally. Those samples have no verified worker attribution. The second runner collected fresh recordings using live worker TIDs, passed all four points, and restored the initial module set. Both archives preserve their guest runners, status and cleanup records. [First guest archive](raw/main-mutex-profile01.tar.gz) · [Retry guest archive](raw/main-mutex-profile02.tar.gz)

| Original guest archive | Bytes | SHA-256 |
| --- | ---: | --- |
| `main-mutex-profile01.tar.gz` | 40,672 | `3e60468426070ba7e6d76c5dcf33ccf33cdfec58cc2a25d52b552b2ac73edb2e` |
| `main-mutex-profile02.tar.gz` | 145,529 | `5070d9044235275a155c08ce071f96842e7064f2cd33e77ac76d057cb270f877` |
