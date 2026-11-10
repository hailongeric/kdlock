# Candidate kernel installation evidence, 2026-11-10

Status through the retained install checkpoint: **v1 preparation failed;
corrected v2 stage, check and fresh candidate installation completed.** Boot
selection and boot are not established by this record. No module was loaded and
no source/JIT body executed by this collection. Arm, boot identity and later live
fixture results require separate receipts.

The candidate is `7.0.0-38-kdrebuild1`, based on source `c6becf81` with the reviewed
`950ee6fc` active-CALL_DEPTH refusal overlay. The completed kernel-build receipts
and preserved combined-objtool warnings are in
[the build record](../kernel-build-20261110/README.md). Installation does not erase
those warnings or establish mitigation coverage. The actual source/output base is
`/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f`.
The VM remains on `7.0.0-38-kdlock1`, boot
`3d32656f-6162-4a0a-9304-bf383d34298d` in the retained preflight/stage records.

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
The actual `check` and fresh-root install receipts are retained above; one-shot
arm and later boot require their own actual receipts. The collector performed only guest reads/SCP and source-host
copy/hash/compression. No guest install, build, module load, boot selection,
reboot or trim was dispatched by the collector. Completed installation is distinct from
kernel boot, actual mutex/JIT execution, returned-body completion, acceptance
T01-T56 and performance; none of those is established here.
