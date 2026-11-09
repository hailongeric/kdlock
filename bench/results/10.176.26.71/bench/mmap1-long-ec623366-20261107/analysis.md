# Retained-evidence analysis of the long mmap1 run

This analysis uses only the records committed at
`282d8f83cb2a1e77a9aebb78b6864aa802363a25` and matching source/images. It adds
no workload, VM operation or runtime change. Runtime code is
`ec623366622d1784f7e819b4e9031ba0482bee9b`; kernel component is
`9a5d606aee0249d0e566a1c9667375eb038bc9cd`, Build ID
`357a7115d21941960b90262ac1165bf70d1b398e`.
[analysis.json](analysis.json) retains exact counter sums, residuals, CPU data,
source hashes and compilation/publication correlations.

## What explains the observed gap

| Model | Native pairs/s | KD pairs/s | Loss |
| --- | ---: | ---: | ---: |
| threads | 225,631.9 | 3,641.5 | 98.39% |
| processes | 1,554,416.0 | 21,074.8 | 98.64% |

Three mechanisms are established, with different evidence limits:

1. Every selected operation in the measured interval used the capture/service
   protocol; no operation used the local no-image path. All thread requests and
   process munmap requests completed through handback. Those requests pay for
   capture, admission/dispatch, generated-prefix execution and transfer before
   the origin finishes the source suffix. Source includes owner/stack/image
   lifetime work and final ACK handling; counts prove which routes completed.
   The records do not time that entire route or assign a percentage of the loss
   to each stage.
2. Learning had not converged by measurement. Thread mmap published g7 during
   the window and process munmap published g6 near its start. Newly reached
   CALLs and indirect return edges required successive complete-image builds.
   Threads performed 16 serial translations totaling 899.422 child wall seconds;
   processes performed 12 totaling 832.969 seconds. Their work overlapped the
   application and continued afterward. It is an observed compilation burden,
   not an additive portion of application elapsed time.
3. Completed retained execution still uses origin services. Process mmap g5
   recorded returns with no measured handbacks, yet its shadow mean was
   187.558 microseconds. Actual image stubs and sampled suspended requests show
   calls to `kd_service_write_owned` and `kvfree_call_rcu`; their returning
   origin-service route resumes the executor. Therefore neither dispatch's
   2.217 microseconds nor a `returned` event means that the entire critical
   section ran without protocol exchanges. Service counts and durations were
   not saved, so their individual runtime shares remain unknown.

The saved data cannot provide a complete causal decomposition of the 98% loss.
The returning g5 path still performs capture and origin-service exchanges; these
records do not separate their costs from concurrent compiler interference.
Contention on one shared mmap lock cannot explain the entire process-model
regression. The current source selects image JIT execution and
refuses `cont->reached_active` at `kd_service.c:1162`; an older interpreter-based
explanation must not be imported into this run.

## Exact lifecycle counts

`selected` counts entry into observed `kd_service_capture_internal`, before its
route is chosen (`kd_service.c:1575`, `kd_service_observe.inc:68`). There is no
independent completed-capture counter. `submitted` occurs after root allocation,
continuation/image adoption and service setup, immediately before queue linkage
(`kd_service.c:1695`). `bound` follows actual executor admission/binding;
`jit_entered` follows initial generated-wrapper execution bookkeeping. Cancellation
fields are listed separately rather than inferred from missing completions.

Measured observer interval, approximately ten seconds:

| Model/root | selected | submitted | bound | jit_entered | returned | handback | handback_finished |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| threads mmap | 36,415 | 36,415 | 36,415 | 36,415 | 0 | 36,415 | 36,415 |
| threads munmap | 36,415 | 36,415 | 36,415 | 36,415 | 0 | 36,416 | 36,415 |
| processes mmap | 210,736 | 210,736 | 210,736 | 210,737 | 210,740 | 0 | 0 |
| processes munmap | 210,735 | 210,735 | 210,736 | 210,736 | 0 | 210,738 | 210,738 |

All window values for `local`, `local_no_image`, `local_success`, `local_cancel`,
`prepublication_cancel`, `canceled` and `invalid_clock` are zero. This rules out
local no-image routing as an explanation of the selected measured-window loss.

Whole 730-sample application, including warmup and postrun observation:

| Model/root | selected | local = local_no_image = local_success | submitted = bound = jit_entered | returned | handback = handback_finished |
| --- | ---: | ---: | ---: | ---: | ---: |
| threads mmap | 6,075,800 | 2,363,514 | 3,712,286 | 0 | 3,712,286 |
| threads munmap | 6,075,797 | 3,045,681 | 3,030,116 | 0 | 3,030,116 |
| processes mmap | 39,002,329 | 19,035,144 | 19,967,185 | 4,199,281 | 15,767,904 |
| processes munmap | 39,002,324 | 22,489,593 | 16,512,731 | 0 | 16,512,731 |

All whole-application cancellation variants and invalid clocks are zero. Exact
drained balances, checked by `observe.py:64`, hold in every row:

```text
selected = local + submitted + prepublication_cancel
local = local_success + local_cancel
submitted = returned + handback_finished + canceled
handback = handback_finished
bound = jit_entered = dispatch_samples = shadow_samples = returned + handback
```

Live window snapshots use sequential `READ_ONCE` sums across per-CPU counters
(`kd_service_observe.inc:125`). Their residuals must remain visible:

| Window row | submitted - completed | bound - jit | handback - finished | bound - shadow_samples |
| --- | ---: | ---: | ---: | ---: |
| threads mmap | 0 | 0 | 0 | 0 |
| threads munmap | 0 | 0 | 1 | -1 |
| processes mmap | -4 | -1 | 0 | -4 |
| processes munmap | -3 | 0 | 0 | -2 |

Here completed means returned + handback_finished + canceled. Selected/local
balances and bound - dispatch_samples are zero in all four window rows.
Process munmap bound - submitted is +1; other such differences are zero.
`analysis.json` also preserves bound - (returned + handback), respectively
0/-1/-4/-2. These small live boundary differences are not repaired or treated as
lost requests. Final drained balances are exact.

## Timer definitions and means

Every timer uses `ktime_get_ns()` elapsed time, not CPU execution time
(`kd_service_observe.inc:84`). Invalid-clock counts are zero.

- **Dispatch:** starts immediately before `kd_exe_on_retained_entry()` and ends
  immediately after that initial invocation (`kd_service.c:1163-1166`). It ends
  before `kd_service_run_scope()`. That loop subsequently performs services,
  resumes JIT execution and handles nested/release operations. Dispatch is not
  total generated-body duration.
- **Shadow:** starts on the origin's independent wait stack before publishing
  STACK_READY (`kd_service.c:1464`). The executor has already reached PIN after
  admission. It includes origin polling, origin-call/memory service, resumed
  executor work and protocol delay during that phase. For handback it ends in
  `kd_service_native_resume` before acceptance/restore and the remaining native
  suffix (`:1444`). For retained return it ends in `kd_service_resume_packet`
  before free/provider restore (`:1519`). It excludes earlier capture, queue and
  acquisition waiting, and it excludes the remaining handback suffix.
- **Local:** surrounds only `kd_service_local_acquire()` (`:1544-1552`), including
  any admission wait there. It excludes preceding registration/lease work and
  the caller's critical-section body. Local is also the timer's sample count.

| Scope/model/root | Dispatch samples | Dispatch mean us | Shadow samples | Shadow mean us | Local samples | Local mean us |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| window threads mmap | 36,415 | 2.220 | 36,415 | 79.537 | 0 | n/a |
| window threads munmap | 36,415 | 3.993 | 36,416 | 67.762 | 0 | n/a |
| window processes mmap | 210,736 | 2.217 | 210,740 | 187.558 | 0 | n/a |
| window processes munmap | 210,736 | 6.572 | 210,738 | 94.223 | 0 | n/a |
| whole threads mmap | 3,712,286 | 2.264 | 3,712,286 | 39.693 | 2,363,514 | 77.322 |
| whole threads munmap | 3,030,116 | 4.130 | 3,030,116 | 28.256 | 3,045,681 | 113.150 |
| whole processes mmap | 19,967,185 | 2.260 | 19,967,185 | 79.499 | 19,035,144 | 0.284 |
| whole processes munmap | 16,512,731 | 6.345 | 16,512,731 | 52.540 | 22,489,593 | 0.337 |

Dispatch is nested within the shadow phase for these requests. Shadow intervals
also overlap across requests, and return/handback timers have different ending
conditions. Summing these values does not give wall time, CPU time, complete
request latency or critical-section ratio. Whole means mix cold local routing,
earlier image generations and later execution; they are not final-window means.

## Publication and the translated completion path

All following times use the saved CLOCK_MONOTONIC metrics, in seconds since boot:

| Event | Time/bound |
| --- | --- |
| Thread measured interval | 772.820647621-782.821852534 |
| Thread mmap g7 publication inferred interval | 775.738643144-775.748059021 |
| Thread munmap g7 compilation finishes | 825.977631959, after application |
| Final thread g8 compilation finishes, mmap/munmap | 902.908163159 / 953.021564712 |
| Process measured interval | 1742.986208833-1752.987197106 |
| Process mmap g5 publication inferred interval | 1554.999078702-1555.009098133 |
| Process munmap g6 publication inferred interval | 1743.359707308-1743.471874931 |
| Final process munmap g7 compilation finishes | 1856.648301922, after application |

