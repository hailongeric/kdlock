# Kernel9 writer-cohort correction: build preparation

These are frozen source-only build inputs. No driver, project import, compiler,
test or VM command was executed while preparing them. The root agent separately
reviews and authorizes the actual bounded VM build.

`package/` and `package.tar` contain the exact same 78 regular member names as
the kernel8 core package, taken from Git commit
`6e486ecec398111fb5d5e30ffc76495f32f557b7`. Only `kernel/mutex.c` differs from
`0d42063ead37dc8fc1631fa56c8348890ede9c5f`; its new SHA-256 is
`014b4a9cfb4609eb8a1e49cc14e715302b13060dc641519a7e68b22a7e515564`.
All 78 hashes independently agree with the private-rwsem preparation's core
manifest. The export receipt records the selected commit and actual worktree
HEAD/status separately; concurrent evidence commits do not select new source.

| Frozen input | Bytes | SHA-256 |
| --- | ---: | --- |
| `package.tar` | 788,480 | `3d278e24eec0b1b25a6cdcd01f9f3974f8aaa874db826d46333f802876d37d50` |
| `package.json` | 7,763 | `4140d5a20a8e33d752d6cb00ebda314e447e28b014ae9c4c339500df862b7d07` |
| `build.py` | 30,668 | `0535aa78d56e019b11de988e217416110176645fb9f25fce4dca9427881e0d57` |
| `plan.json` | 23,909 | `0df23f4f69069b9b8dfcff3c58b69df9b4b6904f7e2abff3073ee9dd71215408` |

The new target is
`/mnt/kdlock-builds2/kdlock-main-kernel9-6e486ece-01/{source,build}`,
with release `7.0.0-38-kdrebuild9`. Input files belong in the separate
`/mnt/kdlock-builds2/kdlock-main-kernel9-input-6e486ece-01` leaf. The driver takes
explicit `--plan-json`, `--plan-sha256`, `--recovery-json` and
`--recovery-sha256` arguments. All seven paths in `plan.provenance_files` must
also be staged unchanged beneath that input leaf.

The build driver requires the recovered ordinary boot
`f1442f01-e060-46fa-a480-da508d7ce8a9`, `7.0.0-38-kdlock1`, taint zero, the exact
54 normal module names and idle task/device checks. Fresh host recovery bytes
must identify the existing QEMU process and three backing images, no block job,
and both complete all-disk tags `kdlock-builddisk-clean-20261031` and
`kd-mm-step-failed-20261111-01`. The failed experiment remains preserved; reset
recovery does not prove its original episode drained.

The driver clones the preserved, already integrated kernel8 source with
`cp -a --reflink=auto`, checks its package 78, integration 8 and native-MM 11
hashes, and verifies that the clone's package files are not hardlinks to the
preserved source. It replaces only the cloned `kernel/mutex.c`. It does not
reapply the installer. A separate output directory receives the unchanged
configuration seed `31d9701e...`. Kernel8's 16 outputs, 78 source files,
integration/native bodies, authenticated normal source/manifest and normal
boot/default files are checked before and after.

Commands retain the earlier ordinary `make -C SOURCE O=BUILD
KERNELRELEASE=7.0.0-38-kdrebuild9 V=1 -j16` form. The build sequence is
`olddefconfig`, the single changed `kernel/kdlock/kernel/mutex.o` target,
`bzImage`, then only `fs/nls/nls_iso8859-1.ko`. The previous native NLS handling
is retained: complete vmlinux export rows must agree, the removed temporary
module order is replaced with the explicit one-module order, and the NLS
vermagic/dependency closure is checked. Linked ELF/GS/return-symbol identity and
the two corrected mutex functions' disassembly are saved. Linked metadata does
not establish a running-kernel GS proof.

The initial output and host floor is 40 GiB. The measured preserved seed source
is 1,824,907,264 bytes and kernel8 output is 6,361,751,552 bytes; this narrower
scope builds one kernel and one NLS module, with no fixture/client or other
module builds. The initial floor is an admission margin, not a measured maximum
disk-use proof. Runtime observation retains an 8 GiB output floor, 1 GiB root
floor, 64 MiB per-command log allowance and a total 1,800-second deadline.
Timeout, low space or excessive output retains the original child/session and
logs without signals or cleanup. It establishes no drain.

The driver records tool identities, exact command arrays, PIDs/sessions,
return codes, complete log hashes, diagnostics, preserved bytes and final idle
identity. It rejects build and Python environment overrides. It performs no
installation, module load, reboot or behavioral test. Existing rwsem mechanism
validation belongs to a separate later command and receipt against the actual
corrected linked kernel.

`SHA256SUMS` covers all files here except itself. The source-host exporter is
`/tmp/kdlock-kernel9-prepare-20261111.py`; it reads exact Git blobs and performs
standard-library file/tar/hash work only. The build driver and all frozen plan,
package and provenance bytes must remain unchanged after launch.
