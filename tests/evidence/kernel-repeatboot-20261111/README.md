# Existing kernel2 repeat boot, 2026-11-11

Status: **fresh preflight, one-shot arm, ordinary reboot and exact postboot proof
completed.** Existing kernel `7.0.0-38-kdrebuild2` was reused without build,
installation, module changes or a permanent-default change. The new clean boot is
`fb0601dd-db5c-4396-aaa5-e59b91b16924`. This record establishes repeat-boot identity
and its admission checks, not any later live3/JIT result.

The earlier [live2 compilation failure](../runtime-compilation-20261111/README.md)
and [exact recovery](../runtime-recovery-20261111/README.md) remain separate.
Recovery ended with ordinary unload, unchanged old boot
`dea66234-7f70-4e5b-acb6-40a6f2884919` and sticky taint 12288; reboot was used to
obtain taint 0 before another live attempt. Successful recovery did not change
the original failed compilation into a pass.

## Reviewed inputs and narrow preflight

The exact [repeat helper](repeat-helper.py.txt) is SHA256
`2ff4389be4a487d613fc5d8a14e54f3f0328e30b8cf46c230bd3d89ccf8baf87`.
[Prepared instructions](prepared-instructions.md) are not execution evidence.
The root controller reports VM hash/AST verification and actual outer return 0
for preflight/arm/postproof; [the labelled report](controller-reported.json)
preserves that transcript-only outer boundary. Actual helper completion,
subcommand results and readbacks are retained independently below.

[The immutable review input](review/input.json), SHA256
`bf9dc029f4a6baecf4b90906583706186d248def9a812906374733be025b5315`,
binds the actual Python-receipt reconciliation, fresh HMP and reviewed headroom.
Its [Python input](review/python-check-result.json) returned 0 while reconciling
successful **4 + 12** checks and a separate **5**-case GS follow-up for source
`18c8f2e499d5fb74972e92bad5748489b921035d`, with 106 source files unchanged.
That reconciliation command ran no tests. It explicitly preserves the initial
overall controller failure caused by the stale GS ELF pin, with zero GS cases;
these separate results are not relabelled as one successful overall run.

The [fresh HMP proof](review/hmp.json) records the real shared recovery snapshot
on all three disks; partial snapshots are not substituted. The
[headroom review](review/headroom.json) records guest root available 1,984,942,080
bytes, builds1 available 14,343,827,456, builds2 available 11,480,756,224 and host
available 11,785,879,552. It explicitly budgets this existing-kernel repeat boot
and bounded 4-worker, 8-iteration live fixture only: 512 MiB output allowance, 1 GiB root reserve,
2 GiB host/data reserve. It is not a full-build or runtime-capacity proof.

The preflight verified fresh recovery/idle/headroom, the exact four installed
boot-file pins, retained ELF/config/BuildID, all
[64 kernel source hashes](repeat/kernel-source64.json), unchanged fixture module
SHA256 `378bf139407bf57de1b4d708db3c6548a5d25537219b8ce83c2232c89010267e`,
and exact GRUB default/config/empty next_entry. The unchanged kernel/module inputs
were already verified by [kernel2 installation](../kernel-install2-20261111/README.md);
all 6,901 module signatures and 88,839 protected files were not rescanned for a
Python-only correction. Actual pre-arm idle receipts observe no fixture/control/
build/test activity and expected old taint 12288. The collector did not perform
these actions; it copied their completed saved receipts read-only.

## Actual sequence and fresh boot binding

All times are UTC on 2026-11-10 (local date November 11):

| Checkpoint | Actual time | Result |
| --- | --- | --- |
| [Preflight](repeat/preflight-complete.json) |18:00:04.171963|COMPLETE|
| [Arm](repeat/arm-complete.json) |18:01:01.650325|COMPLETE|
| [Ordinary reboot request](repeat/reboot-result.json) |18:01:41.473646|return 0|
| [Postproof](repeat/postproof-complete.json) |18:02:28.318319|COMPLETE|

All retained helper subcommand results returned 0 without timeout. Arm changed
only next_entry to the same kernel2 advanced-menu entry. The normal kdlock1
default, other environment fields and GRUB configuration SHA256
`8d4c66b404bdf56ea6a94569882a495bd9d5ed23a4d38e98d11950c0d0c54089`
remained unchanged. The root controller separately issued bounded ordinary
`systemctl reboot`; its actual argv/return 0/empty stdout/stderr are retained.
There was no force variant or module operation in this repeat helper.

The unchanged pinned 91d postboot helper produced
[POSTBOOT_IDENTITY_VERIFIED](postboot/result.json), with its own actual
[subcommand return 0](repeat/postproof-helper-result.json). Its historical OLD_BOOT
and first kernel2-arm input paths remain unchanged. The independent
[fresh repeat binding](repeat/repeat-postboot-binding.json) therefore also proves
new boot fb0601dd differs from the immediate prior boot dea66234, binds this fresh
repeat arm and checks its next_entry was consumed while normal default/config/
other environment fields remained unchanged. Historical first-arm inputs are
retained separately; they are not relabelled as this repeat arm.

The saved pre-live proof observes taint 0 and no fixture module/devices, and
matches running BuildID `fd2262c047e130787ef669419111eba6eb9ebb2c`, ELF SHA256
`7de39e303412b36ea7dd36f7260183669bc4d2829569dd1e3ac9bc2426e91809`,
config SHA256 prefix `31d9701e…`, bzImage `a5fc0917…` and System.map `47cc1e87…`. Full linked GS symbols
are current_task == const_current_task == `0xffffffff8440f018`, with per-CPU
start/section `0xffffffff843f7000`. Existing nokaslr/mitigation settings are retained;
all 64 exported CPU rows omit call_depth, while the actual runtime feature guard
remains authoritative. This is not complete handwritten/generated mitigation
coverage or proof of fixture GS execution.

## Retention and limits

[The copy index](copied-files.json) binds all 62 raw/retained copies by exact
SHA256/size; large symbol output is compressed losslessly. The
[guest index](guest-index.json) records original saved-file paths. Original
preflight/postboot process lists and taint observations remain pre-live evidence,
not fresh claims about a later loaded-module state. No new helper/parser/test,
module/control, arm or reboot action was dispatched by this collector.

No kernel/module binary is duplicated here. Earlier failures, recovery and
original kernel2 installation remain preserved. Actual JIT publication, returned
body completion, coverage ACK, acceptance T01-T56 and performance require their
own subsequent evidence and are not established by this repeat boot.
