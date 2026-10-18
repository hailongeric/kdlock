# Real mutex and UTS API run record

The [results document](RESULTS.md) introduces the APIs, kernel locks, matched
implementations and performance comparisons. This receipt records the measured
inputs, validation, rejected pilots and reproduction details. It extends the
[earlier spinlock API campaign](../20261011/README.md).

The final comparison contains **504 accepted/drained sessions and 3,495,313,152
timed operations**, measured on 2026-10-11 UTC. Including pilots and compatibility
checks, the archive retains **722 accepted, one failed and 53 unrun sessions**,
plus two build/capture failures before session planning.

| Final matrix | Sessions | Complete comparisons and data |
| --- | ---: | --- |
| FIONREAD, 16/128 buffers | 144 | [Tables](pipebytes/README.md), [CSV](pipebytes/summary.csv), [JSON](pipebytes/summary.json) |
| F_GETPIPE_SZ, 16 pages | 72 | [Tables](pipecap/README.md), [CSV](pipecap/summary.csv), [JSON](pipecap/summary.json) |
| lseek, SET/END | 144 | [Tables](seek/README.md), [CSV](seek/summary.csv), [JSON](seek/summary.json) |
| UTS hostname/domain, 20% writes | 144 | [Tables](utsname/README.md), [CSV](utsname/summary.csv), [JSON](utsname/summary.json) |

## Exploratory evidence

Pilots and failed sessions remain separate from the three-round final matrices.
Their original status is preserved, including any subsequent cleanup evidence.

| Run | Retained outcome |
| --- | --- |
| `real-sync-pipe-screen-v1` | Build failed before any benchmark module loaded: missing `FIONREAD` declaration. Fixed the required architecture ioctl include. No timed sessions. |
| `real-sync-pipe-screen-v2` | Capture failed before any timed session: `fs/shmem.c` was the wrong source path. Corrected to `mm/shmem.c`; the already built binaries and logs remain archived. |
| [real-sync-pipe-screen-v3](exploratory/real-sync-pipe-screen-v3/README.md) | Ten accepted sessions, one excluded TCLock client failure, 53 unrun. The checked post-oracle worker drain returned `EBUSY` after `pthread_join`. A subsequent normal checked drain and unload succeeded; the failed session remains failed/undrained in its original record. |
| [real-sync-pipe-screen-v4](exploratory/real-sync-pipe-screen-v4/README.md) | 64 accepted/drained sessions after adding a bounded retry of the existing checked drain. No live-task, queue or frame check was bypassed. Includes both 16- and 128-page capacity controls. |
| [real-sync-uts-screen-v1](exploratory/real-sync-uts-screen-v1/README.md) | 64 accepted/drained exploratory sessions, but Native used global `uts_sem` while KD/TCLock used private locks. This unequal scope is unsuitable for the final matched comparison. Contains 100%-writer controls with zero KD JIT bodies. |
| [real-sync-uts-screen-v2](exploratory/real-sync-uts-screen-v2/README.md) | 32 accepted/drained sessions with a private Native rwsem matching KD/TCLock's namespace scope. Uses 20% writes and explicit source reader/writer-state drain checks. |
| [real-sync-seek-screen-v1](exploratory/real-sync-seek-screen-v1/README.md) | 32 accepted/drained sessions covering both seek modes at 1/16/48/60 workers. |

The first pipe drain failure retained the module and exact worker registrations.
After the client exited, the existing provider's drain was called through a
saved ordinary-mutex fixture; it returned success, and all three involved modules
unloaded normally. There was no forced unload or snapshot recovery. The raw
`manual-drain-note.json` keeps the commands, helper identity and subsequent idle
check. Delayed checked-drain success is consistent with the gap between userspace
join completion and final kernel task exit; no trace of that scheduling interval
was collected. The client now retries only `EBUSY`, for at most five seconds.

