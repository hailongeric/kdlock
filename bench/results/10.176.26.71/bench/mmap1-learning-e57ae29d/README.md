# Retained-image learning: bounded eight-process comparison

The Native arm completed. The KD arm encountered a kernel failure during
preparation, before its final measurement window. The candidate remains
unaccepted; no performance gain, successful MM completion, or pending-image
runtime proof is claimed. No additional workload was run after the failure.

## Candidate and focused checks

The isolated branch is `codex/mmap-reached-jit`:

- Design: `3b598b7a7fa55feee7db9bc22ab47f31aa4aa57f`.
- Implementation: `796fbb9906f2e044ed426bb6c1ea1ddf6a33698f`.
- Fixture correction and tested revision:
  `e57ae29d53c00d0bde215b3eee696239e118e2be`.

Eligible retained ABI2 captures can use an immutable image while a recoverable
CALL/IJ report is pending. Publication uses one revisioned latest-report record
and a per-device read/upload receipt; duplicates coalesce, distinct replacements
are counted, and publication cannot erase a newer report. Daemon command reuse
is generation-qualified. Ordinary batch readiness and terminal continuation
behavior remain unchanged. This does not implement separate child images.

The first VM check attempt passed service joins, immutable images, retained
terminal paths, the selected source-frontier case and the sample-window harness.
Demand activation then failed compilation: its mock lookup could index `-1`
for an unknown entry. The fixture-only correction returns NULL and checks the
index before reading readiness. The failed receipt is retained. The five
unchanged groups were reused; the corrected group and remaining checks passed.

The production registry fixture completed **63,488 checks, zero failures**,
including report acknowledgment/replacement and failed-read receipt rollback.
Daemon-policy checks passed. The provider and daemon built on the VM. Existing
assembly warnings and the compiler-name warning remain in the full build log;
the build is not warning-free. There was no additional Nano run, broad suite,
or claim of live validation for every API combination.

Static dispatch verification also confirms that retained entry/resume bypass
the NORMAL-only check at `kernel_module/exe.c:298`. The checks at
`kernel_module/execution/wrapper_entry.inc:918` and `:1014` belong to ordinary
spin/mutex batch preparation. The immediate call chain is retained in
`../../raw/bench/mmap1-learning-e57ae29d/dispatch-check.md`.

## Matched run configuration and result

Both arms use unchanged will-it-scale
`75f66e45697e6f5f49c33dd950c4e6b289198f8f`:

```text
mmap1_processes -t 8 -s 724 -m
```

Each arm has one application lifetime: six upstream warmup samples, 714 further
preparation samples, then ten selected measurement samples. PTY delivery marks
sample 720 and sample 730; the executable is unchanged. The application bound
is 800 seconds; KD learning/drain is separately bounded at 1200 seconds.

Kernel `7.0.0-38-kdscope5`, Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`, is identical across modes:
`kd_mmap=off` for Native and `kd_mmap=on` for KD. Both use lazy preemption,
64 vCPUs and 24 GiB. Requesters use CPUs 0–7 on node 0, KD executors 0–61
across both nodes, and the collector CPU 63. The verified host policy is fixed
2 GHz. Strict timing qualification remains separate; these are exploratory
single-round observations with no repeat variance.

| Arm | Final-ten pairs | Pairs per nominal second | Outcome |
| --- | ---: | ---: | --- |
| Native | 22,378,192 | 2,237,819.2 | Completed and drained |
| KD | Unavailable | Unavailable | Kernel failure during preparation |

Native retained all 730 samples. The callback interval was 10.001281210 seconds;
the reported rate uses ten nominal samples, not that callback interval. Its
original 724-sample upstream average, 2,233,043, is retained separately.

KD retained 348 complete sample lines, including three zero-progress lines,
followed by an incomplete tail containing 660 zero bytes. No sample-720 or
sample-730 callbacks exist. The original application record remains RUNNING,
`passed=false`, `drained=false`; it is not rewritten to suggest normal exit.
Seven compiler completion records returned zero, totaling 362.509763767 seconds
of compiler wall time; several occurred after the first failure and are not
correctness evidence. Current generated artifacts and histories were preserved,
but do not identify the exact image bound to the first failing request.

No paired pending-image/counter snapshots were obtained: the attempted read
timed out at the guest connection. Whole-application selected counters and
returned-body conservation were not finalized. There is therefore no measured
proof here that pending-image capture continues successfully through completion.
No KD/Native percentage is calculated from an incomplete preparation prefix.

## First failure and interpretation

The earliest console failure is at boot time **140.476822 seconds**, or
**104.824910303 seconds after application launch**, on origin PID 2426,
`mmap1_processes`:

```text
RIP: kd_provider_assert_held_write+0x5/0x80
instruction: 48 8b 17   (mov (%rdi),%rdx)
RDI: 856488d3cbaf5b00
```

The recorded chain is `__vm_munmap` → `do_vmi_munmap` →
`do_vmi_align_munmap` → `vms_gather_munmap_vmas` →
`? kd_mmap_assert_held_write` → `kd_provider_assert_held_write`.
The question mark is the unwinder's uncertainty, preserved here.

This is an invalid callback argument dereference before the ownership predicate
or its warning, corresponding to the initial owner load in
`kernel_module/kd_rwsem_provider.c:150`. The adapter should pass `&lock->kd`
through `kernel_integration/mmap_lock/overlay/kernel/locking/kd_mmap/adapter.c:287`.
The first actual ownership warning is later, at 159.178277 seconds on PID 2427.
Later mmap, munmap and scheduler failures cannot establish the initial cause.

Argument/source-stack preservation is an **unproven lead**, not a diagnosed root
cause. The console contains no per-request generation, exported packet, or
handoff record for PID 2426. If it used origin continuation, the narrow chain
to inspect is full register export, retained-miss handling, packet copying in
`kernel_module/kd_service.c:1431`, then the builtin MM completion restore in
`kernel_integration/mmap_lock/overlay/kernel/locking/kd_mmap/provider.c:95`.
That restore loads packet DI into RDI before continuing. Inspect argument setup,
packet DI/SP, stack placement and the single CALL return word against this run's
matching source/build artifacts before another live attempt. Neither downgrade
nor scheduling policy is established as the cause.

## Preservation and recovery

The available full console prefix, 138,929,894 bytes, was compressed and
verified on the host; its receipt records both original and compressed hashes.
It remains at `/tmp/kdlock-learning-e57ae29d-failure/console.log.gz` on the VM
host, with a verified local copy under `/tmp/kdlock-learning-e57ae29d-recovery/`.
Only the current-boot console and compact receipts are duplicated in this
report's raw directory. A new full VM-state snapshot was not made: host free
space was about 3.9 GiB for a 24 GiB guest. The existing recovery snapshot and
guest disks were preserved; no disk rollback was performed.

After one authorized reset, normal `7.0.0-38-kdlock1` was verified at boot
`4ff57d48-bc4c-43bd-9946-b16e0db3d4da`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, with idle state and an empty
one-shot boot selection. Recovery is not proof of ordinary request retirement;
the failed KD run has no exact-retirement receipt.

`analysis.json` retains measured values and failure status. `retained-files.json`
indexes 105 compact raw records by size and SHA256 under
`../../raw/bench/mmap1-learning-e57ae29d/`. The generated-artifact manifest also
records the separately retained current code copies. Master and unrelated work
remain unchanged. The remaining blocker is the unexplained invalid callback
argument, not performance acceptance.
