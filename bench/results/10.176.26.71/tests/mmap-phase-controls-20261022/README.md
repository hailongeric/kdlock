# Deterministic mmap phase-observer controls

Status: **serial correctness validation passed** on frozen `47fa612`; the three
previously uncovered observer paths now have positive independent controls.
Two basic programs, six receipt tests, the unchanged API baseline (139 checks)
and the new fixture (51 checks) passed. The guest is restored idle on recovery.
No timing ran, no wake policy changed and no performance acceptance follows.
The `d9210e13` observer, original API fixture, 683 workload bindings and installed
`kdmm1` image remain unchanged.

## Results and limits

Run `mmap-phase-controls-20261022`, continuation `stage-2`, guest fixture
`kd-2/controls-1` used candidate boot
`3b208f35-bb94-4746-99e4-4dcde3ab6b72`, Build ID
`687ff5a29315d732f93a618e50ac407c794bbf9b`. Initial host admission passed at
67 threads. The first post-boot control admission refused 68; the second passed
the exact original 67-thread set. The complete guest gate then confirmed the
original QEMU process/configuration, pins, frequency policy, memory bindings,
dependencies and guest topology before any module load. Resident page placement
was recorded, not assumed identical.

| Forced path | First schedule: voluntary / involuntary switches | Unchanged observer result |
| --- | --- | --- |
| Explicit wake while the holder keeps admission | 1 / 0 | Two blocked returns; one failed next predicate, then one reservation |
| Wake current immediately before scheduling | 0 / 0 | One no-switch return, followed by one real blocked return |
| Wake current and a higher-priority fixture peer | 0 / 1 | One runnable-only departure/return, followed by one real blocked return |

All three writers succeeded and joined. The peer also completed and joined.
The exact task/TID/mm/semaphore records match their fixture cases. Aggregate
counts are three entries/epilogues/successes/reservations, six scheduling calls
and returns, four blocked returns, one no-switch return and one runnable-only
return. Their next predicates are one failed retry and three reservations.
Errors, missed probes, active acquisitions, cancellations and gate errors are
zero. Workers joined before observer retirement. Locks and queues were idle;
after observer references were released, allocation references returned to their
ordinary count before normal module unload.

The original 139-check baseline also retained nested locking, cancellation,
concurrent sleeping readers, downgrade, IRQ refusal, reference transfer and
deferred destruction oracles. The new controls explicitly inject wake events;
they validate the observer's classifications, not natural wake-all fanout or
uninstrumented cost. The [wake-correlation design](WAKE_CORRELATION.md) remains
an unimplemented proposal. Callback/activation attribution, per-acquisition
retry distributions and fairness remain unresolved. All seven original mutex
causes, qualified throughput variance and prior endpoint failures remain open.

Recovery boot `97c45a77-3ce3-4d3f-87b4-4ef3e880af64` is
`6.1.159-kdclobber2`, with the original 73 modules, recovery default and all
5,686 recovery module files preserved. Thirteen retained kernel-log captures
contain no matches for the unchanged fault scan; the six known `fd0` boot I/O
messages remain recorded. The module build retained Perl locale fallback
warnings, with no compiler or modpost failure. Basic-test logs include their
intentional negative cases and end with two passed, zero failed; none was
treated as a skipped test.

The coordinator exited zero. All 58 recorded orchestration child commands
across synchronization, the retired wait and the continuation exited zero;
the separately approved waiting coordinator exited 130. Final source inspection
found neither coordinator nor any known child PID and no visible checkout
writer. It could not inspect 534 processes, so this is bounded visibility.

## Admission history and setup

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

Three separate correctness controls use real `mm_struct` objects and the
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

Only fixture writer and peer threads receive temporary scheduler policies;
they exit and are joined. No host setting, workload input, lock field, return
register or production wake decision changes. Target-specific probes check exact
emitted bytes and refuse any mismatch. Their injection is explicit correctness work,
not a passive observer or timing result. The unchanged observer counts the real
scheduler events independently. Missing positive coverage is a failure.

## Evidence

Local raw root: `bench/results/10.176.26.71/raw/tests/mmap-phase-controls-20261022`.
Guest root: `/root/kdlock-evidence/10.176.26.71/tests/mmap-phase-controls-20261022`.
The live fixture bytes are from `f7d9086`; the approved coordinator is
`47fa61281c79187f581d08e2290ca6b675aa597b`.

