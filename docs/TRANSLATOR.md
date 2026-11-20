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
| Calls in the `native` list (memcpy, strlen, ..., `__rcu_read_lock`, `__rcu_read_unlock`) and the `kd_` functions the kernel lists as `KD_SYM_LOCAL` | native `call` |
| Any other `kd_` function | frontier |
| Calls in `skip` (`__fentry__`, `__might_sleep`, ...) | dropped |
| Inline `cond_resched()` static-call site, patched to `xor %eax,%eax` or a NOP | `mov rax, gs:[kd_cpu.task]; test byte [rax], TIF_NEED_RESCHED`; set → frontier exit at the site, clear → the site's own instruction |
| Frontiers | exit carrying the address of the first unexecuted instruction |

`__rcu_read_lock` and `__rcu_read_unlock` are called natively on purpose:
with preemptible RCU they count in the task structure, which only code
running as that task may change, so they must count for the executor; the
kernel carries the depth over to the origin (ARCHITECTURE 6).

A plain instruction whose operand cannot be relocated becomes a frontier at
that instruction; the rest of the site stays delegable. The displacement of
a rip-relative or `%gs`-absolute operand is located by the decoder and
checked against the operand's value; with an operand-size prefix (for
example `or %ax, %gs:x(%rip)`) the decoder reports a 2-byte displacement
although the encoding carries the usual disp32 behind ModRM, and the
translator finds it there. Before this, one such instruction anywhere in
the reachable code (it sits in `__raise_softirq_irqoff`) made the whole
site fail, which kept every section with an `rcu_read_unlock()` from being
delegated.

For kernels whose own locks are kdlock in part (the mmap lock), sections
run kernel code that takes native locks. Native spinlock acquires and
releases are called natively (no task identity; the preempt-count change is
moved to the origin as usual). Native sleeping-lock acquires
(`mutex_lock*`, `down_read*`, `down_write*`, ...), TLB shootdowns and
cross-CPU calls (`flush_tlb_mm_range`, `smp_call_function_many_cond`, ...),
`switch_mm*`, `__cond_resched` and `synchronize_rcu*` are frontiers: their
slow paths prepare to sleep for the task, act on "this CPU", or wait for
other CPUs, among them the origin's.

**Scheduling points patched out of the text.** With `preempt=full`
(PREEMPT_DYNAMIC), the kernel patches every inline `cond_resched()` call to
`cs cs cs xor %eax,%eax`, so no call to `__cond_resched` is left to
classify. Code such as `zap_pmd_range()` then relies on preemption instead:
`zap_pte_range()` stops when `need_resched()` is true, and the caller
retries the same address after `cond_resched()`. An executor runs the
session with preemption off, so a delegated `brk()` shrink spun there for
37 minutes with two mmap_lock writers queued behind it
(`bench/results/kdclaude/kdall-deleg-20261117-64cpu/`, section 3).

- **Finding the sites:** `KernelView.static_call_sites()` reads them from
  the kernel's static-call site tables, starting at the key `__SCK__name`.
  That covers the core kernel and every module, and leaves out init text.
- **Copying them:** each site of the calls in `frontier_static_call`
  (`cond_resched`) is copied behind a test of the origin's
  `TIF_NEED_RESCHED`, read through the redirected task (row above). The
  copy ends there exactly when native code would schedule, and goes on
  otherwise. A site patched to a real call stays a frontier.
- **Not included:** `might_resched` (from `might_sleep()` and
  `might_alloc()`). Nothing waits there for `need_resched` to clear, and as
  a frontier it ended every delegated `mmap()` and `munmap()` at its first
  slab allocation.
- **How it was established:** an unconditional frontier at the
  `cond_resched()` sites handed back about half of all brk1 sections.
  brk1 at 64 threads fell to 0.54 of no delegation, and with the check
  it is at 1.10.

The mmap paths need images of about 50 000 instructions after learning,
and the per-CPU regions (section 3a) add their code to that; `max_insns`
is 250 000 by default.

Handbacks for reasons the translator cannot learn are reported as
`KD_EV_HANDBACK` events (256 per image) and counted by reason in debugfs
(`hb_frontier`, `hb_miss`, `hb_acquire`, `hb_downgrade`, `hb_other`); the
daemon logs them with `-v`. A handback at a downgrade (`kd_vdown=0`) counts
as useful for the site's usefulness account: the write part ran on the
combiner. A handback of the read part after a downgrade the combiner kept
(`kd_vdown=1`, the default; counter `vdown_hb`) counts as a handback since
2026-11-20: a `munmap` of mapped pages always ends that way, at the TLB
flush, and delegating it loses 7 to 12% against not delegating it
(LevelDB with a thrashing table cache, 2.4 M sections in 20 s of which
0.2% completed; `kd_exec_one()` has the numbers and
`bench/results/kdclaude/plain-20261119-64cpu/` the runs).

A site that the kernel switched off (most executions handed back) is
switched on again by the kernel after a wait, 1 s at first and doubled
with each switch-off in a row up to 4 s (`kd_site_retry()`, counter
`site_retry`; up to 64 s until 2026-11-20). What a site executes changes
with the workload: `mmap` and `munmap` were switched off by a test that
unmaps touched memory and stayed off for mmap1 until build #71; with the
short wait the `munmap` site follows the workload, off for one that unmaps
mapped pages and on within seconds for one whose sections complete.

The daemon's stored knowledge is keyed by release and build (`uname -r`
and `uname -v`). It is addresses; a rebuild under the same release moves
the text, and until build #70 the knowledge of earlier builds was
republished as images for addresses that were no longer lock calls.

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
start as `MISS_CODE` exits. At most `max_insns` (250000) instructions go into
one image. Known return addresses (callers inside the image) feed the `ret`
chains. Indirect branches start with an empty chain.

The site's own code is decoded first. Learned code roots and return
targets come after it, each again up to `call_depth` deep, in whatever
budget is left. A root that no longer fits stays a `MISS_CODE` exit. When
learned roots came first, the mmap and brk sites used up the budget before
their own code was reached, after about 20-60 learned roots. The build then
failed ("cannot decode site"), the daemon gave the site up, and the kernel
kept running the image it had.

## 3a. Per-CPU regions

The copy runs on the executor's CPU, so its per-CPU accesses are the
executor's (only task identity is redirected, section 2). That is right as
long as a stretch of code that depends on staying on one CPU also ends on
that CPU. Code that derives the CPU's identity (`this_cpu_ptr()` reads
`this_cpu_off`, `smp_processor_id()` reads `cpu_number`) relies on it until
it enables preemption or interrupts again: it keeps the pointer in
registers, and a local lock (`local_trylock_t`) marks its acquisition in that
CPU's memory and is released through a pointer derived again. An exit in
between moves the rest to another CPU, the origin's after a handback or
another combiner's after a published nested acquisition. Before this
analysis, brk1 handbacks at misses inside memcg's `obj_stock` region left
its `acquired` byte set on 57 of 64 CPUs for the rest of the boot
(`bench/results/kdclaude/appgrid-20261118-64cpu/`, section 6).

`Translator._pcpu_spans()` runs after discovery:

* **Region edges.** An identity read starts a region. Increments of
  `%gs:__preempt_count` and `cli` open a level, decrements, `sti` and `popf`
  close one; so do the `_irq`/`_irqsave`/`_bh` lock calls and their
  releases (`_lock_level()`), and a branch around `sti`
  (`local_irq_restore()`) closes it on both paths.
* **Walk.** Interprocedural through callee summaries per (entry, level,
  depth). A callee returns at the level it was called at. Whether a callee
  released the region is often decided by a result the walk does not
  follow (a failed `local_trylock()`), and summing both branches would leave
  regions open on paths that cannot run. In the read's own function a close
  ends the path, and its return continues in its callers within the image.
  At the site's own function the lock class decides: a sleepable-class
  section runs preemptibly (no region is open there), a spin-class section
  is itself one. Inside a callee a close does not end the walk (the slab
  sheaf helpers drop and take their lock again and return with it), but
  exits and calls are not followed while closed.
