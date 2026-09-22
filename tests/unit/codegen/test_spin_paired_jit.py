"""Execute compiler-clobber cold-gate continuations through the real wrapper.

The body has one ordinary stack value and an unlock-path byte, without a
manual five-register save area. Poison uncaptured GPRs and check COMPLETE,
entry refusal and FULL at native calls. Only the native callee/dispatcher is
substituted; admission and generated code run.
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
  stack[16]=0x115;
  stack[17]=1; /* A hot-owned lock takes the clobber unlock branch. */
  for(unsigned int i=18;i<24;i++) stack[i]=0x123400+i;
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
   assert(stack[16]==0x115 && stack[17]==1);
   continue;
  }
#if NATIVE_CALL
  assert(call.args[0]==1 && call.args[1] && state==0 && regs.w[16]==0x5000);
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
  assert(stack[16]==0x116 && stack[17]==1);
  for(unsigned int i=18;i<24;i++) assert(stack[i]==0x123400+i);
 }
 puts("PASS cold-gate clobber JIT: no manual register saves, hot unlock branch, minimal COMPLETE/refusal, native FULL continuation");
}
'''


def main():
    symbols = {'kd_spin_lock_pinned_clobber_v1': 0x3000,
               'kd_spin_lock_clobber_v1': 0x3100,
               'kd_spin_unlock_clobber_v1': 0x4000,
               'kd_spin_direct_native_unlock': 0x6000,
               'kd_spin_lock': 0x5000}
    for native in (False, True):
        # A compiler-spilled body value, not five incoming register saves.
        # CPU heat is consumed before the continuation and is never a JIT input.
        code = bytes.fromhex('48ff0424')  # incq (%rsp)
        if native:
            # Existing ordinary-C inner control calls retain resumable FULL
            # boundaries. The new native cold entry precedes the outer JIT
            # continuation and is deliberately not admitted as an inner lock.
            for target in (0x5000, 0x6000):
                code += bytes.fromhex('48c7c700910000')
                code += b'\xe8' + (target-0x1000-len(code)-5).to_bytes(4, 'little', signed=True)
        # The lock-byte input lives in a guarded stack slot in this fixture;
        # production callers read their actual lock object. Both control ABIs
        # must remain distinct even though hot ownership selects only one.
        code += bytes.fromhex('807c2408050f84')  # cmpb $5,8(%rsp); je cold
        cold_branch = len(code)
        code += bytes(4)
        code += bytes.fromhex('48c7c7009000004889e648c7c2')
        final_ip = 0x1000+len(code)+4+3+5
        code += final_ip.to_bytes(4, 'little') + bytes.fromhex('4889e9')
        code += b'\xe8' + (0x4000-0x1000-len(code)-5).to_bytes(4, 'little', signed=True)
        code += b'\xc3'
        cold_offset = len(code)
        code = (code[:cold_branch] + (cold_offset-cold_branch-4).to_bytes(4, 'little', signed=True)
                + code[cold_branch+4:])
        code += bytes.fromhex('48c7c700900000')
        code += b'\xe8' + (0x6000-0x1000-len(code)-5).to_bytes(4, 'little', signed=True)
        code += b'\xc3'
        assembly, log, status = render(code.hex(), kernel_symbols=symbols, abi=1,
                                       body_witness=True, return_status=True)
        assert status == 0, log
        # Exercise the production stack-input predicate before any body write.
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
