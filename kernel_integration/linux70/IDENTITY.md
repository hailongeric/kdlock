# Linux 7 kernel identity

The schema-2 identity is for `linux=7.0.0-38.38`. Its default `kdlock1`
variant uses release `7.0.0-38-kdlock1` with `CONFIG_KDLOCK_MMAP=n` and
keeps these two directories distinct:

| Purpose | Canonical guest path |
| --- | --- |
| Development source | `/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/source` |
| Build output and external-module KDIR | `/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build` |
| Captured identity | `/root/kdlock-kernel-baselines/linux70-kdlock1-20261027` |

After installing and booting that exact kernel, run in the VM:

```sh
python3 kernel_integration/linux70/capture.py --preempt lazy
python3 kernel_integration/linux70/verify.py --running
```

If the source includes the optional mmap overlay, also pass
`--mmap-prepare /absolute/path/to/prepare.json` to capture, including when
`CONFIG_KDLOCK_MMAP` is disabled. The preparation receipt must describe the
actual source outputs and current generator inputs. Capture requires a new
output directory and does not replace an existing identity. A failed capture
is not a pass; resolve its reported mismatch before using the bundle.

The capture hashes the three exact source-package archives against their
authenticated Ubuntu checksums and preserves the previously verified source
acquisition receipt. Subsequent checks bind that receipt and those identities;
they do not repeat the archive signature verification or a complete upstream
source audit. The named source scope includes the original Makefile/changelog,
all core patch destinations, and, when present, every mmap preparation output
and its recorded untouched MM bodies. All mmap generator inputs are copied
into the bundle. This records the prepared implementation without claiming
that every other source file was inspected.

The verifier checks the canonical source/build roots and generated O= Makefile
binding, the complete configuration, generated release/version headers,
`Module.symvers`, `System.map`, `vmlinux`, and `bzImage`. The release must be
the explicitly selected variant's exact release; the source's 7.0.14 version
code remains `458766`.
Installed boot image, config, System.map and initrd hashes are required. The
installed image/config/System.map must equal their build counterparts, and
`/lib/modules/<release>/build` must point to the captured build directory.
If an installed `source` link exists, its target is also captured and checked;
the generated O= Makefile always binds the separate source directory.
This does not inventory every installed module or establish module correctness.

Running verification additionally checks uname and the GNU Build ID against
the built vmlinux. It compares the exact captured command line and active
dynamic-preemption control, requires `nokaslr` and `nopvspin`, and supports an
explicitly captured `lazy` or `voluntary` policy for `kdlock1`, without a
`kd_mmap=` option. The separate MM variants below require `lazy`. Only this complete live check
returns `runtime_policy_verified: true`. An identity pass does not establish
recovery readiness, CPU frequency, topology, ownership correctness, returned
JIT execution, or performance qualification.

The shared benchmark helper dispatches schema 1 to the unchanged legacy
verifier and schema 2 to this verifier. For schema 2, `--kernel-source` names
the **build directory**, because runners use it as KDIR. Code that copies
original kernel implementations uses `kernel_identity.source_directory()` to
locate the separately bound source. Result capture preserves `manifest.json`
and every `bundle_files` entry, then verifies the retained copy again.

## Separate enabled-MM identities

The two additional variants describe one separate enabled-MM build and two
explicit boot modes. The [enabled-MM checkpoint](../../bench/results/10.176.26.71/tests/linux70-kdmm1-20261027/README.md)
records its completed build/installation, both clean boot modes, fresh API,
mapping, fault and completed-fault passes in both modes, and all 42 shared-MM
timing points with normal drain. The matched comparison uses the same image,
configuration, source and prepared binaries, with one exploratory round per
point. The original `contention_ok` failure, later normal cleanup and separate
diagnostic pass remain distinct outcomes.
These variants do not change the `kdlock1`
normal default. Do not modify the source, build, installation or identity used
by an active campaign.

| Explicit variant | Release | Required config and boot mode | Canonical bundle |
| --- | --- | --- | --- |
| `kdlock1` | `7.0.0-38-kdlock1` | `CONFIG_KDLOCK_MMAP=n`, no `kd_mmap=` | `/root/kdlock-kernel-baselines/linux70-kdlock1-20261027` |
| `kdmm1-native` | `7.0.0-38-kdmm1` | `CONFIG_KDLOCK_MMAP=y`, exactly one `kd_mmap=off` | `/root/kdlock-kernel-baselines/linux70-kdmm1-native-20261027` |
| `kdmm1-kd` | `7.0.0-38-kdmm1` | `CONFIG_KDLOCK_MMAP=y`, exactly one `kd_mmap=on` | `/root/kdlock-kernel-baselines/linux70-kdmm1-kd-20261027` |

Both MM modes bind source
`/mnt/kdlock-builds/linux-7.0.0-38-kdmm1/source` and build/KDIR
`/mnt/kdlock-builds/linux-7.0.0-38-kdmm1/build`. They require active lazy
preemption, `nokaslr`, `nopvspin`, the exact recorded command line, the full
configuration and the same source/install checks as `kdlock1`. A missing,
duplicate, opposite or unknown `kd_mmap` option fails. Capture also requires
the MM preparation receipt and each mode's canonical new bundle directory.
The manifest records `variant` and `runtime_policy.mmap_mode`; verification
requires the caller to select the matching variant, even for a copied bundle.
An old `kdlock1` manifest without `variant` remains valid only as `kdlock1`.

The existing canonical trees and bundles below are already populated and
frozen. The following preparation sequence documents their construction;
do not rerun it over those inputs. Any later rebuild needs a separately
reviewed destination and a drained VM:

1. Create the new source/build directories from the authenticated pristine
   Ubuntu source and the captured `kdlock1` configuration, keeping all old
   inputs unchanged. Apply [kernel.patch](kernel.patch) to that new source.
2. Generate a fresh MM overlay from pristine input with the command below.
   Verify `prepare.json` succeeded, hash-check every named output, copy only
   those outputs into the new source, and recheck the installed output hashes
   and unchanged native-body hashes. Retain the receipt and copy inventory.
3. Set `CONFIG_KDLOCK_MMAP=y` in the new build config and choose a distinct
   `CONFIG_VERSION_SIGNATURE`. Preserve the compiler, configuration dependencies,
   signing setup and required guards in the [kernel build guide](README.md).
   Run `olddefconfig`, review the complete config delta, and record it before
   building. Only the adapter selection and version signature are intended
   differences from the captured `kdlock1` config.

```sh
python3 kernel_integration/linux70/prepare_mmap.py \
  --source /mnt/kdlock-builds/ubuntu-7.0.0-38-source/linux-7.0.0 \
  --output /mnt/kdlock-builds/linux70-mmap-prepared-kdmm1

make -C /mnt/kdlock-builds/linux-7.0.0-38-kdmm1/source \
  O=/mnt/kdlock-builds/linux-7.0.0-38-kdmm1/build \
  KERNELRELEASE=7.0.0-38-kdmm1 CC=x86_64-linux-gnu-gcc olddefconfig

python3 tests/kernel/mmap_lock/linux70_scope.py \
  --pristine /mnt/kdlock-builds/ubuntu-7.0.0-38-source/linux-7.0.0 \
  --tree /mnt/kdlock-builds/linux-7.0.0-38-kdmm1/source \
  --build-output /mnt/kdlock-builds/linux-7.0.0-38-kdmm1/build \
  --preparation /mnt/kdlock-builds/linux70-mmap-prepared-kdmm1/prepare.json \
  --mode enabled --make-arg KERNELRELEASE=7.0.0-38-kdmm1 \
  --make-arg CC=x86_64-linux-gnu-gcc \
  --output /root/kdlock-evidence/10.176.26.71/tests/linux70-kdmm1-scope

make -C /mnt/kdlock-builds/linux-7.0.0-38-kdmm1/source \
  O=/mnt/kdlock-builds/linux-7.0.0-38-kdmm1/build \
  KERNELRELEASE=7.0.0-38-kdmm1 CC=x86_64-linux-gnu-gcc -j16 bzImage modules
```

Use this same explicit release for full-kernel installation. Do not override
`SUBLEVEL` or export `KERNELRELEASE` into external-module wrapper builds.
Preserve the installed stock and `kdlock1` kernels, verify actual module
signatures and initramfs contents, and establish recovery before live work.
Boot the new image with `kd_mmap=off` first, capture it, then separately boot
the same image with `kd_mmap=on` and capture that mode. Check clean boot state
and the actual backend mode before running any workload. These helpers do not
install, select a boot entry, reboot, or create a recovery snapshot.

Both canonical mode bundles have already been captured. Their manifest hashes
are `7e1032c4b89618882bbadc128084e36c35e1ef9a4627608668b8404e71fc6649`
(Native) and `39aa98e8a62d2e150064f8c6d5bfb5ae61e16b4a207b9efec80a0b9c263c6a7f`
(KD), with common Build ID `ac9ea2ec7f24be8b910547bdfdbfb071176677e6`.
The clean Native snapshot is `linux70-kdmm1-native-clean-20261027`; its actual
monitor listing is bound by the checkpoint. Recheck the actual snapshot and
current boot before live work. Existing bundles should only be verified:

```sh
# Choose only the variant matching the current kd_mmap= boot mode.
python3 kernel_integration/linux70/verify.py --variant kdmm1-native --running
python3 kernel_integration/linux70/verify.py --variant kdmm1-kd --running
```

The original capture sequence below requires new, absent bundle directories;
it is provenance for the populated bundles, not a command to repeat over them:

```sh
# After booting 7.0.0-38-kdmm1 with kd_mmap=off:
python3 kernel_integration/linux70/capture.py --variant kdmm1-native \
  --mmap-prepare /mnt/kdlock-builds/linux70-mmap-prepared-kdmm1/prepare.json
python3 kernel_integration/linux70/verify.py --variant kdmm1-native --running

# After booting the same image with kd_mmap=on:
python3 kernel_integration/linux70/capture.py --variant kdmm1-kd \
  --mmap-prepare /mnt/kdlock-builds/linux70-mmap-prepared-kdmm1/prepare.json
python3 kernel_integration/linux70/verify.py --variant kdmm1-kd --running
```

The shared benchmark helper exposes `--kernel-variant`, defaulting to
`kdlock1`. MM callers must also pass the exact MM build and selected bundle
paths using `--kernel-source` and `--kernel-baseline`; the helper never infers
a mode from a manifest. `kernel_identity.check(source, bundle, variant=...)`
and `source_directory(..., variant=...)` preserve their two-argument default
for existing callers. Result capture forwards that selection to both the
live preflight and the retained-copy check. Schema-1 bundles reject MM variants.

Focused identity checks are in
[test_linux70_identity.py](../../tests/unit/infrastructure/test_linux70_identity.py).
Run it in the designated VM after an idle synchronization; it covers both
explicit modes, old defaults, source/build/install drift, MM provenance,
command-line mismatch, configuration mismatch and copied-bundle dispatch.
These new checks have not yet been executed. Identity acceptance still does
not replace the separate MM API/lifetime/fault checks, writer-site binding,
same-image comparison gates or recovery checks in the
[MM runner plan](../../bench/mmap_fault/LINUX70_PLAN.md).
