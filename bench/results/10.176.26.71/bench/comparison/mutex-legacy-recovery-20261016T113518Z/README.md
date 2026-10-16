# Recovered KD mutex legacy baseline, 2026-10-16

The historical KD mutex implementation associated with **5.330 Mops/s at
60 workers** has been recovered on branch `recovery/mutex-legacy-5m330`, in
`/tmp/kdlock-mutex-legacy-5m330` on source host `380G10`. A fresh three-round
`api-pipebytes-query-n16` comparison reaches **5.367 Mops/s**, 0.698% above
that historical median. The recovered provider retains the original Linux
mutex ownership, shadow MCS queue, live successor combining, bounded NUMA cohorts,
successor prefetch and pinned polling producer wait.

The owned/adaptive experiment was rejected by the user. Its exact tip remains
at tag `archive/owned-mutex-adaptive-a49a87c`, commit
`a49a87c38b22390b1924f51972c69bfb00bc908b`; no adaptive logic is part of this recovered
branch. The primary worktree `/home/eric/vm/vm-shared/kdlock` still contains that
experimental source and its **35 pre-existing edits**, all verified unchanged.
The separate worktree permits exact recovery without overwriting those edits.
Use the recovered worktree for subsequent legacy work.

## Source recovery

The [source proof](provenance.json) checks the original archive
`real-sync-20261011.tar.gz`, SHA256
`68be68c2e0aa21169eaa57a6940cf3886a7bbf9c46e39cf65182c9c2d30aa59e`,
and restores **all 215 captured source files byte for byte**. The additional
captured generated `daemon/0xffffffffc0c02f1b/39032/asm/jit.S` remains historical
evidence; new sessions generate their own JIT images.

| Component | Identity |
| --- | --- |
| Legacy provider, 51 code/build inputs | `e306412c55fe1e091f56c6bb5e34591bbb42e365` |
| API workload and runner code | `9bb0cb18df182886cd72b76c06d7d00cc5a3ebc3` |
| Captured direct-call header | `09bfffe` plus its full commit in [provenance](provenance.json) |
| Remaining checkout files outside the captured set | Recovered branch base `9bb0cb18df182886cd72b76c06d7d00cc5a3ebc3` |

The archive is authoritative for the measured inputs. Recovery is not a claim
that one historical commit contained the complete original dirty working tree.
The four archive differences from the base are the direct-call header formatting,
two pre-existing post-work fixture files, and the pre-publication API runner guide.
Those bytes are preserved. The uncaptured synthetic post-work inputs come from
the base commit; this receipt validates pipebytes, not a new synthetic matrix.

Builds used a new manifest-only guest copy of the recovered checkout. The copy
contains 764 tracked files and excludes obsolete files left in the synchronization
destination. The original benchmark observation overlay, caller ABI2, translator,
API adapter and header were built together. No owned mutex or adaptive objects
enter this build. The normal supported owner, ACK, source retirement and frame
checks remain in place. Source hashes were rechecked after all measurements.

## Fresh comparison

Whole-run median throughput is in **Mops/s**, three repetitions per point.
Higher is better. All **18/18 sessions** passed correctness, worker-progress,
affinity, peak-window and normal-drain checks.

| Workers | Linux Native | TCLock | Restored KD legacy |
| --- | ---: | ---: | ---: |
| 1 | 5.128 | 5.408 | 5.174 |
| 60 | 1.786 | 2.499 | **5.367** |

At 60 workers, the legacy rounds were **5.371261, 5.356040 and 5.367095 Mops/s**.
Its whole-run spread is **0.284%**. The highest valid warmed peak is
**5.393726 Mops/s**; the historical best peak was 5.360 Mops/s. The historical
whole-run median of **5.329886 Mops/s** is a reference from a different date and
is not pooled into the fresh statistics.

| 60-worker backend | Whole min | Whole median | Whole max | Whole spread | Peak min | Peak median | Best peak |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Native | 0.544 | 1.786 | 1.918 | 76.933% | 0.561 | 1.820 | 1.920 |
| TCLock | 1.905 | 2.499 | 2.537 | 25.308% | 2.411 | 2.516 | 2.553 |
| KD legacy | 5.356 | 5.367 | 5.371 | 0.284% | 5.381 | 5.385 | 5.394 |

The first Native round and first TCLock round were slower; both passed the same
acceptance checks and remain included. Native also had 34.946% whole-run spread
at one worker. These are three-round ranges, not confidence intervals, and no
cause is assigned to the control variability. The fresh 60-worker median ratios
are 3.005× Native and 2.148× TCLock; the variability limits how broadly those
ratios should be interpreted.

