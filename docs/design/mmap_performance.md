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
This avoids waiting for the observing controller's own live MM object to be
destroyed while that controller is still running. Emit an explicit pending
retirement stage; only the subsequent exact cleanup completes the point. A
failed application or unknown profiler lifetime leaves state for diagnosis.
Never force an unload, detach a live object or relabel a timeout as drain.

Throughput is the unchanged upstream's measured mmap/munmap pairs per second.
Queue admission and interpreter/Native service costs are included naturally.
Profiler samples and trace-enabled request durations are separate diagnostics.
The workload maps/unmaps128MiB anonymous ranges without touching their data;
these results cannot establish demand-page-fault throughput.
