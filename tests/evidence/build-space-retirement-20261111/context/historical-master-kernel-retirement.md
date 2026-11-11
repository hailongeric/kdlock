# Linux 6.1 retirement and next kernel target

On October 27, 2026, the user retired development on the Linux 6.1 kernel and
selected **Ubuntu 26.04 / Linux 7.0** for future adaptation. This is a target,
not a compatibility claim. This cleanup does not install, build or boot the new
platform, and none of the retained Linux 6.1 results establishes Linux 7.0
correctness or performance.

The final measured project checkpoint is `9de8660a9f82331e2690e871b56ba6388f74507c`,
preserved at `archive/linux-6.1-final-20261027`. The source measured by the final
catalog is `a9aeb280a68242818aa469d8277e0c5a22fffee1`. The
[full catalog](../../bench/results/10.176.26.71/bench/catalog-fixedfreq-20261027/README.md)
retains 3,830 valid observations and 139 drained preparation failures, including
the MM regression and failed strict timing qualification. Retirement changes no
historical outcome or numerical evidence.

## Retention policy

Keep one complete **project kernel** as a legacy recovery reference:

| Item | Retained identity or location |
| --- | --- |
| Release | `6.1.159-kdclobber2` |
| GNU Build ID | `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960` |
| Source/build tree | Guest `/mnt/kdlock-builds/linux-6.1.159-kdclobber2` |
| Source entry | Guest `/root/linux-6.1.159-kdclobber2`, linked to that tree |
| Captured bundle | Guest `/root/kdlock-kernel-baselines/mutex-clobber2-20260919` |
| Installed inputs | Matching `/boot` files and `/lib/modules/6.1.159-kdclobber2` |

The distro-managed Ubuntu 22.04 kernel packages are operating-system inputs,
outside this project's kernel-archive deletion scope. The retained legacy VM is
not the future Ubuntu 26.04 environment.

Preserve all benchmark/test reports and raw evidence under `bench/results/`,
including frozen source, images and failed runs needed to audit those results.
An image embedded in a result archive is evidence, not an additional maintained
kernel installation. Keep Git archive refs for rejected experiments and user
work. Do not infer permission to delete unrelated WIP from the retirement date.

The small tracked `kernel_baseline/` configurations, patches, manifests and
verifier remain required provenance and test fixtures. The retained external
bundle includes its ancestor/parent manifests and patches. Deleting separate
ancestor build trees does not remove that verification chain.

## Cleanup records

The [source-host receipt](../../bench/results/380G10/tests/kernel-retirement-20261027/README.md)
records removal of 24 clean historical worktrees after preserving and verifying
their exact HEADs under archive refs. It records about 3.000 GiB more available
space and explicitly retains the other 23 worktrees containing WIP or raw
evidence. The pre-existing local edit to the October 22 cleanup report remains
outside this commit.

The [completed VM cleanup](../../bench/results/10.176.26.71/tests/kernel-retirement-20261027/README.md)
removed 219 exact roots covering 980,109 frozen filesystem records: four ancestor
build trees, the MM experiment work root, 36 superseded bundles, 35 old project
module versions and 143 boot files. It separately backed up and removed 32
obsolete GRUB menu files. One complete `6.1.159-kdclobber2` version
remains, with its Build ID, boot ID, 73 loaded modules and zero taint unchanged.
The guest is idle and has no pending one-shot boot. All 64 host policies remain
at the requested 2.0 GHz with turbo disabled.

The initial apply stopped after 106 roots when removing known hardlink aliases
changed two remaining System.map link counts from two to one. The recorded
inventory/journal proof derived the exact new counts; resume revalidated all 113
remaining files before deleting them. Its later boot postcondition then stopped
on manually configured obsolete menu entries. Finalization removed only the 32
backed-up menu files, preserved 15 other configuration files, and passed GRUB
syntax and recovery-default checks. Both exit-1 stops and the final exit-0
completion remain explicit. No ownership or link-count check was bypassed, and
the retained boot did not change.

The independent source-host audit covered all 930,368 non-directory leaves and
242,275 preservation-archive members. The retained source/metadata archive is
2,930,628,726 bytes, SHA256
`9ea2769b87e2ea20f5cf7a4d670b056e2fbb747a40ac50f2a5847f4ac6179fcc`.
It preserves changed source, metadata and unknown evidence; public-upstream
matches and explicit generated/signing-material omissions retain exact records.
The report distinguishes copied-byte verification from guest-only observations
of deliberately omitted bytes. Opaque historical archives remain private raw
evidence. Missing members in the already incomplete historical MM tree remain
documented; this is not a bit-for-bit recovery promise for every retired image.

At this retirement checkpoint, the new `legacy-kdclobber2-20261027` recovery
snapshot was verified and all 43 existing snapshots remained: **44 snapshots
total**. Automatic approval review rejected
the proposed irreversible purge before execution because the kernel-archive
cleanup request did not explicitly authorize deleting VM recovery snapshots.
No snapshot was deleted in this operation. The linked report supplied the exact
43-name proposal for explicit approval, so snapshot purging was pending at this
checkpoint. The user subsequently approved those removals; the
[later storage and migration record](vm-ubuntu2604-migration-20261027.md)
records their completion and the sole retained `legacy-kdclobber2-20261027`
snapshot. This follow-up does not change the earlier rejection or observations.

Intermediate preservation archives were pruned only after the final source-host
copy was verified; metadata and results remain. Distro-managed Linux 5.15 packages
were excluded.

Old command paths in historical reports continue to identify their original
inputs; they do not promise those retired build copies remain installed.
Reproduction of a retired variant requires its captured source/configuration
evidence and a separately validated environment.

## Next adaptation

Use the [project roadmap](../ROADMAP.md) for the three development stages. The
platform transition does not close the existing semantic or performance gates.
Before new live work, record the exact Ubuntu image, Linux source/package
revision, configuration, toolchain, topology and recovery mechanism. Port and
validate the required lock APIs, caller register contracts, hooks, source
lifetime and JIT admission against that kernel. Preserve native MM bodies and
their original-task execution boundary.

Existing [VM commands](../operations/VM.md) describe the retained legacy
environment. New-platform measurements need new kernel/source identities and
matched Native/TCLock/KD controls; do not pool them with these Linux 6.1 results.