All three 60-worker KD sessions executed returned JIT bodies: **31,561,859**
bodies out of **32,213,760** operations, **97.976%** aggregate JIT share. All three
one-worker KD sessions were correctly classified `NO_JIT`. A published image
alone is not execution evidence. Throughput is not acquisition latency.

[Summary CSV](summary.csv), [summary JSON](summary.json),
[all individual samples](samples.csv), [generated comparison tables](benchmark-tables.md)
and [recomputed acceptance](verification.json) preserve the full statistics.

## Configuration and validation

Physical benchmark host: `10.176.26.71`. Exactly 64 guest vCPUs, pinned one to one
to physical CPUs; node 0 is 0–31 and node 1 is 32–63, 24 GiB total memory. Workers
use CPU 0 or CPUs 0–59; collector and QEMU service threads use CPU 63. The
[before/after placement check](host-consistency.json) confirms unchanged topology,
pins, QEMU process and host frequency policy (`ondemand`).

Kernel `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, with `nokaslr nopvspin`, native qspinlocks
and voluntary preemption. The [validation receipt](validation.json) confirms the
same boot and kernel identity before and after; no kernel rebuild, reboot,
topology change or snapshot restore occurred. The fresh recoverable snapshot is
`before-mutex-legacy-recovery-20261016T113518Z` ([monitor receipt](recovery-snapshot.txt)).

Timing matches the historical case: 2,000 ms per measurement, at least 48,000
warmup operations per worker and 1,000 ms warmup; valid peaks require at least
300 ms after 300 ms settling, 10 ms samples, and progress by every worker.
Backend order rotates across repetitions. Timed provider/replacement modules
have UBSAN disabled; the emitted TCLock context audit passed. No stock arm was
needed for this three-backend recovery comparison.

Two basic C programs and nine targeted drivers passed: mutex outer API,
resources, terminal path, task cache, outer progress, wait/clobber ABI, codegen
clobber ABI, API reporting and peak calculation. This is not the full project
suite. Initial preflight parsing expected square brackets around `voluntary`;
the actual kernel reports parentheses. An initial direct unit-driver invocation
also omitted the documented launcher import paths. Both invocation errors are
retained, corrected without changing production code, and followed by successful
checks. Neither ran a live benchmark or loaded a project module.

All syscall oracles, raw whole-run totals, full-cohort peaks, source/binary/JIT
hashes, worker affinity and exact KD retirement were replayed. The
[source-host replay](archive-replay.json) equals the guest audit. Final checks
found no project module or benchmark/daemon left running, no new kernel fault,
and exact zero modules/frames/writers after retirement. One pre-existing,
explicitly recorded userspace mutation-test trap remains in the old kernel log;
no new fault is ignored and no log was cleared.

## Reproduction and evidence

Use the recovered source worktree, follow [operations](../../../../../../docs/AGENTS.md),
verify a new recovery snapshot and synchronize while idle. Freeze only the
manifest-listed files into a new guest source directory before building.
The [recorded command](benchmark-command.json) used the pinned guest environment:

```sh
export PATH=/root/kdlock-evidence/clobber-20260918/venv/bin:$PATH
export LC_ALL=C KDLOCK_RECOVERY_CONFIRMED=1
export KDLOCK_SNAPSHOT_TAG=YOUR_CONFIRMED_SNAPSHOT
python3 bench/real_api/run.py --kinds pipebytes --queries query \
  --entries 16 --threads 1 60 --repeats 3 \
  --backends native tclock kdlock --output NEW_GUEST_OUTPUT_DIRECTORY
```

Only the guest executes builds and tests. The archived
`control/source-host/prepare-v2.py` and `control/source-host/run-guest.py` retain
exact input manifests and the frozen-copy procedure. `audit.py` is the original
historical per-session verifier with a single-run command-line entry point.
A source-host archive check was restarted as a streaming read to avoid repeated
gzip seeks; the final complete checksum and replay checks passed.

Raw guest evidence is under
`/root/kdlock-evidence/10.176.26.71/bench/mutex-legacy-recovery-20261016T113518Z`.
The archive is retained on both physical hosts at
`bench/results/10.176.26.71/raw/bench/mutex-legacy-recovery-20261016T113518Z/mutex-legacy-recovery-20261016T113518Z.tar.gz`:
**18,899,421 bytes**, SHA256
`cfa734b8670eee49d0f265d9f28310336026d525820970df73cf7b36b3028d6c`.
The [archive receipt](archive.json) verifies all 1,903 regular files and 12
symlinks against the sealed evidence manifest. Raw samples, all code/build/JIT
artifacts, source-host controls and failed invocation logs are preserved.