The old UTS pilot is preserved to expose the lock-scope correction, not to inflate
the final speedups. Its pure-writer results have no measured JIT execution and
sometimes lose to Native/TCLock. These controls and the slower large-pipe cases
remain visible. No pilot is pooled into final medians or peaks.

## Environment and validation

The host is `10.176.26.71`, with two Xeon Gold 6438N sockets, 32 physical cores
each, SMT off and the `ondemand` governor. The guest has 64 vCPUs and 24 GiB,
split equally over two NUMA nodes. vCPU N is pinned to physical CPU N; workers
use prefixes of CPUs 0–59 and collector CPU 63 shares QEMU service threads.
The actual current-topology snapshot `real-sync-20261011-v1` was created and
verified before live tests. No recovery was needed.

Every runner invocation verifies the captured source/config/build inputs and
live Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960` for
`6.1.159-kdclobber2`. Boot policy remains `nokaslr nopvspin` with voluntary
preemption. The kernel was not rebuilt. Native, KD and TCLock replacement/provider
modules were checked for absence of UBSAN imports. The Stock kernel retains
UBSAN. Assembly audits check the emitted TCLock mutex/rwlock context-switch code.

The four final matrices use one frozen working-tree source version based on
Git `e306412`, including the pre-existing changes recorded in their manifests.
A clean checkout of the base commit alone does not identify those tested bytes.
Code under measurement was not edited or synchronized during the final matrix.
The later report files and navigation edits do not change that measured code.

[Two basic C checks](validation/basic.log), [five report checks](validation/report-final.log)
and [eight peak-window checks](validation/peak.log) passed in the guest. The C log
includes intentionally induced translator errors from its negative tests; both
programs report PASS. The report checks cover failed/undrained exclusion, missing
and NO_JIT cases, and the write-only UTS JIT denominator.

The extended runner also passed eight single-round
[OFD compatibility sessions](exploratory/real-sync-ofd-regression-v1/README.md)
and eight [bitmap compatibility sessions](exploratory/real-sync-setfd-regression-v1/README.md)
at 1/16 workers under all four arms. Both 16-worker KD checks executed JIT bodies.
These validate compatibility; they are not pooled with the earlier spinlock
performance report or the new three-round matrices. No full project suite ran.

All 504 final measurements and full-cohort peaks were replayed from raw samples,
along with syscall oracles, affinity, hook counts, exact retirement, kernel-log
fault checks and emitted TCLock context audits. The final 126 KD sessions contain
99 JIT-positive and 27 NO_JIT outcomes, with 811,435,879 returned JIT bodies.
UTS shares count writes; mutex shares count all operations. The
[verification receipt](evidence.json) preserves each run's counts, statuses,
arguments and manifest identities; [derived metrics](metrics.json) preserve the
strict comparison and processor-cost results.

The archive was copied to the source host, hash-verified and replayed there;
[replay results](archive-replay.json) match the guest's per-run audit exactly.
The [215 tracked-source checks](source-current-check.json) confirm that only the
runner guide changed after the measured snapshot. One additional archived file
is a pre-existing generated `daemon/0x.../asm/jit.S`, not a tracked source input.
The nine unrelated working-tree edits remain outside this benchmark commit.

[Host placement](host-environment.json) confirms all 64 physical pins. The
[final guest check](guest-final-state.json) found no project modules or active
benchmark; the [snapshot receipt](recovery-snapshot.txt) confirms recovery remained
available. Plotting ran after all timing in the separate analysis environment;
[dependency versions](plot-dependencies.json) and [generator commands](report-commands.json)
are recorded. Native/Stock instrumentation and UTS lock-scope limits are detailed
in the results document.

## Reproduction

Follow [operations](../../../../../../docs/operations/VM.md): edit on the source host,
synchronize into an idle guest, verify the exact kernel and physical pins, and
confirm a fresh recoverable snapshot. The benchmark Python environment is
`/root/kdlock-evidence/clobber-20260918/venv`. Run each command with an outer timeout
and a new output directory, without concurrent builds or other benchmarks.

```sh
export PATH=/root/kdlock-evidence/clobber-20260918/venv/bin:$PATH
export LC_ALL=C KDLOCK_RECOVERY_CONFIRMED=1
export KDLOCK_SNAPSHOT_TAG=YOUR_CONFIRMED_SNAPSHOT

