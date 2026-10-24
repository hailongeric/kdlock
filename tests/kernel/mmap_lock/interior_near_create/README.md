# Queued native near-survivor creation

This correctness-only family reuses **kdmm29**, with no production change. It
creates a private near survivor after unmap requests publish, then proves locked
revalidation and actual different-task removal of an empty/shared-zero interior
target. All **70 serial cases, two basic tests and 2,632 negative receipt
controls** passed; recovery is restored and test modules unloaded.
See the [result record](../../../../bench/results/10.176.26.71/tests/mm-interior-near-create-20261024/README.md)
and [execution mechanism](../../../../kernel_integration/mmap_lock/UNMAP.md#queued-private-near-survivor-creation).

A VMA (virtual memory area) spans three pages across a 2-MiB boundary. Its middle
page is removed. The near survivor shares the target's leaf PTE (page-table entry)
table; the far survivor lies across the boundary. For P=4 KiB and boundary B:

| Orientation | Original VMA | Removed interval | Near slot |
| --- | --- | --- | --- |
| left | `[B-2P,B+P)` | `[B-P,B)` | 0 |
| right | `[B-P,B+2P)` | `[B,B+P)` | 2 |

Both outer neighboring VMAs and the native two-split table-retention proof are
mandatory. Neither target is a private page. Genuine shared-zero PTEs are created
by read faults and verified through locked kernel walks; untouched means an
absent PTE, not just a zero value read from memory.

`client-empty` and `client-zero` accept:

```text
native|target middle-PAIR left|right MODE
```

Survivor letters are in address order: U=untouched, Z=shared zero, R=ordinary
private resident. Initially the near survivor is U or Z; the far survivor may be
R/Z/U. All 24 combinations of target class, orientation and survivor types have
native comparisons. No combination was deduplicated.

| Mode | Control |
| --- | --- |
| `create` | Native write fault creates near R while three writers are queued |
| `create-busy` | Same creation, then locks the new near page before revalidation |
| `create-far-busy` | Same creation, then locks an existing far R without another reference |
| `create-error1`, `create-error2` | Inject `-ENOMEM` after the first/second split |
| `create-cancel` | Create the near page, then cancel the queued victim while both readers remain held |

Busy controls use two published requests and a later sticky-local third call.
Errors and cancellation use two requests. Native controls run one operation with
the same creation under a local read share. `create-cancel` is KD-only. The
[results](../../../../bench/results/10.176.26.71/tests/mm-interior-near-create-20261024/README.md#results-and-controls)
list the exact busy/error/cancellation subset; not every mode is claimed for every
layout.

The original caller prepares both split descriptors, mapping-index reserves and
reverse-map links before queue publication. A test reader calls native
`get_user_pages(FOLL_WRITE)` without dropping/reacquiring its existing read lock.
The probe owns only the new private reference, never the shared zero page. The
combiner rewalks current state under the actual mmap writer and PTE locks, checks
new or preserved simple ancestry, acquires exact survivor holds and executes
native splitting/removal. Readers remain local and concurrent. Post-split errors
return directly; pre-effect refusal uses exact handback/ACK (acknowledgment) and
sticky fallback. Cancellation retires resources while keeping the victim mapped.

The validator binds the transition's mm/task/slot, table, new page and ancestry
identity to the real body's executor and exact hold retirement. Pre-access PTE,
VMA/residency and reference checks precede U reads. Later demand faults and
isolated writes preserve neighbors and the independent zero mapping. Target
access faults before/after survivor accesses; full cleanup retires all tables,
pages and ownership records. A local fallback is never counted as delegation.

On the same idle VM with verified recovery, reuse installed artifacts:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-interior-near-create-20261024/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-interior-near-create-20261024/workflow.py collect --attempt 2
python3 bench/results/10.176.26.71/tests/mm-interior-near-create-20261024/workflow.py recovery --attempt 2
```

Use `run --attempt 2` only for an already verified kdmm29 boot. Attempt 1 is
completed evidence and must not be overwritten. Do not repeat `prepare`/`build`,
force unload or change the recovery default. The fixed archive is checked by
`python3 bench/results/10.176.26.71/tests/mm-interior-near-create-20261024/audit.py`
without live testing. New probe-module builds must use the exact captured kernel
ELF for split BTF (type metadata referencing the kernel); symbol versions alone
are insufficient.

This is deterministic pre-execution coverage. Uncontrolled write/fault/reclaim/
pinning races, interior neighbor replacement, allocation exhaustion and a new
waiting-fault fixture remain untested. Private interior targets, larger VMAs,
complex ancestry and general page-table destruction remain unsupported.
Performance/p95, mutex-regression work and nano reruns remain deferred.
