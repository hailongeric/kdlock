# Unified queue infrastructure checkpoint

This is the Stage (b) infrastructure artifact on `codex/unified-lock-queue`.
It is an isolated candidate, with functional evidence for the connected paths.
General delegated killable capture, generalized nesting, the selected rwsem
writer/read-tail protocol and delegated mmap execution remain unfinished.
There is no performance acceptance or promotion to `master`.

## Source and environment

| Identity | Value |
| --- | --- |
| Production baseline | `7231ddf0963ff2cc730590c09cc81e7f96f93095` |
| Committed Stage (a) design | `81e2c674764eea877241021946062d53398f01f3` |
| Initial queue integration | `a9713a99` |
| Serialized batch entry | `531bbd74` |
| Preallocated cold-pool correction | `6277cb9d1fb0e90735850164893f0ee6b7fb0ad4` |
| Original frame/record sizes restored | `3e4549edd831a12ee8a160c3e01c62d35421fb71` |
| Final smoke source, including observation overlay | `8a83635de776bd6603c486937db86179d5c19341` |
| VM | `10.176.26.71`, `7.0.0-38-kdlock1` |
| Kernel Build ID | `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62` |
| Boot ID throughout | `b4c42511-d2fd-4ac7-b6b5-48650aae48b7` |
| Recovery snapshot verified on host | `kdlock-builddisk-clean-20261031` |
| Topology / frequency | 64 vCPUs, nodes 0–31 / 32–63, fixed 2 GHz, turbo disabled |

Source edits, Git and static inspection ran on `380G10`; every compilation,
unit driver, module, translator and workload ran in the VM. The normal kernel's
MM backend remains disabled. No enabled-MM kernel was built or booted here.
Fresh host captures accompany the final functional run. Final idle was checked
again before archiving; all attempt directories remain on the VM.

At reporting, `master` had independently advanced to
`20fde062729703208ac54445f51fc0f21f24e0e8` with the flags-stack work. This
candidate remains based on `7231ddf0963ff2cc730590c09cc81e7f96f93095`; it was
neither rebased onto that work nor merged into `master`. The retained source
manifests bind the receipts to this branch, not the newer `master`.

## Implemented scope

- The local sleeping mutex ring and captured delegation chain now publish into
  one guarded circular request queue. Publication has no delayed predecessor
  link. A captured head uses its existing membership for physical admission.
- Each request records immutable delegation permission, origin, submitter,
  wait mode and invocation generation. Guarded local selection prevents a
  request entering physical admission from also being dispatched by a combiner.
- The shared election attempts actual acquisition before the origin's signal.
  Selection cleanup, cancellation ACK, membership removal and request reuse are
  separate operations. Local signalable acquisition uses this election;
  delegated result-returning killable capture is still Stage (c).
- NUMA reordering retains pending nodes in the common queue. There is no
  private deferred topology. Mutex total/local limits remain 1024/1024.
- Rwsem phase and reader-drain conditions reuse the queue implementation with
  separate heads/predicates and one object guard. Prepared/unprepared writer
  ordering, positive cohorts, reader concurrency, downgrade and rollback retain
  their existing policies. Atomic release still avoids queue/scheduler locking.
- Cold records are preallocated in a dynamic per-CPU pool during initialization.
  No allocation was added to the lock path. Mutex size remains 32 bytes and
  captured packet size remains 320 bytes.
- Retained continuation/activation/owner-reference helpers are compiled but
  unenabled. Their pointer uses existing union space behind a discriminator;
  VM build assertions verify the original 656-byte execution frame and
  704-byte spin continuation, including the existing hot offsets.
- The generated local MM backend includes the common primitives and preserves
  its current local behavior. This is generation/compatibility evidence only.

The mutex optimistic OSQ and rwsem reader OSQ remain independent during this
migration. Rwlock keeps its existing physical/ABI3 queue adapter: changing only
its local header would leave competing acquisition topologies. Its joint
provider/local migration is explicitly pending. The four capture slots and
eight-entry legacy frame/owner limits are also still present. New helper
interfaces do not establish support beyond those boundaries.

## Focused validation and retained failures