Publication intervals are source-supported inferences from successful serial
compile -> upload -> next child launch, matched by per-root generation/final
chunk counts. They are not directly logged publication events. In particular,
`sys.c:323` prints a final chunk before copying/validation/publication, and its
printk clock is not calibrated to the observer clock here. Raw chunk timestamps
are retained separately in `analysis.json`; they are not substituted for exact
publication times. The last thread publication lacks a timed upper bound.

Only the final process mmap g5 assembly was present during its observed positive
return interval. It contains translated `unmapped_area_topdown` and
`mas_wr_node_store` bodies, and the witnessed assertion forward/return edges.
In the retained epoch-002 g5 `jit.S`, lines 128434/141387 contain those bodies,
and lines 180384/184336 contain the assertion dispatches. At line 100586,
`loc_ffffffff817b6fd9` emits actual CALL word `0xffffffff817b6ff9` and jumps to
`kd_mmap_write_unlock_clobber_v1` (`0xffffffff814f4f70`).

The runtime maps that operation to UP_WRITE (`service_control.inc:38`), releases
the exact retained owner (`kd_service.c:975`), and returns RUN_TO_UNLOCK only
when outer/all ownership obligations are released (`continuation.inc:640`).
This concrete translated route matches observed process mmap completion; it
does not prove every possible mmap branch is covered.

Other exercised roots were still learning specific reached paths:

| Root | Actual sampled pending/reached targets | Static final-image limit |
| --- | --- | --- |
| threads mmap | query RET pair, then CALL `is_mergeable_anon_vma` | g8 contains these, but was not exercised afterward |
| threads munmap | CALL `anon_vma_interval_tree_insert`; a native-accepted IP there | final g8 contains its body; old g6/g7 assembly is not retained |
| processes munmap | `unmap_single_vma`, then `unlink_anon_vmas`; sampled native-accepted IP at former | final g7 contains them, but was not exercised afterward |

The retained images include only thread g8/g8 and process g5/g7, plus duplicate
workspace copies. They cannot reconstruct every instruction/exit of earlier
generations. Final NORMAL/static coverage is not evidence that final images
remain unable to return. Neither is it proof that their new paths worked.
CALL reports lack the CALL instruction address; IJ report addresses may be
return-dispatch keys. Exact sampled tuples remain in `sampled-misses.json`.

## Origin services are different from permanent handback

Process mmap g5 has a service-exit stub for `kd_service_write_owned`
(`0xffffffffc0e28370`, `jit.S:185276`) and `kvfree_call_rcu`
(`0xffffffff817ca480`, `jit.S:184611`). Registered-target recognition in
`exe.c:599` selects ORIGIN_CALL, followed by executor resumption, rather than an
unknown CALL's permanent handback. Process snapshot progress-07 records mmap
continuations SUSPENDED with origin-call RUNNING/DONE at these targets while
the current image is g5 NORMAL. This supports actual service activity, not its
per-request frequency.

`kd_rwsem_provider.c:471` declares `kd_service_write_owned` as ATOMIC_ORIGIN.
`kd_service_origin_primitive()` checks the logical origin and invokes its bridge
on that task (`kd_service.c:493-532`). The executor waits for DONE and resumes
the same retained frame (`:836-879`). Unpinned services also redo the allowed-mask,
active-origin exclusion and CPU/frame binding in `kd_service_pin_cpu`.

This is a remaining difference from the approved direction of executor-local
pure ownership queries (`docs/design/compiled_mm_continuations.md:839`). The
public assertion body is JIT translated, but its delegated ownership helper
still takes an origin service. It is not sufficient to change the context enum:
`kd_service_write_owned` first requires `task == current` (`kd_service.c:359`),
whereas the source query carries the logical task. An executor route needs exact
logical-origin/ownership token validation and preserved CALL/return semantics.
No such redesign is made or implicitly authorized by this analysis.

Permanent handback has a separate retained dependency. `kd_service_handoff`
(`kd_service.c:988-1021`) explicitly retains E-owned gates and E-stack ownership
anchors, publishes NATIVE_READY and waits in `kd_exec_native_wait` before the
worker finishes this root. It does not make the executor reusable at initial
packet transfer. This differs from the earlier immediate physical-transfer/
executor-reuse target. The exact completion condition matters: transferred
Native read custody may satisfy it without waiting for the entire read tail
(`kd_service_native_finished`, `:734-752`). Do not assume every handback keeps E
through the whole suffix, or infer that delay from shadow timing, which has
already ended. An independent service worker also has no private pending writer
to requeue. External semantic failure is not demonstrated by this dependency;
its capacity/CPU cost is unmeasured here.

## Workload, CPU and contention limits

The exact clean upstream source at `75f66e45697e6f5f49c33dd950c4e6b289198f8f`
exists locally. `tests/mmap1.c:6-18` maps private anonymous 128 MiB, immediately
unmaps, then increments the counter. It does not touch mapped pages; this is not
direct data-page-fault evidence. `Makefile:15-19` selects pthread (`main.c:103-140`)
or fork (`:175-220`) workers. Saved TGIDs and masks agree: one TGID for threads,
eight TGIDs for processes, each worker pinned to its CPU 0-7. This supports the
shared-mm versus distinct-mm interpretation, without direct saved mm addresses.
Distinct mm objects do not imply absence of all shared kernel resources.

Thread local acquisition means 77.322/113.150 us versus process 0.284/0.337 us
are consistent with more shared-mm admission contention. They cover the earlier
local phase, not critical-section time or the final window. This cannot explain
all of either 98% regression, especially independent process mmap requests.

Whole-application RUSAGE_CHILDREN from `bench/mmap1/run.py:433-439`:

| Model/mode | User CPU s | System CPU s | Total CPU s | Voluntary switches | Involuntary switches |
| --- | ---: | ---: | ---: | ---: | ---: |
| threads Native | 35.569 | 5613.747 | 5649.316 | 8,087,814 | 9,466 |
| threads KD | 2.093 | 5803.800 | 5805.893 | 756 | 5,672,079 |
| processes Native | 190.703 | 5619.007 | 5809.710 | 747 | 225,136 |
| processes KD | 13.973 | 5566.032 | 5580.005 | 749 | 20,797,825 |

These are reaped application/worker totals over the whole lifetime, excluding
separately running executor kthreads and translation children. They are not
ten-second CPU measurements or total KD CPU cost. Fewer KD thread voluntary
switches do not support blaming increased origin sleeping. Increased involuntary
switches establish scheduling activity, not its exact cause or timing.

The configured executor pool 0-61 overlaps workload CPUs, but pinned JIT execution
excludes all active origins (`kd_service.c:768-802`); workers are not fixed one
per CPU. Saved diagnostics show 46 selected executor observations: one thread
record on CPU58, and 45 process records with 16 on node 0 and 29 on node 1.
None uses CPU0-7 or its recorded origin CPU. These are concurrent snapshots,
not time shares or placement-frequency estimates. Initial claim/admission and
unpinned service phases have different placement rules. Compiler/daemon effective
affinity was not recorded; host `taskset -c63` captures do not establish it.
Idle workers use exclusive waits (`kd_service.c:1246`), so 62 configured workers
must not be treated as 62 continuously runnable workers or a proven wake-all herd.

Cross-node requests are observed, but memory placement, cache-line transfers,
PMU traffic, per-lock wait, executor jiffies and queue/admission durations are
unmeasured. CPU contention and NUMA cost remain plausible contributions, not
quantified causes. Per-CPU observation increments/clock reads and active
translation/publication add work; no matched observer-disabled control exists.
Counter overhead and translator CPU interference cannot be isolated here.

## Smallest next decision

First separate unfinished learning from steady execution. In a future owned
session, keep the factory/source lifetime open after learning settles, verify
its actual current NORMAL images, and run one short eight-worker application
before retirement. Expect unchanged generations/statuses, no no-image routing,
exact drained conservation, and retained completion or an identified reached
handback for each root. The current session is retired: raw g8/g7 bytes or old
context pointers cannot be reused. A fresh session needs current identities,
source leases and ordinary validated publication; any learned seeds must be
rebuilt/rebound, not blindly uploaded.

This is a proposed diagnostic, not a new accepted comparison against the long
baseline. If stable images still have a large gap, inspect complete request and
origin-service costs, with a narrow placement control only if needed. The most
concrete optimization candidate is the ownership query's origin exchange, but
moving it to the executor requires a reviewed logical-task/token design rather
than flipping ATOMIC_ORIGIN. Pairing encountered indirect CALL/RET learning can
reduce compilation waves but cannot by itself explain or repair the already
returning g5 path's cost. These choices require design confirmation before any
implementation; none is executed here.

Normal recovery remains the recorded boot `e994319f-cc52-42b5-b9f9-8bd2b239cc2b`,
Build ID `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, with verified idle state.
That is the preceding run's receipt; no new live verification was performed.
