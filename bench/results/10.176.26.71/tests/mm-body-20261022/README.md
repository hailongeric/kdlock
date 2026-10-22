# Actual mmap-lock body correctness stage

Run family: `mm-body-20261022`. Candidate source: `5652f58`.
Status: first separate `6.1.159-kdmm2` build failed; corrected build pending. No live result or
performance acceptance is claimed. The user confirmed sole writer and test-slot
ownership before resumption. Only the original 64-vCPU VM at
`10.176.26.71:2222` is used. Performance tuning and p95 are deferred.

The [implementation guide](../../../../../kernel_integration/mmap_lock/BODY.md)
defines the fixed compiled in-tree MADV_DONTDUMP/MADV_DODUMP body, concurrent local
readers, exact physical owner and origin ACK, sticky refusal, and limitations.
Untouched mmap and page fault remain separate workloads. The existing `kdmm1`
results and recovery kernel are preserved under their original identities.

`build.py`, `source-inputs.json` and `module-targets.json` specify the serial
guest-only preparation, basic checks, kernel build, 73 runtime modules and
independent kernel capture. The new candidate's heavy object directories use
the existing guest data disk; neither the recovery tree nor the prior candidate
is removed. The controller records commands and never kills on timeout. It
does not install or reboot. Recovery boot files, GRUB configuration and module
hashes are captured before building and verified afterwards.

Raw source-side preflight and synchronization records are in
`bench/results/10.176.26.71/raw/tests/mm-body-20261022/{preflight,preflight-2}`.
The resumed synchronization verified 4,107 tracked file hashes. The fresh
functional host screen permits only the already reviewed extra I/O workers on
CPU 63; the original timing admission checks remain unchanged.

Build control is copied to
`/root/kdlock-evidence/10.176.26.71/tests/mm-body-20261022/build-control-1`.
The intended new source and baseline are
`/root/kdlock-kernel-work/mm-body-20261022/candidate-1/linux` and
`/root/kdlock-kernel-baselines/mmap-kdmm2-20261022`.

Validation and artifact identifiers will be appended after each completed stage.
No rejected attempt, failure or incomplete drain may be counted as a pass.

## Build attempt 1

Source `5652f58`: both basic C programs and all four receipt-guard tests passed.
Kernel compilation exited 2 before image creation. The generated local mutex
source included the new internal header before the atomic type definitions;
the split `arch` directory also made a relative vDSO include resolve against the
data-disk directory. Neither error changes instruction admission. Full logs and
the failed source/prepare identities remain in `build-control-1` and
`candidate-1/build-1.*`. Nothing was installed or booted.

Attempt 2 adds the explicit atomic include and a complete symlink view of the
new candidate at its data-disk directory, preserving relative include paths.
Only the new experimental build is updated after its confirmed exit. The prior
prepare manifest and changed generated inputs are retained before replacement.
