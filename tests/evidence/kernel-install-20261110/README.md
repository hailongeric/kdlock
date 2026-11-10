# Candidate kernel installation evidence, 2026-11-10

Status through the retained boot checkpoint: **v1 preparation failed; corrected
v2 stage/check/install/one-shot arm completed, and the candidate boot identity was
verified.** The original kdlock1 default remains pinned. No module was loaded or
source/JIT body executed by this collector. Live fixture/JIT execution, whole-lane
correctness, acceptance and performance require separate records.

The candidate is `7.0.0-38-kdrebuild1`, based on source `c6becf81` with the reviewed
`950ee6fc` active-CALL_DEPTH refusal overlay. The completed kernel-build receipts
and preserved combined-objtool warnings are in
[the build record](../kernel-build-20261110/README.md). Installation does not erase
those warnings or establish mitigation coverage. The actual source/output base is
`/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f`.
The retained preflight/stage records are on `7.0.0-38-kdlock1`, boot
`3d32656f-6162-4a0a-9304-bf383d34298d`. The later actual candidate boot is
`91f48b75-2d02-4de1-81cf-f99902f6e3c7`; the stages remain distinct below.

## V1: actual parser failure, no module staging

[The complete error](attempt-v1/stage-idle.log) records `SyntaxError: expected
'except' or 'finally' block` at line 119 of the copied checks helper. A newly added
process-name condition was indented outside its `try` block. The idle command
returned 1 without timeout. The controller records
[FAILED_NO_AUTOMATIC_RETRY](attempt-v1/stage-failure.json); its
[journal](attempt-v1/stage-journal.jsonl) contains no protection, identity or
modules-install command. A subsequent read-only inventory confirms the original
stage directory exists and is empty. It and its guest receipts were preserved.

The actual failed helper bytes are retained as
[checks.py.txt](attempt-v1/checks.py.txt), SHA256
`4637f7f6c7f93a91efdaef6ab76647c25283cb4610c8bd8c7669dec036c3372d`.
Its [controller](attempt-v1/controller.py.txt) is SHA256
`e4a19e1bd68cba3df73e60a083097e5e7c31e382d74825afec351ddf79e7fe1f`.
The `.txt` suffix is only the evidence filename; copied bytes and original guest
paths/hashes are recorded in [the copy index](copied-files.json). Configuration,
command result and full failure metadata remain beside them. This is a failed
preparation attempt, never an install or kernel correctness pass.

## V2: narrow correction, fresh namespace, actual stage completion

[The helper correction](checks.py.txt.correction.diff) adds exactly four spaces,
returning that condition to its existing `try` block. The
[controller correction](controller.py.txt.correction.diff) changes only both stage
and receipt paths to fresh `-v2` namespaces; it does not resume or overwrite v1.
Corrected exact helpers are retained under [attempt-v2](attempt-v2/helper-hashes.json):

- Checks SHA256: `d0554e9590d2c17249894a9aadf121512b5c7f21227c27290bf0bd0ac5ac05b8`.
- Controller SHA256: `cc31b2ebeffac4c074e1a389fb95d1c149faef0b9bbfca1a90f63cc9ee68132b`.

The controller reports that it asserted both hashes and parsed both files with
`ast.parse` in the VM before dispatch. That exact raw command/output was retained
only in the controller transcript, not a separate VM artifact. The
[explicitly labelled report](preflight/controller-reported-ast.json) preserves
that boundary without inventing a raw receipt or rerunning the parser. The
[actual preflight idle JSON](preflight/kdlock-kdrebuild1-v2-preflight-idle.json)
and later successful copied-helper idle/stage executions are retained separately.
Static peer review had missed the v1 indentation error; it is not syntax evidence.

[The actual stage command/result](attempt-v2/stage-modules-install-result.json)
uses the explicit fresh `INSTALL_MOD_PATH`, `INSTALL_MOD_STRIP=1`, final candidate
release and separate source/output directories. It returned 0 without timeout in
162.20628352199856 seconds. The [full log](attempt-v2/stage-modules-install.log.gz)
is compressed losslessly; its decompressed SHA256 is
`47efffeac9ee895e7cdf034132d5b55e428cc11c3db757d3326451b4e10f9101`.
[Stage completion](attempt-v2/stage-complete.json) marks no module load or reboot.

The log contains 74 vendor `Not signing` lines. These are preserved actual vendor
outcomes, not suppressed warnings or a new unsigned-module rejection policy.
At the stage boundary, per-file module inventory/vermagic/DWARF/signature
validation was still pending. The subsequent actual `check` result is recorded
below; stage success alone did not establish it. Compression
configuration remains ZSTD support with COMPRESS_ALL off, so normal staging uses
uncompressed `.ko` files. No claim that every module is signed follows from a
SIGN progress line.

The initial old-file protection inventory contains 81,918 records covering
8,105,535,897 regular-file bytes across boot/default files and 21 existing module
roots. Its 18,844,038-byte raw JSON remains on the guest at
`receipts/install-kdrebuild1-01a1bc4f-v2/stage-protected-before.json`, SHA256
`cc274a266bed82ffb3d9c3147b071b40cf728c7125c212b2116f0b2dec328b8d`.
Only its hash/count/path and module-root list are copied in
[the guest index](guest-receipt-index.json); old module binaries and the large
per-file map are not duplicated here. The later actual unchanged verification is
recorded below. The bounded [source/tool/artifact identity](attempt-v2/identity-pin.json),
configuration, logs, command results and journal are retained in full.

## V2 check and installation: actual completed phases

The [check phase](attempt-v2/check-complete.json) completed at 2026-11-10
15:29:42.573545 UTC; the [install phase](attempt-v2/install-complete.json)
completed at 15:33:54.019887 UTC. Each command result and complete journal is
retained beside those receipts. The actual commands returned 0 without timeout.

[The staged module inventory](attempt-v2/check-modules-stage.json.gz) contains
6,901 exact modules matching the built modules.order. The helper checked candidate
vermagic and absence of DWARF debug sections after normal INSTALL_MOD_STRIP=1.
It records 6,827 signed modules and 74 unsigned modules, preserving actual vendor
signing exclusions. The [installed inventory](attempt-v2/install-modules-installed.json.gz)
has the same relative module names, sizes, SHA256 and modes; the controller's
exact comparison completed successfully. Both JSON inventories are compressed
losslessly; raw-byte and compressed-byte hashes are retained in
[the copy index](through-install-copied-files.json). No module binary is copied
into this evidence directory, and unsigned status alone was not a new gate.

The install uses only the fresh `/lib/modules/7.0.0-38-kdrebuild1` and candidate
boot filenames. Actual depmod, update-initramfs and update-grub returned 0. The
[installed boot record](attempt-v2/installed-boot.json) binds the actual files:

| File | Bytes | SHA256 |
| --- | ---: | --- |
| vmlinuz-7.0.0-38-kdrebuild1 | 17,183,232 | b3e3ecb331bd163c7a4b97ca6c82f365b07519488b7e499f90dee875d945ddbd |
| System.map-7.0.0-38-kdrebuild1 | 10,564,272 | 47cc1e87e95f2e118f9a20ff01ec8e31dee1f9d0f650ef9649392a25db98395f |
| config-7.0.0-38-kdrebuild1 | 308,548 | 31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483 |
| initrd.img-7.0.0-38-kdrebuild1 | 103,186,109 | f0b83f82385e46c5f89dad941318c2a8406e3c89262625ebf00276d3d4b86984 |

The four local-root dependency queries (`virtio_pci`, `virtio_scsi`, `sd_mod`,
`ext4`) and installed-network query (`virtio_net`) each returned an actual
`builtin` result in this exact candidate. They therefore require no corresponding
module file in the initrd. This is the observed dependency result, not an assumed
ext4 module path or a generic permission to omit loadable root dependencies.
The complete initrd listing and dependency logs/results are retained.

