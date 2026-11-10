# Kernel3 installation and postboot controller preparation

Prepared on the source host only. Nothing in this recipe has been executed.
The existing reviewed one-off phase controller is the orchestration; there is
no extra build, retry, cleanup, reboot or module-loading engine.

Fixed candidate source/output remain:

```
/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source
/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/build
```

The fresh release is `7.0.0-38-kdrebuild3`, core commit
`1b50e37382d2c739b16953027c47d7e2388562f0`. The sole changed operational
namespace is:

```
BASE/install-stage-kdrebuild3-1b50e373-v1
BASE/receipts/install-kdrebuild3-1b50e373-v1
```

The normal default stays `7.0.0-38-kdlock1`; legacy recovery, installed candidate
kernel1/kernel2, their module trees, old stages and all earlier receipts remain
protected by the existing install-controller inventory.

## Actual prerequisites before dispatch

1. Require the full kernel3 build's actual rc0 and exact source/config/tool
   identity receipt, with no active make/compiler/module/test processes.
   The per-directory core compilation result alone does not satisfy this.
2. Recheck the running normal boot, taint0, real recovery snapshot on all three
   QEMU disks, guest/host headroom and no pending GRUB selection. Retain the raw
   recovery receipt; supply its exact path and SHA to the controller.
3. Retained old kernel2 witness must still have phase
   `KERNEL2_WITNESS_RETAINED` and manifest SHA
   `ac0a6e0ee74abb3fba101be5532806b3aa5d237a8969273ef031f60a74ac85c9`.
   Its source/build originals were not mutated by retention. Existing frozen
   workload/module inputs remain separate and unchanged.
4. Fill the postboot3 helper from the actual final kernel3 ELF/config/Build ID
   and actual `current_task`, `const_current_task`, `.data..percpu` and
   `__per_cpu_start` linkage in the new gs-config/identity receipt. The prepared
   helper deliberately has `None` pins and refuses to run. Kernel2 addresses,
   hashes and Build ID are not carried over. Review/freeze/hash it after filling.
5. Before any phase, root verifies copied helper SHAs and performs actual VM
   AST parsing of those exact bytes. Preparation on the source host does not
   claim a syntax pass. Use a fresh helper directory under the new overlay.

## One phase per actual successful result

All paths and SHA arguments below must be replaced with the actual reviewed
kernel3 receipt/helper values. They are deliberately not populated while the
full build is running. Root controls the guest window and preserves each
command/result/stdout. The controller never reboots.

Stage argv:

```
python3 /ACTUAL-OVERLAY/kdlock-kdrebuild3-install.py stage
  --controller-idle-recovery-confirmed
  --final-build-success-reviewed
  --final-build-receipt /ACTUAL-KERNEL3-FINAL-BUILD-RECEIPT.json
  --final-build-receipt-sha256 ACTUAL-RECEIPT-SHA256
  --recovery-receipt /ACTUAL-RECOVERY-CONTROLLER-RECEIPT.json
  --recovery-receipt-sha256 ACTUAL-RECOVERY-SHA256
  --root-reserve-bytes 1073741824
  --initrd-budget-bytes 268435456
  --checks /ACTUAL-OVERLAY/kdlock-kdrebuild3-checks.py
```

Require actual stage rc0 and `stage-complete.json` before check. Check argv:

```
python3 /ACTUAL-OVERLAY/kdlock-kdrebuild3-install.py check
  --controller-idle-recovery-confirmed
```

Review actual candidate module count (6901 only if the new build confirms it),
vermagic, stripped sections, and vendor signing outcomes. Unsigned alone is not
a new rejection. Review the actual staged allocation/root budget: the helper
requires actual module allocation + current boot files + 1 GiB root reserve +
256 MiB initrd budget to fit. Prior root free space was only about 2.102 GB; no
budget or reserve may be relaxed to force a fit.

Only after actual check rc0, `check-complete.json` and root's budget review:

```
python3 /ACTUAL-OVERLAY/kdlock-kdrebuild3-install.py install
  --controller-idle-recovery-confirmed
```

Require actual install rc0/completion, exact staged/installed module equality,
all old protected files unchanged, normal GRUB default and dependency checks.
Local ext4 root needs the four root-driver dependency closures in initrd;
virtio_net's dependency closure must be installed, with no unnecessary network
initrd requirement.

Only after installed identity/protection/headroom/idle gates pass:

```
python3 /ACTUAL-OVERLAY/kdlock-kdrebuild3-install.py arm
  --controller-idle-recovery-confirmed
```

Require actual arm rc0/completion and exact new3-only `next_entry`, unchanged
GRUB config/default and all other environment fields. Stop here. Root separately
controls the authorized ordinary reboot; there is no automatic reboot or retry.

## Fresh boot and read-only proof

After the root-controlled reboot and reconnect, require a new boot ID and the
expected release before invoking the final frozen postboot helper. Example argv:

```
python3 /ACTUAL-OVERLAY/kdlock-kdrebuild3-postboot.py
  --output BASE/receipts/postboot-kdrebuild3-20261110-UTC-01
  --timeout 30
  --max-command-bytes 67108864
  --max-notes-bytes 65536
```

That output namespace must be fresh. The helper requires rc0 AND result phase
`POSTBOOT_IDENTITY_VERIFIED`; an existing proof file alone is insufficient.
It checks the actual running notes Build ID against the new final ELF, exact
artifact hashes and full actual GS alias/per-CPU linkage, records the pinned core commit,
taint0/no fixture modules, ordinary mitigation observations, consumed one-shot
entry and unchanged normal default/configuration. It rehashes the eight exact
normal/recovery boot files from the install's retained pre-change snapshot;
the installer separately verifies all old installed module files before arm.

Preserve every failure and partial namespace. Do not silently retry, delete old
kernels, trim, force unload, weaken mitigation checks or infer drain from a
timeout. This preparation establishes no new build, installation, boot, JIT or
acceptance result.
