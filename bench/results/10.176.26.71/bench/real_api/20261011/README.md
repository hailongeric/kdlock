# Real kernel API run record, 2026-10-11

This record preserves the environment, validation, exploratory outcomes and
reproduction details for the 288 accepted final OFD/setfd sessions. The
[benchmark results document](RESULTS.md) introduces the test subjects, their
kernel locks, the relationship to the TCLocks paper, and the measured performance
comparisons. It also covers single-thread cost, regressions and comparison limits.

| Document | Responsibility |
| --- | --- |
| [Benchmark results](RESULTS.md) | Workloads, lock implementations, methodology, scaling figures and interpretation |
| [OFD tables](ofd/README.md) / [bitmap tables](setfd/README.md) | Generated comparisons for every thread count and layout; adjacent CSV/JSON retain full statistics |
| [Runner guide](../../../../../real_api/README.md) | Supported integration contract and maintained commands |
| This run record | Frozen environment, validation, exploratory failures and evidence locations |

## Exploratory runs

These pilot and failed sessions remain separate from the final matrices. Their
original status and samples are preserved, including subsequent cleanup records.

| Exploratory run | Outcome retained separately |
| --- | --- |
| [screen-v1](exploratory/real-api-screen-v1/README.md) | Setup failed before module loading: this kernel's tmpfs has no `user.*` xattr handler. One failure, seven unrun sessions. The workload was changed to root-only `trusted.*`. |
| [screen-v2](exploratory/real-api-screen-v2/README.md) | Eight single-thread xattr/OFD controls passed; no KD JIT execution. |
| [contended-v1](exploratory/real-api-contended-v1/README.md) | 32 short-warmup sessions passed. OFD produced JIT bodies; xattr hit an unlearned `strcmp()` helper and completed through the native remainder with zero returned JIT bodies. Those xattr rates are fallback results. |
| [learning-v1](exploratory/real-api-learning-v1/README.md) | Runner incorrectly required zero writers while the paused daemon still held its writer lease. Session remains failed/undrained in its original record; subsequent normal retirement and unload are documented in the [manual cleanup note](exploratory/manual-drain-note.json). |
| [learning-v2](exploratory/real-api-learning-v2/README.md) | After helper learning, xattr was refused by pointer/context analysis with `CONTEXT_ADDRESS_WIDENED` / `CONTEXT_NATIVE_ONLY`. Automatic cleanup drained successfully. [Exact diagnostic excerpt](exploratory/xattr-refusal.txt). Admission safeguards were retained. |
| [setfd-screen-v1](exploratory/real-api-setfd-screen-v1/README.md) | 24 sessions passed with duplicated descriptors sharing one file description. KD lost the 48-thread cases to TCLock. These have a different reference-counter bottleneck and shorter warmup than the final bitmap test; they are not pooled with it. |

## Environment and validation

Physical host `10.176.26.71`: two Xeon Gold 6438N sockets, 32 physical cores each,
SMT off, `ondemand`. The recovery VM has 64 vCPUs and 24 GiB split across two
NUMA nodes. Guest vCPU N is pinned to physical CPU N; node 0 is CPUs 0–31,
node 1 is 32–63. Worker cohorts are prefixes of CPUs 0–59; collector CPU 63
also hosts QEMU service threads. Setup first-touches metadata on CPU 0.
See the [physical placement capture](host-environment.json).

