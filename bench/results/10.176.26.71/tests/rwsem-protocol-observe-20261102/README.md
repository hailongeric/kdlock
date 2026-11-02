# General rwsem protocol: design and API observation checkpoint

Stage 1 design and baseline API observation passed. **Forced delegated MM
execution is not implemented or validated.** This is neither a throughput
comparison nor candidate acceptance. Every capture has `proxy_proof=false`.

The [design](../../../../../docs/design/rwsem_delegated_protocol.md) explicitly
allows a delegated writer's downgraded read tail to continue on its executor
for all equivalent callers. Ordinary direct reads remain local. This
supersedes the earlier request to return to origin at downgrade; production
source still implements the previous local-only MM protocol.

## Source and runtime identities

- Branch: `codex/rwsem-delegated-protocol-20261102`.
- Source baseline: `7231ddf0963ff2cc730590c09cc81e7f96f93095`.
- Revised read-tail design: `1f1c72c0394e4a30e7b127545dd8842176136986`.
- Instrumentation: `838398edd9b29975713d29a9f16ea4069ee8cd76`.
- Validated source: `bbb79781e85305cf3881f21108d11d4bf063af7e`.
- Production lock/MM sources are unchanged from the baseline. Master was not
  modified or promoted.
- Existing kernel: `7.0.0-38-kdscope4`, `kd_mmap=on`, Build ID
  `a3bd8cda22af4c668b952472822188c6f3708440`.
- Schema-2 bundle: `/root/kdlock-kernel-baselines/linux70-kdscope4-kd-20261101`,
  manifest SHA256 `5bb0fcbd453f307ae159746da133163247538acf7d3f152fa05ceeb53a633957`.
- Observation boot: `4b1e10f4-108b-45bd-806f-13d6f2a4d04c`.
- Observer module SHA256:
  `95bb849c6903d913027f9287e04a47c40205bb3947266f1d1ce0fd0561502a3a`.

All source edits/Git ran on 380G10. Builds, fixtures, modules and application
runs ran only in the designated VM. Its actual recovery snapshot
`kdlock-builddisk-clean-20261031` was listed before live work. The guest had
64 vCPUs, NUMA nodes 0..31 and 32..63; workload workers used 0..N-1 and collector
63. Fixed 2 GHz/no-turbo policy and pins were captured. This diagnostic did not
activate the strict timing campaign's stable auxiliary task pool. No performance
qualification or no-regression verdict follows from these functional results.

## Checks and observations

The observer external module built with `W=1`; fourteen decoder fixtures passed.
Fresh actual-MM API/cancellation/downgrade checks passed, followed by fresh
thread/process mmap1 identity checks on the same boot. The existing kernel
remains a local implementation: those API receipts explicitly report
`delegated=false`, `jit_bodies=0`, `accepted=false`.

Unchanged will-it-scale source was pinned at
`75f66e45697e6f5f49c33dd950c4e6b289198f8f` and existing preparation input SHA256
`beeb3e82481b881ba09d77667408f29fc37366b7fe5d987f3fd02af0c5ac4dc0`.
Thread executable SHA256:
`e6a8102ff408e0a3909248fef301a41b0b0bd07861662002e4e13833534f59c6`;
process executable SHA256:
`6ec2ac78249dd13ad201faa0a2708e176f9628d2b537d69d5ff8d584004da733`.
Each diagnostic case ran once with `-t N -s 2 -m` and completed the original
application's six warmup/two post-marker samples. Original stdout and parsed
values are retained; they are not presented as a scored performance comparison.

| Model | Workers | Events | Killable writer calls | Downgrades | Write releases | Read releases |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| threads | 1 | 17,896 | 3,579 | 1,789 | 1,790 | 1,790 |
| threads | 2 | 18,066 | 3,613 | 1,807 | 1,806 | 1,807 |
| processes | 1 | 20,178 | 4,035 | 2,018 | 2,018 | 2,018 |
| processes | 2 | 32,064 | 6,413 | 3,206 | 3,206 | 3,207 |

Total: 88,204 events, 44,102 complete API invocation/return pairs. Every capture
had zero missed probes, overflow, retained invocation and event errors. Every
application completed and drained; modules unloaded normally. This proves the
generic observer works on the existing backend, not that bodies ran remotely.

The observer accepts exact symbols and TIDs, with no application filter. These
cases selected the existing `kd_mmap_` symbol namespace as diagnostic input.
It records CLOCK_MONOTONIC events with exact task-lifetime and pairing IDs.
Requested entry admission was 10 ms; actual admission windows were about
10.05..10.11 ms. Cutoff and final probe stop are distinct: unregister/drain
extended total capture lifetimes to about 139..153 ms. Full API pairs do not
imply complete protected-body intervals: unmatched boundary bodies and
cross-cutoff intervals remain labeled in [result.json](result.json).

Body intervals are delimited by successful acquire return and release/downgrade
invocation; downgrade return starts the read interval. These are API boundaries,
not exact physical ownership transitions. There is no per-worker runtime
denominator, request/executor identity, delegated credit ledger or returned-body
witness. Delegation episodes/length and critical-section ratio are therefore
unset, rather than estimated from these events.

## Failures retained and fixes

1. `check-r2` at `ba82a657` failed compilation: Linux 7 has no `no_llseek`.
   `bc5bab5023158ab04ad582f93fee9868ccb285d6` leaves `.llseek` unset, preserving
   sequential reads while VFS refuses seek. No module or workload ran in the
   failed attempt. Fresh `check-r3` and final `check-r4` builds/fixtures passed.
2. The first identity prerequisite copied an old generated
   `kd_mmap1_identity.mod.c` into frozen source. Kbuild regenerated it and the
   unchanged-input check correctly failed before application execution.
   `bbb79781e85305cf3881f21108d11d4bf063af7e` excludes `*.mod.c` and retains
   private `.inc` inputs. Fresh identity checks passed; all original hash and
   runtime oracles remain active. The preceding successful API checks were
   retained and reused on the same boot rather than relabeled as rerun.

A source-host controller quoting error before the first VM invocation is also
retained. It was neither a VM build nor a workload failure.

## Remaining protocol work

The new read-tail policy is a design, not a switch in the current implementation:

| Current gap, verified at the validated source | Consequence / required change |
| --- | --- |
| `include/kd_rwsem_api.h:17` captures only void writer continuation; `kernel_module/kd_rwsem_api.c:31` implements that entry. | Killable entry needs complete result/cancellation capture. A committed proxy entry must explicitly define success EAX; cancellation must publish no body. |
| `kernel_module/kd_rwsem.c:392,411` reserves a positive cohort and drains before publication; `:334` downgrade requires the local -1 phase. | Separate queued reservations from selected writer phases, drain for each selected writer, and publish an exact delegated read share before reopening shared admission. |
| `include/kd_rwsem_api.h:36` ends at mutex unlock and origin phase retirement; `execution/lock_ledger.inc:219` and `execution/frame_lifecycle.inc:395` enforce exact completion. | Add the read ownership class/final release while retaining frame, stack, object/source and ACK lifetimes; keep all completion checks. |
| `kernel_module/exe.c:704` ordinary CALL continuation runs the origin and remaining suffix. | Executor-side resumable services are needed. This existing route cannot silently count as forced delegated completion. |
| `kernel_integration/mmap_lock/prepare.py:44,61` and builtin `pool.c:6` omit JIT/image publication; `daemon/compiler.inc:97,114` forks/executes Python. | Resolve executor/image availability before activating the general protocol. The startup dependency is inferred from source, not a reproduced forced-delegation boot failure. |

These are missing implementation capabilities, not proof that every MM body is
inherently non-delegatable. No check was disabled, no origin suffix was newly
introduced, and no mmap1-specific production adapter was added. A new kernel
candidate build/run and protocol-transition evidence remain pending. No gain or
regression claim is made.

## Preserved evidence and restoration

Guest evidence root:
`/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/rwsem-protocol-observe-20261102`.
Complete archives, original inventories and controllers are in ignored source-host
`bench/results/10.176.26.71/raw/tests/rwsem-protocol-observe-20261102/`.
The [archive receipt](archives.json), [download verification](download.json) and
[local inventory](local-files.json) bind every retained file. Archive SHA256:

- `checks.tar.gz`: `e869bff0d628e628a08813d1c4e34ec8fac1b3cfb1e2033ccfad49027569397a`.
- `observations.tar.gz`: `93a07bbabcce404bd9c329abe6faa070d24a0be9af9cc7c11ebc62837f14216a`.
- `metadata.tar.gz`: `f432cb1c478ca263754bde7743adc50252f7d0918dd876da34020c6bfdcb0c7c`.
- `controllers.tar.gz`: `83881d103145a97e6db2c65cd93764e831e3f8f1c80b0e3eaba5e14b94975dd0`.

After idle and archive verification, an ordinary reboot restored the unchanged
default `7.0.0-38-kdlock1`, boot `b4c42511-d2fd-4ac7-b6b5-48650aae48b7`.
The normal running schema-2 verification passed and final idle was confirmed.
The permanent boot default was unchanged. No evidence was deleted.