The [offline audit](../../raw/tests/mmap-phase-controls-20261022/audit.json)
passed 3,495 checks with zero mismatches. Four guest archives contain 341 regular
files, 29 directories and no links: 1,468,141 compressed bytes, 7,147,520 tar
bytes and 6,470,688 payload bytes. All 421 new preparation bindings and all 427
prior observer bindings match the archived/current bytes. The VM independently
verified all 683 original workload bindings before and after controls.
Separate byte-preservation checks retain all 15 prior observer/profile archives
(25,103,628 bytes) and their nine sealed manifests.

The separate [local evidence package](../../raw/tests/mmap-phase-controls-20261022/completed-local-archives-1/archives.json)
contains 241 regular files, no directories or links: 439,264 compressed bytes,
4,433,920 tar bytes and 4,262,296 payload bytes. Its independent
[packaging reconciliation](../../raw/tests/mmap-phase-controls-20261022/completed-local-archives-1/verification.json)
passed 2,685 checks with zero mismatches. Every member matches its inventory and
current input bytes. All 16 control-source snapshots match Git `47fa612`; the
retired coordinator matches `f7d9086`. The audit, run-result, approved stop/drain
and all 58 command-receipt bindings match. The four guest archives remain
separately sealed. The post-seal verifier and its receipt sit beside this package
and are not members of it; neither check extracts or executes archived code.

| Artifact relative to the raw root | SHA-256 |
| --- | --- |
| `stage-2/result.json` | `db8ab55197e57a3ac30ae5895badfe9e58083cadb18216b04e101f4aa240b453` |
| `stage-2/kd/controls.json` | `326572adf4046d4b9acd8877c03b5dd49cecc4ba8dfb678c293da6e20f608846` |
| `stage-2/kd/archives/archives.json` | `a52c0f703898f278b1c10241d6d5542fcec3f511160bc883c48757efe41a23eb` |
| `stage-2/kd/archives/transition.tar.gz` | `57818d7a6caf38924116676cd760c85538e5c9833af24ca260ec00c5d1fa6769` |
| `stage-2/kd/archives/metadata.tar.gz` | `754ead47f5d5b21ebd0cddc5cdd24546e2fbb57336e39e393626e1027f9fb4eb` |
| `stage-2/recovery/archives/archives.json` | `14846ddb3848cb7ee7a65d7bac8f1c51bf767a68f4612e6d67bfc3aa9b4d9da8` |
| `stage-2/recovery/archives/transition.tar.gz` | `a99fb15fc163a80f9d0b154da260c0b7b39df9806c60bbc2d94abf201858b9be` |
| `stage-2/recovery/archives/metadata.tar.gz` | `0d5a9d80dd93b9e031566f3bae8120683200fcf0ef0c3e87d4de7c37ab95c3b1` |
| `completed-local-archives-1/archives.json` | `25d08b844220af323b677f596625ba8f3e5554b91cebdbf7ecc9912cc6724e20` |
| `completed-local-archives-1/input-inventory.json` | `e30d51fbed66b1cdf2a4b5a7c0e24aa6e50a5299aa4f0ef55a4b4442c7b3a698` |
| `completed-local-archives-1/control-and-offline.tar.gz` | `adf7361d639e36a87a2ec10262e2c3d2fff493893ecd9001724fba484be4206d` |
| `completed-local-archives-1/verification.json` | `e8d3d706182cecea6a91a2b7cd2ee0e9a4dd5d4ada3d511f21826048e0bdb15a` |
| `source-drain.json` | `293c1ec0af51d36f8c3a24217b0ffc33fdfd79cd7cc0e7e3fb8b5e23d86f01ee` |

Inside the KD metadata archive, `controls-1/baseline.json` hashes to
`f6d895b5de4891136e7edbb24e353c0804f17b987aee17e5d6158c568c97d748`,
`controls-1/controls.json` to
`3081b25fca0ab4d7cbea16ae5312cff9da669950483d0d68763761ef1ef0f559`,
and `controls-1/observer.json` to
`5eccdd3c890ee1670077836f6f8fca1cee19dcc0b3bf4a7d29061c07c0c745c7`.
