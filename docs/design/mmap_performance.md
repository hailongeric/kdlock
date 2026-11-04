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
   samples, retaining the raw recording and application time
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

## Reached accounting arithmetic

The next diagnostic connection reached `ffffffff81828d5f` in
`get_page_from_freelist`: `65 48 01 04 d5 60 0e 42 84`, an indexed GS-memory
ADD using RAX. The current decoder supports register-destination ADD only.
The worker stopped. This occurred after the application had already returned;
it is not the cause of the application's earlier diagnostic failure. Recovery
preserves the recording and logs.

Extend the general retained instruction channel with memory-destination ADD
(operation9) and its read-only compare form (operation10). Both accept ordinary
32/64-bit scalar addressing, import the exact register operand, execute the
Native instruction on the original CPU and return arithmetic flags after ACK.
ADD changes only the addressed memory; CMP changes no operand. Neither writes
the captured source register. The read flag is explicit: operation9 is a write,
irrespective of its numeric value. Reject ADD overlapping the preempt count:
only the existing exact INC/DEC ownership protocol implements that transition.
Image publication continues to refuse both reached-only operations.

This is general scalar instruction support, with no symbol-specific branch or
upfront control-flow expansion. Validate indexed and RIP-relative addressing,
missing final bytes, source-register preservation, upper32-bit memory
preservation and arithmetic flags against actual Native ADD/CMP. The application
must return normally and retire before any throughput or profile is accepted.

The recovered application record shows normal exit,2142 completed roots and
130 pairs/s, but it failed the unchanged kernel-diagnostic check. Its actual
failure is perf's stack-frame-pointer warning during call-chain collection.
That rate remains an excluded diagnostic, not an accepted baseline. Use flat
cycle samples for the next profile: requesting stack unwinding across the
retained instruction bridge is not validated. Keep the diagnostic check intact;
this changes only the requested profiler data. Call-chain support is a separate
remaining limitation, and no call-path attribution may be inferred from flat
samples alone.

## First profile and bounded dispatch iteration

The flat two-thread profile completed with normal application return and exact
normal retirement. It recorded no lost samples. Within its application window,
22.24% of system-wide kernel cycles sampled worker-side queued-spin waiting;
11.55% sampled the origin's IRQ-save locking. Origin instruction-service polling
also occupied a substantial fraction. The first report did not resolve module
addresses because recording began before module load; retain those raw values,
and capture the actual module section addresses and symbol table before each
subsequent profile. Do not attribute unresolved addresses solely from assumed
module alignment. Flat samples identify cost locations, not complete callers.

Source inspection identifies two avoidable dispatch costs in `kd_service.c`.
Each ready-root notification calls `wake_up_all()` for the entire worker pool;
every awakened worker takes the same dispatch guard even when only one root
exists. Meanwhile, an origin whose custody is already on the executor repeatedly
takes that guard to discover it cannot arbitrate. Keep all guard-protected
selection, origin-signal cancellation, predecessor linking and retirement rules.
Use an acquire-read solely as a negative hint to skip arbitration while actor
custody says EXECUTOR; any attempt to arbitrate must still recheck under the
guard. A custody change after the hint is handled on the next iteration and
cannot authorize an origin action or cache an old object guard.

Wake one exclusive worker for each ready-root notification. Workers read the
work sequence before claiming and test it again when entering the wait, so a
publication between claim and sleep is not lost. Every notification corresponds
to one request, workers continue claiming queued work before sleeping, and
shutdown retains its direct stop wake. This removes the all-worker competition
without changing lock ordering, physical ownership or admission readiness.

The untraced two-thread baseline returned132 pairs/s. Its first fresh retirement
check observed nonzero bindings; a later exact retry observed zero and unloaded
normally. Add a bounded five-second wait for those same exact zero conditions
to the finalizer, recording observed counts. A timeout remains a failure;
neither the application nor any timed interval is repeated for cleanup.

The first dispatch build stopped because Linux7 has no
`wait_event_exclusive()` helper. No application ran on that revision. Implement
the same wait with `DEFINE_WAIT`, `prepare_to_wait_exclusive()` in
`TASK_UNINTERRUPTIBLE`, a stop/sequence recheck, `schedule()` and
`finish_wait()`. Registration precedes the condition check, so neither a ready
notification nor task stop can be lost between deciding to wait and scheduling.

The corrected dispatch revision passed all11 actual killable/nesting/downgrade
fixture phases. Its first untraced thread point returned170 pairs/s versus132
before. One object binding remained through the five-second finalizer, with
zero frames/writers and every root complete; a later observation was zero before
an attempted CPU-progress diagnostic began. The cause of that delay remains
unidentified; that diagnostic did not establish causality.

For subsequent points, after the timed application has exited and the provider
factory is inactive, allow one bounded pass of ordinary userspace activity on
each online CPU. Record binding counts before and after. This gives ordinary
scheduling and deferred MM lifetimes an opportunity to progress, without
changing any MM reference or forcing retirement. It is outside the measured
application window. Keep every exact final zero-state requirement and retain
timeouts. This is measurement cleanup, not a lock or MM-body optimization.

## Current-instruction fetch window

The corrected dispatch point returned170/229.5 pairs/s (threads/processes)
against132/183 before, one untraced lifetime per point. Its separate flat
profile sampled worker-side queued-spin waiting at0.22%, versus22.24% before.
The reports have different sampled event totals, so these are fractions of
their own application windows, not absolute cycle savings. Origin waiting and
IRQ-save locking remain prominent. The runtime still performs millions of
instruction fetches; `kd_reached_frame_fetch()` takes source residency and
no-fault copy paths for each decoder byte on most cache misses.

Add one preallocated15-byte current-instruction window to the reached session.
On the first fetch at the packet's current IP, invalidate the previous window,
retain/read at most15 actual bytes once, and serve only that window's bounds.
Always refresh on a new step, including a loop back to the same IP and service
reentry. A failed optional full-window read cannot reject a valid shorter
instruction: retain the existing exact cached-length and requested-byte paths
as fallbacks. A failed copy never publishes a window. Check overflow before
the optional range. No successor is decoded or executed, and no control-flow
graph is built. The final instruction event still records its complete actual
bytes and retains its normal source/frame/artifact lifetimes.

Keep every existing frame/context check, ownership probe, service ACK and packet
checkpoint. This change reduces repeated source lookups/copies; it does not
batch retirement, relax publication, replace a packet or add a lock/allocation.
Test changed text on repeated IPs, partial ranges/copies, shorter valid
instructions at range ends, out-of-window reads, ordinary non-reached fetching
and source readiness failures. Run the focused actual continuation fixtures
and remeasure both models once as a distinct candidate.

The source-window candidate returned161.5/274.5 pairs/s, versus170/229.5 for
dispatch alone. Retain the measured5.0% thread loss as well as the19.6% process
gain; one round does not establish a noise bound. Both remain above the starting
KD point. Native plain mode returned257231.5/671651.5 pairs/s on the same image
and placement. The current interpreted path remains far below Native and is
unaccepted. Nano and larger-worker qualification remain unrun in this iteration.

Use the same bounded postrun CPU-progress method for the detailed correctness
monitor. It acts only after the observer is stopped, the controller reports
DRAINING, the factory is inactive and exact frame/reached counters show no live
execution. The frozen correctness controller still performs all its original
zero-binding, source retirement, trace joins and normal unload checks. Keep the
monitor/helper hashes separately from the immutable provider inputs; do not
change a running source snapshot or put this activity inside an application
timing window. This prevents known cleanup delays from obscuring proof while
preserving a failure if normal lifetimes do not actually drain.

Both detailed models completed their original checks and normal unload. The
thread run joined 1528 returned other-task sections, 764 read tails and 758 later
same-executor/object writer observations; processes joined 3156, 1577 and 1515.
Each also individually joined 16 syscall pairs. These observations do not account
for every invocation or directly establish reader drainage or physical batch
length. Fresh reader drainage is covered by the separate actual continuation
fixture. The current timed and detailed provider code/data sections match, with
artifact and instrumentation identities retained separately.

The fixed [iteration report](../../bench/results/10.176.26.71/bench/mm-perf-iter1-20261103/README.md)
records all measured gains/losses, builds, failed setups and remaining limits.
The current interpreted candidate remains unaccepted and separate from master.
