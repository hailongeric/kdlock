# Linux 7 MM catalog execution plan

This is a prepared command plan, not a test or performance pass. Runner ports
and their focused tests are authored on 380G10. All tests, compilation, module
work and timing run only in the VM, after the current lock/API campaign drains.
Do not synchronize sources, build a kernel or reboot during that campaign.

| Catalog suite | Arms | Points | Kernel |
| --- | --- | ---: | --- |
| Independent-mm untouched mmap/munmap | Native | 21 | `7.0.0-38-kdlock1`, MM adapter disabled |
| Private-backing page-fault cycle | Native / KD local reader / TCLock local reader | 63 | Same disabled-MM kernel |
| Actual shared-mm untouched mmap/munmap | Native / KD local MM backend | 42 | Separate `7.0.0-38-kdmm1`, `kd_mmap=off` / `on` |

Each arm uses workers 1–8 and 12–60 in steps of four, one plain repetition per
point. Workers use the CPU prefix 0..N−1; the collector uses CPU 63. Configured
host frequency remains 2.0 GHz with turbo disabled. The private backing lock is
separate from the real kernel mmap lock. The shared suite compares that real
lock while all MM bodies execute on the original task. No MM-body JIT delegation
is claimed. These 4 KiB device mappings do not replace the planned mmap1 target.

## Current-kernel private suites

Use the pinned interpreter
`/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3`, the current
confirmed recovery tag, exact verified boot UUID and schema-2 bundle. Obtain a
fresh host capture before every phase, and supply its original reference with
an independently recorded SHA256. `--host-state` must be at most five minutes
old when admitted. The commands below use shell variables for those recorded
paths; they are not inferred from historical receipts.

```bash
MM_PY=/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3
MM_COMMON=(--boot-id "$MM_BOOT" --host-state "$MM_HOST_NOW"
  --host-reference "$MM_HOST_REFERENCE" --host-reference-sha256 "$MM_HOST_SHA")
"$MM_PY" tests/kernel/mmap_fault/run.py "${MM_COMMON[@]}" \
  --source-manifest "$MM_SOURCE_MANIFEST" --output "$MM_RAW/private-correctness-kd" \
  --backends 0,1 --split
"$MM_PY" tests/kernel/mmap_fault/run.py "${MM_COMMON[@]}" \
  --source-manifest "$MM_SOURCE_MANIFEST" --output "$MM_RAW/private-correctness-tc" \
  --backends 2 --split --native-kd-result "$MM_RAW/private-correctness-kd/result.json"
"$MM_PY" bench/mmap_fault/timing.py prepare "${MM_COMMON[@]}" \
  --source-manifest "$MM_SOURCE_MANIFEST" --output "$MM_RAW/private-preparation" \
  --correctness-kd "$MM_RAW/private-correctness-kd" \
  --correctness-tc "$MM_RAW/private-correctness-tc" --plain-only
"$MM_PY" bench/mmap_fault/check_oracles.py "$MM_RAW/private-preparation"
"$MM_PY" bench/mmap_fault/timing.py measure "${MM_COMMON[@]}" \
  --inputs "$MM_RAW/private-preparation/inputs.json" --output "$MM_RAW/independent-mmap" \
  --single-round-grid --workload mmap --exploratory-host
"$MM_PY" bench/mmap_fault/timing.py measure "${MM_COMMON[@]}" \
  --inputs "$MM_RAW/private-preparation/inputs.json" --output "$MM_RAW/private-fault" \
  --single-round-grid --workload fault --exploratory-host
```

Refresh `MM_HOST_NOW` and rebuild `MM_COMMON` before each phase. Correctness must
pass all Native/KD and TCLock split cases; preparation validates all eight
workload/arm/1-or-16-worker combinations. Exact fault callbacks, local-reader
releases, completed operations, joins, CPU placement and normal drain remain
mandatory. Only absence of a positive full-cohort peak window is optional in
the explicit single-round plan. Keep whole-operation throughput in that case.

## Separate enabled-MM kernel

Use the explicit variants in the [Linux 7 identity guide](../../kernel_integration/linux70/IDENTITY.md).
The canonical development roots are
`/mnt/kdlock-builds/linux-7.0.0-38-kdmm1/{source,build}` and the release is
`7.0.0-38-kdmm1`. Preserve the current working kernel and recovery snapshot.

1. After timing drains, copy the authenticated pristine Ubuntu source into the
   new source root, apply the reviewed core patch with zero fuzz, and generate
   a fresh MM overlay from pristine input as specified in the identity guide.
   Preserve the source archive identities and new core/MM preparation receipts.
   Copy only the named overlay outputs; check every output and all seven
   unchanged native MM body hashes against the recorded inputs.
2. Create an independent build output using the current configuration. Enable
   only `CONFIG_KDLOCK_MMAP=y`, with the new release/signing identities. Review
   the entire config difference; keep the existing restrictions excluding RT,
   lockdep, DEBUG_LOCK_ALLOC and DEBUG_MUTEXES. Do not change native MM bodies,
   upstream version code, mitigation or preemption settings to obtain a pass.
3. Run the enabled affected-object/scope check and extracted deferred-read
   reservation fixture. Build the full image and modules using the same
   Ubuntu-style `KERNELRELEASE` override as the existing kernel. Keep upstream
   version 7.0.14 and `LINUX_VERSION_CODE=458766`; do not override `SUBLEVEL`.
4. Install the separately named image/modules with the reviewed module signing
   procedure, refresh initramfs/GRUB and preserve recovery. First boot with
   exactly one `kd_mmap=off`, active lazy preemption, `nokaslr` and `nopvspin`.
   Require the new release/build/header/installed-file identity, clean service
   and kernel state, topology and snapshot evidence before live probes.
