# MM continuation restore: first-failure investigation and bounded correction

Offline inspection found and corrected a definite packet-lifetime defect in
the builtin MM restore functions. Focused VM userspace checks pass. The evidence
does **not** establish that this defect caused the first failure in
[the bounded mmap1 attempt](../../bench/mmap1-learning-e57ae29d/README.md).
No new mmap workload, kernel rebuild, installation, reboot or cleanup occurred
during this investigation. The candidate remains unaccepted.

| Role | Commit |
| --- | --- |
| Investigation baseline | `fe753cc3856ab308f77e0525597fd772d1e20b39` |
| Design before implementation | `459967842d9737886a62053f04d30bb0b89003f9` |
| Builtin restore correction and fixture | `b1884ccbe3227c138d8c427b83328407648b00be` |
| Fixture declaration correction, tested revision | `e342cfc1d9f529abd74390bc070e20b51d9d9ff1` |

## First failure and instruction provenance

At boot time 140.476822 seconds, 104.824910303 seconds after application launch,
origin PID 2426 (`mmap1_processes`, CPU 5) reached
`kd_provider_assert_held_write+0x5/0x80`. Instruction `48 8b 17`
(`mov (%rdi),%rdx`) dereferenced `RDI=856488d3cbaf5b00` before evaluating
the ownership predicate. The first ownership warning is a different, later
event on PID 2427. Later munmap and scheduler traces do not explain the first
invalid argument.

The matched kernel is `7.0.0-38-kdscope5`, Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`. Its recorded chain is
`__vm_munmap` → `do_vmi_munmap` → `do_vmi_align_munmap` →
`vms_gather_munmap_vmas` → `? kd_mmap_assert_held_write` →
`kd_provider_assert_held_write`. The adapter frame's question mark is the
unwinder's uncertainty. Its source should pass `&lock->kd`.

The matching ELF establishes the adapter argument and CALL sequence:

| Source PC | Bytes | Operation |
| --- | --- | --- |
| `0xffffffff814f4a10` | `48 89 7d e8` | Save lock argument at source BP−24 |
| `0xffffffff814f4a1f` | `e8 cc 6d 06 00` | Call `__module_get`; return word `0xffffffff814f4a24` |
| `0xffffffff814f4a28` | `48 8b 7d e8` | Reload the lock argument into RDI |
| `0xffffffff814f4a2c` | `48 8b 92 c8 00 00 00` | Load provider callback into RDX |
| `0xffffffff814f4a33` | `e8 08 f8 20 01` | Call through the RDX thunk; return word `0xffffffff814f4a38` |

The same-run, later generated image represents source BP/SP in physical R12/R13.
It preserves the argument store/reload, decreases virtual SP by eight and writes
the real `0xffffffff814f4a38` return word once before indirect dispatch. The
unknown-target path exports target IP, source SP/BP, GPRs, flags and the CALL
site. `kd_jit_retained_miss()` verifies the already-pushed return word and pins
the target/source before recording the terminal continuation. It does not
replay the CALL or earlier `__module_get` effects. Full export maps BP/SP to
packet offsets 16/8 and DI to 128.

On the origin, `kd_service_shadow_wait()` chooses the lower helper stack,
`kd_service_native_resume()` copies the packet before accepting retirement,
and the MM completion calls builtin `kd_rwsem_provider_resume()`. Tagged
continuation resumes at the first unexecuted target with exported SP unchanged;
the target's eventual RET consumes the original CALL word. Ordinary completion
instead consumes its existing return word immediately. The correction preserves
both contracts, including exact ownership and reference retirement.

These are verified source/ELF/lowering contracts, **not a dynamic reconstruction
of PID 2426**. Its packet, bound image and exact local-versus-handback path were
not recorded. Only the first munmap compiler job had completed by the first
failure (133.076762327 seconds); the next started at 184.213387809 seconds.
There was no completed munmap replacement available at the first failure.
Current generated files contain later learned targets and cannot serve as the
missing first-image bytes. No exact original DI/SP/BP values before restoration
or interruption history are available.

## Confirmed compiled layout and defect

The inspected module has SHA256
`0eed22735568e59e0b55306a7d3311be8659b2ddd7dd986854f0f7f1d3e322ae`.
Let S be exported source SP and
T = align_down(min(saved helper SP, S), 16). The exact compiled
`kd_service_native_resume` pushes its return/frame words and reserves 192 bytes,
leaving helper RSP=T−232. Its 21-word packet starts at helper RSP+16.

| Item | Exact location |
| --- | --- |
| Packet, 168 bytes | `[T−216, T−48)` |
| Packet SP / BP / DI offsets | 8 / 16 / 128 |
| Packet SP / BP / DI addresses | T−208 / T−200 / T−88 |
| Old tagged target and flags pushes | S−8 / S−16 |

The builtin consumer uses exactly those packet offsets. Since S≥T, the old
target/flags pushes are above the packet: **direct push/packet alias is ruled
out for this layout**. They do not explain a deterministic overwrite of DI.

The actual defect is subsequent access below the raised stack pointer. At
`0xffffffff814f5769`, tagged restoration sets RSP=S before loading most packet
GPRs, including DI at `0xffffffff814f57a8`. Ordinary restoration similarly
sets RSP at `0xffffffff814f5830` before its DI load at `0xffffffff814f5834`.
IRQs are enabled on this path. Interrupt stack use may reuse the now-inactive
storage containing unread fields. The module-side copy and packet offsets are
consistent; the read ordering is not. This is the same lifetime principle
already enforced by `include/wrapper.S` full export.

That hazard can corrupt restored registers. No retained observation proves it
produced the particular `856488d3cbaf5b00` value. There is no claim that the
modeled reuse below reproduces the original interrupt sequence.

## Correction and focused checks

Both changed functions are in
`kernel_integration/mmap_lock/overlay/kernel/locking/kd_mmap/provider.c`,
**built into the comparison kernel**. `kd_service_native_resume()` and the JIT
wrapper are module-built and unchanged. A new module alone cannot activate this
builtin correction.

Ordinary completion stages S on the active helper stack, reads every GPR
including DI, then uses `popq %rsp` and the existing return. Final SP is S+8.
Tagged completion stages S−8, writes target IP at S−8, stages merged flags on
the active helper stack, reads every GPR, then uses `popfq; popq %rsp` and the
existing return. Final SP is S; the actual source CALL word at S remains intact.
There are no packet reads after the stack change. No new queue, backend,
interpreter, instruction service or context policy is introduced.

The first fixture build stopped on a test-only `noinline` declaration error;
its receipt remains retained. The corrected fixture then compiled and executed
the actual builtin function bodies on the normal VM:

- **390 passing cases:** ordinary completion plus 64 tagged arithmetic-flag
  combinations, with and without modeled DI-slot reuse, across three return
  configurations. All GPRs, source SP/BP and tagged CALL-word checks passed.
- **Six expected failures:** moving the final stack change ahead of unread
  GPRs made the reuse model detect the DI error in both paths and all three
  configurations.

The reuse hook performs one flags-neutral DI-slot write at the stack transition.
It models the lifetime consequence, not a real interrupt. The reordered cases
are deliberate controls, not exact archived old assembly. Configured return
routes use a RET stand-in; actual kernel thunk execution is not validated by
this fixture. Logs are in the raw records; no broad suite was run.

## Publication role, preserved state and blockers

Retained capture obtains source/module/task-stack leases before lookup, stores
the exact image and binds it to the execution frame. Published immutable
descriptors/code remain resident for the provider session. Upload uses a new
descriptor/block; replacing the current registry pointer does not redirect a
bound frame. Revision receipts contain metadata, not GPR or source-stack data.
No in-place image replacement mechanism was found that explains this argument.
Wider capture can expose unchanged restore paths more often; that is a possible
triggering condition, not proof of first-failure causation. Active pending-image
capture, original JIT/backend/GS behavior and existing limits remain unchanged.

The focused check verified the same normal boot
`4ff57d48-bc4c-43bd-9946-b16e0db3d4da`, `7.0.0-38-kdlock1`, idle state and
unchanged frozen inputs. Host free space is 4,123,881,472 bytes; guest build
filesystems have 15,129,886,720 and 6,514,458,624 bytes free. A separate matching
kernel build is blocked by headroom. Installed kernels, recovery identities and
historical data were preserved. No kernel rebuild or live mmap rerun was made.

The remaining requirements are a preserved-data storage plan, a matching
corrected kernel build, and first-failure validation that distinguishes packet
export from restoration using exact request/image identity. The fixture pass
alone does not authorize treating the original failure as resolved or repeating
the long warmup. Master is unchanged; all work remains isolated.

`analysis.json` records identities and conclusions. `retained-files.json` indexes
16 compact evidence files (29,277 bytes) under
`../../raw/tests/mmap-continuation-restore-e342cfc1/`, including exact assembly
excerpts, the failed and passing check receipts, source-freeze identities and
headroom. Larger original binaries and generated files remain at the referenced
paths; they were not duplicated into this report.
