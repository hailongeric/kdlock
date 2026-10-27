# Linux 7 enabled-MM kernel checkpoint

`7.0.0-38-kdmm1` built, installed and booted cleanly in Native-control and
KD-local modes. Fresh API, mapping, fault and completed-fault prerequisites
passed in both modes, followed by **42 shared-MM timing points with normal
drain**. Combined with the separate 84 private-MM points, all **126 selected MM
points** are complete. The [shared comparison](../../bench/catalog-linux70-mm-shared-20261028/shared-mm/README.md)
uses the same image, configuration, source and prepared binaries; Native was
faster at all 21 worker counts in this exploratory single-round measurement.

The original KD mapping failure, its later normal cleanup and the separately
frozen [mapping diagnostic](../linux70-kdmm1-mapping-diagnostic-20261027/README.md)
remain distinct outcomes. [evidence.json](evidence.json) binds the raw results
and offline audits; [raw evidence](../../raw/tests/linux70-kdmm1-20261027/)
retains the build, installation, boot and recovery records.

## Build and installation

The build uses authenticated Ubuntu `linux=7.0.0-38.38`, upstream 7.0.14 and
unchanged version code `458766`. Its GNU Build ID is
`ac9ea2ec7f24be8b910547bdfdbfb071176677e6`. The fresh configuration changes only
`CONFIG_KDLOCK_MMAP=y` and its version signature from the captured normal
development configuration. Rust, BTF, frame pointers and certificate settings
remain enabled as captured. Source/configuration checks, ten affected-object
checks and the deferred-read ownership fixture passed before the full build.
The full build produced 6,901 modules and retains eleven compiler/modpost
warnings. Native MM bodies and algorithms remain unchanged.

Installation verified signature metadata for all 6,827 policy-selected modules;
74 Ubuntu staging-policy exclusions remain unsigned. Four module signatures
also passed independent CMS verification. All 1,188 module copies extracted
from the new initramfs match the verified installed bytes. The signing key's
private contents were not archived. Existing `kdlock1`, stock Linux 7, legacy
recovery images and the normal GRUB default remained unchanged.

The original installer **failed** its final broad filename check because
`usr/lib/modprobe.d/blacklist_linux_7.0.0-38-generic.conf` contains the old release
name. Its failed receipt remains immutable. A separate validation-only
continuation checked actual `lib/modules/<release>` components and module
bytes, repeated signature/frozen-input/protected-file checks, and passed with
receipt SHA256
`2167c0726da627700c4c9fc294e7fcdf7c6047693e4d5e4dca64cbc375d7f6d4`.
It did not reinstall modules, regenerate the initramfs or replace the failed
receipt. The original failure and subsequent validation are separate outcomes.

## Boot identities and recovery

| Mode | Boot ID | Observed backend | Taint before probes | Bundle manifest SHA256 |
| --- | --- | --- | ---: | --- |
| Native | `a84cb9f5-bbab-457e-83ca-dcfc3bffed09` | `NATIVE_CONTROL` | 0 | `7e1032c4b89618882bbadc128084e36c35e1ef9a4627608668b8404e71fc6649` |
| KD | `55696c5f-b3bb-46cd-8676-60877a4a79f1` | `KD_LOCAL` | 0 | `39aa98e8a62d2e150064f8c6d5bfb5ae61e16b4a207b9efec80a0b9c263c6a7f` |

Both boots passed schema-2 running verification, exact command-line/backend
checks and clean health checks. Both use lazy preemption, `nokaslr`, `nopvspin`
and the same build, source, installed files and configuration. Only the boot
mode selects `kd_mmap=off` or `kd_mmap=on`; no rebuild separates them. Each
capture preserves 61 files, including 23 bundle files, whose hashes were
rechecked on the source host. One-shot selection was consumed on each boot;
`7.0.0-38-kdlock1` remains the normal default. After both timing grids, the
[return verification](../../raw/tests/linux70-kdmm1-20261027/cycle-control/verify-normal/phase-evidence/result.json)
passed on boot `15dc5977-59d3-4471-a196-d71f03f450ed`, with taint 0 before
subsequent project probes and the one-shot entry consumed.

The clean Native snapshot is `linux70-kdmm1-native-clean-20261027`. HMP `savevm`
returned to its prompt after **41.64 seconds**, and `info snapshots` listed the
tag on all disks with 23.6 GiB of VM state at **2026-10-28 00:01:50**. The tag
retains the campaign date despite the later creation date. Its pre-save health
receipt confirms the clean Native boot, idle state and taint 0. This records
creation and actual listing; it does not claim a restore drill. The normal
`linux70-kdlock1-clean-20261027` and legacy recovery snapshots remain separate.

## Current validation boundary

The final shared-only generation used 527 frozen source files. Native2 boot
`1672c452-0346-4703-8215-ddb1cec50915` completed all four correctness prerequisites
and preparation. KD2 boot `f5a6f61b-b1a0-47ed-a2a2-ff73b79a13ac` completed fresh
correctness, reused the Native2 prepared binaries, and measured its 21 points.
Native3 boot `ddec066b-7a80-4a75-8376-897365e8b848` then completed fresh correctness
before measuring its 21 points with those same binaries. All phases drained
normally; their mode-specific bundles and exact boot identities remain separate.

| Prerequisite | Native | KD |
| --- | --- | --- |
| Actual-mm API and lifetime | PASS; 137 checks, zero errors | PASS; 161 checks, zero errors |
| Shared mapping and lifetime | PASS; six cases and nine negative witness checks | PASS; six cases and nine negative witness checks |
| Fault interactions | PASS; eighteen cases; sixteen children and sixteen fault threads joined | PASS; eighteen cases; sixteen children and sixteen fault threads joined |
| Completed-fault handling | PASS; 64 entries, completions and returns; zero errors/misses | PASS; 64 entries, completions and returns; zero errors/misses |
| Plain preparation | PASS; one and sixteen workers, eleven negative mutations | PASS; one and sixteen workers, eleven negative mutations; exact Native binaries reused |
| Shared timing | COMPLETE; 21 unique points, one round each | COMPLETE; 21 unique points, one round each |

The four same-boot prerequisites were rechecked before each timing grid. The
[Native3 correctness audit](../../raw/tests/linux70-kdmm1-20261027/native3-correctness-offline-audit.json),
[KD measurement audit](../../raw/tests/linux70-kdmm1-20261027/kd2-measurement-offline-audit.json)
and [Native measurement audit](../../raw/tests/linux70-kdmm1-20261027/native3-measurement-offline-audit.json)
verify the preserved source, binary, kernel-bundle, raw accounting, host endpoint
and normal-drain records. Native completed 11,171,072 cycles and KD completed
3,181,920; each grid joined 504 workers across its 21 points. These aggregate
counts are audit totals, not a pooled throughput comparison.

The [matched comparison audit](../../raw/tests/linux70-kdmm1-20261027/shared-matched-comparison-offline-audit.json)
verified all 42 published rows with no duplicate coordinate. Whole-run Mops/s
use completed mmap/munmap cycles divided by actual wall time:

| Workers | Native Mops/s | KD Mops/s |
| ---: | ---: | ---: |
| 1 | 0.373048 | 0.365013 |
| 8 | 0.312908 | 0.061433 |
| 16 | 0.295099 | 0.044061 |
| 32 | 0.269637 | 0.025969 |
| 60 | 0.154433 | 0.006731 |

Native was higher at 21/21 matched points. This establishes neither a cause nor
a universal ordering: each point has one two-second round, with no variance
estimate. Strict timing qualification remains false. Both phases retained 55
APERF/MPERF samples, all 64 host policies fixed at 2GHz with turbo disabled,
unchanged permanent CPU pins and no thermal-counter increase. Auxiliary QEMU
workers are confined to CPU63. Configured frequency does not mean every
observed effective-frequency sample is exactly 2GHz. KD's peak window is
unavailable at 40, 44, 48, 52, 56 and 60 workers because no sampled full-cohort
window had positive progress from every worker; whole-run rates remain valid.
Native MM bodies execute on the original task without body delegation. Live
BPF/IRQ/NMI coverage and broader kernel replacement remain unvalidated.

## Earlier mapping failure and separate diagnostic

On KD boot `55696c5f-b3bb-46cd-8676-60877a4a79f1`, the 16-worker mapping
control completed 80,000 cycles and joined all workers with zero worker errors,
but its `contention_ok` predicate failed and the client exited 1. The runner's
original result remains `FAILED`, `passed=false`, `drained=false`. The controller
then tried to JSON-decode empty after-health output, masking that exit with a
secondary `JSONDecodeError`; its original `STOPPED` record is also retained.
Neither completed operations nor the parser failure is a passing test.

The separate [normal-cleanup receipt](../../raw/tests/linux70-kdmm1-20261027/kd-mapping-normal-cleanup.json)
records zero files, mm references and release errors, module refcount zero,
successful normal unload without force, and an idle guest on the same boot.
It establishes the later cleanup boundary without changing either failed
receipt. Controller handling was subsequently corrected in source to retain
the primary nonzero exit and require an explicit completed same-boot idle proof;
nineteen controller regression methods subsequently passed. Four actual-C
classifier fixture methods also passed. A separate plotting test failed because
`matplotlib` was missing, and the attempted isolated plotting setup timed out
after 180 seconds. Both failures remain preserved. A later one-method
publication data check passed and drained with two separately bound source
changes; graphical rendering was explicitly untested. The earlier combined
check driver is not an all-pass result. The final shared run used a separate
source generation, campaign and fresh shared-MM prerequisites. The 84 already
completed private points remain in their original campaign.

The separately frozen diagnostic completed all six mapping/lifetime cases,
including 80,000 cycles with sixteen joined workers and zero worker errors.
It retained one exact ELF-bound writer witness after four sampled observations
failed due to changing task state, wait channels and scheduler counters. All
nine negative witness checks rejected corrupted evidence. Normal unload,
same-boot idle, source verification and host endpoints passed. These sampled
values explain the new rejected observations; the first attempt did not retain
them, and its failure remains unchanged. The
[diagnostic checkpoint](../linux70-kdmm1-mapping-diagnostic-20261027/README.md)
records the sample limits and hashes. The later
`catalog-linux70-mm-shared-20261028` generation completed fresh prerequisites,
both mode preparations and all 42 shared timing points. It does not overwrite
the original failed attempt or the separate diagnostic.

## Separate campaign scopes

The original [private-MM campaign](../../bench/catalog-linux70-mm-trusted-20261027/README.md)
contains **84 exploratory points** on `7.0.0-38-kdlock1`: 21 independent-mmap
points and 63 module-owned private-fault points. Its global MM adapter was
disabled. Its own shared grid remains unmeasured; no later result is imported
into that generation.

The new [shared-only campaign](../../bench/catalog-linux70-mm-shared-20261028/README.md)
contains **42 exploratory shared-MM points** on `7.0.0-38-kdmm1` and selects no
private points. Its [scope record](../../bench/catalog-linux70-mm-shared-20261028/SCOPE.md)
links the generations without pooling their source or kernel identities. The
126-point completion count spans these distinct suites; it is not one combined
performance series or a KD improvement claim.

## Preserved working locations

| Purpose | Guest path |
| --- | --- |
| Enabled-MM source | `/mnt/kdlock-builds/linux-7.0.0-38-kdmm1/source` |
| Build / external-module KDIR | `/mnt/kdlock-builds/linux-7.0.0-38-kdmm1/build` |
| Fresh MM preparation | `/mnt/kdlock-builds/linux70-mmap-prepared-kdmm1/prepare.json` |
| Native identity | `/root/kdlock-kernel-baselines/linux70-kdmm1-native-20261027` |
| KD identity | `/root/kdlock-kernel-baselines/linux70-kdmm1-kd-20261027` |

Keep these frozen inputs distinct from the normal `kdlock1` tree. Follow the
[identity procedure](../../../../../kernel_integration/linux70/IDENTITY.md)
and [VM operations](../../../../../docs/operations/VM.md); verify an existing
bundle rather than recapturing over it.
