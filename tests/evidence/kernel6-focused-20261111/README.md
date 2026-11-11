# Kernel6 focused compilation and unselected syscall baseline

Core532b68a6 and source/installer3512f5dd compiled on the normal Linux7 guest,
boot51b49fa4-4d99-457e-a73e-632b690eb95e, taint0. Candidate source/output is
`/mnt/kdlock-builds2/kdlock-main-kernel6-532b68a6-rwsem-04/{source,build}`.
The normal source/output, kernel5, installed kernels/modules and boot selectors
were preserved. All builds, imports, parsers and execution occurred in the VM.

The exact seven-file application committed successfully. Its first verification
invocation omitted the required fingerprint arguments and returned1; no make
had run then. The raw [application collection](applied/collection.json) includes
actual source, before/after backups, manifest, COMMITTED journal and failed
verification receipt. A separately reviewed continuation supplied all three
original pins without reapplying or editing the source.

[The original compilation receipt](compile/payload/receipts/result.json) records
verification0, olddefconfig0 with configuration SHA31d9701e unchanged, and
focused make0 in56.7914s for33 KD units plus8 affected native objects. It then
failed the final strict idle check on kworker PID/TID6734 waiting at
`drm_crtc_wait_one_vblank`. This original FAILED_OR_INCOMPLETE receipt remains
unchanged. A later bounded inspection found that worker idle, with no build or
D-state thread. No task was interrupted and compilation was not repeated.

The [read-only finalization receipt](finalization-controller/actual-finalization-result.json),
SHA `ca47a75c78d61492c1209fff0ccae18821cd3dd14812c8cc2fc059578d789f80`,
returned0 after verifying all41 objects and41 command files, original rc0 logs,
configuration/release, source/application/protected input hashes, and fresh
strict idle before/after. It writes a separate FOCUSED_COMPILE_COMPLETE record
with explicit provenance to the original failed final-idle result. It executes
no make, source update, module or kernel code. The source and object checks
prove scoped compilation, not lock semantics or auxiliary-stack compatibility.

The subsequent [focused-check receipt](checks/payload/checks/receipts/result.json),
SHA `e41c5d136840d3babcf718968e63cc866bfccd18881f537ee2fc76ce782ab655`,
returned0 with:

- Four exact source-boundary regressions passed, with no skip, in0.510s.
- The actual userspace client compiled with `-std=c11 -O2 -Wall -Wextra -Werror
  -pthread`, return0 in0.410s.
- An unselected2-thread x8-iteration real mmap/munmap baseline completed0 in
  0.0097s, with deterministic zero/write/readback, holes and fresh address reuse.

The [raw syscall output](checks/payload/checks/receipts/native-syscall-baseline.stdout)
remains separate from KD observation. This baseline ran the existing normal
kernel without selecting a KD object. It establishes client effects and test
construction only. Generic selected-API behavior, selected real-MM execution,
new-image boot and generated execution remain unrun at this checkpoint. There
is no performance comparison or gain claim. The later full build has separate
[build/linked-image evidence](../kernel6-build-20261111/README.md).
