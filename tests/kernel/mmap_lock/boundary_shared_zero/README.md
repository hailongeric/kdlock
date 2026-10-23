# Shared-zero target in shared boundary geometry

This is a **prepared, unbuilt kdmm20 candidate**. No live support is claimed yet.
The [stage record](../../../../bench/results/10.176.26.71/tests/mm-boundary-shared-zero-20261023/README.md)
contains the storage blocker, exact cleanup proposal, mechanism, planned checks
and guarded reproduction commands. kdmm19 remains the validated guest baseline.

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
