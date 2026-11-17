
/work/out/vmlinux:     file format elf64-x86-64


Disassembly of section .text:

ffffffff81427eb0 <kd_spin_lock_irqsave>:
ffffffff81427eb0:	9c                   	pushf  
ffffffff81427eb1:	59                   	pop    %rcx
ffffffff81427eb2:	fa                   	cli    
ffffffff81427eb3:	65 ff 05 76 71 7a 02 	incl   %gs:0x27a7176(%rip)        # ffffffff83bcf030 <__preempt_count>
ffffffff81427eba:	31 c0                	xor    %eax,%eax
ffffffff81427ebc:	ba 01 00 00 00       	mov    $0x1,%edx
ffffffff81427ec1:	f0 0f b1 17          	lock cmpxchg %edx,(%rdi)
ffffffff81427ec5:	75 08                	jne    ffffffff81427ecf <kd_spin_lock_irqsave+0x1f>
ffffffff81427ec7:	48 89 c8             	mov    %rcx,%rax
ffffffff81427eca:	e9 e1 00 1f 01       	jmp    ffffffff82617fb0 <__pi___x86_return_thunk>
ffffffff81427ecf:	89 c2                	mov    %eax,%edx
ffffffff81427ed1:	48 8b 34 24          	mov    (%rsp),%rsi
ffffffff81427ed5:	51                   	push   %rcx
ffffffff81427ed6:	57                   	push   %rdi
ffffffff81427ed7:	e8 24 36 00 00       	call   ffffffff8142b500 <kd_q_lock_slow>
ffffffff81427edc:	5f                   	pop    %rdi
ffffffff81427edd:	59                   	pop    %rcx
ffffffff81427ede:	84 c0                	test   %al,%al
ffffffff81427ee0:	74 08                	je     ffffffff81427eea <kd_spin_lock_irqsave+0x3a>
ffffffff81427ee2:	48 89 c8             	mov    %rcx,%rax
ffffffff81427ee5:	e9 c6 00 1f 01       	jmp    ffffffff82617fb0 <__pi___x86_return_thunk>
ffffffff81427eea:	65 0f ba 2d e1 28 7c 	btsl   $0x0,%gs:0x27c28e1(%rip)        # ffffffff83bea7d4 <kd_cpu+0x54>
ffffffff81427ef1:	02 00 
ffffffff81427ef3:	0f 82 b0 00 00 00    	jb     ffffffff81427fa9 <kd_spin_lock_irqsave+0xf9>
ffffffff81427ef9:	48 89 c8             	mov    %rcx,%rax
ffffffff81427efc:	65 48 89 1d 8c 29 7c 	mov    %rbx,%gs:0x27c298c(%rip)        # ffffffff83bea890 <kd_cpu+0x110>
ffffffff81427f03:	02 
ffffffff81427f04:	65 48 89 2d fc 28 7c 	mov    %rbp,%gs:0x27c28fc(%rip)        # ffffffff83bea808 <kd_cpu+0x88>
ffffffff81427f0b:	02 
ffffffff81427f0c:	65 4c 89 25 c4 29 7c 	mov    %r12,%gs:0x27c29c4(%rip)        # ffffffff83bea8d8 <kd_cpu+0x158>
ffffffff81427f13:	02 
ffffffff81427f14:	65 4c 89 2d c4 29 7c 	mov    %r13,%gs:0x27c29c4(%rip)        # ffffffff83bea8e0 <kd_cpu+0x160>
ffffffff81427f1b:	02 
ffffffff81427f1c:	65 4c 89 35 c4 29 7c 	mov    %r14,%gs:0x27c29c4(%rip)        # ffffffff83bea8e8 <kd_cpu+0x168>
ffffffff81427f23:	02 
ffffffff81427f24:	65 4c 89 3d c4 29 7c 	mov    %r15,%gs:0x27c29c4(%rip)        # ffffffff83bea8f0 <kd_cpu+0x170>
ffffffff81427f2b:	02 
ffffffff81427f2c:	65 48 89 05 ec 28 7c 	mov    %rax,%gs:0x27c28ec(%rip)        # ffffffff83bea820 <kd_cpu+0xa0>
ffffffff81427f33:	02 
ffffffff81427f34:	48 8d 44 24 08       	lea    0x8(%rsp),%rax
ffffffff81427f39:	65 48 89 05 bf 28 7c 	mov    %rax,%gs:0x27c28bf(%rip)        # ffffffff83bea800 <kd_cpu+0x80>
ffffffff81427f40:	02 
ffffffff81427f41:	48 8b 04 24          	mov    (%rsp),%rax
ffffffff81427f45:	65 48 89 05 c3 28 7c 	mov    %rax,%gs:0x27c28c3(%rip)        # ffffffff83bea810 <kd_cpu+0x90>
ffffffff81427f4c:	02 
ffffffff81427f4d:	9c                   	pushf  
ffffffff81427f4e:	65 8f 05 c3 28 7c 02 	pop    %gs:0x27c28c3(%rip)        # ffffffff83bea818 <kd_cpu+0x98>
ffffffff81427f55:	65 c6 05 0d 29 7c 02 	movb   $0x0,%gs:0x27c290d(%rip)        # ffffffff83bea86a <kd_cpu+0xea>
ffffffff81427f5c:	00 
ffffffff81427f5d:	48 89 fb             	mov    %rdi,%rbx
ffffffff81427f60:	65 48 8b 25 70 28 7c 	mov    %gs:0x27c2870(%rip),%rsp        # ffffffff83bea7d8 <kd_cpu+0x58>
ffffffff81427f67:	02 
ffffffff81427f68:	e8 53 51 00 00       	call   ffffffff8142d0c0 <kd_spin_wait>
ffffffff81427f6d:	85 c0                	test   %eax,%eax
ffffffff81427f6f:	0f 8f 1b 12 00 00    	jg     ffffffff81429190 <kd_resume>
ffffffff81427f75:	89 c6                	mov    %eax,%esi
ffffffff81427f77:	48 89 df             	mov    %rbx,%rdi
ffffffff81427f7a:	65 48 8b 1d 0e 29 7c 	mov    %gs:0x27c290e(%rip),%rbx        # ffffffff83bea890 <kd_cpu+0x110>
ffffffff81427f81:	02 
ffffffff81427f82:	65 48 8b 15 76 28 7c 	mov    %gs:0x27c2876(%rip),%rdx        # ffffffff83bea800 <kd_cpu+0x80>
ffffffff81427f89:	02 
ffffffff81427f8a:	48 8d 62 f8          	lea    -0x8(%rdx),%rsp
ffffffff81427f8e:	65 48 8b 15 8a 28 7c 	mov    %gs:0x27c288a(%rip),%rdx        # ffffffff83bea820 <kd_cpu+0xa0>
ffffffff81427f95:	02 
ffffffff81427f96:	65 c7 05 33 28 7c 02 	movl   $0x0,%gs:0x27c2833(%rip)        # ffffffff83bea7d4 <kd_cpu+0x54>
ffffffff81427f9d:	00 00 00 00 
ffffffff81427fa1:	48 89 d0             	mov    %rdx,%rax
ffffffff81427fa4:	e9 07 00 1f 01       	jmp    ffffffff82617fb0 <__pi___x86_return_thunk>
ffffffff81427fa9:	51                   	push   %rcx
ffffffff81427faa:	e8 71 52 00 00       	call   ffffffff8142d220 <kd_spin_lock_plain>
ffffffff81427faf:	58                   	pop    %rax
ffffffff81427fb0:	e9 fb ff 1e 01       	jmp    ffffffff82617fb0 <__pi___x86_return_thunk>

Disassembly of section .data:

Disassembly of section .init.text:

Disassembly of section .altinstr_aux:

Disassembly of section .altinstr_replacement:

Disassembly of section .exit.text:
