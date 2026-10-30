# Interpreting the upcoming local mmap and unchanged mmap1 comparisons

Source-only inspection on 380G10; no new measurements, tests or VM actions.
Scope configuration was checked from `/tmp/kdlock-scope-preinstall-r2-fetched-20261030/.config`
against the retained full-build and installed-boot receipts.
Project source: `f7a84065e84474380faa37eeadfdf534abd72a68` at
`/tmp/kdlock-continuation-perf-20261030`. The installed scope kernel remains the
recipe from `8446f4ecb08816380a4c233197a8ce5e4d333aac`. Git comparison confirms
no changes between those commits in `kernel_module/kd_rwsem.c`,
`kernel_module/kd_mutex_local.c`, `kernel_module/kd_mutex_osq.c`, or the
`kernel_integration/{mmap_lock,linux70}` trees. The f7 loadable instruction-service
and spin-batch optimizations are not a new built-in MM implementation.

Native call-path references below are from the locally captured authenticated
Linux 7 source under `/tmp/kdlock-semantic-source-20261030/source/` (prefix `L/`).
The active integration patch is `kernel_integration/linux70/mmap-lock.patch`;
`kernel_integration/mmap_lock/guest-kernel.patch` is historical Linux 6.1 input
and must not be treated as the active kernel patch.

## Workload and path mapping

| Workload/path | Actual lock operation and interpretation |
| --- | --- |
| Localized shared-mm workload | Pthreads share one mm. One operation is untouched 4 KiB `mmap(PROT_READ, MAP_SHARED, device_fd)` plus `munmap`; native MM bodies and the mapping callback run on the original task. `bench/mmap_writer/timed_client.c:84–108`. It exercises actual mmap_lock writers and teardown, not a copied critical section or a sustained reader workload. |
| Unchanged `mmap1_threads` | The original will-it-scale loop maps/unmaps an untouched 128 MiB anonymous private read/write range. Threads share mmap_lock. It is primarily writer acquisition plus mapping/unmapping algorithms; no payload page faults are deliberately generated. |
| Unchanged `mmap1_processes` | Same upstream loop, separate worker mms. This is a separate control for same-mm contention, not another sample of the thread workload. It still includes system-wide allocation/MM costs. |
| Mapping entry | `L/mm/util.c:565–586`, `vm_mmap_pgoff`: killable mmap write acquisition, native `do_mmap`, write unlock; userfaultfd completion and any population follow the unlock. |
| Unmapping entry | `L/mm/vma.c:3259–3274`, `__vm_munmap`: killable write acquisition and `do_vmi_munmap`. Errors/non-unlocking callers use write unlock. Successful unlocked teardown can downgrade in `vms_complete_munmap_vmas` (`:1311–1347`), then clear PTEs/free VMAs and finish with read unlock. Thus an untouched map/unmap writer workload can still exercise a downgraded read share. |
| Fault controls | `L/arch/x86/mm/fault.c:1325–1413` has a per-VMA/RCU fast path and mmap-read fallback, with RETRY/COMPLETED release rules. Those controls validate additional paths; their costs must not be assigned automatically to untouched mmap1. Reads remain local. |

The Linux 7 patch preserves mmap_lock tracing and sequence-count operations
around the substituted rwsem calls (`kernel_integration/linux70/mmap-lock.patch:114–140`);
it does not rewrite `do_mmap`, munmap or fault bodies. The adapter chooses one
backend per mm before publication, and all its users keep that choice
(`kernel_integration/mmap_lock/overlay/kernel/locking/kd_mmap/adapter.c:28–143`).
Both readers and writers execute locally; there is no MM JIT/combiner path.

## Concrete implementation costs to test against observations

1. **Killable writer admission is the leading bounded hypothesis.**
   `kernel_module/kd_rwsem.c:237–253` first uses
   `wait_event_killable(phase_wait, kd_rwsem_reserve_local(sem))`, then acquires
   the local gate and drains readers. Reservation checks admission/reader-OSQ
   tail and CASes admission from 0 to -1 (`:191–196`). It bypasses the 16,384-probe
   polling macro used by ordinary uninterruptible writers (`:18–36,207–212`).
   Native Linux 7's captured `rwsem_down_write_slowpath` tries owner-aware
   optimistic spinning before enqueuing/sleeping (`L/kernel/locking/rwsem.c:1111–1119`)
   and can spin again after handoff (`:1169–1185`). Actual contention frequency
   and time saved/lost are not established yet.

2. **A mutex OSQ does not remove that admission difference.** The built-in local
   mutex has owner-on-CPU spinning and scheduling fallback
   (`kernel_module/kd_mutex_local.c:170–204,228–283`), but rwsem writers must win
   the exclusive -1 admission reservation first. Inference: ordinary writers
   principally compete at the phase wait, so the embedded gate's optimistic
   spin cannot serve as writer-admission spinning. No delegated positive phase
   exists in the generated built-in backend (`kernel_integration/mmap_lock/prepare.py:61–72`).

3. **Wake-all competition and shared atomic traffic are plausible costs.**
   Writer phase release ordered-exchanges admission to 0 then calls
   `wake_up_all` when phase waiters exist (`kernel_module/kd_rwsem.c:59–65,199–204`).
   Multiple awakened writers can contend for the same CAS. Acquisition and
   release also touch the separate gate/reader/admission state. More cross-node
   sharing or more unsuccessful woken contenders could lower throughput, but
   ordinary timing receipts do not count those events or prove cacheline bouncing.
   Do not change fairness to explain or hide a result; that work is deferred.

4. **Reader-drain fallback has a specific trigger.** A killable writer checks
   zero readers with a one-jiffy timed wait (`kd_rwsem.c:80–102`). Final reader
   release wakes immediately in schedulable context; IRQ/atomic release omits
   that wake and relies on recheck (`:68–76`). There is no mandatory one-jiffy
   sleep when the predicate is already true. For these map/unmap loops,
   overlapping downgraded teardown is relevant. The captured ordinary-kernel
   `.config` has `CONFIG_HZ_1000=y` / `CONFIG_HZ=1000` at lines 543–544;
   the separately fetched scope configuration has the same values and SHA256
   `7131e48d4bb556e54f9fc287c04e6fab33a3de80eb923a215872a01a07609f4b`,
   matching the scope full-build receipt and installed boot-config manifest.
   One jiffy is therefore 1 ms for this scope image, not the historical 4 ms.
   This is a timeout/recheck parameter, not an exact delay: timer phase and
   scheduling affect elapsed latency. The current scored receipts cannot prove
   that an omitted wake or reader-drain timeout actually occurred.

5. **MM body and layout costs remain distinct from locking.** Both workloads
   perform VMA allocation/Maple Tree/accounting and teardown, but the device
   workload has 4 KiB MAP_SHARED file callbacks while mmap1 is 128 MiB anonymous
   private. Unchanged algorithms do not imply equal per-operation costs.
   Native and KD modes share the same scope image/object layout, reducing that
   confound within this cohort. This is not a comparison against the ordinary
   CONFIG-off kernel. Virtual addresses do not establish physical NUMA placement.

## What the existing outputs can and cannot distinguish

