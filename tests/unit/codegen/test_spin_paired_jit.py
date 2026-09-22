"""Execute generated paired continuations through the actual minimal wrapper.

Use an entry stack carrying the five saves, poison uncaptured GPRs, and check
COMPLETE/refusal plus FULL at a native call and a bounded continuation. Only
the native callee/dispatcher is substituted; admission and generated code run.
"""
from io import StringIO
import subprocess
import tempfile
from pathlib import Path

from test_jit_diagnostics import ROOT, render
from context_guards import EntryGuards
from miasm.expression.expression import ExprId

FIXTURE = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct pt_regs { unsigned long w[21]; };
#define __KERNEL__
#include "kd_jit_batch.h"
extern void main_wrapper(struct pt_regs *, unsigned long *);
int main(void) {
 for (unsigned int refuse=0;refuse<2;refuse++) {
  struct pt_regs regs;
  memset(&regs,0xde,sizeof(regs));
  unsigned long stack[64]={0};
  for(unsigned int i=0;i<5;i++) stack[16+i]=0x115-i;
  regs.w[4]=(unsigned long)&stack[refuse?16:48];
  regs.w[16]=0x1000;
  regs.w[19]=(unsigned long)&stack[16];
  struct pt_regs before=regs;
  unsigned int state=1;
  struct kd_jit_batch_call call={
   .regs=&regs, .args={0,0}, .code=(char *)main_wrapper+32,
   .lock=0x9000, .unlock=0x4000, .entry_abi=1,
   .packet_state=&state, .complete=1,
  };
  kd_jit_clobber_call_v1(&call);
  if(refuse) {
   assert(call.args[0]==6 && !call.args[1] && state==1);
   assert(!memcmp(&before,&regs,sizeof(regs)));
   continue;
  }
#if NATIVE_CALL
  assert(call.args[0]==1 && call.args[1] && state==0 && regs.w[16]==0x5000);
  assert(regs.w[0]==0x116 && regs.w[1]==0x115 && regs.w[2]==0x114);
  assert(regs.w[3]==0x113 && regs.w[5]==0x112);
  /* The substituted native callee returns with the ordinary C callee saves
   * intact. Resume only its exact saved return PC/stack, in the same packet. */
  for(unsigned int step=0;step<2;step++) {
   assert(call.args[0]==1 && regs.w[16]==(step?0x6000:0x5000));
   regs.w[16]=*(unsigned long *)regs.w[19];
   regs.w[19]+=8;
   call.args[0]=call.args[1]=0;
   /* FULL packets reenter the regular wrapper, never the pristine-minimal
    * directory. Known control calls retain their precise continuation. */
   main_wrapper(&regs,call.args);
  }
  assert(call.args[0]==1 && call.args[1] && state==0);
  assert(regs.w[16]==0x4000 && regs.w[19]==before.w[19]-8);
  assert(regs.w[13]==before.w[19] && regs.w[12]==FINAL_IP);
#else
  assert(call.args[0]==7 && call.args[1] && state==2);
  assert(regs.w[16]==FINAL_IP && regs.w[19]==before.w[19]);
#endif
  assert(regs.w[4]==before.w[4]);
  for(unsigned int i=0;i<5;i++) assert(stack[16+i]==0x116-i);
 }
 puts("PASS paired JIT: stack reloads, updated unlock saves, minimal COMPLETE/refusal, native FULL continuation");
}
'''


def main():
    symbols = {'kd_spin_lock_pinned_clobber_v1': 0x3000,
               'kd_spin_lock_clobber_v1': 0x3100,
               'kd_spin_unlock_clobber_v1': 0x4000,
               'kd_spin_direct_native_unlock': 0x6000, 'kd_spin_lock': 0x5000}
    for native in (False, True):
        # Same POP order and cookie assignment as the real paired continuation.
        code = bytes.fromhex('415f415e415d415c5bb801000000')
        code += bytes.fromhex('48ffc349ffc449ffc549ffc649ffc7')
        if native:
            # A matched ordinary-C control pair has resumable FULL boundaries.
            for target in (0x5000, 0x6000):
                code += bytes.fromhex('48c7c700910000')
                code += b'\xe8' + (target-0x1000-len(code)-5).to_bytes(4, 'little', signed=True)
        code += bytes.fromhex('53415441554156415748c7c7009000004889e648c7c2')
        final_ip = 0x1000+len(code)+4+3+5
        code += final_ip.to_bytes(4, 'little') + bytes.fromhex('4889e9')
        code += b'\xe8' + (0x4000-0x1000-len(code)-5).to_bytes(4, 'little', signed=True)
        code += bytes.fromhex('415f415e415d415c5bc3')
        assembly, log, status = render(code.hex(), kernel_symbols=symbols, abi=1,
                                       body_witness=True, return_status=True)
        assert status == 0, log
        # Exercise the production stack-input predicate's refusal before POPs.
        # Do not confuse a dispatch miss (FULL) with a pristine entry refusal.
        guards = EntryGuards()
        assert guards.stack_value((ExprId('kd_entry_RSP', 64), 0))
        output = StringIO(); guards.emit(output, 0x1000)
        assembly = output.getvalue().replace('kd_entry_guard', 'kd_pair_test_guard').encode() + assembly
        with tempfile.TemporaryDirectory(prefix='kd-paired-jit-') as directory:
            path = Path(directory)
            (path/'asm').mkdir(); (path/'linux').mkdir()
            (path/'linux/objtool.h').write_text('#define UNWIND_HINT(...) ""\n')
            (path/'asm/asm.h').write_text('register unsigned long current_stack_pointer asm("rsp");\n#define ASM_CALL_CONSTRAINT "+r"(current_stack_pointer)\n')
            (path/'asm/nospec-branch.h').write_text('#define CALL_NOSPEC "call *%[thunk_target]\\n"\n')
            (path/'asm/jit.S').write_bytes(assembly)
            (path/'wrapper.S').write_text((ROOT/'include/wrapper.S').read_text()+
                                         '\n.globl main\n.section .note.GNU-stack,"",@progbits\n')
            (path/'fixture.c').write_text(FIXTURE)
            subprocess.run(['cc', '-c', '-DKD_GENERATED_ENTRY_ABI=1', '-Dmain=main_wrapper',
                            '-I'+str(path), '-I'+str(path/'asm'), '-I'+str(ROOT/'include'),
                            str(path/'wrapper.S'), '-o', str(path/'wrapper.o')], check=True, timeout=30)
            subprocess.run(['cc', '-O2', '-fno-omit-frame-pointer', '-mno-red-zone',
                            '-Wall', '-Wextra', '-Werror', f'-DNATIVE_CALL={int(native)}',
                            f'-DFINAL_IP={final_ip}', '-I'+str(path), '-I'+str(ROOT/'include'),
                            str(path/'fixture.c'), str(path/'wrapper.o'), '-o', str(path/'test')],
                           check=True, timeout=30)
            subprocess.run([path/'test'], check=True, timeout=10)


if __name__ == '__main__':
    main()
