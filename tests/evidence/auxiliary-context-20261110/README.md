# Auxiliary context and GS source audit, 2026-11-10

This is read-only target-source/configuration inspection. It supports the
ordinary IRQ and scheduler save/restore route for the selected task-owned
auxiliary design and records concrete diagnostic and mitigation limits. It is
not auxiliary-stack execution, an IRQ/preemption stress test, a stack-usage
measurement, a linked-candidate GS proof or a fixture pass. The module's
`auxiliary_contract=1` assertion does not establish those results.

## Inputs and retained readback

The candidate is
`/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/{source,build}`,
using the source/package identities recorded in
[the core compilation receipt](../kernel-core-20261110/README.md). The kdlock
core snapshot is `c6becf81987ae29a97000a641d76a0ff2e300860`; fixture source
was separately committed as `a4c7f2a1`. The vendor-derived tree includes the
protected older kdlock1 source changes and the five new integration edits; it
is not a pristine vendor tree.

`target-source-readback.txt` is the retained stdout from bounded read-only SSH
commands at 14:49:25 UTC. It starts with the actual running release, candidate
configuration SHA256 and hashes of every inspected vendor source. The selected
candidate configuration is
`31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483`.
It matches the separately retained `kernel-core-20261110/config-after`.
Source excerpts retain their original file line numbers; the file/path/hash
index precedes them. No candidate `vmlinux` or `System.map` existed at this
readback. The full build was parent-owned and running separately.

The configuration has `THREAD_INFO_IN_TASK`, `VMAP_STACK`,
`SCHED_STACK_END_CHECK`, frame pointers and `UNWINDER_FRAME_POINTER` enabled;
ORC and `DEBUG_ENTRY` are disabled. It has dynamic/lazy preemption, its own
softirq stack, normal retpoline/return-thunk/call-depth options and stack
protector enabled; kernel IBT is disabled. The currently running older kernel
reported eIBRS, `retbleed: Not affected`, `nokaslr`, and the `nop` tracer.
Those are observations of that older boot, not the future candidate boot.

## Concrete stack path and its limits

- `arch/x86/include/asm/current.h:16–25` gets current from a GS per-CPU
  `current_task` symbol. With `THREAD_INFO_IN_TASK`, task identity does not
  derive from masking the auxiliary RSP.
- `arch/x86/entry/entry_64.S:178–220` saves the actual RSP in
  `task->thread.sp` and restores it on scheduling. It does not require that RSP
  numerically reside in `task->stack`. This supports saving a blocked auxiliary
  C chain without moving or copying W's source packet.
- `entry_64.S:1006–1071` keeps the interrupted kernel-mode register frame on
  the interrupted stack; only user-mode entry takes the `sync_regs` path.
  `arch/x86/include/asm/irq_stack.h:84–105,146–173` saves that RSP in the IRQ
  stack link, runs the handler on the per-CPU IRQ stack and restores RSP.
  Thus the inspected ordinary IRQ route can return to auxiliary RSP.
- `kernel/entry/common.c:187–197` tests `on_thread_stack()` only under
  `CONFIG_DEBUG_ENTRY`. That option is off here. This audit does not claim that
  every IRQ return inevitably warns on this target.

The private entry changes RSP before source publication, and the final native
restore reinstates canonical source IP/SP on W. The numerical preflight and
retained task/source backing remain necessary. They do not establish every
architecture entry, fault, unwinder, instrumentation or stack-size property.
NMI/IST/FRED/paravirtual entry completeness was not established by this audit.

There are two concrete remaining diagnostic limits:

1. `arch/x86/kernel/dumpstack.c:31–45` recognizes only `task->stack` as its task
   stack. `dumpstack_64.c:170–188,195–203` additionally recognizes exception,
   IRQ and entry stacks, with no auxiliary range. Its frame-pointer walker
   (`unwind_frame.c:219–234,373–417`) therefore cannot describe this auxiliary
   chain as a recognized stack. Private `include/mutex_entry.S:35–37` installs
   no kernel-recognized auxiliary stack link/type. Traceback completeness on
   auxiliary control is unavailable; a successful mechanism run would not
   establish it. This diagnostic limit alone is not a refusal of the focused
   mechanism run.
