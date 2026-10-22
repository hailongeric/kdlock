# Populated anonymous munmap: bounded functional stage

Status: the basic populated-unmap milestone and all preservation checks passed
on `kdmm5`: 20 serial sessions, zero live failures, recovery restored and archive
audit complete. The single failed probe build remains separately recorded.
Performance, p95, broad stress and the seven mutex regressions remain deferred.
Initial inspection found the original
MM VM idle on recovery boot
`880aa11b-ab56-4129-b700-06b037473530`, with the expected 73 modules and
9,757,523,968 bytes free on root. The real snapshot and original placement were
rechecked. Checkout commit `d575556` is confined to nano results; its work and
the pre-existing cleanup report remain untouched. MM work has one writer.

The selected extension is one writable resident 4-KiB private anonymous VMA
(virtual memory area), with ordinary exclusive anonymous memory, no swap/huge
page, callback, notifier, special state or memory-account reservation. Both
neighboring VMAs must lie in the same PMD span (the 2-MiB range described by one
page-middle-directory entry). This retains the leaf PTE table (page-table-entry
array), while the real original unmap body removes the mapping, drops its page
reference, updates the explicit mm accounting and completes its TLB flush
(invalidation of cached translations).

This restriction addresses a concrete review finding: freeing page-table pages
can allocate an RCU deferred-free batch using the executing task's allocation
context. The captured `free_pgd_range` returns before table removal for the
admitted neighbor bounds; the original helper is still executed. One data page
fits the native eight-page local gather. General page-table destruction and
larger populated ranges are deferred rather than run with another caller's
allocation context.

The origin prepares maple allocations and synchronizes its own deferred RSS
(resident-page accounting) and LRU additions (recently used page queues) before
publication. Admission takes a temporary page reference and tries its page lock
under the PTE lock; it never waits in the inverse lock order. The page lock
excludes reclaim/migration through removal. Normal teardown unlinks reverse
maps and updates the page's recorded memory cgroup, not the executor's cgroup.
After real teardown, the exact PTE must be empty, page mapcount zero and table
bytes unchanged. The executor releases its temporary page lock/reference before
publishing completion. Existing mmap writer ownership, node retirement and
handback/ACK routing are unchanged. Unsupported and busy-page cases make later
calls sticky-local. The separate populated opt-in leaves the validated old
unpopulated admission unchanged.

Review captured 20 actual `kdmm4` source/configuration files under
`bench/results/10.176.26.71/raw/tests/mm-populated-unmap-20261022/inspection/`.
The candidate uses a new `kdmm5` tree and baseline; recovery and all earlier
installations are retained. Focused serial tests must prove another task removed
the original physical page mapping, cached-translation invalidation, neighboring
contents, exact ACKs, sticky refusal, cancellation and complete cleanup, and
rerun the directly affected preserved paths before this stage can pass.

Kernel source `4b8ec51` built successfully on the first attempt: both basic
programs, five advice, five fault and five unpopulated-unmap receipt controls,
the `kdmm5` image and all 73 required runtime modules passed. The captured
manifest SHA-256 is
`8f9bd2899aa5c69bb2eb113b4d914d780dd5daa17f20b31ada3bced1a0f71cb1`.
The single `serio_raw` target
uses the already validated one-job external-directory form, avoiding the
previous stage's competing builds.

The probe retains explicit original-page references for PFN (physical page
number), contents, mapcount and memory-charge ownership checks, then retires
every reference. An additional unreferenced case releases these test references
before real munmap, exercises normal final release, and deliberately does not
dereference freed pages. All originating CPUs repeat their earlier cached
access after unmap and must fault. A separate hardware fault to an untouched
neighbor must wait behind the writer and resolve normally after writer release.

Probe build attempt 1 failed at module symbol checking: `lru_add_drain` is not
exported by this kernel. No module loaded, installation started or boot changed.
The retained `test-build-1/build-module.log` and source snapshot are a failure,
not a pass. The follow-up probe uses the existing exported page-vector release
API to retire exact scratch references on the original pinned setup CPU; its
normal local LRU drain makes the same strict reference-count oracle usable.
No kernel candidate, admission check or ownership assertion changed.

Probe revision `f7af0fd` passed module/client compilation and all five receipt
controls in `test-build-2`. Candidate installation preserved the recovery default
and files. Build ID: `557ee1e502bacf98c48b3f21b2c328aa92e273e9`.
`native-1` passed all four controls on boot
`6a6e9224-49ed-4bbc-93d6-b21255ba17fc`. On KD boot
`da7ca065-c431-4822-af2d-cf26b6532c5d`, these new sessions passed and drained:

| Run/session | Observed result |
| --- | --- |
| `kd-1/populated-body` | 16 supported one-page removals, 15 completed on another task; 15 original-PFN/body receipt pairs; 1,640,290 content/ownership checks; 48 originating-CPU translation invalidations; 15 exact partial-unmap refusal ACKs; 16 later sticky-local calls; two concurrent local readers and a real blocked neighbor fault that resumed with zero-filled data; all 48 test references released. |
| `kd-1/populated-cancellation` | One queued fatal cancellation retained its original mapping/page; healthy head completed; both test references and all queue ownership retired. |
| `kd-1/populated-no-neighbor` | Required page-table freeing returned to the original waiter with one exact ACK; one later sticky-local call; original CPU translation invalidated; three test references released. |
| `kd-1/populated-free` | Both test page references released before the body; two actual removals, one remote, with original-PFN completion; both originating CPUs faulted after removal; no freed page dereferenced. |

