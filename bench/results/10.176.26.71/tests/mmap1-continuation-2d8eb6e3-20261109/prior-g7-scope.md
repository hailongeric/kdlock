# Saved munmap g7 scope review

Read-only source-host inspection; no VM queries, tests or new measurements. Saved assembly: `/tmp/kdlock-live-ac0-collected/run/workspace/daemon/0xffffffff8181c73b/2417/asm/jit.S`, SHA256 `27a9b385b863e9e5a82f18c313a906dd50274889fd9bbfafda740863809bc291`.

**The 26,102 instructions cannot all be described as inside the write critical section.** This is a static decoded-source inventory, including alternative branches and callees, and the saved image concretely contains source continuations after release operations. No reliable numerical inside/outside partition is established.

## Count definition

- `disassem/disassem.py:101-120` constructs a set of `(line.offset, line.offset + line.l)` from the selected CFG blocks, requiring complete instruction bytes contained in cached source regions. `decoded_instructions` is the size of that set; `decoded_instruction_bytes` is its byte-range union. It counts neither generated wrappers nor executed instructions. The completed-CFG reporting call is at `disassem/disassem.py:753-762`, before later emission processing.
- Captured `run/daemon.log:30635` reports g7: `decoded_instructions=26102`, `decoded_instruction_bytes=101962`, `blocks=6204`, `cached_bytes=950272`, `cache_outside_selected_instructions=848310`, and zero pending/incomplete blocks.
- Independent offline parsing of the saved assembly's `/*\nloc_<address> ... */` source listings counted **26,102 instruction lines in 6,204 distinct block listings**, excluding block headings and `->` CFG annotations. Thus these static totals match this saved image's source listings. Generated lowering, register/stack bookkeeping, budgets, service paths and dispatch code are additional assembly; no generated-machine-instruction total was established.

## Concrete boundaries in the saved image

The captured `run/provenance/compile-5/rwsem-controls.txt` identifies `814f4f70` as operation 5 (`UP_WRITE`, line 14), `814f4fa0` as operation 6 (`DOWNGRADE_WRITE`, line 6), and `814f5280` as operation 11 (`UP_READ`, line 10). Operation meanings are defined in `include/kd_rwsem_provider.h:21-34` and routed in `kernel_module/execution/service_control.inc:38-45`.

- **Post-write-release source:** `jit.S:165189` calls `0xffffffff814f4f70`, with return word `0xffffffff8181c86e`. The emitted successor at `jit.S:165206-165215` jumps to `8181c7a5`; that source block at `jit.S:165046-165058` calls `81965500` and continues toward the function epilogue. This proves an emitted source path after that write release; it does not prove that generated invocation executed it.
- **Downgrade:** `jit.S:163786-163815` calls `814f4fa0`, then emits `81818dd9 -> 81818bfe`. Subsequent work can be outside the write-held phase while still holding a read lock; downgrade is not complete unlock.
- **Read release:** `jit.S:163737-163766` calls `814f5280`, then emits `81818daf -> 81818d2d`. The source listings use the same `R12 + 0x1c0` object expression as the nearby downgrade path.

These are path-specific static boundaries. A block can be reached under different ownership contexts; neither a large callee nor a cold branch is automatically outside the selected scope.

## Why emitted scope and runtime scope differ

`disassem/context_policy.py:514-524` explicitly treats lexical depth as conservative rather than an ownership proof. Its runtime-delimited mode follows the finite decoded CFG, while discovered callees have unknown entry depth. CALL successors are retained at `:571-575`; the coordinator selects runtime-delimited handling in `disassem/disassem.py:496-522` when required.

Runtime release resolves the actual object against exact owner records (`kernel_module/kd_service.c:953-985`). Downgrade changes the admission state; write/read release marks that owner released. `kernel_module/execution/continuation.inc:641-648` ends the JIT scope with `KD_EXE_RUN_TO_UNLOCK` once the outer owner and all nested owners are released, before resuming the emitted successor. If other owners remain, it can continue. Therefore source emission after a release is not evidence of execution outside all held locks.

The 26,102 total supplies no actual executed subset or frequency. Existing run timing placed g7 build completion after the learning application ended; publication is not evidence that g7 returned a translated body.
