# Completed recovery, db7 module build and repeat-boot collection

Preparation on the source host only. Do not issue guest or QEMU monitor commands while the backend owns the live window. Collection starts only after its explicit closure and the parent’s read-only collection clearance. Read existing immutable receipt files and copy them to new source-host evidence paths. Collection does not take a new runtime, taint, idle or recovery observation.

Each collection has a finite inventory before copying. Limits are 512 regular files, 32 MiB per file and 128 MiB total origin bytes. Remote inventory and copy commands have 60-second and 120-second bounds. Reject symbolic links, changed metadata or hashes, unexpected paths and duplicate archive members. Copy through a read-only tar stream into a fresh source-host directory, verify every received byte count and SHA256 against the independent inventory, and use lossless gzip for large JSON/log files. Retain the original size/hash and compressed size/hash separately. Preserve raw spacing and stderr. No automatic retry or partial overwrite is permitted. Retain every failed collection receipt.

## Earlier failed-run recovery

Proposed evidence path: `tests/evidence/runtime-spin-recovery-20261111`.

Read only the old fixture’s `recovery-spin-approved-01`, `recovery-spin-controller-01` and `recovery-spin-helpers-01` trees under `/mnt/kdlock-builds/kdlock-main-work/kernel4-fixtures-0a07f678-01a1bc4f`. Include the actual task-before/task-after, ordinary stop result, QUERY binding and exact wire frames, archive file and fsync receipt, SETTLE/END, destroy/unload, final module/device/activity and dmesg comparisons. The original failure’s existing evidence remains separate.

Require result SHA256 `d5b188ce454de29a730dd8871d1926c121bca8d79c1be04a7fa099726b116524`, observer result `172eedfe8c6d4ac131f1e6a63467b90c3851fdd94b3d50a67e101bd94e937262` and actual 8,824,917-byte archive `21328862c8fb47dd8ad4b7842c5b766e169c6a027aee964a458d9b78b66a678d`. The archive has five pending exact keys, not an empty claim. Keep ordinary stop errno110 separate from the actual five joined tasks, zero workers and clear locks. Record SHUTDOWN22, ARCHIVE23, SETTLE24 and END25 status0 separately. Retain source helper `3b871de1…`, observer `bfbf9386…` and the original dispatch-rejection note `541ee800…`. State that the first dispatch was rejected before SSH, and the later one ordinary attempt followed renewed explicit user authorization. The authorization discussion is a controller-transcript boundary, not a fabricated guest artifact. This evidence establishes recovery, not a successful spin workload or JIT recursive completion.

## Actual db7 two-module build

Proposed evidence path: `tests/evidence/module-spin-db7-build-20261111`.

Read the `module-build-receipts` tree under `/mnt/kdlock-builds/kdlock-main-work/kernel4-fixtures-db7d7d6e-01a1bc4f`, exact source state/manifest, the controller source, actual package manifest and six-kernel pin file. Copy `.cmd` files from the two explicit `module-build/spin` and `module-build/mutex` directories and the seven correctness-fixture source files, including the private observation include. Do not copy `.ko`, `.o`, `.a`, kernel images or entire source/build trees into Git. Retain the actual module binary paths, independently read size/hash and original build result identities.

Require actual `COMPLETE` result `cb79249bfbb6f883935b93dbeef33045a4714deecdc2da5082163830987399af`, source db7d7d6e/core2d0ad60b, 103 snapshot files, 67 package inputs and the six pins `503fab29…`. Retain both AST results, exact separate M/MO argv, eight jobs, 300-second observers, full normal compiler flags and complete warning output. Spin is 615800 bytes/SHA79521d2e…, mutex is 584856 bytes/SHAbdbfb211…. Retain the 2288/2264-byte frame warnings against 1024. The build ran on the original boot84e4/taint12288, after ordinary recovery. It is not a fresh boot or execution result.

## Same installed kernel4 repeat boot

Proposed evidence path: `tests/evidence/kernel-repeatboot4-db7-20261111`.

Read both exact completed trees `BASE/receipts/repeat-kdrebuild4-db7-20261111-01` and `BASE/receipts/postboot-kdrebuild4-db7-20261111-01`, plus the five persisted `repeat-db7*` helper/review/HMP/plan/reboot files in `overlay-kdrebuild4-spin-01`. Copy the source-host persisted-file receipt, HMP reader and raw response, helper/review/recipe/reboot source, actual reboot dispatch, bounded reconnect script and all attempts. Preserve the two different summary errors as transcript-derived notes: the initial installation’s list/string `TypeError` is historical and already recorded in kernel-install4, while the repeat’s string/integer taint `AssertionError` occurred after the saved successful proof. Neither caused a postboot helper rerun. Keep these errors distinct from the actual helper0, saved proof phase and corrected final idle0.

Require saved result `73fc01fbee3837d406fbf2ed1741b3bef85721440db3d44c369037c3ecce82db`, GS proof `a51191f8f080af052a3efb9f89b4d51d1c834b730772c07d84030165656a960d` and final idle receipt `b7942a9fa8b1a6bce5c4f164fd677db21dc5a06338c27630c2ddda4065d23745`. Exact new boot is `1b3b298f-051b-42ea-a53b-429c16f4e114`, kernel4, taint0 and BuildIDf3ca. Preserve preflight0/arm0/ordinary reboot0/postproof0 and exact arm-to-consumed-one-shot binding. The normal GRUB default remains unchanged. Root 1,212,698,624 bytes, build disk 8,591,519,744 bytes and host 8,856,014,848 bytes are the saved preflight measurements, not current values. Preserve the complete recovery snapshot proof on all three disks and the bounded serial offset if later copied. Do not infer any later fixture outcome from this boot proof.

## Return preparation

Reviewed source-only return helper is `/tmp/kdlock-main-return-normal-after-kdrebuild4-db7.py`, SHA256 `42fde322327293f3cfd9a2016ac8d07fb6d709a0775438ce8d1c61a1684a35ce`. It requires actual distinct successful spin and mutex controller receipts, the same actual module-build identity and fresh postboot73fc, positive warm completion and exact child return, actual shutdown/archive/SETTLE/END, module/device absence, idle and protected normal boot files. Only then can a separately authorized ordinary reboot run. Preparation is not an actual success or return receipt. Leave this file unchanged and do not transfer, parse or execute it during the live window.

`BASE` is `/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f`.
