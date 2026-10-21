# QEMU worker-creation controls, 2026-10-21

Status: **focused phase diagnostics complete; no accepted performance comparison.**
The single workload and all completed controls drained; archives passed 2,340
inert checks. All seven regression causes, acquisition latency and historical
worker interference remain unresolved. Fresh ownership and drain checks found
clean `master` at `08ab5d6`,
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

## Setup-only repetition and next phases

`setup-1` at `4874f2e` completed 69 samples: 67 initially, peak 76, last 71.
One worker first appears during SSH/setup and eight during the first no-op
tail. No tmpfs/disk file is created by this control. See
[setup accounting](setup-review-1.json). The same pattern has now occurred
twice without a benchmark. It establishes repeatability of setup-associated
worker creation, not attribution to SSH versus guest background writeback.

An independent read-only review verified every first-control evidence/source
hash, phase delta and original task identity. For `guest-1`, the eight-worker
appearance bracket is 13.222–13.738 seconds after observer ready, before tmpfs
write at 14.995 seconds and disk write at 21.034 seconds. Across matching reads,
workers added 11.935290 ms runtime, 155,648 read bytes and 5,558,272 write bytes;
8.600856 ms and 5,193,728 write bytes cross phase boundaries and remain
unattributed. These are incomplete lifetime costs, not benchmark overhead.

Next controls observe normal idle synchronization, a forced rebuild/run of the
two basic guest unit programs, and one frozen OUTER five-worker session. The
single-session option retains every existing provenance, correctness, placement
and strict original host gate. Phase handshakes occur outside joined worker
execution; the observer and pauses make this an intrusive diagnostic. The prior
six-session runner/results remain preserved at their recorded revisions.

`sync-1` at `038379b` completed both the dry run and synchronization: 20 changed
files, all 3,949 approved hashes verified, no deletion. A read-only review found
two failure-path issues in the new, **not yet executed** workload phase hooks:
loss of an observer reply could precede a loaded/bound flag update, and final
success was recorded before the last reply. The follow-up uses unsafe failure
retention for uncertain state and records success only after the final reply.
Its workload observer bound is 600 seconds and event wait is 240 seconds,
covering existing bounded publication/identity/client waits. This does not
extend or change the workload's own timeout or drain rules. Observer phase
acknowledgements do not represent kernel ownership or unlock ACKs.

`sync-1` itself began at 67, reached 68 during the read-only dry run, then 76
during its tail; actual synchronization started with the pool already present.
The first basic-build control, `basic-1`, was refused at 68 before any guest
command. Its early observer EOF, failure receipt and zero-command record are
retained. A later attempt must independently reach the unchanged 67-task gate.

`basic-2` passed both rebuilt default unit programs with unchanged captured
inputs. It began at 67, peaked/ended at 70 across 36 samples. This is basic
validation and a compiler/test I/O control, not a new full affected suite.
`sync-2` was subsequently refused before any guest command because the original
thread-count preflight had not yet recovered. Neither refusal is counted as a
test pass; no in-flight command was interrupted.

## Read-only delegation-path analysis

Both callers use the same frozen OUTER acquisition and admission rules. General
unlock adds task-routing lookup before releasing a locally acquired physical
mutex; it does not update heat or directly enqueue requests. A plausible
feedback mechanism is that additional work before release increases exhaustion
of the eight probes, increasing contention samples and hot admission, which
allows more delegation. The counters are consistent with this hypothesis but
do not establish its causal timing.

The transformation removes 15 bytes of native cookie-routing code and changes
generated control flow too: cookie routing and an additional budget check
disappear, reducing the loaded image from 1,118 to 994 bytes. Normal delegated
completion reaches `clobber_complete`, rather than executing the C routing
lookup for each delegated body. The comparison cannot isolate unlock-provider
cost. Actual acquisition, provider, headers, source admission and ownership
rules remain identical in the retained control inputs.

Measured returned fractions are separate from lifetime counters including
warmup. All six prior sessions had zero native-continuation started/completed/
unlock counters; task reroutes are not ACK traffic. OUTER repeat 2 had no
delegation slowpath/combiner/JIT activity but did have 1,024 gate-owned native
acquisitions. General sessions ended with the lock's five CPU-local records hot; OUTER repeats
0/2 ended cold and repeat 1 hot. Final heat snapshots cannot reconstruct timed
transitions. Preserve all six prior unaccepted observations and the four
separate correctness sessions; no production fix follows from this analysis.

## Frozen workload phase diagnostic

After completed `sync-3` and `sync-4` verified the reviewed harness bytes,
`phase-1` was refused before any guest command at the unchanged thread gate.
`phase-2` started at 67 and passed the full original environment comparison and
all retained correctness/provenance prerequisites. It completed one original
OUTER five-worker session with 167,972 returned generated bodies and normal
retirement. The original provider/workload binaries were reused; no build or
production change was introduced. Source supervisor revision: `a345918`;
the guest runner's exact file bytes are retained with the session.
The guest source synchronization manifest records clean `fc43dff` and 3,952
verified files. The runner bytes are identical at `a345918`; its later
source-host supervisor changes do not replace frozen guest runtime inputs.

The continuous trace contains 45 samples, starting at 67 and ending/peaking at
73. One worker appears during guest setup; additional workers appear around
warmup/measurement. The four samples labelled `client-measure-begin` all contain
73 tasks. Matched intervals wholly within that label show zero additional
worker runtime/read/write counters. This is a limited interior observation:
boundary activity, first cumulative observations and missing lifetime tails
cannot be assigned to the timed critical section. It does not establish zero
interference or restore the failed original task-count condition. See
[phase accounting](phase-review-2.json). Rates remain unaccepted and are not
compared against prior uninstrumented arms.