The [kernel identity check](kernel-identity.json) verified the captured source,
config, build files and live Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`
for `6.1.159-kdclobber2`. Boot policy is `nokaslr nopvspin` with voluntary
preemption. The actual monitor snapshot `real-api-20261011-v1` was created and
confirmed before live work; it remained available after completion.
KD and TCLock use NUMA-aware spin backends with configured batch size 1024.
TCLock is the repository's port pinned to upstream
`bbfb9f00a12af51dff6ca291cb9829a82960c2ef`.

Each final matrix has two data layouts × six worker counts × four backends ×
three rounds = 144 sessions. Warmup requires at least 48,000 operations and one
second per worker; measurement lasts two seconds. Actual finishing timestamps
form the whole-run denominator. Peak selection uses a full-cohort window of at
least 300 ms after 300 ms settling, sampled every 10 ms in 256-operation batches.
Checkpoint quantization and sampling brackets remain measurement limitations.

The final runs completed **2,242,388,480 timed operations**. Every substituted
arm recorded exactly one helper redirection per operation. All syscalls passed
the per-operation and before/after oracles, all workers progressed, and each
KD session retired with zero modules, frames and writers before normal unload.
TCLock passed its queue/context quiescence check; kernel-log checks found no
session faults. The guest was independently checked idle after all runs.

There are **59 JIT-positive KD sessions out of 72**, with 529,107,216 returned
JIT bodies. The 13 `NO_JIT` sessions are the 12 single-thread controls and one
8-thread/16-range OFD round. At the recommended 16–60-thread points, the JIT
share is about 95.5–99.9%. TCLock spin delegation counts remain unmeasured;
the emitted stack-switch/continuation code passed its assembly audit.

[Two basic C programs](validation/basic.log), [four report checks](validation/report-final.log)
and [eight peak-window checks](validation/peak.log) passed in the guest. The
report checks reject failed/undrained scores and retain missing/NO_JIT cases.
All archived source and binary hashes were verified, and all 288 raw final
measurements and peak scores were independently recomputed. The
[verification receipt](evidence.json) records counts, commands, environments
and per-run manifest/binary digests. Plotting used a separate guest analysis
environment after timing; [dependency versions](plot-dependencies.txt) are saved.

## Reproduction and evidence

Follow the [VM workflow](../../../../../../docs/operations/VM.md), synchronize source
while idle, verify the kernel and physical pins, and confirm a recoverable
snapshot. Then use the pinned benchmark Python environment:

```sh
export PATH=/root/kdlock-evidence/clobber-20260918/venv/bin:$PATH
export LC_ALL=C KDLOCK_RECOVERY_CONFIRMED=1
export KDLOCK_SNAPSHOT_TAG=YOUR_CONFIRMED_SNAPSHOT
python3 bench/real_api/run.py --kinds ofd --queries tail \
  --entries 16 128 --threads 1 8 16 32 48 60 --repeats 3 \
  --backends stock native tclock kdlock --warmup 48000 --warmup-ms 1000 \
  --duration-ms 2000 \
  --output /root/kdlock-evidence/10.176.26.71/bench/real-api-ofd-new
python3 bench/real_api/run.py --kinds setfd --queries toggle \
  --entries 16 512 --threads 1 8 16 32 48 60 --repeats 3 \
  --backends stock native tclock kdlock --warmup 48000 --warmup-ms 1000 \
  --duration-ms 2000 \
  --output /root/kdlock-evidence/10.176.26.71/bench/real-api-setfd-new
```

Exact executed arguments are in `evidence.json`. The two final matrices retain
their own frozen source versions: the bitmap client gained independent file
descriptions after the OFD run. Each point compares all backends at one version;
no samples were pooled across source versions or warmup settings.
The tested inputs are working-tree snapshots based on Git `3863910`, including
pre-existing edits. Their archived bytes and hashes define the experiment;
a clean checkout of that base commit alone does not reproduce those inputs.

Guest originals remain under `/root/kdlock-evidence/10.176.26.71/bench/real-api-*`
and `tests/real-api-20261011`. A complete 46,009,122-byte archive and host receipts
are preserved on both the physical benchmark host and the source host at
`bench/results/10.176.26.71/raw/bench/real-api-20261011/`. It retains **352 accepted,
three failed and seven unrun sessions**, including source copies, ELFs, JIT
images/disassembly, commands, raw samples, kernel logs and drain records.
Raw files are ignored in Git; this directory contains the compact reports.
The archive SHA256 is
`0bd1310e4c6bea5d2499d6ee4d39de970d3c566cd9ddaa855b0d71e3d8129a24`;
[all receipt hashes](archive-sha256.json) are included.