5. Capture `kdmm1-native` into
   `/root/kdlock-kernel-baselines/linux70-kdmm1-native-20261027`. After clean
   Native checks, boot the same image with `kd_mmap=on` and capture `kdmm1-kd`
   into `/root/kdlock-kernel-baselines/linux70-kdmm1-kd-20261027`. The two bundles
   retain separate exact command lines. Never relabel the disabled kernel.

## Enabled-MM correctness and one-round timing

For each mode, set `MM_MODE` to `native` or `kd`, use that boot's UUID and fresh
host capture, and rebuild the common arguments. `shared_platform.py` selects
only the canonical enabled build and matching mode bundle. All four current
correctness entry points below require these arguments:

```bash
MM_SHARED=(--mode "$MM_MODE" --boot-id "$MM_BOOT" --host-state "$MM_HOST_NOW"
  --host-reference "$MM_HOST_REFERENCE" --host-reference-sha256 "$MM_HOST_SHA")
"$MM_PY" tests/kernel/mmap_lock/run.py "${MM_SHARED[@]}" --output "$MM_MODE_RAW/api"
"$MM_PY" bench/mmap_writer/sites.py --mode "$MM_MODE" --boot-id "$MM_BOOT" \
  --kernel-variant "kdmm1-$MM_MODE" \
  --kernel-source /mnt/kdlock-builds/linux-7.0.0-38-kdmm1/build \
  --kernel-baseline "/root/kdlock-kernel-baselines/linux70-kdmm1-$MM_MODE-20261027" \
  --output "$MM_MODE_RAW/writer-sites"
```

Review the exact function disassembly and record the SHA256 of
`writer-sites/writer-sites.json` as `MM_WRITER_SHA`. The capture is not a live
writer pass. Unexpected direct-call, wait-frame or return shapes refuse capture
and require a precise compiler/ELF review. Then run:

```bash
"$MM_PY" tests/kernel/mmap_lock/mapping.py "${MM_SHARED[@]}" \
  --api-result "$MM_MODE_RAW/api/result.json" --output "$MM_MODE_RAW/mapping" \
  --writer-sites "$MM_MODE_RAW/writer-sites/writer-sites.json" \
  --writer-sites-sha256 "$MM_WRITER_SHA"
"$MM_PY" tests/kernel/mmap_lock/faults.py "${MM_SHARED[@]}" --output "$MM_MODE_RAW/faults"
"$MM_PY" tests/kernel/mmap_lock/page_fault_completed/run.py "${MM_SHARED[@]}" \
  --output "$MM_MODE_RAW/completed"
"$MM_PY" bench/mmap_writer/linux70.py prepare "${MM_SHARED[@]}" \
  --api-result "$MM_MODE_RAW/api/result.json" --mapping-result "$MM_MODE_RAW/mapping/result.json" \
  --faults-result "$MM_MODE_RAW/faults/result.json" --completed-result "$MM_MODE_RAW/completed/result.json" \
  --output "$MM_MODE_RAW/preparation"
```

Prepare Native first. Add `--reuse-inputs "$MM_NATIVE_RAW/preparation/inputs.json"`
to the KD preparation so the same payload, timed client and frozen runtime
sources are used in both modes. Each preparation runs one and sixteen workers
and checks eleven negative mutations of the real sixteen-worker timing receipt.
Measurement requires both preparations to pass, including exact image/source
identity and identical timed artifacts:

```bash
"$MM_PY" bench/mmap_writer/linux70.py measure "${MM_SHARED[@]}" \
  --inputs "$MM_MODE_RAW/preparation/inputs.json" \
  --other-preparation "$MM_OTHER_RAW/preparation/result.json" \
  --api-result "$MM_CURRENT_RAW/api/result.json" --mapping-result "$MM_CURRENT_RAW/mapping/result.json" \
  --faults-result "$MM_CURRENT_RAW/faults/result.json" --completed-result "$MM_CURRENT_RAW/completed/result.json" \
  --output "$MM_MODE_RAW/measurement" --exploratory-host
```

This runs only the selected boot mode's 21 points. `MM_CURRENT_RAW` must contain
all four correctness passes from the current boot; preparation's passes can be
used if that boot is still active. After a mode-switch reboot, rerun the four
checks into a fresh directory before measurement. The identical timed artifacts
remain reusable across those verified boots. Repeat on the other verified mode
for 42 total. No driver boots a kernel or changes the selected backend.
The API probe retains cancellation, exclusion, downgrade, acquired-read
transfer, IRQ release and destruction checks. Mapping requires an actual
same-mm blocked writer with exact ELF-bound return frames. Fault controls cover
retry/VMA revalidation, fork/COW/exit/remote accesses and genuine completed-fault
returns. The retired phase observers with unbound instruction sites remain
disabled. BPF/IRQ/NMI coverage beyond these focused checks remains explicit.

## Evidence and focused verification

Run these directly affected tests in a new private frozen VM source copy:
`bench/mmap_fault/test_platform.py`, `bench/mmap_fault/test_single.py`,
`bench/mmap_writer/test_sites.py`, `bench/mmap_writer/test_linux70.py`, and
`tests/unit/bench/test_mmap_aggregate.py`, plus the updated kernel-identity tests.
Do not describe authored tests or successful object compilation as live passes.

The source controller must retain fresh host endpoints and frequency-monitor
evidence, and write a table/chart after each suite completes. Runner records
remain `accepted=false` with `host_endpoint=PENDING` until that evidence is
checked. Single-round tables have no repeat-based variance estimate. Preserve
failures and distinguish configured frequency from measured effective frequency.
