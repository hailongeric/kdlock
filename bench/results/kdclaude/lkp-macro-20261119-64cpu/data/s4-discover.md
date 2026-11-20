| candidate | lock users asking for delegation (requests) |
|---|---|
| dbench-btrfs | btrfs_block_rsv_release 366, reserve_bytes 313, btrfs_tree_lock_nested 132, btrfs_add_reserved_bytes 3 |
| dbench-ext4 | jbd2_journal_next_log_block 66, __jbd2_log_wait_for_space 34, jbd2_journal_dirty_metadata 33, jbd2_journal_commit_transaction 31 |
| filebench-fileserver | futex_q_lock 911, futex_wake 646, path_openat 8, filename_unlinkat 5 |
| filebench-varmail | futex_q_lock 1041, futex_wake 776, filename_unlinkat 21, path_openat 20 |
| filebench-webproxy | futex_q_lock 1085, futex_wake 819, filename_unlinkat 8, path_openat 7 |
| filebench-webserver | futex_q_lock 1039, futex_wake 898, shmem_file_write_iter 8 |
| fio-randwrite-shared | shmem_file_write_iter 955, unlink_file_vma_batch_add 1, unlink_anon_vmas 1, __shm_close 1 |
| fsmark-btrfs-fsync | btrfs_tree_lock_nested 561, wait_log_commit 82, btrfs_get_free_objectid 19, filename_create 17 |
| fsmark-btrfs-nosync | btrfs_tree_lock_nested 236, btrfs_block_rsv_release 20, reserve_bytes 9, filename_create 2 |
| fsmark-ext4-fsync | __jbd2_log_wait_for_space 119, jbd2_journal_dirty_metadata 56, jbd2_journal_next_log_block 52, add_transaction_credits 47 |
| fsmark-xfs-fsync | __flush_workqueue 91, xlog_cil_push_work 10, filename_create 7, xlog_cil_force_seq 1 |
| fsmark | filename_create 24 |
| hb-pipe-process | anon_pipe_write 3, anon_pipe_read 2 |
| pbe-ctl | do_epoll_ctl 1318 |
| pbe-wait | ep_send_events 606, eventfd_read 22 |
| sng-affinity | cpuset_cpus_allowed 3786, anon_vma_clone 1, anon_vma_fork 1, dup_mmap 1 |
| sng-chattr | shmem_fallocate 2879, filename_unlinkat 427, path_openat 275, shmem_file_write_iter 144 |
| sng-chmod | chmod_common 1356 |
| sng-chown | chown_common 1394 |
| sng-clock | add_device_randomness 361, dput.part.0 3, __dentry_kill 2, d_alloc_parallel 1 |
| sng-clone | __register_sysctl_table 22, pcpu_alloc_noprof 16, anon_vma_fork 8, rtnl_lock_killable 4 |
| sng-copy-file | folio_lruvec_lock_irqsave 7 |
| sng-cpu-sched | cpuset_cpus_allowed 1178, anon_vma_clone 2, anon_vma_fork 2, proc_sched_autogroup_set_nice 1 |
| sng-dentry | __iterate_supers 2, proc_sys_permission 2, unlink_file_vma_batch_final 1, unlink_file_vma_batch_add 1 |
| sng-dev-shm | dquot_add_space 2212, folio_lruvec_lock_irqsave 28, __rmqueue_pcplist 1, get_page_from_freelist 1 |
| sng-dir | d_move 339, filename_rmdir 4, d_walk 3, dput.part.0 1 |
| sng-dirdeep | __iterate_supers 2831, __flush_workqueue 17, sync_inodes_sb 4, sync_bdevs 3 |
| sng-dirmany | evict 643, inode_sb_list_add 368 |
| sng-dnotify | fcntl_dirnotify 488, dnotify_flush 487, fsnotify_put_mark 1 |
| sng-dynlib | vma_prepare 1544, unlink_file_vma_batch_final 1499, vma_link_file 1096, folio_wake_bit 17 |
| sng-env | folio_lruvec_lock_irqsave 107, folio_lruvec_lock_irq 1, free_pcppages_bulk 1 |
| sng-epoll | do_epoll_ctl 701, filename_unlinkat 1 |
| sng-epollmany | do_epoll_ctl 109, lock_for_kill 9 |
| sng-exit-group | do_exit 134, release_task 119, copy_process 112, unlink_anon_vmas 41 |
| sng-fault | evict 80, inode_sb_list_add 53 |
| sng-fcntl | posix_lock_inode 1106, posix_test_lock 248, do_truncate 21, filename_rmdir 1 |
| sng-fd-abuse | evict 1147, inode_sb_list_add 1143, shmem_file_llseek 13, shmem_file_write_iter 7 |
| sng-file-ioctl | folio_lruvec_lock_irqsave 881 |
| sng-filehole | folio_lruvec_lock_irqsave 13, __vm_munmap 1 |
| sng-filename | inode_sb_list_add 1020, evict 1012, __put_anon_vma 1 |
| sng-filerace | inode_sb_list_add 634, evict 625, filename_rmdir 277, path_openat 231 |
| sng-flock | percpu_rwsem_wait 60, flock_lock_inode 19, locks_unlink_lock_ctx 16, locks_move_blocks 5 |
| sng-forkheavy | ipcget 137, proc_sys_permission 73, start_creating_noperm 52, start_removing_noperm 36 |
| sng-fpunch | shmem_fallocate 2583, shmem_file_write_iter 2423, do_truncate 142, folio_lruvec_lock_irqsave 57 |
| sng-fsize | folio_lruvec_lock_irqsave 106 |
| sng-fstat | dput.part.0 1929, lockref_get_not_dead 1924 |
| sng-full | chrdev_open 2806 |
| sng-getdent | fget_task_next 2, find_positive_dentry 2, get_proc_task_net 1, d_alloc_parallel 1 |
| sng-handle | dput.part.0 1850, lockref_get_not_dead 1163, lockref_get 411, ilookup5 327 |
| sng-io-uring | none |
| sng-io | __iterate_supers 2924, __flush_workqueue 62, sync_inodes_sb 7, prepare_to_wait_event 3 |
| sng-ioprio | __do_sys_ioprio_get 84, set_task_ioprio 14, folio_lruvec_lock_irqsave 2, filename_create 1 |
| sng-landlock | dput.part.0 541, lockref_get_not_dead 447, anon_vma_fork 276, anon_vma_clone 200 |
| sng-link | filename_create 51 |
| sng-membarrier | membarrier_private_expedited 81, __do_sys_membarrier 32, sync_runqueues_membarrier_state 1 |
| sng-memfd | inode_sb_list_add 1127, evict 1027, locked_inode_to_wb_and_lock_list 1 |
| sng-mknod | __iterate_supers 3081, sync_inodes_sb 23, __flush_workqueue 8, find_positive_dentry 5 |
| sng-mlock | folio_lruvec_lock_irq 3068, folio_lruvec_lock_irqsave 389, evict 49, inode_sb_list_add 10 |
| sng-mmap | __slab_free 12, __refill_objects_node 5, alloc_from_new_slab 1 |
| sng-mmapcow | lru_gen_rotate_memcg 527, folio_lruvec_lock_irqsave 50, __remove_mapping 24, __filemap_add_folio 8 |
| sng-mmapfork | dup_mmap 15, anon_vma_fork 14, unlink_anon_vmas 14, anon_vma_clone 12 |
| sng-mmapmany | folio_lruvec_lock_irqsave 774, lru_gen_rotate_memcg 239, folio_lruvec_lock_irq 144, __remove_mapping 9 |
| sng-mremap | cgroup_file_notify 2981, folio_alloc_swap 1 |
| sng-msg | msgctl_down 37, __slab_free 37, __refill_objects_node 15, alloc_from_new_slab 11 |
| sng-msync | folio_lruvec_lock_irq 2063, __slab_free 20, free_pcppages_bulk 1 |
| sng-munmap | unlink_file_vma_batch_final 382, vma_prepare 372, dup_mmap 15, unlink_file_vma_batch_add 4 |
| sng-netlink-task | genl_rcv_msg 1101 |
| sng-open | inode_sb_list_add 1503, evict 452, vfs_utimes 32, dput.part.0 9 |
| sng-physpage | memory_lseek 1068 |
| sng-pidfd | anon_vma_fork 999, anon_vma_clone 928, unlink_anon_vmas 868, dup_mmap 361 |
| sng-procfs | proc_sys_permission 1517, proc_sys_call_handler 902, proc_sys_open 374, proc_sys_compare 281 |
| sng-ptrace | cgroup_leave_frozen 1566, cgroup_enter_frozen 1558 |
| sng-pty | ptmx_open 67, tty_open 56, tty_release_struct 53, pty_close 18 |
| sng-ramfs | free_percpu 45, pcpu_alloc_noprof 36, do_lock_mount.part.0 19, path_umount 18 |
| sng-rawpkt | __slab_free 1487, __refill_objects_node 115, packet_rcv 2, __skb_try_recv_datagram 2 |
| sng-rawsock | __slab_free 996, __skb_try_recv_datagram 1 |
| sng-rawudp | __slab_free 583, ip_ra_control 105, raw_hash_sk 45, raw_unhash_sk 32 |
| sng-rename | __start_renaming 361, __put_anon_vma 1 |
| sng-rlimit | chrdev_open 2683, expand_downwards 8, anon_vma_fork 1 |
| sng-schedpolicy | cpuset_lock 591 |
| sng-seal | inode_sb_list_add 1133, evict 1118, __vm_munmap 1, folio_lruvec_lock_irqsave 1 |
| sng-seccomp | anon_vma_fork 168, pcpu_alloc_noprof 121, bpf_prog_pack_free 117, bpf_prog_pack_alloc 100 |
| sng-secretmem | __change_page_attr_set_clr 621, __slab_free 2, __refill_objects_node 2 |
| sng-session | anon_vma_fork 449, anon_vma_clone 399, unlink_anon_vmas 384, dup_mmap 231 |
| sng-shm-sysv | ipcget 137, shmctl_down 57, do_shmat 56, __shm_close 53 |
| sng-shm | dquot_add_space 3010, __dquot_free_space 16, unlink_anon_vmas 7, folio_lruvec_lock_irqsave 7 |
| sng-sigchld | anon_vma_fork 1095, anon_vma_clone 1041, unlink_anon_vmas 976, dup_mmap 368 |
| sng-sigstop | cgroup_leave_frozen 1556, cgroup_enter_frozen 1553 |
| sng-sleep | do_exit 2, release_task 2, copy_process 1, evict 1 |
| sng-sockdiag | unix_diag_dump 322, netlink_release 162, netlink_table_grab.part.0 8, remove_wait_queue 1 |
| sng-sockfd | unix_del_edges 1408, unix_add_edges 1393, anon_vma_fork 1, chrdev_open 1 |
| sng-sockmany | established_get_first 1 |
| sng-sysinfo | drop_super 322, user_get_super 321, dput.part.0 10, __d_lookup 7 |
| sng-touch | filename_unlinkat 6, path_openat 4, __iterate_supers 3, dup_mmap 1 |
| sng-udp | vma_link_file 1 |
| sng-umask | none |
| sng-unlink | inode_sb_list_add 621, evict 601, filename_unlinkat 93, path_openat 45 |
| sng-vfork | copy_process 246, do_exit 246, release_task 240, cgroup_leave_frozen 3 |
| sng-vforkmany | do_exit 238, copy_process 227, release_task 224, alloc_vmap_area 11 |
| sng-wait | cgroup_leave_frozen 1477, cgroup_enter_frozen 1462 |
| sng-xattr | __slab_free 2 |
| sng-zombie | __do_sys_setpgid 1222 |
| sysbench-threads | futex_q_lock 1825, futex_wake 1269, futex_unqueue 1 |
| ub-execl | vma_prepare 1582, vma_link_file 1208, unlink_file_vma_batch_final 1089, unlink_file_vma_batch_add 185 |
| vms-lru-file-mmap-read-rand | __list_lru_walk_one 1064, evict_folios 557, folio_lruvec_lock_irqsave 455, __remove_mapping 66 |
| vms-lru-file-mmap-read | compact_zone 120, get_page_from_freelist 72, evict_folios 36, free_one_page 32 |
| vms-mmap-pread-rand-mt | __remove_mapping 19975, __filemap_add_folio 2613, __folio_migrate_mapping 4, vm_mmap_pgoff 1 |
| vms-mmap-xread-rand-mt | __remove_mapping 17581, __filemap_add_folio 1676, try_to_inc_max_seq 1 |
| vms-mremap-xread-rand-mt | __remove_mapping 17578, __filemap_add_folio 1835 |
| vms-small-allocs | vma_link_file 641, unlink_file_vma_batch_add 76 |
| wis-brk1 | __do_sys_brk 2222 |
| wis-brk2 | __do_sys_brk 2117 |
| wis-dup1 | file_close_fd 3550, alloc_fd 3548, fd_install_slowpath 24, path_openat 1 |
| wis-fallocate1 | dquot_add_space 6980, __dquot_free_space 26 |
| wis-fallocate2 | dquot_add_space 6864, __dquot_free_space 25 |
| wis-lock1 | fcntl_setlk 7550 |
| wis-lock2 | posix_lock_inode 7639, fcntl_setlk 1, taskstats_exit 1, release_task 1 |
| wis-lseek2 | none |
| wis-mmap1 | vm_mmap_pgoff 731, __vm_munmap 728, do_exit 1, release_task 1 |
| wis-mmap2 | vm_mmap_pgoff 934, __vm_munmap 933 |
| wis-open1 | alloc_fd 3591, file_close_fd 3590 |
| wis-open2 | alloc_fd 3515, file_close_fd 3506 |
| wis-open3 | alloc_fd 3564, file_close_fd 3547, unlink_file_vma_batch_final 1, acct_collect 1 |
| wis-page_fault1 | vma_prepare 1, __vm_munmap 1 |
| wis-pread2 | folio_wake_bit 2410, folio_wait_bit_common 2022, finish_wait 1, do_exit 1 |
| wis-pthread_mutex1 | futex_wake 3315, futex_q_lock 2113, futex_unqueue 1 |
| wis-pthread_mutex3 | futex_wake 3549, futex_q_lock 2203 |
| wis-pthread_mutex4 | futex_wake 3423, futex_q_lock 2153 |
| wis-pthread_mutex5 | futex_wake 3519, futex_q_lock 2195 |
| wis-pwrite2 | shmem_file_write_iter 1696, do_exit 1, release_task 1 |
| wis-pwrite3 | shmem_file_write_iter 3184 |
| wis-readseek2 | folio_wake_bit 2437, folio_wait_bit_common 1967, finish_wait 1 |
| wis-sched_yield | none |
| wis-signal1 | set_current_blocked 1709, get_signal 1704, signal_setup_done 1703, do_send_sig_info 1698 |
| wis-unlink1 | path_openat 509, filename_unlinkat 507 |
| wis-unlink2 | dquot_free_inode 1540, dquot_add_inodes 1371, dqget 442, dqput.part.0 322 |
| wis-writeseek2 | shmem_file_write_iter 1787 |
| wis-writeseek3 | shmem_file_write_iter 3720 |
| wisp-brk1 | __refill_objects_node 4, __slab_free 3 |
| wisp-brk2 | __refill_objects_node 4, __slab_free 3 |
| wisp-fallocate1 | dquot_add_space 7073, __dquot_free_space 26, unlink_file_vma_batch_final 1 |
| wisp-fallocate2 | dquot_add_space 7124, __dquot_free_space 26 |
| wisp-futex1 | none |
| wisp-lock2 | posix_lock_inode 1, unlink_anon_vmas 1 |
| wisp-mmap1 | __slab_free 13 |
| wisp-mmap2 | __slab_free 21, folio_wake_bit 1 |
| wisp-page_fault1 | __rmqueue_pcplist 1, free_pcppages_bulk 1 |
| wisp-pread2 | folio_wake_bit 2407, folio_wait_bit_common 2034 |
| wisp-pwrite2 | shmem_file_write_iter 1643, unlink_file_vma_batch_add 1 |
| wisp-pwrite3 | shmem_file_write_iter 3188, unlink_anon_vmas 1 |
| wisp-readseek2 | folio_wake_bit 2355, folio_wait_bit_common 1909 |
| wisp-tlb_flush2 | folio_lruvec_lock_irqsave 18 |
| wisp-unlink1 | filename_unlinkat 487, path_openat 486, evict 1, __slab_free 1 |
| wisp-unlink2 | dquot_free_inode 1763, dquot_add_inodes 1495, dqget 165, dqput.part.0 110 |
| wisp-writeseek2 | shmem_file_write_iter 1732 |
| wisp-writeseek3 | shmem_file_write_iter 3484 |

| lock user | candidates | requests | which |
|---|---|---|---|
| __remove_mapping | 8 | 55236 | vms-mmap-pread-rand-mt, vms-mmap-xread-rand-mt, vms-mremap-xread-rand-mt, vms-lru-file-mmap-read-rand, sng-mmapcow, sng-mmapmany ... |
| dquot_add_space | 6 | 33263 | wisp-fallocate2, wisp-fallocate1, wis-fallocate1, wis-fallocate2, sng-shm, sng-dev-shm |
| shmem_file_write_iter | 14 | 24009 | wis-writeseek3, wisp-writeseek3, wisp-pwrite3, wis-pwrite3, sng-fpunch, wis-writeseek2 ... |
| futex_wake | 9 | 18214 | wis-pthread_mutex3, wis-pthread_mutex5, wis-pthread_mutex4, wis-pthread_mutex1, sysbench-threads, filebench-webserver ... |
| futex_q_lock | 9 | 14565 | wis-pthread_mutex3, wis-pthread_mutex5, wis-pthread_mutex4, wis-pthread_mutex1, sysbench-threads, filebench-webproxy ... |
| alloc_fd | 5 | 14265 | wis-open1, wis-open3, wis-dup1, wis-open2, wis-unlink2 |
| file_close_fd | 5 | 14243 | wis-open1, wis-dup1, wis-open3, wis-open2, wis-unlink2 |
| folio_wake_bit | 7 | 9628 | wis-readseek2, wis-pread2, wisp-pread2, wisp-readseek2, sng-dynlib, wisp-mmap2 ... |
| __iterate_supers | 6 | 8842 | sng-mknod, sng-io, sng-dirdeep, sng-touch, sng-dentry, sng-open |
| posix_lock_inode | 3 | 8746 | wis-lock2, sng-fcntl, wisp-lock2 |
| folio_wait_bit_common | 5 | 7940 | wisp-pread2, wis-pread2, wis-readseek2, wisp-readseek2, sng-dynlib |
| inode_sb_list_add | 13 | 7661 | sng-open, sng-fd-abuse, sng-seal, sng-memfd, sng-filename, sng-filerace ... |
| fcntl_setlk | 2 | 7551 | wis-lock1, wis-lock2 |
| evict | 14 | 6806 | sng-fd-abuse, sng-seal, sng-memfd, sng-filename, sng-dirmany, sng-filerace ... |
| __filemap_add_folio | 5 | 6133 | vms-mmap-pread-rand-mt, vms-mremap-xread-rand-mt, vms-mmap-xread-rand-mt, sng-mmapcow, sng-mmapmany |
| chrdev_open | 4 | 5491 | sng-full, sng-rlimit, sng-sockfd, sng-open |
| shmem_fallocate | 3 | 5463 | sng-chattr, sng-fpunch, sng-filerace |
| folio_lruvec_lock_irq | 5 | 5277 | sng-mlock, sng-msync, sng-mmapmany, sng-forkheavy, sng-env |
| cpuset_cpus_allowed | 2 | 4964 | sng-affinity, sng-cpu-sched |
| cgroup_leave_frozen | 5 | 4603 | sng-ptrace, sng-sigstop, sng-wait, sng-vfork, sng-vforkmany |
| cgroup_enter_frozen | 5 | 4582 | sng-ptrace, sng-sigstop, sng-wait, sng-vforkmany, sng-vfork |
| dput.part.0 | 10 | 4364 | sng-fstat, sng-handle, sng-landlock, sng-forkheavy, sng-sysinfo, sng-open ... |
| __do_sys_brk | 2 | 4339 | wis-brk1, wis-brk2 |
| lockref_get_not_dead | 7 | 3542 | sng-fstat, sng-handle, sng-landlock, sng-open, sng-dir, sng-clock ... |
| vma_prepare | 8 | 3509 | ub-execl, sng-dynlib, sng-munmap, sng-mmapmany, sng-fd-abuse, wis-page_fault1 ... |
| dquot_free_inode | 4 | 3310 | wisp-unlink2, wis-unlink2, sng-shm, sng-forkheavy |
| __slab_free | 18 | 3194 | sng-rawpkt, sng-rawsock, sng-rawudp, sng-msg, wisp-mmap2, sng-msync ... |
| anon_vma_fork | 18 | 3065 | sng-sigchld, sng-pidfd, sng-session, sng-landlock, sng-seccomp, sng-exit-group ... |
| unlink_file_vma_batch_final | 16 | 3026 | sng-dynlib, ub-execl, sng-munmap, sng-sigchld, sng-pidfd, sng-session ... |
| cgroup_file_notify | 1 | 2981 | sng-mremap |
| vma_link_file | 8 | 2951 | ub-execl, sng-dynlib, vms-small-allocs, sng-fd-abuse, wis-signal1, vms-lru-file-mmap-read-rand ... |
| folio_lruvec_lock_irqsave | 22 | 2928 | sng-file-ioctl, sng-mmapmany, vms-lru-file-mmap-read-rand, sng-mlock, sng-env, sng-fsize ... |
| dquot_add_inodes | 4 | 2873 | wisp-unlink2, wis-unlink2, sng-shm, sng-forkheavy |
| anon_vma_clone | 15 | 2681 | sng-sigchld, sng-pidfd, sng-session, sng-landlock, sng-seccomp, sng-exit-group ... |
| unlink_anon_vmas | 25 | 2563 | sng-sigchld, sng-pidfd, sng-session, sng-landlock, sng-seccomp, sng-exit-group ... |
| do_epoll_ctl | 3 | 2128 | pbe-ctl, sng-epoll, sng-epollmany |
| filename_unlinkat | 13 | 1858 | wis-unlink1, wisp-unlink1, sng-chattr, sng-filerace, sng-unlink, sng-landlock ... |
| set_current_blocked | 1 | 1709 | wis-signal1 |
| get_signal | 2 | 1705 | wis-signal1, sng-exit-group |
| signal_setup_done | 1 | 1703 | wis-signal1 |
| do_send_sig_info | 1 | 1698 | wis-signal1 |
| vm_mmap_pgoff | 5 | 1668 | wis-mmap2, wis-mmap1, vms-mmap-pread-rand-mt, sng-procfs, sng-exit-group |
| __vm_munmap | 7 | 1666 | wis-mmap2, wis-mmap1, wis-page_fault1, vms-mmap-pread-rand-mt, sng-seal, sng-procfs ... |
| path_openat | 12 | 1612 | wis-unlink1, wisp-unlink1, sng-chattr, sng-filerace, sng-unlink, sng-landlock ... |
| proc_sys_permission | 5 | 1608 | sng-procfs, sng-forkheavy, sng-pty, sng-sysinfo, sng-dentry |
| unix_del_edges | 1 | 1408 | sng-sockfd |
| chown_common | 2 | 1395 | sng-chown, sng-filerace |
| unix_add_edges | 1 | 1393 | sng-sockfd |
| chmod_common | 2 | 1357 | sng-chmod, sng-filerace |
| __do_sys_setpgid | 1 | 1222 | sng-zombie |
| dup_mmap | 15 | 1160 | sng-sigchld, sng-pidfd, sng-session, sng-landlock, sng-seccomp, sng-exit-group ... |
| genl_rcv_msg | 1 | 1101 | sng-netlink-task |
| memory_lseek | 1 | 1068 | sng-physpage |
| __list_lru_walk_one | 2 | 1067 | vms-lru-file-mmap-read-rand, vms-lru-file-mmap-read |
| btrfs_tree_lock_nested | 3 | 929 | fsmark-btrfs-fsync, fsmark-btrfs-nosync, dbench-btrfs |
| proc_sys_call_handler | 3 | 927 | sng-procfs, sng-forkheavy, sng-pty |
| lru_gen_rotate_memcg | 5 | 774 | sng-mmapcow, sng-mmapmany, sng-forkheavy, vms-lru-file-mmap-read-rand, vms-lru-file-mmap-read |
| do_exit | 17 | 767 | sng-vfork, sng-vforkmany, sng-exit-group, sng-sigchld, sng-pidfd, sng-session ... |
| copy_process | 10 | 720 | sng-vfork, sng-vforkmany, sng-exit-group, sng-sigchld, sng-pidfd, sng-session ... |
| release_task | 14 | 709 | sng-vfork, sng-vforkmany, sng-exit-group, sng-sigchld, sng-pidfd, sng-session ... |
| __change_page_attr_set_clr | 1 | 621 | sng-secretmem |
| dqget | 2 | 607 | wis-unlink2, wisp-unlink2 |
| ep_send_events | 1 | 606 | pbe-wait |
| evict_folios | 5 | 602 | vms-lru-file-mmap-read-rand, vms-lru-file-mmap-read, sng-mmapcow, sng-mmapmany, sng-forkheavy |
| cpuset_lock | 1 | 591 | sng-schedpolicy |
| lockref_get | 7 | 511 | sng-handle, sng-landlock, sng-forkheavy, sng-sysinfo, sng-pty, sng-procfs ... |
| fcntl_dirnotify | 1 | 488 | sng-dnotify |
| dnotify_flush | 1 | 487 | sng-dnotify |
| unlink_file_vma_batch_add | 18 | 435 | ub-execl, vms-small-allocs, sng-sigchld, sng-pidfd, sng-session, sng-forkheavy ... |
| dqput.part.0 | 2 | 432 | wis-unlink2, wisp-unlink2 |
| btrfs_block_rsv_release | 3 | 392 | dbench-btrfs, fsmark-btrfs-nosync, fsmark-btrfs-fsync |
| proc_sys_open | 3 | 390 | sng-procfs, sng-forkheavy, sng-pty |
| __start_renaming | 3 | 371 | sng-rename, sng-filerace, sng-dir |
| add_device_randomness | 1 | 361 | sng-clock |
| d_move | 1 | 339 | sng-dir |
| reserve_bytes | 3 | 327 | dbench-btrfs, fsmark-btrfs-nosync, fsmark-btrfs-fsync |
| ilookup5 | 1 | 327 | sng-handle |
| unix_diag_dump | 1 | 322 | sng-sockdiag |
| drop_super | 1 | 322 | sng-sysinfo |
| user_get_super | 1 | 321 | sng-sysinfo |
| proc_sys_compare | 4 | 292 | sng-procfs, sng-forkheavy, sng-pty, sng-sysinfo |
| pcpu_alloc_noprof | 10 | 285 | sng-seccomp, sng-sigchld, sng-ramfs, sng-pidfd, ub-execl, sng-clone ... |
| filename_rmdir | 3 | 282 | sng-filerace, sng-dir, sng-fcntl |
| ipcget | 3 | 275 | sng-shm-sysv, sng-forkheavy, sng-msg |
| proc_sys_poll | 1 | 250 | sng-procfs |
| posix_test_lock | 1 | 248 | sng-fcntl |
| __put_anon_vma | 11 | 224 | sng-sigchld, sng-pidfd, sng-session, sng-landlock, sng-seccomp, sng-exit-group ... |
| __flush_workqueue | 4 | 178 | fsmark-xfs-fsync, sng-io, sng-dirdeep, sng-mknod |
| do_truncate | 4 | 174 | sng-fpunch, sng-fcntl, sng-filerace, sng-unlink |
| netlink_release | 1 | 162 | sng-sockdiag |
| __refill_objects_node | 8 | 158 | sng-rawpkt, sng-msg, sng-session, sng-mmap, wisp-brk2, wisp-brk1 ... |
| proc_sys_lookup | 1 | 158 | sng-procfs |
| __jbd2_log_wait_for_space | 2 | 153 | fsmark-ext4-fsync, dbench-ext4 |
| vfs_unlink | 2 | 139 | sng-chattr, sng-filerace |
| filename_create | 11 | 135 | sng-link, fsmark, sng-unlink, fsmark-btrfs-fsync, fsmark-ext4-fsync, fsmark-xfs-fsync ... |
| vfs_fileattr_set | 2 | 132 | sng-chattr, sng-filerace |
| proc_sys_getattr | 2 | 130 | sng-procfs, sng-pty |
| compact_zone | 2 | 121 | vms-lru-file-mmap-read, sng-mmapcow |
| __dquot_free_space | 6 | 120 | wisp-fallocate2, wisp-fallocate1, wis-fallocate1, wis-fallocate2, sng-shm, sng-forkheavy |
| jbd2_journal_next_log_block | 2 | 118 | dbench-ext4, fsmark-ext4-fsync |
| bpf_prog_pack_free | 1 | 117 | sng-seccomp |
| d_find_alias | 1 | 113 | sng-handle |
| get_from_partial_node | 1 | 111 | sng-session |
| ip_ra_control | 1 | 105 | sng-rawudp |
| bpf_prog_pack_alloc | 1 | 100 | sng-seccomp |
| jbd2_journal_dirty_metadata | 2 | 89 | fsmark-ext4-fsync, dbench-ext4 |
| text_poke_copy | 1 | 87 | sng-seccomp |
| wait_log_commit | 2 | 85 | fsmark-btrfs-fsync, dbench-btrfs |
| __do_sys_ioprio_get | 1 | 84 | sng-ioprio |
| membarrier_private_expedited | 1 | 81 | sng-membarrier |
| get_page_from_freelist | 3 | 74 | vms-lru-file-mmap-read, vms-lru-file-mmap-read-rand, sng-dev-shm |
| ptmx_open | 3 | 74 | sng-pty, sng-forkheavy, sng-open |
| d_alloc_parallel | 4 | 66 | sng-landlock, sng-procfs, sng-getdent, sng-clock |
| add_transaction_credits | 2 | 61 | fsmark-ext4-fsync, dbench-ext4 |
| percpu_rwsem_wait | 1 | 60 | sng-flock |
| __dentry_kill | 6 | 59 | sng-landlock, sng-open, sng-clock, sng-sysinfo, sng-procfs, sng-getdent |
| tty_open | 2 | 57 | sng-pty, sng-forkheavy |
| shmctl_down | 1 | 57 | sng-shm-sysv |
| do_shmat | 1 | 56 | sng-shm-sysv |
| __shm_close | 2 | 54 | sng-shm-sysv, fio-randwrite-shared |
| tty_release_struct | 2 | 54 | sng-pty, sng-forkheavy |
| start_creating_noperm | 1 | 52 | sng-forkheavy |
| jbd2_journal_commit_transaction | 2 | 48 | dbench-ext4, fsmark-ext4-fsync |
| free_percpu | 4 | 48 | sng-ramfs, sng-sigchld, sng-seccomp, sng-clone |
| exit_mmap | 2 | 46 | sng-pidfd, sng-sigchld |
| vfs_utimes | 2 | 45 | sng-open, sng-filerace |
| raw_hash_sk | 1 | 45 | sng-rawudp |
| list_lru_add | 3 | 41 | vms-lru-file-mmap-read-rand, vms-lru-file-mmap-read, sng-open |
| msgctl_down | 2 | 40 | sng-msg, sng-forkheavy |
| free_one_page | 3 | 36 | vms-lru-file-mmap-read, dbench-ext4, sng-mmapcow |
| sync_inodes_sb | 5 | 36 | sng-mknod, sng-io, sng-dirdeep, sng-touch, sng-open |
| start_removing_noperm | 1 | 36 | sng-forkheavy |
| follow_up | 1 | 34 | sng-landlock |
| __do_sys_membarrier | 1 | 32 | sng-membarrier |
| raw_unhash_sk | 1 | 32 | sng-rawudp |
| fd_install_slowpath | 2 | 27 | wis-dup1, wis-unlink2 |
| __rmqueue_pcplist | 5 | 26 | vms-lru-file-mmap-read-rand, vms-lru-file-mmap-read, wisp-page_fault1, sng-mmapcow, sng-dev-shm |
| free_pcppages_bulk | 11 | 25 | vms-lru-file-mmap-read, sng-mmapcow, vms-lru-file-mmap-read-rand, dbench-ext4, wisp-page_fault1, sng-shm ... |
| text_poke_set | 1 | 25 | sng-seccomp |
| eventfd_read | 1 | 22 | pbe-wait |
| __register_sysctl_table | 1 | 22 | sng-clone |
