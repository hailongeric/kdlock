# Kernel3 installation and fresh boot — 2026-11-10 UTC

All four installation phases returned **0** for `7.0.0-38-kdrebuild3`, followed
by one ordinary `systemctl reboot` returning **0**. The frozen postboot helper
returned **0** and saved phase `POSTBOOT_IDENTITY_VERIFIED` on fresh boot
`bceee25d-a189-4f51-89fa-0e31322b70e6`, taint 0.
This record establishes installation, protection checks and boot identity.
It does not establish fixture execution, returned protected JIT episodes,
recursive delegation, deferred physical release or performance. Later live
results have their own identity and receipts.

The linked inputs are the [kernel3 build](../kernel-build3-20261110/README.md):
core `1b50e37382d2c739b16953027c47d7e2388562f0`, source snapshot
`69ba6b030c1eb7e5f1c3f9461b70f5fef6791309`, 66 exact package inputs and 27 C
plus three assembly core units. Source and output remained separate under
`/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/{source,build}`.
The old kernel2 witness was retained independently before its inactive output
tree was reused; its manifest and copy evidence are in the build record.
The earlier [single intermediate retention](../build-space-retention-20261110/README.md)
is a separate operation and is not duplicated here.

| Phase | Actual result | Completion UTC | Outer controller seconds |
| --- | --- | --- | ---: |
| Stage | `COMPLETE`, rc0 | 20:15:38.206284 | 207.875 |
| Check | `COMPLETE`, rc0 | 20:16:43.550630 | 30.209 |
| Install | `COMPLETE`, rc0 | 20:20:32.344261 | 87.343 |
| Arm | `COMPLETE`, rc0 | 20:23:09.770730 | 27.554 |

The raw phase journals, command results, completion records and logs are under
`install/`. Stage and check outer command/return/stdout records were retained in
the guest receipt directory; install and arm outer records are under
`controller/`. Each dependent phase followed actual successful completion.
No phase was automatically retried. The helpers never loaded a module or
rebooted during these four phases.

The fresh stage was
`install-stage-kdrebuild3-1b50e373-v1`, with receipts in
`receipts/install-kdrebuild3-1b50e373-v1`. Staging used ordinary
`modules_install` with explicit `INSTALL_MOD_PATH`, `KERNELRELEASE` and
`INSTALL_MOD_STRIP=1`. It returned 0 in 155.605 seconds. The staged and installed
inventories contain exactly 6,901 `.ko` files with matching bytes, modes and
relative names, expected kernel3 vermagic and no checked DWARF sections.
There are 6,827 signed and 74 unsigned modules under the existing vendor policy;
unsigned alone was not a new rejection. `CONFIG_MODULE_COMPRESS_ZSTD=y` did not
mean compression was enabled for this installation; `COMPRESS_ALL` remained off.

The check budget retained the unchanged 1 GiB root reserve and 256 MiB initrd
allowance. It required 2,061,741,724 bytes against 2,101,727,232 available,
leaving 39,985,508 bytes. The controller rechecked immediately before copying:
2,101,694,464 bytes were available against the same requirement. Staged module
allocation was 691,503,104 bytes; the three copied boot inputs totaled
28,061,340 bytes. The actual initrd was 103,176,800 bytes. Root free space before
the reboot was 1,272,942,592 bytes, above the retained reserve.

`depmod`, `update-initramfs`, `update-grub` and all dependency checks returned 0.
The four root-driver checks (`virtio_pci`, `virtio_scsi`, `sd_mod`, `ext4`) and
the installed network dependency check reported built-in providers in this
configuration. The helper required any non-built-in root dependencies to be
in the initrd; it did not impose a network-initrd requirement for local ext4 root.

The complete protected pre-change snapshot is retained losslessly as
[install/stage-protected-before.json.gz](install/stage-protected-before.json.gz):
95,760 records across 23 existing module roots, including normal, legacy
recovery and installed candidate1/kernel2 files. Its raw SHA256 is
`4a3cb0f0242a92191eb72314702c042394291aea4b77313a98c0f3109e823c0d`.
Both post-install and pre-arm checks returned `unchanged: true` for all 95,760
records. These compare recorded paths, contents, modes and link targets; they
do not claim every inode or timestamp was an acceptance condition.