Collection, frozen-input verification and archival completed as separately
observed phases. They occurred after the workload and cannot explain workers
already observed during it. `collection-1` began at 67, reached 78 and ended at
78 across 33 samples. Archive/download/tail observations remain separate from
the workload trace.

BOOTTIME and the acknowledged phase boundary resolve an important ambiguity:
**all six observed workload-session workers were born before the measured client
could start.** The last worker, `449252/96977227`, was born within
`[969772270000000, 969772280000000)` BOOTTIME ns. The begin acknowledgement
was later, at `969772285134436` ns, before the guest was allowed to deliver the
measurement command. Thus first observing this worker during measurement does
not mean measurement created it. This conclusion covers observed workers only.

| Matched observation interval | Worker runtime | Read bytes | Write bytes | Meaning |
| --- | ---: | ---: | ---: | --- |
| Samples 29→30, five survivors | 2.831871 ms | 221,184 | 1,343,488 | Crosses measurement start; unattributed |
| New worker's first counters | 0.554741 ms | 0 | 704,512 | Cumulative, not an interval delta |
| Samples 30→33, six workers | 0 | 0 | 0 | Only the matched interior reads |
| Samples 33→34, six workers | 0.647599 ms | 24,576 | 282,624 | Crosses measurement end/cleanup; unattributed |

The phase envelope is 2.057704305 seconds and brackets the client command/reply,
not exact kernel worker start/finish instants. Whole-interval inactivity and
indirect interference remain unproven. The observer used 1.82% of one core;
the maximum unsampled gap was 501.7 ms. Existing workers still make the original
task-count condition fail even when retained interior deltas are zero.

## Results, preservation and remaining gaps

The one intrusive session completed **24,489,984 operations**, with **167,972
entries and returns** (0.685880% returned fraction), stable images, original
32-byte object placement, five correctly placed workers, collector CPU63,
exact `state=2, modules=frames=writers=0` retirement and no matched kernel
faults. Final verification confirmed the unchanged original provider SHA256
`cf7f9a47c5b36c762e732641b4e33459bf46ef11f6a67fbbcbc7c9a807757988`, all frozen
inputs and the original 73 runtime modules on the same recovery boot. No
kernel, snapshot, security policy, topology, admission or ownership change was
made. Helpers touched no files and performed no remote actions.

| Completed diagnostic | Initial / peak / last tasks | Samples |
| --- | --- | ---: |
| `host-1` | 67 / 67 / 67 | 38 |
| `guest-1` | 67 / 76 / 74 | 75 |
| `setup-1` | 67 / 76 / 71 | 69 |
| `sync-1` | 67 / 76 / 76 | 69 |
| `sync-3` | 67 / 69 / 69 | 67 |
| `sync-4` | 67 / 75 / 75 | 67 |
| `basic-2` | 67 / 70 / 70 | 36 |
| `phase-2` | 67 / 73 / 73 | 45 |
| `collection-1` | 67 / 78 / 78 | 33 |

`basic-1`, `sync-2` and `phase-1` were refused at 68, 72 and 68 respectively,
before any guest command. All failures remain retained. These controls have
different stimuli and source revisions; do not pool them into a performance
variance estimate. The two setup repetitions share the 76-task peak but differ
in final counts. The prior six paired rate/variance results remain unchanged
and unaccepted; this single intrusive session supplies no new rate variance.

Guest archive directory:
`/root/kdlock-evidence/10.176.26.71/bench/qemu-workers-20261021-archives-1`.
Local archives:
`../../raw/bench/qemu-workers-20261021/collection-1/archives-1/`.
Manifest SHA256:
`71db76f5ab21797c90f0c1a43cf1aad4401e6eb286e71adc304b141b1aac9859`.

| Archive | Bytes | SHA256 |
| --- | ---: | --- |
| `phase.tar.gz` | 117,530 | `2bcbd0d9a930edca1f131ab7cfe7ad6ac62621f57953a47a9c4a6298b7fde08e` |
| `controls.tar.gz` | 3,486,937 | `09acfad1ec315a25f41c49349dbea725b20b1a9f25a56f576f8902a76251b9ea` |
| `metadata.tar.gz` | 27,073 | `67cde06a43625a2e29de5d5e22d4afc16acf087b40175bdf172381e5b7987e5d` |

[The inert audit](review.json) checks inventories, hashes, retained cross-archive
links, committed runner bytes, all five exact prerequisite receipts, original
provider/settings, 112 copied control files and all 38 phase events. The
collection observer is necessarily outside the archives it observes; its raw
files remain in `collection-1/`, bound by hashes in the audit. No archived code
was executed. [Collection accounting](collection-review-1.json) includes that
trace and the final synchronization control.
Independent read-only review also confirmed all archive hashes, exact copied
files/prerequisites and source bindings, phase stream ordering, provider
settings and zero native-continuation ACK counters. Both reviewers touched no
files; only the main agent wrote source and executed serial VM work.

What remains unresolved: SSH/setup versus delayed guest/background writeback
as the source of each worker, wholly unsampled lifetimes and departed accounting
tails, the original 53 workers' historical activity, indirect CPU63/cache/I/O
effects during timing, and the causal size of either unlock-path contribution.
Do not infer an acceptance waiver from worker-pool behavior. All seven points
(`c08/3,4,5`, `pipebytes/3,5`, `pipecap/5`, `rcuht/2`) remain unresolved;
acquisition latency remains unresolved and complete-operation p95 remains a
separate metric. No broader comparison or production change is justified yet.
