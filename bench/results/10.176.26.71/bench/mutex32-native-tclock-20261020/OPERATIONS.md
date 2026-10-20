# Fresh Native, TCLock and 32-byte KD mutex comparison

This is a collection plan. It supplies no performance conclusion. Root owns VM
commands and Git; source edits and inert audits run on `380G10`. Follow
[VM operations](../../../../../docs/operations/VM.md). Confirm the real recovery
snapshot, an idle guest, kernel and boot identity, 64-vCPU topology, CPU pinning
and host frequency policy before live work. Record host-before/after snapshots.
Initial guest preflight was observed in tool output; persisted guest runtime
receipts are guest-during.log and guest-after.log. Do not label the later
capture as an initial preflight record.
Never edit frozen running inputs or interpret a timeout as proof of drain.

The external guest root (`RUN`) is
`/root/kdlock-evidence/10.176.26.71/bench/mutex32-native-tclock-20261020`.
The maintained production is the shared-node, bounded-locality implementation
from `752fec1`. Record the exact later documentation/helper commit passed to
both collectors; each collection freezes actual source hashes, including private
`.inc` inputs. All three backends are built fresh from that one source tree.

## Scope and interpretation

Seven separate collections contain **81 sessions each, 567 total**: Native,
TCLock and KD × workers 1, 2, 4, 8, 16, 32, 36, 48, 60 × three repeats. Every session is
plain, 2000 ms, collector CPU 63, workers 0 through N−1, 300 ms peak window after
300 ms settling with 10 ms samples. All workers warm up for 48000 operations;
API warmup also lasts at least 1000 ms. There are no profiles or full-grid runs.

| Collection | Workload | KD evidence |
| --- | --- | --- |
| c01 | One cache line plus 64 dependent post-unlock arithmetic rounds | Generated-body entry only |
| c08 | Eight cache lines plus 64 dependent post-unlock arithmetic rounds | Generated-body entry only |
| rcuht | 1024 buckets, 4096 preallocated nodes, 8192 keys, 100% writes | Generated-body entry only |
| seek-set | Real API SEEK_SET, n16/value64 | Entries and matching returned completions |
| seek-end | Real API SEEK_END, n16/value64 | Entries and matching returned completions |
| pipebytes | Real API pipe byte-count query, n16/value64 | Entries and matching returned completions |
| pipecap | Real API pipe capacity query, n16/value64 | Entries and matching returned completions |

RCUHT uses immediate unlink/relink, fixed CPU-seeded streams, no timed allocation
or RCU service, and timed arithmetic outside the lock. It is the repository's
adaptation, not byte-identical upstream RCUHT. The name does not add RCU to KD.
TCLock uses its actual ordinary mutex backend; Native uses Linux mutex. The API
substitutions protect private objects under one consistent protocol; they do not
validate whole-kernel replacement. The configured KD/TCLock batch limit is 1024,
NUMA on, KD prefetch 2, entry ratio 2, delegation on and provider UBSAN off.

Workload blocks are sequential. Within each synthetic worker/repeat the existing
runner reverses backend order on odd repeats; API rotates order across repeats.
Do not pool different workload, source, caller, placement or instrumentation
identities. Whole-run throughput uses completed operations divided by actual
wall time; peak windows are separate reconstructed evidence. Group medians and
min/max ranges require three repeats of the same execution class. Preserve raw
per-worker progress and final-drain evidence.

No `--require-jit` is used. API PASS/RETURNED_JIT, PARTIAL_JIT and NO_JIT remain
separate; Native/TCLock are NOT_APPLICABLE. Synthetic WITNESSED_JIT means entry
only, never a returned-body claim. A NORMAL image establishes publication only.
A synthetic contended NO_JIT retains the runner's original failure verdict and
nonzero exit, is excluded from accepted timing scores, and can be collected only
when its complete data oracle and final drain pass. `matrix.passed` means all
expected sessions were collected safely with their explicit verdicts; it does
not turn these NO_JIT rejections into JIT or timing passes. Any other failure or
uncertain drain stops collection. Low-contention NO_JIT accepted by the original
runner remains a separate local-execution timing class.

Expected elapsed collection time is roughly 45–65 minutes, including warmup,
builds and teardown; measured time alone is 18.9 minutes. Each workload subprocess
has an 1800-second hard bound; the driver stops at an idle boundary if fewer than
1800 seconds remain of its 9000-second total budget. A timed-out worker is retained
for diagnosis, never automatically force-unloaded.

## Commands

Copy reviewed helper bytes to `RUN` while idle, synchronize the exact committed
source, activate the pinned translation environment and set confirmed recovery
variables. Root's basic/affected helper runs two basic programs, provider/daemon
builds, dependency checks, and four benchmark test programs. No old protocol
check or live-probe pass is represented as a fresh check in this round.

```sh
python3 "$RUN/run-checks.py" --commit EXACT_REV --output "$RUN/checks"
python3 "$RUN/run-matrix.py" --commit EXACT_REV --base "$RUN"
```

The seven workload command logs and receipts, current/matrix.json, per-session
JSON, raw samples, kernel logs, source snapshots and built/JIT binary manifests
are all retained. Existing output directories are refused. Any failed collection
requires a separately named preserved attempt and explicit analysis scope;
never overwrite or silently substitute its records.

## Finalization and preservation

After completed collection and confirmed idle, capture host-after.json. The
finalizer must validate all 567 session logs, exact source/command scope, current
production identity and fresh checks; no live-probe logs are expected. It keeps
entry-only, returned and local-execution groups separate. Whole-session provider
`jit_success / combiner` includes warmup/checks and is a diagnostic ratio, not a
measured-phase batch distribution. The mutex TCLock backend records measured
delegation counts; keep these separate from KD generated-body entries and returned-completion probes.

```sh
python3 "$RUN/run-finalize.py" --base "$RUN" > /tmp/mutex32-native-tclock-finalize.log 2>&1
python3 bench/archive_run.py --base "$RUN" --output "${RUN}-archives" \
  --health "$RUN/health.json" --group current=current --group checks=checks \
  > /tmp/mutex32-native-tclock-archive.log 2>&1
python3 "$RUN/export-compact.py" --base "$RUN" --archives "${RUN}-archives" \
  --output "${RUN}-compact" > /tmp/mutex32-native-tclock-export.log 2>&1
```

Root bounds finalization and archive commands. Keep stdout outside the evidence
tree, as the archive idle guard rejects writable descriptors into that tree.
Raw grouped archives remain authoritative; compact export retains reviewable
receipts without duplicating source trees or sample arrays. After transfer to
380G10, independently audit archive/source bindings and arithmetic without
executing retained code. Preserve original failed audit receipts if an analysis
helper needs a correction; helper failure is not silently a workload failure.
