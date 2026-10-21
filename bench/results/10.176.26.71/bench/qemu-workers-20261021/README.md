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
