
/work/out/vmlinux:     file format elf64-x86-64


Disassembly of section .text:

ffffffff81427c10 <kd_spin_lock>:
ffffffff81427c10:	65 ff 05 19 74 7a 02 	incl   %gs:0x27a7419(%rip)        # ffffffff83bcf030 <__preempt_count>
ffffffff81427c17:	31 c0                	xor    %eax,%eax
ffffffff81427c19:	ba 01 00 00 00       	mov    $0x1,%edx
ffffffff81427c1e:	f0 0f b1 17          	lock cmpxchg %edx,(%rdi)
ffffffff81427c22:	75 05                	jne    ffffffff81427c29 <kd_spin_lock+0x19>
ffffffff81427c24:	e9 87 03 1f 01       	jmp    ffffffff82617fb0 <__pi___x86_return_thunk>
ffffffff81427c29:	89 c2                	mov    %eax,%edx
ffffffff81427c2b:	48 8b 34 24          	mov    (%rsp),%rsi
ffffffff81427c2f:	51                   	push   %rcx
ffffffff81427c30:	57                   	push   %rdi
ffffffff81427c31:	e8 ca 38 00 00       	call   ffffffff8142b500 <kd_q_lock_slow>
ffffffff81427c36:	5f                   	pop    %rdi
ffffffff81427c37:	59                   	pop    %rcx
ffffffff81427c38:	84 c0                	test   %al,%al
ffffffff81427c3a:	74 05                	je     ffffffff81427c41 <kd_spin_lock+0x31>
ffffffff81427c3c:	e9 6f 03 1f 01       	jmp    ffffffff82617fb0 <__pi___x86_return_thunk>
ffffffff81427c41:	65 0f ba 2d 8a 2b 7c 	btsl   $0x0,%gs:0x27c2b8a(%rip)        # ffffffff83bea7d4 <kd_cpu+0x54>
ffffffff81427c48:	02 00 
ffffffff81427c4a:	0f 82 b0 00 00 00    	jb     ffffffff81427d00 <kd_spin_lock+0xf0>
ffffffff81427c50:	48 89 c8             	mov    %rcx,%rax
ffffffff81427c53:	65 48 89 1d 35 2c 7c 	mov    %rbx,%gs:0x27c2c35(%rip)        # ffffffff83bea890 <kd_cpu+0x110>
ffffffff81427c5a:	02 
ffffffff81427c5b:	65 48 89 2d a5 2b 7c 	mov    %rbp,%gs:0x27c2ba5(%rip)        # ffffffff83bea808 <kd_cpu+0x88>
ffffffff81427c62:	02 
ffffffff81427c63:	65 4c 89 25 6d 2c 7c 	mov    %r12,%gs:0x27c2c6d(%rip)        # ffffffff83bea8d8 <kd_cpu+0x158>
ffffffff81427c6a:	02 
ffffffff81427c6b:	65 4c 89 2d 6d 2c 7c 	mov    %r13,%gs:0x27c2c6d(%rip)        # ffffffff83bea8e0 <kd_cpu+0x160>
ffffffff81427c72:	02 
ffffffff81427c73:	65 4c 89 35 6d 2c 7c 	mov    %r14,%gs:0x27c2c6d(%rip)        # ffffffff83bea8e8 <kd_cpu+0x168>
ffffffff81427c7a:	02 
ffffffff81427c7b:	65 4c 89 3d 6d 2c 7c 	mov    %r15,%gs:0x27c2c6d(%rip)        # ffffffff83bea8f0 <kd_cpu+0x170>
ffffffff81427c82:	02 
ffffffff81427c83:	65 48 89 05 95 2b 7c 	mov    %rax,%gs:0x27c2b95(%rip)        # ffffffff83bea820 <kd_cpu+0xa0>
ffffffff81427c8a:	02 
ffffffff81427c8b:	48 8d 44 24 08       	lea    0x8(%rsp),%rax
ffffffff81427c90:	65 48 89 05 68 2b 7c 	mov    %rax,%gs:0x27c2b68(%rip)        # ffffffff83bea800 <kd_cpu+0x80>
ffffffff81427c97:	02 
ffffffff81427c98:	48 8b 04 24          	mov    (%rsp),%rax
ffffffff81427c9c:	65 48 89 05 6c 2b 7c 	mov    %rax,%gs:0x27c2b6c(%rip)        # ffffffff83bea810 <kd_cpu+0x90>
ffffffff81427ca3:	02 
ffffffff81427ca4:	9c                   	pushf  
ffffffff81427ca5:	65 8f 05 6c 2b 7c 02 	pop    %gs:0x27c2b6c(%rip)        # ffffffff83bea818 <kd_cpu+0x98>
ffffffff81427cac:	65 c6 05 b6 2b 7c 02 	movb   $0x0,%gs:0x27c2bb6(%rip)        # ffffffff83bea86a <kd_cpu+0xea>
ffffffff81427cb3:	00 
ffffffff81427cb4:	48 89 fb             	mov    %rdi,%rbx
ffffffff81427cb7:	65 48 8b 25 19 2b 7c 	mov    %gs:0x27c2b19(%rip),%rsp        # ffffffff83bea7d8 <kd_cpu+0x58>
ffffffff81427cbe:	02 
ffffffff81427cbf:	e8 fc 53 00 00       	call   ffffffff8142d0c0 <kd_spin_wait>
ffffffff81427cc4:	85 c0                	test   %eax,%eax
ffffffff81427cc6:	0f 8f c4 14 00 00    	jg     ffffffff81429190 <kd_resume>
ffffffff81427ccc:	89 c6                	mov    %eax,%esi
ffffffff81427cce:	48 89 df             	mov    %rbx,%rdi
ffffffff81427cd1:	65 48 8b 1d b7 2b 7c 	mov    %gs:0x27c2bb7(%rip),%rbx        # ffffffff83bea890 <kd_cpu+0x110>
ffffffff81427cd8:	02 
ffffffff81427cd9:	65 48 8b 15 1f 2b 7c 	mov    %gs:0x27c2b1f(%rip),%rdx        # ffffffff83bea800 <kd_cpu+0x80>
ffffffff81427ce0:	02 
ffffffff81427ce1:	48 8d 62 f8          	lea    -0x8(%rdx),%rsp
ffffffff81427ce5:	65 48 8b 15 33 2b 7c 	mov    %gs:0x27c2b33(%rip),%rdx        # ffffffff83bea820 <kd_cpu+0xa0>
ffffffff81427cec:	02 
ffffffff81427ced:	65 c7 05 dc 2a 7c 02 	movl   $0x0,%gs:0x27c2adc(%rip)        # ffffffff83bea7d4 <kd_cpu+0x54>
ffffffff81427cf4:	00 00 00 00 
ffffffff81427cf8:	48 89 d0             	mov    %rdx,%rax
ffffffff81427cfb:	e9 b0 02 1f 01       	jmp    ffffffff82617fb0 <__pi___x86_return_thunk>
ffffffff81427d00:	e9 1b 55 00 00       	jmp    ffffffff8142d220 <kd_spin_lock_plain>

Disassembly of section .data:

Disassembly of section .init.text:

Disassembly of section .altinstr_aux:

Disassembly of section .altinstr_replacement:

Disassembly of section .exit.text:
