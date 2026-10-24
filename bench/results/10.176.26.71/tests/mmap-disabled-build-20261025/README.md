# Disabled KD mmap configuration: object and link compatibility

**Passed for the existing x86-64 SMP configuration with `CONFIG_KD_MMAP_LOCK`
undefined, meaning disabled. No production fix was necessary.** The check covers
preprocessor selection, affected builtin objects and relocatable links. It is
not a full-kernel build or disabled-configuration runtime result.

Only the correctness runner and fixture were added. The restored production
patch, lock implementation and native MM bodies are unchanged. No installation,
boot, module load, mapping workload or performance run occurred.

## Configuration and method

The tracked reports, Git history and available result paths contained no matching
disabled-configuration check. Prior Native-control runs used
`CONFIG_KD_MMAP_LOCK=y` with `kd_mmap=off`; they do not establish the disabled
preprocessor branch. The earlier cleanup and eight reconciled runtime runs were
reused without repeating their tests.

The check used the exact recovery `.config` and generated configuration header:

- `.config` SHA-256: `e1dd628c6f2315c77debd559cf6df1f299814b0b4ba47d5964cfb5bde4dd4ccd`.
- `autoconf.h` SHA-256: `d3f84201b7699d18c174ba6e20f01cc8b8b80fc939c542f9aa87f2f9dd1e1cd1`.
- `CONFIG_SMP=y`, `CONFIG_BPF_SYSCALL=y`; KD mmap, RT, lockdep and debug lock
  allocation are disabled. The new KD Kconfig boolean has no default-y clause.
- GCC `11.4.0-1ubuntu1~22.04.3`, GNU ld `2.38`. Captured native compiler recipes,
  including UBSAN instrumentation and frame-pointer settings, were retained.

Nine interface files were copied into private scratch and patched with fuzz
disabled. Patched headers precede native include paths, and compiler dependency
files prove those headers were selected. No recovery source, configuration or
object was overwritten. The unchanged native objects were reused as the baseline.
The existing object sizes produced a final scratch budget of 26,895,132 bytes;
3,736,309,760 bytes were available before the final check.

The affected sources are `mm/mmap_lock.c`, `kernel/fork.c`,
`kernel/bpf/task_iter.c` and `kernel/bpf/stackmap.c`. The last two are the direct
consumers of the changed BPF asynchronous-unlock header. A compile-only fixture
instantiates the real headers and APIs in both native and disabled-integrated
forms; it introduces no replacement lock or runtime MM body.

## Results

| Check | Result |
| --- | --- |
| Preprocessor and Kbuild selection | All 15 aliases select native interfaces; `kd_mmap/` is absent from selected builtin/module objects |
| Native lock type and layout | `mm_struct.mmap_lock` is `struct rw_semaphore`; 40-byte lock at offset 112 in the 1,056-byte mm structure, identical in both fixtures |
| Initialization and ordinary wrappers | All 15 function byte sequences and their relocations match native; static initializer and layout constants also match, 17 comparisons total |
| Disabled destruction wrapper | No KD destruction dependency; emitted function has only entry/return instrumentation and ordinary prologue/epilogue |
| Actual fork/BPF/lifetime objects | All four compile with the patched interfaces; both BPF consumers select the patched lifetime header |
| Native and integrated partial links | Both pass; `mmap_read_unlock_prepare`, `mmap_read_unlock_complete` and `mmdrop_async` resolve across objects; no new unresolved symbols relative to native |
| Unintended services | No KD mmap or retired prepared-MM service symbols in the integrated link |
| Preservation | Recovery inputs, configuration, original objects, reused outputs and six native MM body files retain their hashes |

`check-1` passed the first three objects and both fixtures: five successful
compiles. The shared-header review then identified `stackmap.c` as additional
coverage. `check-2` **failed** before producing that object because the isolated
copy lacked the native quoted-header search for `percpu_freelist.h`. This was a
runner setup omission, not a kernel defect or a pass. Its exact driver, diagnostic
and receipt remain preserved.

`check-3` fixed only that search path, compiled `stackmap.c`, and completed the
four-object-plus-fixture link comparisons. It reused all five successful
`check-1` objects after checking source/header hashes, original compiler commands,
configuration, tool versions and object hashes. There were six successful object
compiles in total, plus the one failed setup attempt. Successful compiler logs
contain no diagnostics. No completed campaign or basic test was rerun.

## Commands and evidence

For a fresh check in an idle recovery guest:

```sh
cd /root/host_fs/kdlock
/root/kdlock-translation-venv-20261019/bin/python3 \
  tests/kernel/mmap_lock/disabled/run.py \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/10.176.26.71/tests/mmap-disabled-build-20261025/check-4
```

The final recorded run used `--output .../check-3` and additionally
`--reuse /root/kdlock-evidence/10.176.26.71/tests/mmap-disabled-build-20261025/check-1`.
Reuse requires a passed prior check and exact matching inputs/commands; it never
edits that prior evidence or accepts a failed check as a cache.

- [Initial pass](../../raw/tests/mmap-disabled-build-20261025/check-1.json),
  [preserved setup failure](../../raw/tests/mmap-disabled-build-20261025/check-2.json),
  [final pass](../../raw/tests/mmap-disabled-build-20261025/check-3.json) and
  [final recovery health](../../raw/tests/mmap-disabled-build-20261025/final-health.json).
- [One essential log archive](../../raw/tests/mmap-disabled-build-20261025/essential.tar.gz):
  37,298 bytes; SHA-256 `52755a87ce4bbdde7b4acd0b331eba56ba0ffc71ef2ddcc231e905a4128b258a`.
  It retains compiler/link commands, dependency paths, comparisons and the failed
  diagnostic. Unchanged kernel images and old archives were not copied.
- Source bindings are in `inputs.json`, `inputs-2.json`, `inputs-3.json` under the
  same raw directory. The first two driver versions are retained there; the final
  runner and fixture are maintained under `tests/kernel/mmap_lock/disabled/`.

## Limits and final state

Relocatable linking combines these objects while leaving ordinary kernel symbols
for the eventual kernel link. The check proves no added unresolved dependencies;
it does not resolve the whole kernel. There was no `olddefconfig` regeneration,
full Kbuild/objtool/BTF pipeline, final image link, installation or boot. Runtime
reference/cancellation behavior in a disabled-integrated image remains untested.
RT, lockdep, broad callback coverage and performance remain separate deferred work.

Recovery stayed idle on `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, boot
`1602542f-b2ec-4f6b-b67d-db89dee83137`. All 73 expected runtime modules remain,
with no test modules, pending boot or kernel-fault pattern matches. No process
was interrupted and no source, recovery artifact or unique evidence was deleted.
The unrelated disk-cleanup README modification remains untouched.
