# One-round long-warmup mmap1 comparison

Both task models completed application checks, postrun settlement and exact
retirement. Performance remains **unaccepted**. Process mmap completed
4,199,281 retained returns; munmap and both thread roots completed through
handback. Both measured windows contained image publication. The executor
downgrade/read-tail/later-writer criterion remains unproved.

## Inputs and bounds

Runtime/provider/daemon bytes remain
`ec623366622d1784f7e819b4e9031ba0482bee9b`, kernel component
`9a5d606aee0249d0e566a1c9667375eb038bc9cd`, Build ID
`357a7115d21941960b90262ac1165bf70d1b398e`. No lock protocol, source body,
publication/admission rule or lifetime check changed. The maintained branch was
not merged. Original will-it-scale applications at
`75f66e45697e6f5f49c33dd950c4e6b289198f8f` invoked actual userspace syscalls.

Selected writer roots remain mmap `0xffffffff817b6f68` and munmap
`0xffffffff8181c73b`. Each model/mode ran once at eight workers. Native/off and
KD/on used the same installed image with separate verified modes. Application
workers used CPUs 0-7 on node 0; KD used `service_cpus=0-61` across both NUMA
nodes; the collector used CPU 63. Host pinning, recovery snapshot and fixed
2.0 GHz policy passed fresh before/after checks. This is an exploratory
Native/KD comparison, not execution-wide same-NUMA or strict timing evidence.

The preceding short run selected `long_warmup=False`, one round and a shared
300-second learning budget to check the builtin restore correction after a
failed long attempt. It did not fulfill the long-warmup objective. This run
used the existing `long_warmup=True` path: `-s724`, 730 total samples, with the
last ten measured after 720 pre-window samples. The application bound remained
800 seconds. The shared learning budget was 1,800 seconds: 730 application
seconds plus two observed 291-297-second translation allowances and about
476 seconds for admission/settling. Controller/finalizer/transport bounds were
2,000/90/2,200 seconds. No point or deadline was repeated or extended in flight.

Native boot: `a6948c09-4888-4c49-bf94-c7141f8e2d56`.
KD boot: `fb9f0bb4-2e63-4791-889d-11bb14507c86`.
One fresh Native host capture failed before any reboot/workload; its receipt
remains separate, and one further strict admission attempt passed.

## Rates and actual windows

| Model | Native pairs/s | KD pairs/s | KD difference |
| --- | ---: | ---: | ---: |
| threads | 225,631.9 | 3,641.5 | -98.39% |
| processes | 1,554,416.0 | 21,074.8 | -98.64% |

Each rate uses the final ten samples and nominal ten-second divisor. Delivered
sample boundaries independently recorded:

| Model/mode | Pre-window elapsed | Measured elapsed | Whole application |
| --- | ---: | ---: | ---: |
| threads Native | 720.126606 s | 10.001122 s | 730.178937 s |
| threads KD | 720.123350 s | 10.001205 s | 730.157022 s |
| processes Native | 720.125209 s | 10.001199 s | 730.130406 s |
| processes KD | 720.120779 s | 10.000988 s | 730.158067 s |

These boundaries include line transport/callback latency and are not atomic
with application counters. Frozen observation prose still says six warmup/two
measured samples; the command, 730 parsed samples and sample-window receipt
establish the actual duration. KD kept translation and selected-service counters
active. Its rates remain learning observations, not quiet scores. Do not pool
them with the short configuration or describe them as gains from a code change.

## Execution and image evidence

Whole-application observations, including warmup:

| Model/root | Local, no image | Submitted | Retained returns | Completed handbacks |
| --- | ---: | ---: | ---: | ---: |
| threads mmap | 2,363,514 | 3,712,286 | 0 | 3,712,286 |
| threads munmap | 3,045,681 | 3,030,116 | 0 | 3,030,116 |
| processes mmap | 19,035,144 | 19,967,185 | 4,199,281 | 15,767,904 |
| processes munmap | 22,489,593 | 16,512,731 | 0 | 16,512,731 |

Whole-application conservation passed. During the measured observer interval,
thread mmap and munmap each recorded 36,415 handbacks and zero retained returns.
Process mmap recorded 210,740 retained returns and zero handbacks; process
munmap recorded 210,738 handbacks and zero retained returns. Boundary deltas
include requests in flight and serial counter reads, so they need not equal
the application's pair count or each other.

`returned` requires the retained run-to-unlock route, released scope ownership
and continuation return. `jit_entered` alone records generated-wrapper dispatch.
Neither counter separately identifies a downgrade, another task executing the
read tail, or a later executor writer acquisition. Physical batch length,
whole-CS ratio and per-service runtime shares were not measured.

| Model | Window begin mmap/munmap | Window end mmap/munmap | Final settled mmap/munmap |
| --- | --- | --- | --- |
| threads | g6 IJ / g6 CALL | g7 CALL / g6 CALL | g8 NORMAL / g8 NORMAL |
| processes | g5 NORMAL / g5 CALL | g5 NORMAL / g6 CALL | g5 NORMAL / g7 NORMAL |

Thread supersession increased by 9,103 during measurement. Process supersession
was zero in all retained snapshots and both window boundaries. Both windows
contained publication. Final NORMAL/zero-frame settlement does not prove that
the final images were exercised by another application or make the earlier
window stable.

Process mmap snapshots show continued handback progress with the same pending
generation: g3 CALL at monotonic 1302.432062020 and 1366.457560465 seconds advanced
completed handbacks from 9,564,617 to 11,447,903; g4 CALL at 1448.689865808 and
1548.103805971 advanced them from 13,412,608 to 15,615,939. Retained returns were
zero at all four endpoints. The positive-return interval was g5 NORMAL.
Therefore these records support continuing dispatch/handback with an eligible
pending image, but do not demonstrate retained completion while pending.

## Exact reached learning

Loaded-module maps matched the expected note and KD boot. In this run,
`0xffffffffc0e32fb0` resolves to `kd_provider_assert_held_write` and
`0xffffffffc0e32a50` to `kd_provider_is_locked`. The old short-run address lacked
its own module map; its attribution remains a source inference despite the new
boot using the same address and module bytes.

| IJ report from | Target | Meaning supported by source/image evidence |
| --- | --- | --- |
| `0xffffffff814f4a38` | `0xffffffffc0e32fb0` | Assertion forward edge; from is the original CALL return address |
| `0xffffffffc0e32fec` | `0xffffffff814f4a38` | Assertion callback return-dispatch edge |
| `0xffffffffc0000f22` | `0xffffffffc0e32a50` | Forward edge to provider query; source address remains unnamed here |
| `0xffffffffc0e32a67` | `0xffffffff814f469a` | Provider query return to `kd_mmap_is_locked` |

Process roots learned the assertion forward/return pair; thread roots learned
all four pairs. [sampled-misses.json](sampled-misses.json) retains exact sampled
roots, generations, tuples and timestamps. CALL reports do not retain their CALL
instruction address. Cumulative learned CALL targets were:

- Thread mmap: `unmapped_area_topdown`, `anon_vma_name`, `is_mergeable_anon_vma`.
- Thread munmap: `anon_vma_name`, `anon_vma_interval_tree_insert` twice.
- Process mmap: `unmapped_area_topdown`, `mas_wr_node_store`.
- Process munmap: `memcpy`, `mas_leaf_max_gap`, `unmap_single_vma`, `unlink_anon_vmas`.

The assertion callback is not intentionally excluded: retained assembly contains
its instructions. `disassem/indirect_jump.py:42` automatically pairs direct CALL
returns. Learning an indirect forward target does not itself add that caller
continuation to the callback RET table. `disassem/memread.py:174` imports later
RET history. The epilogue reads and advances virtual SP once; on a missing edge,
`kernel_module/execution/wrapper_entry.inc:303` reports the post-RET packet for
handback without replaying RET. The observed return target matches the exact
builtin continuation. This supports incremental return learning, not a
demonstrated incorrect stack join.

A thread snapshot at monotonic 710.123153049 seconds showed a native-accepted
continuation (`state=7`, `transport=4`) at `anon_vma_interval_tree_insert`, matching
a pending CALL target. Process snapshots also showed native-accepted
continuations at `unmap_single_vma`. This diagnostic view is concurrent, not an
atomic per-request trace; a consumed `call_target` may describe an earlier
service. It cannot attribute every handback or distinguish all CALL/IJ misses,
source/context frontiers and release boundaries. Per-request tracing stayed off.

## Reports, acknowledgment and cost

`kernel_module/execution/images.inc:291` accepts current-image reports and
coalesces identical current status/target/from tuples. Different tuples advance
revision and may increment supersession. That counter does not identify whether
a replaced tuple was already consumed or prove lost coverage. `sys.c:208` keeps
the writer's first successful read receipt per generation; `sys.c:295` binds it
to upload. Publication at `images.inc:217` clears pending only if the
base-generation/revision receipt matches. This conservative rule can require an
extra compile. Daemon command reuse includes generation, allowing duplicate
table rows; the decoder deduplicates their target set. Exact per-event revision
and acknowledgment history was not logged. No distinct-report-loss defect or
publication/queue correction was demonstrated.

Threads completed 16 translations totaling 899.422 child wall seconds, maximum
76.822 seconds. Processes completed 12 totaling 832.969 seconds, maximum
123.443 seconds. These serial phases overlapped the application and continued
afterward. Short-run children took about 46-51 seconds. The new records show
further CALL/RET learning and increased compilation cost as callees are added;
they do not isolate runtime costs of queueing, instruction services, NUMA traffic
or scheduling.

The finite larger budget allowed settlement. It did not yield stable images by
measurement or complete munmap's retained return path. Extending it again alone
would not repair learning cost or establish the executor read-tail criterion.
A bounded next optimization to evaluate is pairing an encountered indirect CALL
with its exact source continuation when learning its callee, retaining existing
return-word checks. Reducing repeated complete-image compilation also needs
measurement. Neither change was implemented or credited with gains here.

Both controllers exited zero; every application returned and drained. Fresh
finalizers reported `retirement_passed=True`, zero frames/modules/writers and
idle state. Pilot finalization's overall `passed=False` denotes the unscored
performance campaign, not failed retirement. Signal cancellation, nested API
equivalence and executor read-tail attribution were not separately exercised.

The normal `7.0.0-38-kdlock1` kernel was restored and verified: Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`e994319f-cc52-42b5-b9f9-8bd2b239cc2b`, final idle. No further workload ran.
[summary.json](summary.json) retains full counters, windows, targets and hashes.
All 156 guest receipt/image files (110,773,288 bytes), plus source-host launch,
progress and identity records, remain in both checkouts beneath
`bench/results/10.176.26.71/raw/bench/mmap1-long-ec623366-20261107/`.
The guest record-index SHA256 is
`81e6cbc9b5c0024b691c7ba4325b3ce6174ce59b93b28a00d69d5a5568f08c59`.