The four sessions issued 165 explicit local cleanup calls and retained zero test
page references. These are built-in real `do_mas_align_munmap_prepared` bodies,
not synthetic callbacks or JIT execution. Their results and kernel receipts are
under `/root/kdlock-evidence/10.176.26.71/tests/mm-populated-unmap-20261022/kd-1/`;
local fetched receipts are in the matching ignored raw-stage directory.
No live failure occurred in these four sessions. Broader populated ranges,
general page-table destruction and mmap creation remain unsupported.

## Preserved functionality and recovery

`kd-1` completed all 16 sessions on one boot. Alongside the four new cases,
the basic API, advice, advice cancellation, actual first-write fault body,
fault cancellation, userfaultfd retry, old unpopulated munmap, its cancellation
and zero-page refusal, untouched mmap, page-fault workloads and completed-fault
return handling all passed. The separate `native-1` completed its four controls.
No MM run overlapped another, no in-flight run was interrupted and this task
changed no nano input. The basic C programs and the 20 directly affected receipt controls
(five each for advice, fault, unpopulated and populated munmap) passed in the VM.

The preservation sessions recorded 1,747 remote advice bodies, 133 remote
first-write page installations with 16 original-PTE receipts, and 15 remote
unpopulated removals. These are this kernel's correctness counts, not throughput,
variance estimates or pooled totals with `kdmm2`/`kdmm3`/`kdmm4`. The page-fault
retry released its read acquisition and allowed the required writer to proceed;
the completed-fault test checked all 64 actual returns and writer reacquisition.
Untouched mmap and page-fault workloads remained distinct.

Recovery boot `e3f803a7-7a85-435a-8f62-82e08b2e9f2a` runs
`6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, with the expected 73 modules, no
remaining MM probe workers and no new kernel-fault matches in the retained log.
All 5,686 recovery module files and preserved boot inputs were checked. Each of
the advice, fault and old unpopulated installations retained all 90 recorded
files. Advice/fault body source hashes are unchanged. All 337 frozen non-document
source inputs matched after validation; the unrelated cleanup-report edit was
left untouched. During final documentation, another task staged deletion of 60
nano report paths. Those unrelated index changes remained outside this task's
path-specific commit; the second source check still matched all 337 MM inputs.

## Commands and artifacts

The [maintained scope guide](../../../../../kernel_integration/mmap_lock/UNMAP.md)
explains admission, caller resources and ownership. The
[probe guide](../../../../../tests/kernel/mmap_lock/populated_unmap/README.md)
gives the four individual guest commands. For the installed candidate, these
source-host commands repeat the focused serial controls on fresh run names:

```sh
python3 bench/results/10.176.26.71/tests/mm-populated-unmap-20261022/validate.py --mode native --run native-2
python3 bench/results/10.176.26.71/tests/mm-populated-unmap-20261022/validate.py --mode kd --run kd-2
python3 bench/results/10.176.26.71/tests/mm-populated-unmap-20261022/validate.py --mode recovery --run recovery-2
```

Each predecessor must pass and drain before the next command. These controllers
make the recorded one-shot transitions in the approved MM guest; they are not
commands for another host or an active VM. They preserve the recovery default,
require the actual snapshot and pins, and never turn a timeout into proof of
drain. No timing command is included.

The tracked [correctness result](correctness-result.json) binds source/probe
revisions, all run receipts, failure and final health. The guest evidence root is
`/root/kdlock-evidence/10.176.26.71/tests/mm-populated-unmap-20261022`; the archives
are in its sibling `mm-populated-unmap-20261022-archives-1`. Local raw evidence is
`bench/results/10.176.26.71/raw/tests/mm-populated-unmap-20261022`.
Its `seal-1/guest-archives-1` contains `native.tar.gz`, `kd.tar.gz`,
`build.tar.gz`, `preparation.tar.gz` and `metadata.tar.gz`, totaling 316,523,055
bytes. The failed first module build is in `preparation.tar.gz`.

Archive manifest SHA-256:
`c2170e201f21d5bf8b348b5b8b8bf4787f0f92a7ab87c21db5ef0c1be854dfff`.
Final health SHA-256:
`478e87488bb4e9046de57ea551a522927791e869438cc1e509ac83dec36a53e8`.
The read-only source-host audit passed 13,452 checks with zero mismatches across
1,893 files and 697 frozen source bindings. It checked inventories, Git and binary
hashes, exact physical-page/body/ACK identities, failed-build preservation and
recovery without extracting or executing archived code. Recheck it with:

```sh
python3 bench/results/10.176.26.71/tests/mm-populated-unmap-20261022/audit.py
```

## Remaining limits

This is one ordinary resident anonymous page with retained page tables. Required
table destruction and partial removals were exercised through the native waiter
continuation, not delegated. Mapping creation, larger populated ranges, swaps,
huge pages, device/file/notifier callbacks and arbitrary MM bodies remain outside
the admitted scope. Busy-page, poisoned-page, DMA-pin, policy and other exclusions
are reviewed guards, not individually fault-injected test passes.

Forced allocation failure, concurrent tree growth during preparation, slot
exhaustion, the 256-request handoff boundary, post-admission cancellation,
advice/unmap queue interleaving, broad reader/fault races, concurrent fast page
pinning, swap/reclaim pressure, different non-root memory cgroups and
oversubscribed progress remain untested. Only the required 73 runtime modules
were built. RT, lockdep and whole-kernel replacement remain unvalidated.
Performance, p95 and the seven mutex regressions are deferred/unresolved;
variance was not measured and performance acceptance is false.