2. `include/linux/sched/task_stack.h:21–35,84–87` and
   `kernel/sched/core.c:5863–5871` check the original task stack's end magic,
   not auxiliary backing. `kernel/task_storage.c` allocates auxiliary backing
   with `vmalloc` and checks its extent; it does not extend that stack-end
   check or prove maximum recursive C/IRQ usage. The fixture's 128-KiB backing
   and 32-KiB declared control requirement are finite test inputs, not measured
   high-water marks or a general overflow/context result.

The selected source/JIT separation remains intact: original W waits on its own
auxiliary backing, a different physical executor uses its own native/control
stack, and virtual source SP addresses W's retained source stack. No TCLock
borrowed-stack body engine or packet copy was introduced by this audit.

## Compiler and return-mitigation boundary

The retained actual `kernel/mutex.o` command uses the normal target flags,
including `-mindirect-branch=thunk-extern`,
`-mindirect-branch-register`, `-mindirect-branch-cs-prefix`,
`-mfunction-return=thunk-extern`, frame pointers and no red zone. The fixture's
Kbuild adds no branch/return-mitigation override. Its actual module has not been
built in this receipt, so actual CALL/thunk forms remain for its later ELF and
exported-byte disassembly.

`include/native_resume.S:36`, `include/mutex_api.S` and per-image
`include/wrapper.S:94` contain handwritten/generated raw returns; the prepared
entry and wrapper also contain indirect control transfers. Their complete
mitigation coverage is not established by ordinary C compiler flags. Compiled
call-depth availability is not proof that the future boot selected it. General
flags/SIMD still use AS01, not a new equivalence result. The runner preserves
native-frontier/nonobservation outcomes when normal compiler thunk forms prevent
ordinary indirect-CALL learning; it does not alter the kernel's mitigations to
manufacture that evidence.

## Exact current-task GS proof procedure

`setup_percpu.c:163–168` sets each CPU's offset to
`pcpu_base_addr - __per_cpu_start + pcpu_unit_offsets[cpu]`.
`processor.h:435–443` supplies this as `cpu_kernelmode_gs_base`, and
`cpu/common.c:809` writes it to `MSR_GS_BASE`. The source identity is therefore
GS base plus the actual linked per-CPU symbol operand, not GS base plus a
second subtraction of `__per_cpu_start`.

The old retained ELF/System.map is a method example only:

```text
__per_cpu_start          0xffffffff841f0000
current_task            0xffffffff84208018
const_current_task      0xffffffff84208018
.data..percpu section VA 0xffffffff841f0000
```

The full current-task operand is `0xffffffff84208018` in that old image;
`0x18018` is the intra-section difference and is not its GS operand.
`vmlinux.lds.S:46` makes `const_current_task` an exact linker alias.
The original KD lowering compares the decoded constant modulo its address
width and substitutes the supplied immutable original-task pointer for this
exact GS access.

For the newly linked and actually booted kernel:

1. Retain its `vmlinux`, `System.map`, `.config`, release, Build ID, hashes and
   actual boot command line. Read both current-task symbol values and the
   per-CPU section from that exact ELF, checking the linker alias.
2. With actually verified `nokaslr`, use the full linked `current_task` value
   as the unsigned 64-bit GS configuration input. With relocation enabled,
   establish the actual relocated runtime symbol/operand instead; an unrelocated
   ELF address is not sufficient by itself.
3. Check the actual fixture module's current-task GS relocation and loaded
   source instruction against that same full operand, including the signed
   disp32/64-bit normalization. Keep the kernel/configuration identity receipt
   with the runner's supplied GS input before publishing an image.

The old example must never populate the new candidate's GS proof. No new linked
symbol value or live GS-load correctness is claimed here.

The raw readback preserves `nl`'s trailing tabs on empty source lines and the
original compile-command whitespace. Git's whitespace checker reports those
literal receipt bytes; they were not normalized or changed into a source pass.
