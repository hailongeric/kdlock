# Kernel 8 AUX source review and conditional stack budget

This archive preserves read-only source and compiled-object inspection for the
bounded real-syscall MM prefix proposal. The final conditional total is
**44,024 bytes**, within a 64 KiB declared control requirement and a 128 KiB
auxiliary allocation. Two inclusive 16 KiB native allowances rely on the user's
separately selected **experimental premise**. They are not measured native call
trees or proof of the complete auxiliary-stack requirement.
[Conditional analysis](analysis/conditional-budget-04.json),
[separate user premise](experimental-admission/user-premise.json)

No provider activation, actual MM dispatch-input receipt, delegated MM execution,
new progress architecture or performance result is established here. The source
generation of a proposed configuration remains separate from its later actual
use. The conditional analysis keeps `native_budget_premise_accepted=false` and
`aux_flag_set=false`; user acceptance is retained in another file rather than
rewriting those source-review findings.

## Exact inputs and capture history

The linked kernel core is `0d42063ead37dc8fc1631fa56c8348890ede9c5f`, release
`7.0.0-38-kdrebuild8`, Build ID
`a33dd4d11d0f0c6649107507e685b6e86e716c1a`. The recorded running boot is
`e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0`, taint 4096. These are same-boot inspection
records, not a later fresh-boot or workload result. Before and after checks retain
the 16 linked outputs, source/protected maps, package 78 hashes and idle identity.

| Capture | Selected payload | Result |
| --- | --- | --- |
| Native context source 01 | 11 files / 693,911 bytes | Exact kernel configuration and scheduler, IRQ, task-switch and stack-inspection sources |
| Frame-pointer source 02 | 3 files / 61,753 bytes | Active frame unwinder, stack classifier and native entry assembly |
| Object attempt 01 | 0 of 144 inspection commands | Failed before dispatch because standalone `kernel/sched/wait.o` was absent |
| Scheduler discovery 02 | Exact source and object inventory | `build_utility.c` includes `wait.c`; the Makefile builds `build_utility.o` |
| Corrected object capture 02 | 292 files / 9,569,064 bytes | 36 existing objects, 144 inspection commands, all return codes zero |
| Runtime metadata | Bounded CPU, tracing and module observations | No knobs changed; unchanged kernel and idle identity |

The failed attempt remains failed. No fallback, rebuild or inspection command
ran during it. The corrected plan used the actual discovered build composition
and a fresh output leaf. It inspected 33 existing KD objects, the rebuilt
provider object and the scheduler core/utility objects. No object was executed.
All 288 command output streams match their exact recorded hashes.
[Failed controls](source-host/object-capture-failed-01/dispatch.stderr),
[scheduler discovery](scheduler-discovery/stdout.json.gz),
[corrected result](object-capture/collection/payload/capture/result.json.gz)

The corrected result's raw SHA-256 is
`5a49b6efa7f3c21201508cdbd724fa9da1d22aa03439e2d856dddb54406873f7`.
Debug frame sections are present in 32 of 36 objects. They are absent from
`exports.o` and the three native assembly objects; absence was recorded rather
than counted as a successful stack proof. Frame-pointer CFA data alone does not
include every local RSP reservation, so the review also uses instruction bytes,
register saves, outgoing call space and exact source callback bindings.

## Functional scope

The proposed four source regions total 1,558 bytes: `vm_mmap_pgoff`,
`__vm_munmap`, `its_return_thunk` and `__x86_return_thunk`. The exact acquisition
continuations are `0xffffffff817ef5ea` and `0xffffffff8185b00e`. The omitted
`do_mmap` and `do_vmi_munmap` calls permit handback before their fentry, GS,
RCU and plain-spin effects. An enabled acquire-returned trace call can stop the
prefix earlier. Native MM bodies and syscall semantics remain unchanged.

The source review follows the existing task-owned auxiliary stack switch and
exact original-task handback. Native context switching saves and restores the
actual RSP. The IRQ helper records its incoming RSP, runs handlers on its own
stack and restores that pointer. The scheduler's stack-end check addresses the
retained original task stack. The active frame-pointer unwinder can stop at an
unknown auxiliary range before following lent source-stack words; diagnostic
traces can be shortened. This is scoped functional source evidence, not complete
diagnostic-unwind equivalence or coverage of every exception configuration.
[Source callgraph](analysis/narrow-source-graph.md),
[native source index](native-source/collection/copy-index.json),
[frame source index](frame-source/collection/copy-index.json)

The actual configuration selects `UNWINDER_FRAME_POINTER`, `VMAP_STACK` and
`SCHED_STACK_END_CHECK`; ORC, `DEBUG_ENTRY`, debug stack usage and KASAN are off.
CPU0 flags omit `fred`; `/proc/xen` and `/sys/hypervisor/type` are absent. The
inventory records current tracer `nop`, empty enabled functions, function
profiling 0, stack tracing 0 and no livepatch entries. Global tracing and ftrace
remain enabled. These observations do not themselves establish text immutability,
future exclusion of other observers, native stack usage or MM-user exclusion.
[Exact runtime inventory](source-host/runtime-metadata/stdout.json.gz)

## Conditional sizing

The admitted source has no translated native callee or nested source operation
before handback. A cohort limit of two repeats service sequentially. The reviewed
maximum named KD control depth is 27; the original source bootstrap unwinds
before switching to AUX. Cold fragments inherit the hot frame rather than
creating another hardware return word. Their fixed reservations and an extra
return word are nevertheless included as conservative overcounts.

| Component | Charged bytes |
| --- | ---: |
| 27 KD depths, each using the measured maximum grouped C reservation 392 plus whole-unit alternative reservation 16 | 11,016 |
| Trace iterator, provider observer and separate readiness allowance | 96 |
| Generated wrapper 136 plus one balanced physical lowering temporary 8 | 144 |
| Inclusive unchanged-native-helper experimental allowance | 16,384 |
| Separate inclusive interrupt-entry experimental allowance | 16,384 |
| **Conditional total** | **44,024** |
| Declared control requirement / remaining margin | **65,536 / 21,512** |

Every named C body in the relevant `.text` and `.text.unlikely` units contributes
to its unit maximum. The explicit cancellation witness totals 3,064 bytes with
missing or inlined wrappers charged another grouped unit maximum; it totals
3,304 bytes with its exact unit alternatives. Each such wrapper identifies its
already counted, locally closed enclosing hot compiled function. The wider
27-depth formula supplies the final conditional overcount.

The provider replacement payload has no fixed positive RSP reservation. The
observer branch is iterator 32 plus observer 48 plus another 8-byte replacement
CALL word, or 88 bytes. Readiness completes separately and uses at most 24 bytes
with the same added word. The charged 96 covers either branch. The trace static
call trampoline is jump-only. Native callees remain within the explicitly
unmeasured inclusive allowance.

The final manifest lists unknown forms, CFG exceptions and manual assembly
closures explicitly. The remaining unused `kd_jit_resume_origin` fallthrough
ends in the declared nonreturning `kd_native_resume` transfer. The source/stack
callbacks and observations retain their exact bindings. No unresolved dynamic
RSP write was silently dropped from a maximum. Earlier conditional analyses and
preliminary weights remain as superseded evidence; final weights 04 bind the
retained final parser. [Final weights](analysis/weights-04.json.gz),
[parser](analysis/stack-weights.py), [final conditional analysis](analysis/conditional-budget-04.json)

The actual 16 KiB `THREAD_SIZE` extent is independently visible as
`add r8,0x4000` in `source_stack.o`. That allocation constant does not measure
native helper usage. The separate user record accepts the native allowance as
an experimental premise and explicitly leaves full AUX and native callback-tree
proof false. Its SHA-256 is
`db233cd8ac3164d3170c071ecc7081c9e58141f93cbf0b147f700dab761f5a1b`.

## Retained bytes

The original raw manifest contains all 450 inputs, totaling 32,949,760 bytes,
with exact file identities and hashes. All three complete collection transports
are preserved and independently matched to their selected payloads: 306 files
and 10,324,728 bytes in total. No complete transport tar is omitted.
[Raw input manifest](input-manifest.json.gz), [copy provenance](copy-index.json)

The archive copies those inputs, the raw manifest, the separate experimental
admission record and its archival script: 453 copied files, 33,138,508 raw bytes
and 6,340,690 stored bytes. Forty-one files use lossless gzip, with exact raw and
stored hashes and readback verification. No `.o` or `.ko` binary was selected;
the existing objects are identified by their captured identities, hashes and
complete inspection output. `SHA256SUMS` covers every retained file except
itself. Historical controls are records of past commands, not instructions to
replay. [Byte audit](audit.json), [archival procedure](archive-copy.py),
[checksums](SHA256SUMS)

The archival audit uses only source-host standard-library file, hash, tar and
metadata inspection. It runs no project import, behavioral test, build, provider
activation or VM workload. Actual MM run inputs, execution, observations and
retirement belong in their own later receipts.
