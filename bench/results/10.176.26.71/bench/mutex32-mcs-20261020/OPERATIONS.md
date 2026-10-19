# Shared MCS node pool and bounded batching comparison

This is a collection plan, not a performance result. Root orchestration owns
all VM commands. Source edits and inert evidence review run on `380G10`;
builds, tests, modules and timing run only on `10.176.26.71`, following
[VM operations](../../../../../docs/operations/VM.md). Preserve every older
evidence tree and frozen source input.

The new external guest evidence root is
`/root/kdlock-evidence/10.176.26.71/bench/mutex32-mcs-20261020` (`RUN` below).
Confirm the real recovery snapshot, current idle state, kernel/boot identity,
64-vCPU topology, collector 63, host pinning and frequency policy before live
work. Retain `host-before.json` and `guest-before.log` there. A timeout does
not establish drain or authorize force unloading, clearing the guest checkout,
or editing running inputs.

## Balanced focused scope

| Arm | Frozen source | Role |
| --- | --- | --- |
| `baseline` | `826faa6` | Retained 32-byte implementation, production `76af844` |
| `candidate` | Concrete committed revision recorded before execution | Shared MCS node pool and longer bounded batch |
| `old256` | `0324e60d6791948e9762a9916a50e8e026f073b0` | Fresh historical 256-byte control |

Each source block runs the same three workloads, in this order:

| Collection | Workload | What the JIT counter establishes |
| --- | --- | --- |
| `synthetic` | c01, one cache line, 64 dependent post-work arithmetic rounds | Measured generated-body entry only; no returned-completion probe |
| `seek` | Real API SEEK_SET, 16 entries, value size 64 | Measured body entries and explicit matching returned completions |
| `pipe` | Real API pipebytes/query, 16 entries, value size 64 | Measured body entries and explicit matching returned completions |

Each workload uses eight and sixty workers, three repetitions, 2000 ms timed
duration, 300 ms peak window after 300 ms settling and 10 ms samples. Workers
use CPUs 0 through N−1; collector 63 remains separate. All workers warm up
for at least 48000 operations; API warmup additionally lasts at least 1000 ms.
NUMA is enabled, the configured batch limit is 1024, entry ratio is 2,
prefetch is 2, delegation is on and provider UBSAN is off. API helper settings
are four waves/eight workers; seek and pipe execute no helper learning waves.
The unchanged c01 post-work policy comes from its frozen workload source.

Total: **18 ordinary timings per source, 54 across the three sources**. There
are no new profiles, controlled placements, c08 runs or full worker grid.
Source blocks are sequential, not randomized pairs. Prior receipts suggest
roughly three minutes per source for collection including private builds;
preflight, source transitions and candidate checks add time. Every individual
collection subprocess has a 900-second bound, independent of this estimate.

Whole-run throughput is measured completed operations divided by the actual
timed wall interval. Medians and min/max ranges use the three matching repeats.
Peak windows remain separately reconstructed evidence. The summary keeps
source, workload, topology, caller shell, settings and execution class separate.
Synthetic `WITNESSED_JIT` never becomes API `RETURNED_JIT`. API `NO_JIT` and
`PARTIAL_JIT`, and mixed repetition classes, remain explicit; mixed groups have
no pooled median. A NORMAL image proves publication only.

Provider `jit_success / combiner` is retained per session and summarized per
matching cohort. This whole-session ratio includes warmup and checks; it is
not a measured-phase batch distribution. Exact owners, acquisitions, node
reservations, frames, source leases, ACKs, worker oracles and final drain remain
authoritative. Approximate heat/admission diagnostics never replace them.

## Collection and affected checks

Copy reviewed helper bytes outside the checkout while idle. The matrix driver
is frozen for all source arms. Synchronize each reviewed committed source only
after establishing idle. Commands run from `/root/host_fs/kdlock` with the pinned
translation environment and confirmed recovery variables:

```sh
python3 "$RUN/run-matrix.py" --version baseline --commit 826faa6 --base "$RUN"
python3 "$RUN/run-checks.py" --commit CANDIDATE_REV --output "$RUN/checks-candidate"
python3 "$RUN/run-matrix.py" --version candidate --commit CANDIDATE_REV --base "$RUN"
python3 "$RUN/run-matrix.py" --version old256 --commit 0324e60d6791948e9762a9916a50e8e026f073b0 --base "$RUN"
```

