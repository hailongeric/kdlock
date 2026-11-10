# Candidate kernel 2 installation and boot, 2026-11-11

Status: **stage/check/install/one-shot arm completed; candidate boot identity
verified.** The normal `7.0.0-38-kdlock1` default, recovery kernel, installed
candidate 1 and all other protected installed files remain preserved. This
record establishes installation and boot identity, not JIT body execution or
whole-lane correctness. The subsequent live compilation failure is retained in
[its separate record](../runtime-compilation-20261111/README.md).

The candidate is `7.0.0-38-kdrebuild2`, with kernel source overlay
`81feb2d749ebbca468c0ab2eb895dcdd82fe519e`. The
[build record](../kernel-build2-20261111/README.md) preserves the actual build,
source/configuration identity and warnings. The cold bulk-allocation correction
uses virtual-capable allocation without reducing the explicit capacities; it
does not erase [candidate 1's initialization failure](../runtime-initialization-20261111/README.md).
The source/output base remains
`/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f`.

## Fresh installation namespace and helpers

All four phases used fresh stage and receipt paths ending in
`install-stage-kdrebuild2-81feb2d7-v1` and
`receipts/install-kdrebuild2-81feb2d7-v1`. No candidate 1 stage or failed helper
receipt was overwritten or resumed. The exact
[controller](phases/controller.py.txt) is SHA256
`b19d15dc1b9120e21159dc75f3f26b6ac3eee73b760ac9e6fa6a2bfc1e1f4cd0`;
the [checks helper](phases/checks.py.txt) is SHA256
`b55bc7fe5c137d1e5e74da0bfefede4e240b383145e0e6b1d562bee0503dc02d`.
The [prepared recipe](prepared-install-recipe.md) describes the reviewed phases;
actual command results and journals below establish execution. The controller
reports a VM hash/AST check before dispatch; no separate raw outer parser receipt
is invented here. Each successfully executed copied helper was parsed by its
actual interpreter as part of the recorded phase commands.

[Configuration](phases/configuration.json) binds the successful final build
receipt and the actual [recovery HMP readback](recovery-hmp.json), SHA256
`8abfedd3e321af4d9c133b987fcbcc9748b9ae554460e5cea62d40837800d051`.
The HMP data records the shared recovery snapshot; this is not a new restore
experiment. Stage ran under the root controller; this collector was explicitly
authorized to execute the reviewed check/install/arm phases. The collector did
not reboot, load a module or run a source/JIT body.

## Actual stage, check and installation

All times below are UTC on 2026-11-10 (local date November 11). The exact raw Unix
times remain in the completion JSON; they are not pooled with candidate 1.

| Phase | Completion UTC | Result |
| --- | --- | --- |
| [Stage](phases/stage-complete.json) | 17:02:27.071857 | COMPLETE |
| [Check](phases/check-complete.json) | 17:05:58.049242 | COMPLETE |
| [Install](phases/install-complete.json) | 17:10:08.281979 | COMPLETE |
| [Arm](phases/arm-complete.json) | 17:14:17.621546 | COMPLETE |

[Modules installation](phases/stage-modules-install-result.json) returned 0 in
158.09024332399986 seconds without timeout. Its complete
[log](phases/stage-modules-install.log.gz) is retained losslessly. The command
uses source/output separation, explicit candidate release, fresh INSTALL_MOD_PATH
and normal INSTALL_MOD_STRIP=1. The configuration enables ZSTD support with
COMPRESS_ALL off, so the staged payloads are uncompressed `.ko` files.

[Staged](phases/check-modules-stage.json.gz) and
[installed](phases/install-modules-installed.json.gz) inventories contain the
same **6,901** modules, matching modules.order, candidate vermagic and absence of
DWARF debug sections. The actual controller compared relative names, sizes,
SHA256 and modes. Each inventory records **6,827 signed and 74 unsigned** modules,
preserving the vendor signing exclusions. Unsigned status alone was not a new
rejection gate; MODULE_SIG_FORCE is not enabled. Every check/install child result
returned 0 without timeout.

[The budget](phases/root-budget-before-install.json) reserved 1 GiB on root and
256 MiB for initrd, with 2,061,728,244 bytes required and 2,814,226,432 available
before installation. These are install budgets, not runtime pool/stack proofs.
The install used only fresh candidate 2 module/boot names. Actual depmod,
update-initramfs and update-grub returned 0. The
[installed files](phases/installed-boot.json) are:

| File | Bytes | SHA256 |
| --- | ---: | --- |
| vmlinuz-7.0.0-38-kdrebuild2 | 17,183,232 | a5fc091793ac0b4dbe9ccb59a390743967d89aa61192eb29e497ac066f356439 |
| System.map-7.0.0-38-kdrebuild2 | 10,564,272 | 47cc1e87e95f2e118f9a20ff01ec8e31dee1f9d0f650ef9649392a25db98395f |
| config-7.0.0-38-kdrebuild2 | 308,548 | 31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483 |
| initrd.img-7.0.0-38-kdrebuild2 | 103,185,042 | fc61d1e8578632686049e56f773801cbc2b741549002a34466d2880d6eb19e17 |

The four local-root dependency queries (`virtio_pci`, `virtio_scsi`, `sd_mod`,
`ext4`) and installed-network query (`virtio_net`) all returned actual `builtin`
results in this configuration. Their loadable dependency arrays are empty, so
no corresponding module file is required in the initrd. The initrd listing and
all actual dependency logs/results are retained.

[Install protection](phases/install-protected-after.json) and
[pre-arm protection](phases/arm-protected-before-arm.json) each report
**88,839 files unchanged**, including installed candidate 1, normal, legacy and
other installed payloads/boot/default files. The comparison covers path
membership, bytes/sizes/modes and symlink targets, not unrecorded inode/time
fields. The original 20,414,736-byte protected map remains on the guest under
SHA256 `1fdbfa459486aa019b284698596183d002e143ed5ea914334b4c68dbf1604b8b`.
[The guest index](guest-index.json) retains its path, record count, 8,913,861,597
recorded regular-file bytes and all 22 module roots rather than duplicating the
map or old module binaries. Final arm disk usage records root available
1,985,495,040 bytes and builds2 available 11,494,305,792 bytes.

## One-shot arm and actual boot

All arm child commands returned 0 without timeout. Before/after GRUB receipts
show only `next_entry` changed to the candidate 2 advanced-menu entry. The normal
kdlock1 default, other environment fields and configuration SHA256
`8d4c66b404bdf56ea6a94569882a495bd9d5ed23a4d38e98d11950c0d0c54089`
remained unchanged. The helper synced the result and performed no reboot.

The root controller then rebooted the guest. The actual
[reconnect trace](reconnect.json) records return 0 at 17:17:11.229299 UTC observing
`7.0.0-38-kdrebuild2`, boot `dea66234-7f70-4e5b-acb6-40a6f2884919` and taint 0.
The prior stage/idle observations belong to normal kernel boot
`5dde9006-ad3c-44eb-81ed-213cd003f31c`.

The persistent [postboot helper](prepared-postboot-helper.py.txt), SHA256
`91d0358d4017e834f489f01a2eb9a14d3ca66e7c6d45ecfb20537b64a0713a3a`,
produced [POSTBOOT_IDENTITY_VERIFIED](postboot/result.json). The root controller
reports actual helper return 0 and VM hash/AST verification; the
[explicit report](controller-reported-postboot.json) labels that outer transcript
boundary. Success requires both that return 0 and the saved success phase.
The retained binary kernel notes match actual vmlinux BuildID
`fd2262c047e130787ef669419111eba6eb9ebb2c` and ELF SHA256
`7de39e303412b36ea7dd36f7260183669bc4d2829569dd1e3ac9bc2426e91809`.
The exact config/bzImage/System.map and installed file pins also match.

The saved pre-fixture proof observed taint 0 and no KD fixture module, retained
the existing `nokaslr`/mitigation options and verified exact full linked GS
symbols: current_task == const_current_task == `0xffffffff8440f018`, per-CPU
start/section `0xffffffff843f7000`. Public flags on all 64 CPU rows omit
call_depth; the runtime's actual feature guard remains authoritative. These
observations do not validate all handwritten/generated return mitigations or
fixture GS lowering. Postboot GRUB confirms the exact armed configuration,
consumed one-shot entry and preserved normal default.

## Evidence limits

[Copy indexes](copied-files.json), [postboot copies](postboot-copied-files.json)
and [source-host copies](sourcehost-copy-index.json) bind exact raw and retained
bytes. Large logs/tables are compressed losslessly with raw and compressed
hashes; `.txt` on copied helpers changes only their evidence names. No installed
module/kernel binary is duplicated here. The postboot observation predates live
fixture loading; it is not a claim that the later live attempt remained taint 0.

Candidate build/install/boot success does not establish actual JIT publication,
returned JIT body completion, full acceptance T01-T56 or performance. The build's
retained warnings, candidate 1 failure and later live2 compilation failure remain
separate, preserved evidence.
