
/work/out/vmlinux:     file format elf64-x86-64


Disassembly of section .text:

ffffffff81427c10 <kd_spin_lock>:
ffffffff81427c10:	65 ff 05 19 74 7a 02 	incl   %gs:0x27a7419(%rip)        # ffffffff83bcf030 <__preempt_count>
ffffffff81427c17:	31 c0                	xor    %eax,%eax
ffffffff81427c19:	ba 01 00 00 00       	mov    $0x1,%edx
ffffffff81427c1e:	f0 0f b1 17          	lock cmpxchg %edx,(%rdi)
ffffffff81427c22:	75 05                	jne    ffffffff81427c29 <kd_spin_lock+0x19>
ffffffff81427c24:	e9 87 03 1f 01       	jmp    ffffffff82617fb0 <__pi___x86_return_thunk>
ffffffff81427c29:	48 8b 34 24          	mov    (%rsp),%rsi
ffffffff81427c2d:	51                   	push   %rcx
ffffffff81427c2e:	57                   	push   %rdi
ffffffff81427c2f:	e8 1c 3a 00 00       	call   ffffffff8142b650 <kd_q_lock_slow>
ffffffff81427c34:	5f                   	pop    %rdi
ffffffff81427c35:	59                   	pop    %rcx
ffffffff81427c36:	84 c0                	test   %al,%al
ffffffff81427c38:	74 05                	je     ffffffff81427c3f <kd_spin_lock+0x2f>
ffffffff81427c3a:	e9 71 03 1f 01       	jmp    ffffffff82617fb0 <__pi___x86_return_thunk>
ffffffff81427c3f:	65 0f ba 2d 8c 2b 7c 	btsl   $0x0,%gs:0x27c2b8c(%rip)        # ffffffff83bea7d4 <kd_cpu+0x54>
ffffffff81427c46:	02 00 
ffffffff81427c48:	0f 82 b0 00 00 00    	jb     ffffffff81427cfe <kd_spin_lock+0xee>
ffffffff81427c4e:	48 89 c8             	mov    %rcx,%rax
ffffffff81427c51:	65 48 89 1d 37 2c 7c 	mov    %rbx,%gs:0x27c2c37(%rip)        # ffffffff83bea890 <kd_cpu+0x110>
ffffffff81427c58:	02 
ffffffff81427c59:	65 48 89 2d a7 2b 7c 	mov    %rbp,%gs:0x27c2ba7(%rip)        # ffffffff83bea808 <kd_cpu+0x88>
ffffffff81427c60:	02 
ffffffff81427c61:	65 4c 89 25 6f 2c 7c 	mov    %r12,%gs:0x27c2c6f(%rip)        # ffffffff83bea8d8 <kd_cpu+0x158>
ffffffff81427c68:	02 
ffffffff81427c69:	65 4c 89 2d 6f 2c 7c 	mov    %r13,%gs:0x27c2c6f(%rip)        # ffffffff83bea8e0 <kd_cpu+0x160>
ffffffff81427c70:	02 
ffffffff81427c71:	65 4c 89 35 6f 2c 7c 	mov    %r14,%gs:0x27c2c6f(%rip)        # ffffffff83bea8e8 <kd_cpu+0x168>
ffffffff81427c78:	02 
ffffffff81427c79:	65 4c 89 3d 6f 2c 7c 	mov    %r15,%gs:0x27c2c6f(%rip)        # ffffffff83bea8f0 <kd_cpu+0x170>
ffffffff81427c80:	02 
ffffffff81427c81:	65 48 89 05 97 2b 7c 	mov    %rax,%gs:0x27c2b97(%rip)        # ffffffff83bea820 <kd_cpu+0xa0>
ffffffff81427c88:	02 
ffffffff81427c89:	48 8d 44 24 08       	lea    0x8(%rsp),%rax
ffffffff81427c8e:	65 48 89 05 6a 2b 7c 	mov    %rax,%gs:0x27c2b6a(%rip)        # ffffffff83bea800 <kd_cpu+0x80>
ffffffff81427c95:	02 
ffffffff81427c96:	48 8b 04 24          	mov    (%rsp),%rax
ffffffff81427c9a:	65 48 89 05 6e 2b 7c 	mov    %rax,%gs:0x27c2b6e(%rip)        # ffffffff83bea810 <kd_cpu+0x90>
ffffffff81427ca1:	02 
ffffffff81427ca2:	9c                   	pushf  
ffffffff81427ca3:	65 8f 05 6e 2b 7c 02 	pop    %gs:0x27c2b6e(%rip)        # ffffffff83bea818 <kd_cpu+0x98>
ffffffff81427caa:	65 c6 05 b8 2b 7c 02 	movb   $0x0,%gs:0x27c2bb8(%rip)        # ffffffff83bea86a <kd_cpu+0xea>
ffffffff81427cb1:	00 
ffffffff81427cb2:	48 89 fb             	mov    %rdi,%rbx
ffffffff81427cb5:	65 48 8b 25 1b 2b 7c 	mov    %gs:0x27c2b1b(%rip),%rsp        # ffffffff83bea7d8 <kd_cpu+0x58>
ffffffff81427cbc:	02 
ffffffff81427cbd:	e8 3e 57 00 00       	call   ffffffff8142d400 <kd_spin_wait>
ffffffff81427cc2:	85 c0                	test   %eax,%eax
ffffffff81427cc4:	0f 8f c6 14 00 00    	jg     ffffffff81429190 <kd_resume>
ffffffff81427cca:	89 c6                	mov    %eax,%esi
ffffffff81427ccc:	48 89 df             	mov    %rbx,%rdi
ffffffff81427ccf:	65 48 8b 1d b9 2b 7c 	mov    %gs:0x27c2bb9(%rip),%rbx        # ffffffff83bea890 <kd_cpu+0x110>
ffffffff81427cd6:	02 
ffffffff81427cd7:	65 48 8b 15 21 2b 7c 	mov    %gs:0x27c2b21(%rip),%rdx        # ffffffff83bea800 <kd_cpu+0x80>
ffffffff81427cde:	02 
ffffffff81427cdf:	48 8d 62 f8          	lea    -0x8(%rdx),%rsp
ffffffff81427ce3:	65 48 8b 15 35 2b 7c 	mov    %gs:0x27c2b35(%rip),%rdx        # ffffffff83bea820 <kd_cpu+0xa0>
ffffffff81427cea:	02 
ffffffff81427ceb:	65 c7 05 de 2a 7c 02 	movl   $0x0,%gs:0x27c2ade(%rip)        # ffffffff83bea7d4 <kd_cpu+0x54>
ffffffff81427cf2:	00 00 00 00 
ffffffff81427cf6:	48 89 d0             	mov    %rdx,%rax
ffffffff81427cf9:	e9 b2 02 1f 01       	jmp    ffffffff82617fb0 <__pi___x86_return_thunk>
ffffffff81427cfe:	e9 fd 58 00 00       	jmp    ffffffff8142d600 <kd_spin_lock_plain>

Disassembly of section .data:

Disassembly of section .init.text:

Disassembly of section .altinstr_aux:

Disassembly of section .altinstr_replacement:

Disassembly of section .exit.text:
