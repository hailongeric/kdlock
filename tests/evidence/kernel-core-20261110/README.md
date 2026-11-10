# Kernel core and lifecycle-hook compilation, 2026-11-10

The exact-target installer applied and verified the selected integration, and
compilation of all 29 kdlock core objects (26 C units and three assembly entries)
plus `kernel/fork.o` and `kernel/exit.o` returned 0 in the designated VM. The
core-compilation log has no warning or error diagnostics. Configuration emitted
one AppArmor Kconfig warning, retained below. This receipt establishes target
application, configuration and those compilation outputs only.

A separate parent-owned full-kernel build was running when these receipts were
collected. Its outcome is outside this record. This record establishes no
complete-kernel link, installation, boot, loaded-image publication/ACK, generated
JIT execution, ordinary mutex execution, performance or T01–T56 acceptance result.
The [12 focused pipeline checks](../runtime-pipeline-20261110/README.md) are
separate evidence on the same source snapshot.

## Exact inputs

The kdlock package is committed source
`c6becf81987ae29a97000a641d76a0ff2e300860`. Its frozen Git archive and complete
99-file manifest are retained with the focused checks. Archive SHA256:
`5be656f42ea85526e44d292b6929dcd6ee826e395e36dd5b91a50e25750b3a52`.
The copied build-input package has 64 hash-pinned files and fingerprint
`c23f80daf6f86ee219ae6d8ecdb5a29b5af2c96dba52b69c203a8a3842796b43`.
Those files all matched their pins at independent readback.

The kernel source derives from Ubuntu `linux=7.0.0-38.38` with the protected
`kdlock1` source changes already present; it is not described as pristine vendor
source. Its schema-2 baseline bundle is
`/root/kdlock-kernel-baselines/linux70-kdlock1-20261027`:

- Full baseline manifest SHA256:
  `1d65f61df1be4ab03e358b456d67165d5c9bdc3edd50cf8f15ad651281feca17`.
- Source-acquisition receipt SHA256:
  `5c5e8a574cf8affb7aedd66e9f609ca006041c1cde0d3fc4e086a4f9849f545a`.
- Baseline build ID: `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`.
- Original source and output:
  `/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/{source,build}`.
- Named target-input fingerprint before integration:
  `e239a781b049f12fc247e298ff02551b0b35246eaf7fba58dba1fd4db5f64e90`.
  Its scope is the top Makefile and five integration files, not a full vendor-tree
  audit. The separate package fingerprint covers the 64 copied build inputs.

The isolated candidate root is
`/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f`, with distinct `source/`
and `build/` directories. Preparation copied the source and package and planned
the exact integration during 14:34:59–14:35:16 UTC. The installer was supplied the
original source/output and the frozen package input as protected trees. Independent
readback still matched all six named original source hashes and four protected
build hashes (`.config`, `Module.symvers`, `System.map` and `bzImage`). This is the
stated checked scope, not a hash audit of every file in those trees.

## Application and the raw argv-report alias error

The retained application journal records PREPARED, STAGED, five exact REPLACED
entries and COMMITTED. `apply.log` contains the actual receipt directory;
`verify.log` reports that exact applied source/config/package bytes match the
complete receipt. All five applied candidate files still matched the manifest
at independent readback. The planned patch and applied patch are retained.

The controller reused a mutable Python argv list before writing its summary:
`preparation.json` calls its recorded list `inspect_argv` but that list's mode
has become `plan`; `configure-core-result.json` names its first step `apply`
but that recorded argv mode has become `verify`. These are report alias errors,
not corrected raw command records. The unedited files remain here. They must
not be cited as literal argv evidence for the earlier inspect/apply invocation.
The actual inspect output, plan, application journal/manifest and separate
apply/verify logs retain the corresponding operation evidence; the journal's
COMMITTED phase and exact after-file readback establish application.

The installer hash in the manifest is
`83983bed0868855fabb83ca0fd66f23e8120bdd6196ec621ef951464466f7086`.
Full before/after source backups remain under the original VM receipt directory;
they are not duplicated here. Their exact hashes and the integration recipe
are retained in `integration-application/manifest.json` and the patch.

## Configuration and compilation

Configuration started from SHA256
`91b6b86611ee18b4c3ef093c9d95cbd135a092602b4546abf762efcf3c0a2aed`.
The exact enabled configuration is retained as `config-after`, SHA256
`31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483`;
the original is `config-before`. The only configuration additions/removal were:

```text
+ CONFIG_KDLOCK_REBUILD=y
- CONFIG_CC_VERSION_TEXT="x86_64-linux-gnu-gcc (Ubuntu 15.2.0-16ubuntu1) 15.2.0"
+ CONFIG_CC_VERSION_TEXT="gcc (Ubuntu 15.2.0-16ubuntu1) 15.2.0"
```

`scripts/config --enable KDLOCK_REBUILD` and `make olddefconfig` returned 0.
`olddefconfig.log` preserves:

```text
security/apparmor/Kconfig:120:warning: multi-line strings not supported
```

The selected core command was:

```sh
make -C /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source \
  O=/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/build \
  KERNELRELEASE=7.0.0-38-kdrebuild1 -j16 \
  kernel/kdlock/ kernel/fork.o kernel/exit.o
```

It ran from 14:38:14.795652 UTC, returned 0 after 53.4027 seconds and completed
at 14:39:08 UTC. `core-and-hooks.log` records exactly 26 package CC entries,
three package AS entries, both lifecycle-hook objects and the package
`built-in.a`. The unexpanded `include/wrapper.S` is excluded from the core.
Independent readback compared the explicit Kbuild list, unique logged entries
and actual nonempty ELF object files: all 29 agreed, with stable file hashes.
This is not a separate per-image wrapper build or runtime claim.

Read-only tool banners and representative actual C/assembly `.cmd` files are
copied into `independent-readback.json`: GCC Ubuntu 15.2.0-16ubuntu1, GNU
assembler and linker 2.46. The observed running kernel remained
`7.0.0-38-kdlock1`, boot ID `3d32656f-6162-4a0a-9304-bf383d34298d`, taint 0;
the candidate release `7.0.0-38-kdrebuild1` was not booted for this receipt.

## Retained material

`preparation.json`, `pins.json`, raw inspect/plan output, application logs,
manifest/journal/patch, configurations, selection/olddefconfig logs and
`configure-core-result.json` are unedited copies from the VM receipt directory.
`core-and-hooks.log` is the complete core-build log. The independent readback
is a separate read-only derived receipt containing baseline manifest/build IDs,
config hashes, actual object hashes, protected-input comparisons, command files
and tool banners; it invokes no build or test. The large baseline configuration
manifest, full source backups, core binaries and the concurrent full-build log
remain at their original paths rather than being copied into this directory.

The two retained raw `.patch` files contain unified-diff context prefixes before
original kernel tabs and blank lines. Git whitespace checking flags those literal
artifact lines; their bytes are preserved rather than reformatted. The warnings
do not describe newly introduced whitespace in the applied kernel source.
