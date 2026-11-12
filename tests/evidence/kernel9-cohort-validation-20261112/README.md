# Kernel9 cohort regression, 2026-11-12

Corrected core `6e486ecec398111fb5d5e30ffc76495f32f557b7` was installed and
booted as `7.0.0-38-kdrebuild9`. The existing four-worker rwsem fixture passed
on that kernel with 7,257 observation records, zero overflow, protected JIT
completion, an unchanged warm feedback baseline and ordinary shutdown/unload.
This is an affected general regression, not a forced reproduction of the
publication-to-await queue race or a new mmap result. The prior kernel8 failure
and the earlier platform review stop keep their original verdicts.

The user explicitly authorized resuming the kernel9 checks. Each resumed
installation, reboot, build and runtime action used the ordinary execution and
approval path; the actual commands were permitted. No assertion about future
platform approval follows from those decisions.

## Identity and scope

| Item | Recorded value |
| --- | --- |
| Kernel Build ID | `8198ffae09db584dce9b71d92b5743a4146ba80a` |
| Boot UUID | `ff9d44b5-bcfc-4ec0-ad0c-2e8798bc8f0c` |
| vmlinux SHA256 | `0fe0fe930e391bb263fdcfa4ba9940eee225280a668021cb11a269a691cb8c15` |
| Kernel configuration SHA256 | `31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483` |
| Signed rwsem fixture SHA256 | `95f82fd9019f66df0b7ee51cc75d42263ff4d4d30f48b89bbd98698381d19a78` |
| Fixture source | Exact earlier 143-file source, raw tar SHA256 `86c84337a6f4391a299eed49bbd64f92d1dc2dd63ce94b5b989b6dc71af66e13` |
| Runtime result SHA256 | `4f8e0c1d3c8b0098671dfcb3bb27b22343946fa9f51fba243056cbd5e782f5ed` |
| Raw full-regression archive SHA256 | `3ca9027e6fddc67c37aa8b748a91e2bcfd25e5509b8e893712ec43b5c2ed54ed` |

The successful full kernel build was reused. Source/core, protected old output,
installed old boot files and the persistent normal-kernel default were checked.
The one-shot kernel9 entry was consumed. Postboot checks bound the live Build ID,
GS current-task offset, return thunk, installed files and signed NLS module to
the exact built ELF/configuration. The normal `7.0.0-38-kdlock1` remains the
persistent boot default.

The fixture completed 16 compiler cycles, 13 publications and 13 coverage-ACKed
keys. Four remaining exact facts were archived and SETTLED at shutdown,
separately from coverage ACK. The accepted generated result is a complete
protected episode; the enclosing C-function epilogue remains native. Selected
native reader overlap/exclusion, nested/shared-read continuation and retained
writer downgrade cases are recorded by the unchanged existing runner. No
whole-kernel context, instruction, lifetime or progress claim is made.

The final supervisor recorded no new kernel faults, only the NLS module loaded,
no remaining fixture devices, empty busy/D-state lists and taint 4096 from the
signed out-of-tree fixture. The fixture was ordinarily unloaded after exact
runtime/source retirement. Two module-build warnings remain recorded: a missing
previous prototype for `fixture_rw_native_checkpoint` and a 4,352-byte frame.
The prior full-kernel warnings remain in the separate build receipt.

## Retained nonpassing steps

The staged verification and installation helpers each completed all twelve
underlying commands with zero status, then failed their single-sample final
idle observation on an unrelated display worker in a vblank wait. Their
original failures remain intact. Separate completion receipts rechecked exact
files, preserved state and ten seconds of sustained idle. Installation was not
repeated to obtain the later completion receipt.

The first private-fixture staging adapter compared a file digest to the entire
`{bytes, sha256}` manifest record and stopped before staging a source member or
building/loading the module. Its partial directory and failure are retained.
The corrected adapter checked both length and digest in a fresh directory.
These steps are not rewritten as first-attempt passes.

## Archive

[receipts.tar.gz](receipts.tar.gz) preserves all 344 collected control/evidence
files, including the original failures, exact helper sources and arguments,
install/boot receipts, signed-module build logs, runtime observations and the
nested full runtime archive. Its SHA256 is
`eaf6f7c26d02c09d683694278f265a58ff21129234b7e53d9a26b01e2e51a30d`.
[files.json](files.json) lists every member's length and digest. The nested
`private-full/runtime.tar.gz` contains 660 files (53,846,583 uncompressed bytes),
including raw wire exchanges, compiler artifacts, final observation bytes and
the shutdown archive. The top-level copies provide convenient access to
[postboot identity](postboot.json), [module build](module-build.json),
[regression supervision](regression-supervisor.json) and
[the runner result](regression.json).

Guest build/input/output roots remain under
`/mnt/kdlock-builds2/kdlock-main-kernel9-6e486ece-01`; the successful fixture uses
`private-rwsem-regression-02`. Recovery snapshots
`kdlock-builddisk-clean-20261031` and `kd-mm-step-failed-20261111-01` were verified
on all three active QEMU disks before live work. This receipt contains no nano
throughput measurement.
