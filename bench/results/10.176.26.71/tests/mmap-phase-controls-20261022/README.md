# Deterministic mmap phase-observer controls

Status: implementation in progress; no new build, live control or timing has
started. This stage preserves the `d9210e13` observer, original API fixture,
683 workload bindings, installed `kdmm1` image and all prior archives.

The sole writer refreshed source ownership on 2026-10-22 at 05:11:27 UTC:
clean `29cf421`, no known coordinator, none of the 47 prior command PIDs present
and no visible writable checkout descriptor. Inspection could not access
534 processes; this is a visibility limit, not proof that those processes were
idle. Existing helpers are completed, read-only, with no files touched.
The guest idle/preservation check at 05:11:50 UTC confirmed recovery boot
`4b9775c4-ac74-4db8-85c7-491f6b81f212`, the original 73 modules and all 5,686
recovery module files. The actual host capture at 05:15:32 UTC, more than
60 seconds later, confirmed QEMU PID 257489, the original 67 threads and pins,
two NUMA nodes and snapshot `before-mutex-kdonly-20261017T140354Z`.

Three separate correctness controls will use real `mm_struct` objects and the
unchanged killable writer. A held writer keeps the admission predicate false.

1. Wake an actually parked writer without releasing the holder; require a
   blocked scheduling return, a failed predicate and another real park before
   finally releasing the holder.
2. Wake the current waiter immediately before its first `schedule`, using only
   a fixture task at FIFO priority 1. Require no switch in that exact invocation,
   independently checked against its task switch counters, and a positive
   no-switch observation. The next invocation must actually park.
3. As in control 2, also wake a parked fixture peer at FIFO priority 50 on the
   same CPU. Require an actual runnable departure and return, zero voluntary
   switches in that exact invocation and peer completion. The next invocation
   must actually park.

Only the two fixture tasks receive temporary scheduler policies; they exit and
are joined. No host setting, workload input, lock field, return register or
production wake decision changes. Target-specific probes check exact emitted
bytes and refuse any mismatch. Their injection is explicit correctness work,
not a passive observer or timing result. The unchanged observer counts the real
scheduler events independently. Missing positive coverage is a failure.

Basic and directly affected checks precede serial live controls. Full admission,
post-idle settling and fault/drain checks remain. No timing is planned in this
stage. The separate [correlation design](WAKE_CORRELATION.md) is a prerequisite
for any later wake-cause experiment; retry counts alone cannot justify a
selective-wake implementation. All seven mutex causes, qualified throughput
variance and existing endpoint failures remain unresolved.