Actual receipts establish source-block order; changing order does not permit
pooling. Existing output directories are refused. Preserve every failed or
preliminary attempt under a new label/directory and an explicit archive group.
Such labels remain `comparison_arm=false` and are not silently substituted for
the named candidate. A future comparison of an additional candidate needs an
explicit analysis scope and its own checks.

The candidate check selection is two basic programs plus fifteen directly
affected drivers (**17 total**), including `mutex/test_mutex_osq.py` and all
fourteen drivers from the preceding cache-line round. The new OSQ fixture
checks actual encoded node reservation, cancellation, handoff and the local-spin
adapter. Existing state/resource/outer-progress fixtures cover borrowed-node
claims. Runner plan/report programs remain separate (currently 11/13 cases).
Ordinary mutex local, rwsem and instruction-exit live probes follow. No missing
dependency, skip or compile failure is a pass.

The source snapshot includes all `include`, `kernel_module`, daemon and
translator inputs; all unit/protocol/kernel-probe sources; benchmark
`spin_cacheline`, `tclock_compare`, and `real_api` imports; captured kernel
identity inputs and the `jit_escape` workload. Private `.inc`, headers,
assembly, fixtures and Makefiles are retained. This includes the execution
capacity fixture's `tests/kernel/execution` dependencies and all common unit
extraction helpers. The OSQ fixture needs only the existing C compiler and
userspace pthread support. The outer-progress fixture uses the already captured
guest kernel headers. Provider `W=1`, daemon `-Werror` and exact warning logs
remain part of the check receipts.

Changing to old256 requires reviewing/removing only source paths absent from
that exact Git tree. Sync does not remove stale files. Use path-specific hashes
and retain the removal receipt; do not reuse an older round's deletion list
without reviewing the current additions, including new node-pool inputs.

## Finalization and preservation

Restore the checked candidate while idle. Capture matching `host-after.json`.
With the default scope, finalization expects 54 ordinary sessions and the three
candidate live-probe logs, **57 kernel logs**. Extra retained attempts are also
scanned and kept visible; expected logs cannot be omitted. Run the bounded
analysis wrapper with stdout outside the evidence tree:

```sh
python3 "$RUN/run-finalize.py" --base "$RUN" --arms baseline candidate old256 \
  --check candidate=checks-candidate --current-arm candidate \
  > /tmp/mutex32-mcs-finalize.log 2>&1
python3 bench/archive_run.py --base "$RUN" --output "${RUN}-archives" \
  --health "$RUN/health.json" --group baseline=baseline --group candidate=candidate \
  --group old256=old256 --group checks_candidate=checks-candidate \
  > /tmp/mutex32-mcs-archive.log 2>&1
python3 "$RUN/export-compact.py" --base "$RUN" --archives "${RUN}-archives" \
  --output "${RUN}-compact" > /tmp/mutex32-mcs-export.log 2>&1
```

The wrapper bounds each analysis subprocess to 240 seconds and records exact
exit statuses. Archiving is separately bounded by root orchestration. Retain
the source snapshots, prepared provider copies, source/binary manifests, JIT
images, per-worker samples, kernel logs, command receipts and failures. Compact
export does not replace the raw archive. Do not modify archived metadata later
to disguise a failed first analysis; preserve that attempt and its refusal.

After copying archives and compact receipts to `380G10`, independent helpers
read archive bytes and Git objects without executing retained code:

```sh
python3 "$REPORT/offline-archive-review.py" --repo "$REPO" --raw "$RAW" --report "$REPORT" \
  --expect baseline=826faa6 --expect candidate=CANDIDATE_REV \
  --expect old256=0324e60d6791948e9762a9916a50e8e026f073b0
python3 "$REPORT/offline-statistics-review.py" --raw "$RAW" --report "$REPORT" \
  --arms baseline candidate old256
```

The arithmetic audit reconstructs all **54 ordinary windows**, including exact
worker counts and peak selection, entry/return semantics, session batch ratios
and three-repetition medians. The source/archive audit separately binds the
complete inventory and exact committed inputs. Additional preserved sources
need explicit `--extra-source DIRECTORY=REVISION` mappings. No performance
conclusion is valid until the collected results and their limitations are
reported; this plan supplies no prior guarantee of improvement or parity.