| Attempt / source | Result |
| --- | --- |
| `local-a`, `531bbd74` | Provider and probe compiled. Loading rejected the 8560-byte static per-CPU section; no fixture ran. No modules remained. |
| `local-b`, `6277cb9d` | PASS: 160,000 operations, eight workers, 2048 reused objects, 32-byte layout, sleeping/nested owners, interruptible/killable cancellation while holder stayed locked, head/middle/tail cancellation, handoff, I/O/helpers and final drain. |
| `focused`, `6277cb9d` | Production queue model: 14 topology checks PASS. Writer model: 82 scenarios and 13 negative controls PASS. Public rwsem and generated-MM checks PASS. |
| `focused`, `6277cb9d` | Two fixture failures retained: generation negative control did not compile because it made a parameter unused; reader model referenced a removed source macro. Neither is recorded as a pass. |
| Live rwsem, `6277cb9d` | PASS: 17 API checks, ten cancellation checks, sleeping readers/writers, same-CPU progress, trylocks, downgrade, three publication checks and exact drain. Three scoped-signal cases also passed, including nonfatal persistence and fatal/interruptible cancellation. |
| `unit-recheck`, `3e4549ed` | Both repaired drivers PASS. Canonical head: eight topology checks plus all six negative controls. Reader admission: all 18 controls; reader count: 21 cases plus eight controls. Oracles and warning flags were retained. |
| `basic-a`, `3e4549ed` | Launcher affinity prevented topology discovery. No build/workload ran. |
| `basic-b`, `3e4549ed` | Dependencies, C basics and runner checks passed; observation overlay rejected stale include context before workload execution. |
| `basic-c`, `46534449` | Dependencies, C basics and runner checks passed; an unbalanced include hunk still failed exact patch application. No workload ran. |
| `basic-d`, `8a83635d` | Dependencies, C basics, runner checks, all four returned-JIT functional points and final idle PASS. |

The cold-pool correction addresses the first loading failure. The two unit
repairs change extraction/control syntax while preserving their assertions.
The observation patch keeps every probe and zero-fuzz application; the complete
overlay passed a static dry run before `basic-d`. Build/assembly diagnostics
remain in the retained logs.

The final smoke ran one functional round per family, 16 workers on CPUs 0–15,
100,000 iterations per worker, collector CPU 63. `c01` means one cacheline;
`c16` means sixteen cachelines. These are completion witnesses, not timing
scores or a Nano comparison.

| Family / workload | Operations | Returned JIT entries | Returned JIT completions | Data and drain |
| --- | ---: | ---: | ---: | --- |
| spin / c01 | 1,600,000 | 1,596,206 | 1,596,206 | PASS |
| public mutex / c01 | 1,600,000 | 1,596,128 | 1,596,128 | PASS |
| rwlock / c01, 20% writes, post4 | 1,600,000 | 17,225 | 17,225 | PASS |
| rwsem / c16, 100% writes, post4 | 1,600,000 | 1,594,539 | 1,594,539 | PASS |

Every final session hash was verified against the downloaded archive. The
same-NUMA points do not validate cross-NUMA policy, oversubscription, fairness,
depth-nine progress, all legacy extraction harnesses, or every retained helper.
No full Python inventory, Nano grid, syscall performance comparison or mmap1
run occurred. Keep receipts bound to their source versions; do not combine
these generations into a performance claim.

## Remaining delivery

Stage (c) must connect result-returning killable capture to actual rwsem
readiness and exact cancellation/retirement, including origin signals for
nested requests and independently retiring an executor's uncommitted request.
Stage (d) must replace positive reservation admission coherently, connect exact
writer/read-tail credits and fresh writer re-acquisition, and migrate nested
execution/resource consumers. The retained read tail is to execute on the
executor; ordinary read acquisitions remain local.

The old legacy continuation service still exists and is explicitly documented;
it is not proxy proof for the required MM path. New retained capture must not
use its slot-release-before-owner-ACK route. There is no claim that the current
killable mmap/munmap path delegates. Stage (e) still requires an enabled general
provider/context service, the new kernel/module build, actual unchanged mmap1
threads/processes, executor/read-tail/fresh-writer proof and comparisons.

## Evidence

[results.json](results.json) and [receipts](receipts/) retain individual outcomes;
[archives.json](archives.json), [archive-checks.json](archive-checks.json) and
[local-files.json](local-files.json) bind raw inputs, outputs and controllers.
The downloaded raw archive is gitignored at
`bench/results/10.176.26.71/raw/tests/unified-queue-20261102/vm-evidence.tar.xz`:
13,257,732 bytes, SHA256
`bcdb70cc8561abb238ba0a98a015e7acccb5d095dd1ea1e4f839706350a4e355`.
Offline inspection verified every source-manifest entry for both local
attempts and the live rwsem snapshot, including private queue/continuation
`.inc` files, and matched those bytes to their stated Git commits. All four
final smoke snapshots and the 111 production provider inputs per family also
match `8a83635de776bd6603c486937db86179d5c19341`. The VM archive and eight
original attempt directories remain.
