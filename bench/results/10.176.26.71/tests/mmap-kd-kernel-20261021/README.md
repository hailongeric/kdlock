# Actual KD mmap-lock integration, 2026-10-21

Status: **IN PROGRESS — preparatory correctness checks passed; no new kernel
built or booted; no performance acceptance.**

The user confirmed that cleanup finished and instructed continuation of the
approved guest-kernel integration. Guest kernel source changes, a separate
build/install and experimental reboot are approved for this stage. Host-system
configuration changes are outside that approval. Only the main agent writes;
correctness tests precede timing and run serially.

## Starting evidence

- Clean source checkout: `443baa6` on `master`. Cleanup changed source/document
  organization and pre-October historical raw records; current VM results remain.
- A coordination hold was honored when another organization task appeared.
  The user then confirmed its completion and assigned this task the sole writer
  and VM-test slot. Commit `f90c26b` and its updated `AGENTS.md` were reviewed
  and preserved. A fresh guest observation found no project modules or runs.
  Correctness-only payloads now belong beside their runner under `payload/`.
- VM: `root@10.176.26.71:2222`, running `6.1.159-kdclobber2`, boot ID
  `b65f0205-c8f9-4385-8b13-039cbce243a6`. No project modules or workloads were
  present in the saved process/module observations.
- Recovery snapshot `before-mutex-kdonly-20261017T140354Z` was listed on all
  disks. The 64 vCPU pins and service-thread CPU 63 placement matched. The
  observation had **82 QEMU threads**, not the strict 67-thread timing profile;
  it is a recovery/preparation observation, not a timing preflight pass.
- Existing GRUB default names the recovery kernel. Root has approximately
  12 GiB available; the data disk approximately 5.7 GiB. The existing 20 GiB
  kernel source/build tree must remain intact.
- Raw read-only receipts:
  `raw/tests/mmap-kd-kernel-20261021/preflight/{guest,host}.json` under the
  machine result root. A later broad disk-size query hit its bounded timeout;
  no build or workload was running and no pass was assigned to that query.

## Scope and gates

The implementation plan is actual-object KD-local integration: concurrent
readers, original-task writers, exact owner and release-mode handling, and
explicit deferred read-transfer lifetime. Arbitrary MM-body delegation remains
unsupported. All per-mm participants must use one immutable protocol, including
fork/exit, remote observers, fault retry and teardown. Native control, KD-local
and any future admitted delegated cases must have distinct result labels.

Required before timing: basic checks; focused read/write exclusion and
concurrency; failed trylock and fatal-signal cancellation; downgrade and nested
old/new mm; untouched mapping lifecycle; page faults including retry and VMA
revalidation; remote-mm access; exact deferred read release; and drained teardown.
Missing dependencies, skips and failed builds are unresolved checks.

The previous shared-mm Native timing, its endpoint topology failure, and all
seven mutex regression causes remain separate and unresolved. This stage does
not overwrite those results or declare whole-kernel, RT or lockdep acceptance.

## Preparatory refactor validation

The physical mutex/rwsem types now have standalone headers with unchanged
layout. Mutex initialization moved to the existing physical implementation
object. No owner, queue, cancellation, ACK, frame or instruction-admission
decision changed. Existing extraction fixtures now read the moved definitions.

| Run | Result | Evidence |
| --- | --- | --- |
| `refactor-1` | Provider W=1 build, daemon warnings-as-errors build, two basic C programs and six affected drivers passed; 8 run targets, zero failures; frozen input hashes unchanged | [receipt](refactor-1.json) |
| `rwsem-refactor-1` | 8 API checks, 10 cancellation checks, 1 downgrade check, 3 publication checks; sleeping local/outer-reader scenarios and same-CPU progress passed; zero errors, all workers joined, normal module unload and drain | [receipt](rwsem-refactor-1.json) |

Both runs used the unchanged recovery kernel and pinned Python environment,
serially. They validate the preparatory refactor, not actual mmap integration or
returned JIT bodies. The live rwsem probe explicitly reports zero JIT bodies.

Recovery preservation copied 11 boot/configuration files and recorded hashes for
5,686 installed module/metadata files. Originals, the recovery default and the
source/build tree remain untouched. The completed four-group archive was copied
to `raw/tests/mmap-kd-kernel-20261021/refactor-archives-1/`. Its manifest SHA-256
and offline review scope are recorded in the [archive receipt](refactor-archive-review.json).

The adapter draft uses an immutable per-mm Native/KD choice and retains local
readers and original-task writers. BPF deferred read release transfers a unique
record plus an mm-count reference; final destruction is deferred to process
context. For a KD mm, IRQ-disabled read trylock fails before reservation so BPF
uses its existing lookup-failure fallback: speculative reader rollback could
otherwise wake a writer while the caller holds a scheduler lock. This restriction
must receive a focused negative check; it does not switch the mm to Native.
