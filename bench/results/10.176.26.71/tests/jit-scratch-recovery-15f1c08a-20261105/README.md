# Scratch recovery and focused mmap1 checks

Runtime source: `15f1c08a3a52ed271fcf3fd81f5da68f1f524878` on
`codex/mmap-reached-jit`. Design `e46874aa` precedes implementation
`87430984`; `b9b4e83f` and `15f1c08a` correct fixture setup/expectations.
Master is unchanged. Source edits and archive inspection ran on `380G10`;
all compilation and execution ran on VM `10.176.26.71`.

**Result:** the compiler correction passes its focused checks and all six
unscored mmap1 application lifetimes complete and drain. Both comparison
attempts remain `LEARNING_ADVANCED`, with no scored KD point or delegation
proof. This is neither performance acceptance nor proof of complete MM proxy
execution. No Nano comparison was run in this focused stage.

## Correction and checks

The prior `8a7b8e73` image borrowed physical R13 for source IP, released that
mapping, then emitted `MOV Stack_R, R13` while restoring logical SP. The
undefined symbol left an ELF relocation and raw extraction produced a store
to zero. The saved object SHA256 is
`c68c91e6e3a00b1b5d8b6470597fc2f86fd205a0cb3d0b785332af0b7c9fff2c`.
Its exact published generation/base and fault correlation are retained in
[the design record](../../../../../docs/design/compiled_mm_continuations.md#empty-scratch-mapping-correction-before-the-next-pilot).

`spill_register()` now skips empty mappings without changing dirty-register
stores or saved SP. Before raw extraction, `require_complete_object()` refuses
unapplied relocations into allocated sections with stored bytes. Failed builds
remove old raw output and retain assembly/object inputs. This adds no semantic
source analysis or lock protocol change.

The final VM run passes six object-image cases, eight original-context read
cases, seven body-witness cases, and the segment wrapper corpus, including
32 GS/RIP executions across reserved GPR destinations, two source-IP ranges
and two backend/ABI combinations. The exact earlier failed object is refused
by the new completeness check. The private provider builds with `W=1`,
`KDLOCK_NUMA=1`, `KDLOCK_SPIN_BATCH=1024`, `KDLOCK_SELFTEST=0` and
`UBSAN_SANITIZE=n`. These are component checks, not live ownership-transfer proof.

Every check attempt is retained under [checks](checks/): `87430984` stops at
missing ABI2 fixture symbols; `b9b4e83f` stops at the old read-metadata
expectation `3968`, which omitted the existing retained-miss bit 13; the
`15f1c08a` attempt passes. No module was loaded by those preflight attempts.

## Workload and results

Unchanged will-it-scale commit `75f66e45697e6f5f49c33dd950c4e6b289198f8f`:
`mmap1_threads -t 2 -s 2 -m` and `mmap1_processes -t 2 -s 2 -m`.
Workers use CPUs 0/1, collector 63 and service pool 0–61. The VM has 64 vCPUs
in two NUMA nodes (0–31 and 32–63), fixed host policy 2.0 GHz, and lazy
preemption. Kernel Build ID is `5f2fce72a33480f6e79a79b374b21a0db377ecd1`,
release `7.0.0-38-kdscope5`, boot
`95abf641-2398-4758-ba85-7937cc651622`, `kd_mmap=on`. Kernel components are
from `1ab7124abb6140752c1f0bb6e862144d426a3875`. Original JIT images, demand
preparation, quiet benchmark provider and disabled service tracing were used.

Rates below are mmap/munmap pairs per **nominal** second: sum the two
post-marker sample totals and divide by two. Six upstream warmup samples are
excluded. Exact elapsed sample duration is not independently measured.

| Model | Retained Native control | Learning 0 | Learning 1 | Learning 2 |
| --- | ---: | ---: | ---: | ---: |
| Threads | 250,997.0 | 106,568.5 | 100,090.5 | 101,708.0 |
| Processes | 669,612.0 | 329,256.0 | 330,626.0 | 331,221.0 |

All six KD rates are **unscored learning observations** from different image
generations. Descriptive differences from the Native control are respectively
−57.54%, −60.12%, −59.48% and −50.83%, −50.62%, −50.54%. These losses are
retained; they are not a qualified estimate of a stable KD/Native gap or a
before/after gain. No measurements are averaged across generations.

The retained Native controls used the same kernel image/topology, `kd_mmap=off`,
boot `b3e73924-47d9-48ce-a45c-baee018d123e`, and runner source
`805e29f3d4c11f602740c066a7ac26c5689d2ef3`. Their original receipts and raw
samples are copied under each model's `native-control/`; Native was not rerun.

Three bounded learning lifetimes and a 900-second learning deadline were
configured per model, with one scored round allowed afterward. No scored point
started: every pass changed the registry. Threads changed all 12 registered
entries in each pass, progressing generations 1→2→3→4. Processes added one
entry, then changed all 13 existing entries in subsequent passes. The equality
check in `demand_learning()` therefore withheld timing instead of silently
renewing a scored receipt or increasing the learning bounds.

Read-only review confirms changed assembly/binary hashes across these
generations and real completed compiler jobs. Existing-row registration in
`execution/registry_publish.inc` is a no-op, and `daemon/daemon.c` skips NORMAL
entries. The CALL/IJ miss path drives replacement; the ready lookup requires
NORMAL, so further delegated coverage can require a later application lifetime.
Exact runtime miss-history edges and joins from every kernel `pid=0` entry to
a benchmark worker were not captured. These receipts cannot attribute every
replacement to a particular mmap1 worker or critical section.

## Compilation, proof limits and retirement

Threads completed 48 compiler jobs: total wall time 634.365 seconds, median
13.208 seconds. Processes completed 51: total 674.220 seconds, median 13.158
seconds. All jobs returned zero. This accounts for most session delay outside
the application samples; it is not an application-runtime profile. The 12 and
13 latest retained objects all pass the completeness check and contain no
unnamed spill. The corrected `map_vdso` source sequence restores R13 directly
from `Stack_RSP` after the GS/RIP load.

Service tracing was off. Per-worker returned JIT bodies, complete delegated MM
paths, delegated read tails, fresh successor-writer drainage, physical batch
length and critical-section ratio were not measured. Publication and application
completion do not prove those properties. The separate permanent ownership
transfer/immediate requeue design is not implemented by this correction.

Both failed comparison verdicts remain unchanged. Separate retirement receipts
verify inactive bindings, zero frames, exact registry/module note and source
module count, then normal daemon close, zero writers, `RETIRE` producing
`state=2 modules=0 frames=0 writers=0`, normal unload and idle state. No forced
unload or reset was used. Long-sleeping service-worker reports are retained in
the application logs; the invalid-store fault did not recur.

[Normal recovery](normal-recovery.json) verifies `7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`a2264466-7090-4587-baf8-177d7394f485`, idle state and empty `next_entry`.
All 7,166 frozen source files remained unchanged after execution.

[summary.json](summary.json) contains identities, rates, registry changes,
compiler timings and object checks. Raw application receipts, sample output,
image-session receipts, compiler metrics and retirement records are retained
per model; [files-sha256.json](files-sha256.json) binds the captured files.
Raw logs retain their original terminal blank lines.
Complete workspaces remain on the VM under
`/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/bench/spill-15f1c08a/`.
