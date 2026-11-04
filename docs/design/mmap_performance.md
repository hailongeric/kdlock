# Delegated mmap performance iteration

The starting branch is `codex/mmap-performance-iter1`, from documentation
checkpoint `1628183c66bfb693479b970c295a0b7708e40aac`. Its verified runtime is
`111170d533fa4ac37bbcc1f641c364a694f9f7e6`. Master remains separate. The first
iteration uses two workers in both unchanged will-it-scale mmap1 models, the
only worker count with current complete delegation evidence. Keep every
successful, failed and unrun result separate by source, boot and instrumentation.

The previous trace-enabled diagnostics averaged81 pairs/s for threads and159
for processes. Their mean entered-request durations were4.880/7.285ms for
thread mmap/munmap and5.574/6.935ms for processes. Those values include detailed
runtime records and Native instruction/API services. They are not a Native
throughput comparison. The engine is the resident reached interpreter with an
instruction-byte cache. Actual compiled-region performance is not established.

## Measurement and optimization sequence

1. Verify current source, exact kernel image/configuration, idle state, real
   recovery snapshot, fixed host frequency/pins and root/build disk headroom.
   Use the existing scope5 KD and Native plain boot profiles for throughput,
   with the same image, lazy preemption and log configuration apart from the
   explicit MM backend mode. Do not pool the log16 correctness profile into
   these throughput series.
2. Profile the baseline thread workload at two workers using kernel cycle
   samples and call chains, retaining the raw recording and application time
   window. Hardware cycle availability has been checked on the VM. This
   diagnostic is a separate instrumented run. Then measure one unprofiled
   upstream lifetime per model with detailed service tracing disabled.
3. Attribute sampled cost to the actual source paths before implementation.
   Candidate areas include repeated current-instruction source reads, family
   cache lookup/publication, register checkpointing, shared instruction
   statistics, Native instruction/API round trips and request dispatch. A low
   cache hit counter alone does not establish which of these dominates.
4. Document the selected bounded change before implementing it. Preserve the
   general API and all MM bodies, original signals, actual acquisition before
   cancellation, local reads, delegated downgrade tails, nesting and exact
   source/frame/owner retirement. Optional cache storage must never authorize
   instruction execution or turn a miss into origin-body execution. Preserve
   complete current instruction bytes, source residency and return routing.
5. Run directly affected production fixtures and VM builds, then remeasure
   both models once at the same point and settings. Retain regressions. Run
   detailed delegation validation separately on the candidate, including
   returned other-task bodies, downgrade/read release, subsequent writers,
   Native services, exact family records and normal final retirement.
6. Measure Linux Native with the same workload, image/topology/pins and plain
   profile settings. Report baseline KD, candidate KD and Native separately.
   Do not promote the candidate on an incomplete functional or performance
   result. Nano acceptance remains separate and must not be inferred from MM.

## Process lifetime and timing boundaries

One performance controller owns one model/point and records its exact immutable
provider, source, executable and site identities. The provider is active for
the whole application lifetime; no caller/body shortcut is introduced. The
ordinary runner checks placement during warmup, normal application exit and
worker disappearance. Detailed service trace records are disabled only in the
timed class. Existing exact ownership/source/frame checks remain active; current
returned-root counters are recorded before and after the application. Those
counters are progress evidence, not a substitute for the separate full trace.

After normal application completion, deactivate future binding and allow both
the controller and profiler to exit. A fresh process then requires zero object
bindings, frames and writers before ordinary source retirement and unload.
This allows residual bound MM objects to finish their ordinary lifetimes.
The binding count alone does not identify which task or deferred release
retains an object. Emit an explicit pending
retirement stage; only the subsequent exact cleanup completes the point. A
failed application or unknown profiler lifetime leaves state for diagnosis.
Never force an unload, detach a live object or relabel a timeout as drain.

Throughput is the unchanged upstream's measured mmap/munmap pairs per second.
Queue admission and interpreter/Native service costs are included naturally.
Profiler samples and trace-enabled request durations are separate diagnostics.
The workload maps/unmaps128MiB anonymous ranges without touching their data;
these results cannot establish demand-page-fault throughput.


## First setup failure and a reached arithmetic addition

The first baseline profiling setup stopped at the unchanged source/family
quiescence requirement before an application point was created. Its initial
cause is not inferred from a later event. A subsequent ordinary diagnostic
connection reached `get_page_from_freelist+0x2c9`, `ffffffff81828ca9`, under
`lock_mm_and_find_vma` and reported GS prefix65 with status-95. The matching
scope5 ELF identifies `65 48 03 1d 77 23 be 02`: ADD of the original CPU's
`this_cpu_off` value into RBX. Static bytes identify the point; the reached
decoder must freshly validate the full actual instruction before execution.

Add reached-only `KD_ORIGIN_MEMORY_ADD` operation8, using the existing retained
Native instruction channel. Support32/64-bit GS-source register ADD with the
same decoded addressing as SUB; preserve the old destination register input,
execute actual Native ADD on the origin, and commit result/arithmetic flags
only after its exact ACK. Preserve source SP, the two-word wrapper and cold
record layout. Image publication continues explicitly to refuse this new
operation until its own backend supports it. Test addressing, result widths,
carry/overflow and flags against actual Native ADD, plus the trace join.
This supplements one reached instruction; it does not move an MM body back
to the origin or bypass acquisition/cancellation.

The runtime source correction precedes a fresh profiling attempt. The setup
also needs a deterministic profiler-ready boundary or bounded exact quiescence
retry; no successful profiler/application run is inferred from the failed
setup. Preserve its raw recording, configuration, console and original error.

Source review additionally shows that `kd_mmap_init()` binds the provider at
object initialization and unregister affects only future objects. Earlier
attribution of residual leases specifically to the observing controller's
own MM was an inference from exit timing, not verified ownership. Retain the
observations and correct that attribution: the fresh retirement step is valid
only because it actually observes zero bindings/frames/writers, irrespective
of which ordinary object lifetime delayed the count.


The VM's installed perf recorder reported `Thread and evlist pollfd index
mismatch` when using its control-ack interface. That setup stopped before
provider load or application execution. Retain this tool failure separately.
Use the recorder's ordinary workload-start ordering instead: its small Native
helper prints a readiness line after setup, then waits for20seconds. Activate
the provider only after receiving that line. The unchanged mmap1 executable
is still launched directly by the benchmark runner. Record only its actual
application time interval in the profile report; the helper is outside the
throughput class and does not alter any production MM path.
