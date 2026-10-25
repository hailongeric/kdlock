# Corrected QEMU diagnostic: new task during guest control

The one authorized corrected attempt at
`39ad0be00c1e6120be29fc83710f7a3c1a68f66c` stopped on **first new QEMU task**
during the guest no-op phase. Metadata and the single snapshot query completed;
the already-launched `/bin/true` completed after the stop. The kernel-checksum
phase did not run. This diagnostic is **incomplete and unaccepted** and supplies
no benchmark qualification or worker-creation cause. There was no retry.

The user's clarified approximate 500 ms cadence was respected: ordinary jitter
did not abort the run. The separate five-second observation-loss rule and other
stop conditions remained active. The [48 mocked tests and independent review](../../tests/mmap-diagnostic-cadence-20261026/README.md)
preceded execution. The [original 504.396027 ms failure](../mmap-diagnostic-20261026/README.md)
and its strict-period inputs remain separately preserved, not reclassified.

## Phase and task evidence

Offsets below are host-monotonic observations relative to the start event, not
cross-host clock estimates or exact task-creation times.

| Event | Offset (seconds) | Evidence |
| --- | ---: | --- |
| Initial inventory | Near 0 | Original 67 task identities |
| Metadata start / completion | 15.006260 / 18.440459 | 323 bounded reads, 6,699 bytes; no serial-log scan |
| Snapshot-query completion | 25.034515 | One socket, one `info snapshots` query, 15 query bytes; retained tag listed |
| Last scan without new task | 34.657334–34.662671 | Sample 70, 67 tasks |
| Guest no-op request | 35.000229 | One `/bin/true` request |
| Launch acknowledgement | 35.030969 | Host received source launch acknowledgement |
| First scan with new task | 35.163779–35.169397 | Sample 71, 68 tasks |
| Stop | 35.169920 | No later stimulus permitted; no-op already in flight |
| No-op completion acknowledgement | 35.939746 | Return 0, empty stdout/stderr, completion confirmed |
| Final record | 40.121450 | Bounded stop tail finished; no pending command |

New TID **553662**, start ticks **133625624**, first appeared as `worker`, state
`S`, affinity `[63]`, wait channel `futex_wait_queue`. At first observation it
had `write_bytes=16384`, `wchar=16416`, seven write syscalls and 382,903 ns runtime.
Its last retained observation had `write_bytes=20480`, `wchar=20528` and ten
write syscalls. These counters show recorded I/O by that task; they do not name
the descriptor, request origin or causal guest operation. The phase association
narrows a window without proving the no-op/SSH created the worker. Names and an
idle wait channel do not establish absence of interference.

All 70 pre-stop scans had 67 tasks. Sample 71 triggered the stop; nine further
scans belong only to the stop tail, all with 68 tasks. Metadata and the query
had no observed task addition. Discrete scans cannot exclude short-lived tasks
between observations. The receipt's missing `guest_true` phase observation means
no successful pre-stop scan was credited to that phase; post-stop raw scans and
the later command acknowledgement are still preserved. Guest hash and the normal
final tail phase were unrun.

| Diagnostic interval | Count | Minimum | Median | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Scan-start gap (ms) | 79 | 221.552136 | 506.443372 | 510.064347 |
| Unobserved gap (ms) | 79 | 215.901981 | 500.445344 | 504.041498 |
| Scan duration (ms) | 80 | 3.691469 | 5.6616245 | 7.582210 |

The minimum includes the required extra post-monitor scan. All 80 samples,
stage labels, exact timestamps, durations and gaps are retained in the raw event
stream, `review.json` and `sample-timing.csv`; no distribution is pooled with
the first attempt. Host elapsed time was 40,121,535,278 ns and observer CPU
1,037,820,759 ns (2.5867% of one core over that interval). Source elapsed time
was 40,485,635,668 ns and CPU 579,244,275 ns (1.4307%). The raw host stream is
3,797,767 bytes. These are diagnostic costs, not lock latency or workload
overhead measurements.

## Completion, preservation and next step

Host and guest completion are confirmed; controller/observer return code was 1,
with zero retries or signals. No module, kernel, boot, setting or snapshot state
was changed. The query only listed snapshots. No benchmark or later checksum
request ran. The generic `drain_proven=false` field is retained; no workload was
loaded that would require a module drain.

Post-run health passed at **2026-10-26 01:26:28 Asia/Shanghai**
(`2026-10-25T17:26:28.662773+00:00`): recovery `6.1.159-kdclobber2`, boot
`d32e2e18-c340-4a98-8105-335bccec0b5d`, original 73 modules, taint **12288**,
CPUs 0–63, voluntary preemption, empty `next_entry` and no competing project
process/open file. Identity, policy, module set, recovery source and dmesg matched
the pre-run check. No additional live work follows this result.

Raw evidence on 380G10:
`bench/results/10.176.26.71/raw/bench/mmap-diagnostic-corrected-20261026/`.
Manifest: **26 files / 4,015,204 bytes**, excluding itself, SHA-256
`051b1c91adfc9351f2c373767672e740fa8bbe1ec11dc7bf3e14226584cf3df7`.
It binds the exact streamed sources, command and scope records, raw outputs,
before/after health and transport completion. Key hashes:

| Artifact | SHA-256 |
| --- | --- |
| Streamed payload | `b4bc22ecff2646c93d538d3f08db7d1189941d11056143a53ee3ff9fb3fbf247` |
| Raw host stream | `4553865bd05722e401dd474b6766459ba59d3543e3af6897bdbbf676f4201baf` |
| Controller receipt | `feb2530e3282689eb23c9fc9204be19a1a7e2fbb9decaebe419e7542bd46ea46` |
| Complete timing CSV | `46c16af439ce4d4c800938cc5d6c569f05f036f4b822ebecffc5580027dde6ee` |

The next useful step is a bounded review of this guest-control/I/O window and
the saved identities to define what evidence can resolve the admission blocker.
Any proposal to admit known auxiliary workers would first need explicit lifetime,
placement, I/O-origin and measured-interference evidence under matched Native/KD
controls, plus approval of the changed rule. This receipt makes no such proposal
effective. The exact **67-task benchmark gate remains unchanged**, qualified
current mmap measurements remain zero, and no repeat diagnostic or throughput
campaign is authorized by this result.
