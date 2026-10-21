# Actual KD mmap-lock integration, 2026-10-21

Status: **FOCUSED CORRECTNESS COMPLETE — Native-control and KD-local basic,
API, untouched mmap, separate fault-retry and file-write fault-completion checks
passed. No timing or performance acceptance.**

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
received the focused negative check in the API runs below; it does not switch
the mm to Native.

## Separate experimental kernel

Synchronization completed after the user-authorized retry. The two earlier
automatic approval reviews expired before execution; neither started a sync.
The successful attempt verified all 3,872 tracked source hashes and copied 15
changed files without deleting project files.

Guest preparation `candidate-1` reconstructed Linux 6.1.159 from the pinned
upstream archive (SHA-256
`1f207ebe93980829ecc0a18b694816f22b715e9893767731651969a168342b9e`) and the
preserved ancestor patches. The nine integration base files exactly matched the
recovery tree. The only configuration differences are `CONFIG_KD_MMAP_LOCK=y`
and `CONFIG_LOCALVERSION="-kdmm1"`; the recovery configuration remained unchanged.

Image build `build-1` completed in the guest with 16 compiler jobs. This is one
build, with no concurrent test or timing run. Its prepared source hashes and
configuration remained unchanged. The `6.1.159-kdmm1` image SHA-256 is
`cb82b0d1ccf3c2b5ce27571783fa2001d7b971d8f36ff1316c114972ff354f0d`.
Guest receipts and logs are under
`/root/kdlock-kernel-work/mmap-20261021/candidate-1/` (`prepare.json`,
`build-1.json`, `build-1.log`). This build result is not a live correctness pass.

The next stage rebuilds modules from the same source/configuration for the
current guest's boot and loaded-module set. Storage does not permit assuming
that every configured module can be rebuilt alongside the preserved recovery
tree. Coverage and any omitted modules must be recorded before installation.
The focused actual-mm probe covers local readers, exact writer identity,
killable cancellation, nested mm locks, downgrade, IRQ-disabled try refusal,
unique deferred read transfer and last-reference destruction in process context.
Its build and live results are recorded below; syscall/fault coverage remains a
separate gate.

Module build `modules-build-1` failed with two `serio_raw` modpost errors. Its
overlapping parent/child target traversal compiled `serio_raw.o` twice; the
second command omitted `-DMODULE`, producing built-in metadata and a non-module
preemption reference. `modules-build-2` separated that target, retained all
license/symbol checks, and built all **73** currently loaded modules plus their
complete recorded dependency closure. Both symbol tables were merged only
after duplicate symbol records matched exactly. No recovery symbol table or
module was reused. The other **1,440** modules from the old initramfs were not
built; all-configured-module coverage remains unresolved.

The image build retained 22 fortify compiler-diagnostic warnings, three objtool
warnings in existing x86 code and locale warnings. The successful build exit is
not a claim that those diagnostics passed. The original configuration and all
warnings remain in `build-1.log` for comparison.

The separate kernel bundle `/root/kdlock-kernel-baselines/mmap-kdmm1-20261021`
verified 44 source files, 11 build files and 5 bundle inputs. Its Build ID is
`687ff5a29315d732f93a618e50ac407c794bbf9b`; version is
`#1 SMP PREEMPT_DYNAMIC Wed Oct 21 07:25:49 UTC 2026`.
`probe-build-1` compiled the actual-mm API probe with `W=1`; its SHA-256 is
`ce6738870ff6235d97a963841f52cf042082c6ad83d3898b69fc5f62e501ae17`.
That build-only artifact was not loaded. Later live API, syscall and fault
checks use the separately hashed binaries recorded below.

Installation `install-1` passed with all 73 modules freshly signed for this
kernel. Recovery boot artifacts, installed modules and the default entry remained
unchanged; only new boot files, a distinct module directory and experimental
menu entries were added. A one-shot Native-control boot matched the new Build
ID, `kd_mmap=off`, `nokaslr`, and `nopvspin`; boot ID is
`a6773b93-8537-4816-a7af-84dca50c85a4`. Boot logs include floppy-device I/O errors;
they are retained, not described as a clean boot log.

`native-api-1` failed before loading the probe: its frozen source selection
omitted `daemon/daemon.c`, required by the second basic C program. The follow-up
runner includes the daemon's source and private fragments; no test was removed.
The probe also explicitly checks that the calling userspace process's actual
mm uses the requested mode. The follow-up is a new run, not a rewrite of this
failed attempt.

## Native-control correctness on the experimental kernel

| Run | Result |
| --- | --- |
| `native-api-2` | Two basic programs passed; 121 API assertions, zero errors; concurrent readers, sleeping writer, three killable cancellations, nested locks, downgrade, IRQ case, exact read transfer and final asynchronous destruction passed; normal unload and drain |
| `native-faults-1` | Sixteen fork/COW/remote-read/remote-write/exit cases plus sixteen userfault retries passed; each unresolved fault allowed a real mmap writer to split its VMA before completion; all children and fault threads joined |
| `native-mapping-1` | All six untouched mapping cases passed; 81,000 cycles, zero payload faults; exact new-ELF writer chain and nine corrupted-proof rejections; no file, VMA or mm reference remained |

The writer chain is bound to the copied and hashed `kdmm1` ELF. It retains
exact shared-mm/TID identity, a blocked `D` state, matching wait channels and
unchanged scheduler counters around the observation. Its first frames differ
from the recovery kernel because the integration adapter is visible. The old
recovery verifier remains the default for its unchanged six-argument client
interface; the experimental runner supplies an explicit exact-chain verifier.
No admission or ownership check was removed.

Page-fault cases and untouched mapping cases are separate tasks and evidence
directories. At this stage, `VM_FAULT_COMPLETED` was still pending; the final
checks below close that focused gap. All filesystem/device fault callbacks and
all-configured-module coverage remain unvalidated. These preliminary results
alone did not permit timing or acceptance of KD-local integration.

The first Native archive passed 3,050 offline checks over 1,517 members in six
groups. Its health receipt identified five previously loaded modules absent
after reboot. All five had been rebuilt; `native-runtime-restore-1` loaded them
and verified the exact original 73-module set and voluntary preemption. Serial
follow-ups `native-api-3`, `native-faults-2` and `native-mapping-2` all passed with
the same case counts. These matched-runtime controls are distinct from the
preliminary Native runs. Their six-group archive passed 3,818 checks over
1,901 members; see [archive review](native-archive-2-review.json).

## KD-local correctness

The one-shot KD boot has ID `c111299d-6442-4d09-bd06-e2677c33fe46`, the same
`kdmm1` Build ID and explicit `kd_mmap=on`. `kd-runtime-restore-1` restored and
verified the same 73 modules and voluntary preemption before testing.

- `kd-api-1`: two basic programs and **139 assertions** passed, zero errors;
  all API, queue, cancellation, downgrade, nesting, transfer and destruction
  cases passed. The calling process and allocated real mm objects used KD.
- `kd-faults-1`: all 16 fork/COW/remote/exit cases and 16 userfault retry/VMA-split
  cases passed; all children and fault threads joined.
- `kd-mapping-1`: all six cases and **81,000 cycles** passed with zero payload
  faults, the exact KD writer chain, nine corrupt-proof rejections and complete
  file/VMA/mm teardown.
- `kd-completed-1`: **64 entries, 64 returns and 64 VM_FAULT_COMPLETED results**
  for the exact selected mm/task/range; zero retries, errors or missed probes.
  The real mmap write lock was reacquired, all persisted file bytes matched,
  and the observer and module drained normally.

All runs were serial, without delegated readers, MM-body delegation or TCLock.
The post-check host observation returned to **67 QEMU threads**, with the same
64 vCPU threads and three service threads on CPU 63. No host setting changed.
This observation alone is not a timing preflight or endpoint acceptance.

## Final correctness disposition

The matching `native-completed-1` passed after the one-shot Native-control boot
`cc9b563e-1761-48d0-8d9c-c2958a500578` and `native-runtime-restore-2` verified
the original 73-module set and voluntary preemption. It recorded **64 entries,
64 returns and 64 genuine VM_FAULT_COMPLETED results**, with zero retries,
errors or missed probes, successful write-lock reacquisition, exact persisted
file data and normal teardown. See the [Native receipt](native-completed-1.json)
and [KD receipt](kd-completed-1.json).

`legacy-validator-1` also passed in the VM: the current default recovery-kernel
writer verifier accepted the original frozen positive data and rejected all
seven original corrupted variants. This is a validator replay, not a new live
baseline. Its [receipt](legacy-validator-1.json) binds the exact input and
validator hashes. The experimental verifier's separate nine negative cases
remain required; no admission, ownership or proof check was removed.

The [final health receipt](correctness-final-health.json) records idle, matching
runtime modules, no matches for the retained kernel-fault patterns, unchanged
recovery boot artifacts and all **5,686** recovery module/metadata hashes.
The floppy-device I/O errors remain in the full boot log. Recovery remains the
default kernel. No source, module, daemon or test was active at archival time.

The complete six-group archive is under
`raw/tests/mmap-kd-kernel-20261021/correctness-archives-1/` in this machine's
result root and
`/root/kdlock-evidence/10.176.26.71/tests/mmap-kd-kernel-20261021-correctness-archives-1/`
in the VM. Manifest SHA-256 is
`3733a6e7f3ec2b3f02474cad22d408360e36137771f017941c5f6e110582c69e`.
The [offline archive review](correctness-archive-review.json) passed **4,842
checks over 2,412 members**: archive lengths/hashes, safe disjoint member names,
the complete recorded inventory and final health hash. It executed no archived
code. Earlier failures, revisions and preliminary runs remain in this archive.

This completes the selected actual-object mmap-lock correctness stage in both
modes. It does not validate arbitrary MM-body delegation, every filesystem or
device fault callback, the 1,440 unbuilt historical initramfs modules, RT,
ww_mutex, lockdep, oversubscription redesign or whole-kernel replacement.
Readers remain concurrent and local; all writers execute on the original task;
no returned JIT body or TCLock MM support is claimed.

All seven original mutex regressions remain **UNRESOLVED_CAUSE**. Their next
follow-up must use the preserved recovery kernel and original frozen binaries,
record the newly authorized reboot separately, retain exact host/policy checks
and keep new measurements apart from earlier boot identities. No experimental
kernel timing is mixed with that investigation. The [final status](final-status.json)
records these limits; overall acceptance remains open.