| Observation to read after finalization | Supported interpretation / limit |
| --- | --- |
| Localized whole rate, peak or retained missing-peak reason, and `worker_cpu_ns` | Whole rate is completed pairs / actual measured wall time. `worker_cpu_ns / (N × wall_ns)` approximates cohort CPU occupancy, with start/finish boundaries retained. Low occupancy is consistent with sleep or scheduling delay, not proof of lock parking. Near-full occupancy rules out spending a comparably large fraction asleep within that accounting scope, but not spinning/coherence costs. |
| Localized per-worker completed counts, starts, CPU time, finish/teardown and progress samples | Unequal progress or late workers can explain whole/peak divergence. No acquisition-latency or scheduler-cause claim follows. Plain mode has no latency samples and `observe=0`; `contended_mmaps=0` therefore means the observer is disabled, not no contention. |
| Localized map/close counts, zero VMAs/fault callbacks/errors and final health | Establish exact operation/lifetime conservation. Zero payload faults does not exclude incidental process/kernel faults. A failed oracle is not a scored performance loss. |
| mmap1 threads versus processes at the same worker count | A thread-only loss supports investigating shared-mm admission/serialization. Similar losses in both models point to broader per-operation/system/placement costs as well. This is evidence for prioritization, not causal isolation. |
| mmap1 raw `min/max/total` for both measured samples and six warmup samples | Low measured minima/large spread show progress imbalance; both measured minima must remain positive. Two sample totals preserve temporal differences; do not choose only the faster sample or invent a variance estimate. |
| mmap1 whole-process user/system CPU and elapsed time | These include warmup, setup, shutdown and reaped children. They are not CPU occupancy for the two scored sample intervals and cannot prove a measured-window parking fraction. |
| 32→36 workers and higher cross-node points | Relates to the actual recorded CPU/node allocation. A drop is compatible with shared-state locality costs but does not prove which cacheline/page moved. No reader-OSQ, wake-all, parking, or hardware-coherence counters are in these scored outputs. |
| Native/KD identity, exact image/config, prepared binary hashes and endpoint captures | Keep each mode, boot and cohort distinct. Endpoint consistency is separate from uninterrupted isolation and acceptance. A local provider/basic pass cannot substitute for actual-mm identity/cancellation/downgrade/teardown evidence. |

The localized runner (`bench/mmap_writer/linux70.py:31–55`) produces 21 plain
points per mode, one 2-second round each; a missing positive full-cohort peak is
retained separately while exact whole accounting remains mandatory. Its
execution label is `KD_LOCAL_MMAP_LOCK` or `NATIVE_CONTROL_MMAP_LOCK`, with
`delegated=false`.

The unchanged upstream revision is
`75f66e45697e6f5f49c33dd950c4e6b289198f8f`. `bench/mmap1/run.py:37–72` runs
`-t N -s 2 -m`, retaining six pre-marker samples and two post-marker samples.
The score is the two post-marker totals divided by two nominal seconds; the
upstream integer average is checked separately. This is not nano/localized
whole-wall rate or a peak. Observed exact elapsed sample seconds are unavailable.
The same prepared executables are reused across modes. The unscored identity
probe establishes worker-mm/backend class separately; timed mm pointers are
not observed or borrowed from that diagnostic.

Current controller order keeps localized KD versus Native-B separate from final
mmap1 Native-B versus KD-B; no earlier Native-A preparation run becomes a scored
baseline. Complete both 21-point thread/process models per final backend, retain
every negative and failure, and do not repeat or pool points. No extra diagnostic
run is proposed by this checklist.

## Semantic boundaries and acceptance

Reads never delegate. Default/callable/killable/try local writers preserve
exclusive ownership, cancellation rollback and downgrade; prepared delegated
rwsem writes are a different loadable protocol and are not used by MM.
Asynchronous BPF read release requires the exact acquired-share token plus mm
reference (`kernel_integration/linux70/mmap-lock.patch:223–327,409–424`). Focused
same-boot MM prerequisites do not establish all BPF/IRQ/NMI callbacks, complete
Native fairness/handoff equivalence, arbitrary page-table/folio replacement or
whole-kernel semantics. RT/debug-mutex/lockdep configurations are explicitly
unsupported. The actual-MM comparison can assess this local lock backend; it
cannot claim successful body delegation or improvement from f7 instruction service.

All costs above are source-backed hypotheses until the finalized observations
are available. Nano acceptance remains false. The user authorized completing
these isolated comparisons while keeping the candidate unaccepted; only the
separate final mmap1 evidence can address that application acceptance criterion.
