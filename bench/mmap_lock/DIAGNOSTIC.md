# QEMU task diagnostic

This is an environment investigation, not a development-stage performance result.
The [project roadmap](../../docs/ROADMAP.md) and [runner guide](README.md) track
later work. Their separately selected policies and completed exploratory screen
do not reclassify the diagnostic failures or authorize a new diagnostic attempt.

Status: the original 43 focused mocked tests passed; the first authorized live
attempt [stopped during initial observation](../results/10.176.26.71/bench/mmap-diagnostic-20261026/README.md)
on October 26 at a 504.396027 ms start gap. No stimulus phase ran; the observation
is incomplete and unaccepted. The user then clarified that 500 ms is an
approximate target. The minimal correction has
[48 focused mocked test passes](../results/10.176.26.71/tests/mmap-diagnostic-cadence-20261026/README.md);
the [one corrected attempt](../results/10.176.26.71/bench/mmap-diagnostic-corrected-20261026/README.md)
then stopped on a new task during the guest no-op phase. The no-op completed
after the stop; the checksum phase did not run. Both attempts remain incomplete
and unaccepted. **No further attempt or benchmark is authorized by these results.**
The October 25
73-versus-67 and later 68-versus-67 admission stops remain in force.
This tool cannot admit, repair or qualify a performance run. The prior capture's
six workers predated that helper by about 63/55 seconds; their roles and creation
source remain unknown. Preserve that failed capture and the unchanged gate.

The [source controller](diagnostic_controller.py) owns one host SSH connection.
It streams the reviewed [observer](diagnostic_observer.py) and the existing
`host_capture_control.stat_fields` parser; it does not execute a mutable remote
copy. `kdmm31.json` supplies the retained VM identity. No code runs on import.
Without `--execute`, the controller only reports local source/payload hashes.

## Retained phase design

Offsets use the observer's host monotonic clock. All phases share a 60-second
observer bound; there are no retries or loops waiting for 67 tasks.

| Offset | Maximum action |
| --- | --- |
| 0–5 s | Resolve `/tmp/kdlock-qemu.pid`; bind host boot, QEMU PID/start, command hash and executable identity; inventory tasks |
| 5–15 s | Idle task observation |
| 15–25 s | One metadata bundle: QEMU `numa_maps`, the existing five cpufreq policy fields, NUMA cpulists |
| 25–35 s | One `/tmp/qemu-monitor.sock` connection; only `info snapshots\n`; immediate post-query task scan |
| 35–45 s | One source-to-guest SSH `/bin/true` control |
| 45–55 s | One source-to-guest SSH `/usr/bin/sha256sum -- /boot/vmlinuz-6.1.159-kdmm31` |
| 55–60 s | Tail observation and finish |

The nominal task cadence is **approximately 500 ms**. Ordinary wakeup jitter is
recorded, not rejected. A scan or start-to-start gap exceeding **five seconds**
stops later stimuli: this is the shortest phase window, so a loss that long can
obscure a whole phase. It is an observation-loss rule, not an exact scheduling
requirement. Every phase must have task-observation evidence before the run can
be complete; successful stimuli alone are insufficient. The final gap is checked
even if a late sleep exits the loop without another scan. Actual start/end,
scan durations, gaps, CPU cost and output bytes remain evidence. Sampling is
coarse and can miss short-lived tasks; it cannot establish precise causation.
No faster sampling or catch-up loop is substituted. The requested post-monitor
scan is additional. The original strict-500-ms receipt remains rejected.

Each task observation records membership before/after, stat before/after,
schedstat, affinity, and non-vCPU `io`/`wchan`. It retains monotonic/BOOTTIME
brackets and observer CPU cost/processor. Boot, PID, start, command and executable
identity are checked on both sides of a scan. Retained 64-vCPU/service placement
is required. The initial task inventory can contain existing extra workers;
binding it is diagnostic bookkeeping, never a replacement 67-task admission.

The metadata bundle excludes serial-log scanning. It has a 1 MiB aggregate
bound and an eight-second observation deadline. The single monitor connection
shares an eight-second total deadline and 1 MiB across banner and response.
Partial monitor bytes survive timeout/EOF/overflow in the receipt when the
output channel remains writable. Only the owned client socket is closed.

Guest SSH retains the source host's batch/strict-host-key routes, port 2222,
three-second connection timeout and eight-second observation deadline. The
host records request and launch/completion acknowledgement brackets; source
timestamps remain source timestamps. An already-issued request may be in flight
when the host detects a stop. No later request is issued, and a stop already
received by the controller suppresses queued launches. These asynchronous
brackets do not prove an exact cross-host event ordering.

## Stop and retention rules

The first new task identity, changed identity, denied read, incomplete sample,
deadline, protocol error or output failure prevents subsequent stimuli. A stop
has at most a five-second tail inside the original 60 seconds. QEMU sampling
continues while monitor and guest operations are pending; there is no
blocking wait replacing the sampler. A source-side 75-second observation bound
covers transport and observer startup, without killing SSH or remote commands.

Local SSH exit after an observation timeout does not clear the earlier unknown
completion. No destructor, timeout, interruption or cleanup path sends signals
to QEMU/SSH/guest commands, retries an action or claims drain. The observer's
own watchdog interrupts its Python work. A stalled kernel read or lost transport
can still prevent a complete receipt; neither a final record nor safe completion
can be guaranteed through a broken output channel.

The controller retains raw host/guest stdout and stderr in a new local directory,
including consumed overflow bytes. Total host output is bounded to 32 MiB and
guest output to 16 KiB, plus at most one consumed 64 KiB overflow chunk per stream.
Host event lines/queued output are bounded to 2 MiB. Stop state and closing the
owned monitor client do not depend on a successful receipt write. Diagnostics
remain incomplete if final flushing fails.

No negative result, worker name or phase association proves a creation cause.
The observer itself costs CPU and performs I/O. Discrete scans can miss short
task lifetimes. This has no workload throughput or latency measurement.

## Offline validation and approval boundary

The [focused mocked tests](../../tests/unit/bench/test_mmap_diagnostic.py) use in-memory
proc/sys fixtures, virtual time and injected transports/processes. Guards refuse
production Proc/Clock adapters, sockets, process launches and pipe operations
unless a case explicitly mocks that adapter. The execution-receipt fixture uses
in-memory files. This tests those paths, not universal interception or live safety.
See the [validation receipt](../results/10.176.26.71/tests/mmap-diagnostic-offline-20261025/README.md)
for exact hashes and VM results. No old validation or cleanup was repeated.

The original invocation, clarified timing requirement, 48-test correction and
independent review are recorded in the linked receipts. The single authorized
corrected execution is complete as a stopped attempt. It used the same phases,
identity/access/completion safeguards and no new instruments, settings, signals,
module operations or reboot. Its authorization is consumed; no retry follows.

Additional invocations need approval for the exact cycle and reviewed source
snapshot. The interface alone is **not authorization to retry**:

```sh
python3 bench/mmap_lock/diagnostic_controller.py --execute --output NEW-local-diagnostic
```

That approval would cover only this diagnostic. It would not authorize a host
capture retry, benchmark, kernel build/install/reboot, settings change, cleanup,
process kill or weaker qualification. Unknown completion requires a separate
review before any further work; elapsed time is not evidence of drain.
