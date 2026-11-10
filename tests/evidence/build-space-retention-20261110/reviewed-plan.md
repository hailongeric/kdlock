# Single intermediate retention and cleanup plan

Prepared for root review only; no copy or unlink has run. Existing user
authorization covers this unused kernel output. The controller must approve
the concrete write phase before dispatch.

Source (the sole unlink target):

`/root/kdlock-build-output/linux-7.0.0-38-kdscope1/.tmp_vmlinux2`

Fresh destination/receipt directory:

`/mnt/kdlock-builds2/root-tmp-retention-kdscope1-20261111-01`

Run an exact one-file helper as root with a 180-second outer timeout after the
normal guest is idle. Reject an existing destination directory; do not resume,
overwrite, remove partial output, or broaden the selection on failure.

## Pinned source

The source is a regular single-link file, device 2049, inode 357757, mode 0755,
uid/gid 0/0, logical size 131727800 bytes, allocated size 118382592 bytes,
mtime_ns 1793303232077713354, ctime_ns 1793303232078618728, SHA256
`66a22524252fb3c33d202879b022be9a5f616fc4b55eca7aba82996375b1da29`.

The read-only refresh reconfirmed all these fields and no external fd/maps or
command-path users. Running identity was normal 7.0.0-38-kdlock1, boot
ca0b717b-c19d-4027-b598-6a1cf58b93d2, taint 0. Recheck them at dispatch.

`scripts/link-vmlinux.sh` in the inactive Linux7 source creates this as its
second kallsyms intermediate before separately linking final vmlinux. The
completed output release is 7.0.0-38-kdscope1. Final vmlinux SHA256
`ea8b44b8f9cc9256c93228adfcb30f5535a1c841a67496b96946f24080240a42`
matches the retained kernel-baseline manifest; the final bzImage and System.map
also match installed kdscope1 files. None of those final artifacts is selected.

## Ordered execution

1. Record command/helper identity, current release/boot/taint, module/device
   absence, process activity, fd/maps/path references, destination free space,
   source identity and SHA256. Refuse builds, fixture/control/source workers or
   a source identity change. Require canonical non-symlink paths and retained
   stable parent-directory identity through completion.
2. Record before hashes and metadata of final vmlinux, bzImage, System.map,
   .config and Module.symvers in the old output; installed kdscope1 vmlinuz and
   System.map; and its retained baseline manifest. Also record root/data2 df.
   Leave all other outputs, source, installed files and legacy ELF cache alone.
3. Exclusively create the fresh data2 directory and `journal.jsonl`; fsync the
   directory and parent. Journal phases with fsync after each record. Copy
   source bytes into an exclusively created `tmp_vmlinux2.retained` on data2,
   through a retained source fd. Do not hardlink, reflink or rename the source.
   Preserve mode/uid/gid/mtime; record destination's actual dev/inode/ctime and
   allocation rather than claiming those equal the original.
4. Fsync/close the destination payload, reopen it independently, rehash all
   bytes and verify logical size, nlink 1, original metadata and expected hash;
   require a distinct source/destination identity. Write/fsync
   `retained-verified.json` containing both complete identities and hashes.
5. Immediately before unlink, recheck guest idle, no external source fd/maps
   users, pinned parent/source identity, all source bytes and unchanged protected
   artifacts. Compare the opened source fd and the directory entry. A mismatch
   stops with the original intact. The helper's own source fd is the one
   explicitly permitted open reference.
6. Execute exactly `os.unlink('.tmp_vmlinux2', dir_fd=source_parent_fd)` once.
   Fsync the source parent; close the source fd so its blocks can be freed.
   Do not invoke any other unlink/rmtree, trim, snapshot or cleanup operation.
7. Verify source absence, rehash the retained payload, verify protected before
   and after identities/hashes, and record actual df/allocated-byte changes.
   Write/fsync `result.json` with COMPLETE only after all checks pass. Preserve
   journal, retained payload and partial-failure receipts on any exception.

The expected root allocation reclaimed is 118382592 bytes, covering the prior
77908468-byte estimate only. The next kernel's actual module/boot staging budget
must be recomputed; this plan does not weaken its existing reserves.
