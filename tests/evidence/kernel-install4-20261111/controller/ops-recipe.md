# Kernel4 isolated build and limited installation

This plan uses the existing candidate source and build output pair under
`/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f` (BASE).
Normal and legacy source, outputs, installed files and default boot selection
stay separate. The independent kernel3 witness is
`BASE/receipts/retained-kdrebuild3-1b50e373-spin-01/manifest.json`,
SHA256 `a253bc04061422153b89c6496494ac12f45b4b49c5f6cb8689f8a1810ca3ff4b`.
The actual retention returned zero and copied 14 output files, 66 package
sources, 10,346 generated archive members and 199 receipts.

## Build

The frozen core is `2d0ad60b0bc46929f3070aefa364e710c0a81115`.
The controller returned zero and both make stages returned zero under
`BASE/receipts/overlay-kdrebuild4-spin-01`. The result SHA256 is
`e00db7a5961879692c102a00e072c70ffc5fcbe1c5051a4203b256ea44a7cac1`.
The final linked identity SHA256 is
`7c79198ee04da92873339bc5d02bd9cba47ac14598f13bf56baf25ce36c69a5c`.
The authorized VM controller built 30 core objects with `-j8 V=1`, then `bzImage modules -j32`, in the
existing isolated source/output pair with `KERNELRELEASE=7.0.0-38-kdrebuild4`.
The commands share a 900-second budget and 4 GB data2 free-space floor. Preserve
both logs including warnings. The build receipt recorded actual closure on normal boot884c, taint0 and idle.
The full output supplies the fresh modversion,
generated headers, public ELF and actual GS-linked instruction identity.

Build and freeze the requested fixture against the exact candidate output
using separate `M=<frozen input> MO=<fresh module output>`. The fixture can
compile before the candidate boots. Record its actual source/module hashes,
normal flags, vermagic, Build ID, warnings and command result separately.

## Limited installation

The root filesystem had 1,273,212,928 bytes free after kernel3 retention.
A complete fourth root module installation does not preserve the 1 GiB reserve.
The candidate kernel and initramfs use the usual new /boot release paths. The
new release's module namespace contains the exact required VM closure. Keep the
normal source, all older /boot files and all older module namespaces protected.

The unchanged local root is ext4 on the VM's virtio SCSI disk and the boot
command line uses its filesystem UUID. PCI, Virtio PCI, Virtio SCSI, SCSI disk,
ext4 and Virtio net were built into kernel3. The EFI fstab entry uses vfat,
which is built in, and its default iso8859-1 NLS module is modular. The stage
rederives these dependencies from actual release4 metadata. The initramfs
keeps normal boot scripts and root UUID handling. The partial namespace does
not establish general hardware or full distribution module support.

Once the actual release4 build has returned zero and the module build window
has closed, refresh normal boot/taint0/idle/recovery/host and guest space.
Use fresh stage and receipt namespaces. The exact helper copies must pass
guest AST and SHA verification before dispatch. The install helper never
reboots or loads a module.

```
python3 /PERSISTENT/HELPERS/kdlock-kdrebuild4-install.py stage \
  --controller-idle-recovery-confirmed --final-build-success-reviewed \
  --final-build-receipt BASE/receipts/overlay-kdrebuild4-spin-01/result.json \
  --final-build-receipt-sha256 ACTUAL_RESULT_SHA \
  --recovery-receipt /ACTUAL_FRESH_HMP.json --recovery-receipt-sha256 ACTUAL_HMP_SHA \
  --root-working-bytes REVIEWED_GRUB_AND_FILESYSTEM_WORK_BYTES \
  --checks /PERSISTENT/HELPERS/kdlock-kdrebuild4-checks.py
```

Stage installs all release4 modules with vendor strip/signing to a fresh
directory on data2. It uses `modprobe --show-depends` to select only the
actual required module closure and matching built-in records for a second
limited directory, then regenerates its depmod indexes. A private mount
namespace makes the staged modules visible only to mkinitramfs. Private
configuration, TMPDIR and initramfs output remain on data2. The existing
`/lib/modules` contents remain outside that namespace and unchanged.

After stage rc0 and its COMPLETE receipt, invoke the same helper with
`check --controller-idle-recovery-confirmed`. Review the exact limited
modules, strip/sign/vermagic, initramfs contents, fresh Build ID/source pins
and actual block-rounded budget. Budget equals limited namespace + three
boot files + actual staged initramfs + working bytes + 1 GiB reserve.
The install phase repeats the budget against current free space immediately
before copying. No in-root initramfs generation or full module copy.

Proceed with `install --controller-idle-recovery-confirmed` only after the
root controller reviews actual check success and budget. Require actual rc0,
installed bytes matching stage, protection inventory unchanged and valid
normal GRUB default. Then use `arm --controller-idle-recovery-confirmed`
within its authorized window to select only the candidate once. Require actual
rc0 and exact armed next_entry with all other GRUB environment fields
unchanged. Each phase preserves failures and performs no automatic retry.

## One-shot boot and proof

Keep the original normal GRUB default. After fresh idle/headroom/recovery and
actual ARM rc0, the root controller may separately request ordinary reboot.
Retain argv, timestamp, old boot ID and exact armed GRUB state before the
single bounded request. Observe a fresh boot ID and the actual candidate
release by bounded read-only reconnect. No reset/force/retry on ambiguity.

The persistent postboot helper pins actual release4 Build ID, ELF,
config, bzImage and System.map and the exact linked GS/per-CPU identity
from the new build. Its source SHA256 is
`80b6eb9d68d2d1bcf1650c9bcdb315b63867665efaff08eda311d4d96c2790eb`.
After the exact persistent bytes pass guest AST verification, run it to a
fresh `BASE/receipts/postboot-kdrebuild4-spin-01` with the prior 30-second,
64 MiB command-output and 64 KiB notes bounds. Require helper rc0 plus actual
`POSTBOOT_IDENTITY_VERIFIED` on the new boot with taint0, exact installed
initramfs, mounted EFI and both build disks, active SSH and the unchanged
normal default after GRUB consumes the one-shot selection. It rehashes the
normal/legacy eight boot files and all twelve prior candidate boot files.
Kernel publication or spin behavior needs a separate admitted fixture run.
