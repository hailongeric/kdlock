# Empty interior target beside a private resident survivor

`kdmm28` removes one empty middle page from a three-page anonymous VMA (virtual
memory area) crossing a 2-MiB boundary. The near survivor, in the target's leaf
page table, may now be an ordinary private resident page. The far survivor may
be private resident, shared zero or untouched. Both original outer neighbors
and the native two-split table-retention proof remain mandatory.

All **48 serial cases, two basic tests and 1,161 negative receipt controls**
passed. Six native-matched layouts produced **12 different-task removals**;
six preservation cases added 12 separate removals. Recovery is restored and
modules unloaded. See the [result record](../../../../bench/results/10.176.26.71/tests/mm-boundary-interior-near-private-20261024/README.md)
and [mechanism](../../../../kernel_integration/mmap_lock/UNMAP.md#empty-interior-target-with-a-private-near-survivor).

For P=4 KiB and boundary B=2 MiB, `left` maps `[B-2P,B+P)` and removes
`[B-P,B)`; `right` maps `[B-P,B+2P)` and removes `[B,B+P)`. Survivor letters
are in address order: R=private resident, Z=shared zero, U=untouched. Test left
`middle-rr/rz/ru` and right `middle-rr/zr/ur`. All six are covered; none is
deduplicated. Locked PTE (page-table entry) walks prove the target is empty and
the near page private, without reading or populating far-U addresses.

The existing payload and clients are reused, except this new client and the
kernel-dependent payload module. The client accepts:

```text
client native|target middle-PAIR left|right [MODE]
```

| Mode | Purpose |
| --- | --- |
| `success` | Actual removal, survivor state/content, references and accounting |
| `error1`, `error2` | Return `-ENOMEM` after first/second split, matching native |
| `free-table` | Remove a required outer guard; refuse before effects |
| `change-zero`, `change-private` | Queued target conversion; refuse this unsupported combination |
| `change-near-busy`, `change-far-busy` | Lock an existing RR survivor after publication; test early/late exact hold rollback |
| `cancel` | Cancel a published waiter and retire its resources |

Busy controls reuse the existing page-lock fixture, changing neither PTE nor
page ownership. They record two pending requests and two concurrent local
readers. Both traversal orders cover refusal before any hold and refusal after
one earlier hold. Handback and ACK (acknowledgment) match the exact origin and
request; the later call stays local. Admitted split errors return directly and
never replay native destructive work. These deterministic controls do not
establish uncontrolled race coverage.

Initial checks precede survivor accesses. Resident contents/PFNs (physical frame
numbers), PTEs, references, neighboring mappings, VMA layout and accounting must
match native. Later far-U faults, zero-page private writes and an extra isolated
near-private write preserve other survivors and the independent zero mapping.
The removed address faults again after those accesses. Full fixture cleanup
and normal module unload are required.

Reuse the installed corrected image/modules with fresh run directories:

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-near-private-20261024/workflow.py kd --attempt 3
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-near-private-20261024/workflow.py recovery --attempt 2
python3 bench/results/10.176.26.71/tests/mm-boundary-interior-near-private-20261024/audit.py
```

`run --attempt 3` uses an already verified candidate without rebooting. The
audit reads the fixed completed evidence. Do not repeat preparation/build,
overwrite attempts, reuse the rejected pre-refresh modules or force unload.

Private interior targets and shared-zero targets beside private near survivors
remain unsupported. Queued near-page creation, interior neighbor replacement,
opposite outer-guard loss, huge/special-entry injection, allocation exhaustion,
uncontrolled writes/faults/reclaim/pinning and hibernation remain untested.
There is no new waiting-fault fixture. Larger mappings, complex ancestry,
general table destruction and performance remain deferred.