| Installed boot file | Bytes | SHA256 |
| --- | ---: | --- |
| `vmlinuz-7.0.0-38-kdrebuild3` | 17,187,328 | `582e7b7b7be00fe9ba6f373ed25ad27864a13949c0bff1d7fa466271d479733e` |
| `System.map-7.0.0-38-kdrebuild3` | 10,565,464 | `e7723218a35731108e2a1ae4ea1b33942fe7c1e44cc6671bc9345f08222c4d22` |
| `config-7.0.0-38-kdrebuild3` | 308,548 | `31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483` |
| `initrd.img-7.0.0-38-kdrebuild3` | 103,176,800 | `30edb5699e61260afd54efedf1f23f0ab5ba77248ecdd55895b923b54eae045c` |

The advanced GRUB one-shot entry named only kernel3. Arming preserved the
normal `7.0.0-38-kdlock1` default, all other environment fields and configuration
SHA256 `17c2ab033f0f294e903ebf53b4a1c3aac5fe88ed8ee4df19aa3c0661937a6fbd`.
Fresh pre-reboot idle, reserve, arm completion and exact selection were checked
again. The pre-reboot request/argv and result were saved before and after the
single ordinary `systemctl reboot`; its actual return was 0 in 0.005 seconds.
There was no force, reset or reboot retry.

The fresh QEMU receipt observed the real `kdlock-builddisk-clean-20261031`
snapshot present on all three disks, 9,605,451,776 host bytes available and serial
offset 141,667,378 before boot. Its raw SHA256 is
`d47477c6dc0ab28cddcd3af96c2cd1f9ca7e39a46abef51ea4739808548c3387`.
The read-only reconnect's first attempt returned 0 and observed the fresh
kernel3 boot. Pre-reboot state was normal boot
`ca0b717b-c19d-4027-b598-6a1cf58b93d2`, taint 0.

The frozen persisted postboot helper has SHA256
`e89de9585165702af7e35d6fd456fa6aaa0bd48166cea6b54158a51d33743495`.
Its actual outer controller returned 0 in 3.827 seconds; the independent saved
[postboot/result.json.gz](postboot/result.json.gz) has SHA256
`3d887623b4fc41467e9aa9422b1f3bc396067fd5a5f99bb2c65c757a4c9f1a0b`.
It matches the running GNU Build ID
`264a4ef8e55952e5d9ceccf93f65f25f05a50c1f` to actual ELF SHA256
`c099d66949ba99bc0ec200ef1570cc2917e7b8a3eb0acdd97811333247d2a43d`.
The complete running notes, ELF notes/sections/symbols, 64 CPU flag rows,
mitigation observations, `nokaslr`, module snapshot and boot logs are retained.
Public observations are not a replacement for the runtime call-depth guard or
proof of complete handwritten/generated mitigation coverage.

The actual new ELF establishes full
`current_task == const_current_task == 0xffffffff8440f018` and per-CPU section/start
`0xffffffff843f7000`; the new values were checked rather than assumed from kernel2.
[postboot/gs-proof.json](postboot/gs-proof.json) has SHA256
`00c8abe89e71c4cb04ce2cf49401ba2cb6873f5a3ec12d3869ec4ccdaaede6b4`.
The helper separately rehashed the eight exact normal/recovery boot files and
confirmed their module namespaces remain present. It did not repeat the whole
module-content inventory after boot. The one-shot entry was consumed, with
the exact normal default and GRUB configuration unchanged. These taint/module
observations belong to this pre-fixture checkpoint, not a later live run.

`overlay/` retains the executed helper bytes and actual VM SHA/AST receipt.
`controller/reviewed-ops-recipe.md` is the earlier frozen preparation recipe;
its pending-pin prose is historical. The executed postboot helper contains the
actual filled kernel3 pins. All helper return codes and commands used here have
raw controller records; no transcript-only AST or outer return was invented.

[remote-index.json](remote-index.json) records 126 immutable VM receipt files,
46,663,096 raw bytes. [copy-index.json](copy-index.json) verifies all 138 retained
copies, including 12 source-host controller artifacts, against their exact raw
and stored sizes/hashes. Large files use lossless gzip; `SHA256SUMS` covers the
stored evidence. Collection used only immutable receipt reads/SCP and source-host
compression. It ran no guest helper, process check, build, test, module operation
or boot action during the live window. The full T01–T56 matrix and performance
evaluation are not established by this record.