[Protected-file verification](attempt-v2/install-protected-after.json) reports
`unchanged: true` for all **81,918** records, with command return 0. The helper
compares original path membership, regular-file bytes/sizes/modes and symlink
targets; this does not claim unchanged inode or timestamp fields it never stored.
Normal/legacy installed payloads, prior boot files/aliases and GRUB default files
remain preserved by that comparison. The large original map stays on the guest
under its recorded hash rather than being duplicated.

The [installed GRUB check](attempt-v2/install-grub-installed.json) passed syntax,
unique normal/legacy/candidate entry and normal-default checks. The generated
configuration SHA256 is
`1275383e31ad29a10cb782e6116cf0fdcd7bb635d51561113e8597b5648b9a7e`;
`next_entry` is empty at this checkpoint. The ordinary default remains the exact
kdlock1 advanced-menu entry. No arm or reboot is implied by a valid candidate
menu. [Final disk usage](attempt-v2/install-disk-usage.log) reports root available
2,815,406,080 bytes and builds2 available 12,809,793,536 bytes. The explicit
1 GiB root reserve and 256 MiB initrd budget were met; these install budgets are
not runtime pool/stack capacity proofs.

## Actual one-shot arm and candidate boot

[Arm completion](attempt-v2/arm-complete.json) is recorded at 2026-11-10
15:50:14.855870 UTC. The actual one-shot command, sync and metadata checks returned
0. [Pre-arm protection](attempt-v2/arm-protected-before-arm.json) again reports all
81,918 old-file records unchanged. Candidate boot-file/module bytes were checked
before arming; the normal and recovery namespaces remain preserved. Before/after
GRUB receipts confirm only `next_entry` changed to the exact candidate advanced
entry. Other environment fields and the generated GRUB configuration hash stayed
unchanged. Arming itself performed no reboot or module load.

The fresh [preboot HMP proof](beforeboot-hmp.json), captured 15:49:08 UTC, again
lists `kdlock-builddisk-clean-20261031` on all three disks and labels the other
snapshots partial/non-loadable. Its SHA256 is
`8ed8e909cff19c9011fdc0ae691bc16f8d9ed0feca37250ab7a9735cf0f7cac4`.
It records the console start offset 141,145,949 and host available bytes
12,448,370,688; it is not a fresh restore experiment.

The controller reports `systemctl reboot` returned 0. The exact saved
[reconnect trace](reconnect.json) preserves a first SSH banner-exchange timeout
(return 255), followed at 15:52:36 UTC by return 0 observing
`7.0.0-38-kdrebuild1`, new boot ID `91f48b75-2d02-4de1-81cf-f99902f6e3c7`
and taint 0. The timeout is retained, not treated as drain or reboot failure.
The [bounded serial interval](serial-boot-interval.log) contains the candidate
Linux-version line and ends at the first subsequent login prompt. Its exact
[range/hash receipt](serial-boot-interval.json) records bytes
[141145949, 141234657), 88,708 bytes, SHA256
`60afab1be0e6e8b5c17adf04e31592e92764349fb960e2de95231977656b6655`.
The full preexisting 141 MB console file stays on the QEMU host.

## Postboot identity and its operational failure boundary

The first postboot launch returned 2 because the temporary `/tmp` helper was
absent after reboot; no proof directory was written. That operational failure's
exact raw command/output was retained only in the controller transcript, not a
saved VM artifact. [The labelled run context](postboot-run-context.json) preserves
that boundary; it does not manufacture a raw log or rerun the failed command.
The same reviewed helper bytes were then copied to persistent receipt storage,
SHA256 `230a28f4f5f56b760c17cd71ae50951a24825729538dce96c2d35b765857e27a`.
The controller reports an actual VM hash/AST check and outer helper return 0;
those outer command observations are explicitly transcript-reported. The exact
[persistent helper](postboot-91f48b75/postboot-helper-230a.py.txt),
[saved result](postboot-91f48b75/result.json) and all its actual read-only command
outputs are retained independently. Success requires both that return 0 and
`POSTBOOT_IDENTITY_VERIFIED`, not a proof file's mere existence.

The saved result identifies the actual running ELF GNU BuildID
`f34c6d56a0f0545790efd04c566dc390cae8d2ae`, parsed from the retained binary
`/sys/kernel/notes` and matched to actual vmlinux readelf output. It also matches
vmlinux SHA256
`466907d2a9e392eaa976035595ca99da8e5a8a25653efead677de82cab006db9`,
the exact config/bzImage/System.map pins and installed image/config bytes. The
command line contains the candidate boot image, `nokaslr` and `nopvspin` without
changing the original mitigation options. The postboot checks observed taint 0
and no KD/fixture module, and verified boot, taint and module list stability
through the proof. These are that immutable pre-fixture observation, not a new
snapshot after later module activity.

[The scoped GS proof](postboot-91f48b75/gs-proof.json) records actual linked
`current_task == const_current_task == 0xffffffff8440f018` and per-CPU section/
start `0xffffffff843f7000`. Full symbol and section outputs are retained; the
13,017,905-byte symbol table is compressed losslessly, with raw/compressed hashes
in [the copy index](through-postboot-copied-files.json). This proves the exact
linked/running-kernel symbol input under the declared layout. It does not prove
fixture relocation normalization or emitted GS instruction behavior.

All exported CPU flag rows showed no `call_depth`; retained public statuses
report retbleed not affected, aligned ITS branch/return thunks and Enhanced/
Automatic IBRS. These are public observations; the built runtime's actual
`cpu_feature_enabled(X86_FEATURE_CALL_DEPTH)` refusal remains authoritative for
source admission. No mitigation was disabled and no return/indirect-branch
coverage claim follows. Full boot journal/dmesg and the earlier build's objtool
warnings remain separate evidence.

Postboot GRUB readback matches the exact prior armed configuration SHA256
`1275383e31ad29a10cb782e6116cf0fdcd7bb635d51561113e8597b5648b9a7e`,
confirms `next_entry` was consumed and preserves the pinned ordinary kdlock1
default. Successful one-shot boot does not select the candidate as the permanent
default or authorize deletion of previous kernels.

## Recovery and evidence limits

[The actual HMP recovery proof](recovery-hmp.json), captured 2026-11-10
15:10:36 UTC, has SHA256
`ce60632a1439be60b359346cada9d58480289a996781f5223a541792cbb34ee7`.
It lists `kdlock-builddisk-clean-20261031` under snapshots present on all disks,
with the system, data1 and builds2 qcow2 devices identified. Four other names are
explicitly partial/non-loadable; they are not substituted for that recovery
point. This readback is not a new restore experiment. The same proof hash is
bound by both actual attempt configurations.

[The prepared recipe](install-recipe.md) is instructions, not execution evidence.
Actual stage/check/install/arm and later boot-identity receipts are retained
above, with failures preserved and their evidence scopes separate. The collector performed only guest reads/SCP and source-host
copy/hash/compression. No guest install, build, module load, boot selection,
reboot or trim was dispatched by the collector. Candidate boot/identity is established above. It is distinct from actual
mutex/JIT execution, returned-body completion, acceptance T01-T56 and performance;
none of those is established here. Later fixture work has its own source/config/
boot/exit attribution and must not be pooled into this boot record.

Raw kernel journal, cpuinfo, readelf and serial output retain their original
trailing spaces, terminal carriage returns and final blank lines so their hashes
remain exact. The full staged whitespace check reports those raw-output format
lines; the separate prose/JSON whitespace check is clear. No evidence bytes were
trimmed to hide that distinction.
