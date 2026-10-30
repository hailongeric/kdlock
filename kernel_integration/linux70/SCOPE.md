# Scoped Linux 7 source composition and identity

## October 31 `kdscope2` killable-writer candidate

The new recipe starts at `8446f4ecb08816380a4c233197a8ce5e4d333aac`, the
original `kdscope1` kernel recipe. Its only lock implementation change is the
`kernel_module/kd_rwsem.c` delta from provider
`f7a84065e84474380faa37eeadfdf534abd72a68` to
`22d62d5c13cad3c61c97dd47524da908769f1a52`. The rwsem source at the original
recipe and at `f7a84065e84474380faa37eeadfdf534abd72a68` is identical. Keep the
original recipe's API overlay, MM adapter, physical mutex implementation and
all shared type/API/register headers. Do not substitute the later provider's
whole input tree or cherry-pick its unrelated runtime changes.

The bounded poll checks the writer reservation first. After a failed reservation,
`need_resched()` or any `signal_pending(current)` ends polling; otherwise it
uses `cpu_relax()` for at most 16,384 probes. A successful reservation returns
immediately without a second predicate evaluation. An unsuccessful poll enters
the existing `wait_event_killable` path, including its condition recheck and
fatal-signal cancellation. Gate acquisition, reader drain, phase release,
downgrade and Native MM bodies remain unchanged. Ordinary and prepared writer
paths are outside this source change; unchanged source is not a binary-layout
or performance guarantee.

The unchanged MM generator retains this helper and renames it into
`kernel/locking/kd_mmap/kd_mmap_rwsem.c`. Compare all generated lock inputs and
outputs against the original recipe: only that generated C file may change.
Release/configuration/build identity and the additive runner profiles are
separate from this algorithmic source comparison. A fresh VM preparation and
full build must record the actual output hashes; source inspection alone does
not establish generated, compiled or running identity.

- Release: `7.0.0-38-kdscope2`, with unchanged upstream version code 458766.
- Canonical source/output pair:
  `/mnt/kdlock-builds2/linux-7.0.0-38-kdscope2/{source,build}` on the separately
  provisioned build disk. Preserve the old source/output trees and their mounts.
- `kdscope2-native`: `kd_mmap=off`, bundle
  `/root/kdlock-kernel-baselines/linux70-kdscope2-native-20261031`.
- `kdscope2-kd`: `kd_mmap=on`, bundle
  `/root/kdlock-kernel-baselines/linux70-kdscope2-kd-20261031`.
- Both variants require `CONFIG_KDLOCK_MMAP=y`, `CONFIG_KD_API_LOCKS=y` and
  `CONFIG_DEBUG_SPINLOCK=n`, with all existing configuration, composition,
  installed-file and runtime-policy checks. The API object default remains
  Native. Existing `kdlock1`, `kdmm1-*` and `kdscope1-*` defaults and identities
  are unchanged.

Use the preparation/composition/capture interfaces below with new scope2
staging paths under `/mnt/kdlock-builds2` and the explicit scope2 variant.
Capture selects the canonical source/build/bundle tuple; neither a manifest nor
a supplied build path may infer another profile. The common benchmark identity
helper, shared MM platform and mmap1 runner must admit the new explicit tuple
without relaxing the old profiles. Keep the recipe generation separate from
the provider generation in every receipt. A sparse source-host checkout is not
a complete synchronized source tree; export every required tracked recipe input
with its hash before VM preparation.

Status: documentation and source preparation only. No scope2 build, boot, MM
correctness result, timing or acceptance is claimed here. Root runs basic and
directly affected checks in the VM, then one fresh matched KD-only nano matrix
and one fresh mmap1 threads/processes matrix for each compared generation.
Historical f7 measurements remain separate; no topology or qualification is
reused as new measurement evidence. Retain every negative result and keep the
candidate unaccepted. Explicit profile support also needs the affected identity,
shared-MM, mmap1 and benchmark-profile fixtures; they are not run on 380G10.

## Original `kdscope1` recipe

Status: source-only implementation and focused test sources; no preparation, build, install, reboot or test execution is established by this document. The candidate API package is still under source review. Preserve all existing `kdlock1` and `kdmm1-*` profiles and their frozen bundles.

## One new image, two explicit MM boot modes

- Release: `7.0.0-38-kdscope1`; upstream version code remains 458766. Pass the release through the reviewed kernel build/install interface; do not change SUBLEVEL or export KERNELRELEASE into external-module wrappers.
- Source/output pair: `/mnt/kdlock-builds/linux-7.0.0-38-kdscope1/{source,build}`. Neither path may reuse a prior build directory or symlink to a frozen source.
- Both `CONFIG_KD_API_LOCKS=y` and `CONFIG_KDLOCK_MMAP=y`, alongside existing x86/SMP/frame-pointer/non-RT/non-lockdep configuration requirements; additionally assert `CONFIG_DEBUG_SPINLOCK=n` for the four-byte API word.
- `kdscope1-native`: same image/configuration, `kd_mmap=off`, bundle `/root/kdlock-kernel-baselines/linux70-kdscope1-native-20261030`.
- `kdscope1-kd`: same image/configuration, `kd_mmap=on`, bundle `/root/kdlock-kernel-baselines/linux70-kdscope1-kd-20261030`.
- API binding remains **default Native in both boots**. A run chooses its bounded file-table/pipe objects through SELECT before creation. A `kdscope1-kd` boot does not make every API object KD; its name certifies MM mode. Every API result must separately carry QUERY receipts proving the actual chosen object/backend. Native/KD API comparisons should use the same MM boot mode so a boot-level MM difference cannot contaminate the API comparison.

Retain exact `nokaslr nopvspin`, consoles, lazy preemption, mitigation state, signing and recovery checks. One frozen source/image has two separately captured runtime-policy bundles, as with kdmm1. Source compilation is not evidence of actual MM or syscall execution.

## Strict composition, no manifest relaxation

The API generator continues to require its exact pristine Ubuntu source hashes. Do not teach it to accept arbitrary already modified Makefiles. Likewise do not weaken the existing MM input manifest to accommodate the API package.

1. Authenticate the same Ubuntu source archives and acquisition receipt already required by schema2. Create a fresh complete source tree from those exact archives. Record all touched pristine input hashes and source acquisition identity.
2. Prepare the MM overlay and API overlay **independently against that pristine tree**, into distinct new staging directories. Retain each prepare receipt, exact generator/patch/manifest/shared-header inputs and output hashes. Verify their unchanged-input checks.
3. Apply the reviewed core Linux7 patch to a fresh source copy using exact patch scope and fuzz0. Its exported symbols/clobber helper changes remain separate from either overlay.
4. Copy the two overlay output sets into the source, refusing any shared output pathname except the one explicitly reviewed below. Require each unique output to equal its prepare receipt hash before and after copying.
5. The only currently overlapping output is `kernel/locking/Makefile`. Both generators start from the same pristine hash and append one independently reviewed object line. Define its final bytes as pristine bytes followed by `\nobj-$(CONFIG_KDLOCK_MMAP) += kd_mmap/\n` and then `\nobj-$(CONFIG_KD_API_LOCKS) += kd_api/\n`. First prove the MM output equals pristine+MM suffix and the API output equals pristine+API suffix. Any other text or second overlap is a hard failure. Hash the composed result separately; never overwrite an input receipt with this final hash.
6. Kconfig changes currently do not overlap: MM changes `mm/Kconfig`; API adds the source statement to `init/Kconfig` and supplies `kernel/locking/kd_api/Kconfig`. Core has no Kconfig edit. API additionally adds the read-only continuation table in `include/asm-generic/vmlinux.lds.h`; it must remain in the final source hash set.
7. Record a new `composition.json` with exact inputs, independent receipt hashes, allowed collision rule, the two pre-composition Makefile hashes, final Makefile hash, and complete final named-source hash map. The independent output maps identify each output's origin; the frozen controller records the selected project commit. Rehash both staging overlays and pristine inputs after composition. Do not execute archived scripts or substitute a previously prepared source tree.
8. Verify original MM body hashes and the API generator's full selected-function normalization: only lock calls differ in set_close_on_exec, pipe_ioctl and pipe_fcntl. All command branches remain. Preserve those function-level hashes as function-level evidence, not filenames for ordinary file hash verification.

The composition helper should only prepare source and emit receipts. It must not enable configuration, compile, install or reboot implicitly. Those remain separately bounded root-owned stages.

## Schema2 extension and verification

Add the two names to the existing strict variant selector; preserve current defaults and existing variant semantics. New variants have their own canonical release/source/build/bundle tuple and require both enabled options. Existing profiles must not accept the new release or enabled API configuration accidentally.

Capture the following additional provenance in the new bundles:

- `composition.json`, both independent prepare receipts, API patch/base manifest/README or policy identity, all API generated-input files including the exact shared KD type headers/control ABI, and existing MM inputs/core patch.
- A new exact source-scope string for named core/MM/API composition, accepted only for these new variants. Existing bundles keep the old exact scope string.
- `source_files` must contain the final composed file hash map. For the Makefile collision, validate original independent output hashes against their retained staging receipt/content and the explicit composition rule, then validate the final source hash. Do not require the final file to equal both contradictory intermediate hashes; do not silently skip the intermediate verification.
- API site table, module provider ABI and binding version belong in source/binary metadata. They do not replace actual binding QUERY, returned-JIT-body, source/frame retirement or same-object syscall receipts.
- All existing build/configuration/generated-header/Module.symvers/System.map/vmlinux/bzImage/installed-file/link/runtime-boot checks remain. Bundles cannot be recaptured over an existing directory.

