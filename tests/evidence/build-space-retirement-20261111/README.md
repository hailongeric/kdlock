# Historical build-space retirement and read-only image inventory

These are separate completed storage operations and read-only observations from
November 11, 2026. This directory was assembled using source-host byte copies
only. Packaging performed no guest/QEMU access, build, test, module action or
snapshot change. The raw failures and their limits remain explicit.

| Operation | Actual result | Primary receipt |
| --- | --- | --- |
| User-approved permanent removal of the exact 25 historical scope2/3/4 objects | COMPLETE, command return 0; all 25 absent, no exceptions | [Deletion summary](deletion/summary.json), [raw pre/post records](deletion/raw.jsonl) |
| Separately approved removal of four dangling module build/source links | Preflight 0, unlink 0, COMPLETE; exact link targets retained before unlink | [Link summary](links/summary.json), [recovery record](links/recovery.json) |
| Guest block mapping and live QEMU image metadata | Guest query 0; ordinary read-only `qemu-img info` returned 1 because the live image lock was refused | [Image summary](image/summary.json), [complete host output](image/host-stdout.jsonl) |
| Snapshot inventory | Saved-listing and source-record analysis only; no new remote query, restore or deletion | [Inventory](image/snapshot-inventory.json), [printed listing](image/snapshot-listing.txt) |

The deletion was explicitly approved after disclosure that no equivalent complete
recovery copy had been verified. It removed exactly 68,189,966,336 allocated bytes
(63.506855 GiB) from `/mnt/kdlock-builds2`: full historical `kdscope2`, `kdscope3`
and `kdscope4` trees and their listed private recipes, preparation/staging roots
and archive/manifest files. The guest's free and available bytes both increased
by that exact amount, from 7,170,695,168 available bytes to 75,360,661,504.
The complete fixed allowlist, each pre-lstat/allocation check and each absence
result are retained in the guest helper and raw receipt. This was not a wildcard
cleanup, and `kdscope2`/`3`/`4` must not be confused with current `kdrebuild` kernels.

Both full process scans recorded 613 PIDs and 461 descriptors, no target
references, no busy build/worker entries and no access errors. All 196 recorded
protected metadata/hash identities were unchanged. This is the captured
protection scope, not a full byte hash of every protected tree. The normal and
legacy trees, scope5, current main/kernel5, current source/work/fixture/history
roots, venv, shared evidence, installed boot/module namespaces and GRUB files
were outside the deletion batch. No host qcow2 reclamation was measured or
claimed; the guest free-space increase is the measured result.

The first operation deliberately left four now-dangling links. The separately
approved follow-up removed only `/lib/modules/7.0.0-38-kdscope2/build`, its
`source` link, and the `build` links for `kdscope3` and `kdscope4`. Preflight
recorded their literal destinations, metadata, parent/sibling state and 720
boot/GRUB protection records. The source-host recovery record was written and
read back before unlink; the helper compared exact current links against it.
All four links then became absent, parents/siblings and all 720 boot/GRUB records
were preserved, and no other unlink occurred. Parent directory mtime/ctime
changes from unlink are expected and recorded. The recovery record can describe
recreation of those links; it does not restore their deleted target trees.

Both cleanup operations ended on boot
`9336b735-78f0-4f9c-9d9e-f04677f8d6bc`, release
`7.0.0-38-kdrebuild5`, taint 12288, with no fixture devices/workers. Those are
recorded end states, not a claim about later rwsem experiments running during
source-host packaging.

The earlier read-only image inspection independently mapped guest `/dev/sda`
(serial `drive_system`) to QEMU PID 257489's open
`/home/eric/vm/qemu-disks/ubuntu22.04.img`, format qcow2. The guest disk was
109,735,575,552 bytes (102.199219 GiB), while its root filesystem was
106,156,367,872 bytes (98.865822 GiB). Host file apparent length was
534,681,157,632 bytes (497.960632 GiB); `st_blocks * 512` allocation was
323,341,860,864 bytes (301.135574 GiB). These measure different things. No
exclusive per-snapshot storage accounting was performed. Normal `qemu-img info
--output=json --backing-chain` refused the shared write lock; inspection stopped
without `-U`, force-share, retry or another access route. Header virtual size and
backing dependencies therefore remain unverified. The refusal is inside the
saved host stdout JSON record; host SSH stderr itself was empty.

The saved HMP listing contains one complete current three-disk recovery set,
`kdlock-builddisk-clean-20261031` (printed VM size 23.5 GiB), and four earlier
partial sets on system/data1: `legacy-kdclobber2-20261027` (23.4 GiB),
`linux70-kdlock1-clean-20261027` (23.6 GiB),
`linux70-kdmm1-native-clean-20261027` (23.6 GiB), and
`kdlock-roleswap-failure-20261029` (22.9 GiB). Partial/non-loadable is relative
to today's attached three-disk topology; it does not by itself establish
corruption or lack of historical value. HMP dates are copied exactly and their
timezone was not established. Its VM-size column is not guest disk usage or an
exclusive reclaimable byte count. The current kernel5 argument source explicitly
selects the October31 tag for its recovery gate. No snapshot was deleted.

[copy-index.json](copy-index.json) records every original source-host path,
identity, raw size/hash and stored size/hash; all copies are byte-exact and
uncompressed. [collection.json](collection.json) records the packaging context.
`context/` preserves the historical master guides/receipts used for snapshot
purposes and the actual kernel5 argument source; these are historical source
copies, not new maintained instructions or evidence of a restore drill. Their
original links/absolute paths and the raw helpers are preserved verbatim.

`SHA256SUMS` covers every retained file except itself, including this README and
the copy index. `links/SHA256SUMS` is the original nested checksum receipt.
Raw HMP text, JSON, command logs and copied historical sources may contain tabs,
trailing whitespace or terminal escape sequences; retain those bytes. Whitespace
diagnostics in copied material are raw-evidence exceptions, not authored prose
changes. No files were staged or committed by this packaging operation.
