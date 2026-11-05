# Default-off syscall argument selection: focused checks

Candidate `4506f6e46394133e439f68a04d6fde38aea0885f` implements the documented
benchmark-only argument envelope before public rwsem capture. Its default is
off. Excluded requests use the existing callable local KD API on the same
bound object; no MM backend, public lock API, nested-service admission, queue,
ownership, downgrade or JIT instruction handling changed.

The warning-frontier proposal remains unchanged and awaiting review. These
checks do not establish mmap1 delegation or a performance gain. No translator
was started, no image was published and both root entries stayed UNINIT with
code/generation zero. `master` was not changed.

## Build and component checks

All builds and checks ran in the VM from immutable
`/root/kdlock-inputs/shape-4506f6e4`. The provider built with `W=1`, NUMA enabled,
1024-body batching and 128 image slots. The unchanged daemon rebuilt with
`-O2 -Wall -Wextra -Werror` and retained its previous binary hash.

- 55 Python cases passed across demand selection (11), mmap1 contracts (22),
  delegated validators (9), image retirement (4), and campaign control (9).
- The compiled rwsem facade/routing, typed release, downgrade and ABI2 checks
  passed. The production predicate component covered exact/near-miss tuples,
  both fd representations, native64/compatibility/kernel contexts, default-off
  behavior, local signal-return routing and unsupported-MM configuration.
- Provider SHA256:
  `a9e121b1dfae464e3199b8d6cec07d7539f3aedac62d31a3affd680b1b629f65`.
- Daemon SHA256:
  `9a80d79d1c43d7c1be8a27fdc2bd2cfd0c278ba76c855e581a85a0ad962bf413`.

Receipts bind `syscall_shape={version:1, enabled:...}`, both getter parameters,
entry selection and the provider hash. A missing/mismatched policy or version
is refused. The live readback confirmed the default is disabled and both
parameters are immutable after load.

## Actual syscall cases

The matched kernel was `7.0.0-38-kdscope5`, Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`, `kd_mmap=on`, boot
`592cb3aa-5bd9-45ab-8852-7ca4544b1779`. A short userspace fixture invoked real
mmap/munmap, checked returned mappings and data, and paused outside each syscall
for registry observations. All six checkpoints passed.

| Checkpoint | Registered roots with the filter enabled |
| --- | --- |
| program startup | none |
| anonymous 64 MiB mmap/munmap | none |
| file-backed 128 MiB mmap | none |
| file-backed 128 MiB munmap | munmap only |
| anonymous 128 MiB mmap | mmap and munmap |
| anonymous 128 MiB munmap | mmap and munmap |

Thus unrelated startup and file-backed mmap were excluded from capture and
registration. The file-backed unmap case deliberately demonstrates the limit:
address/length does not prove mapping type or pairing. Both selected entries
were registered by the fixture task and remained UNINIT. Registration proves
eligibility here, not a queued/delegated request or returned JIT body.

The retained unchanged upstream `tests/mmap1.c`, SHA256
`a7e09c6a7a12524a2cd949e5d37cf8ec0ba2479868cbd04ebd8c83c4eaed9d06`, uses the
same anonymous-private 128 MiB read/write tuple with fd -1 and offset zero.
Its exact returned address is passed to munmap. This source evidence does not
turn the stateless predicate into a pairing check.

## Focused unchanged mmap1 API checks

One unscored two-worker lifetime each ran `mmap1_threads` and
`mmap1_processes`, using the unchanged prepared binaries and the existing
identity observer with syscall-pair logging disabled. Both completed and
drained. Existing validation joined exact task lifetimes, CPU placement and
MM/lock identity: threads shared one MM/lock; processes had two distinct
MM/locks. Every observed worker used the same bound KD provider, route 2.

The selected entries had no images, so these bodies executed locally. This
validates the actual API and provider binding under the new selection mode;
it does not validate mixed local/delegated execution or the pending warning
frontier. Raw program output is retained as unscored diagnostic data, never a
Native/KD comparison. No cold 32-run learning campaign or live profiling ran.

## Retention and final state

The first host capture failed its QEMU task-stability check before any guest
module/application action. Its error is retained. A fresh capture passed;
the functional check ran once.

All children exited normally, observer STOP was idempotent with balanced MM
references, both observers unloaded normally, and kernel collection completed
without a detected fault. At controller exit three bindings remained; the
fresh finalizer later observed zero without needing the optional CPU-progress
step. Exact retirement returned `state=2, modules=0, frames=0, writers=0`;
ordinary provider unload and final idle passed. The original result hash stayed
`802ea9c2689ea4f0c45e39342bea0cd380a221ab158291671a60ca75c4423001`.

Normal `7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, was restored and verified idle on
boot `1ed38b4b-301c-4c76-a2a1-eb4b9f1bd93e`, with no pending GRUB entry.

`functional-as-run.py` is the successful helper. Review found a failure-path
custody gap after insmod and before readback; actual readbacks succeeded, so
that path was not taken. `functional-next.py` records the corrected custody
ordering for future reuse and was statically reviewed only, not rerun.
All outcomes, snapshots, logs, source identity and hashes remain separate.
