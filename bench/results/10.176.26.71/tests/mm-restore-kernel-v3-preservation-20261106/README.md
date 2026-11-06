# Current-generation preservation before the builtin restore rebuild

The current scope5 v3 generation was fully preserved and verified on 380G10
before amending its existing VM source/build tree. This is preservation evidence,
not a kernel build, live mmap1 result or performance result.

| Identity | Value |
| --- | --- |
| Kernel component | `1ab7124abb6140752c1f0bb6e862144d426a3875` |
| Release | `7.0.0-38-kdscope5` |
| Build ID | `5f2fce72a33480f6e79a79b374b21a0db377ecd1` |
| Composition SHA256 | `906a7089f001d93256fc7b36a7fe9c739fde151b9452f4e26aeb2b35e91f1777` |
| Inventory SHA256 | `af19e67b1fda6ea63a435bd592974d635cbcdc806a718c4d63239f880160012a` |
| Entries / logical content | 226,905 / 36,131,409,510 bytes |
| Archive bytes | 7,608,849,525 |
| Archive SHA256 | `3540f91006463beca4af9680b7e1e9cb0ae964420cac94cf4dca1c6b77a875d3` |
| Complete-member verification SHA256 | `d4caf51ac53e011f26bb50811ea4c966405c811f25970c9628dbe8861b71bae7` |

The full inventory matched both before and after streaming. Sender and receiver
computed the same compressed length/hash. Tar and zstd exited successfully with
empty recorded process groups. The source-host verifier checked the exact member
set, contents, types, mode/ownership, nanosecond timestamps, extended attributes,
symbolic links and hardlink relationships, then consumed the entire compressed
stream. Only afterward was the partial file renamed to its retained final name.

The archive and full receipts are in the main 380G10 checkout at
`bench/results/10.176.26.71/raw/tests/mm-restore-kernel-v3-preservation-20261106/`.
The archive filename is `linux-7.0.0-38-kdscope5-v3.tar.zst`. The guest evidence
directory has the same suffix beneath
`/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/`.
No complete archive was staged on the guest or QEMU host.

The correction is a separate kernel component,
`9a5d606aee0249d0e566a1c9667375eb038bc9cd`, based directly on the preserved
component. Only the bodies of `kd_rwsem_provider_resume_instruction()` and
`kd_rwsem_provider_resume()` change, plus a design note. Its VM source snapshot
shares 6,745 unchanged files and creates two new file inodes. The parent frozen
bytes and canonical shared project remained unchanged. Build and runtime
validation are separate stages and require their own receipts.

For installation headroom, one inactive rotated log, `/var/log/kern.log.1`, was
preserved as `/var/log/kern.log.1.preserved-20261107.gz`. Complete decompressed
length/hash verification preceded removal of its original. Original length was
654,879,356 bytes; retained gzip length is 34,078,778 bytes, SHA256
`3886e703f1d90235f8a1d6d77342d39b70c4a5da088eb499e31fdbf60adb9cbe`.
Available root space increased by 620,797,952 bytes to 3,845,509,120 bytes.
Current logs, installed kernels and all source/build/module trees were retained.
The actual new installation allowance still must be checked after the build.
