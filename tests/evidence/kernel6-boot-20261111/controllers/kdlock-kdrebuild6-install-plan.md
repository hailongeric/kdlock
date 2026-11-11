# Kernel6 limited installation and one-shot boot

This source-only preparation adapts the approved kernel5 procedure. None of
these helper phases has run. The controller must retain each actual command,
return code and receipt. A failed phase preserves partial state for review.

The independent source/output pair is
`/mnt/kdlock-builds2/kdlock-main-kernel6-532b68a6-rwsem-04/{source,build}`.
Its successful linked-metadata receipt is
`receipts/full-metadata-01/result.json` with SHA
`240d1a501251cd65ea29ec81f8d8b67f9cb077f6aac5a0011fca1ed922d358f9`.
The linked identity SHA is
`995255c9c14c513a356a70ba4155beac0879d37f3abd07ab7afb1fc328c0353b`.
Build ID is `5ed6cd8cffed6960ce901261dfab3bb019a0442d`.

The native strip/sign NLS stage has completed separately. Its receipt is
`receipts/nls-stage-01/result.json` with SHA
`054ea3702187da1e24f9990b4f9bd10349952f839ff661fe89cbaca782d385a6`.
The raw stage is `receipts/nls-stage-01/raw`. Its sole rebuilt module has SHA
`b00f793a4a39e3378beef5651bf6489ffa7b86985627529297a404384f769a4b`
and 12,913 bytes. The installer consumes that stage and never invokes make.

The reviewed helpers are `kdlock-kdrebuild6-install.py`,
`kdlock-kdrebuild6-checks.py` and `kdlock-kdrebuild6-postboot.py`. Transfer only
their frozen reviewed bytes to a persistent candidate path. A fresh actual
all-three-disk recovery observation, strict normal-kernel idle state and current
host/guest headroom precede each authorized mutating dispatch. The installed
normal and all prior candidate namespaces remain protected.

Run installer phases separately. Substitute actual persistent paths and the
fresh reviewed recovery receipt and SHA. Every argument is passed as an argv
element without shell interpolation.

```text
python3 -B <persistent>/kdlock-kdrebuild6-install.py stage
--controller-idle-recovery-confirmed --final-build-success-reviewed
--final-build-receipt <BASE>/receipts/full-metadata-01/result.json
--final-build-receipt-sha256 240d1a501251cd65ea29ec81f8d8b67f9cb077f6aac5a0011fca1ed922d358f9
--offroot-receipt <BASE>/receipts/nls-stage-01/result.json
--offroot-receipt-sha256 054ea3702187da1e24f9990b4f9bd10349952f839ff661fe89cbaca782d385a6
--recovery-receipt <actual-fresh-recovery.json>
--recovery-receipt-sha256 <actual-fresh-recovery-sha256>
--root-working-bytes 268435456
--checks <persistent>/kdlock-kdrebuild6-checks.py
```

`BASE` denotes the independent candidate root above. The stage output is
`<BASE>/install-stage-kdrebuild6-api-01`, with receipts in
`<BASE>/receipts/install-kdrebuild6-api-01`. It copies the exact one-module
dependency closure, regenerates depmod metadata and creates a private
MODULES=list initramfs through a mount namespace. It changes no real installed
kernel namespace. The next invocation is the same persistent installer with
phase `check` and `--controller-idle-recovery-confirmed`. Review its successful
receipt, exact dependency closure, signed module, initramfs content and measured
root budget before dispatching `install` with the same confirmation flag.

Installation creates only `7.0.0-38-kdrebuild6` module and boot files, then appends
one top-level entry `kdlock-kdrebuild6-api-01` to the existing sourced
`/boot/grub/custom.cfg`. Its loader body is copied from the actual normal entry,
with only the candidate image/initrd release, title and ID changed. Stage syntax
checks the exact combined configuration before any append. Install preserves
the entire old custom prefix and file identity/mode through O_APPEND, and
`grub.cfg` stays byte-identical. No GRUB generation command runs. This retains
the intentionally dangling scope2–4 menu entries as well as every other old
entry. The persistent normal default stays `7.0.0-38-kdlock1`. All previous
boot/module/source records and GRUB source files are compared with the
pre-stage snapshot. The root reserve
is 1 GiB in addition to the explicit 256 MiB working allowance and measured
candidate namespace/image/initramfs extent.

After actual install checks succeed and a new recovery/idle review completes,
invoke phase `arm` once. It uses top-level ID `kdlock-kdrebuild6-api-01` through `grub-reboot`,
checks that only `next_entry` changed and leaves the persistent normal default.
An independently reviewed ordinary `systemctl reboot --no-wall` dispatch follows
the actual successful arm receipt. The installer never reboots automatically.
Record its command outcome separately from the later successful reconnect.

After reconnect, run the postboot helper once with a fresh direct child of the
candidate receipts directory and explicit read/command limits.

```text
python3 -B <persistent>/kdlock-kdrebuild6-postboot.py
--output <BASE>/receipts/postboot-kdrebuild6-api-01
--timeout 30 --max-command-bytes 33554432 --max-notes-bytes 1048576
```

Consumers require helper return 0 and saved phase POSTBOOT_IDENTITY_VERIFIED.
The proof verifies a new boot distinct from normal boot
`51b49fa4-4d99-457e-a73e-632b690eb95e`, release6, taint0, actual binary GNU notes,
the new ELF/config/image/map hashes, actual signed rebuilt NLS bytes/vermagic,
all prior candidate and normal/recovery boot files, mounts/SSH and consumed
one-shot selection. Its full linked `current_task` and `const_current_task`
are `0xffffffff84416018`, with per-CPU start `0xffffffff843fe000`. These new
values come from kernel6 metadata. No kernel5 numeric alias is reused.

These operations establish installation and boot identity only. Compatibility
module checks, actual original-task mmap/munmap effects, native gate/downgrade
observations and generated execution remain separate results. No MM body is
replaced, and no performance claim follows from building or booting this image.