python3 bench/real_api/run.py --kinds pipebytes --queries query \
  --entries 16 128 --threads 1 8 16 32 48 60 --repeats 3 \
  --backends stock native tclock kdlock \
  --output /root/kdlock-evidence/10.176.26.71/bench/pipebytes-new
python3 bench/real_api/run.py --kinds pipecap --queries query \
  --entries 16 --threads 1 8 16 32 48 60 --repeats 3 \
  --backends stock native tclock kdlock \
  --output /root/kdlock-evidence/10.176.26.71/bench/pipecap-new
python3 bench/real_api/run.py --kinds seek --queries set end \
  --entries 16 --threads 1 8 16 32 48 60 --repeats 3 \
  --backends stock native tclock kdlock \
  --output /root/kdlock-evidence/10.176.26.71/bench/seek-new
python3 bench/real_api/run.py --kinds utsname --queries host domain \
  --entries 20 --value-size 64 --threads 1 8 16 32 48 60 --repeats 3 \
  --backends stock native tclock kdlock \
  --output /root/kdlock-evidence/10.176.26.71/bench/uts-new
```

Defaults used here are `--warmup 48000 --warmup-ms 1000 --duration-ms 2000`.
Exact arguments, source manifests and binary manifests live with each run and
in the verification receipt. After timing, use the separate analysis environment
with Matplotlib 3.9.4 to generate each run's tables and figures:

```sh
python3 bench/real_api/report.py RUN_DIRECTORY --plots
```

TCLocks reference workloads were read from `/home/eric/TCLocks` at commit
`bbfb9f00a12af51dff6ca291cb9829a82960c2ef`. The inspected source hashes are:

| Path relative to TCLocks | SHA256 |
| --- | --- |
| `src/benchmarks/fxmark/src/MWRM.c` | `971f62e2d4f9a79099e735659cab768230e8a9e0297b45354b6393fd288e4642` |
| `src/benchmarks/will-it-scale/tests/mmap1.c` | `a7e09c6a7a12524a2cd949e5d37cf8ec0ba2479868cbd04ebd8c83c4eaed9d06` |

## Evidence locations

Guest originals are under `/root/kdlock-evidence/10.176.26.71/bench/real-sync-*`
and `tests/real-sync-20261011`. The ignored raw archive is mirrored on the physical
benchmark host and source host at
`bench/results/10.176.26.71/raw/bench/real-sync-20261011/`. It retains all pilots,
build failures, final sessions, source copies, ELFs, JIT images/disassembly,
commands, samples, kernel logs and drain records. Only compact reports and
receipts are tracked in Git.

The archive `real-sync-20261011.tar.gz` is **73,758,659 bytes** on both hosts.
Its SHA256 is
`68be68c2e0aa21169eaa57a6940cf3886a7bbf9c46e39cf65182c9c2d30aa59e`;
the [archive receipt](archive-sha256.json) records both locations. It also contains
the recovery helper binary whose hash matches the original cleanup note, the
[qualified cleanup interpretation](exploratory/manual-drain-interpretation.txt),
reference-source identities, and the scripts used for reports and validation.

To replay an extracted archive without loading any module:

```sh
python3 verify.py /path/to/extracted/bench > replay.json
python3 metrics.py /path/to/extracted/bench > metrics.json
```

The [verifier](verify.py) reads each run's frozen peak and report code. Older
pilot schemas lack some derived fields; these are recomputed from their raw
counts, without altering the records. Build failures, unequal-scope UTS pilots
and the failed drain session remain distinct from accepted final scores.
