# Deterministic mmap phase-observer controls

Status: the controls are implemented; VM validation is pending. No new build,
live control or timing has started. This stage preserves the `d9210e13` observer, original API fixture,
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

The first coordinator used frozen `f7d9086` and 60-second post-idle settling.
Its five initial admission captures refused 68, 68, 68, 68 and 69 QEMU threads
against the original 67. Nothing reached preparation, boot transition or live
testing. The separate host-only observation saw its last extra worker still
present at 05:36:38 UTC and absent at 05:36:43; that later quiet sample did not
replace any failed capture. The user approved stopping only this waiting
coordinator and increasing settling to 90 seconds. At 05:39:13 UTC, its exact
PID 865830/start-ticks 974179357 had no children and all 13 command receipts
had exited zero; a pidfd SIGINT stopped it with exit 130. Independent follow-up
confirmed its exit, child drain, the same idle recovery boot, all original 683
workload bindings and all 427 prior observer bindings. The source descriptor
checks retain their inaccessible-process limitation.

The approved continuation uses `stage-2`, guest `kd-2` and 90-second settling.
Its stop/drain prerequisite SHA-256 is
`8ca5c607a0bcb13fdecf42fe67414a925049ca699bb56d37bec94bd6d4a728ae`.
The old coordinator source, five refusals, lifetime samples and original result
remain under `raw/tests/mmap-phase-controls-20261022/stage-1`; no refusal is a
pass. The complete original host/guest gates and fixture bytes are unchanged.

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
