# QEMU worker-creation controls, 2026-10-21

Status: **focused diagnostics in progress; no new performance comparison or
acceptance.** Fresh ownership and drain checks found clean `master` at `08ab5d6`,
no writable project descriptors/Git lock, and the original idle recovery VM with
73 modules on boot `88449cfc-cea9-4647-a294-bc601e372146`. The main agent is the
sole writer/test executor; helpers perform read-only source/evidence analysis.

The preceding [six paired sessions](../pipecap-unlock-followup-20261021/README.md)
remain unaccepted and immutable: preflight 67 tasks, immediate endpoint 120,
one class-mismatched pair and varying returned fractions. No new acceptance
threshold or relaxation of the original gate is authorized.

Competing hypotheses are observer/monitor overhead, SSH/guest setup, source
synchronization and builds, guest disk writes, preparation/JIT/warmup, the
measured critical section, cleanup/logging, and later collection/archiving.
Begin with host-only observation and the existing snapshot query, then small
guest controls. Use a short, bounded read-only observer with 0.5-second spacing;
retain its own CPU cost, clock/read brackets, TID/start-tick identities and
worker scheduler/I/O fields. Bracket controls and workload phases explicitly.
The observation is intrusive and is not used to accept throughput.

Record unavailable/departed tails and sampling gaps; zero tick deltas or sleeping
snapshots do not prove no work. Align clocks using causal request/reply brackets
instead of assuming synchronized wall clocks. Keep original frozen binaries and
receipts intact; no unknown process is killed, retuned or inspected beyond the
existing bounded QEMU `/proc` and monitor workflow. All seven causes remain open.

## Controls at `4685340`

Both controls began with 67 tasks, retained the original identities/pins and
completed normally. No modules or workload ran. Raw source copies, phase
acknowledgements, read brackets and console receipts are in
`../../raw/bench/qemu-workers-20261021/{host-1,guest-1}/`.
[Offline accounting](controls-review-1.json) retains per-file SHA256 values.

| Run | Stimulus | Samples | Count range / last | Observer CPU / elapsed |
| --- | --- | ---: | --- | --- |
| `host-1` | Host observation, existing snapshot query | 38 | 67–67 / 67 | 268.267 ms / 18.820 s |
| `guest-1` | Persistent SSH, no-op, tmpfs and disk 4 MiB writes/reads, own-file cleanup | 75 | 67–76 / 74 | 683.865 ms / 38.188 s |

In `guest-1`, one worker first appears during SSH/setup, then eight more during
the no-op tail, **before the explicit tmpfs or disk write**. Both file hashes
matched and both own files were removed. The later disk write/fsync did not add
observed workers to the existing pool. Setup/background I/O can accompany the
count failure without a benchmark; this does not identify the historical 53
workers' origin. A separate setup-only repetition is the next discriminator.

Worker runtime and I/O increased across retained exact identities. The first
and last cumulative values are not phase-local work; only surviving, matched
intervals are differenced. Two workers depart before the last scan; all tails
beyond the last read remain unknown. Maximum gaps are 501.6/501.7 ms and maximum
scan durations 9.56/11.74 ms. Observer CPU is 1.43/1.79% of one core, excluding
SSH/sudo startup and the source supervisor. Host allowed affinity is 0–63;
observations are intrusive and no overhead is subtracted from rates.

Clock offsets are bounded for each request. Host/source offsets varied by
milliseconds; guest/source clock requests bound about 42.6–45.6 ms. Do not assume
identical wall clocks. These first controls retain start ticks and CLK_TCK but
lack BOOTTIME samples, so birth ticks are not converted to UTC. The next observer
revision records BOOTTIME explicitly. Entire lifetimes between samples remain
unobservable. No original admission or acceptance check changed.
