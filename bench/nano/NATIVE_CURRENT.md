# Bounded Native versus current KD-off comparison

This harness adds `--scope native-current` to the existing runner. Both mutex
and rwsem use one timed worker on CPU0, collector CPU63, one padded cacheline,
post256, the existing deterministic write mix (100% mutex, 20% rwsem), three
two-second samples per backend and the unchanged progress/peak criteria.
Native and KD-off together produce 12 timed samples. This scope accepts only
Native and KD. Default comparison and recorder-pair retain their existing plans
and prerequisite requirements.

The first handoff keeps core, headers, compiler, workload modules and evidence
ABI2 at `a1ad50e5f218dbeb3dd4f7c77e0568271c3880ca` on kernel11. Its source
archive is that exact baseline plus an explicit overlay of this guide,
`run.py` and `tests/test_nano_native_current.py`. The overlay commit and every
file hash are recorded separately. Use that frozen archive for the baseline
comparison; current main also contains the subsequent reader candidate. No
new kernel build or reboot is required for this harness alone. Existing
kernel11 source/build/ELF/configuration/boot and recovery evidence remain
required. Preserve all kernel9/10/11 inputs and prior receipts.

## Correctness and phase ordering

Timing requires four successful functional receipts: mutex and rwsem, each
with Native and KD. All four must use this scope, the same build receipt,
current boot and identical runner bytes. A missing/duplicate lane, old scope,
changed build/boot/runner, or incomplete KD on/off functional pair is refused.
Native has no KD recorder ioctl; its recorder metadata says `unavailable`.
KD explicitly verifies recorder control for every phase, including listener
state. Off-mode generated and retirement observations remain unavailable.

Each load retains the existing 32-operation local phase. Every KD invocation
retains bounded eight-worker training with recording on, returned JIT-body
evidence and an empty claim. It then runs single-worker functional checks with
recording on and off. Native performs its own ordinary functional check.
Timing repeats these prerequisites within the load before its three samples.
All three KD timing samples run with recording off against the same trained
image. Every subsequent claim must remain empty with no publication. Native
uses the same body, mix, postwork, worker placement and timing specification.

The initial bounded invocation order is mutex Native, mutex KD-off, rwsem
Native, rwsem KD-off, with three samples in each load. Preserve command and
phase timestamps; these are sequential backend blocks, not interleaved pairs.
Training, local and functional work is untimed. Exact data/mix/postwork checks,
kernel faults/taint checks, source settlement, runtime destruction, ordinary
unload and final device absence remain mandatory. A timeout retains state and
does not establish drain.

## Bench-session invocation

Only the existing bench session runs the following. Stage a fresh immutable
snapshot while idle, verify recovery/headroom and kernel11 identity, and set
the existing exact paths and live identity variables. All outputs must be new.
Run the six new scope checks, the baseline's eleven recorder checks and five
kernel/module identity checks in the VM (22 tests total for this handoff):

```sh
python3 -B -m unittest discover -s "$nano_source/tests" -p test_nano_native_current.py -v
python3 -B -m unittest discover -s "$nano_source/tests" -p test_nano_recording.py -v
python3 -B -m unittest discover -s "$nano_source/tests" -p test_nano_identity.py -v
python3 -B "$nano_source/bench/nano/build.py" \
  --repo "$nano_source" --kernel-source "$kernel_source" \
  --kernel-output "$kernel_output" --output "$experiment_root/build" \
  --expected-release 7.0.0-38-kdrebuild11 --backends native kdlock
```

This builds four fresh workload modules against the existing kernel11 output.
Use the same resulting build receipt for every functional and timing lane.
Record signed module hashes and warnings. In Bash, bind the common runner
arguments to the verified inputs, including the live/ELF ITS address and its
admitted `c3cc` span:

```bash
nano_common=(--repo "$nano_source" --build-receipt "$experiment_root/build/result.json"
  --scope native-current --expected-release 7.0.0-38-kdrebuild11
  --boot-id "$boot_id" --kernel-elf "$kernel_output/vmlinux" --gs-proof "$gs_proof"
  --builtin-source-start "$its_return_start")
for nano_family in mutex rwsem; do
  for nano_backend in native kdlock; do
    python3 -B "$nano_source/bench/nano/run.py" "${nano_common[@]}" \
      --family "$nano_family" --backend "$nano_backend" --stage functional \
      --output "$experiment_root/functional-$nano_family-$nano_backend" || exit "$?"
  done
done
```

After all four functional runs and ordinary unload pass, supply all four exact
receipts to every timing invocation:

```bash
nano_prerequisites=()
for nano_family in mutex rwsem; do
  for nano_backend in native kdlock; do
    nano_prerequisites+=(--prerequisite "$experiment_root/functional-$nano_family-$nano_backend/result.json")
  done
done
for nano_family in mutex rwsem; do
  for nano_backend in native kdlock; do
    python3 -B "$nano_source/bench/nano/run.py" "${nano_common[@]}" "${nano_prerequisites[@]}" \
      --family "$nano_family" --backend "$nano_backend" --stage timing \
      --output "$experiment_root/timing-$nano_family-$nano_backend" || exit "$?"
  done
done
```

Keep every sample, rejection, failure and unrun stage. Compare Native primarily
with KD-off on this same boot; show the previous recorder-on result separately
with its own identity. Report whole-workload and selected peak results
separately. Sequential blocks and unqualified host timing remain exploratory;
these results cannot establish pure lock latency, physical batch length or
returned JIT-body counts during recorder-off timing.