* **Not exits:** native helpers; spin-class releases (whether one releases
  the root is only known at run time; `kd_exec_one()` counts a completion
  with the section's preempt count or IRQ-off still raised as
  `done_in_region`); `preempt_schedule*()` calls, which in the copy are never
  reached because the executor's `KD_EXEC_PIN` keeps the count above zero;
  noreturn calls (`__stack_chk_fail`, `ud2`); reporting paths (printk, the
  UBSAN handlers, the WARN `ud1` trap, `bad_page`, kfence and slab
  out-of-memory reports, `_REPORT`): a handback inside a report can still
  move a region, only after a report. Indirect calls are walked through their
  learned targets (`pcpu_ind_exits`).
* **Nested lock calls** inside a region call the native lock function
  instead of its `*_jit` entry, so a contended one waits on the executor
  (`kd_cpu.busy` stops it from publishing) instead of continuing on another
  combiner.
* **Policy.** An exit found in the read's own function
  (`pcpu_near_depth`, 0) makes the read a frontier: the origin derives its
  own identity there. Deeper exits stay in the copy and carry `KD_X_REGION`;
  `kd_exec_one()` counts one taken with the section's preempt count or
  IRQ-off raised as `hb_region` (an upper bound: an inner lock held at the
  exit counts too). Region code is decoded `pcpu_walk_depth` (4) calls deep
  whatever `call_depth` says, so regions do not miss there. The analysis is
  repeated until no region changes and no new read turns up. With `-v` the
  daemon prints each per-CPU frontier and its reason.
* **Why not every exit:** without value analysis the walk cannot tell that
  a slab or memcg slow path runs only after the lock was dropped. With every
  exit a frontier (`pcpu_near_depth: null`) or the depth 1-2 tried first,
  the slab and `obj_stock` regions became frontiers at every vma
  allocation and the mmap sites were switched off: in the per-CPU check
  (64 threads, 10 s each) mmap1 and mmap2 delegated 0 sections and brk1
  451 362, against 11.29 M, 11.22 M and 14.09 M with this policy
  (`bench/results/kdclaude/appgrid-20261118-64cpu/`, section 8).
* **Limit:** the far exits are not proven unreachable with a region open.
  `hb_region` shows whether any was taken; runs report it with the
  per-CPU lock bytes (`pcpu_check.sh`).

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
* An allow list (`--allow FILE`, fnmatch patterns over function names, one
  per line) limits which sites get images. A site in a function that matches
  no pattern is never built, and its waiters queue plainly. The refused sites
  are listed when the daemon exits. This is how delegation is switched on
  lock user by lock user in a kernel where every lock is a kdlock
  (`bench/allow/`).
* Images stay loaded when the daemon exits, and the kernel asks only for
  sites without an image. To start a measurement from new images, drop the
  old ones (`Device.site_drop()`, as `deleg_mm.sh` does).
* `KD_EV_REQUEST` always triggers a build; the kernel sends it only for sites
  without an image. With adaptive delegation that is a site whose lock has
  reached delegation mode: a lock that stays in plain mode never asks.
* Known weakness: the state file is keyed by address and kernel release. A
  module loaded at another address after a reboot leaves entries for
  addresses that now hold other code; the daemon builds images for them
  that no waiter ever looks up (or fails to, with a logged error). They are
  dropped only when their text range goes away while the daemon runs.

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

Run: `python3 jit/kd_daemon.py [--config policy.json] [--state FILE] [--allow FILE] [-v]`.
Policy lists and values (`native`, `skip`, `frontier`, `frontier_prefix`,
`frontier_static_call`, `need_resched_offset`, `need_resched_mask`,
`call_depth`, `max_insns`, `pcpu_near_depth`, `pcpu_walk_depth`,
`pcpu_ind_exits`) are overridable from the JSON config.
