# Collection candidate test-session handoff

The kernel candidate is `629f20ab6d5b9fe17bac420c4eac03fcd50056a5`, based on
`b74e65106a9f2315ded12264d570848ed48f0e13`. It replaces the full frame-array
walk with an exact pending-grant list. The [collector review and focused
checks](../../tests/episode_collection/README.md) describe source authority,
unchanged release order and final-user handling. Compilation, unit/live
validation and performance remain unrun for this candidate.

The separate harness change makes the previously fixed kernel release and
return-thunk address explicit inputs. It also matches the module build receipt
to the selected kernel ELF and the requested thunk to the live built-in text
symbol. The existing boot/GS proof, signed module hashes, thunk bytes and all
workload checks remain required. Defaults preserve the old kernel9 selection;
candidate commands must provide both identity arguments. These checks are not
another kernel optimization. The two commits must be reported separately.

## Preserve the baseline and build the candidate

The bench session owns all VM operations. Preserve the kernel9 image,
source/output tree, boot/recovery entries, frozen b74e6510 source and completed
recorder receipts. The baseline report and raw archive are at
`/tmp/kdlock-main-recorder-ab-20261112-zk79bf/report`; their hashes are recorded
in the collector guide. Do not overwrite or restage the baseline directory.

`episode.c` is built into `kdlock_rebuild`, and frame/resource layouts change.
An isolated kernel build, install and boot with a distinct release are required
before loading candidate modules. Use the frozen candidate's `Kbuild`,
`include/` and `kernel/` files in the established source/output-separated kernel
build. Rebuild all dependent objects. Keep the authenticated Linux source,
configuration, compiler and topology comparable; record necessary release
identity differences and the complete build receipt. Preserve the baseline
kernel and verified recovery point throughout. A timeout does not prove drain.

Bind the new live boot to its exact ELF hash/Build ID, configuration, source
manifest and fresh GS proof. Recheck idle state, disk headroom, recovery and host
placement before staging and live work. Do not call a new module on the old
running kernel an optimization measurement. If a kernel or module check fails,
retain the failed stage and inspect its actual state before any next stage.

## Bounded validation and measurement

In the VM, set `nano_source` to the frozen candidate source; `kernel_source`
and `kernel_output` to the candidate kernel trees; `experiment_root` to a new
output directory; and `kernel_release`, `boot_id`, `gs_proof` to the verified
candidate identities. Set `builtin_source_start` to that kernel's exact
`__x86_return_thunk` address, which must agree between ELF and live kallsyms.
The supported two-byte source span remains `c3cc`; a changed thunk is a refusal,
not permission to broaden this experiment. Do not reuse the old GS offset or
old thunk address without current evidence.

Configure the eight collector checks with the explicit VM JSON described in
the collector guide. Run only these and the affected recorder/identity units:

```sh
python3 -B -m unittest discover -s "$nano_source/tests" -p test_episode_collection.py -v
python3 -B -m unittest discover -s "$nano_source/tests" -p test_nano_recording.py -v
python3 -B -m unittest discover -s "$nano_source/tests" -p test_nano_identity.py -v
python3 -B "$nano_source/bench/nano/build.py" \
  --repo "$nano_source" --kernel-source "$kernel_source" \
  --kernel-output "$kernel_output" --expected-release "$kernel_release" \
  --output "$experiment_root/build" --backends kdlock
```

Rebuild and run the existing mutex recursive, rwsem reader/mode and managed
killable fixtures, as specified in the collector guide, with this same kernel
and frozen source. Retain exact lifetime/physical-ACK checks and ordinary
unload. This is the directly affected correctness set, not a full suite or mmap
campaign. Complete these checks and both functional recorder lanes before
either timed lane:

```sh
for nano_family in mutex rwsem; do
  python3 -B "$nano_source/bench/nano/run.py" \
    --repo "$nano_source" --build-receipt "$experiment_root/build/result.json" \
    --family "$nano_family" --backend kdlock --scope recorder-pair \
    --stage functional --output "$experiment_root/functional-$nano_family" \
    --expected-release "$kernel_release" --builtin-source-start "$builtin_source_start" \
    --boot-id "$boot_id" --kernel-elf "$kernel_output/vmlinux" --gs-proof "$gs_proof" || exit "$?"
done
for nano_family in mutex rwsem; do
  python3 -B "$nano_source/bench/nano/run.py" \
    --repo "$nano_source" --build-receipt "$experiment_root/build/result.json" \
    --family "$nano_family" --backend kdlock --scope recorder-pair \
    --stage timing --output "$experiment_root/timing-$nano_family" \
    --prerequisite "$experiment_root/functional-$nano_family/result.json" \
    --expected-release "$kernel_release" --builtin-source-start "$builtin_source_start" \
    --boot-id "$boot_id" --kernel-elf "$kernel_output/vmlinux" --gs-proof "$gs_proof" || exit "$?"
done
```

Keep the same one-worker CPU 0, collector 63, cacheline1/post256 body, write
mix, capacities, proxy limit 16, training and alternating three two-second
on/off pairs per family: twelve candidate timed phases total. The common
untimed training must still prove generated completion; recorder-on timing
may remain NO_JIT, and recorder-off evidence remains explicitly unavailable.
Preserve every pair and sample, failed phase, fixed-image/empty-claim checks,
normal retirement/unload and host auxiliary-thread placement limits.

Report candidate-on versus baseline-on and candidate-off versus baseline-off,
with each source, kernel build and boot kept distinct. Record the source-only
mechanism hypothesis, actual build/correctness verdicts and measured changes
separately. This small comparison remains exploratory across separate boots;
it does not prove strict timing qualification or explain the full Native gap.
