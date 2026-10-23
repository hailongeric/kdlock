# Shared-zero target in shared boundary geometry

`kdmm20` supports one shared-zero prefix/suffix target in a three-page anonymous
VMA (virtual memory area) crossing a 2-MiB boundary, with one survivor sharing
the target table. Both outer-neighbor guards and the exact native table-retention
proof remain mandatory. All 65 serial cases, two basic tests and 1,935 negative
receipt controls passed, with 40 different-task zero removals and two additional
removals after queued conversion to private targets. Recovery is restored.
See the [result record](../../../../bench/results/10.176.26.71/tests/mm-boundary-shared-zero-20261023/README.md)
and maintained [mechanism](../../../../kernel_integration/mmap_lock/UNMAP.md#shared-zero-target-sharing-a-boundary-table).

## Reuse the installed candidate

On `380G10`, first verify the VM is idle and current capacity covers boot/log
growth. Attempt 1 is completed evidence; use a fresh attempt and keep tests serial:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-zero-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-shared-zero-20261023/workflow.py recovery --attempt 2
```

This reuses the installed image and eight existing clients, checks the original
snapshot/placement and captured identity, runs the 65 cases and restores recovery.
Preserve the source-host compressed identity referenced by the result record;
the workflow transports it through guest RAM. No build is needed. Do not repeat
`prepare`/`build` in completed directories or reboot an undrained run.

On an already verified kdmm20 boot, `run --attempt 2` avoids another boot. The
equivalent guest command requires the verified RAM identity:

```sh
env PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 \
  KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z \
  /root/kdlock-translation-venv-20261019/bin/python3 \
  /root/kdlock-evidence/10.176.26.71/tests/mm-boundary-shared-zero-20261023/control/focus.py \
  --build-attempt 1 --run focused-2
```

## Fixture and controls

The client accepts `native|target SHAPE [MODE]`. SHAPE is `prefix-PAIR` or
`suffix-PAIR`; PAIR names the two survivors in increasing address order using
R (private resident), Z (shared zero), U (untouched). The target is read-faulted
to a real shared-zero PTE (leaf page-table entry), with one survivor in its leaf
table and one across the 2-MiB boundary. Inspection does not write to the target
or fault U survivors. Existing native neighboring-VMA retention checks remain.

Modes are `success`, `error`, `free-table`, `change-private`,
`change-private-busy`, `busy`, `cancel` and `fault`. Transition/fault controls use
UU survivors. `busy` uses prefix-RR. `free-table` retains its historical name:
loss of the outer-neighbor guard forces KD handback, but native code retains the
target table because the surviving VMA still spans it. No table free is expected.

The two new queued write-fault controls preserve an exact ordinary GUP
(`get_user_pages`) reference to the newly private target for post-body inspection.
`change-private` must use the fully eligible kdmm19 body; `change-private-busy`
locks that page and must hand back before effects. Original shared zero pages
never receive private ownership. No physical allocator-reuse claim is intended.
The runner checks state before intentional survivor reads and isolated writes,
then exact cleanup and normal module unload after drain.

All nine survivor pairs run in both directions; reversed pairs change the near
and far table roles. Twenty new zero removals held no private pages. The native
controls use the native body on the same KD boot. Queue ownership, request-bound
completion, handback/acknowledgment (ACK), sticky fallback and cancellation are
required, including exact post-split error outcomes without destructive replay.
Queued neighboring-VMA replacement conflicts with the fixture's held reader
shares and remains untested. Controlled target changes do not establish
uncontrolled fault/reclaim/pinning race coverage. kdmm20 refuses empty/missing
targets in this geometry; kdmm21 adds the separate
[empty-target fixture](../boundary_shared_empty/README.md). Missing target tables,
larger VMAs and general table destruction remain unsupported here.
