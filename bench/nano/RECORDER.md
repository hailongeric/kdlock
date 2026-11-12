# Single-worker recorder comparison

This is a source-only handoff to the separate **bench new version kdlock**
session. Source changes remain in the restructure session. That test session
owns VM inspection, frozen staging, builds and live measurements, and must not
edit the shared source tree. No build, unit test or live result is claimed for
this change until that session supplies its receipts.

The preserved baseline is `526fcc48`, with the kernel9 regression at
`aea4edd8`. The existing 54-session archive is unchanged. This experiment
isolates observation overhead before any kernel optimization: no `kernel/`,
`include/`, payload, post-work, lock binding or batching setting is changed.

## Control and evidence

Recording remains enabled by default. The `RB_RECORDING` ioctl only changes
the workload's `rb_observe` tracepoint subscription under the existing exclusive
ioctl admission gate. It refuses a live worker, retained worker storage or a
nonempty lock state. Disabling unregisters and synchronizes the listener;
enabling registers it again. Both modes retain the same allocated measurement
storage, map setup, task enter/leave and source/runtime configuration. No
recording branch is added to the per-operation workload loop.

The control returns both subscription state and the core tracepoint enabled
state. The paired runner requires both to match the requested mode. A remaining
observer makes the off phase fail before measurement rather than silently
measuring only partial removal. With the last listener removed, off mode skips
tracepoint dispatch, event construction guarded by the tracepoint key, and the
recorder's lookup, IRQ-saving spinlock, counters and witness copies. It measures
this combined observation path, not just the callback's spinlock.

All protocol ownership, request/frame/image users, source leases, release ACKs,
256-frame collection scans, auxiliary-stack switching and task/runtime/source
retirement remain. Exact operation/mix/post-work/snapshot checks, normal
`leave_current`, runtime/provider destruction, source archival/settlement,
fault checks and ordinary unload remain required. Recorded request-retirement
and read-credit observations are unavailable in off mode; actual core lifetime
checks still run. Unavailability is not proof that no generated body executed.

`RB_EVIDENCE` reports `EOPNOTSUPP` for an unrecorded phase. Its availability is
captured at phase configuration; changing subscription invalidates availability
until the next configuration, so a later change cannot relabel earlier data.
Userspace emits `EVIDENCE_UNAVAILABLE` with null JIT entry,
completion and share fields. Other ioctl errors remain errors. Recorder-on
validation retains the original exact witness and request-lifetime checks.

## Fixed experiment

Select `--scope recorder-pair --backend kdlock`. Default `--scope comparison`
retains the existing full comparison behavior and prerequisite checks.
The narrow functional prerequisite is a current matching family/boot/build
recorder-pair receipt; it cannot satisfy a full-comparison prerequisite.

Each family load performs the unchanged 32-operation local phase and the
existing eight-worker bounded training with recording on. Training must prove
completed generated execution and an empty feedback claim. Afterward the
same loaded module, source epoch and published image serve both modes. One
256-operation single-worker functional phase runs in each mode. Timing then
runs three two-second phases per mode, ordered on/off, off/on, on/off. Only
CPU 0 is timed; collector CPU 63, post256, deterministic write mix, batching,
progress sampling and whole/warmed-peak denominators remain unchanged.
Both families together produce **12 timed phases**, not another 54-session
matrix. The eight-worker work is common untimed training only.

The phase receipt records requested/returned recorder state and exact fixed
image identity. Every post-phase claim must remain empty with no publication.
Compare on/off within this new build and boot. Retain all pairs, NO_JIT on-mode
results, unavailable off-mode evidence, failed phases and timing limits.
Do not substitute historical kernel9 medians for the current on-mode control.

## Test-session invocation

Use a fresh experiment directory on the existing kernel9 boot/build. Verify
recovery, idle state, disk reserve, host pins/frequency policy and live kernel
identity before staging; keep the source snapshot immutable. The existing
kernel ELF must still have SHA256
`0fe0fe930e391bb263fdcfa4ba9940eee225280a668021cb11a269a691cb8c15`,
Build ID `8198ffae09db584dce9b71d92b5743a4146ba80a`, release
`7.0.0-38-kdrebuild9`. No kernel rebuild/install/reboot is needed for this change.
Bind `$boot_id` and `$gs_proof` to freshly verified live identities; do not reuse
an old boot assertion. Preserve the exploratory CPU-63 auxiliary-worker policy
and report its limits separately from operation correctness.

In the VM, set `$nano_source` to the verified frozen source directory,
`$experiment_root` to its fresh output parent, and `$kernel_source` and
`$kernel_output` to the existing source/output-separated kernel9 paths. Run only
the focused test and two KD module builds:

```sh
python3 -B -m unittest discover -s "$nano_source/tests" -p test_nano_recording.py
python3 -B "$nano_source/bench/nano/build.py" \
  --repo "$nano_source" --kernel-source "$kernel_source" \
  --kernel-output "$kernel_output" --output "$experiment_root/build" \
  --backends kdlock
```

Require the unchanged payload/post-work/binding source hashes and record both
signed module hashes, compiler flags and exact build warnings. Complete both
functional lanes before either timed lane:

```sh
for nano_family in mutex rwsem; do
  python3 -B "$nano_source/bench/nano/run.py" \
    --repo "$nano_source" --build-receipt "$experiment_root/build/result.json" \
    --family "$nano_family" --backend kdlock --scope recorder-pair \
    --stage functional --output "$experiment_root/functional-$nano_family" \
    --boot-id "$boot_id" --kernel-elf "$kernel_output/vmlinux" --gs-proof "$gs_proof" || exit "$?"
done
```

After both functional results pass and ordinary unload is confirmed:

```sh
for nano_family in mutex rwsem; do
  python3 -B "$nano_source/bench/nano/run.py" \
    --repo "$nano_source" --build-receipt "$experiment_root/build/result.json" \
    --family "$nano_family" --backend kdlock --scope recorder-pair \
    --stage timing --output "$experiment_root/timing-$nano_family" \
    --prerequisite "$experiment_root/functional-$nano_family/result.json" \
    --boot-id "$boot_id" --kernel-elf "$kernel_output/vmlinux" --gs-proof "$gs_proof" || exit "$?"
done
```

A failed or timed-out observer retains its child/module state; stop and inspect
it. Do not force unload, infer drain from timeout, fall back to a different
kernel or replace absent evidence with a successful completion count. Archive
the exact input manifest, commands, all phase receipts, host placement and
ordinary shutdown evidence in a new result directory.
