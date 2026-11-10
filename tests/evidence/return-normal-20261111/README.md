# Normal-kernel return after live4, 2026-11-11

Status: **ordinary reboot returned 0; the normal kernel identity was verified.**
The VM returned to `7.0.0-38-kdlock1`, boot
`ca0b717b-c19d-4027-b598-6a1cf58b93d2`, with taint 0 and no fixture module or
devices. The pinned normal default remained unchanged. Candidate/live JIT
results remain bound to the earlier kernel2 boots, not this normal-kernel boot.

## Actual prerequisite and reboot

The source-reviewed [return helper](return-helper.py.txt), SHA256
`57254ed07eb4acd89f707672f430398d7693225a665293fc4af5907d6552eba1`,
required the completed live4 controller/result, actual native-hold drain,
all eight ordinary observations acknowledged, no pending/settled keys and all
30 recorded wire statuses 0. Final operations were SHUTDOWN, ARCHIVE_CLAIM,
SETTLE and CLAIM_END (9/10/11/6). The relevant result/controller SHA256 and full
operation list are retained in [pre-reboot.json](vm/pre-reboot.json); the learning
run itself has separate execution and publication receipts.

The helper freshly checked kernel2 boot
`0f3f9c09-8837-4763-8320-388278bd83d7`, taint 12288, module/devices absent,
no unexpected fixture/build/test activity, empty next_entry/prev_saved_entry,
normal default and exact GRUB configuration. Its complete process readback is
preserved. It performed no unload, reset, experiment, arm or force command.

[The actual reboot result](vm/reboot-result.json) records ordinary
`systemctl reboot`, timeout bound 30 seconds, return 0, empty stdout/stderr and
elapsed 0.004891836000069816 seconds. Its request timestamp is 2026-11-10
18:47:13.598773 UTC (local date November 11). This is command-return metadata,
not a timing/performance experiment or a claim that reboot completed at that
instant. [Reconnect](reconnect.json) subsequently returned 0 at
18:47:39.615354 UTC with the new normal release/boot/taint identity above.

## Saved normal-kernel proof

[The post-return result](vm/post-normal/result.json), timestamped
18:48:20.940548 UTC, records `NORMAL_KERNEL_RETURN_VERIFIED` and running GNU
BuildID `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`. The actual
[binary kernel notes](vm/post-normal/kernel-notes.bin), complete dmesg,
module list, activity and GRUB environment are retained. Independent
[source-host static inspection](static-notes-check.json) of those saved notes
matches the same BuildID; it is not another VM observation or test.

The root controller used an inline read-only post-return identity/assertion
observer and reported outer return 0. That observer source was not saved as a
standalone file. [The explicit report](controller-reported.json) labels this
transcript-only boundary; no raw observer script or outer command receipt is
invented. The actual saved result, notes and outputs remain independently
available. The root likewise reports the return helper's actual outer return 0;
the child systemctl return has its own saved receipt above.

The saved proof observes module/devices absent and taint 0. GRUB configuration
SHA256 remains
`8d4c66b404bdf56ea6a94569882a495bd9d5ed23a4d38e98d11950c0d0c54089`,
with empty next_entry. The prior exact configuration/default is retained in the
pre-reboot receipt and matches the post-return hash; normal release was actually
observed. Sticky out-of-tree/unsigned taint was cleared by this boot, not by the
earlier unload. Root available bytes are 1,983,856,640, builds1 14,333,890,560 and
builds2 11,452,841,984 at the saved post-return checkpoint.

## Evidence limits and retention

[The copy index](copied-files.json) binds all 11 copied raw artifacts by exact
SHA256/size; [the guest index](guest-index.json) preserves original VM paths.
The helper contains no candidate-output deletion or source/build mutation;
normal and candidate evidence remains in its original namespaces. Kernel and
module binaries are not duplicated in this directory.

This collector performed only saved-file reads/copies and static inspection of
the saved notes. It issued no VM probes, tests, module/control, build, arm,
reboot or cleanup commands. Normal-kernel return does not alter earlier failures,
prove a candidate result on this new boot, complete acceptance T01-T56 or
establish a performance gain. Later work requires its own idle/recovery/input
checks and evidence.