A capture must fail if an input receipt, generator, type header, final source, mode, image or installed file differs. Verification rechecks both independent preparation and explicit composition. It retains authenticated pristine `fs/file.c` and `fs/pipe.c` as data and recomputes selected-function normalization against the current source; captured Python is never executed.

## Preparation and capture interfaces

These are VM-only interfaces for root's reviewed kernel experiment. The output directory must be new. The preparation commands do not configure or build a kernel:

```sh
python3 kernel_integration/linux70/prepare_mmap.py \
  --source /mnt/kdlock-builds/ubuntu-7.0.0-38-source/linux-7.0.0 \
  --output /mnt/kdlock-builds/kdscope1-mmap-prepare
python3 kernel_integration/real_api/prepare.py \
  --source /mnt/kdlock-builds/ubuntu-7.0.0-38-source/linux-7.0.0 \
  --output /mnt/kdlock-builds/kdscope1-api-prepare
python3 kernel_integration/linux70/compose_scope.py \
  --source /mnt/kdlock-builds/ubuntu-7.0.0-38-source/linux-7.0.0 \
  --output /mnt/kdlock-builds/linux-7.0.0-38-kdscope1 \
  --mmap-prepare /mnt/kdlock-builds/kdscope1-mmap-prepare/prepare.json \
  --api-prepare /mnt/kdlock-builds/kdscope1-api-prepare/prepare.json \
  --acquisition /mnt/kdlock-builds/ubuntu-7.0.0-38-source/source-acquisition.json \
  --source-archives /mnt/kdlock-builds/ubuntu-7.0.0-38-source/downloads
```

After separately reviewed configuration, build, installation and Native-mode boot, capture the actual running image with:

```sh
python3 kernel_integration/linux70/capture.py --variant kdscope1-native \
  --mmap-prepare /mnt/kdlock-builds/kdscope1-mmap-prepare/prepare.json \
  --api-prepare /mnt/kdlock-builds/kdscope1-api-prepare/prepare.json \
  --composition /mnt/kdlock-builds/linux-7.0.0-38-kdscope1/composition.json
```

The separate `kdscope1-kd` capture uses the same inputs after its own `kd_mmap=on` boot. Capture requires the explicit profile's canonical source, build and bundle paths. `bench/mmap1/run.py`, shared MM runners and the common identity helper accept these explicit variants; no benchmark may infer a different release from a supplied manifest. Existing command defaults continue selecting their existing development/MM profiles.

Directly affected VM checks are `tests/unit/infrastructure/test_linux70_identity.py`, `tests/unit/infrastructure/test_linux70_scope_identity.py`, `bench/mmap_writer/test_linux70.py` and `tests/unit/bench/test_mmap1.py`. They validate identity/routing logic using controlled fixtures; real preparation, compiled bridge behavior, boot and syscall/MM execution remain separate gates.

## Gate sequence

Before a new kernel build: finish directly affected module/unit/ABI checks on the current development kernel where applicable; source-derived mock tests cannot prove built-in link/Kbuild correctness. Review final source diff and body hashes. Then root builds the combined image with the new options, compiles matching provider and checks actual bridge/site-table/continuation ELF shapes before installation.

Boot Native mode first with no API selector and no provider. Validate clean identity and basic kernel behavior. Load the single matching provider, validate selected object creation/cancellation/normal destruction and actual syscall bodies, then the bounded syscall comparison. API comparison arms keep one MM boot mode. Separately boot `kd_mmap=on`, satisfy all enabled-MM native/KD/cancellation/non-owner prerequisites and actual mmap1 lock-identity observations before claiming mmap improvement/parity. User-facing scores remain one-round workload results, separated from diagnostics and system correctness evidence.

Keep `7.0.0-38-kdlock1` as the ordinary recovery/default until root explicitly reviews a promotion. Do not infer promotion from a successful new build or boot.

## October 30 build storage plan

The initial VM check found 28 GiB free on the data disk and 36 GiB free on
root; each retained full kernel build occupies approximately 31 GiB. Preserve
those builds and all evidence. The new output may use a fresh root-filesystem
backing directory `/root/kdlock-build-output/linux-7.0.0-38-kdscope1`, bind-mounted
at the canonical build path above. The source remains on the data disk. This is
an output-storage mapping, not a source or identity alias: no symbolic link and
no shared writable old output is allowed. Record both paths, filesystem identity,
mount options and available space before building and after any boot. Reestablish
that exact mount before verification or external-module compilation; a missing
mount is not an empty build to initialize. Do not alter the existing boot default.

Before a full build, account for the observed build footprint, link intermediates,
installed stripped modules/initramfs and a reserve on root. Freeze source/config
and verify the bounded API/MM objects first. Preserve any preparation/compile
failure as a separate attempt. A deadline or insufficient-space stop must record
actual compiler process state; it does not establish drain or authorize deletion.
