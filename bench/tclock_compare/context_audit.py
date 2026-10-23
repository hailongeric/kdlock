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
        for line in text.splitlines():
            insn = re.match(r'^\s*[0-9a-f]+:\s+([a-z][a-z0-9]*)\s*(.*)$', line)
            if insn:
                operand = re.sub(r'\s+', '', insn[2].split('#')[0])
                code.append(insn[1] + (' ' + operand if operand else ''))
        while code and code[0] == 'endbr64':
            code.pop(0)
        return text, code

    text, switch = function('komb_context_switch')
    expected = SAVES + ['mov %rsp,(%rsi)', 'mov (%rdi),%rsp'] + RESTORES
    if switch[:len(expected)] != expected:
        raise ValueError('context switch has an unexpected stack/register layout')
    tail = switch[len(expected):]
    if not tail or not (tail[0] == 'ret' or
                         (tail[0].startswith('jmp ') and '__x86_return_thunk' in text)):
        raise ValueError('unexpected context-switch return')

    slow_name = {'mutex': '__komb_mutex_lock', 'rwlock': 'kombrw_spin_lock_slowpath',
                 'spin': 'komb_spin_lock_slowpath', 'rwsem': '__komb_write_stack_switch'}[lock_kind]
    slow_text, slow = function(slow_name)
    # Original rwlock masks interrupts before saving the continuation.
    if lock_kind == 'rwlock' and slow:
        irq_prefix = slow[0] == 'cli'
        # Captured x86_64 kernel: pv_ops.irq.irq_disable relocation. Accept
        # this exact call only before the first save, never an arbitrary call.
        irq_prefix |= (slow[0].startswith('call *') and
                       re.search(r'R_X86_64_PC32\s+pv_ops\+0xf4\b',
                                 slow_text.split('push', 1)[0]) is not None)
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
        _, helper = function(name)
        for instruction in helper:
            if instruction == 'ret' or instruction.startswith('jmp '):
                break
            if not (instruction.split()[0] in ('mov', 'lea', 'add') and
                    instruction.endswith(',%rax')):
                raise ValueError(f'{name} clobbers more than the expected RAX/flags')
    return dict(six_register_switch=True, slowpath_inline_returns=2,
                hidden_helpers_preserve_lock=True)
