# Kernel5 build, installation and postboot checkpoints

This preserves six completed guest receipt trees for core
`1114b41ea0f6ecf92f2c9af2904a4218bb344829`, release
`7.0.0-38-kdrebuild5`. It records build/installation/identity evidence, not reader
mechanism acceptance or performance. The failed bounded-read proof remains
failed; its later successful proof is a separate result on the same boot.

| Receipt tree | Recorded result |
| --- | --- |
| [overlay](guest/overlay/result.json) | 71 input files; targeted 31 units (28 C, 3 assembly) return 0; ordinary bzImage/modules return 0; aggregate 284.598 seconds |
| [install](guest/install/stage-complete.json) | Separate stage/check/install/arm COMPLETE records; bounded selected module namespace and off-root initramfs |
| [initial postboot](guest/postboot-initial/result.json) | POSTBOOT_IDENTITY_VERIFIED; boot `6f99fdb9-8d47-46dd-9e72-dfa6ecd774f4`, taint 0 |
| [capacity postboot](guest/postboot-capacity/result.json) | POSTBOOT_IDENTITY_VERIFIED; boot `9336b735-78f0-4f9c-9d9e-f04677f8d6bc`, taint 0 |
| [learning proof, initial attempt](guest/postboot-learning-failed/result.json) | FAILED_RETAIN_OUTPUT: the 16 MiB read bound refused the installer protection record |
| [learning proof, follow-up](guest/postboot-learning-proof/result.json) | Separate 32 MiB bounded proof passed on the same `b827f92c-254a-4cd3-a989-c6ea32c74605` boot, taint 0 |

The linked [final identity](guest/overlay/final-identity.json) records Build ID
`a0314627518435aa4e937dae6741de947c9cf864`, ELF SHA256
`98bda14cfcc4bfa181d73867f8713a51b70f0b834708bb2ed822a59f83c903f6`,
System.map SHA256
`127e70c3de6fca251731a5868ff90935e8fcb9c1ee345fd5aaf0b482463e1d07`,
and configuration SHA256
`31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483`.
The full build produced 6,901 modules; this is not a claim that all were installed
in the limited release namespace. Normal flags, commands and all warnings remain
in the retained logs. The kernel4 retention manifest is metadata evidence of the
prior witness; its large binaries/generated archive are not copied here.

[gs-config.json](guest/overlay/gs-config.json) retains the fresh linked witness
at `0xffffffff814fc32b`, bytes `65 48 8b 05 e5 2c f1 02`, targeting the full
`current_task` alias `0xffffffff8440f018`; `.data..percpu` begins at
`0xffffffff843f7000`. Each successful postboot has its own actual running-note,
Build ID, GS and protected-boot-file checks. These do not by themselves establish
generated-code execution, complete mitigation support or successful reader tests.

The failed learning proof refused
`install/stage-protected-before.json`, exactly 23,560,184 bytes. Its separately
reviewed 32 MiB proof retained the failure and completed the protection check;
there was no inference of pass from the partial first output. The receipt
collector's 16 MiB metadata bound is a different limit: it bounds inventory and
control output, while its per-file bound was 48 MiB and accepted this file.

The completed read-only collection contains 295 guest files / 88,762,743 raw
bytes. Caller limits were 10,240 files, 40,960 paths, 512 MiB total, 48 MiB per
file, 16 MiB metadata, 90 seconds per inventory and 180 seconds for copy. Exact
before/copy/after identities and hashes matched. No host-image/QEMU operation,
build, test or reboot was performed by the collector. Its guest SSH window
closed before the next boot. No later rwlock postboot/runtime outputs are included.

`guest-index.json` preserves the independent original guest path/identity/hash
map. `copy-index.json` maps every retained source-host file to its stored bytes.
Files larger than 1 MiB are losslessly gzip-compressed where useful; the index
records both raw and stored size/SHA256, and every gzip was decoded and compared
byte-for-byte. Small source-host operational contexts and exact helpers are
under `context/` and `helpers/`; actual executed guest controller/checks source
is retained under `guest/install/`. A helper copied later as context does not
rewrite an earlier failed invocation's result.

The duplicate uncompressed collector transport tar remains in the source-host
collection directory, rather than being duplicated in Git. Its SHA256 and copy
command/result are retained alongside all 295 validated payload members.
`collection-control/` preserves all other original collection metadata, including
the original collection and copy indexes; `launch/` records the actual bounded
invocation and return 0. `SHA256SUMS` covers every stored file except itself.
Raw logs/JSON/source copies may contain tabs or trailing whitespace; preserve
those raw-evidence exceptions. Packaging ran only on the source host and staged
or committed nothing.
