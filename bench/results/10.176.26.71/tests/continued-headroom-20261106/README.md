# Continued log preservation and build headroom

This continues the approved November 6 storage work. No source/build tree,
installed kernel, module staging tree, VM image or recovery snapshot was removed.
The normal VM remained on `7.0.0-38-kdlock1`, boot
`4ff57d48-bc4c-43bd-9946-b16e0db3d4da`. No benchmark or corrected-kernel build
was performed by these cleanup operations.

| Operation | Retained evidence | Actual available-space gain |
| --- | --- | ---: |
| Compress 16 inactive host serial copies | Full gzip contents, decompressed length/hash and original metadata | Host 1,448,267,776 B |
| Remove 36 old host archive duplicates | Matching complete copies on 380G10, verified again before removal | Host 925,724,672 B |
| Compress 59 inactive guest logs/event records | Full gzip contents, decompressed length/hash and original metadata | Guest build disk 2: 8,665,710,592 B |
| Move 33 old compressed guest logs to 380G10 | Exact compressed and decompressed hashes, complete retained copies | Guest build disk 2: 1,268,899,840 B |

The last operation retained seven earlier compressed logs and 26 of the newly
compressed files. It therefore replaces those 26 guest gzip locations with
verified source-workspace locations; it is not a second copy on the guest.
Source-workspace archive names are their compressed SHA256 values. Full path
mapping is in `archive-transfer-verified.json`.

The final observed available space was 17,720,115,200 B on guest build disk 2
and 9,621,184,512 B on the QEMU host. Guest unlinks did not reclaim measured host
space. Host reserved blocks were excluded. Cleanup stopped after the guest
exceeded the unchanged 16 GiB guard plus a 512 MiB working margin. This is a
capacity observation, not a measured build peak or permission to lower guards.

Four unmatched host archives remain. Current first-failure records, the active
console, frozen inputs, old builds and recovery artifacts remain. No result was
reclassified as passing. The current normal idle state does not establish
retirement of the earlier failed workload.

The raw records are under
`bench/results/10.176.26.71/raw/tests/continued-headroom-20261106/receipts/` in
both the candidate and main source checkouts. `copied-records.json` binds their
exact sizes/hashes. Full compressed copies are in the sibling `archives/`
directory of the main 380G10 checkout. The earlier pass remains separately
reported in `tests/headroom-cleanup-20261106/README.md`.
