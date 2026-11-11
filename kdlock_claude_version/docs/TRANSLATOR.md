# Translator and daemon

The translator is a userspace component (`jit/`). It turns the kernel code
that follows a lock call into a relocated copy that a combiner can run on the
waiter's stack. This page states what it produces and the contract with the
kernel. Kernel side: [ARCHITECTURE.md](ARCHITECTURE.md) sections 5 and 9;
interfaces: [INTERFACES.md](INTERFACES.md).

## 1. Input and trust

Input is the live kernel text read through `/dev/kdlock` (`KD_IOC_READ`),
decoded with capstone, plus `/proc/kallsyms` for names and `KD_IOC_TEXT` for
text regions and their exception-table entries (core kernel and modules).
**Kernel and module source is trusted**; no semantic
safety proof is attempted. What is checked is structural: decodability, target
ranges, instruction support. Anything the translator cannot place correctly
becomes an exit, never a guess.

Requirements (stated, not verified): a kernel text base within sign-extended
imm32, and an image within rel32 range of kernel text. Run as root with
`kptr_restrict=0`.

Every build belongs to one **text generation** (read before symbols and text).
When modules come or go the kernel bumps it and refuses older images; the
daemon then rereads symbols and builds again (see INTERFACES 1).

## 2. What is copied and what is rewritten

The copy runs on the **origin's real stack** and the executor's CPU, so
almost every instruction is copied **byte for byte** (this also keeps `PAUSE`,
fences and `LOCK` prefixes exactly as they are). Only these change:

| Source | Copy |
| --- | --- |
| Direct `jmp`/`jcc`; short-only branches (`jcxz`, `loop*`) | go to the copied target (the short-only forms get their own emission kind because their 8-bit range cannot reach the copy) |
| Direct `call` | `push imm32` of the **source** return address, then jump to the copy of the target. The origin's stack therefore always holds ordinary kernel addresses and it can take over at any instruction |
| `ret` | compare chain over the known return targets (learned), then a learnable `MISS_RET` exit |
| Indirect `call`/`jmp` (including `__x86_indirect_*` thunks, unnamed module ITS thunks that are a single `jmp *%reg`, and `ret` through return thunks) | evaluate the target, compare chain over known targets, `MISS_IND` exit. This also removes return/indirect-branch mitigations from the copied path |
| rip-relative operands | displacement recomputed for the new address |
| `%gs:current_task`, `__stack_chk_guard`, `cpu_current_top_of_stack` | `%gs:kd_cpu.task / canary / stack_top` (via an absolute-modrm form) |
| Call to a release API | `cmp rdi, gs:[kd_cpu.root]`; equal → `UNLOCK` exit (section complete). If `gs:[kd_cpu.anc]` is nonzero a non-root release → `UNLOCK_ANC` exit |
| Call to a spin-class acquire | native call to its `_jit` alternative (same fast path; contended → `NESTED`) |
| Call to a sleeping acquire | `ACQUIRE` exit |
| Calls in the `native` list (memcpy, strlen, ...) and every `kd_` function | native `call` |
| Calls in `skip` (`__fentry__`, `__might_sleep`, ...) | dropped |
| Frontiers | exit carrying the address of the first unexecuted instruction |

**Frontiers** are: instructions with an exception-table entry (they rely on
their own address being in the table), text outside a live text region,
privileged/CPU-state instructions
(`stac`, `swapgs`, `wrmsr`, `iret*`, `sys*`, `hlt`, `int*`, `ud*`, `invlpg`,
`invpcid`, descriptor-table loads, `mwait`, VM instructions, `xsave*`,
`xrstor*`, `fxsave/fxrstor`), scheduler entry points, user-copy helpers and
get/put-user helpers, and text it cannot decode or that lies outside kernel
text.

Every exit records, through `mov` only (no flags, no registers clobbered
beyond what the exit stub saves), `exit_ip` (first source instruction not
executed), `resume` (generated-code address to continue at, when relevant),
`exit_code` and `aux`, and jumps to `kd_jit_exit`.

Layout: hot code first, exit stubs and miss paths in a cold area; the image
is linked at the address the kernel allocated (`KD_IOC_IMAGE_ALLOC` returns
the base), so rel32 displacements are final.

## 3. Discovery

Starting from the return address of the lock call, the translator follows
direct jumps and up to `call_depth` (5) direct-call edges. Deeper callees
start as `MISS_CODE` exits. At most `max_insns` (60000) instructions go into
one image. Known return addresses (callers inside the image) feed the `ret`
chains. Indirect branches start with an empty chain.

## 4. Learning loop (daemon)

```
kernel: contended site without image  -> KD_EV_REQUEST
kernel: image runs, meets unknown     -> MISS_CODE / MISS_IND / MISS_RET (budget 64/image)
kernel: most executions handed back   -> SITE_OFF
daemon: poll events (10 ms), add to cumulative knowledge, wait 50 ms (settle),
        rebuild the whole site, publish, save state
```

* Knowledge per site (`Learned`): extra code roots, indirect targets keyed by
  branch address, return targets keyed by `ret` address. It is cumulative and
  saved as JSON per kernel release (`/var/lib/kdlock/learned.json`); a restart
  republishes everything known.
* The current invocation never waits: a miss hands the section back to its
  origin, and the report only improves later images.
* Convergence is by rounds: each round exposes one more layer of targets.
  Raising `call_depth` (via `--config`) covers deeper static chains in the
  first image.
* A site the translator cannot handle (`TranslationError`, load error) is
  added to a failed set and left undelegated. `ESTALE` (text changed during
  the build) only schedules another build.
* `KD_EV_TEXT_GONE`: knowledge inside the range is discarded (sites, code
  roots, indirect and return targets) and every other site is republished,
  since the kernel dropped all images.
* `KD_EV_REQUEST` always triggers a build; the kernel sends it only for sites
  without an image.

## 5. Contract the kernel assumes of an image

1. Entry: registers and flags as left by `kd_jit_enter` from the packet; the
   image starts at the instruction after the lock call.
2. It never leaves except through an exit stub or by `kd_jit_exit`.
3. Calls to native code obey the System V convention; flags are dead at
   `call`, `ret` and indirect branches (assumption 3 in ARCHITECTURE 11).
4. The origin's stack below `rsp` is used as a normal stack; interrupts on the
   executor CPU push onto it.
5. An exit's `exit_ip` is exactly the next instruction the origin must execute,
   with all earlier effects (including pushed return words) complete.

## 6. Files

| File | Role |
| --- | --- |
| `jit/kd_daemon.py` | event loop, knowledge, build/publish, state file |
| `jit/kdjit/translator.py` | decode, classify, emit, link |
| `jit/kdjit/kernel.py` | `/dev/kdlock` wrappers, kallsyms, text page cache, text regions and fixups, generation |
| `jit/kd_dryrun.py` | build images for the lock calls in named functions without loading; print summary or code |
| `jit/requirements.txt` | `capstone` |

Run: `python3 jit/kd_daemon.py [--config policy.json] [--state FILE] [-v]`.
Policy lists (`native`, `skip`, `frontier`, `frontier_prefix`, `call_depth`,
`max_insns`) are overridable from the JSON config.
