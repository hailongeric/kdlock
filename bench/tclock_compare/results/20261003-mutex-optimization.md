# Mutex optimization, 2026-10-03

This continues from `3332e25` using the default UBSAN-off private KD provider.
All builds, tests and measurements ran in the recovery guest on the existing
`6.1.159-kdclobber2` kernel (Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`). Host CPU placement and the recovery
snapshot were freshly checked. Worker CPUs 0–35 and collector CPU 38 have
2.5 GHz minimum/maximum frequency; QEMU vCPUs map one-to-one to host CPUs.
Workers 0–19 are on node 0, 20–35 on node 1. NUMA builds stay enabled;
the current KD mutex queue itself remains FIFO. KD waiters stay pinned;
TCLock retains its parking implementation.

Each scored configuration has three rounds, 48,000 warmup operations per worker,
2 seconds measurement, and the highest valid 300 ms window after 300 ms settling.
All samples, including variation in Linux/TCLock, are retained. These initial
screens cover 1, 2, 16 and 36 threads, one cacheline; they are not a full matrix.

## Baseline diagnosis

The baseline reaches only 66.30% of TCLock's corresponding best 36-thread peak
(3.222 versus 4.860 Mops/s), although its 16-thread peak exceeds TCLock.
At one thread it reaches 15.123 versus 36.140 Mops/s, without any JIT execution.
Thus neither cross-node accesses nor generated code alone explains the gap.
KD delegates 4.42–6.48% of measured operations at 16 threads and 6.28–7.35% at 36;
TCLock delegates 98.71–98.88% and 96.12–98.11%, respectively.

A separate flat-IP cycles profile (499 Hz, no lost samples, exact kernel/module
ELF ranges) attributes 40.38% of KD worker event-period weight at 16 threads and
70.21% at 36 to `__pv_queued_spin_lock_slowpath`. KD queue polling accounts for
35.80%/12.03%. The task registry and shadow map both have global writer locks;
flat samples alone do not identify which lock caused every wait. At one thread,
RCU read lock/unlock account for 7.79%, and task rerouting another 5.36%.
TCLock at 36 spends 93.30% in its own queued waiter slowpath. These are CPU-wide
sample weights, not isolated executor costs or remote-memory latency.

Separate one-event diagnostics at 36 threads counted instructions and cycles
with 100% running time. Per completed operation they include every worker's
polling and client setup: instructions KD ~1,428 versus TCLock ~2,059;
cycles KD ~11,060 versus TCLock ~21,042. Different diagnostic sessions must not
be divided into a purported per-body IPC. Lower aggregate KD counts do not mean
higher throughput: parking, global lock waits and useful-work distribution differ.
No remote-latency or cache-miss attribution is inferred from these counters.

Historical stable-task-cache failures used the kernel UBSAN policy and greatly
increased JIT coverage/batch length. They do not establish that task caching
itself is expensive, but they do rule out assuming that higher JIT coverage is
necessarily faster. Their failed samples remain in the September report.

## Native acquisition before the counting pin

Successful original-owner CAS now precedes preemption disabling. Its approximate
entry observation is one x86 `this_cpu_inc`; failed acquisition still pins entry
and contention sampling together, and unpins before any sleeping native path.
No ownership, task reference, admission threshold, wrapper ABI or waiter policy
changes. This is independent of subsequent registry/shadow experiments.

The guest's two basic tests plus mutex resource and hotlock sampling drivers
passed (four drivers total). The resource fixture checks native success never
pins and failed-acquisition sampling remains pinned. All 36 timed sessions passed
business/JIT requirements and drained; 1/2-thread sessions correctly report JIT=0,
while every 16/36-thread KD session has returned-body evidence.
KD median changes versus the fresh baseline: +10.19% (1), +7.96% (2), +5.75% (16),
+2.44% (36). The 36-thread spread is 9.50%, so its small median gain is not a claim
of a stable isolated cross-node speedup. Its best peak remains only 75.49% of
same-phase TCLock. The overall target is not met.

## Scored samples

Values are Mops/s. Each triple is minimum / median / maximum. Spread is
(maximum − minimum) / median for peak throughput. Whole-run values remain
separate from selected windows.

### baseline

| Threads | Arm | Peak min/median/max | Whole min/median/max | Peak spread |
|---:|---|---|---|---:|
| 1 | native | 27.801/27.986/27.994 | 27.788/27.970/27.984 | 0.69% |
| 1 | tclock | 36.132/36.137/36.140 | 36.107/36.109/36.122 | 0.02% |
| 1 | kdlock | 15.110/15.112/15.123 | 15.091/15.105/15.115 | 0.09% |
| 2 | native | 6.653/6.985/7.256 | 6.627/6.960/7.236 | 8.63% |
| 2 | tclock | 9.652/10.195/11.012 | 9.617/10.163/10.960 | 13.35% |
| 2 | kdlock | 5.126/5.128/5.841 | 5.122/5.127/5.754 | 13.94% |
| 16 | native | 6.975/7.227/7.407 | 6.902/7.136/7.361 | 5.98% |
| 16 | tclock | 4.366/4.435/4.701 | 4.333/4.416/4.687 | 7.56% |
| 16 | kdlock | 4.855/4.862/5.026 | 4.839/4.888/4.958 | 3.53% |
| 36 | native | 5.304/5.498/5.704 | 5.156/5.158/5.187 | 7.26% |
| 36 | tclock | 4.471/4.484/4.860 | 4.417/4.462/4.495 | 8.67% |
| 36 | kdlock | 3.106/3.182/3.222 | 2.764/2.840/2.875 | 3.63% |

### native-pin

| Threads | Arm | Peak min/median/max | Whole min/median/max | Peak spread |
|---:|---|---|---|---:|
| 1 | native | 27.979/27.979/27.988 | 27.911/27.964/27.975 | 0.03% |
| 1 | tclock | 36.132/36.135/36.143 | 36.092/36.100/36.113 | 0.03% |
| 1 | kdlock | 16.647/16.652/16.791 | 16.642/16.648/16.783 | 0.86% |
| 2 | native | 6.441/6.577/7.143 | 6.408/6.558/7.130 | 10.68% |
| 2 | tclock | 10.215/10.341/11.108 | 10.186/10.324/11.062 | 8.63% |
| 2 | kdlock | 5.421/5.536/6.138 | 5.219/5.527/6.125 | 12.95% |
| 16 | native | 6.944/7.199/7.317 | 6.821/7.103/7.271 | 5.18% |
| 16 | tclock | 4.571/4.613/4.689 | 4.548/4.605/4.662 | 2.57% |
| 16 | kdlock | 5.134/5.141/5.432 | 5.159/5.192/5.331 | 5.80% |
| 36 | native | 5.447/5.714/5.777 | 4.931/5.530/5.639 | 5.77% |
| 36 | tclock | 4.454/4.491/4.539 | 4.429/4.474/4.475 | 1.89% |
| 36 | kdlock | 3.116/3.260/3.426 | 3.009/3.021/3.375 | 9.50% |

## Evidence

Guest directories under `/root/kdlock-evidence/`:
`mutex-20261003-mutex-baseline-c1`, `mutex-20261003-native-pin-unit`,
`mutex-20261003-mutex-native-pin-c1`, `mutex-20261003-baseline-profile`,
`mutex-20261003-baseline-instructions`, `mutex-20261003-baseline-cycles`.
Each benchmark directory retains frozen source/ELF identities, commands, kernel
identity, all session records and cleanup logs. Host observations and downloaded
records are under `bench/.tmp/mutex-20261003/`; diagnostic throughput is excluded
from scored results. No guest kernel changes or full test suite were run.

Record SHA256 (downloaded directly from completed guest outputs):

- `baseline-records.json`: `ada4d660f9a04f87522748a81b1e5fa47dbf48ccff3673d1e292897c0560a8e1`
- `native-pin-records.json`: `ef418e38c81dad834b217a0903040b32c41455424e15505d3e4ce026e4a1b3cc`
- `instructions-records.json`: `565103878074b84288a7b2f9afd9faf97b71f9e4c7146b6f6c4626a4ab104690`
- `cycles-records.json`: `4d359f61b3b39494adbc320060ce4b1ca98fa2829e28d4b1255583247f025c5d`
