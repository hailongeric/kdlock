# VM disk cleanup, October 22, 2026

The user requested removal of old, expired files from the original VM because
its root disk was 99% full. Run `vm-disk-cleanup-20261022` removed 97,025 reviewed
obsolete build files, reclaiming 10,752,356,352 allocated bytes (10.01 GiB).
Root usage fell to **89%**, with **11 GiB available**. The net increase in
available space was 10,695,970,816 bytes (9.96 GiB), after retaining the cleanup
inventories and normal filesystem activity.

| Filesystem | Before | After |
| --- | --- | --- |
| `/dev/sda1`, mounted at `/` | 99%; 1,090,732,032 bytes available | 89%; 11,786,702,848 bytes available |
| `/dev/sdb`, mounted at `/mnt/kdlock-builds` | 88%; approximately 3.6 GiB available | Unchanged; excluded from deletion |

## Deletion scope

Only regular, singly linked files dated before October 1, 2026 were eligible,
under these four exact directories:

- `/root/linux-6.1.159`
- `/root/linux-6.1.159-kdstatic1`
- `/root/linux-6.1.159-kdstatic2`
- `/root/linux-6.1.159-kdclobber1`

| Category | Files | Allocated bytes removed |
| --- | ---: | ---: |
| Original `6.1.159` build modules with complete retained installed copies | 5,673 | 5,495,554,048 |
| Object command sidecars whose corresponding object was already absent | 91,344 | 4,504,702,976 |
| Old `.tmp_vmlinux.kallsyms1/2` linker intermediates | 8 | 752,099,328 |

For every removed module, its entire original byte sequence matched the prefix
of the corresponding file under `/lib/modules/6.1.159/kernel/`; only a bounded
appended module signature could differ. The retained installed file's SHA256
was checked again after deletion. Other historical module build outputs were
retained; a stripped installed module was not accepted as an exact copy.

The deletion manifest was copied to the source host and reviewed before use.
Its SHA256 is
`33630cfc3e5a4aaab8c4eea10e9cd548f40b061d191dde52afe2eb9bed11ec8e`.
Every selected path, file identity and content hash was rechecked before
deletion. This was a one-time cleanup, not an automatic expiry policy.

## Preservation and verification

The VM remained on recovery kernel `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, boot
`d4980f92-14c5-4bed-9749-beac916e76d3`. No reboot, kernel build, module load,
workload run or process termination was performed.

All seven captured source/configuration/build baselines passed before and
after deletion: original `6.1.159`, `kdstatic1`, `kdstatic2`, `kdclobber1`,
recovery `kdclobber2`, and both `kdmm1/2` experiments. All 619 regular boot files
had unchanged hashes, all 5,673 retained module hashes matched, and the loaded
module set remained the same 73 entries. The source host's offline audit matched
all 97,025 deletion records to the reviewed manifest.

The recovery and MM source/build trees, generated headers, baseline artifacts,
kernel images, installed modules, source checkout, frozen experiments, archives
and logs were preserved. No evidence directory or `/root/host_fs` was cleared.
This housekeeping validation does not extend correctness or performance claims.
The removed historical intermediate outputs would require restoration or
regeneration before reusing those old build outputs for installation.

## Receipts and working checks

The compact [result](cleanup-result.json) records byte counts, checks and artifact
hashes. Guest receipts remain at
`/root/kdlock-maintenance/disk-cleanup-20261022/` (`before.json`, `plan.json`,
`deleted.jsonl`, `after.json`). The source-host
[raw directory](../../raw/tests/vm-disk-cleanup-20261022/) contains the exact
cleanup script, pre-deletion archive, completed archive and offline audit result.
The completed archive SHA256 is
`3f64bd09146b65e8ae715f878aff7899839cb6a4ba7c279695515fa57ed70418`.

Check current space without changing the VM:

```sh
ssh -o BatchMode=yes -o ConnectTimeout=10 -p 2222 root@10.176.26.71 \
  'df -hT / /mnt/kdlock-builds'
```

The existing kernel identity command in [VM operations](../../../../../docs/operations/VM.md#kernel-identity)
remains valid. Cleanup did not modify the current recovery kernel's build tree.
