
/work/out/vmlinux:     file format elf64-x86-64


Disassembly of section .text:

ffffffff8142b500 <kd_q_lock_slow>:
ffffffff8142b500:	55                   	push   %rbp
ffffffff8142b501:	48 89 e5             	mov    %rsp,%rbp
ffffffff8142b504:	53                   	push   %rbx
ffffffff8142b505:	8b 17                	mov    (%rdi),%edx
ffffffff8142b507:	48 89 fb             	mov    %rdi,%rbx
ffffffff8142b50a:	81 fa 00 01 00 00    	cmp    $0x100,%edx
ffffffff8142b510:	0f 84 6b 02 00 00    	je     ffffffff8142b781 <kd_q_lock_slow+0x281>
ffffffff8142b516:	81 fa ff 00 00 00    	cmp    $0xff,%edx
ffffffff8142b51c:	77 5f                	ja     ffffffff8142b57d <kd_q_lock_slow+0x7d>
ffffffff8142b51e:	f0 0f ba 2b 08       	lock btsl $0x8,(%rbx)
ffffffff8142b523:	0f 92 c0             	setb   %al
ffffffff8142b526:	8b 13                	mov    (%rbx),%edx
ffffffff8142b528:	0f b6 c0             	movzbl %al,%eax
ffffffff8142b52b:	c1 e0 08             	shl    $0x8,%eax
ffffffff8142b52e:	30 f6                	xor    %dh,%dh
ffffffff8142b530:	09 c2                	or     %eax,%edx
ffffffff8142b532:	81 fa ff 00 00 00    	cmp    $0xff,%edx
ffffffff8142b538:	77 3a                	ja     ffffffff8142b574 <kd_q_lock_slow+0x74>
ffffffff8142b53a:	85 d2                	test   %edx,%edx
ffffffff8142b53c:	74 10                	je     ffffffff8142b54e <kd_q_lock_slow+0x4e>
ffffffff8142b53e:	0f b6 03             	movzbl (%rbx),%eax
ffffffff8142b541:	84 c0                	test   %al,%al
ffffffff8142b543:	74 09                	je     ffffffff8142b54e <kd_q_lock_slow+0x4e>
ffffffff8142b545:	f3 90                	pause  
ffffffff8142b547:	0f b6 03             	movzbl (%rbx),%eax
ffffffff8142b54a:	84 c0                	test   %al,%al
ffffffff8142b54c:	75 f7                	jne    ffffffff8142b545 <kd_q_lock_slow+0x45>
ffffffff8142b54e:	83 e2 02             	and    $0x2,%edx
ffffffff8142b551:	83 ca 01             	or     $0x1,%edx
ffffffff8142b554:	66 89 13             	mov    %dx,(%rbx)
ffffffff8142b557:	b8 01 00 00 00       	mov    $0x1,%eax
ffffffff8142b55c:	48 8b 5d f8          	mov    -0x8(%rbp),%rbx
ffffffff8142b560:	c9                   	leave  
ffffffff8142b561:	31 d2                	xor    %edx,%edx
ffffffff8142b563:	31 c9                	xor    %ecx,%ecx
ffffffff8142b565:	31 f6                	xor    %esi,%esi
ffffffff8142b567:	31 ff                	xor    %edi,%edi
ffffffff8142b569:	45 31 c0             	xor    %r8d,%r8d
ffffffff8142b56c:	45 31 c9             	xor    %r9d,%r9d
ffffffff8142b56f:	e9 3c ca 1e 01       	jmp    ffffffff82617fb0 <__pi___x86_return_thunk>
ffffffff8142b574:	f6 c6 01             	test   $0x1,%dh
ffffffff8142b577:	75 04                	jne    ffffffff8142b57d <kd_q_lock_slow+0x7d>
ffffffff8142b579:	c6 43 01 00          	movb   $0x0,0x1(%rbx)
ffffffff8142b57d:	0f b6 05 9c 17 29 02 	movzbl 0x229179c(%rip),%eax        # ffffffff836bcd20 <kd_adapt>
ffffffff8142b584:	84 c0                	test   %al,%al
ffffffff8142b586:	0f 84 dc 01 00 00    	je     ffffffff8142b768 <kd_q_lock_slow+0x268>
ffffffff8142b58c:	66 85 d2             	test   %dx,%dx
ffffffff8142b58f:	75 30                	jne    ffffffff8142b5c1 <kd_q_lock_slow+0xc1>
ffffffff8142b591:	89 d0                	mov    %edx,%eax
ffffffff8142b593:	c1 e8 10             	shr    $0x10,%eax
ffffffff8142b596:	74 29                	je     ffffffff8142b5c1 <kd_q_lock_slow+0xc1>
ffffffff8142b598:	eb 27                	jmp    ffffffff8142b5c1 <kd_q_lock_slow+0xc1>
ffffffff8142b59a:	8b 05 70 17 29 02    	mov    0x2291770(%rip),%eax        # ffffffff836bcd10 <kd_spin_phase_wait>
ffffffff8142b5a0:	b9 80 00 00 00       	mov    $0x80,%ecx
ffffffff8142b5a5:	39 c8                	cmp    %ecx,%eax
ffffffff8142b5a7:	0f 47 c1             	cmova  %ecx,%eax
ffffffff8142b5aa:	eb 10                	jmp    ffffffff8142b5bc <kd_q_lock_slow+0xbc>
ffffffff8142b5ac:	f3 90                	pause  
ffffffff8142b5ae:	8b 13                	mov    (%rbx),%edx
ffffffff8142b5b0:	66 85 d2             	test   %dx,%dx
ffffffff8142b5b3:	75 0c                	jne    ffffffff8142b5c1 <kd_q_lock_slow+0xc1>
ffffffff8142b5b5:	89 d7                	mov    %edx,%edi
ffffffff8142b5b7:	c1 ef 10             	shr    $0x10,%edi
ffffffff8142b5ba:	74 05                	je     ffffffff8142b5c1 <kd_q_lock_slow+0xc1>
ffffffff8142b5bc:	83 e8 01             	sub    $0x1,%eax
ffffffff8142b5bf:	73 eb                	jae    ffffffff8142b5ac <kd_q_lock_slow+0xac>
ffffffff8142b5c1:	83 e2 02             	and    $0x2,%edx
ffffffff8142b5c4:	0f 85 9e 01 00 00    	jne    ffffffff8142b768 <kd_q_lock_slow+0x268>
ffffffff8142b5ca:	65 48 8b 05 56 3a 7a 	mov    %gs:0x27a3a56(%rip),%rax        # ffffffff83bcf028 <this_cpu_off>
ffffffff8142b5d1:	02 
ffffffff8142b5d2:	65 48 ff 05 4e f3 7b 	incq   %gs:0x27bf34e(%rip)        # ffffffff83bea928 <kd_cpu+0x1a8>
ffffffff8142b5d9:	02 
ffffffff8142b5da:	48 8d b0 80 a7 be 83 	lea    -0x7c415880(%rax),%rsi
ffffffff8142b5e1:	8b 86 a0 01 00 00    	mov    0x1a0(%rsi),%eax
ffffffff8142b5e7:	83 f8 03             	cmp    $0x3,%eax
ffffffff8142b5ea:	0f 8f 54 02 00 00    	jg     ffffffff8142b844 <kd_q_lock_slow+0x344>
ffffffff8142b5f0:	8d 50 01             	lea    0x1(%rax),%edx
ffffffff8142b5f3:	89 96 a0 01 00 00    	mov    %edx,0x1a0(%rsi)
ffffffff8142b5f9:	65 8b 3d 34 3a 7a 02 	mov    %gs:0x27a3a34(%rip),%edi        # ffffffff83bcf034 <cpu_number>
ffffffff8142b600:	48 63 d0             	movslq %eax,%rdx
ffffffff8142b603:	48 8d 4a 06          	lea    0x6(%rdx),%rcx
ffffffff8142b607:	48 c1 e2 06          	shl    $0x6,%rdx
ffffffff8142b60b:	48 c1 e1 06          	shl    $0x6,%rcx
ffffffff8142b60f:	8d 3c bd 04 00 00 00 	lea    0x4(,%rdi,4),%edi
ffffffff8142b616:	48 01 f2             	add    %rsi,%rdx
ffffffff8142b619:	09 f8                	or     %edi,%eax
ffffffff8142b61b:	48 01 f1             	add    %rsi,%rcx
ffffffff8142b61e:	48 c7 82 80 01 00 00 	movq   $0x0,0x180(%rdx)
ffffffff8142b625:	00 00 00 00 
ffffffff8142b629:	66 89 82 8c 01 00 00 	mov    %ax,0x18c(%rdx)
ffffffff8142b630:	c6 82 b0 01 00 00 00 	movb   $0x0,0x1b0(%rdx)
ffffffff8142b637:	c7 41 08 01 00 00 00 	movl   $0x1,0x8(%rcx)
ffffffff8142b63e:	8b 03                	mov    (%rbx),%eax
ffffffff8142b640:	85 c0                	test   %eax,%eax
ffffffff8142b642:	0f 84 62 01 00 00    	je     ffffffff8142b7aa <kd_q_lock_slow+0x2aa>
ffffffff8142b648:	0f b7 82 8c 01 00 00 	movzwl 0x18c(%rdx),%eax
ffffffff8142b64f:	66 87 43 02          	xchg   %ax,0x2(%rbx)
ffffffff8142b653:	66 85 c0             	test   %ax,%ax
ffffffff8142b656:	0f 84 69 01 00 00    	je     ffffffff8142b7c5 <kd_q_lock_slow+0x2c5>
ffffffff8142b65c:	41 89 c0             	mov    %eax,%r8d
ffffffff8142b65f:	83 e0 03             	and    $0x3,%eax
ffffffff8142b662:	48 c7 c7 80 a7 be 83 	mov    $0xffffffff83bea780,%rdi
ffffffff8142b669:	66 41 c1 e8 02       	shr    $0x2,%r8w
ffffffff8142b66e:	48 83 c0 06          	add    $0x6,%rax
ffffffff8142b672:	45 0f b7 c0          	movzwl %r8w,%r8d
ffffffff8142b676:	48 c1 e0 06          	shl    $0x6,%rax
ffffffff8142b67a:	41 83 e8 01          	sub    $0x1,%r8d
ffffffff8142b67e:	4d 63 c0             	movslq %r8d,%r8
ffffffff8142b681:	4a 03 3c c5 60 7f fb 	add    -0x7d0480a0(,%r8,8),%rdi
ffffffff8142b688:	82 
ffffffff8142b689:	48 01 c7             	add    %rax,%rdi
ffffffff8142b68c:	48 89 0f             	mov    %rcx,(%rdi)
ffffffff8142b68f:	75 07                	jne    ffffffff8142b698 <kd_q_lock_slow+0x198>
ffffffff8142b691:	e9 2f 01 00 00       	jmp    ffffffff8142b7c5 <kd_q_lock_slow+0x2c5>
ffffffff8142b696:	f3 90                	pause  
ffffffff8142b698:	8b 82 88 01 00 00    	mov    0x188(%rdx),%eax
ffffffff8142b69e:	83 f8 01             	cmp    $0x1,%eax
ffffffff8142b6a1:	74 f3                	je     ffffffff8142b696 <kd_q_lock_slow+0x196>
ffffffff8142b6a3:	83 f8 06             	cmp    $0x6,%eax
ffffffff8142b6a6:	48 8b 82 80 01 00 00 	mov    0x180(%rdx),%rax
ffffffff8142b6ad:	0f 84 b0 01 00 00    	je     ffffffff8142b863 <kd_q_lock_slow+0x363>
ffffffff8142b6b3:	48 85 c0             	test   %rax,%rax
ffffffff8142b6b6:	74 03                	je     ffffffff8142b6bb <kd_q_lock_slow+0x1bb>
ffffffff8142b6b8:	0f 18 08             	prefetcht0 (%rax)
ffffffff8142b6bb:	0f b6 05 5e 16 29 02 	movzbl 0x229165e(%rip),%eax        # ffffffff836bcd20 <kd_adapt>
ffffffff8142b6c2:	84 c0                	test   %al,%al
ffffffff8142b6c4:	0f 84 06 01 00 00    	je     ffffffff8142b7d0 <kd_q_lock_slow+0x2d0>
ffffffff8142b6ca:	e9 01 01 00 00       	jmp    ffffffff8142b7d0 <kd_q_lock_slow+0x2d0>
ffffffff8142b6cf:	8b 46 68             	mov    0x68(%rsi),%eax
ffffffff8142b6d2:	8d 78 01             	lea    0x1(%rax),%edi
ffffffff8142b6d5:	89 7e 68             	mov    %edi,0x68(%rsi)
ffffffff8142b6d8:	a8 7f                	test   $0x7f,%al
ffffffff8142b6da:	0f 85 f0 00 00 00    	jne    ffffffff8142b7d0 <kd_q_lock_slow+0x2d0>
ffffffff8142b6e0:	44 8b 05 35 16 29 02 	mov    0x2291635(%rip),%r8d        # ffffffff836bcd1c <kd_deleg_enter>
ffffffff8142b6e7:	48 89 c8             	mov    %rcx,%rax
ffffffff8142b6ea:	31 ff                	xor    %edi,%edi
ffffffff8142b6ec:	45 85 c0             	test   %r8d,%r8d
ffffffff8142b6ef:	7f 0a                	jg     ffffffff8142b6fb <kd_q_lock_slow+0x1fb>
ffffffff8142b6f1:	eb 19                	jmp    ffffffff8142b70c <kd_q_lock_slow+0x20c>
ffffffff8142b6f3:	83 c7 01             	add    $0x1,%edi
ffffffff8142b6f6:	41 39 f8             	cmp    %edi,%r8d
ffffffff8142b6f9:	74 11                	je     ffffffff8142b70c <kd_q_lock_slow+0x20c>
ffffffff8142b6fb:	48 8b 00             	mov    (%rax),%rax
ffffffff8142b6fe:	48 85 c0             	test   %rax,%rax
ffffffff8142b701:	75 f0                	jne    ffffffff8142b6f3 <kd_q_lock_slow+0x1f3>
ffffffff8142b703:	41 39 f8             	cmp    %edi,%r8d
ffffffff8142b706:	0f 8f c4 00 00 00    	jg     ffffffff8142b7d0 <kd_q_lock_slow+0x2d0>
ffffffff8142b70c:	48 83 86 18 04 00 00 	addq   $0x1,0x418(%rsi)
ffffffff8142b713:	01 
ffffffff8142b714:	0f b6 05 05 16 29 02 	movzbl 0x2291605(%rip),%eax        # ffffffff836bcd20 <kd_adapt>
ffffffff8142b71b:	84 c0                	test   %al,%al
ffffffff8142b71d:	0f 84 07 01 00 00    	je     ffffffff8142b82a <kd_q_lock_slow+0x32a>
ffffffff8142b723:	8b 3d eb 15 29 02    	mov    0x22915eb(%rip),%edi        # ffffffff836bcd14 <kd_deleg_exit>
ffffffff8142b729:	31 c0                	xor    %eax,%eax
ffffffff8142b72b:	85 ff                	test   %edi,%edi
ffffffff8142b72d:	7f 10                	jg     ffffffff8142b73f <kd_q_lock_slow+0x23f>
ffffffff8142b72f:	e9 f6 00 00 00       	jmp    ffffffff8142b82a <kd_q_lock_slow+0x32a>
ffffffff8142b734:	83 c0 01             	add    $0x1,%eax
ffffffff8142b737:	39 c7                	cmp    %eax,%edi
ffffffff8142b739:	0f 84 eb 00 00 00    	je     ffffffff8142b82a <kd_q_lock_slow+0x32a>
ffffffff8142b73f:	48 8b 09             	mov    (%rcx),%rcx
ffffffff8142b742:	48 85 c9             	test   %rcx,%rcx
ffffffff8142b745:	75 ed                	jne    ffffffff8142b734 <kd_q_lock_slow+0x234>
ffffffff8142b747:	39 c7                	cmp    %eax,%edi
ffffffff8142b749:	0f 8e db 00 00 00    	jle    ffffffff8142b82a <kd_q_lock_slow+0x32a>
ffffffff8142b74f:	48 83 86 20 04 00 00 	addq   $0x1,0x420(%rsi)
ffffffff8142b756:	01 
ffffffff8142b757:	eb 77                	jmp    ffffffff8142b7d0 <kd_q_lock_slow+0x2d0>
ffffffff8142b759:	0f b6 05 c0 15 29 02 	movzbl 0x22915c0(%rip),%eax        # ffffffff836bcd20 <kd_adapt>
ffffffff8142b760:	84 c0                	test   %al,%al
ffffffff8142b762:	0f 85 59 fe ff ff    	jne    ffffffff8142b5c1 <kd_q_lock_slow+0xc1>
ffffffff8142b768:	48 89 f7             	mov    %rsi,%rdi
ffffffff8142b76b:	e8 90 df ff ff       	call   ffffffff81429700 <kd_can_offer>
ffffffff8142b770:	89 c2                	mov    %eax,%edx
ffffffff8142b772:	31 c0                	xor    %eax,%eax
ffffffff8142b774:	84 d2                	test   %dl,%dl
ffffffff8142b776:	0f 84 4e fe ff ff    	je     ffffffff8142b5ca <kd_q_lock_slow+0xca>
ffffffff8142b77c:	e9 db fd ff ff       	jmp    ffffffff8142b55c <kd_q_lock_slow+0x5c>
ffffffff8142b781:	8b 0f                	mov    (%rdi),%ecx
ffffffff8142b783:	b8 00 02 00 00       	mov    $0x200,%eax
ffffffff8142b788:	81 f9 00 01 00 00    	cmp    $0x100,%ecx
ffffffff8142b78e:	74 07                	je     ffffffff8142b797 <kd_q_lock_slow+0x297>
ffffffff8142b790:	eb 11                	jmp    ffffffff8142b7a3 <kd_q_lock_slow+0x2a3>
ffffffff8142b792:	83 e8 01             	sub    $0x1,%eax
ffffffff8142b795:	74 c2                	je     ffffffff8142b759 <kd_q_lock_slow+0x259>
ffffffff8142b797:	f3 90                	pause  
ffffffff8142b799:	8b 0b                	mov    (%rbx),%ecx
ffffffff8142b79b:	81 f9 00 01 00 00    	cmp    $0x100,%ecx
ffffffff8142b7a1:	74 ef                	je     ffffffff8142b792 <kd_q_lock_slow+0x292>
ffffffff8142b7a3:	89 ca                	mov    %ecx,%edx
ffffffff8142b7a5:	e9 6c fd ff ff       	jmp    ffffffff8142b516 <kd_q_lock_slow+0x16>
ffffffff8142b7aa:	bf 01 00 00 00       	mov    $0x1,%edi
ffffffff8142b7af:	f0 0f b1 3b          	lock cmpxchg %edi,(%rbx)
ffffffff8142b7b3:	0f 85 8f fe ff ff    	jne    ffffffff8142b648 <kd_q_lock_slow+0x148>
ffffffff8142b7b9:	83 ae a0 01 00 00 01 	subl   $0x1,0x1a0(%rsi)
ffffffff8142b7c0:	e9 92 fd ff ff       	jmp    ffffffff8142b557 <kd_q_lock_slow+0x57>
ffffffff8142b7c5:	0f b6 03             	movzbl (%rbx),%eax
ffffffff8142b7c8:	a8 02                	test   $0x2,%al
ffffffff8142b7ca:	0f 85 44 ff ff ff    	jne    ffffffff8142b714 <kd_q_lock_slow+0x214>
ffffffff8142b7d0:	41 b9 01 00 00 00    	mov    $0x1,%r9d
ffffffff8142b7d6:	b9 01 00 00 00       	mov    $0x1,%ecx
ffffffff8142b7db:	eb 02                	jmp    ffffffff8142b7df <kd_q_lock_slow+0x2df>
ffffffff8142b7dd:	f3 90                	pause  
ffffffff8142b7df:	8b 03                	mov    (%rbx),%eax
ffffffff8142b7e1:	66 85 c0             	test   %ax,%ax
ffffffff8142b7e4:	75 f7                	jne    ffffffff8142b7dd <kd_q_lock_slow+0x2dd>
ffffffff8142b7e6:	41 89 c0             	mov    %eax,%r8d
ffffffff8142b7e9:	0f b7 ba 8c 01 00 00 	movzwl 0x18c(%rdx),%edi
ffffffff8142b7f0:	41 c1 e8 10          	shr    $0x10,%r8d
ffffffff8142b7f4:	41 39 f8             	cmp    %edi,%r8d
ffffffff8142b7f7:	74 3e                	je     ffffffff8142b837 <kd_q_lock_slow+0x337>
ffffffff8142b7f9:	88 0b                	mov    %cl,(%rbx)
ffffffff8142b7fb:	48 8b 82 80 01 00 00 	mov    0x180(%rdx),%rax
ffffffff8142b802:	48 85 c0             	test   %rax,%rax
ffffffff8142b805:	74 15                	je     ffffffff8142b81c <kd_q_lock_slow+0x31c>
ffffffff8142b807:	83 e1 02             	and    $0x2,%ecx
ffffffff8142b80a:	80 f9 01             	cmp    $0x1,%cl
ffffffff8142b80d:	19 d2                	sbb    %edx,%edx
ffffffff8142b80f:	83 e2 fd             	and    $0xfffffffd,%edx
ffffffff8142b812:	83 c2 06             	add    $0x6,%edx
ffffffff8142b815:	89 50 08             	mov    %edx,0x8(%rax)
ffffffff8142b818:	eb 9f                	jmp    ffffffff8142b7b9 <kd_q_lock_slow+0x2b9>
ffffffff8142b81a:	f3 90                	pause  
ffffffff8142b81c:	48 8b 82 80 01 00 00 	mov    0x180(%rdx),%rax
ffffffff8142b823:	48 85 c0             	test   %rax,%rax
ffffffff8142b826:	74 f2                	je     ffffffff8142b81a <kd_q_lock_slow+0x31a>
ffffffff8142b828:	eb dd                	jmp    ffffffff8142b807 <kd_q_lock_slow+0x307>
ffffffff8142b82a:	41 b9 03 00 00 00    	mov    $0x3,%r9d
ffffffff8142b830:	b9 03 00 00 00       	mov    $0x3,%ecx
ffffffff8142b835:	eb a8                	jmp    ffffffff8142b7df <kd_q_lock_slow+0x2df>
ffffffff8142b837:	f0 44 0f b1 0b       	lock cmpxchg %r9d,(%rbx)
ffffffff8142b83c:	0f 84 77 ff ff ff    	je     ffffffff8142b7b9 <kd_q_lock_slow+0x2b9>
ffffffff8142b842:	eb b5                	jmp    ffffffff8142b7f9 <kd_q_lock_slow+0x2f9>
ffffffff8142b844:	8b 03                	mov    (%rbx),%eax
ffffffff8142b846:	ba 01 00 00 00       	mov    $0x1,%edx
ffffffff8142b84b:	85 c0                	test   %eax,%eax
ffffffff8142b84d:	74 08                	je     ffffffff8142b857 <kd_q_lock_slow+0x357>
ffffffff8142b84f:	f3 90                	pause  
ffffffff8142b851:	8b 03                	mov    (%rbx),%eax
ffffffff8142b853:	85 c0                	test   %eax,%eax
ffffffff8142b855:	75 f8                	jne    ffffffff8142b84f <kd_q_lock_slow+0x34f>
ffffffff8142b857:	f0 0f b1 13          	lock cmpxchg %edx,(%rbx)
ffffffff8142b85b:	0f 84 f6 fc ff ff    	je     ffffffff8142b557 <kd_q_lock_slow+0x57>
ffffffff8142b861:	eb ec                	jmp    ffffffff8142b84f <kd_q_lock_slow+0x34f>
ffffffff8142b863:	48 85 c0             	test   %rax,%rax
ffffffff8142b866:	0f 84 a8 fe ff ff    	je     ffffffff8142b714 <kd_q_lock_slow+0x214>
ffffffff8142b86c:	0f 18 08             	prefetcht0 (%rax)
ffffffff8142b86f:	e9 a0 fe ff ff       	jmp    ffffffff8142b714 <kd_q_lock_slow+0x214>

Disassembly of section .data:

Disassembly of section .init.text:

Disassembly of section .altinstr_aux:

Disassembly of section .altinstr_replacement:

Disassembly of section .exit.text:
