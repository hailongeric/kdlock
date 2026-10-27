"""Reject compiler-generated stack frames that invalidate upstream inline asm.

This checks the emitted x86 code before module loading; source equality alone
does not establish the hidden CALL/RSP contract of the C inline assembly.
"""
import re


SAVES = [f'push %{r}' for r in ('rbp', 'rbx', 'r12', 'r13', 'r14', 'r15')]
RESTORES = [f'pop %{r}' for r in ('r15', 'r14', 'r13', 'r12', 'rbx', 'rbp')]


def audit(disassembly, lock_kind='spin'):
    def function(name):
        match = re.search(r'^\s*[0-9a-f]+ <' + name + r'>:\n(.*?)(?=^\s*[0-9a-f]+ <|\Z)',
                          disassembly, re.M | re.S)
        if not match:
            raise ValueError(f'missing inline-asm function: {name}')
        text = match.group(1)
        code = []
        relocations = []
        for line in text.splitlines():
            insn = re.match(r'^\s*[0-9a-f]+:\s+([a-z][a-z0-9]*)\s*(.*)$', line)
            if insn:
                operand = re.sub(r'\s+', '', insn[2].split('#')[0])
                code.append(insn[1] + (' ' + operand if operand else ''))
                relocations.append([])
            else:
                relocation = re.match(r'^\s*[0-9a-f]+:\s+(R_X86_64_\S+)\s+(\S+)', line)
                if relocation and relocations:
                    relocations[-1].append(relocation.groups())
        while code and code[0] == 'endbr64':
            code.pop(0)
            relocations.pop(0)
        return text, code, relocations

    text, switch, _ = function('komb_context_switch')
    expected = SAVES + ['mov %rsp,(%rsi)', 'mov (%rdi),%rsp'] + RESTORES
    if switch[:len(expected)] != expected:
        raise ValueError('context switch has an unexpected stack/register layout')
    tail = switch[len(expected):]
    if not tail or not (tail[0] == 'ret' or
                         (tail[0].startswith('jmp ') and '__x86_return_thunk' in text)):
        raise ValueError('unexpected context-switch return')

    slow_name = {'mutex': '__komb_mutex_lock', 'rwlock': 'kombrw_spin_lock_slowpath',
                 'spin': 'komb_spin_lock_slowpath', 'rwsem': '__komb_write_stack_switch'}[lock_kind]
    slow_text, slow, slow_relocations = function(slow_name)
    rwlock_pv_preserves_argument = False
    # Original rwlock masks interrupts before saving the continuation.
    if lock_kind == 'rwlock' and slow:
        if slow[0] == 'mov %rdi,%r8':
            # Linux 7 ZERO_CALL_USED_REGS adds RDI to PV CALLEESAVE's
            # clobbers, but preserves R8. GCC saves the lock there across
            # IRQ-disable, the RAX-only hidden helpers, and IRQ-enable.
            # Bind the complete emitted dataflow; skipping an arbitrary
            # preamble would hide another compiler frame or an R8 clobber.
            def pv_call(index, offset):
                return (slow[index] == 'call *0x0(%rip)' and
                        slow_relocations[index] == [('R_X86_64_PC32', 'pv_ops+' + offset)])

            def named_call(index, name):
                return re.fullmatch(r'call [0-9a-f]+<' + name + r'>', slow[index]) is not None

            valid = (len(slow) > 19 and pv_call(1, '0xec') and
                     slow[2:8] == SAVES and
                     named_call(8, 'get_komb_rwlock_node') and
                     slow[9] == 'mov %rsp,0x28(%rax)' and
                     named_call(10, 'get_shadow_stack_ptr') and
                     slow[11] == 'mov (%rax),%rsp' and
                     pv_call(12, '0xf4') and slow[13] == 'mov %r8,%rdi' and
                     named_call(14, '__kombrw_spin_lock_slowpath') and
                     slow[15] == 'mov %eax,%r8d' and pv_call(16, '0xec') and
                     slow[17] == 'test %r8d,%r8d' and slow[18].startswith('je '))
            if not valid:
                raise ValueError('rwlock PV prefix does not preserve the exact lock/return dataflow')
            rwlock_pv_preserves_argument = True
            slow = slow[2:]
        irq_prefix = slow[0] == 'cli'
        # Ubuntu linux=7.0.0-38.38, captured config: DWARF places
        # pv_ops.irq.irq_disable.func at 232 + 8 + 0 = 0xf0.
        # The PC32 relocation subtracts four, giving +0xec. Runners verify
        # the exact Linux 7 kernel first; the retired +0xf4 is not accepted.
        # Accept this call only before the first save, never an arbitrary call.
        irq_prefix |= (slow[0] == 'call *0x0(%rip)' and
                       slow_relocations[0] == [('R_X86_64_PC32', 'pv_ops+0xec')])
        if irq_prefix:
            slow = slow[1:]
    if slow[:6] != SAVES or not slow[6].startswith('call '):
        raise ValueError('slowpath has an extra prologue before saving the continuation')
    returns = [i for i, instruction in enumerate(slow) if instruction == 'ret']
    if len(returns) != 2 or any(slow[i-6:i] != RESTORES for i in returns):
        raise ValueError('slowpath does not restore six registers on both inline returns')

    # Upstream's hidden asm calls do not declare RDI clobbers. The emitted
    # helpers must preserve the incoming lock argument and the saved stack.
    node_name = {'mutex': 'get_komb_mutex_node', 'rwlock': 'get_komb_rwlock_node',
                 'spin': 'get_komb_node', 'rwsem': 'get_komb_mutex_node'}[lock_kind]
    for name in (node_name,
                 'get_shadow_stack_ptr'):
        _, helper, helper_relocations = function(name)
        returned = False
        for index, instruction in enumerate(helper):
            if instruction == 'ret':
                returned = True
                break
            if instruction.startswith('jmp '):
                if (re.fullmatch(r'jmp [0-9a-f]+<[^>]+>', instruction) is None or
                        helper_relocations[index] !=
                        [('R_X86_64_PLT32', '__x86_return_thunk-0x4')]):
                    raise ValueError(f'{name} has an unbound helper tailcall')
                returned = True
                break
            if not (instruction.split()[0] in ('mov', 'lea', 'add') and
                    instruction.endswith(',%rax')):
                raise ValueError(f'{name} clobbers more than the expected RAX/flags')
        if not returned:
            raise ValueError(f'{name} has no verified return')
    return dict(six_register_switch=True, slowpath_inline_returns=2,
                hidden_helpers_preserve_lock=True,
                rwlock_pv_preserves_argument=rwlock_pv_preserves_argument)
