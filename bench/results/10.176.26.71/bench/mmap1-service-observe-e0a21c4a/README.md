# mmap1 selected-path observation

The eight-thread diagnostic passed and drained, but almost all selected
acquisitions ran locally. Each entry submitted eight requests, entered JIT
eight times and completed eight permanent handbacks. No captured request
completed entirely through delegated execution. The candidate remains
unaccepted; this observation introduces no lock performance optimization.

Runtime source: `e0a21c4a1c043fbb7d77ca9a679f47e5cf7a6c90`, isolated branch
`codex/mmap-reached-jit`. Design preceded implementation in `3cc15f24`;
`328817076bbac8e17bfe2125609a450f63716a6d` added observations, and `f1956d5d`
documented the allocation correction implemented by `e0a21c4a`.
No merge was performed.

## Configuration and method

Unchanged will-it-scale revision
`75f66e45697e6f5f49c33dd950c4e6b289198f8f`, `mmap1_threads -t N -s 2 -m`.
One one-worker application primed fresh histories, followed by one eight-thread
application. Each had the upstream six warmup samples plus two nominal measured
seconds. The daemon was paused during each entire application; generation 1
images were available to the eight-thread application. Generation 2 was
published after it drained. No image changed during either application.

Kernel: `7.0.0-38-kdscope5`, Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`, `kd_mmap=on`, lazy preemption,
boot `cf5e0b99-3f9c-4d45-984b-bc42b95e05c7`. The 64-vCPU / 24-GiB VM has
two 32-CPU NUMA nodes. Requesters used CPUs 0–7, collector 63 and the existing
executor pool 0–61. Host pins, the 2-GHz/performance/turbo-off policy and the
existing recovery snapshot were verified. This is not a cross-NUMA comparison.

The active aggregate source budget remains 1,048,576 bytes, each source read at
most 262,144 bytes, with the original backend, 8-KiB lookahead, 4-KiB alignment,
32 combined transitions and 33 decode passes. The selected image pool remains
128 slots of 4 MiB; four slots were used at the end, with 124 free.

The optional `service_observe` counters match the exact origin task name
`mmap1_threads` and two selected source entries. They observe that task-name /
entry scope, rather than a per-TID allowlist. The existing syscall-shape
selector remains unchanged. Other entry/shape combinations remain local KD
users of the same lock object. Initial separate child images are scoped to
selected KD acquisitions; allocator and other Native locks retain their
existing instruction-service handling. This diagnostic adds no child-image
implementation or caller-specific MM body.

Counters are cumulative CPU-local values, allocated once at service
initialization. The existing controller reads them before and after the
application, outside its lifetime. No extra guest observer, per-request
logging, new protocol guard or packet/frame ABI change was added.
`jit_timing=0`, `service_trace=N` and the identity probe remained off.
The base application field `instrumentation=none` describes those existing
trace/probe facilities; the enclosing result explicitly records
`instrumentation=selected-service-counters` for this run.

Monotonic timestamps independently show zero overlap between these two
application intervals and four compiler jobs. Compiler wall time totaled
31.428659031 seconds outside application execution. The raw intervals and
hash-bound receipts are in `analysis.json` and `retained-files.json`.

## Counter definitions and results

`selected` counts matching capture-helper calls. `local` counts completed
ordinary local admission calls; `local_no_image` is the subset with no eligible
image. `submitted` counts retained requests immediately before publication.
`bound` counts successful binding to an executor. `jit_entered` checks the
existing frame's executed mark after its initial dispatcher call; it does not
prove completion of the source body. An explicitly refused unstarted root
clears that mark in the existing dispatcher.

`handback` counts publication of permanent Native continuation.
`handback_finished` follows the exact retained release/ACK join. `returned`
counts ordinary delegated completion. Published cancellation and cancellation
before publication have separate counters; local cancellation is also
separate. All cancellation and invalid-clock counts were zero here. These
applications did not exercise live cancellation.

The following eight-thread totals cover the whole application, including
warmup. Each entry passed all conservation checks.

| Entry | Selected | Local / no image | Submitted / bound / JIT entered | Handback / finished | Delegated return |
| --- | ---: | ---: | ---: | ---: | ---: |
| `0xffffffff817b6f68`, mmap | 408241 | 408233 | 8 | 8 | 0 |
| `0xffffffff8181c73b`, munmap | 408237 | 408229 | 8 | 8 | 0 |

Local acquisition share was **99.99804%** for both entries. These are request
counts, not instruction or CPU-time shares. The one-worker priming application
had 1,526,327 selected calls per entry, all local/no-image, and no submitted
request. There was no image during that application's paused-translation
lifetime.

Checks after drain established `selected = local + submitted +
prepublication_cancel`, `local = local_success + local_cancel`, and
`submitted = returned + handback_finished + canceled`. In this run, bound,
JIT-entry, dispatcher-sample and shadow-sample counts also matched the terminal
successful counts. These are root-request counts, not nested segment counts or
measured physical chain length. `physical_batch_length_measured=false` remains.

## Timing definitions and results

All new timers use `ktime_get_ns()` and measure inclusive elapsed time.

- Local admission: entry to return of `kd_service_local_acquire()`, which calls
  ordinary `kd_down_write_killable()` for these acquisitions. It includes
  contention, reader drainage, spinning and any scheduling inside that helper.
  Earlier capture/registry work and the protected body are outside this timer.
- Initial dispatcher: the first `kd_exe_on_retained_entry()` call through its
  return to service execution. This includes C dispatcher and generated-prefix
  execution. Later services/resumes and the Native suffix are outside it.
- Shadow wait: entry on the independent waiting stack through normal resume
  or just before Native acceptance. It includes polling, services and any
  scheduling in that interval, and overlaps dispatcher time. It excludes the
  subsequent Native body after acceptance and earlier publication/admission.

| Eight-thread entry | Summed local admission | Mean local admission | Initial dispatcher total / mean | Shadow wait total / mean |
| --- | ---: | ---: | ---: | ---: |
| mmap | 28.511605422 s | 69.8415 µs | 50.737 µs / 6.342125 µs | 87.400 µs / 10.925 µs |
| munmap | 29.112401189 s | 71.3139 µs | 39.312 µs / 4.914 µs | 63.347 µs / 7.918375 µs |

The summed local interval was **57.624006611 task-seconds**, across tasks that
can wait concurrently. It must not be compared additively with the 8.090715414-s
application wall time. In the one-worker priming application, mean local
admission was 0.286780185 µs for mmap and 0.286234399 µs for munmap. Different
contention and image states are explicit; these are not repeated controls.

Existing child-resource accounting recorded 0.09699 user CPU seconds and
63.96396 system CPU seconds for the eight-thread application, with 36 voluntary
and 190 involuntary context switches. These values include warmup and reaped
workers and exclude executor-task CPU time. Context switches are not parking
counts. The small voluntary count and nearly eight CPUs of requester CPU time
are consistent with heavy running/polling, but do not identify an instruction
or cache-line cost by themselves.

## Interpretation and performance boundary

The main verified limitation of this image state is low delegated coverage.
`kd_image_report()` publishes a reached miss for the current immutable image
(`kernel_module/execution/images.inc:256`); readiness requires
`KD_EXE_NORMAL` (`kernel_module/execution/registry_lifecycle.inc:54`).
`kd_service_capture_internal()` then finds no eligible image and calls ordinary
local admission (`kernel_module/kd_service.c:1593`). With translation paused,
publication of a more complete image waits until after application drain.
The observed eight handbacks followed by over 408,000 local admissions per
entry agree with that code path. A published prefix is insufficient evidence
of sustained delegated execution.

The dominant measured interval is local writer admission. Its source path is
`kd_service_local_acquire()` → `kd_down_write_killable()` →
`kd_rwsem_down_write_state()` → `kd_admission_wait()`
(`kernel_module/kd_service.c:1530`, `kernel_module/kd_rwsem.c:312`,
`kernel_module/kd_admission.c:340`). The admission loop repeatedly arbitrates
under `gate.wait_lock`, gives readiness priority over signals, and uses a
16,384-iteration budget before its scheduler conditions. The counters establish
which interval dominates; the precise split between that guard's contention,
reader drainage, spin instructions and scheduler delay is still unmeasured.
Those are bounded follow-up targets, not measured attribution to a specific
cache line. This observation does not change cancellation or ownership.

| Application | Native pairs/s | Observed pairs/s | Difference |
| --- | ---: | ---: | ---: |
| One-worker priming | 281886.5 | 190737.5 | -32.34% |
| Eight-thread diagnostic | 225144.5 | 51042.0 | -77.33% |

The [preserved Native controls](../mmap1-scaling-f9fdaa2a/README.md#native-results)
use the same experimental kernel Build ID with `kd_mmap=off`, upstream binary,
placement and sample definition. They were not rerun. The prior
[uninstrumented preliminary pilot](../mmap1-pilot-090ec98c/README.md) reported
49,296.5 pairs/s at eight threads. Its different observation policy and boot
remain separate; the numerical difference is not an optimization gain or a
repeatability estimate. Every present rate is unscored, one observation only.

No full critical-section held time, dynamic instruction count or
critical-section runtime ratio was measured. The actual generation-1 graphs
contain 152 source bytes / 43 decoded instructions for mmap and 165 / 39 for
munmap, including static alternatives; these are neither executed instruction
counts nor the full critical sections. The later generation-2 graphs contain
288 / 76 and 523 / 127. No fully delegated downgrade/read-tail completion was
proved. No processes, Nano, TCLock, cross-NUMA or steady-image comparison was
run in this focused phase.

## Validation, retained failures and recovery

The final candidate passed the production observation fixture (disabled/on,
allocation refusal/cleanup, local results, terminal conservation and clocks),
three Native continuation-join cases (write/downgrade/read, with supplied
physical/task primitives), nine existing controller cases, and the provider
module build with `W=1`. Unchanged daemon/probe source and artifact hashes were
verified and reused. Existing unrelated full-driver failures remain separate;
this was not a full suite or a fresh general API validation.

Two earlier setup/load outcomes remain retained. The first preflight expected
the callback getter in `modinfo -p`; the parameter definition was subsequently
verified directly. The initial module then refused loading because its 7984-byte
static per-CPU reservation did not fit the available reserved chunk. No
application ran in that attempt. The correction allocates optional observation
storage once with `alloc_percpu()` and frees it after service drain. The retry
used new committed, frozen inputs and fresh histories. No check was disabled.

Both final applications passed and drained. One residual binding reduced to
zero through bounded ordinary CPU activity. Exact retirement returned
`state=2, modules=0, frames=0, writers=0`, followed by ordinary unload and idle.
`pilot_data_passed=true`, `retirement_passed=true` and `final_idle=true`.
Strict `passed=false`, `accepted=false` and `campaign_complete=false` retain
their intended meaning because no strict proof/scoring campaign ran.

Normal kernel `7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, was restored on boot
`208cd2a1-f17a-4d89-b9bb-336b11049695`; idle and empty `next_entry` were verified.
VM records remain under
`/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/bench/frontier-e0a21c4a/kd/`.
The full result, counter snapshots/deltas, compiler intervals, source/build
identities, earlier failures and recovery receipts are retained by hashes in
`retained-files.json` and the corresponding raw evidence directory.
