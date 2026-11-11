# Kernel4 evidence collection plan

Prepared source-host-only while the separately owned fixture build window is
active. Collection starts only after its owner closes that window. The plan
authorizes receipt reads and source-host copies. Installation, boot, fixture
execution and return require their own actual phase results.

## Kernel build and the retained kernel3 witness

Use a new `tests/evidence/kernel-build4-20261111` directory. The actual build
source/core is `2d0ad60b0bc46929f3070aefa364e710c0a81115`, with 67 package
inputs. The final controller returned zero. Thirty core object targets and the
normal `bzImage modules` build returned zero. Linked identity collection
finished at 2026-11-11T02:05:58.908058Z, 288.18998034 seconds after make start.
The build's successful closure recorded normal boot884c, taint0 and idle.

Copy the bounded files from these exact VM locations.

- `DATA1/kdlock-main-work/kernel4-core-2d0ad60b-spin-01` contains transferred
  archive/source manifests, exact build helper, controller argv/result and log.
- `BASE/receipts/overlay-kdrebuild4-spin-01` contains result, final identity,
  GS config/disassembly/symbols, normal C/assembly command files, full core and
  kernel logs, ELF notes/sections, module-vermagic and six-kernel pins.
- `BASE/receipts/kernel4-retention-preflight-01` contains exact retention
  helper, its actual AST/pin receipt and fresh raw all-three-disk recovery.
- `BASE/receipts/retained-kdrebuild3-1b50e373-spin-01` contributes manifest,
  journal, preflight, ELF notes and generated-members index. Retained binaries,
  generated tar and source copies stay in the VM and are identified by their
  manifest paths, sizes and SHAs. Copying or linking the retained ELF to the
  repository is unnecessary.

BASE is
`/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f`.
DATA1 is `/mnt/kdlock-builds`.

The retention manifest SHA256 is
`a253bc04061422153b89c6496494ac12f45b4b49c5f6cb8689f8a1810ca3ff4b`.
It records 14 build outputs, 66 package sources, 10,346 generated members,
199 receipts and 612,161,618 logical bytes. Source/build originals and
installed kernel3 boot files were rehashed unchanged before its completion.

The new build result SHA256 is
`e00db7a5961879692c102a00e072c70ffc5fcbe1c5051a4203b256ea44a7cac1`.
Its final identity SHA256 is
`7c79198ee04da92873339bc5d02bd9cba47ac14598f13bf56baf25ce36c69a5c`.
The linked Build ID is `f3caad92c0cdc5f955a2410f3ec3ec0e5ccad053`.
Actual ELF SHA256 is
`310df27ab801ecb0cb291d510a77d491030b6c85388a3930df2f54306bc27dd5`.
The config remains `31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483`.
Actual new GS witness bytes at `0xffffffff814f9ec1` are
`65 48 8b 05 4f 51 f1 02`. Full current_task/const_current_task is
`0xffffffff8440f018`, per-CPU start is `0xffffffff843f7000`.

Preserve the entire diagnostic logs. Core has zero warning lines. Full kernel
has 21,201 warning lines, including 21,192 Perl locale lines, eight objtool
lines and one vendor missing-description warning. The objtool lines include
new spin entry naked returns and unsupported stack pointer realignment in
the spin-native resume. Capture exact diagnostics without removing repeats.
Build success supplies no mitigation, boot or returned-source proof.

## Staging, installation and candidate boot

Use a separate new `tests/evidence/kernel-install4-20261111` directory.
Collect all bounded files under
`BASE/receipts/install-kdrebuild4-spin-01` and
`BASE/receipts/kernel4-install-helpers-spin-01`. Preserve each phase's
outer argv/result/stdout, journal, command status, exact copied helpers and
actual AST/pin receipt. Copy the full protected-file JSON losslessly compressed,
including counts and its raw SHA. Retain metadata and actual signer/vermagic
checks for the one installed module, with full vendor module-stage log.
Store no module-tree binary copies in the repository.

STAGE and CHECK returned zero. The off-root module stage used ordinary vendor
strip/signing. The limited root namespace contains one signed same-release
NLS module and the actual depmod/built-in metadata. Root, storage, networking,
VFAT and EFIVAR dependencies were reported as built in. The actual staged
initramfs is 30,886,382 bytes with SHA256
`9b356a73d19bb9861fa05a7a77e6bad4ed875462b7cd9fe780f9a8554c34c31d`.
It was generated with private mount/config/output/TMPDIR on the build disk.

Preserve all 30 raw find diagnostics for absent optional crypto module
directories in `stage-initramfs-off-root.log`. The command returned zero and
the required init/local scripts and exact root-module closure were checked.
This status does not claim the standard full-distribution module inventory
is installed in the candidate release.

The measured CHECK budget is 1,150,128,128 bytes against 1,273,057,280 free,
with 1 GiB reserve and 16 MiB working allowance included. The 122,929,152-byte
margin is a CHECK-time observation. Actual INSTALL must record its own current
budget. Its reviewed budget receipt SHA256 is
`76a9aaa262fdcecad85d55d36abdae2cb2033c901f2c5857c9170d064d903bed`.

Append INSTALL and ARM only after their actual outer rc0 and saved COMPLETE
receipts. Record installed bytes matching stage, protected file count/hash,
required dependency closure, normal default, root space and exact next_entry.
Append the ordinary reboot command/result, read-only reconnect transcript,
fresh QEMU snapshot/headroom receipt and bounded serial interval if collected.
Retain all operational failures separately with their exact receipt boundary.

The frozen postboot helper SHA256 is
`80b6eb9d68d2d1bcf1650c9bcdb315b63867665efaff08eda311d4d96c2790eb`.
It is already persisted in the helper directory and guest AST-verified.
A successful boot claim requires actual helper rc0 and its saved
POSTBOOT_IDENTITY_VERIFIED result in a fresh postboot receipt directory.
Record actual new boot ID, running Build ID notes, ELF/config/GS identity,
module/taint state, consumed one-shot, unchanged normal default, root/EFI/build
mounts and active SSH. The helper additionally rehashes normal/recovery eight
boot files and the prior candidates' twelve boot files. Broad protected module
equality remains an installation-time check.

## Runtime evidence and ordinary return

The fixture build and each live runner have separate authors/receipt roots.
Link their eventual records without pooling spin and mutex source roles,
taints, boots, compiler images or execution scopes. A successful candidate
boot is a separate observation from generated execution, atomic recursion,
physical release ACK or exact final retirement.

A separate `tests/evidence/return-normal-kernel4-20261111` should preserve
the eventual approved ordinary return command/result, retained exact live
completion/drain/unload proof, read-only reconnect transcript and saved normal
postproof. The normal release/default remains `7.0.0-38-kdlock1`. Record
actual fresh normal boot ID, Build ID, taint0, absent fixture/control devices,
idle and protected boot/default hashes. No return has occurred at preparation.

## Copy/index discipline

Before copying a selected receipt, independently inventory remote path, regular
file type, size and SHA256 while idle. Copy exact files or compress large text
losslessly on the source host. For every compressed local copy, record both
stored bytes/hash and raw origin bytes/hash, and verify decompression against
the independently recorded origin. Include read/collection argv and rc.
List source-host helper and raw QEMU/reconnect origins separately from guest
receipts. A transcript-only operation remains labelled transcript-only.

A copy index and SHA256SUMS cover all retained files. Preserve raw control
characters and captured whitespace in logs/disassembly. Report exact
whitespace-check exceptions. Review READMEs against raw phase, wire/event
and identity receipts, then commit only the coherent evidence path. Keep
T01–T56 and performance claims at their separately recorded status.
