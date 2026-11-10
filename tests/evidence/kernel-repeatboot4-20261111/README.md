# Existing kernel2 repeat boot for live4, 2026-11-11

Status: **narrow preflight, one-shot arm, ordinary reboot and exact postboot proof
completed.** The unchanged installed `7.0.0-38-kdrebuild2` kernel booted with new
ID `0f3f9c09-8837-4763-8320-388278bd83d7` and taint 0. The normal kdlock1 default
remains pinned. This record establishes boot identity and admission checks only;
it contains no later live4 source/JIT outcome.

The immediately prior boot was `fb0601dd-db5c-4396-aaa5-e59b91b16924`. Its
[live3 prefix result](../runtime-jit-prefix-20261111/README.md) completed actual
shutdown, archival settlement of eight facts and ordinary destroy/unload. Sticky
out-of-tree/unsigned taint 12288 remained, so a fresh clean boot preceded another
live attempt. That partial JIT result is not relabelled as a full generated body.

## Exact inputs and scope of the checks

The source-reviewed [one-off helper](repeat-helper.py.txt) is SHA256
`236de120d2ecd6c3c96920b7ebb590360d55f91bb35789edb8c2487d00ca1056`.
It derives from the earlier reviewed repeat helper, with immediate old boot,
fresh repeat/postboot output paths, the new module pin and the actual completed
live3 shutdown prerequisite changed. It retains the original phase separation,
normal default, once-only arm and no automatic retry/reboot behavior. The
[prepared instructions](prepared-instructions.md) are not an execution receipt.
The root controller reports actual VM helper hash/AST verification and outer
preflight/arm/postproof return 0; [the labelled report](controller-reported.json)
keeps that transcript-only outer boundary distinct from saved command results.

The helper checked the same four installed boot files, ELF/config/BuildID,
[64 kernel source hashes](repeat/kernel-source64.json) and GRUB identity as the
[first kernel2 install](../kernel-install2-20261111/README.md). No kernel rebuild,
reinstallation, full 6,901-module signature scan or 88,839-file protection scan
was repeated. Source-kernel overlay remains `81feb2d7`; running BuildID is
`fd2262c047e130787ef669419111eba6eb9ebb2c`, ELF SHA256
`7de39e303412b36ea7dd36f7260183669bc4d2829569dd1e3ac9bc2426e91809` and config
SHA256 `31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483`.

The separately [built module3](../module3-build-20261111/README.md) has SHA256
`bbd3ba41a3c4d4a68efbf24843b291ede0a38ef9223a24e421fe978a94635048`,
528,944 bytes. Preflight hashes that exact retained module at its original
`module3-9f327952-01a1bc4f/module-build` path; it does not load it.

[The immutable review JSON](review/input.json), SHA256
`a9700a5c1dd1745fa1d5de2c3d5226ff99767ffa9f279210ce0425cbf5e38673`,
keeps the existing common-source check receipts separate from changed inputs.
The prior reconciliation command ran no tests: it verified separate successful
4/12 and later 5-case receipts while preserving the initial stale-GS zero-case
refusal and failed aggregate. The changed runner AST and module build labels
both point to **one actual command result**, SHA256
`93cde66867106c3fff3c3a637222b20827aaf244d2361bc3dc754d743b9925fc`.
That command returned 0, recorded runner_ast PASS and verified 106 input files
before/after, with 104 common files unchanged. It is not two executions or a
rerun of those earlier tests. Both exact copies are retained under review/.

The fresh [HMP proof](review/hmp.json) records the real shared recovery snapshot
on all three disks; partial snapshots are not substituted. The
[headroom review](review/headroom.json) records available bytes: root
1,984,401,408; builds1 14,338,166,784; builds2 11,466,887,168; host 11,778,322,432.
It admits this existing-kernel repeat boot and bounded four-worker/eight-iteration
fixture only, with 512 MiB total live output allowance including 128 MiB wire-log
reservations and a 64 MiB archive bound. It reserves 1 GiB root and 2 GiB host/
data space. These are explicit run budgets, not general deployment capacities.
Fresh pre-arm idle checks observed no fixture/control/build/test execution and
no module or fixture devices on the old boot.

## Actual boot sequence

All times below are UTC on 2026-11-10 (local date November 11):

| Checkpoint | Actual time | Result |
| --- | --- | --- |
| [Preflight](repeat/preflight-complete.json) | 18:34:05.206744 | COMPLETE |
| [Arm](repeat/arm-complete.json) | 18:34:48.209592 | COMPLETE |
| [Ordinary reboot request](repeat/reboot-result.json) | 18:35:14.917901 | return 0 |
| [Reconnect](reconnect.json) | 18:35:37.680179 | new boot, taint 0 |
| [Postproof](repeat/postproof-complete.json) | 18:36:03.988900 | COMPLETE |

Actual helper subcommands returned 0 without timeout. Arm changed only
next_entry to the same candidate kernel2 advanced-menu entry; other environment
fields, normal kdlock1 default and GRUB configuration SHA256
`8d4c66b404bdf56ea6a94569882a495bd9d5ed23a4d38e98d11950c0d0c54089`
remained unchanged. Root separately issued bounded ordinary `systemctl reboot`;
its saved actual return 0, stdout/stderr and argv are retained. No force variant
or module operation occurred in this helper.

The unchanged pinned 91d postboot helper produced
[POSTBOOT_IDENTITY_VERIFIED](postboot/result.json), with actual
[subcommand return 0](repeat/postproof-helper-result.json). The independent
[repeat binding](repeat/repeat-postboot-binding.json) proves new boot 0f3f9c09
differs from immediate old boot fb0601dd and binds this fresh arm to the consumed
next_entry. The pinned helper's historical first-arm inputs remain separately
retained; they are not relabelled as this fresh arm.

The saved pre-live proof observed taint 0 and module/devices absent. Full linked
GS symbols match current_task == const_current_task == `0xffffffff8440f018`,
with per-CPU start/section `0xffffffff843f7000`. All 64 public CPU flag rows omit
call_depth; the runtime's actual feature guard remains authoritative. Existing
nokaslr/mitigation settings remain unchanged. This establishes neither full
handwritten/generated mitigation coverage nor later fixture GS execution.

## Retention and limits

[The copy index](copied-files.json) binds all 68 raw/retained copies by exact
SHA256/size, including losslessly compressed symbol output. The
[guest index](guest-index.json) records original saved paths. Actual review-input
child hashes match the immutable review JSON, including identical AST/build
receipt bytes. Old failures, earlier boots and module3 compilation remain
separate records.

Collection used only immutable saved-file reads/copies. No helper/parser/test,
module/control, arm or reboot command was dispatched by this collector. The
pre-live taint/idle observations are not new claims about a later loaded-module
state. This boot record establishes no later generated body, recursive execution,
indirect learning, coverage ACK, T01-T56 acceptance or performance result.
