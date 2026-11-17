
/work/out/vmlinux:     file format elf64-x86-64


Disassembly of section .text:

ffffffff8142b650 <kd_q_lock_slow>:
ffffffff8142b650:	55                   	push   %rbp
ffffffff8142b651:	48 89 e5             	mov    %rsp,%rbp
ffffffff8142b654:	53                   	push   %rbx
ffffffff8142b655:	8b 17                	mov    (%rdi),%edx
ffffffff8142b657:	48 89 fb             	mov    %rdi,%rbx
ffffffff8142b65a:	81 fa 00 01 00 00    	cmp    $0x100,%edx
ffffffff8142b660:	0f 84 3c 02 00 00    	je     ffffffff8142b8a2 <kd_q_lock_slow+0x252>
ffffffff8142b666:	81 fa ff 00 00 00    	cmp    $0xff,%edx
ffffffff8142b66c:	77 63                	ja     ffffffff8142b6d1 <kd_q_lock_slow+0x81>
ffffffff8142b66e:	f0 0f ba 2b 08       	lock btsl $0x8,(%rbx)
ffffffff8142b673:	0f 92 c0             	setb   %al
ffffffff8142b676:	8b 13                	mov    (%rbx),%edx
ffffffff8142b678:	0f b6 c0             	movzbl %al,%eax
ffffffff8142b67b:	c1 e0 08             	shl    $0x8,%eax
ffffffff8142b67e:	80 e6 fe             	and    $0xfe,%dh
ffffffff8142b681:	09 c2                	or     %eax,%edx
ffffffff8142b683:	81 fa ff 00 00 00    	cmp    $0xff,%edx
ffffffff8142b689:	77 3a                	ja     ffffffff8142b6c5 <kd_q_lock_slow+0x75>
ffffffff8142b68b:	85 d2                	test   %edx,%edx
ffffffff8142b68d:	74 10                	je     ffffffff8142b69f <kd_q_lock_slow+0x4f>
ffffffff8142b68f:	0f b6 03             	movzbl (%rbx),%eax
ffffffff8142b692:	84 c0                	test   %al,%al
ffffffff8142b694:	74 09                	je     ffffffff8142b69f <kd_q_lock_slow+0x4f>
ffffffff8142b696:	f3 90                	pause  
ffffffff8142b698:	0f b6 03             	movzbl (%rbx),%eax
ffffffff8142b69b:	84 c0                	test   %al,%al
ffffffff8142b69d:	75 f7                	jne    ffffffff8142b696 <kd_q_lock_slow+0x46>
ffffffff8142b69f:	83 e2 02             	and    $0x2,%edx
ffffffff8142b6a2:	83 ca 01             	or     $0x1,%edx
ffffffff8142b6a5:	66 89 13             	mov    %dx,(%rbx)
ffffffff8142b6a8:	b8 01 00 00 00       	mov    $0x1,%eax
ffffffff8142b6ad:	48 8b 5d f8          	mov    -0x8(%rbp),%rbx
ffffffff8142b6b1:	c9                   	leave  
ffffffff8142b6b2:	31 d2                	xor    %edx,%edx
ffffffff8142b6b4:	31 c9                	xor    %ecx,%ecx
ffffffff8142b6b6:	31 f6                	xor    %esi,%esi
ffffffff8142b6b8:	31 ff                	xor    %edi,%edi
ffffffff8142b6ba:	45 31 c0             	xor    %r8d,%r8d
ffffffff8142b6bd:	45 31 c9             	xor    %r9d,%r9d
ffffffff8142b6c0:	e9 eb c8 1e 01       	jmp    ffffffff82617fb0 <__pi___x86_return_thunk>
ffffffff8142b6c5:	f6 c6 01             	test   $0x1,%dh
ffffffff8142b6c8:	75 07                	jne    ffffffff8142b6d1 <kd_q_lock_slow+0x81>
ffffffff8142b6ca:	f0 81 23 ff fe ff ff 	lock andl $0xfffffeff,(%rbx)
ffffffff8142b6d1:	0f b6 05 4c 16 29 02 	movzbl 0x229164c(%rip),%eax        # ffffffff836bcd24 <kd_adapt>
ffffffff8142b6d8:	84 c0                	test   %al,%al
ffffffff8142b6da:	0f 84 f8 01 00 00    	je     ffffffff8142b8d8 <kd_q_lock_slow+0x288>
ffffffff8142b6e0:	84 d2                	test   %dl,%dl
ffffffff8142b6e2:	0f 85 e7 01 00 00    	jne    ffffffff8142b8cf <kd_q_lock_slow+0x27f>
ffffffff8142b6e8:	f6 c6 02             	test   $0x2,%dh
ffffffff8142b6eb:	0f 84 1b 02 00 00    	je     ffffffff8142b90c <kd_q_lock_slow+0x2bc>
ffffffff8142b6f1:	89 d0                	mov    %edx,%eax
ffffffff8142b6f3:	c1 e8 10             	shr    $0x10,%eax
ffffffff8142b6f6:	74 18                	je     ffffffff8142b710 <kd_q_lock_slow+0xc0>
ffffffff8142b6f8:	0f b6 05 11 16 29 02 	movzbl 0x2291611(%rip),%eax        # ffffffff836bcd10 <kd_spin_queue_phase>
ffffffff8142b6ff:	84 c0                	test   %al,%al
ffffffff8142b701:	0f 85 d1 01 00 00    	jne    ffffffff8142b8d8 <kd_q_lock_slow+0x288>
ffffffff8142b707:	f6 c6 01             	test   $0x1,%dh
ffffffff8142b70a:	0f 84 10 02 00 00    	je     ffffffff8142b920 <kd_q_lock_slow+0x2d0>
ffffffff8142b710:	65 48 8b 05 10 39 7a 	mov    %gs:0x27a3910(%rip),%rax        # ffffffff83bcf028 <this_cpu_off>
ffffffff8142b717:	02 
ffffffff8142b718:	65 48 ff 05 08 f2 7b 	incq   %gs:0x27bf208(%rip)        # ffffffff83bea928 <kd_cpu+0x1a8>
ffffffff8142b71f:	02 
ffffffff8142b720:	48 8d b0 80 a7 be 83 	lea    -0x7c415880(%rax),%rsi
ffffffff8142b727:	8b 86 a0 01 00 00    	mov    0x1a0(%rsi),%eax
ffffffff8142b72d:	83 f8 03             	cmp    $0x3,%eax
ffffffff8142b730:	0f 8f aa 02 00 00    	jg     ffffffff8142b9e0 <kd_q_lock_slow+0x390>
ffffffff8142b736:	8d 50 01             	lea    0x1(%rax),%edx
ffffffff8142b739:	89 96 a0 01 00 00    	mov    %edx,0x1a0(%rsi)
ffffffff8142b73f:	65 8b 3d ee 38 7a 02 	mov    %gs:0x27a38ee(%rip),%edi        # ffffffff83bcf034 <cpu_number>
ffffffff8142b746:	48 63 d0             	movslq %eax,%rdx
ffffffff8142b749:	48 8d 4a 06          	lea    0x6(%rdx),%rcx
ffffffff8142b74d:	48 c1 e2 06          	shl    $0x6,%rdx
ffffffff8142b751:	48 c1 e1 06          	shl    $0x6,%rcx
ffffffff8142b755:	8d 3c bd 04 00 00 00 	lea    0x4(,%rdi,4),%edi
ffffffff8142b75c:	48 01 f2             	add    %rsi,%rdx
ffffffff8142b75f:	09 f8                	or     %edi,%eax
ffffffff8142b761:	48 01 f1             	add    %rsi,%rcx
ffffffff8142b764:	48 c7 82 80 01 00 00 	movq   $0x0,0x180(%rdx)
ffffffff8142b76b:	00 00 00 00 
ffffffff8142b76f:	66 89 82 8c 01 00 00 	mov    %ax,0x18c(%rdx)
ffffffff8142b776:	c6 82 b0 01 00 00 00 	movb   $0x0,0x1b0(%rdx)
ffffffff8142b77d:	c7 41 08 01 00 00 00 	movl   $0x1,0x8(%rcx)
ffffffff8142b784:	8b 03                	mov    (%rbx),%eax
ffffffff8142b786:	85 c0                	test   %eax,%eax
ffffffff8142b788:	0f 84 63 01 00 00    	je     ffffffff8142b8f1 <kd_q_lock_slow+0x2a1>
ffffffff8142b78e:	0f b7 82 8c 01 00 00 	movzwl 0x18c(%rdx),%eax
ffffffff8142b795:	66 87 43 02          	xchg   %ax,0x2(%rbx)
ffffffff8142b799:	66 85 c0             	test   %ax,%ax
ffffffff8142b79c:	0f 84 db 01 00 00    	je     ffffffff8142b97d <kd_q_lock_slow+0x32d>
ffffffff8142b7a2:	41 89 c0             	mov    %eax,%r8d
ffffffff8142b7a5:	83 e0 03             	and    $0x3,%eax
ffffffff8142b7a8:	48 c7 c7 80 a7 be 83 	mov    $0xffffffff83bea780,%rdi
ffffffff8142b7af:	66 41 c1 e8 02       	shr    $0x2,%r8w
ffffffff8142b7b4:	48 83 c0 06          	add    $0x6,%rax
ffffffff8142b7b8:	45 0f b7 c0          	movzwl %r8w,%r8d
ffffffff8142b7bc:	48 c1 e0 06          	shl    $0x6,%rax
ffffffff8142b7c0:	41 83 e8 01          	sub    $0x1,%r8d
ffffffff8142b7c4:	4d 63 c0             	movslq %r8d,%r8
ffffffff8142b7c7:	4a 03 3c c5 60 7f fb 	add    -0x7d0480a0(,%r8,8),%rdi
ffffffff8142b7ce:	82 
ffffffff8142b7cf:	48 01 c7             	add    %rax,%rdi
ffffffff8142b7d2:	48 89 0f             	mov    %rcx,(%rdi)
ffffffff8142b7d5:	75 07                	jne    ffffffff8142b7de <kd_q_lock_slow+0x18e>
ffffffff8142b7d7:	e9 a1 01 00 00       	jmp    ffffffff8142b97d <kd_q_lock_slow+0x32d>
ffffffff8142b7dc:	f3 90                	pause  
ffffffff8142b7de:	8b 82 88 01 00 00    	mov    0x188(%rdx),%eax
ffffffff8142b7e4:	83 f8 01             	cmp    $0x1,%eax
ffffffff8142b7e7:	74 f3                	je     ffffffff8142b7dc <kd_q_lock_slow+0x18c>
ffffffff8142b7e9:	83 f8 06             	cmp    $0x6,%eax
ffffffff8142b7ec:	48 8b 82 80 01 00 00 	mov    0x180(%rdx),%rax
ffffffff8142b7f3:	0f 84 06 02 00 00    	je     ffffffff8142b9ff <kd_q_lock_slow+0x3af>
ffffffff8142b7f9:	48 85 c0             	test   %rax,%rax
ffffffff8142b7fc:	74 03                	je     ffffffff8142b801 <kd_q_lock_slow+0x1b1>
ffffffff8142b7fe:	0f 18 08             	prefetcht0 (%rax)
ffffffff8142b801:	0f b6 05 1c 15 29 02 	movzbl 0x229151c(%rip),%eax        # ffffffff836bcd24 <kd_adapt>
ffffffff8142b808:	84 c0                	test   %al,%al
ffffffff8142b80a:	0f 84 78 01 00 00    	je     ffffffff8142b988 <kd_q_lock_slow+0x338>
ffffffff8142b810:	e9 73 01 00 00       	jmp    ffffffff8142b988 <kd_q_lock_slow+0x338>
ffffffff8142b815:	8b 46 68             	mov    0x68(%rsi),%eax
ffffffff8142b818:	8d 78 01             	lea    0x1(%rax),%edi
ffffffff8142b81b:	89 7e 68             	mov    %edi,0x68(%rsi)
ffffffff8142b81e:	a8 7f                	test   $0x7f,%al
ffffffff8142b820:	0f 85 62 01 00 00    	jne    ffffffff8142b988 <kd_q_lock_slow+0x338>
ffffffff8142b826:	44 8b 05 f3 14 29 02 	mov    0x22914f3(%rip),%r8d        # ffffffff836bcd20 <kd_deleg_enter>
ffffffff8142b82d:	48 89 c8             	mov    %rcx,%rax
ffffffff8142b830:	31 ff                	xor    %edi,%edi
ffffffff8142b832:	45 85 c0             	test   %r8d,%r8d
ffffffff8142b835:	7f 0a                	jg     ffffffff8142b841 <kd_q_lock_slow+0x1f1>
ffffffff8142b837:	eb 19                	jmp    ffffffff8142b852 <kd_q_lock_slow+0x202>
ffffffff8142b839:	83 c7 01             	add    $0x1,%edi
ffffffff8142b83c:	41 39 f8             	cmp    %edi,%r8d
ffffffff8142b83f:	74 11                	je     ffffffff8142b852 <kd_q_lock_slow+0x202>
ffffffff8142b841:	48 8b 00             	mov    (%rax),%rax
ffffffff8142b844:	48 85 c0             	test   %rax,%rax
ffffffff8142b847:	75 f0                	jne    ffffffff8142b839 <kd_q_lock_slow+0x1e9>
ffffffff8142b849:	41 39 f8             	cmp    %edi,%r8d
ffffffff8142b84c:	0f 8f 36 01 00 00    	jg     ffffffff8142b988 <kd_q_lock_slow+0x338>
ffffffff8142b852:	48 83 86 18 04 00 00 	addq   $0x1,0x418(%rsi)
ffffffff8142b859:	01 
ffffffff8142b85a:	0f b6 05 c3 14 29 02 	movzbl 0x22914c3(%rip),%eax        # ffffffff836bcd24 <kd_adapt>
ffffffff8142b861:	84 c0                	test   %al,%al
ffffffff8142b863:	0f 84 56 01 00 00    	je     ffffffff8142b9bf <kd_q_lock_slow+0x36f>
ffffffff8142b869:	8b 3d a9 14 29 02    	mov    0x22914a9(%rip),%edi        # ffffffff836bcd18 <kd_deleg_exit>
ffffffff8142b86f:	31 c0                	xor    %eax,%eax
ffffffff8142b871:	85 ff                	test   %edi,%edi
ffffffff8142b873:	7f 10                	jg     ffffffff8142b885 <kd_q_lock_slow+0x235>
ffffffff8142b875:	e9 45 01 00 00       	jmp    ffffffff8142b9bf <kd_q_lock_slow+0x36f>
ffffffff8142b87a:	83 c0 01             	add    $0x1,%eax
ffffffff8142b87d:	39 c7                	cmp    %eax,%edi
ffffffff8142b87f:	0f 84 3a 01 00 00    	je     ffffffff8142b9bf <kd_q_lock_slow+0x36f>
ffffffff8142b885:	48 8b 09             	mov    (%rcx),%rcx
ffffffff8142b888:	48 85 c9             	test   %rcx,%rcx
ffffffff8142b88b:	75 ed                	jne    ffffffff8142b87a <kd_q_lock_slow+0x22a>
ffffffff8142b88d:	39 c7                	cmp    %eax,%edi
ffffffff8142b88f:	0f 8e 2a 01 00 00    	jle    ffffffff8142b9bf <kd_q_lock_slow+0x36f>
ffffffff8142b895:	48 83 86 20 04 00 00 	addq   $0x1,0x420(%rsi)
ffffffff8142b89c:	01 
ffffffff8142b89d:	e9 e6 00 00 00       	jmp    ffffffff8142b988 <kd_q_lock_slow+0x338>
ffffffff8142b8a2:	8b 0f                	mov    (%rdi),%ecx
ffffffff8142b8a4:	b8 00 02 00 00       	mov    $0x200,%eax
ffffffff8142b8a9:	81 f9 00 01 00 00    	cmp    $0x100,%ecx
ffffffff8142b8af:	74 0b                	je     ffffffff8142b8bc <kd_q_lock_slow+0x26c>
ffffffff8142b8b1:	eb 15                	jmp    ffffffff8142b8c8 <kd_q_lock_slow+0x278>
ffffffff8142b8b3:	83 e8 01             	sub    $0x1,%eax
ffffffff8142b8b6:	0f 84 10 01 00 00    	je     ffffffff8142b9cc <kd_q_lock_slow+0x37c>
ffffffff8142b8bc:	f3 90                	pause  
ffffffff8142b8be:	8b 0b                	mov    (%rbx),%ecx
ffffffff8142b8c0:	81 f9 00 01 00 00    	cmp    $0x100,%ecx
ffffffff8142b8c6:	74 eb                	je     ffffffff8142b8b3 <kd_q_lock_slow+0x263>
ffffffff8142b8c8:	89 ca                	mov    %ecx,%edx
ffffffff8142b8ca:	e9 97 fd ff ff       	jmp    ffffffff8142b666 <kd_q_lock_slow+0x16>
ffffffff8142b8cf:	83 e2 02             	and    $0x2,%edx
ffffffff8142b8d2:	0f 84 38 fe ff ff    	je     ffffffff8142b710 <kd_q_lock_slow+0xc0>
ffffffff8142b8d8:	48 89 f7             	mov    %rsi,%rdi
ffffffff8142b8db:	e8 00 df ff ff       	call   ffffffff814297e0 <kd_can_offer>
ffffffff8142b8e0:	89 c2                	mov    %eax,%edx
ffffffff8142b8e2:	31 c0                	xor    %eax,%eax
ffffffff8142b8e4:	84 d2                	test   %dl,%dl
ffffffff8142b8e6:	0f 84 24 fe ff ff    	je     ffffffff8142b710 <kd_q_lock_slow+0xc0>
ffffffff8142b8ec:	e9 bc fd ff ff       	jmp    ffffffff8142b6ad <kd_q_lock_slow+0x5d>
ffffffff8142b8f1:	bf 01 00 00 00       	mov    $0x1,%edi
ffffffff8142b8f6:	f0 0f b1 3b          	lock cmpxchg %edi,(%rbx)
ffffffff8142b8fa:	0f 85 8e fe ff ff    	jne    ffffffff8142b78e <kd_q_lock_slow+0x13e>
ffffffff8142b900:	83 ae a0 01 00 00 01 	subl   $0x1,0x1a0(%rsi)
ffffffff8142b907:	e9 9c fd ff ff       	jmp    ffffffff8142b6a8 <kd_q_lock_slow+0x58>
ffffffff8142b90c:	f6 c6 01             	test   $0x1,%dh
ffffffff8142b90f:	0f 85 fb fd ff ff    	jne    ffffffff8142b710 <kd_q_lock_slow+0xc0>
ffffffff8142b915:	89 d0                	mov    %edx,%eax
ffffffff8142b917:	c1 e8 10             	shr    $0x10,%eax
ffffffff8142b91a:	0f 84 f0 fd ff ff    	je     ffffffff8142b710 <kd_q_lock_slow+0xc0>
ffffffff8142b920:	e9 eb fd ff ff       	jmp    ffffffff8142b710 <kd_q_lock_slow+0xc0>
ffffffff8142b925:	8b 05 e9 13 29 02    	mov    0x22913e9(%rip),%eax        # ffffffff836bcd14 <kd_spin_phase_wait>
ffffffff8142b92b:	b9 80 00 00 00       	mov    $0x80,%ecx
ffffffff8142b930:	39 c8                	cmp    %ecx,%eax
ffffffff8142b932:	0f 47 c1             	cmova  %ecx,%eax
ffffffff8142b935:	eb 13                	jmp    ffffffff8142b94a <kd_q_lock_slow+0x2fa>
ffffffff8142b937:	f3 90                	pause  
ffffffff8142b939:	8b 13                	mov    (%rbx),%edx
ffffffff8142b93b:	f7 c2 ff 01 00 00    	test   $0x1ff,%edx
ffffffff8142b941:	75 0c                	jne    ffffffff8142b94f <kd_q_lock_slow+0x2ff>
ffffffff8142b943:	89 d7                	mov    %edx,%edi
ffffffff8142b945:	c1 ef 10             	shr    $0x10,%edi
ffffffff8142b948:	74 05                	je     ffffffff8142b94f <kd_q_lock_slow+0x2ff>
ffffffff8142b94a:	83 e8 01             	sub    $0x1,%eax
ffffffff8142b94d:	73 e8                	jae    ffffffff8142b937 <kd_q_lock_slow+0x2e7>
ffffffff8142b94f:	84 d2                	test   %dl,%dl
ffffffff8142b951:	0f 85 78 ff ff ff    	jne    ffffffff8142b8cf <kd_q_lock_slow+0x27f>
ffffffff8142b957:	f6 c6 02             	test   $0x2,%dh
ffffffff8142b95a:	0f 84 b0 fd ff ff    	je     ffffffff8142b710 <kd_q_lock_slow+0xc0>
ffffffff8142b960:	c1 ea 10             	shr    $0x10,%edx
ffffffff8142b963:	0f 84 a7 fd ff ff    	je     ffffffff8142b710 <kd_q_lock_slow+0xc0>
ffffffff8142b969:	0f b6 05 a0 13 29 02 	movzbl 0x22913a0(%rip),%eax        # ffffffff836bcd10 <kd_spin_queue_phase>
ffffffff8142b970:	84 c0                	test   %al,%al
ffffffff8142b972:	0f 85 60 ff ff ff    	jne    ffffffff8142b8d8 <kd_q_lock_slow+0x288>
ffffffff8142b978:	e9 93 fd ff ff       	jmp    ffffffff8142b710 <kd_q_lock_slow+0xc0>
ffffffff8142b97d:	0f b6 03             	movzbl (%rbx),%eax
ffffffff8142b980:	a8 02                	test   $0x2,%al
ffffffff8142b982:	0f 85 d2 fe ff ff    	jne    ffffffff8142b85a <kd_q_lock_slow+0x20a>
ffffffff8142b988:	b9 01 00 00 00       	mov    $0x1,%ecx
ffffffff8142b98d:	41 b9 01 00 00 00    	mov    $0x1,%r9d
ffffffff8142b993:	eb 02                	jmp    ffffffff8142b997 <kd_q_lock_slow+0x347>
ffffffff8142b995:	f3 90                	pause  
ffffffff8142b997:	8b 03                	mov    (%rbx),%eax
ffffffff8142b999:	a9 ff 01 00 00       	test   $0x1ff,%eax
ffffffff8142b99e:	75 f5                	jne    ffffffff8142b995 <kd_q_lock_slow+0x345>
ffffffff8142b9a0:	41 89 c0             	mov    %eax,%r8d
ffffffff8142b9a3:	0f b7 ba 8c 01 00 00 	movzwl 0x18c(%rdx),%edi
ffffffff8142b9aa:	41 c1 e8 10          	shr    $0x10,%r8d
ffffffff8142b9ae:	41 39 f8             	cmp    %edi,%r8d
ffffffff8142b9b1:	75 5d                	jne    ffffffff8142ba10 <kd_q_lock_slow+0x3c0>
ffffffff8142b9b3:	f0 0f b1 0b          	lock cmpxchg %ecx,(%rbx)
ffffffff8142b9b7:	0f 84 43 ff ff ff    	je     ffffffff8142b900 <kd_q_lock_slow+0x2b0>
ffffffff8142b9bd:	eb d8                	jmp    ffffffff8142b997 <kd_q_lock_slow+0x347>
ffffffff8142b9bf:	b9 03 00 00 00       	mov    $0x3,%ecx
ffffffff8142b9c4:	41 b9 03 00 00 00    	mov    $0x3,%r9d
ffffffff8142b9ca:	eb cb                	jmp    ffffffff8142b997 <kd_q_lock_slow+0x347>
ffffffff8142b9cc:	0f b6 05 51 13 29 02 	movzbl 0x2291351(%rip),%eax        # ffffffff836bcd24 <kd_adapt>
ffffffff8142b9d3:	84 c0                	test   %al,%al
ffffffff8142b9d5:	0f 85 0d fd ff ff    	jne    ffffffff8142b6e8 <kd_q_lock_slow+0x98>
ffffffff8142b9db:	e9 f8 fe ff ff       	jmp    ffffffff8142b8d8 <kd_q_lock_slow+0x288>
ffffffff8142b9e0:	8b 03                	mov    (%rbx),%eax
ffffffff8142b9e2:	ba 01 00 00 00       	mov    $0x1,%edx
ffffffff8142b9e7:	85 c0                	test   %eax,%eax
ffffffff8142b9e9:	74 08                	je     ffffffff8142b9f3 <kd_q_lock_slow+0x3a3>
ffffffff8142b9eb:	f3 90                	pause  
ffffffff8142b9ed:	8b 03                	mov    (%rbx),%eax
ffffffff8142b9ef:	85 c0                	test   %eax,%eax
ffffffff8142b9f1:	75 f8                	jne    ffffffff8142b9eb <kd_q_lock_slow+0x39b>
ffffffff8142b9f3:	f0 0f b1 13          	lock cmpxchg %edx,(%rbx)
ffffffff8142b9f7:	0f 84 ab fc ff ff    	je     ffffffff8142b6a8 <kd_q_lock_slow+0x58>
ffffffff8142b9fd:	eb ec                	jmp    ffffffff8142b9eb <kd_q_lock_slow+0x39b>
ffffffff8142b9ff:	48 85 c0             	test   %rax,%rax
ffffffff8142ba02:	0f 84 52 fe ff ff    	je     ffffffff8142b85a <kd_q_lock_slow+0x20a>
ffffffff8142ba08:	0f 18 08             	prefetcht0 (%rax)
ffffffff8142ba0b:	e9 4a fe ff ff       	jmp    ffffffff8142b85a <kd_q_lock_slow+0x20a>
ffffffff8142ba10:	44 88 0b             	mov    %r9b,(%rbx)
ffffffff8142ba13:	25 00 02 00 00       	and    $0x200,%eax
ffffffff8142ba18:	41 83 e1 02          	and    $0x2,%r9d
ffffffff8142ba1c:	75 5b                	jne    ffffffff8142ba79 <kd_q_lock_slow+0x429>
ffffffff8142ba1e:	85 c0                	test   %eax,%eax
ffffffff8142ba20:	74 20                	je     ffffffff8142ba42 <kd_q_lock_slow+0x3f2>
ffffffff8142ba22:	f0 81 23 ff fd ff ff 	lock andl $0xfffffdff,(%rbx)
ffffffff8142ba29:	48 8b 82 80 01 00 00 	mov    0x180(%rdx),%rax
ffffffff8142ba30:	48 85 c0             	test   %rax,%rax
ffffffff8142ba33:	74 27                	je     ffffffff8142ba5c <kd_q_lock_slow+0x40c>
ffffffff8142ba35:	ba 03 00 00 00       	mov    $0x3,%edx
ffffffff8142ba3a:	89 50 08             	mov    %edx,0x8(%rax)
ffffffff8142ba3d:	e9 be fe ff ff       	jmp    ffffffff8142b900 <kd_q_lock_slow+0x2b0>
ffffffff8142ba42:	48 8b 82 80 01 00 00 	mov    0x180(%rdx),%rax
ffffffff8142ba49:	48 85 c0             	test   %rax,%rax
ffffffff8142ba4c:	75 e7                	jne    ffffffff8142ba35 <kd_q_lock_slow+0x3e5>
ffffffff8142ba4e:	48 8b 82 80 01 00 00 	mov    0x180(%rdx),%rax
ffffffff8142ba55:	48 85 c0             	test   %rax,%rax
ffffffff8142ba58:	75 db                	jne    ffffffff8142ba35 <kd_q_lock_slow+0x3e5>
ffffffff8142ba5a:	f3 90                	pause  
ffffffff8142ba5c:	48 8b 82 80 01 00 00 	mov    0x180(%rdx),%rax
ffffffff8142ba63:	48 85 c0             	test   %rax,%rax
ffffffff8142ba66:	74 f2                	je     ffffffff8142ba5a <kd_q_lock_slow+0x40a>
ffffffff8142ba68:	ba 03 00 00 00       	mov    $0x3,%edx
ffffffff8142ba6d:	45 84 c9             	test   %r9b,%r9b
ffffffff8142ba70:	74 c8                	je     ffffffff8142ba3a <kd_q_lock_slow+0x3ea>
ffffffff8142ba72:	ba 06 00 00 00       	mov    $0x6,%edx
ffffffff8142ba77:	eb c1                	jmp    ffffffff8142ba3a <kd_q_lock_slow+0x3ea>
ffffffff8142ba79:	0f b6 0d 90 12 29 02 	movzbl 0x2291290(%rip),%ecx        # ffffffff836bcd10 <kd_spin_queue_phase>
ffffffff8142ba80:	84 c9                	test   %cl,%cl
ffffffff8142ba82:	75 19                	jne    ffffffff8142ba9d <kd_q_lock_slow+0x44d>
ffffffff8142ba84:	85 c0                	test   %eax,%eax
ffffffff8142ba86:	74 07                	je     ffffffff8142ba8f <kd_q_lock_slow+0x43f>
ffffffff8142ba88:	f0 81 23 ff fd ff ff 	lock andl $0xfffffdff,(%rbx)
ffffffff8142ba8f:	48 8b 82 80 01 00 00 	mov    0x180(%rdx),%rax
ffffffff8142ba96:	48 85 c0             	test   %rax,%rax
ffffffff8142ba99:	74 c1                	je     ffffffff8142ba5c <kd_q_lock_slow+0x40c>
ffffffff8142ba9b:	eb d5                	jmp    ffffffff8142ba72 <kd_q_lock_slow+0x422>
ffffffff8142ba9d:	85 c0                	test   %eax,%eax
ffffffff8142ba9f:	75 ee                	jne    ffffffff8142ba8f <kd_q_lock_slow+0x43f>
ffffffff8142baa1:	f0 81 0b 00 02 00 00 	lock orl $0x200,(%rbx)
ffffffff8142baa8:	48 8b 82 80 01 00 00 	mov    0x180(%rdx),%rax
ffffffff8142baaf:	48 85 c0             	test   %rax,%rax
ffffffff8142bab2:	74 a8                	je     ffffffff8142ba5c <kd_q_lock_slow+0x40c>
ffffffff8142bab4:	eb bc                	jmp    ffffffff8142ba72 <kd_q_lock_slow+0x422>

Disassembly of section .data:

Disassembly of section .init.text:

Disassembly of section .altinstr_aux:

Disassembly of section .altinstr_replacement:

Disassembly of section .exit.text:
