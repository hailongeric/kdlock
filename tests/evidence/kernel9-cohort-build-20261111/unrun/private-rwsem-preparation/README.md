# Kernel9 private rwsem validation preparation

This preparation is source-only and **not dispatchable**. It selects one
existing private rwsem/query regression against corrected built-in core
`6e486ecec398111fb5d5e30ffc76495f32f557b7`. It does not select mutex, spin,
native API, syscall/MM or full-suite execution and is not a deterministic
reproduction of the failed queue interleaving. No new hook, test, helper model
or execution architecture is added. Root remains the sole VM operator.

The new kernel source/output target is
`/mnt/kdlock-builds2/kdlock-main-kernel9-6e486ece-01`, release
`7.0.0-38-kdrebuild9`. Its built-in core/NLS build, install and boot are separate
parent-owned work. Do not reapply the installer to the existing integrated
kernel source. A successful kernel9 build is not assumed by these files.

## Exact committed source

`source/` and `source.tar` freeze the **exact 143 regular names** from the prior
0798 export's `source-sha256.json`. Every byte comes from `git show` at corrected
commit 6e486ece. Private `.inc` dependencies remain included. This avoids a
recursive worktree copy and excludes the new untracked failure-evidence archive.

The export has 1,622,641 source bytes. The 1,740,800-byte deterministic regular
tar retains all 143 members. Compared with old0798, exactly these members differ:

- `kernel/mutex.c`, the reviewed cohort-await correction;
- `kernel/integration/RWSEM.md` and `tests/kernel/mmap_api/README.md`, maintained
  evidence/scope prose already among the original 143 names.

All 78 core member hashes are taken from the same corrected commit. Relative
to old core0d, only `kernel/mutex.c` changes, to SHA-256
`014b4a9cfb4609eb8a1e49cc14e715302b13060dc641519a7e68b22a7e515564`.
`core-78-sha256.json` records that exact comparison. The selected tracked names
have no worktree edits; **the whole workspace is not claimed clean**. The
untracked failure archive and actual global status are recorded separately in
`source-state.json` and `source-derivation.json`. Their empty `git_status` is
explicitly scoped to the selected 143 tracked names only.

| Frozen input | SHA-256 |
| --- | --- |
| `source.tar` | `86c84337a6f4391a299eed49bbd64f92d1dc2dd63ce94b5b989b6dc71af66e13` |
| `source-sha256.json` | `ea8c7cc7b502ec250c0933d3c72ebdef93b89a30a2fc6c9389c32f9e85ccb45e` |
| `source-state.json` | `606946f626e6bcb06d380d70dea8d9e38019248e5a564b2e8cfd9bd63dbb9ad2` |
| `core-78-sha256.json` | `da8fb180d68c5a0af461160ad52add05a355b07630f59f4aa5d9c4eb32c76f98` |

The parent can stage this exact source snapshot as
`<kernel9 target>/private-rwsem-regression-01/input`, with manifests outside
that immutable input tree. Bind the export hashes, built-in core78 and actual
kernel9 build receipt together before building the module.

## Module-only external build and signing

`module-build-sign.template.json` retains structured argv derived from the
actual kernel8 rwsem module build. Its sole build is:

```text
/usr/bin/make -C <kernel9 target>/source O=<kernel9 target>/build
M=<kernel9 target>/private-rwsem-regression-01/input/tests/kernel/rwsem/payload
MO=<kernel9 target>/private-rwsem-regression-01/module-build
KERNELRELEASE=7.0.0-38-kdrebuild9 -j8 V=1 modules
```

These lines display one argv, not a shell script to run independently. The
actual `M` payload's unchanged Kbuild selects only
`kd_rwsem_runtime_fixture.ko`; the included shared runtime source remains in
the frozen tree. Source and module output stay separate.

After actual success, require exactly that named `.ko`, retain its unsigned
hash, copy it to a fresh exclusive `signed/` file, fsync, then use the new
kernel9 build's `scripts/sign-file sha512` with its actual signing key and
public certificate. Do not log private key data. Preserve the unsigned file
unchanged. Record actual signed size/hash and `modinfo` vermagic, signer,
sig_key, sig_hashalgo and depends. Require release9, nonempty signer/key,
sha512 and empty module dependencies against the built-in core.

The historical build's bounds are retained: 180 seconds for this module,
60 seconds per signing/metadata check, 900 seconds overall, eight jobs, root
free-space floor 1 GiB and output floor 4 GiB. Before and after, recheck the
actual new source78/kernel16/protected/default-boot identities. The old
five-module build driver must not be executed to obtain this one module.
Retain all actual diagnostics: the historical rwsem build had a 4,352-byte
frame warning and a checkpoint prototype warning, not a warning-free baseline.

## Existing runtime argv

`rwsem-arguments.template.json` derives from the saved successful kernel8
private-rwsem arguments. It retains:

- four workers and eight iterations;
- dependency-page limit16, total source131072, event capacity65536;
- wire log268435456, runtime source visits16000000;
- reader learning passes16, coordination spins1000000;
- holder timeout20000 ms, runner deadline600 seconds and outer observer660.

Only the frozen source/module/output/kernel paths, release and fresh actual
GS/builtin-thunk bindings are changed in the argv template. The existing
`tests/kernel/rwsem/run_rwsem_runtime_fixture.py` is the sole runtime entry.
No mutex/spin role CPU or new source scene is introduced. Immutable text and
auxiliary stack contracts retain their existing explicit meaning; a module
build, same-mm check or successful private fixture does not prove general
native-context/AUX support.

Every `__UNBOUND_...__` value intentionally fails admission. Replace it only
from fresh actual linked/boot records: kernel9 ELF/config/BuildID and full GS
offset/proof, exact `its_return_thunk` address/size/bytes, new signed module,
recovery and required build/boot/identity receipts. Do not reuse kernel8's GS
offset, thunk address or module hash even if one appears likely unchanged.
The unchanged runner checks the supplied builtin source against the actual
kernel9 ELF and exported bytes (`run_runtime_fixture.py:235-260,956-959`).

## Supervisor derivation and required binding

`prior-supervisor-reference.py` is a byte-exact copy of the successful kernel8
private supervisor, SHA-256
`625834d3f1e4f45629b2e1069049253722dba5e7e6c27ae791391bb70c7bab9a`.
It is **reference only**: its literal kernel8 paths, e001 boot, old K02
predecessor, a991 host-check receipt, old module/GS hashes, and mutex branch
must not be run unchanged on kernel9.

`supervisor-binding.template.json` provides the complete required rebindings
and the existing single-child observer behavior. Once the parent has actual
receipts, derive the rwsem-only supervisor from that reference and source-review
the concrete bytes before dispatch. Its first prerequisite is the new exact
kernel9 linked build and fresh boot/GS/recovery/idle proof, not rerunning the
old predecessor or host-check suite. Source trust/immutable dependencies and
the existing explicit context admission stay separate from those receipts.

Use the same 660-second observer, 32 MiB child-log bound and space floors.
Record child PID, exact argv/env, returncode and raw logs. Timeout or failure
retains child/control state and records an incomplete verdict; it does not
signal, unload, clear state or infer drain. Keep fresh output leaves and never
edit staged or running inputs. The old supervisor's same-before/after taint4096
literal must be rebound: for a fresh kernel9 boot, record actual initial
taint0 and allow only the expected ordinary out-of-tree-module4096 change
after the signed fixture loads. A different taint is not silently accepted.

Success requires the existing inner status
`protected_rwsem_jit_reader_mechanism_pass`, protected episode completion,
warm-claim no-new-facts proof, actual child exit0, raw final observations and
archive, exact shutdown/archive/settlement/end responses, ordinary module/device
absence and no remaining actors, with source/kernel/protected pins unchanged.
Keep intentional pending facts distinct from coverage ACKs. The full C
epilogue remains outside the protected episode scope. Report actual counts;
do not require kernel8's old publication/ACK totals as a new pass criterion.

## Evidence and scope

`derivation-inputs.json` pins the old arguments/supervisor, actual old build
receipt, source membership/core map and current frozen Kbuild/runner. The
preparation script and `source-derivation.json` make the source selection and
actual changes reviewable. `preparation-result.json` reports zero VM commands,
project imports, tests or builds for this preparation. No executable module,
new linked/boot identity or runtime result is asserted here.

The private check is an affected regression for the corrected core. It cannot
by itself deterministically reproduce the earlier timing window, validate the
deeper actual mmap run, prove full-MM execution or establish performance.
