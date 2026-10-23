# Bounded resident anonymous munmap: correctness probe

The `kdmm6` run passed eight populated-removal cases and three preservation
smokes serially in the original MM VM. The default remains one page; the
supported extension removes a whole isolated VMA (virtual memory area) containing
two through four ordinary resident anonymous pages, with neighboring VMAs
retaining the page table. The [scope guide](../../../../kernel_integration/mmap_lock/UNMAP.md)
explains caller preparation, admission and teardown restrictions; the
[single result record](../../../../bench/results/10.176.26.71/tests/mm-range-unmap-20261023/README.md)
contains counts, identities, logs and remaining gaps. Earlier `kdmm5` evidence
and its initial probe-build failure remain in the
[baseline record](../../../../bench/results/10.176.26.71/tests/mm-populated-unmap-20261022/README.md).

The probe coordinates existing readers/queues and retains exact test references
to original pages. Real userspace `munmap`, or `vm_munmap` for cancellation,
reaches the actual in-tree body. No supplied callback substitutes for removal.
Every remote completion must match its originating task, different executing
task, mm, request ID, range and every original PFN (physical page number).

The main case queues 16 whole-range removals, 16 unsupported partial removals and
16 later sticky-local calls. It checks every retained byte, page mapcount,
reference, charge ownership, lock state, neighboring contents, originating-CPU
TLB (cached address translation) invalidation, exact handback/ACK
(acknowledgement) records and cleanup. Two readers remain concurrent and local;
a real untouched-neighbor fault waits behind the writer and then resolves
locally. The warmed stack-observer setup from the existing probe is retained.

The additional cases cover a busy final page, a five-page refusal, queued fatal
cancellation and final page release without test references at widths two,
three and four. The busy-page case independently checks that the three earlier
temporary locks/references were released before the matching ACK. The single-page
preservation smoke also releases its test references before the body. No case
dereferences a freed page. All exact test references and queue ownership must
retire before ordinary module unload.

## Reuse the installed candidate and built probes

Run from `380G10` only when this task owns the VM test slot and the VM is idle.
The helper verifies the real recovery snapshot, placement and boot identity;
selects the installed `kdmm6` KD entry once; and runs the frozen 11-case stream
with its already-built binaries. It does not rebuild or archive old evidence.
Use the next unused attempt number (`1` is the completed run):

```sh
cd /home/eric/vm/vm-shared/kdlock
python3 bench/results/10.176.26.71/tests/mm-range-unmap-20261023/workflow.py kd --attempt 2
python3 bench/results/10.176.26.71/tests/mm-range-unmap-20261023/workflow.py recovery --attempt 2
```

Run the second command only after the first passed and drained. A timeout is
not drain: retain the module and failed state, inspect live workers, and never
force unload or reboot an active operation. Both commands use only the existing
`10.176.26.71:2222` VM and preserve its recovery default and configuration.

Guest receipts are under
`/root/kdlock-evidence/10.176.26.71/tests/mm-range-unmap-20261023/focused-2/`.
The frozen driver is `control/focus.py` under that stage root, and binaries are
in `probes-1/`. The source-host workflow saves transition and result receipts in
`bench/results/10.176.26.71/raw/tests/mm-range-unmap-20261023/kd-2/`.
Existing output paths are refused.

The candidate identity snapshot is
`/mnt/kdlock-builds/mm-range-unmap-20261023/linux`, with baseline
`/root/kdlock-kernel-baselines/mmap-kdmm6-20261023`. That snapshot deliberately
contains only the captured source/configuration/build-identity files. It is
**not a full `KDIR`** for the standalone `run.py`, which builds fresh modules.
Use the prebuilt workflow above for this installed candidate. For future source
changes, compile affected targets in a new verified build workspace and preserve
their identity before testing; never edit these frozen inputs.

The client retains `--pages 1|2|3|4` (default `1`), `--cancel`, `--no-neighbor`,
`--free`, `--busy-last` and `--too-wide`. The standalone runner spells the cancel
option `--cancellation`; it requires a complete matching kernel build tree.
The focused driver is the minimal recorded stream, including the unchanged
advice, first-write fault and unpopulated-removal smokes. Fault and munmap cases
remain separate. General mapping support and performance remain unvalidated.
