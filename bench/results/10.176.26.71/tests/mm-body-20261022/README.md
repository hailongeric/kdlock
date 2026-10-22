# Actual mmap-lock body correctness stage

Run family: `mm-body-20261022`. Built kernel: `3c01e17`; probes: `0d2a471`.
Status: minimal body and affected correctness checks passed; recovery restored
and archives audited. Performance acceptance remains false. The user confirmed sole writer and test-slot
ownership before resumption. Only the original 64-vCPU VM at
`10.176.26.71:2222` is used. Performance tuning and p95 are deferred.
The [machine-readable result](correctness-result.json) separates correctness
completion from the unresolved performance work.

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

## Build attempt 2 and capture correction

Source `3c01e17`: basic programs (2), receipt guards (4), kernel image and all 73
runtime modules built successfully. Capture refused the external `arch` symlink
under the unchanged baseline containment check. Its incomplete bundle is retained
as `mmap-kdmm2-20261022-capture-failed-1`; it is not an accepted baseline.

`storage.py` replaces only this candidate's three staging symlinks with bind
mounts at the original build paths. The data remains on the same guest disk.
The verifier keeps its path-containment and byte-hash checks. These mounts are
recreated after each guest reboot; no fstab or recovery boot policy is changed.
Capture is repeated as `capture-control-3`, without rebuilding or changing any
kernel source, configuration, image or runtime module bytes.

Capture passed with Build ID `198726ed15a65c0fd91fb9afd10ba8e3c5a31c83` and manifest
SHA-256 `76603b0060bdea616a1b4a94b46f96299a98faebd2fad396a332af729f6af405`.
Recovery files and modules were verified unchanged. Live checks use newly frozen
probe sources, including a separate queued-cancellation/no-effect/retirement
case; the built kernel remains the `3c01e17` implementation.

## Native control

Installation passed with 73 signed runtime modules, distinct Native/KD one-shot
entries, and the recovery default unchanged. Probe revision `0d2a471` passed all
five receipt guards. Run `native-1`, boot
`f2e97abf-0c3a-450f-b9a7-24fc41237537`, passed two basic programs, 121 actual-mm API
checks, six untouched mmap/munmap cases, 18 separate fault/lifetime result rows,
and 64 genuine completed file-write faults. Final module set was exactly the
original 73; project modules were unloaded and no kernel fault was recorded.
The recorded fd0 boot I/O messages are retained separately from test faults.

## KD correctness

Run `kd-1`, boot `74f9b040-42ba-46b2-819f-ec501db49d88`, passed two basic programs
and all 139 ordinary actual-mm API checks. The compiled-body probe passed 55
checks and 2,576 calls with zero errors: 2,048 supported calls included **1,690
different-task completions**; all 16 refused partial ranges completed locally,
including **15 handbacks and 15 ACKs**; all **512 post-refusal calls remained
local**. Both readers were admitted together, all 16 writers published, all
workers joined, all 16 VMAs unmapped, and exact owner/queue/slot state was idle.
Sixteen retained completion records identify the actual mm, different origin
and executor tasks, exact range, behavior and successful result.

The separate fresh-mm cancellation case passed all 11 checks: one head completed,
one queued follower returned EINTR without changing its VMA, and both requests
retired. It proves safe cancellation after reader release, not bounded signal
latency while the predecessor remains blocked.

The KD boot also passed the six untouched mmap/munmap cases, 18 separate
page-fault/lifetime result rows, and 64 genuine completed file-write faults.
Final health confirmed the original 73 modules, no project module or active
worker, and no recorded kernel fault. No timing or p95 run was started.

## Recovery and preserved evidence

Run `recovery-1` returned to `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, boot
`d4980f92-14c5-4bed-9749-beac916e76d3`. All 5,686 recorded recovery module files,
recovery boot artifacts and the default entry were preserved. The installed
candidate and old `kdmm1` remain available. No run was interrupted or run in
parallel; helpers remained stopped and touched no files in this stage.

The [archive manifest](../../raw/tests/mm-body-20261022/seal-1/guest-archives-1/archives.json)
seals all ten passing result groups, both failed build/capture attempts and final
health. The [read-only audit](../../raw/tests/mm-body-20261022/audit.json) passed
**9,675 checks, zero mismatches**, covering 1,371 files, 174 directories and 558
frozen source bindings. It checked actual executor receipts, exact ACK/cancel
balances, binaries, probe Git identities, failed source bytes, complete inventory
coverage and recovery. It extracted or executed no archived code.

The first offline audit included the 17 lifetime completions in its cycle total.
That failed checker and its receipt are retained as `audit-attempt-1.*`. The
corrected audit checks cycle totals `[1000, 80000]` and separate lifetime totals
`[1, 16]` exactly; no VM acceptance check was changed.

| Artifact | SHA-256 |
| --- | --- |
| Archive manifest | `1c39e0564a6cf1c57330424bb8cf9e65732013ccd668204efb2a58079bd45d47` |
| Native archive | `a9069c925b210339c7549f39bfe96de350814bdbdf599b23aad952617748c297` |
| KD archive | `7640cd30371acc5d3b2dd22a9d9f82c6259b3475cdc115867c7619bd2f01646f` |
| Build archive | `acc6a692a10a44834674c85f92d4e75216127863a3cb2277602a0de0997035c5` |
| Metadata/recovery archive | `dae98340941caa366351e1c709fe190dd9b25932d0cba97359d155c36cdb1f11` |
| Final health | `3956f72dde6f683325a6f6ac3e2371b821c88c85732403064081a22fc9635ae0` |

Four archives total 85,383,500 compressed bytes and 110,463,807 regular-file
payload bytes. The source-host candidate ELF is retained at
`raw/tests/mm-body-20261022/kernel-elf/vmlinux`, SHA-256
`5aa170972001acfe5f0bbe8cca7d225dd78fd634fbdae172d1aae031cecc6a9b`.
The adjacent `writer-proof/` directory records exact new ELF call sites; the old
`kdmm1` manifest was not replaced. Raw paths here are relative to
`bench/results/10.176.26.71/`.

## Commands and limits

The [maintained body guide](../../../../../kernel_integration/mmap_lock/BODY.md#repeating-the-validated-checks)
contains the executed serial commands, queue pseudocode and flowchart. Final
documentation also corrects the Kconfig help text; the tested kernel remains
the captured `3c01e17` bytes and the tested probe remains `0d2a471`.

This stage validates one explicitly enabled, fixed compiled in-tree advice body
under the actual mmap lock. It does not enable general mmap creation, page-fault
or arbitrary JIT body delegation. Readers stay local and concurrent. Refused
shapes of the selected advice entry use origin handback and sticky refusal;
other MM operations retain their existing local route. General killable-lock
equivalence, bounded cancellation latency, oversubscription, RT/ww_mutex,
lockdep and whole-kernel replacement remain unvalidated. Only the 73 runtime
modules and their dependency closure were built, not all configured modules.
The seven prior performance regressions, qualified variance and p95 remain
unresolved/deferred. These correctness results establish no performance gain.
