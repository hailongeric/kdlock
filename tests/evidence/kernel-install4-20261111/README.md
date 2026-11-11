# Kernel4 limited installation and boot — 2026-11-11 UTC

The authorized STAGE, CHECK, INSTALL and ARM phases returned **0**, followed
by one ordinary `systemctl reboot` returning **0** and the frozen postboot
helper returning **0** with saved phase `POSTBOOT_IDENTITY_VERIFIED`.
The new boot is `84e4ba94-b616-4b65-9efe-820921f36c16`, release
`7.0.0-38-kdrebuild4`, taint 0 and running Build ID
`f3caad92c0cdc5f955a2410f3ec3ec0e5ccad053`.
Fixture execution has separate runtime receipts.

| Completed phase | UTC completion | Outer rc |
| --- | --- | --- |
| STAGE | 02:13:52.740 | 0 |
| CHECK | 02:15:13.292 | 0 |
| INSTALL | 02:27:10.610 | 0 |
| ARM | 02:28:14.898 | 0 |
| Ordinary reboot request | 02:29:15.056 | 0 |
| Postboot helper | 02:30:23.629 | 0 |

The build record identifies core/source
`2d0ad60b0bc46929f3070aefa364e710c0a81115`, all 67 package inputs, actual
kernel artifacts and full compiler diagnostics. The separate successful
spin/mutex module build receipt was matched before INSTALL. Its source fixture
commit is `0a07f67876a81c9b341670107bfef39b66a99f9e`. The module build
receipt SHA256 is
`1bfa8f99cbd05c231e39000749f6772944c2bf1586cc9856525533bde3d0c620`.
[Build record](../kernel-build4-20261111/README.md),
[installation input gate](helpers/install-controller-command.json).

Root had about 1.27 GB free, so installation used a measured release-specific
module closure. All 6,901 modules were staged on the build disk with ordinary
vendor strip/signing. The installed namespace contains one signed
`kernel/fs/nls/nls_iso8859-1.ko` and its exact depmod/built-in metadata.
This module serves the existing EFI VFAT default charset. Actual Virtio PCI,
Virtio SCSI, SCSI disk, ext4, Virtio net, VFAT and EFIVAR dependencies are built
in. The dependency replies and one-module signer/vermagic/stripped-section
checks are retained. This is a scoped VM module inventory.

The initramfs was generated on the build disk using private configuration,
TMPDIR, output and a private mount namespace for staged modules. It contains
the ordinary local-root init/scripts and required dependency closure for the
existing filesystem-UUID root command line. Its actual 30,886,382 bytes have
SHA256 `9b356a73d19bb9861fa05a7a77e6bad4ed875462b7cd9fe780f9a8554c34c31d`.
The raw generation log preserves 30
`find` diagnostics for absent optional `kernel/crypto` and
`kernel/arch/*/crypto` module directories. Generation and the saved content
checks returned zero. General hardware/distribution module support requires
its own provisioning. [Generation log](install/stage-initramfs-off-root.log).

The CHECK budget charged 643,072 bytes for the module namespace, 28,078,080
for three boot files and 30,887,936 block-rounded initramfs bytes. It included
1 GiB root reserve and 16 MiB working allowance, totaling 1,150,128,128 bytes
against 1,273,057,280 available. The actual pre-INSTALL repetition observed
1,272,926,208 available. These receipts retain their actual measurement times.
All 102,681 protected existing file identities matched after INSTALL and again
before ARM. The installed module/boot copies matched staged bytes and hashes.

The normal default is the existing `7.0.0-38-kdlock1` advanced GRUB entry.
ARM selected only the new kernel4 entry for one boot. Its configuration hash
is `9797117f0ac48ebd8122a39b38716c3f7dd5c86c59ced0ead048389ae086f9a1`.
The postboot proof records the consumed `next_entry` and the same normal
default/configuration. Normal/legacy eight boot files and all twelve prior
candidate boot files matched their protected hashes. The installation's full
protected comparison covers the pre-existing module trees.

The persistent postboot helper SHA256 is
`80b6eb9d68d2d1bcf1650c9bcdb315b63867665efaff08eda311d4d96c2790eb`.
Its actual copied bytes passed guest AST/hash checks before execution.
The saved postboot result SHA256 is
`9d9c7203ef44ab2e92c2d99b9a15663f4a38f8fa000b433c2a900825ee209e31`.
The GS proof SHA256 is
`34e0e8eaa537dd42f36bbef547c271de2e2fe740131d1dd3f8cf92349f2683ea`.
It binds the running Build ID to ELF
`310df27ab801ecb0cb291d510a77d491030b6c85388a3930df2f54306bc27dd5`,
config `31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483`,
full current/const-current-task `0xffffffff8440f018` and per-CPU start
`0xffffffff843f7000`. Root/EFI/both build mounts and SSH were checked.
Public CPU/mitigation observations retain the helper's stated scope.
[Postboot result](postboot/result.json.gz), [GS proof](postboot/gs-proof.json).

After actual helper rc0 and its saved success phase, an inline outer summary
observer indexed the list-valued `uname` field as a dictionary and raised
`TypeError`. That outer SSH/tool observation returned 1. The saved
helper/controller rc0 preceded the
summary failure. Existing proof scalars were read afterward. The helper was
executed once. The transcript-derived note
labels the missing separate raw outer-observer artifact and the later display
correction. The reconnect receipt is an actual retained source-host artifact. Final read-only status observed taint 0 and absent
fixture/devices/build activity, with 1,213,038,592 root bytes available.
That final status observation is transcript-only.
[Helper result](helpers/postboot-controller-result.json),
[observer note](controller/postproof-observer-note.json).

The remote index independently inventories 194 copied VM files, totaling
41,149,992 raw bytes. The copy index records all origin and stored hashes. Large protection/module indexes, logs and symbol
text use verified lossless gzip. `SHA256SUMS` covers local retained files.
Collection reads only completed receipts and performs source-host compression.
T01–T56, broad spin semantics and mitigation coverage retain their separate
evidence requirements. [Remote index](remote-index.json), [copy index](copy-index.json).

The raw note dumps, dependency replies and boot/kernel logs preserve 119
trailing-space lines. Their captured bytes are retained for hash equality.
