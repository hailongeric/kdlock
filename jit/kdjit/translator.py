# SPDX-License-Identifier: GPL-2.0
"""Critical-section translator.

Produces, for one lock call site, a relocated copy of the code that follows
it. The copy runs on the combiner's CPU with the stack pointer on the
origin's stack, so almost every instruction is copied byte for byte. Only
these are rewritten:

  control flow      Direct branches go to the copied target. A call pushes
                    the *source* return address and jumps, so the origin's
                    stack always holds ordinary kernel addresses and the
                    origin can take over at any instruction. Returns and
                    indirect branches compare against known targets.
  rip-relative      Displacements are recomputed for the new location.
  task identity     %gs accesses to current_task / stack canary / stack top
                    are redirected to kd_cpu fields holding the origin's
                    values. All other per-CPU accesses stay with the CPU
                    that physically executes the code.
  lock API          A release call first compares its argument with the
                    session root; equal means the section is complete. If
                    the section is itself running nested under outer
                    sessions, any other release leaves generated code so
                    the executor can tell outer roots from ordinary locks.
                    Spin-class acquires call a kernel entry that returns
                    normally when uncontended and leaves generated code,
                    with the continuation stored, when contended.
                    Sleeping-family acquires always leave generated code.
  frontiers         Instructions or callees only the origin may execute end
                    the path with an exit carrying their own address. This
                    includes voluntary scheduling points whose static call
                    is patched to something that no longer looks like one.

Every exit records the address of the first source instruction that was not
executed. The origin resumes there natively; nothing is replayed.

Assumptions (stated, not verified here): flags are dead across call, ret
and indirect branches; kernel text addresses fit a sign-extended imm32; the
image is loaded within rel32 range of kernel text.
"""

import re
import struct
from collections import defaultdict

import capstone
from capstone import x86_const as X

from .kernel import (MASK64, KD_X_REGION, KD_SYM_ACQUIRE, KD_SYM_LOCAL, KD_SYM_NESTED, KD_SYM_UNLOCK,
                     KD_X_ACQUIRE,
                     KD_X_FRONTIER, KD_X_MISS_CODE, KD_X_MISS_IND, KD_X_MISS_RET, KD_X_TAIL,
                     KD_X_UNLOCK, KD_X_UNLOCK_ANC)

# ---- policy -----------------------------------------------------------------

DEFAULT_CONFIG = {
    # Static discovery follows this many direct-call edges from the site.
    # Deeper callees start as learnable exits.
    "call_depth": 5,
    "max_insns": 250000,
    # Per-CPU regions (Translator._pcpu_spans). An exit found in the
    # region's own function or at most this many calls below it makes the
    # region's start a frontier; deeper ones (slow paths: a slab page freed
    # under a sheaf flush, kfence, memcg teardown) stay in the copy as
    # KD_X_REGION exits, which kd_exec_one() counts as hb_region when one
    # is taken with the region open. None makes every exit a frontier.
    "pcpu_near_depth": 0,
    # The walk decodes and follows a region this many calls deep (its code
    # is decoded whatever "call_depth" says, so the region does not miss
    # there) and steps over deeper calls; their exits are left to the copy.
    "pcpu_walk_depth": 4,
    # An indirect call inside a region is walked through its learned
    # targets; its unknown-target exit (a target never seen before) is not
    # treated as an exit of the region (KD_X_REGION covers it at run time).
    # True treats it as an exit like any other.
    "pcpu_ind_exits": False,
    # Callees run natively: leaf helpers that do not depend on the current
    # task or on return addresses. The kd_ functions that may be called
    # natively come from the kernel's own list (KD_SYM_LOCAL); they act for
    # the origin by themselves. Any other kd_ function is a frontier.
    "native": [
        "memcpy", "__memcpy", "memset", "__memset", "memmove", "__memmove",
        "memcmp", "memchr", "memchr_inv", "strlen", "strnlen", "strcmp", "strncmp",
        "strchr", "strrchr", "__sw_hweight32", "__sw_hweight64",
        "_find_first_bit", "_find_next_bit", "_find_first_zero_bit",
        "_find_next_zero_bit", "__list_add_valid_or_report",
        "__list_del_entry_valid_or_report",
        # Preemptible RCU counts read-side nesting in the task structure,
        # which only code running as that task may change. Called natively
        # they count for the executor; the kernel carries the depth over to
        # the origin (kd_rcu_sync() in kd_core.c).
        "__rcu_read_lock", "__rcu_read_unlock",
        # Native spinlocks: no task identity, and the preempt-count change
        # is measured and moved to the origin like any other. Calling them
        # spares copying the queued-spinlock slow path into every image.
        "_raw_spin_lock", "_raw_spin_lock_irq", "_raw_spin_lock_irqsave",
        "_raw_spin_lock_bh", "_raw_spin_unlock", "_raw_spin_unlock_irq",
        "_raw_spin_unlock_irqrestore", "_raw_spin_unlock_bh",
        "_raw_spin_trylock", "_raw_read_lock", "_raw_read_unlock",
        "_raw_write_lock", "_raw_write_unlock", "queued_spin_lock_slowpath",
        "native_queued_spin_lock_slowpath",
    ],
    # Calls dropped from the copy.
    "skip": ["__fentry__", "__might_sleep", "__might_resched", "__might_fault"],
    # Callees only the origin may execute: anything that can switch tasks,
    # touch user memory, or not return.
    "frontier": [
        "schedule", "__schedule", "schedule_timeout", "schedule_preempt_disabled",
        "schedule_hrtimeout", "schedule_hrtimeout_range", "schedule_hrtimeout_range_clock",
        "preempt_schedule", "preempt_schedule_notrace", "preempt_schedule_common",
        "preempt_schedule_irq", "io_schedule", "io_schedule_timeout", "yield",
        "msleep", "msleep_interruptible", "usleep_range_state",
        "__switch_to", "__switch_to_asm", "do_exit", "make_task_dead", "panic",
        "__stack_chk_fail", "_copy_from_user", "_copy_to_user",
        "rep_movs_alternative", "rep_stos_alternative",
        "strncpy_from_user", "strnlen_user",
        # Native sleeping locks. Their fast path is fine on any CPU, but
        # their slow path prepares to sleep for the task (task state, wait
        # entries, optimistic spinning on per-CPU queue nodes) before it
        # reaches schedule(); the origin does all of that itself.
        "mutex_lock", "mutex_lock_interruptible", "mutex_lock_killable",
        "mutex_lock_io", "down_read", "down_read_killable",
        "down_read_interruptible", "down_write", "down_write_killable",
        "rt_mutex_lock", "down", "down_interruptible", "down_killable",
        "percpu_down_write", "__percpu_down_read",
        # TLB shootdown and cross-CPU calls. They act on "this CPU" (the
        # executor) and may wait for other CPUs, among them the origin's,
        # which may be waiting with interrupts off for a spin-class lock.
        "flush_tlb_mm_range", "flush_tlb_kernel_range", "flush_tlb_multi",
        "native_flush_tlb_multi", "arch_tlbbatch_flush", "flush_tlb_all",
        "smp_call_function_many_cond", "smp_call_function_single",
        "smp_call_function_any", "on_each_cpu_cond_mask",
        "switch_mm", "switch_mm_irqs_off", "leave_mm",
        "__cond_resched", "synchronize_rcu", "synchronize_rcu_expedited",
        # Static call trampoline of the scheduling point below.
        "__SCT__cond_resched",
    ],
    # Static calls whose inline call sites are scheduling points, whatever
    # they are patched to. With preempt=full, cond_resched() sites are
    # patched to `xor %eax,%eax`: nothing to see in the text, and the code
    # relies on preemption at the next preempt_enable() instead. An executor
    # runs the whole session with preemption off, so a loop that stops on
    # need_resched() and retries after cond_resched() never progresses there
    # (zap_pte_range() under a delegated brk() livelocked this way).
    #
    # Such a site ends the copy only when the origin has TIF_NEED_RESCHED
    # set; the origin then takes over there and is scheduled as usual.
    # Otherwise the copy goes on through the patched instruction, as native
    # cond_resched() does when nothing needs to run. (An unconditional exit
    # handed back about half of all brk() shrinks, at the cond_resched() of
    # zap_pmd_range().) A site patched to a real call stays a frontier.
    # Not included:
    # - might_resched (might_sleep(), might_alloc()): nothing waits there for
    #   need_resched to clear, and as a frontier it ended every delegated
    #   mmap() and munmap() at their first slab allocation. With voluntary
    #   preemption its sites call __cond_resched, a frontier by name.
    # - preempt_enable()'s preempt_schedule sites: they are only reached at
    #   preempt count 0, and their thunk calls preempt_schedule.
    "frontier_static_call": ["cond_resched"],
    # need_resched() as the kernel compiles it: the thread_info flags word
    # at offset 0 of the task (THREAD_INFO_IN_TASK) and TIF_NEED_RESCHED
    # (bit 4 of the generic TIF bits). Taken from the live text of
    # zap_pte_range() in 7.0.0-38: mov %gs:current_task,%rax;
    # mov (%rax),%rax; test $0x10,%al.
    "need_resched_offset": 0,
    "need_resched_mask": 0x10,
    "frontier_prefix": [
        "schedule_timeout_", "wait_for_completion", "__get_user_", "__put_user_",
        "copy_user_", "__copy_user_", "kd_jit_", "kd_resume",
    ],
}

_FRONTIER_INSNS = (
    "STAC", "SWAPGS", "WRMSR", "IRET", "IRETD", "IRETQ", "SYSRET", "SYSRETQ",
    "SYSCALL", "SYSENTER", "SYSEXIT", "SYSEXITQ", "HLT", "INT", "INT1", "INT3",
    "INTO", "UD0", "UD1", "UD2", "UD2B", "WRGSBASE", "WRFSBASE", "RDGSBASE",
    "RDFSBASE", "INVLPG", "INVPCID", "LGDT", "LIDT", "LLDT", "LTR", "RETF",
    "RETFQ", "LCALL", "LJMP", "MWAIT", "MONITOR", "VMLAUNCH", "VMRESUME",
    "VMCALL", "VMMCALL", "XSAVE", "XSAVE64", "XSAVEC", "XSAVEC64", "XSAVEOPT",
    "XSAVEOPT64", "XSAVES", "XSAVES64", "XRSTOR", "XRSTOR64", "XRSTORS",
    "XRSTORS64", "FXSAVE", "FXSAVE64", "FXRSTOR", "FXRSTOR64",
)
FRONTIER_IDS = {getattr(X, "X86_INS_" + n) for n in _FRONTIER_INSNS if hasattr(X, "X86_INS_" + n)}

_SHORT_ONLY = ("JCXZ", "JECXZ", "JRCXZ", "LOOP", "LOOPE", "LOOPNE")
SHORT_ONLY_IDS = {getattr(X, "X86_INS_" + n) for n in _SHORT_ONLY if hasattr(X, "X86_INS_" + n)}

_IND_THUNK = re.compile(r"^__x86_indirect_(?:call_|jump_|its_)?thunk_(r[a-z0-9]+)$")
_RET_THUNK = re.compile(r"return_thunk$")

_REG_NUM = {"rax": 0, "rcx": 1, "rdx": 2, "rbx": 3, "rsp": 4, "rbp": 5, "rsi": 6, "rdi": 7,
            "r8": 8, "r9": 9, "r10": 10, "r11": 11, "r12": 12, "r13": 13, "r14": 14, "r15": 15}

_LEGACY_PREFIXES = frozenset((0x26, 0x2E, 0x36, 0x3E, 0x64, 0x65, 0x66, 0x67, 0xF0, 0xF2, 0xF3))


class TranslationError(Exception):
    pass


# ---- encoding helpers ---------------------------------------------------------

def _s32(value):
    if not -(1 << 31) <= value < (1 << 31):
        raise TranslationError("value %#x does not fit 32 bits" % value)
    return struct.pack("<i", value)


def _rel32(target, end):
    return _s32(target - end)


def _signed(value):
    value &= MASK64
    return value - (1 << 64) if value >> 63 else value


def _fits_simm32(value):
    return -(1 << 31) <= _signed(value) < (1 << 31)


def _simm32(value):
    """imm32 that sign-extends to the 64-bit value."""
    return _s32(_signed(value))


def _gs_abs_modrm(disp):
    """ModRM+SIB+disp32 for an absolute %gs:disp32 operand with reg field 0."""
    return b"\x04\x25" + _simm32(disp)


class Asm:
    """Two-section image builder with late-bound labels.

    Every item has a fixed size, so label addresses are known before any
    byte is produced. The cold section follows the hot one and holds exit
    stubs and landing pads.
    """

    def __init__(self):
        self.sec = ([], [])
        self.labels = {}

    def label(self, name, cold=False):
        self.labels[name] = (int(cold), len(self.sec[int(cold)]))

    def emit(self, size, fn, cold=False):
        self.sec[int(cold)].append((size, fn))

    def raw(self, data, cold=False):
        data = bytes(data)
        self.emit(len(data), lambda pc, labels: data, cold)

    def size(self):
        return sum(size for sec in self.sec for size, _ in sec)

    def link(self, base):
        starts = ([], [])
        pc = base
        for s in (0, 1):
            for size, _ in self.sec[s]:
                starts[s].append(pc)
                pc += size
            starts[s].append(pc)
        labels = {name: starts[s][i] for name, (s, i) in self.labels.items()}
        out = bytearray()
        for s in (0, 1):
            for (size, fn), at in zip(self.sec[s], starts[s]):
                data = fn(at, labels)
                if len(data) != size:
                    raise TranslationError("item at %#x changed size" % at)
                out += data
        return bytes(out), labels


def _loc(addr):
    return "loc_%x" % addr


class Ins:
    __slots__ = ("addr", "size", "raw", "kind", "target", "op", "falls", "depth",
                 "reg", "mem", "patch", "pcpu", "plevel", "pdec", "orig")

    def __init__(self, addr, raw, depth):
        self.addr = addr
        self.size = len(raw)
        self.raw = raw
        self.kind = "plain"
        self.target = None      # direct branch/call destination
        self.op = 0             # enum kd_op for lock API calls
        self.falls = True       # execution may continue at addr + size
        self.depth = depth
        self.reg = None         # indirect branch through this register number
        self.mem = None         # indirect branch through memory: (prefixes, rex, tail, riprel_target)
        self.patch = None       # (disp_offset, new_target, absolute) for plain instructions
        self.pcpu = False       # derives this CPU's identity (per-CPU base or CPU number)
        self.plevel = 0         # +1 opens a preempt/IRQ-off region, -1 closes one
        self.orig = None        # native target of a nested-class lock call
        self.pdec = False       # decrements the preempt count (sets ZF at zero)


class Learned:
    """Cumulative runtime knowledge for one site (see kd_daemon.py)."""

    def __init__(self, code=(), ind=None, ret=None):
        self.code = set(code)                   # addresses reached but missing
        self.ind = defaultdict(set)             # branch insn -> targets
        self.ret = defaultdict(set)             # ret insn -> return addresses
        for k, v in (ind or {}).items():
            self.ind[int(k)].update(v)
        for k, v in (ret or {}).items():
            self.ret[int(k)].update(v)

    def to_json(self):
        return {"code": sorted(self.code),
                "ind": {str(k): sorted(v) for k, v in self.ind.items()},
                "ret": {str(k): sorted(v) for k, v in self.ret.items()}}

    @classmethod
    def from_json(cls, data):
        return cls(data.get("code", ()), data.get("ind"), data.get("ret"))


class Translator:
    def __init__(self, kv, info, config=None):
        self.kv = kv
        self.info = info
        self.cfg = dict(DEFAULT_CONFIG)
        self.cfg.update(config or {})
        self.native = set(self.cfg["native"])
        self.skip = set(self.cfg["skip"])
        self.frontier = set(self.cfg["frontier"])
        self.frontier_prefix = tuple(self.cfg["frontier_prefix"])
        self.subst = info.gs_substitutions()
        # Per-CPU spans (_pcpu_spans): reads of these give the executor's CPU
        # identity, and writes to the preempt count open and close regions.
        self.pcpu_src = {a for a in (kv.addr_of.get("this_cpu_off"),
                                     kv.addr_of.get("cpu_number")) if a}
        self.preempt_count = kv.addr_of.get("__preempt_count")
        self.region_addrs = set()
        self.pcpu_starts = set()
        self.pcpu_far = 0
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True
        for name in ("pcpu_task", "pcpu_canary", "pcpu_stack_top", "pcpu_root",
                     "pcpu_exit_ip", "pcpu_resume", "pcpu_aux", "pcpu_exit_code",
                     "pcpu_anc"):
            if not _fits_simm32(getattr(info, name)):
                raise TranslationError("kd_cpu is not addressable with a 32-bit %gs displacement")

    # ---- target classification ------------------------------------------------

    def classify(self, target):
        """What a control transfer to `target` means for the copy.

        Returns (class, detail): unlock/acquire (detail = kd_op), nested
        (detail = entry to call instead), native, skip, frontier, ind
        (detail = register number), ret, or code.
        """
        sym = self.info.syms.get(target)
        if sym:
            cls, op, alt = sym
            if cls == KD_SYM_UNLOCK:
                return "unlock", op
            if cls == KD_SYM_ACQUIRE:
                return "acquire", op
            if cls == KD_SYM_NESTED:
                return "nested", alt
            if cls == KD_SYM_LOCAL:
                return "native", 0
        names = self.kv.names(target)
        for name in names:
            if name in self.skip:
                return "skip", 0
            if name in self.frontier or name.startswith(self.frontier_prefix):
                return "frontier", 0
            m = _IND_THUNK.match(name)
            if m and m.group(1) in _REG_NUM:
                return "ind", _REG_NUM[m.group(1)]
            if _RET_THUNK.search(name):
                return "ret", 0
        for name in names:
            if name in self.native:
                return "native", 0
            if name.startswith("kd_"):
                return "frontier", 0
        if not self.kv.in_text(target):
            reg = self._thunk_reg(target)
            if reg is not None:
                return "ind", reg
            return "frontier", 0
        return "code", 0

    def _thunk_reg(self, target):
        """Register of an unnamed indirect-branch thunk at target, or None.

        Modules get their indirect-branch (ITS) thunks in separately
        allocated pages without symbols. Such a thunk is a single
        `jmp *%reg`, so a call or jump to it is an indirect branch through
        that register, which the copy handles like any other.
        """
        try:
            raw = self.kv.read(target, 3)
        except OSError:
            return None
        cs = next(self.md.disasm(raw, target, 1), None)
        if cs is None or cs.id != X.X86_INS_JMP or len(cs.operands) != 1:
            return None
        op = cs.operands[0]
        if op.type != X.X86_OP_REG:
            return None
        return _REG_NUM.get(cs.reg_name(op.reg))

    # ---- decoding -------------------------------------------------------------

    def _decode_one(self, addr, depth, learned):
        try:
            raw = self.kv.read(addr, 15)
        except OSError:
            return None, ()
        cs = next(self.md.disasm(raw, addr, 1), None)
        if cs is None:
            return None, ()
        ins = Ins(addr, bytes(cs.bytes), depth)
        nxt = addr + ins.size
        succs = []

        def frontier():
            ins.kind = "frontier"
            ins.falls = False
            return ins, ()

        # Text that may go away or is unknown, and instructions with a
        # fault fixup (found by their own address), stay with the origin.
        if not self.kv.in_text(addr) or self.kv.has_fixup(addr) or cs.id in FRONTIER_IDS:
            return frontier()
        # A scheduling point, whatever its static call is patched to. Patched
        # to a real call, it is a frontier. Patched to `xor %eax,%eax` or a
        # NOP, it is copied behind a check of the origin's need_resched
        # flag (_resched_point). Neither form has an operand to relocate.
        if addr in self.sched_sites:
            if cs.id == X.X86_INS_CALL or cs.id == X.X86_INS_JMP:
                return frontier()
            if cs.id not in (X.X86_INS_XOR, X.X86_INS_NOP) or self._plain_patch(cs) is not None:
                return frontier()
            ins.kind = "resched_point"
            return ins, ()
        for op in cs.operands:
            if op.type == X.X86_OP_REG and cs.reg_name(op.reg)[:2] in ("cr", "dr"):
                return frontier()

        ops = cs.operands
        is_call = cs.id == X.X86_INS_CALL
        is_jmp = cs.id == X.X86_INS_JMP

        if is_call or is_jmp:
            ins.falls = False
            if ops and ops[0].type == X.X86_OP_IMM:
                target = ops[0].imm & MASK64
                cls, detail = self.classify(target)
                ins.target = target
                if cls == "frontier":
                    return frontier()
                if cls == "skip":
                    if is_call:
                        ins.kind = "skip"
                        ins.falls = True
                    else:
                        ins.kind = "ret"
                elif cls == "unlock":
                    ins.kind = "unlock_call" if is_call else "unlock_tail"
                    ins.op = detail
                    ins.falls = is_call
                elif cls == "acquire":
                    ins.kind = "acquire_call" if is_call else "acquire_tail"
                    ins.op = detail
                    if is_call:
                        succs.append((nxt, depth))
                elif cls == "native":
                    ins.kind = "native_call" if is_call else "native_tail"
                    ins.falls = is_call
                elif cls == "nested":
                    # A real call, so a contended exit finds its continuation
                    # (the return address in this image) on the stack.
                    ins.kind = "native_call" if is_call else "native_tail"
                    ins.orig = target
                    ins.target = detail
                    ins.falls = is_call
                elif cls == "ret":
                    ins.kind = "ret"
                elif cls == "ind":
                    ins.kind = "ind_call" if is_call else "ind_jmp"
                    ins.reg = detail
                elif is_call:
                    ins.kind = "call"
                    succs.append((nxt, depth))
                    self.call_edges.append((nxt, target))
                    if depth < self.cfg["call_depth"] or target in learned.code:
                        succs.append((target, depth + 1))
                else:
                    ins.kind = "jmp"
                    succs.append((target, depth))
                    self._note_tail(addr, target)
            elif ops and ops[0].type == X.X86_OP_REG:
                reg = _REG_NUM.get(cs.reg_name(ops[0].reg))
                if reg is None:
                    return frontier()
                ins.kind = "ind_call" if is_call else "ind_jmp"
                ins.reg = reg
            elif ops and ops[0].type == X.X86_OP_MEM:
                ins.kind = "ind_call" if is_call else "ind_jmp"
                ins.mem = self._split_mem_branch(cs, ops[0])
                if ins.mem is None:
                    return frontier()
            else:
                return frontier()
            if ins.kind in ("ind_call", "ind_jmp"):
                if is_call:
                    succs.append((nxt, depth))
                for target in learned.ind.get(addr, ()):
                    if self.classify(target)[0] != "code":
                        continue
                    succs.append((target, depth))
                    if is_call:
                        self.call_edges.append((nxt, target))
                    else:
                        self._note_tail(addr, target)
            return ins, succs

        if cs.id in (X.X86_INS_RET, getattr(X, "X86_INS_RETQ", -1)):
            if ops:                 # ret imm16: not produced by the kernel's compilers
                return frontier()
            ins.kind = "ret"
            ins.falls = False
            return ins, ()

        if cs.id in SHORT_ONLY_IDS:
            ins.kind = "jshort"
            ins.target = ops[0].imm & MASK64
            succs.append((ins.target, depth))
            self._note_tail(addr, ins.target)
            return ins, succs

        if cs.group(X.X86_GRP_JUMP) and ops and ops[0].type == X.X86_OP_IMM:
            ins.kind = "jcc"
            ins.target = ops[0].imm & MASK64
            ins.op = self._condition_code(ins.raw)
            succs.append((ins.target, depth))
            self._note_tail(addr, ins.target)
            return ins, succs

        try:
            ins.patch = self._plain_patch(cs)
        except TranslationError:
            # An operand that cannot be relocated: the origin runs this
            # instruction, the rest of the site stays delegable.
            return frontier()
        self._pcpu_note(cs, ins)
        return ins, ()

    # Opening and closing a preempt-off or IRQ-off region, for _pcpu_spans().
    _PLEVEL = {X.X86_INS_INC: 1, X.X86_INS_DEC: -1, X.X86_INS_ADD: 1, X.X86_INS_SUB: -1}

    def _pcpu_note(self, cs, ins):
        """Mark per-CPU identity reads and preempt/IRQ region edges."""
        if cs.id == X.X86_INS_CLI:
            ins.plevel = 1
            return
        if cs.id in (X.X86_INS_STI, X.X86_INS_POPF, getattr(X, "X86_INS_POPFQ", -1)):
            ins.plevel = -1
            return
        for i, op in enumerate(cs.operands):
            if op.type != X.X86_OP_MEM or op.mem.segment != X.X86_REG_GS:
                continue
            mem = op.mem
            if mem.base == X.X86_REG_RIP:
                addr = (cs.address + cs.size + mem.disp) & MASK64
            elif mem.base == 0 and mem.index == 0:
                addr = mem.disp & MASK64
            else:
                addr = None         # %gs:(reg): a per-CPU pointer computed at run time
            # Every %gs access of the image, for gs_report(): which per-CPU
            # data a section can touch. Only the three identity variables
            # are redirected to the origin (self.subst); all the rest is the
            # executor's.
            ref = self.gs_refs.setdefault(addr, [0, 0, set()])
            ref[1 if op.access & capstone.CS_AC_WRITE else 0] += 1
            ref[2].add(self.kv.func_of(cs.address))
            if addr is None:
                continue
            if addr in self.pcpu_src and i > 0:
                ins.pcpu = True             # read: source operand
            elif addr == self.preempt_count and i == 0 and cs.id in self._PLEVEL:
                delta = self._PLEVEL[cs.id]
                if cs.id in (X.X86_INS_ADD, X.X86_INS_SUB) and len(cs.operands) > 1 \
                        and cs.operands[1].type == X.X86_OP_IMM and cs.operands[1].imm < 0:
                    delta = -delta
                ins.plevel = delta
                ins.pdec = delta < 0

    @staticmethod
    def _condition_code(raw):
        i = 0
        while raw[i] in _LEGACY_PREFIXES or 0x40 <= raw[i] <= 0x4F:
            i += 1
        if 0x70 <= raw[i] <= 0x7F:
            return raw[i] & 0x0F
        if raw[i] == 0x0F and 0x80 <= raw[i + 1] <= 0x8F:
            return raw[i + 1] & 0x0F
        raise TranslationError("unexpected conditional branch encoding %s" % raw.hex())

    def _plain_patch(self, cs):
        """Displacement fix-up for an instruction that is otherwise copied.

        Returns None, or (disp_offset, target, absolute). `absolute` means
        the displacement is the address itself (%gs:abs32) rather than
        rip-relative.
        """
        for op in cs.operands:
            if op.type != X.X86_OP_MEM:
                continue
            mem = op.mem
            if mem.base == X.X86_REG_RIP:
                target = (cs.address + cs.size + mem.disp) & MASK64
                if mem.segment == X.X86_REG_GS:
                    target = self.subst.get(target, target)
                return self._disp32_offset(cs, mem.disp, "rip-relative"), target, False
            if mem.segment == X.X86_REG_GS and mem.base == 0 and mem.index == 0:
                target = self.subst.get(mem.disp & MASK64)
                if target is not None:
                    return self._disp32_offset(cs, mem.disp, "%gs absolute"), target, True
        return None

    @staticmethod
    def _disp32_offset(cs, disp, what):
        """Offset of the 32-bit displacement of a rip-relative or absolute operand.

        The decoder's own answer is used when it names a disp32 that holds
        `disp`. With an operand-size prefix (for example
        `or %ax, %gs:x(%rip)`) it does not, although the encoding is the
        usual one: in 64-bit mode such an operand always carries a disp32,
        directly behind ModRM (rip-relative) or behind ModRM and SIB
        (absolute). The bytes are checked against `disp` before they are
        trusted.
        """
        enc = cs.encoding
        raw = bytes(cs.bytes)
        want = struct.pack("<i", _signed(disp)) if _fits_simm32(disp) else None
        cands = []
        if enc.disp_size == 4:
            cands.append(enc.disp_offset)
        m = enc.modrm_offset
        if m and want is not None:
            modrm = raw[m]
            if modrm & 0xC7 == 0x05:                    # mod 00, rm 101: disp32 follows
                cands.append(m + 1)
            elif modrm & 0xC7 == 0x04 and m + 1 < len(raw) and raw[m + 1] & 0x07 == 0x05:
                cands.append(m + 2)                     # SIB with no base: disp32 follows
        for off in cands:
            if want is not None and raw[off:off + 4] == want:
                return off
        raise TranslationError("%s operand without a locatable disp32 at %#x" % (what, cs.address))

    @staticmethod
    def _split_mem_branch(cs, op):
        """Pieces of `call/jmp [mem]` needed to re-use its memory operand."""
        enc = cs.encoding
        raw = bytes(cs.bytes)
        m = enc.modrm_offset
        if m < 1 or raw[m - 1] != 0xFF:
            return None
        rex = raw[m - 2] if m >= 2 and 0x40 <= raw[m - 2] <= 0x4F else 0
        npfx = m - 1 - (1 if rex else 0)
        # notrack (3E) and bnd (F2) only make sense on the branch itself.
        prefixes = bytes(b for b in raw[:npfx] if b not in (0x3E, 0xF2))
        tail = raw[m:]          # modrm, sib, disp
        riprel = None
        if op.mem.base == X.X86_REG_RIP:
            riprel = (cs.address + cs.size + op.mem.disp) & MASK64
        return prefixes, rex, tail, riprel

    def _note_tail(self, src, dst):
        a, b = self.kv.func_of(src), self.kv.func_of(dst)
        if a != b:
            self.tail_edges.add((a, b))

    def gs_report(self):
        """The per-CPU data the last image can touch: a list of (symbol,
        class, reads, writes, functions). Class "origin": redirected to the
        origin's value; "cpu": CPU identity or the preempt count, which the
        region analysis follows; "executor": everything else, the
        executor's own copy; "pointer": %gs with a register, a per-CPU
        pointer computed at run time."""
        out = []
        for addr, (rd, wr, funcs) in self.gs_refs.items():
            if addr is None:
                name, cls = "(computed)", "pointer"
            else:
                name = self.kv.data_sym(addr)
                cls = ("origin" if addr in self.subst else
                       "cpu" if addr in self.pcpu_src or addr == self.preempt_count else
                       "executor")
            fn = sorted((self.kv.names(f) or ("%#x" % (f or 0),))[0] for f in funcs)
            out.append((name, cls, rd, wr, fn))
        out.sort(key=lambda t: (t[1], t[0]))
        return out

    def _decode(self, site, learned):
        self.ins = {}
        self.gs_refs = {}           # address or None -> [reads, writes, functions]
        # Per build: the view is synchronised before each one.
        self.sched_sites = set()
        for name in self.cfg["frontier_static_call"]:
            self.sched_sites |= self.kv.static_call_sites(name)
        self.call_edges = []        # (return address, callee)
        self.tail_edges = set()     # (function, function it jumps into)
        # work is a stack: the site goes on last so that its own code is
        # decoded first. Learned addresses start again at depth 0 and can
        # each pull in thousands of instructions; taken first, they used up
        # the budget before the site was reached, and the build failed.
        work = [(a, 0) for a in learned.code]
        for targets in learned.ret.values():
            work += [(a, 0) for a in targets]
        work.append((site, 0))
        budget = self.cfg["max_insns"]
        while work:
            addr, depth = work.pop()
            while addr not in self.ins and len(self.ins) < budget:
                ins, succs = self._decode_one(addr, depth, learned)
                if ins is None:
                    break
                self.ins[addr] = ins
                work.extend(succs)
                if not ins.falls:
                    break
                addr += ins.size
        if site not in self.ins:
            raise TranslationError("cannot decode site %#x" % site)

    def _return_sites(self, learned):
        """Function -> return addresses its ret instructions may see."""
        sites = defaultdict(set)
        func_of = self.kv.func_of
        for ret_addr, callee in self.call_edges:
            sites[func_of(callee)].add(ret_addr)
        for ret_ip, targets in learned.ret.items():
            sites[func_of(ret_ip)].update(targets)
        # A function entered by a jump returns to the jumping function's callers.
        changed = True
        while changed:
            changed = False
            for src, dst in self.tail_edges:
                before = len(sites[dst])
                sites[dst] |= sites[src]
                changed |= len(sites[dst]) != before
        return sites

    # ---- per-CPU spans ----------------------------------------------------------
    #
    # The copy runs on the executor's CPU. Code that derives this CPU's
    # identity (this_cpu_ptr() reads this_cpu_off, smp_processor_id() reads
    # cpu_number) relies on it until it re-enables preemption or interrupts:
    # it keeps the pointer or number in registers, and a local lock
    # (local_trylock_t) marks its acquisition in this CPU's memory and is
    # released through a pointer derived again. Any exit in between moves the
    # rest of the region to another CPU: a handback to the origin's, or a
    # published nested acquisition to another combiner's. The region then
    # works on the executor's per-CPU data from that CPU, and a local lock
    # is released on the wrong CPU and stays taken on the executor's for
    # the rest of the boot (memcg's obj_stock on 57 of 64 CPUs after a
    # delegated brk1 run, bench/results/kdclaude/appgrid-20261118-64cpu/).
    #
    # So an identity read whose region (to the matching preempt or IRQ
    # re-enable, through calls) can exit becomes a frontier: the origin
    # derives its own identity there. Callees inside a region are decoded
    # whatever their depth, so learned regions do not exit through misses.
    # Not exits: native helpers; nested lock acquisitions, which inside a
    # region call the native lock function instead of its *_jit entry, so
    # that a contended one waits here (kd_cpu.busy keeps the executor from
    # publishing, kd_can_offer()) instead of continuing on another
    # combiner; and spin-class releases, since whether one releases the
    # root is only known at run time (kd_exec_one() counts a completion
    # inside a region the section opened, done_in_region).

    _SPIN_RELEASE_OPS = frozenset((1, 2, 3, 4))     # KD_OP_UNLOCK .. KD_OP_UNLOCK_BH
    _FLOW = frozenset(("plain", "skip", "native_call", "jmp", "jcc", "jshort", "call", "ret"))
    _SPAN_STEPS = 200000
    _LEVEL_SAT = 4

    def _ensure(self, addr, learned):
        """The instruction at addr, decoding it now if needed (None: cannot)."""
        ins = self.ins.get(addr)
        if ins is None and len(self.ins) < self.cfg["max_insns"]:
            ins, _succs = self._decode_one(addr, 0, learned)
            if ins is not None:
                self.ins[addr] = ins
                if ins.plevel > 0:
                    self._open_funcs.add(self.kv.func_of(addr))
        return ins

    def _callers(self, func, seen=None):
        """Return addresses in this image of the calls that reach `func`,
        directly or through sibling calls."""
        seen = seen if seen is not None else set()
        if func in seen:
            return set()
        seen.add(func)
        out = {nxt for nxt, t in self.call_edges if self.kv.func_of(t) == func}
        for a, b in self.tail_edges:
            if b == func:
                out |= self._callers(a, seen)
        return out

    def _span_exit(self, start, learned):
        """Why the region begun at `start` may exit, or None if it cannot.

        Levels count from the identity read. The walk is interprocedural
        through summaries (_span_callee): a callee returns at the level it
        was called at, so what a callee does for a region depends only on
        the level it is entered at and on its depth. Whether a callee
        releases the region is often decided by a result the walk does not
        follow (a failed local_trylock() returns early); summing both
        branches would leave regions open on paths that cannot run. This
        only keeps more code inside a region. Inside a callee, a region
        that closes does not end the walk (the callee may take it again and
        return with it, as the slab sheaf helpers do), but exits and calls
        are not followed while it is closed. In the read's own function a
        close ends the path, and its return continues in its callers
        (_span_return).

        Exits found within "pcpu_near_depth" calls of the read make the
        region a frontier; deeper ones are counted as far exits and left in
        the copy, flagged KD_X_REGION.
        """
        return self._span_frame(start, 0, 0, learned, top=True)

    def _span_callee(self, entry, level, depth, learned):
        """Summary of a callee for a region: (why, far, addrs, nested)."""
        key = (entry, min(level, 2), depth)
        memo = self._span_memo
        if key in memo:
            return memo[key] or (None, 0, frozenset(), frozenset())   # recursion
        memo[key] = None
        saved = self._span_addrs, self._span_nested, self._span_far
        self._span_addrs, self._span_nested, self._span_far = set(), set(), 0
        why = self._span_frame(entry, level, depth, learned, top=False)
        out = (why, self._span_far, frozenset(self._span_addrs), frozenset(self._span_nested))
        self._span_addrs, self._span_nested, self._span_far = saved
        memo[key] = out
        return out

    def _span_frame(self, start, level0, depth, learned, top):
        """Walk one function frame from `start`. Returns a near exit's
        reason or None; far exits, region addresses and nested lock calls
        go to self._span_far, _span_addrs and _span_nested."""
        near = self.cfg["pcpu_near_depth"]
        seen = set()
        work = [(start, level0)]

        def push(addr, level):
            if (addr, level) not in seen:
                seen.add((addr, level))
                work.append((addr, level))

        def exit_(why):
            if near is not None and depth > near:
                self._span_far += 1
                return None
            return why

        steps = 0
        while work:
            addr, level = work.pop()
            steps += 1
            if steps > self._SPAN_STEPS:
                return "region too long"
            ins = self._ensure(addr, learned)
            if ins is None:
                self._span_addrs.add(addr)      # its miss exit is in the region
                why = exit_("undecodable code at %#x" % addr)
                if why:
                    return why
                continue
            if level < self._LEVEL_SAT:
                # Above _LEVEL_SAT nesting the level saturates and stays
                # (a loop that takes a region per pass, against a release
                # the walk does not pair with it): the region stays open.
                level = min(level + ins.plevel + self._lock_level(ins), self._LEVEL_SAT)
            if level < 0 and top:
                continue                # the region ends on this path
            if level >= 0:
                self._span_addrs.add(addr)
            kind, nxt = ins.kind, addr + ins.size
            if level < 0 and kind not in self._FLOW:
                # Closed inside a callee: an exit here moves nothing (the
                # origin takes the region again itself if the rest does).
                continue
            if ins.orig is not None:
                self._span_nested.add(addr)
            if ins.pdec:
                # preempt_enable(): the decrement, then je/jne on reaching
                # zero to preempt_schedule(). In the copy the count holds
                # the executor's KD_EXEC_PIN (kd_exec_one()) and never
                # reaches zero: only the other branch is taken.
                j = self._ensure(nxt, learned)
                if j is not None and j.kind == "jcc" and j.op in (4, 5):
                    push(j.addr + j.size if j.op == 4 else j.target, level)
                    continue
            if kind in ("plain", "skip", "native_call") or \
                    (kind == "unlock_call" and ins.op in self._SPIN_RELEASE_OPS):
                push(nxt, level)
            elif kind == "jmp":
                push(ins.target, level)
            elif kind in ("jcc", "jshort"):
                taken = fall = level
                if level > 0 and kind == "jcc":
                    taken, fall = self._restore_skip(ins, level, learned)
                push(ins.target, taken)
                push(nxt, fall)
            elif kind == "call" and (level < 0 or self._report_call(ins.target) or
                                     self._resched_call(ins.target)):
                # Closed (a callee's own region is its business), a report
                # (_REPORT) or preempt_schedule() (_resched_call()).
                push(nxt, level)
            elif kind == "call":
                why = self._span_call(ins.target, level, depth, learned)
                if why:
                    return why
                push(nxt, level)
            elif kind == "frontier" and (self._noreturn_call(ins) or self._trap(ins) == "bug"):
                continue                # never comes back: nothing to move
            elif kind == "frontier" and self._trap(ins) == "warn":
                push(self._ud1_end(addr), level)            # WARN: see _REPORT
            elif kind == "frontier" and self._call_target(ins) is not None and \
                    (self._report_call(self._call_target(ins)) or
                     self._resched_call(self._call_target(ins))):
                push(nxt, level)
            elif kind in ("ind_call", "ind_jmp") and not self.cfg["pcpu_ind_exits"]:
                why = self._span_indirect(ins, level, depth, learned, push, exit_, top)
                if why:
                    return why
            elif kind in ("ret", "native_tail") or \
                    (kind == "unlock_tail" and ins.op in self._SPIN_RELEASE_OPS):
                # A sibling call returns where a ret would.
                if not top:
                    continue            # back to the caller, at its level
                why = self._span_return(addr, level, push)
                if why:
                    why = exit_(why)
                    if why:
                        return why
            else:
                why = exit_("%s at %#x" % (kind, addr))
                if why:
                    return why
        return None

    def _span_call(self, target, level, depth, learned):
        """A direct call inside a region: merge the callee's summary."""
        if depth + 1 > self.cfg["pcpu_walk_depth"]:
            # Below the walk: a far part of the region. Its entry is marked
            # so that a miss there carries KD_X_REGION.
            self._span_addrs.add(target)
            if self.cfg["pcpu_near_depth"] is None:
                return "calls nested too deeply at %#x" % target
            return None
        why, far, addrs, nested = self._span_callee(target, level, depth + 1, learned)
        self._span_far += far
        self._span_addrs |= addrs
        self._span_nested |= nested
        if why:
            names = self.kv.names(target)
            why = "%s > %s" % (names[0] if names else "%#x" % target, why)
        return why

    # Frontier calls that do not return (the stack check's failure panics).
    _NORETURN = frozenset(("__stack_chk_fail",))

    # Reporting paths: printk and the UBSAN handlers run only when the
    # kernel reports a problem, and walking into them (deep, recursive)
    # would turn every region with a WARN or a UBSAN check into a frontier.
    # The walk steps over these calls. Limit: a handback inside a report
    # can still move the rest of a region to the origin's CPU.
    _REPORT = ("_printk", "vprintk", "__warn_printk", "__ubsan_handle_", "__SCT__WARN_trap",
               "bad_page", "add_taint", "refcount_warn_saturate", "kfence_report_error",
               "slab_out_of_memory", "warn_alloc", "dump_stack")

    _IRQ_RELEASE_OPS = frozenset((2, 3, 4))     # KD_OP_UNLOCK_IRQ, _IRQRESTORE, _BH

    def _lock_level(self, ins):
        """The region a lock call opens or closes inside the call: the
        _irq, _irqsave and _bh acquisitions disable interrupts or softirqs,
        and their releases enable them again (spin_unlock_irqrestore()
        closes a local_irq_save() region the same way)."""
        if ins.kind in ("unlock_call", "unlock_tail"):
            return -1 if ins.op in self._IRQ_RELEASE_OPS else 0
        if ins.kind not in ("native_call", "native_tail"):
            return 0
        # Native lock functions (raw spinlocks), or a nested lock call.
        for n in self.kv.names(ins.orig if ins.orig is not None else ins.target):
            if "lock" not in n:
                continue
            if n.endswith(("_unlock_irqrestore", "_unlock_irq", "_unlock_bh")):
                return -1
            if n.endswith(("_lock_irqsave", "_lock_irq", "_lock_bh")) and "trylock" not in n:
                return 1
        return 0

    def _resched_call(self, target):
        """preempt_enable() calls preempt_schedule() when the count reaches
        zero, which in the copy it never does (KD_EXEC_PIN, kd_exec_one()):
        such a call is not reached. The compiler often tests the zero flag
        of the decrement later, through a register, so the call is
        recognised by its target (the function, its thunks and the static
        call trampolines of PREEMPT_DYNAMIC)."""
        return any(n.startswith(("preempt_schedule", "__SCT__preempt_schedule"))
                   for n in self.kv.names(target))

    def _report_call(self, target):
        return any(n.startswith(self._REPORT) for n in self.kv.names(target))

    def _span_indirect(self, ins, level, depth, learned, push, exit_, top):
        """Walk an indirect branch through its learned targets ("pcpu_ind_exits")."""
        is_call = ins.kind == "ind_call"
        nxt = ins.addr + ins.size
        for target in learned.ind.get(ins.addr, ()):
            cls, _ = self.classify(target)
            if cls == "code" and is_call:
                why = self._span_call(target, level, depth, learned)
                if why:
                    return why
            elif cls == "code":
                push(target, level)
            elif cls == "native" and not is_call and top:
                why = self._span_return(ins.addr, level, push)
                if why and exit_(why):
                    return why
            elif cls not in ("native", "skip"):
                why = exit_("%s through %s at %#x" % (cls, ins.kind, ins.addr))
                if why:
                    return why
        if is_call:
            push(nxt, level)            # an unknown target: a run-time exit
        return None

    @staticmethod
    def _trap(ins):
        """'warn' for the ud1 a WARN site is patched to (it reports and goes
        on), 'bug' for ud2 (BUG: does not return), else None."""
        raw = ins.raw
        i = 0
        while i < len(raw) and (raw[i] in _LEGACY_PREFIXES or 0x40 <= raw[i] <= 0x4F):
            i += 1
        if raw[i:i + 2] == b"\x0f\xb9":
            return "warn"
        if raw[i:i + 2] == b"\x0f\x0b":
            return "bug"
        return None

    def _ud1_end(self, addr):
        """End of the ud1 at addr. ud1 has a ModRM byte, which the decoder
        leaves out (the kernel's WARN is 67 48 0f b9 3a)."""
        raw = self.kv.read(addr, 16)
        i = 0
        while raw[i] in _LEGACY_PREFIXES or 0x40 <= raw[i] <= 0x4F:
            i += 1
        i += 2                      # 0f b9
        modrm = raw[i]
        i += 1
        mod, rm = modrm >> 6, modrm & 7
        if mod != 3 and rm == 4:    # SIB
            sib = raw[i]
            i += 1
            if mod == 0 and (sib & 7) == 5:
                i += 4
        if mod == 1:
            i += 1
        elif mod == 2 or (mod == 0 and rm == 5):
            i += 4
        return addr + i

    @staticmethod
    def _call_target(ins):
        """Target of a direct call rel32, or None."""
        if ins.raw[:1] != b"\xe8" or ins.size != 5:
            return None
        return (ins.addr + 5 + int.from_bytes(ins.raw[1:5], "little", signed=True)) & MASK64

    def _noreturn_call(self, ins):
        target = self._call_target(ins)
        return target is not None and any(n in self._NORETURN for n in self.kv.names(target))

    def _span_return(self, addr, level, push):
        """The function containing `addr` returns with the region open (as
        far as the walk knows). Returns why that is an exit, or None after
        queueing where the walk goes on."""
        func = self.kv.func_of(addr)
        if func in self._open_funcs:
            return None             # it opened the region: closed by now
        if func == self._root_func:
            # The site's own function. A sleepable-class section runs with
            # preemption on: no region is open here, and the read did not
            # rely on staying on this CPU. A spin-class section is one.
            return None if self._sleepable else \
                "region continues past the section at %#x" % addr
        callers = self._callers(func)
        if not callers:
            return "region continues past the return at %#x" % addr
        for nxt in callers:
            push(nxt, level)
        return None

    def _is_sti(self, addr, learned):
        ins = self._ensure(addr, learned)
        return ins is not None and ins.raw == b"\xfb", ins

    def _restore_skip(self, ins, level, learned):
        """local_irq_restore() enables interrupts only if the saved flags
        had them on: a branch around sti. The path that skips it leaves
        the region as well (levels for the taken and fall-through paths)."""
        nxt = ins.addr + ins.size
        sti, s_ins = self._is_sti(nxt, learned)
        if sti and ins.target == nxt + 1:
            return level - 1, level           # jcc over the sti that follows
        sti, s_ins = self._is_sti(ins.target, learned)
        if sti:
            back = self._ensure(ins.target + 1, learned)
            if back is not None and back.kind == "jmp" and back.target == nxt:
                return level, level - 1       # sti out of line, then back
        return level, level

    def _pcpu_spans(self, learned):
        """Turn identity reads whose region may exit into frontiers, and
        make the nested lock calls of the other regions wait in place."""
        out = []
        done = set()
        self.region_addrs = set()       # instructions inside walked regions
        self.pcpu_far = 0               # far exits left in the copy (KD_X_REGION)
        self._open_funcs = {self.kv.func_of(a) for a, ins in self.ins.items() if ins.plevel > 0}
        self._root_func = self.kv.func_of(self.site)
        raw = self.kv.read(self.site - 5, 5)
        callee = (self.site + int.from_bytes(raw[1:], "little", signed=True)) & MASK64
        self._sleepable = raw[0] == 0xE8 and \
            self.info.syms.get(callee, (0,))[0] == KD_SYM_ACQUIRE
        # A new frontier is an exit for the regions that contain it, and a
        # walk decodes callees that can hold identity reads of their own:
        # repeat until no region changes and no new read turned up.
        changed = True
        walked = set()
        while changed:
            changed = False
            nested, regions, far = set(), set(), 0
            self._span_memo = {}        # callee summaries; frontiers changed
            reads = sorted(a for a, ins in self.ins.items() if ins.pcpu)
            walked |= set(reads)
            for addr in reads:
                if addr in done:
                    continue
                self._span_nested = set()
                self._span_addrs = set()
                self._span_far = 0
                why = self._span_exit(addr, learned)
                if why:
                    ins = self.ins[addr]
                    ins.kind = "frontier"
                    ins.falls = False
                    out.append((addr, why))
                    done.add(addr)
                    changed = True
                    continue
                nested |= self._span_nested
                regions |= self._span_addrs
                far += self._span_far
            if any(ins.pcpu and a not in walked for a, ins in self.ins.items()):
                changed = True
        for a in nested:
            ins = self.ins[a]
            ins.target = ins.orig
            ins.orig = None
        self.region_addrs = regions
        self.pcpu_starts = done
        self.pcpu_far = far
        return out

    # ---- emission -------------------------------------------------------------

    def _ref(self, addr):
        """Label for source address `addr`; an exit stub if it was not copied."""
        if addr in self.ins:
            return _loc(addr)
        self.missing.add(addr)
        return "miss_%x" % addr

    def _jmp(self, label, cold=False):
        self.asm.emit(5, lambda pc, L: b"\xe9" + _rel32(L[label], pc + 5), cold)

    def _jcc(self, cc, label, cold=False):
        self.asm.emit(6, lambda pc, L: bytes((0x0F, 0x80 | cc)) + _rel32(L[label], pc + 6), cold)

    def _call_native(self, target, cold=False):
        self.asm.emit(5, lambda pc, L: b"\xe8" + _rel32(target, pc + 5), cold)

    def _push_ret(self, ret_addr, cold=False):
        """Push the source return address, as the original call would."""
        if _fits_simm32(ret_addr):
            self.asm.raw(b"\x68" + _simm32(ret_addr), cold)
        else:
            # sub rsp,8 ; mov dword [rsp],lo ; mov dword [rsp+4],hi (flags are dead at a call)
            lo, hi = ret_addr & 0xFFFFFFFF, (ret_addr >> 32) & 0xFFFFFFFF
            self.asm.raw(b"\x48\x83\xec\x08" + b"\xc7\x04\x24" + struct.pack("<I", lo) +
                         b"\xc7\x44\x24\x04" + struct.pack("<I", hi), cold)

    def _exit(self, code, ip, resume=None, cold=False, aux=None):
        """Exit stub: record why and where, then leave through kd_jit_exit.

        Uses only mov, so the source program's flags reach the packet.
        """
        info = self.info
        target = info.jit_exit
        if ip in self.region_addrs and ip not in self.pcpu_starts:
            # A region start that became a frontier hands back before its
            # own region: not flagged (its own increment raises the count).
            code |= KD_X_REGION         # see _pcpu_spans(), hb_region
        if aux is not None:
            # mov qword gs:[aux], simm32
            self.asm.raw(b"\x65\x48\xc7" + _gs_abs_modrm(info.pcpu_aux) + _simm32(aux), cold)
        # mov qword gs:[exit_ip], simm32(ip)
        self.asm.raw(b"\x65\x48\xc7" + _gs_abs_modrm(info.pcpu_exit_ip) + _simm32(ip), cold)
        if resume is not None:
            head = b"\x65\x48\xc7" + _gs_abs_modrm(info.pcpu_resume)
            self.asm.emit(len(head) + 4, lambda pc, L: head + _simm32(L[resume]), cold)
        # mov dword gs:[exit_code], imm32
        self.asm.raw(b"\x65\xc7" + _gs_abs_modrm(info.pcpu_exit_code) + struct.pack("<I", code), cold)
        self.asm.emit(5, lambda pc, L: b"\xe9" + _rel32(target, pc + 5), cold)

    def _resched_point(self, ins):
        """A cond_resched() site: hand back if the origin should reschedule.

            mov  rax, gs:[task]          ; the origin's task (redirected current)
            test byte [rax+off], mask    ; its TIF_NEED_RESCHED
            jnz  -> frontier exit at the site
            <the site's own xor/nop>

        The site stands for a call, so rax and the flags are dead there, and
        the site's xor sets both again. The origin resumes at the site and
        runs natively from there with preemption enabled.
        """
        off = self.cfg["need_resched_offset"]
        mask = self.cfg["need_resched_mask"]
        if not (0 <= off < 128 and 0 < mask < 256):
            raise TranslationError("need_resched check needs disp8 and imm8")
        # mov rax, qword gs:[task]
        self.asm.raw(b"\x65\x48\x8b" + _gs_abs_modrm(self.info.pcpu_task))
        # test byte [rax+disp8], imm8
        self.asm.raw(bytes((0xF6, 0x40, off, mask)))
        label = "resched_%x" % ins.addr
        self._jcc(0x5, label)
        self.asm.label(label, cold=True)
        self._exit(KD_X_FRONTIER, ins.addr, cold=True)
        self.asm.raw(ins.raw)

    def _root_check(self, ins, tail):
        """Guards in front of a release call.

            cmp rdi, gs:[root]   ; je  -> exit: this level's section is complete
            cmp dword gs:[anc],0 ; jne -> exit: nested run, executor decides
                                           whether rdi is an outer session root
        Otherwise the release is an ordinary native call.
        """
        flags = (ins.op << 8) | (KD_X_TAIL if tail else 0)
        resume = None if tail else self._ref(ins.addr + ins.size)

        label = "unlock_%x" % ins.addr
        self.asm.raw(b"\x65\x48\x3b\x3c\x25" + _simm32(self.info.pcpu_root))
        self._jcc(0x4, label)
        self.asm.label(label, cold=True)
        self._exit(KD_X_UNLOCK | flags, ins.addr, resume=resume, cold=True)

        label = "unlockanc_%x" % ins.addr
        self.asm.raw(b"\x65\x83\x3c\x25" + _simm32(self.info.pcpu_anc) + b"\x00")
        self._jcc(0x5, label)
        self.asm.label(label, cold=True)
        self._exit(KD_X_UNLOCK_ANC | flags, ins.addr, resume=resume, cold=True,
                   aux=ins.target)

    def _ret_chain(self, ins, cold=False):
        """Return: dispatch on the source return address on top of the stack."""
        for target in sorted(self.ret_sites.get(self.kv.func_of(ins.addr), ())):
            if not _fits_simm32(target):
                continue
            self.ret_pads.add(target)
            # cmp qword [rsp], simm32
            self.asm.raw(b"\x48\x81\x3c\x24" + _simm32(target), cold)
            self._jcc(0x4, "retpad_%x" % target, cold)
        self._exit(KD_X_MISS_RET, ins.addr, cold=cold)

    def _mem_form(self, ins, opcode, reg_field, rex_w, imm):
        """Re-encode the memory operand of an indirect branch under another opcode."""
        prefixes, rex, tail, riprel = ins.mem
        new_rex = (0x48 if rex_w else 0x40) | (rex & 0x3)
        head = prefixes + (bytes((new_rex,)) if new_rex != 0x40 else b"") + bytes((opcode,))
        modrm = bytes(((tail[0] & 0xC7) | (reg_field << 3),))
        size = len(head) + len(tail) + len(imm)
        if riprel is None:
            data = head + modrm + tail[1:] + imm
            return size, lambda pc, L: data
        fixed = head + modrm + tail[1:-4]
        return size, lambda pc, L: fixed + _rel32(riprel, pc + size) + imm

    def _ind_compare(self, ins, target):
        if ins.reg is not None:
            n = ins.reg
            self.asm.raw(bytes((0x48 | (n >> 3), 0x81, 0xF8 | (n & 7))) + _simm32(target))
        else:
            self.asm.emit(*self._mem_form(ins, 0x81, 7, True, _simm32(target)))

    def _ind_capture(self, ins):
        """Store the unknown branch target in kd_cpu.aux for the learning report."""
        aux = self.info.pcpu_aux
        if ins.reg is not None:
            n = ins.reg
            # mov gs:[aux], reg
            self.asm.raw(bytes((0x65, 0x48 | ((n >> 3) << 2), 0x89, 0x04 | ((n & 7) << 3), 0x25)) +
                         _simm32(aux), cold=True)
        else:
            # push qword [mem] ; pop qword gs:[aux]
            self.asm.emit(*self._mem_form(ins, 0xFF, 6, False, b""), cold=True)
            self.asm.raw(b"\x65\x8f" + _gs_abs_modrm(aux), cold=True)

    def _indirect(self, ins, learned):
        is_call = ins.kind == "ind_call"
        nxt = ins.addr + ins.size
        for target in sorted(learned.ind.get(ins.addr, ())):
            if not _fits_simm32(target):
                continue
            cls, _ = self.classify(target)
            self._ind_compare(ins, target)
            if cls == "code" and not is_call:
                self._jcc(0x4, self._ref(target))
                continue
            pad = "ind_%x_%x" % (ins.addr, target)
            self._jcc(0x4, pad)
            self.asm.label(pad, cold=True)
            if cls == "code":
                self._push_ret(nxt, cold=True)
                self._jmp(self._ref(target), cold=True)
            elif cls == "native":
                self._call_native(target, cold=True)
                if is_call:
                    self._jmp(self._ref(nxt), cold=True)
                else:
                    self._ret_chain(ins, cold=True)
            else:
                # Lock API or frontier reached through a pointer: the origin runs it.
                self._exit(KD_X_FRONTIER, ins.addr, cold=True)
        miss = "indmiss_%x" % ins.addr
        self._jmp(miss)
        self.asm.label(miss, cold=True)
        self._ind_capture(ins)
        self._exit(KD_X_MISS_IND, ins.addr, cold=True)

    def _plain(self, ins):
        if ins.patch is None:
            self.asm.raw(ins.raw)
            return
        off, target, absolute = ins.patch
        raw, size = ins.raw, ins.size
        if absolute:
            self.asm.raw(raw[:off] + _simm32(target) + raw[off + 4:])
        else:
            self.asm.emit(size, lambda pc, L: raw[:off] + _rel32(target, pc + size) + raw[off + 4:])

    def _emit(self, ins, learned):
        kind = ins.kind
        nxt = ins.addr + ins.size
        if kind == "plain":
            self._plain(ins)
        elif kind == "skip":
            pass
        elif kind == "call":
            self._push_ret(nxt)
            self._jmp(self._ref(ins.target))
        elif kind == "jmp":
            self._jmp(self._ref(ins.target))
        elif kind == "jcc":
            self._jcc(ins.op, self._ref(ins.target))
        elif kind == "jshort":
            # jrcxz/loop only have rel8 forms: hop to a rel32 jump.
            self.asm.raw(ins.raw[:-1] + b"\x02" + b"\xeb\x05")
            self._jmp(self._ref(ins.target))
        elif kind == "native_call":
            self._call_native(ins.target)
        elif kind == "native_tail":
            self._call_native(ins.target)
            self._ret_chain(ins)
        elif kind == "unlock_call":
            self._root_check(ins, tail=False)
            self._call_native(ins.target)
        elif kind == "unlock_tail":
            self._root_check(ins, tail=True)
            self._call_native(ins.target)
            self._ret_chain(ins)
        elif kind == "acquire_call":
            self._exit(KD_X_ACQUIRE | (ins.op << 8), ins.addr, resume=self._ref(nxt))
        elif kind == "acquire_tail":
            self._exit(KD_X_ACQUIRE | (ins.op << 8) | KD_X_TAIL, ins.addr)
        elif kind == "ret":
            self._ret_chain(ins)
        elif kind in ("ind_call", "ind_jmp"):
            self._indirect(ins, learned)
        elif kind == "frontier":
            self._exit(KD_X_FRONTIER, ins.addr)
        elif kind == "resched_point":
            self._resched_point(ins)
        else:
            raise TranslationError("unknown instruction kind %s" % kind)

    def build(self, site, learned=None):
        """Decode and lay out the copy for `site`.

        Returns an Image; call Image.link(base) once the load address is
        known.
        """
        learned = learned or Learned()
        self.site = site
        self._decode(site, learned)
        self.pcpu_frontiers = self._pcpu_spans(learned)
        self.ret_sites = self._return_sites(learned)
        self.asm = Asm()
        self.missing = set()
        self.ret_pads = set()

        addrs = sorted(self.ins)
        for i, addr in enumerate(addrs):
            ins = self.ins[addr]
            self.asm.label(_loc(addr))
            self._emit(ins, learned)
            nxt = addr + ins.size
            if ins.falls and (i + 1 == len(addrs) or addrs[i + 1] != nxt):
                self._jmp(self._ref(nxt))

        for target in sorted(self.ret_pads):
            self.asm.label("retpad_%x" % target, cold=True)
            self.asm.raw(b"\x48\x8d\x64\x24\x08", cold=True)    # lea rsp,[rsp+8]
            self._jmp(self._ref(target), cold=True)
        for addr in sorted(self.missing):
            self.asm.label("miss_%x" % addr, cold=True)
            self._exit(KD_X_MISS_CODE, addr, cold=True)

        image = Image(site, self.asm, len(self.ins))
        image.pcpu_frontiers = self.pcpu_frontiers
        return image


class Image:
    def __init__(self, site, asm, insns):
        self.site = site
        self.asm = asm
        self.insns = insns
        self.size = asm.size()

    def link(self, base):
        """Returns (bytes, offset of the site's entry) for load address `base`."""
        text, labels = self.asm.link(base)
        return text, labels[_loc(self.site)] - base
