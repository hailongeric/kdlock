# Continue the verified module installation without repeating completed work

The r2 installation receipt remains FAILED at
`343b64688df8f055104c4262a28add64bc79800d515b04ce4e48ee984bb07293`.
Its copy and `depmod -a 7.0.0-38-kdscope1` children both returned zero and
drained. It created the new module release but no boot files or initramfs.

The fetched diagnostic SHA is
`8b7c99d1a1a3e72b39c6912720e7944b4553bb7cdcb6d5e0fdb44f371ac179c3`.
All 187 inventory differences concern only `allocated_bytes` (`st_blocks *
512`); no file bytes, length, mode, paths or symlink targets changed. The
existing `byte_identity` check passed, but the next raw-inventory comparison
mistook filesystem allocation accounting changes for unexpected file changes.
The allocation mechanism is not established by that diagnostic.

Create a new install-r3 controller and fresh r3 evidence/work directories.
Retain the old r2 controller, failed result, command logs and inventories. Bind
the exact failure and successful copy/depmod operations. Require the current
6,901-module tree to match both the verified stage and the retained pre-depmod
inventory under `byte_identity`, preserving every content hash, size, mode,
path, directory mode and literal link target. Compute semantic differences
with that same projection. Keep raw allocation differences as observations;
use allocation only for storage budgeting, never artifact identity.

Recheck the complete source/build/stage inputs and original protected baseline.
The latter is the r2 pre-install inventory, with only this release's already
created module subtree excluded from the current comparison. All new boot
leaves must still be absent. Do not copy modules or run depmod again. Admit
space for only the remaining boot files, initramfs and existing reserves.
Continue the existing boot-file copy, initramfs creation/inspection, exact
module-copy verification and final unchanged-input/protected-path checks.

The successful schema-2 receipt remains compatible with boot-r4 and records
`NEW_KERNEL_INSTALLED_NOT_ARMED`. Add explicit reused-module/copy/depmod fields
and retain the prior FAILED receipt. No GRUB changes, boot-link changes,
loading, reboot, current-provider validation or performance acceptance occurs.
Timeouts retain children and partial evidence without automatic retry or kill.

Development here is source preparation and static AST inspection on 380G10.
Only the parent may execute the reviewed controller in the idle VM.

Controller: `/tmp/kdlock-scope-install-only-r3-20261030.py`, SHA256
`22b2fd3781a435510b580ef2478068327d4260b7d86de628c8ff712542e56cde`.
After the parent transfers that exact file, the future VM invocation is:

```sh
python3 /tmp/kdlock-scope-install-only-r3-20261030.py \
  --boot-id 677b7afa-5358-4ece-a650-5f4a4adecd55 \
  --prior-install-result /mnt/kdlock-builds/kdlock-evidence/10.176.26.71/tests/kernel-scope-install-r2-20261030/result.json \
  --prior-install-result-sha256 343b64688df8f055104c4262a28add64bc79800d515b04ce4e48ee984bb07293 \
  --stage-result /mnt/kdlock-builds/kdlock-evidence/10.176.26.71/tests/kernel-scope-module-stage-r3-20261030/result.json \
  --stage-result-sha256 7d34d4860abad6cee800a383651f4fe8f7695ca295ebad528e1207c17b57ece4 \
  --stage-controller /tmp/kdlock-scope-stage-modules-r3-20261030.py \
  --stage-controller-sha256 023a69e7ab63224fad238fd0b5b0254008ad4cd2872039595b5fc7fe972a185a \
  --idle-confirmed
```

The expected new result is under
`/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/tests/kernel-scope-install-r3-20261030/result.json`.
Its actual successful result SHA must be used later; it is not known in advance.
