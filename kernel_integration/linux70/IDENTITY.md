# Linux 7 kernel identity

The schema-2 identity is for `linux=7.0.0-38.38`, built as
`7.0.0-38-kdlock1`. It keeps these two directories distinct:

| Purpose | Canonical guest path |
| --- | --- |
| Development source | `/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/source` |
| Build output and external-module KDIR | `/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build` |
| Captured identity | `/root/kdlock-kernel-baselines/linux70-kdlock1-20261027` |

After installing and booting that exact kernel, run in the VM:

```sh
python3 kernel_integration/linux70/capture.py --preempt lazy
python3 kernel_integration/linux70/verify.py --running
```

If the source includes the optional mmap overlay, also pass
`--mmap-prepare /absolute/path/to/prepare.json` to capture, including when
`CONFIG_KDLOCK_MMAP` is disabled. The preparation receipt must describe the
actual source outputs and current generator inputs. Capture requires a new
output directory and does not replace an existing identity. A failed capture
is not a pass; resolve its reported mismatch before using the bundle.

The capture hashes the three exact source-package archives against their
authenticated Ubuntu checksums and preserves the previously verified source
acquisition receipt. Subsequent checks bind that receipt and those identities;
they do not repeat the archive signature verification or a complete upstream
source audit. The named source scope includes the original Makefile/changelog,
all core patch destinations, and, when present, every mmap preparation output
and its recorded untouched MM bodies. All mmap generator inputs are copied
into the bundle. This records the prepared implementation without claiming
that every other source file was inspected.

The verifier checks the canonical source/build roots and generated O= Makefile
binding, the complete configuration, generated release/version headers,
`Module.symvers`, `System.map`, `vmlinux`, and `bzImage`. The release must be
`7.0.0-38-kdlock1`; the source's 7.0.14 version code remains `458766`.
Installed boot image, config, System.map and initrd hashes are required. The
installed image/config/System.map must equal their build counterparts, and
`/lib/modules/<release>/build` must point to the captured build directory.
If an installed `source` link exists, its target is also captured and checked;
the generated O= Makefile always binds the separate source directory.
This does not inventory every installed module or establish module correctness.

Running verification additionally checks uname and the GNU Build ID against
the built vmlinux. It compares the exact captured command line and active
dynamic-preemption control, requires `nokaslr` and `nopvspin`, and supports an
explicitly captured `lazy` or `voluntary` policy. Only this complete live check
returns `runtime_policy_verified: true`. An identity pass does not establish
recovery readiness, CPU frequency, topology, ownership correctness, returned
JIT execution, or performance qualification.

The shared benchmark helper dispatches schema 1 to the unchanged legacy
verifier and schema 2 to this verifier. For schema 2, `--kernel-source` names
the **build directory**, because runners use it as KDIR. Code that copies
original kernel implementations uses `kernel_identity.source_directory()` to
locate the separately bound source. Result capture preserves `manifest.json`
and every `bundle_files` entry, then verifies the retained copy again.
