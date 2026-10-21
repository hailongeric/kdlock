# Bounded guest receipt-I/O diagnostic, 2026-10-21

Status: protocol review and serial basic/affected validation passed; live control
pending.
New p95 measurements are deferred and missing p95 is not a throughput gate.
Existing latency and baseline artifacts remain unchanged. All seven mutex
causes remain unresolved under the original correctness, matched-work,
execution-class, retirement and environment requirements.

Fresh ownership checks at clean `9c22aac` found no source writer or index lock
on 380G10 and no in-flight project work in the existing recovery VM. The guest
retained boot `88449cfc-cea9-4647-a294-bc601e372146`, release
`6.1.159-kdclobber2` and the original 73 modules. Main is the sole writer and
VM executor; helpers review retained evidence/source read-only and touch no files.

The [preceding phase control](../mutex-phase-accounting-20261021/README.md)
located three worker births after the post-warmup capture and before cleanup.
This control observes the existing guest evidence writes to distinguish their
timing from control exchanges and later trace export. It does not identify the
initiating block request or rule out delayed earlier I/O/background activity.

One opt-in trace arms after the unchanged pre-warmup gate and fresh guest
comparison, records in memory for at most 60 seconds / 256 rows, and wraps only
existing `Path.write_text`/`write_bytes` calls inside the new evidence directory.
It preserves original arguments, bytes, return values, exceptions and order;
no fsync, write suppression, check removal or endpoint replacement is added.
Logical byte counts, guest clock/CPU brackets, phase request/reply byte counts
and starting/final process-I/O counters remain separate. Direct open-file,
copy, child-process, translator, SSH, background and prior I/O are outside its
write-hook coverage. Control byte counts cover phase messages only; large
boundary request/reply traffic and client pipe commands remain uncounted.
Text counts are encoded logical bytes before any explicit newline translation.
Overflow/errors make the diagnostic incomplete without
interrupting original writes or normal retirement.

After the original final receipt save and confirmed normal drain, two bounded
stdout records export the trace and its measured first-record send/flush cost.
No new guest trace file is written. Export adds pre-exit SSH traffic and delay;
the supervisor still waits for normal runner/SSH exit before the original full
endpoint capture. The trailer's own cost is bounded only by source receipt/EOF.
Malformed/missing/duplicate exports must not skip that endpoint. Source-side
raw logging remains in place. These observation effects prohibit treating the
control as throughput evidence or attributing the endpoint to a specific file.

Run basic and directly affected checks serially before one no-timing live
control, preserving the frozen provider/client/workload/translator and original
single warmup. Record exact gates, work/returned-body counts, owners/ACKs,
retirement, final idle, recovery and unchanged input hashes. No broad matrix,
kernel transition or new p95 collection is part of this diagnostic.

Separate read-only work prepares an RCUHT execution-class audit and distinct
actual-mmap/fault comparison plans. Experimental-kernel execution stays
separately scheduled after recovery diagnostics drain, in this same VM with
the recovery path preserved.

## Focused validation

Implementation `aba2dbf` synchronized while idle, verifying all 3,991 tracked
hashes and changing 16 files without deletion. `checks-1` passed 49 checks/programs
serially from 107 frozen sources: two rebuilt basic programs, eleven receipt
observer tests, five phase-accounting tests, nine trigger tests, four boundary
protocol tests, twelve pre-warmup tests and six recovery-gate tests. Sources
remained unchanged and final idle passed.

Read-only review identified and verified repairs for observer clock failures
changing original write behavior and optional export failures skipping the
endpoint. Tests inject those failures, preserve original effects/exceptions,
check logical text/binary byte counts, bounded overflow/expiry, excluded paths,
normal-drain-before-export and EOF/endpoint-before-trace-validation order.
An uncertain guest still cannot produce a fabricated endpoint or drain.
The reviewer found no remaining blocker for this focused live diagnostic,
touched no files and ran no tests, builds or remote actions.
