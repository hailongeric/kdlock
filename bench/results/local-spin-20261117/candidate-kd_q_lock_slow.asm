
/work/out/vmlinux:     file format elf64-x86-64


Disassembly of section .text:

ffffffff8142b500 <kd_q_lock_slow>:
ffffffff8142b500:	55                   	push   %rbp
ffffffff8142b501:	48 89 e5             	mov    %rsp,%rbp
ffffffff8142b504:	53                   	push   %rbx
ffffffff8142b505:	48 89 fb             	mov    %rdi,%rbx
ffffffff8142b508:	81 fa 00 01 00 00    	cmp    $0x100,%edx
ffffffff8142b50e:	0f 84 16 02 00 00    	je     ffffffff8142b72a <kd_q_lock_slow+0x22a>
ffffffff8142b514:	81 fa ff 00 00 00    	cmp    $0xff,%edx
ffffffff8142b51a:	77 5f                	ja     ffffffff8142b57b <kd_q_lock_slow+0x7b>
ffffffff8142b51c:	f0 0f ba 2b 08       	lock btsl $0x8,(%rbx)
ffffffff8142b521:	0f 92 c0             	setb   %al
ffffffff8142b524:	8b 13                	mov    (%rbx),%edx
ffffffff8142b526:	0f b6 c0             	movzbl %al,%eax
ffffffff8142b529:	c1 e0 08             	shl    $0x8,%eax
ffffffff8142b52c:	30 f6                	xor    %dh,%dh
ffffffff8142b52e:	09 c2                	or     %eax,%edx
ffffffff8142b530:	81 fa ff 00 00 00    	cmp    $0xff,%edx
ffffffff8142b536:	77 3a                	ja     ffffffff8142b572 <kd_q_lock_slow+0x72>
ffffffff8142b538:	85 d2                	test   %edx,%edx
ffffffff8142b53a:	74 10                	je     ffffffff8142b54c <kd_q_lock_slow+0x4c>
ffffffff8142b53c:	0f b6 03             	movzbl (%rbx),%eax
ffffffff8142b53f:	84 c0                	test   %al,%al
ffffffff8142b541:	74 09                	je     ffffffff8142b54c <kd_q_lock_slow+0x4c>
ffffffff8142b543:	f3 90                	pause  
ffffffff8142b545:	0f b6 03             	movzbl (%rbx),%eax
ffffffff8142b548:	84 c0                	test   %al,%al
ffffffff8142b54a:	75 f7                	jne    ffffffff8142b543 <kd_q_lock_slow+0x43>
ffffffff8142b54c:	83 e2 02             	and    $0x2,%edx
ffffffff8142b54f:	83 ca 01             	or     $0x1,%edx
ffffffff8142b552:	66 89 13             	mov    %dx,(%rbx)
ffffffff8142b555:	b8 01 00 00 00       	mov    $0x1,%eax
ffffffff8142b55a:	48 8b 5d f8          	mov    -0x8(%rbp),%rbx
ffffffff8142b55e:	c9                   	leave  
ffffffff8142b55f:	31 d2                	xor    %edx,%edx
ffffffff8142b561:	31 c9                	xor    %ecx,%ecx
ffffffff8142b563:	31 f6                	xor    %esi,%esi
ffffffff8142b565:	31 ff                	xor    %edi,%edi
ffffffff8142b567:	45 31 c0             	xor    %r8d,%r8d
ffffffff8142b56a:	45 31 c9             	xor    %r9d,%r9d
ffffffff8142b56d:	e9 3e ca 1e 01       	jmp    ffffffff82617fb0 <__pi___x86_return_thunk>
ffffffff8142b572:	f6 c6 01             	test   $0x1,%dh
ffffffff8142b575:	75 04                	jne    ffffffff8142b57b <kd_q_lock_slow+0x7b>
ffffffff8142b577:	c6 43 01 00          	movb   $0x0,0x1(%rbx)
ffffffff8142b57b:	0f b6 05 9a 17 29 02 	movzbl 0x229179a(%rip),%eax        # ffffffff836bcd1c <kd_adapt>
ffffffff8142b582:	84 c0                	test   %al,%al
ffffffff8142b584:	74 05                	je     ffffffff8142b58b <kd_q_lock_slow+0x8b>
ffffffff8142b586:	83 e2 02             	and    $0x2,%edx
ffffffff8142b589:	74 10                	je     ffffffff8142b59b <kd_q_lock_slow+0x9b>
ffffffff8142b58b:	48 89 f7             	mov    %rsi,%rdi
ffffffff8142b58e:	e8 6d e1 ff ff       	call   ffffffff81429700 <kd_can_offer>
ffffffff8142b593:	89 c2                	mov    %eax,%edx
ffffffff8142b595:	31 c0                	xor    %eax,%eax
ffffffff8142b597:	84 d2                	test   %dl,%dl
ffffffff8142b599:	75 bf                	jne    ffffffff8142b55a <kd_q_lock_slow+0x5a>
ffffffff8142b59b:	65 48 8b 05 85 3a 7a 	mov    %gs:0x27a3a85(%rip),%rax        # ffffffff83bcf028 <this_cpu_off>
ffffffff8142b5a2:	02 
ffffffff8142b5a3:	65 48 ff 05 7d f3 7b 	incq   %gs:0x27bf37d(%rip)        # ffffffff83bea928 <kd_cpu+0x1a8>
ffffffff8142b5aa:	02 
ffffffff8142b5ab:	48 8d b0 80 a7 be 83 	lea    -0x7c415880(%rax),%rsi
ffffffff8142b5b2:	8b 86 a0 01 00 00    	mov    0x1a0(%rsi),%eax
ffffffff8142b5b8:	83 f8 03             	cmp    $0x3,%eax
ffffffff8142b5bb:	0f 8f 3f 02 00 00    	jg     ffffffff8142b800 <kd_q_lock_slow+0x300>
ffffffff8142b5c1:	8d 50 01             	lea    0x1(%rax),%edx
ffffffff8142b5c4:	89 96 a0 01 00 00    	mov    %edx,0x1a0(%rsi)
ffffffff8142b5ca:	65 8b 3d 63 3a 7a 02 	mov    %gs:0x27a3a63(%rip),%edi        # ffffffff83bcf034 <cpu_number>
ffffffff8142b5d1:	48 63 d0             	movslq %eax,%rdx
ffffffff8142b5d4:	48 8d 4a 06          	lea    0x6(%rdx),%rcx
ffffffff8142b5d8:	48 c1 e2 06          	shl    $0x6,%rdx
ffffffff8142b5dc:	48 c1 e1 06          	shl    $0x6,%rcx
ffffffff8142b5e0:	8d 3c bd 04 00 00 00 	lea    0x4(,%rdi,4),%edi
ffffffff8142b5e7:	48 01 f2             	add    %rsi,%rdx
ffffffff8142b5ea:	09 f8                	or     %edi,%eax
ffffffff8142b5ec:	48 01 f1             	add    %rsi,%rcx
ffffffff8142b5ef:	48 c7 82 80 01 00 00 	movq   $0x0,0x180(%rdx)
ffffffff8142b5f6:	00 00 00 00 
ffffffff8142b5fa:	66 89 82 8c 01 00 00 	mov    %ax,0x18c(%rdx)
ffffffff8142b601:	c6 82 b0 01 00 00 00 	movb   $0x0,0x1b0(%rdx)
ffffffff8142b608:	c7 41 08 01 00 00 00 	movl   $0x1,0x8(%rcx)
ffffffff8142b60f:	8b 03                	mov    (%rbx),%eax
ffffffff8142b611:	85 c0                	test   %eax,%eax
ffffffff8142b613:	0f 84 4d 01 00 00    	je     ffffffff8142b766 <kd_q_lock_slow+0x266>
ffffffff8142b619:	0f b7 82 8c 01 00 00 	movzwl 0x18c(%rdx),%eax
ffffffff8142b620:	66 87 43 02          	xchg   %ax,0x2(%rbx)
ffffffff8142b624:	66 85 c0             	test   %ax,%ax
ffffffff8142b627:	0f 84 54 01 00 00    	je     ffffffff8142b781 <kd_q_lock_slow+0x281>
ffffffff8142b62d:	41 89 c0             	mov    %eax,%r8d
ffffffff8142b630:	83 e0 03             	and    $0x3,%eax
ffffffff8142b633:	48 c7 c7 80 a7 be 83 	mov    $0xffffffff83bea780,%rdi
ffffffff8142b63a:	66 41 c1 e8 02       	shr    $0x2,%r8w
ffffffff8142b63f:	48 83 c0 06          	add    $0x6,%rax
ffffffff8142b643:	45 0f b7 c0          	movzwl %r8w,%r8d
ffffffff8142b647:	48 c1 e0 06          	shl    $0x6,%rax
ffffffff8142b64b:	41 83 e8 01          	sub    $0x1,%r8d
ffffffff8142b64f:	4d 63 c0             	movslq %r8d,%r8
ffffffff8142b652:	4a 03 3c c5 60 7f fb 	add    -0x7d0480a0(,%r8,8),%rdi
ffffffff8142b659:	82 
ffffffff8142b65a:	48 01 c7             	add    %rax,%rdi
ffffffff8142b65d:	48 89 0f             	mov    %rcx,(%rdi)
ffffffff8142b660:	75 07                	jne    ffffffff8142b669 <kd_q_lock_slow+0x169>
ffffffff8142b662:	e9 1a 01 00 00       	jmp    ffffffff8142b781 <kd_q_lock_slow+0x281>
ffffffff8142b667:	f3 90                	pause  
ffffffff8142b669:	8b 82 88 01 00 00    	mov    0x188(%rdx),%eax
ffffffff8142b66f:	83 f8 01             	cmp    $0x1,%eax
ffffffff8142b672:	74 f3                	je     ffffffff8142b667 <kd_q_lock_slow+0x167>
ffffffff8142b674:	83 f8 06             	cmp    $0x6,%eax
ffffffff8142b677:	48 8b 82 80 01 00 00 	mov    0x180(%rdx),%rax
ffffffff8142b67e:	0f 84 9b 01 00 00    	je     ffffffff8142b81f <kd_q_lock_slow+0x31f>
ffffffff8142b684:	48 85 c0             	test   %rax,%rax
ffffffff8142b687:	74 03                	je     ffffffff8142b68c <kd_q_lock_slow+0x18c>
ffffffff8142b689:	0f 18 08             	prefetcht0 (%rax)
ffffffff8142b68c:	0f b6 05 89 16 29 02 	movzbl 0x2291689(%rip),%eax        # ffffffff836bcd1c <kd_adapt>
ffffffff8142b693:	84 c0                	test   %al,%al
ffffffff8142b695:	0f 84 f1 00 00 00    	je     ffffffff8142b78c <kd_q_lock_slow+0x28c>
ffffffff8142b69b:	e9 ec 00 00 00       	jmp    ffffffff8142b78c <kd_q_lock_slow+0x28c>
ffffffff8142b6a0:	8b 46 68             	mov    0x68(%rsi),%eax
ffffffff8142b6a3:	8d 78 01             	lea    0x1(%rax),%edi
ffffffff8142b6a6:	89 7e 68             	mov    %edi,0x68(%rsi)
ffffffff8142b6a9:	a8 7f                	test   $0x7f,%al
ffffffff8142b6ab:	0f 85 db 00 00 00    	jne    ffffffff8142b78c <kd_q_lock_slow+0x28c>
ffffffff8142b6b1:	44 8b 05 60 16 29 02 	mov    0x2291660(%rip),%r8d        # ffffffff836bcd18 <kd_deleg_enter>
ffffffff8142b6b8:	48 89 c8             	mov    %rcx,%rax
ffffffff8142b6bb:	31 ff                	xor    %edi,%edi
ffffffff8142b6bd:	45 85 c0             	test   %r8d,%r8d
ffffffff8142b6c0:	7f 0a                	jg     ffffffff8142b6cc <kd_q_lock_slow+0x1cc>
ffffffff8142b6c2:	eb 19                	jmp    ffffffff8142b6dd <kd_q_lock_slow+0x1dd>
ffffffff8142b6c4:	83 c7 01             	add    $0x1,%edi
ffffffff8142b6c7:	41 39 f8             	cmp    %edi,%r8d
ffffffff8142b6ca:	74 11                	je     ffffffff8142b6dd <kd_q_lock_slow+0x1dd>
ffffffff8142b6cc:	48 8b 00             	mov    (%rax),%rax
ffffffff8142b6cf:	48 85 c0             	test   %rax,%rax
ffffffff8142b6d2:	75 f0                	jne    ffffffff8142b6c4 <kd_q_lock_slow+0x1c4>
ffffffff8142b6d4:	41 39 f8             	cmp    %edi,%r8d
ffffffff8142b6d7:	0f 8f af 00 00 00    	jg     ffffffff8142b78c <kd_q_lock_slow+0x28c>
ffffffff8142b6dd:	48 83 86 18 04 00 00 	addq   $0x1,0x418(%rsi)
ffffffff8142b6e4:	01 
ffffffff8142b6e5:	0f b6 05 30 16 29 02 	movzbl 0x2291630(%rip),%eax        # ffffffff836bcd1c <kd_adapt>
ffffffff8142b6ec:	84 c0                	test   %al,%al
ffffffff8142b6ee:	0f 84 f2 00 00 00    	je     ffffffff8142b7e6 <kd_q_lock_slow+0x2e6>
ffffffff8142b6f4:	8b 3d 16 16 29 02    	mov    0x2291616(%rip),%edi        # ffffffff836bcd10 <kd_deleg_exit>
ffffffff8142b6fa:	31 c0                	xor    %eax,%eax
ffffffff8142b6fc:	85 ff                	test   %edi,%edi
ffffffff8142b6fe:	7f 10                	jg     ffffffff8142b710 <kd_q_lock_slow+0x210>
ffffffff8142b700:	e9 e1 00 00 00       	jmp    ffffffff8142b7e6 <kd_q_lock_slow+0x2e6>
ffffffff8142b705:	83 c0 01             	add    $0x1,%eax
ffffffff8142b708:	39 c7                	cmp    %eax,%edi
ffffffff8142b70a:	0f 84 d6 00 00 00    	je     ffffffff8142b7e6 <kd_q_lock_slow+0x2e6>
ffffffff8142b710:	48 8b 09             	mov    (%rcx),%rcx
ffffffff8142b713:	48 85 c9             	test   %rcx,%rcx
ffffffff8142b716:	75 ed                	jne    ffffffff8142b705 <kd_q_lock_slow+0x205>
ffffffff8142b718:	39 c7                	cmp    %eax,%edi
ffffffff8142b71a:	0f 8e c6 00 00 00    	jle    ffffffff8142b7e6 <kd_q_lock_slow+0x2e6>
ffffffff8142b720:	48 83 86 20 04 00 00 	addq   $0x1,0x420(%rsi)
ffffffff8142b727:	01 
ffffffff8142b728:	eb 62                	jmp    ffffffff8142b78c <kd_q_lock_slow+0x28c>
ffffffff8142b72a:	8b 17                	mov    (%rdi),%edx
ffffffff8142b72c:	b8 00 02 00 00       	mov    $0x200,%eax
ffffffff8142b731:	81 fa 00 01 00 00    	cmp    $0x100,%edx
ffffffff8142b737:	0f 85 d7 fd ff ff    	jne    ffffffff8142b514 <kd_q_lock_slow+0x14>
ffffffff8142b73d:	f3 90                	pause  
ffffffff8142b73f:	8b 13                	mov    (%rbx),%edx
ffffffff8142b741:	81 fa 00 01 00 00    	cmp    $0x100,%edx
ffffffff8142b747:	0f 85 c7 fd ff ff    	jne    ffffffff8142b514 <kd_q_lock_slow+0x14>
ffffffff8142b74d:	83 e8 01             	sub    $0x1,%eax
ffffffff8142b750:	75 eb                	jne    ffffffff8142b73d <kd_q_lock_slow+0x23d>
ffffffff8142b752:	0f b6 05 c3 15 29 02 	movzbl 0x22915c3(%rip),%eax        # ffffffff836bcd1c <kd_adapt>
ffffffff8142b759:	84 c0                	test   %al,%al
ffffffff8142b75b:	0f 85 3a fe ff ff    	jne    ffffffff8142b59b <kd_q_lock_slow+0x9b>
ffffffff8142b761:	e9 25 fe ff ff       	jmp    ffffffff8142b58b <kd_q_lock_slow+0x8b>
ffffffff8142b766:	bf 01 00 00 00       	mov    $0x1,%edi
ffffffff8142b76b:	f0 0f b1 3b          	lock cmpxchg %edi,(%rbx)
ffffffff8142b76f:	0f 85 a4 fe ff ff    	jne    ffffffff8142b619 <kd_q_lock_slow+0x119>
ffffffff8142b775:	83 ae a0 01 00 00 01 	subl   $0x1,0x1a0(%rsi)
ffffffff8142b77c:	e9 d4 fd ff ff       	jmp    ffffffff8142b555 <kd_q_lock_slow+0x55>
ffffffff8142b781:	0f b6 03             	movzbl (%rbx),%eax
ffffffff8142b784:	a8 02                	test   $0x2,%al
ffffffff8142b786:	0f 85 59 ff ff ff    	jne    ffffffff8142b6e5 <kd_q_lock_slow+0x1e5>
ffffffff8142b78c:	41 b9 01 00 00 00    	mov    $0x1,%r9d
ffffffff8142b792:	b9 01 00 00 00       	mov    $0x1,%ecx
ffffffff8142b797:	eb 02                	jmp    ffffffff8142b79b <kd_q_lock_slow+0x29b>
ffffffff8142b799:	f3 90                	pause  
ffffffff8142b79b:	8b 03                	mov    (%rbx),%eax
ffffffff8142b79d:	66 85 c0             	test   %ax,%ax
ffffffff8142b7a0:	75 f7                	jne    ffffffff8142b799 <kd_q_lock_slow+0x299>
ffffffff8142b7a2:	41 89 c0             	mov    %eax,%r8d
ffffffff8142b7a5:	0f b7 ba 8c 01 00 00 	movzwl 0x18c(%rdx),%edi
ffffffff8142b7ac:	41 c1 e8 10          	shr    $0x10,%r8d
ffffffff8142b7b0:	41 39 f8             	cmp    %edi,%r8d
ffffffff8142b7b3:	74 3e                	je     ffffffff8142b7f3 <kd_q_lock_slow+0x2f3>
ffffffff8142b7b5:	88 0b                	mov    %cl,(%rbx)
ffffffff8142b7b7:	48 8b 82 80 01 00 00 	mov    0x180(%rdx),%rax
ffffffff8142b7be:	48 85 c0             	test   %rax,%rax
ffffffff8142b7c1:	74 15                	je     ffffffff8142b7d8 <kd_q_lock_slow+0x2d8>
ffffffff8142b7c3:	83 e1 02             	and    $0x2,%ecx
ffffffff8142b7c6:	80 f9 01             	cmp    $0x1,%cl
ffffffff8142b7c9:	19 d2                	sbb    %edx,%edx
ffffffff8142b7cb:	83 e2 fd             	and    $0xfffffffd,%edx
ffffffff8142b7ce:	83 c2 06             	add    $0x6,%edx
ffffffff8142b7d1:	89 50 08             	mov    %edx,0x8(%rax)
ffffffff8142b7d4:	eb 9f                	jmp    ffffffff8142b775 <kd_q_lock_slow+0x275>
ffffffff8142b7d6:	f3 90                	pause  
ffffffff8142b7d8:	48 8b 82 80 01 00 00 	mov    0x180(%rdx),%rax
ffffffff8142b7df:	48 85 c0             	test   %rax,%rax
ffffffff8142b7e2:	74 f2                	je     ffffffff8142b7d6 <kd_q_lock_slow+0x2d6>
ffffffff8142b7e4:	eb dd                	jmp    ffffffff8142b7c3 <kd_q_lock_slow+0x2c3>
ffffffff8142b7e6:	41 b9 03 00 00 00    	mov    $0x3,%r9d
ffffffff8142b7ec:	b9 03 00 00 00       	mov    $0x3,%ecx
ffffffff8142b7f1:	eb a8                	jmp    ffffffff8142b79b <kd_q_lock_slow+0x29b>
ffffffff8142b7f3:	f0 44 0f b1 0b       	lock cmpxchg %r9d,(%rbx)
ffffffff8142b7f8:	0f 84 77 ff ff ff    	je     ffffffff8142b775 <kd_q_lock_slow+0x275>
ffffffff8142b7fe:	eb b5                	jmp    ffffffff8142b7b5 <kd_q_lock_slow+0x2b5>
ffffffff8142b800:	8b 03                	mov    (%rbx),%eax
ffffffff8142b802:	ba 01 00 00 00       	mov    $0x1,%edx
ffffffff8142b807:	85 c0                	test   %eax,%eax
ffffffff8142b809:	74 08                	je     ffffffff8142b813 <kd_q_lock_slow+0x313>
ffffffff8142b80b:	f3 90                	pause  
ffffffff8142b80d:	8b 03                	mov    (%rbx),%eax
ffffffff8142b80f:	85 c0                	test   %eax,%eax
ffffffff8142b811:	75 f8                	jne    ffffffff8142b80b <kd_q_lock_slow+0x30b>
ffffffff8142b813:	f0 0f b1 13          	lock cmpxchg %edx,(%rbx)
ffffffff8142b817:	0f 84 38 fd ff ff    	je     ffffffff8142b555 <kd_q_lock_slow+0x55>
ffffffff8142b81d:	eb ec                	jmp    ffffffff8142b80b <kd_q_lock_slow+0x30b>
ffffffff8142b81f:	48 85 c0             	test   %rax,%rax
ffffffff8142b822:	0f 84 bd fe ff ff    	je     ffffffff8142b6e5 <kd_q_lock_slow+0x1e5>
ffffffff8142b828:	0f 18 08             	prefetcht0 (%rax)
ffffffff8142b82b:	e9 b5 fe ff ff       	jmp    ffffffff8142b6e5 <kd_q_lock_slow+0x1e5>

Disassembly of section .data:

Disassembly of section .init.text:

Disassembly of section .altinstr_aux:

Disassembly of section .altinstr_replacement:

Disassembly of section .exit.text:
