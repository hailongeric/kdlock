# Rwsem writer delegation validation, 2026-10-18

The [rwsem outer writer](../../../../../docs/design/rwsem_implementation.md)
reserves writer admission and drains readers before entering the selected mutex
ABI2 protocol. Ordinary sleeping readers/writers, cancellation and downgrade
remain available. The mutex queue, pinned published waiters, physical ownership,
immutable images and acknowledgement protocol are unchanged.

This receipt covers focused build, API, correctness and returned-JIT checks.
The separate [standard 1–60-worker performance grid](../../bench/rwsem/20261018/README.md)
completed all 756 sessions with correct results and full drain; its throughput
results remain in that report. All compilation and execution occurred in the
designated recovery VM on `10.176.26.71`.

## Recorded environment

Linux `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, ran with `nokaslr`, `nopvspin` and
voluntary preemption. The guest exposed CPUs 0–63; workers used the CPU prefix
0 through N−1 and collector CPU 63. These functional cohorts used node-0 worker
CPUs and a node-1 collector. The four scheduling-probe workers shared CPU 0.
The recorded recovery snapshot was `before-mutex-kdonly-20261017T140354Z`.
The guest kernel was not modified, rebuilt or rebooted for this work.

Native workloads used the ordinary C rwsem API. KD delegation workloads used explicit
`delegated-epoch-abi2` writers, local readers, NUMA-on, mutex batch limit 1,024,
UBSAN-off private providers, entry/completion probes and post4 work. Each workload
had 48,000 warmup operations per worker. Source, binary, kernel and topology
identities remain attached to their own runs in [validation.json](validation.json).

## Results

| Check | Result |
| --- | --- |
| Dependencies and kernel identity | Passed in v1; final live runners also verified kernel identity |
| Provider build | W=1, UBSAN-off build passed; build diagnostics are retained, not claimed warning-free |
| Basic checks | Both C programs passed, including 56 control-call phase/error combinations and daemon policy/failure observations |
| Context admission | 104 cases passed in v1, including rwsem helper refusal inside translated bodies |
| Mutex waiter/clobber fixture | 32 intact returns and 32 destroyed-frame minimal resumes passed in v1 |
| Runner and shared assembly | 22 rwlock/rwsem-runner tests and 7 shared assembly tests passed in v1 |
| Final ABI fixture | 29 cases passed in v3 after correcting obsolete symbol identities; the earlier failure is retained below |
| Sleeping/API probe | Final v3 probe passed all expected result fields, with zero errors and complete drain |
| Native/KD functional workloads | 24 sessions: c01/c08/RCUHT × 1%/20% writes × 1/8 workers × Native/KD, 100,000 operations per worker; all correct and drained |
| Strict returned-JIT acceptance | Four additional v3 sessions passed, detailed below |
| Local and read-only controls | Five v4 c08 sessions passed: ordinary local writers at 0%/20% writes and 1/8 workers, plus the outer writer shell at 0% writes/8 workers; 100,000 operations per worker, correct results, zero JIT and complete drain |
| Final health | Idle after the performance grid and controls; unchanged boot ID, 233 source files and 9 binaries verified, no Linux mutex API imports, no new faults in retained kernel logs |

The scheduler probe recorded `api_checks=8`, `cancellation_checks=10`,
`readers_slept=2`, `writer_slept=1`, `late_reader_slept=1`,
`outer_readers_slept=2`, `outer_writer_slept=1`, `downgrade_checks=1`,
`publication_checks=3`, `colocated=1`, `errors=0` and `idle=1`.
It verified that sleeping readers can resume before an outer writer publishes,
and that ordinary downgrade cannot create a reader behind a published outer
writer. The probe used local outer returns and records zero JIT bodies.

The 24 functional sessions likewise recorded zero JIT entries/completions; they
are correctness evidence, not delegation acceptance. Separate `--require-jit`
runs used 16 workers and 200,000 operations per worker, giving 3,200,000 completed
operations per session:

| Workload | Writes | Reads | Writes completed | JIT entries and matching completions |
| --- | ---: | ---: | ---: | ---: |
| c08 | 100% | 0 | 3,200,000 | 3,174,269 |
| RCUHT | 100% | 0 | 3,200,000 | 3,178,872 |
| c08 | 80% | 640,000 | 2,560,000 | 404,874 |
| RCUHT | 80% | 640,000 | 2,560,000 | 163,345 |

All four sessions passed business-result checks and complete drain. Every worker
completed its assigned count. The mixed c08 run also recorded zero reader
consistency errors across its eight updated cachelines. These are fixed-iteration
acceptance checks, not performance samples for the 1%/20% comparison.

## Retained failures

- **v1 ABI fixture:** the aggregate basic/affected command failed one of five
  drivers. Its old ABI2 fixture supplied Linux bridge symbol names rather than
  the selected KD-only direct endpoints, causing identity admission to refuse.
  The fixture now uses direct endpoint identities and separately checks rejection
  of obsolete bridge-only identities. Production admission was not weakened.
- **v1 probe build:** MODPOST rejected the module's call to the unexported
  `kd_mutex_waiter_count` accessor. The probe now reads the same exact atomic
  waiter-count field directly. No provider mutex export or protocol changed.
  This attempt failed before loading the probe and is not a live test pass.
- **v2 invocation:** direct Python invocation omitted the unit runner's import
  setup and failed with `ModuleNotFoundError: test_jit_diagnostics`. The same
  227-file source manifest passed in v3 through the supported Makefile driver.
- **v3 strict acceptance at 20% writes/32 workers:** c08 completed all 3,200,000
  operations, including 640,000 writes, with correct data and full drain, but
  recorded zero JIT entries or completions. `--require-jit` correctly failed.
  The following RCUHT item remained `NOT_RUN`; its placeholder `drained=false`
  describes an unstarted plan item, not an outstanding live acquisition.

That last failure was heat admission, not translation refusal. All 32 CPUs
became CPU-hot, but their subsequent per-lock samples ended at 349–698, below
the unchanged 1,025-sample lock threshold. The logs record `lock_hot=0` and zero
mutex slowpath, combiner and JIT-success counts. The published translation was
accepted; publication alone did not make these callers eligible to delegate.

The later 80% and 100% acceptance passes are different workloads and do not erase
the 20% failure. This receipt therefore contains 33 successful workload checks,
one executed/drained acceptance failure and one unstarted plan item, plus the
separate scheduler probe. It is not a full-suite pass, performance-parity claim,
oversubscription validation or integration into `mm_struct::mmap_lock`.

## Evidence and source distinctions

[validation.json](validation.json) preserves command exit statuses, manifest
hashes and selected input hashes, all compact session outcomes, the final probe
result, kernel/boot identities and retained failures. The static
[source comparison](mutex-source-equivalence.json) records 112 inputs unchanged
from `d2a2304`, including all 16 mutex-specific paths, with explicit exclusions
for the new rwsem implementation and prior integration. Guest roots are:

- `/mnt/kdlock-builds/rwsem-delegation-20261018-v1`
- `/mnt/kdlock-builds/rwsem-delegation-20261018-v2`
- `/mnt/kdlock-builds/rwsem-delegation-20261018-v3`
- `/mnt/kdlock-builds/rwsem-delegation-20261018-v4`

The v1 snapshot contains the original failed fixtures. The v2 and v3 unit
snapshots share SHA-256
`a2bb431ca36b74907a43f65b6d7e81952dd0404beefa489de3ab8ec17c2179e7` for their
227-file source manifest. The four v3 workload groups share SHA-256
`4ab41cc461d68945022c74a305a1e28258901bd6dbab2dc907128e78c8ef41e3` for their
workload source manifest; both v4 control groups share that same source manifest.
The probe has its own manifest and binaries.

The saved mixed-JIT caller disassembly and `publications/00/jit.S` also preserve
the completion boundary. For c08, the direct mutex unlock returns to
`rb_write+0x106`, and the phase-exit call follows at `+0x10d`; RCUHT uses `+0x14b`
and `+0x152`. Both translated images check the matching continuation and leave
through `clobber_complete`. Thus the compiled phase release remains after the
origin's completed mutex unlock. The exact addresses belong to those frozen
module loads and are not stable API addresses.

The [archive receipt](archive.json) records the final transfer and integrity
metadata for raw evidence from v1–v4 under
`bench/results/10.176.26.71/raw/tests/rwsem-delegation-20261018/`.
The final v4 health record is embedded with its SHA-256 in
[validation.json](validation.json). It records an idle guest with the same boot
ID as the preceding checks and verified source/binary inputs. Kernel-log coverage
is the final retained ring plus each session's own fault checks; the ring may
have rotated, so this is not a claim that its final contents retain every prior
kernel message. Performance evidence is retained separately in the
[grid report](../../bench/rwsem/20261018/README.md).
