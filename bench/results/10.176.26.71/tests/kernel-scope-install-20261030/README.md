# Scoped kernel installation: 2026-10-30

`7.0.0-38-kdscope1` was installed successfully. The final installation receipt
is `NEW_KERNEL_INSTALLED_NOT_ARMED`: it establishes installed artifact
correspondence, not a boot, actual-syscall/MM execution or performance result.
The two earlier failed attempts remain failed and are retained separately.

The compiled kernel recipe is
`8446f4ecb08816380a4c233197a8ce5e4d333aac`. The later comparison provider is
`f7a84065e84474380faa37eeadfdf534abd72a68`; the kernel was not rebuilt or
relabeled as f7. The [generation record](receipts/generation-f7.json) binds
those distinct inputs. The user authorized completing comparisons while
keeping f7 unaccepted; this installation does not change that status.

All four attempts ran in the VM on the existing `7.0.0-38-kdlock1` boot
`677b7afa-5358-4ece-a650-5f4a4adecd55`. Host work was source preparation,
static review and offline evidence analysis. The full build and historical
preinstall evidence are linked through [fullbuild.json](receipts/fullbuild.json)
and [preinstall.json](receipts/preinstall.json).

| Attempt | Recorded outcome | Receipt SHA256 |
| --- | --- | --- |
| [Stage r2](receipts/stage-r2.json) | FAILED after successful `modules_install` | `b55eee6dad571da7d1f5a55a74f04b7ed8c1c34f755aa8e3a8bb60174885046f` |
| [Stage r3](receipts/stage-r3.json) | DATA_MODULE_STAGE_VERIFIED_NOT_INSTALLED | `7d34d4860abad6cee800a383651f4fe8f7695ca295ebad528e1207c17b57ece4` |
| [Install r2](receipts/install-r2.json) | FAILED after successful copy and `depmod` | `343b64688df8f055104c4262a28add64bc79800d515b04ce4e48ee984bb07293` |
| [Install r3](receipts/install-r3.json) | NEW_KERNEL_INSTALLED_NOT_ARMED | `74110b25f9909843bad1b248864612ea791c7952b6698e774349e2ef21bfa0cf` |

Stage r2 rejected the first stripped `amd-uncore.ko` because its standalone
symbol inventory retained unused section-symbol placeholders. Offline
comparison found identical properties/bytes for all 25 allocated sections and
identical 1,041 normalized loader relocations. Exactly 18 unnamed local
`STT_SECTION` symbols disappeared; all had zero value/size and no retained
relocation reference. The [exact diagnostic](diagnostics/stage-elf.json) and
[explanation](diagnostics/stage-elf.md) preserve the pair's hashes and records.

Stage r3 omitted only that canonical unreferenced symbol class. It reused the
completed stage without rerunning `modules_install`, checked all 6,901 module
identities and release strings, and checked the complete source/build, staged
tree and protected live paths before/after. Referenced and noncanonical symbols,
allocated bytes and normalized relocations remained checked. Its successful
receipt did not replace the failed r2 receipt.

Install r2 copied the verified release and ran `depmod` successfully, with both
children drained. It then rejected 187 raw-inventory differences. All 187
concerned only `allocated_bytes` (`st_blocks * 512`); no bytes, sizes, modes,
paths or link targets differed. The existing content-identity comparison had
passed, but the following raw-row comparison misclassified allocation accounting
changes. The diagnostic does not establish the filesystem mechanism responsible.

Install r3 retained that failure, reused the completed copy and `depmod`, and
required the existing module tree to match both the retained pre-depmod
inventory and verified stage in every content/size/mode/path/link field.
Allocation remained a storage observation and budget input. The
[allocation observations](diagnostics/allocation-observations.json) retain all
187 differences; [semantic changes](diagnostics/depmod-index-changes.json) are
empty. The continuation copied the three new boot files, generated and
inspected the initramfs, and verified the unchanged source/build/stage and old
kernel/module/boot/GRUB/default/boot-link contents. It did not repeat the module
copy or `depmod`.

The final initramfs is 103,182,918 bytes, SHA256
`e21e0ad9f9cbd784abd35bfca747bf77ae60fc237b8cd47d0dd466c9b07bcf43`.
All 1,188 module copies, representing 1,188 unique modules, match the verified
installed bytes. The [module manifest](manifests/initramfs-modules.json) and
[boot manifest](manifests/installed-boot.json) retain those identities. The
three fresh initramfs commands returned zero with no remaining descendants.
Root free space at completion was 3,673,931,776 bytes, above the 2 GiB reserve.

This record ends at installation completion. Its receipt explicitly leaves
GRUB modification, boot-link modification, boot arming, reboot, module loading,
current-provider validation, live-kernel validation and performance acceptance
false. Subsequent boot and syscall/MM comparisons require their own evidence.
No timing point was run or repeated by these installation controllers.

Reviewed controller bytes are retained under [controllers](controllers/).
The [stage reuse plan](plans/stage-r3.md) and [install continuation plan](plans/install-r3.md)
describe the bounded corrections. [copy-manifest.json](copy-manifest.json)
records the exact source path, destination, size and SHA256 for each selected
copy. Original `/tmp` evidence remains intact. Full fetched evidence, including
large inventories, journals and logs, is retained in the main checkout's ignored
`bench/results/10.176.26.71/raw/tests/kernel-scope-install-20261030/` directory;
its complete file inventory is [raw-manifest.json](raw-manifest.json).
