| candidate | 16 | 64 | lock share | busy | context switches/s | top symbols | passes |
|---|---|---|---|---|---|---|---|
| pbe-wait | 3.728e+04 | 8374 | 83% | 79% | 25742 | osq_lock 80%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 83%; fall 0.22 |
| pbe-ctl | 2.656e+05 | 3.927e+04 | 85% | 99% | 17786 | osq_lock 83%, __raw_callee_save___kvm_vcpu_is_preempted 13% | lock 85%; fall 0.15 |
| pbf-requeue | 75.76 | 32.68 | 4% | 0% | 202 | update_sd_lb_stats.constprop.0 9%, __free_one_page 8% | fall 0.43; sleep (busy 0%) |
| pbf-wake | 37.31 | 12.14 | 8% | 0% | 183 | rb_next 7%, update_rq_clock 5% | fall 0.33; sleep (busy 0%) |
| pft | 3.614e+06 | 7.091e+06 | 3% | 0% | 185 | smp_text_poke_batch_finish 8%, drm_crtc_vblank_get_vblank_timeout 7% | sleep (busy 0%) |
| schbench | 5999 | 2.234e+04 | 0% | 98% | 96690 | worker_thread 99%, lapic_next_deadline 0% | no |
| netperf-TCP_RR | 1.052e+06 | 7.502e+06 | 3% | 100% | 15059418 | pvclock_clocksource_read_nowd 4%, tcp_ack 4% | no |
| netperf-TCP_CRR | 4.882e+05 | 1.462e+06 | 6% | 100% | 5850218 | _raw_spin_lock_bh 3%, pvclock_clocksource_read_nowd 3% | no |
| netperf-UDP_RR | 1.191e+06 | 8.131e+06 | 1% | 99% | 16552216 | __ip_select_ident 13%, pvclock_clocksource_read_nowd 3% | no |
| netperf-TCP_STREAM | 5.895e+05 | 2.514e+05 | 2% | 15% | 40043 | _copy_to_iter 53%, kernel_init_pages 18% | fall 0.43; sleep (busy 15%) |
| redis | 4.706e+06 | 8.954e+06 | 6% | 98% | 1170984 | dictFind 9%, dictRehash 8% | no |
| memcached | 9.69e+05 | 2.161e+06 | 7% | 95% | 1809950 | pthread_mutex_unlock 6%, event_mm_malloc_ 5% | no |
| sysbench-mutex | 6683 | 9442 | 4% | 0% | 185 | asm_sysvec_apic_timer_interrupt 12%, mas_walk 6% | sleep (busy 0%) |
| sysbench-threads | 5717 | 5304 | 90% | 99% | 898009 | native_queued_spin_lock_slowpath 89%, pthread_mutex_unlock 1% | lock 90%; fall 0.93 |
| blogbench-w | 2608 | 2539 | 2% | 100% | 890 | entry_SYSCALL_64 10%, do_syscall_64 9% | fall 0.97 |
| blogbench-r | 4722 | 1.912e+04 | 2% | 99% | 940 | entry_SYSCALL_64 10%, do_syscall_64 9% | no |
| filebench-fileserver | 4.263e+05 | 3.47e+05 | 77% | 97% | 719866 | native_queued_spin_lock_slowpath 77%, _copy_to_iter 2% | lock 77%; fall 0.81 |
| filebench-varmail | 6.656e+05 | 6.259e+05 | 87% | 97% | 908865 | native_queued_spin_lock_slowpath 86%, filebench_log 1% | lock 87%; fall 0.94 |
| filebench-webserver | 7.019e+05 | 6.734e+05 | 89% | 99% | 786016 | native_queued_spin_lock_slowpath 88%, filebench_log 1% | lock 89%; fall 0.96 |
| filebench-webproxy | 5.728e+05 | 5.119e+05 | 88% | 97% | 890892 | native_queued_spin_lock_slowpath 88%, filebench_log 1% | lock 88%; fall 0.89 |
| fio-randwrite-shared | 9.069e+05 | 7.341e+05 | 84% | 88% | 64338 | osq_lock 82%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 84%; fall 0.81 |
| fio-randwrite-own | 2.488e+06 | 2.276e+06 | 6% | 0% | 1238 | find_lock_entries 10%, lru_gen_del_folio.constprop.0 7% | fall 0.91; sleep (busy 0%) |
| fio-randread-shared | 1.298e+07 | 1.616e+07 | 0% | 100% | 3536 | _copy_to_iter 58%, filemap_get_entry 21% | no |
| fio-randread-own | 6.102e+06 | 5.444e+06 | 0% | 101% | 1382 | _copy_to_iter 83%, filemap_get_entry 10% | fall 0.89 |
| pgbench-select | 4.369e+05 | 2.097e+06 | 1% | 100% | 4344674 | LWLockAttemptLock 5%, palloc0 3% | no |
| pgbench-update | 1.063e+05 | 2.29e+05 | 2% | 98% | 4080064 | base_yyparse 2%, LWLockAttemptLock 2% | no |
| vms-lru-file-mmap-read | 5.906e+07 | 6.625e+07 | 35% | 17% | 1331 | native_queued_spin_lock_slowpath 33%, kernel_init_pages 24% | lock 35%; sleep (busy 17%) |
| vms-lru-file-mmap-read-rand | 4.504e+07 | 1.076e+07 | 66% | 105% | 1078 | native_queued_spin_lock_slowpath 65%, smp_call_function_many_cond 14% | lock 66%; fall 0.24 |
| vms-mmap-pread-rand-mt | 1.103e+07 | 3.295e+06 | 90% | 106% | 1252 | native_queued_spin_lock_slowpath 90%, page_vma_mapped_walk 1% | lock 90%; fall 0.30 |
| vms-mmap-pread-seq-mt | 1.419e+08 | 5.139e+08 | 3% | 100% | 734030 | do_rw_once 30%, do_access 24% | no |
| vms-mmap-xread-rand-mt | 1.134e+07 | 4.128e+06 | 14% | 2% | 989 | native_queued_spin_lock_slowpath 11%, __free_one_page 9% | lock 14%; fall 0.36; sleep (busy 2%) |
| vms-mmap-xread-seq-mt | 1.451e+08 | 5.79e+08 | 8% | 98% | 255550 | do_rw_once 52%, do_access 32% | no |
| vms-mremap-xread-rand-mt | 2.266e+07 | 8.61e+06 | 22% | 3% | 756 | native_queued_spin_lock_slowpath 18%, migrate_pages_batch 9% | lock 22%; fall 0.38; sleep (busy 3%) |
| vms-shm-pread-rand-mt | 1.954e+06 | 4.671e+06 | 0% | 102% | 426 | do_access 97%, do_rw_once 1% | no |
| vms-shm-xread-rand-mt | 3.574e+06 | 1.171e+07 | 0% | 82% | 389 | do_access 96%, do_rw_once 1% | no |
| vms-lru-shm-rand | 2.925e+06 | 6.413e+06 | 3% | 0% | 200 | __free_one_page 6%, _find_next_and_bit 5% | sleep (busy 0%) |
| vms-msync-mt | 1.054e+07 | 3.764e+07 | 0% | 43% | 588 | do_rw_once 73%, do_access 17% | sleep (busy 43%) |
| vms-anon-r-seq-mt | 1.085e+08 | 2.182e+08 | 1% | 100% | 309 | do_access 38%, do_rw_once 26% | no |
| vms-anon-rx-rand-mt | 5.417e+07 | 6.041e+07 | 0% | 93% | 390 | do_access 91%, do_rw_once 2% | no |
| kbuild | - | 67.06 | 1% | 11% | 6288 | expr_lookup 3%, asm_exc_page_fault 1% | sleep (busy 11%) |
| aim7-ext4-disk_cp | 3.704e+05 | 1.014e+06 | 4% | 0% | 196 | unmap_page_range 8%, pv_native_safe_halt 7% | sleep (busy 0%) |
| aim7-ext4-disk_rr | 3.679e+05 | 9.288e+05 | 0% | 0% | 326 | update_sd_lb_stats.constprop.0 8%, free_pcppages_bulk 5% | sleep (busy 0%) |
| aim7-ext4-disk_rw | 3.58e+05 | 8.675e+05 | 9% | 0% | 178 | _raw_spin_lock 8%, free_pcppages_bulk 5% | sleep (busy 0%) |
| aim7-ext4-disk_src | 2.085e+05 | 3.213e+05 | 3% | 0% | 246 | pv_native_safe_halt 10%, pvclock_clocksource_read_nowd 5% | sleep (busy 0%) |
| aim7-ext4-creat-clo | 6.856e+04 | 1.054e+05 | 1% | 0% | 360 | __intel_pmu_enable_all.isra.0 10%, pick_task_fair 7% | sleep (busy 0%) |
| aim7-ext4-sync_disk_rw | 1.746e+04 | 2.261e+04 | 6% | 0% | 246 | cpuidle_get_cpu_driver 7%, rb_next 6% | sleep (busy 0%) |
| aim7-ext4-disk_rd | 1.14e+06 | 2.886e+06 | 1% | 0% | 248 | sched_ttwu_pending 7%, filemap_map_pages 5% | sleep (busy 0%) |
| fsmark-ext4-nosync | 5.724e+05 | 4.681e+05 | 4% | 0% | 776 | 0x000000000000087b 6%, 0x000000000000b888 4% | fall 0.82; sleep (busy 0%) |
| fsmark-ext4-fsync | 6.128e+04 | 5.963e+04 | 46% | 7% | 484794 | native_queued_spin_lock_slowpath 25%, osq_lock 13% | lock 46%; fall 0.97; sleep (busy 7%) |
| dbench-ext4 | 8379 | 1.16e+04 | 25% | 81% | 148662 | native_queued_spin_lock_slowpath 17%, osq_lock 5% | lock 25% |
| aim7-xfs-disk_cp | 2.309e+05 | 3.648e+05 | 7% | 0% | 228 | pvclock_clocksource_read_nowd 8%, _raw_spin_lock 5% | sleep (busy 0%) |
| aim7-xfs-disk_rr | 3.082e+05 | 6.083e+05 | 0% | 0% | 229 | lapic_next_deadline 8%, pvclock_clocksource_read_nowd 7% | sleep (busy 0%) |
| aim7-xfs-disk_rw | 2.984e+05 | 5.984e+05 | 7% | 0% | 324 | unmap_page_range 7%, tick_check_oneshot_broadcast_this_cpu 5% | sleep (busy 0%) |
| aim7-xfs-disk_src | 6.012e+04 | 6.417e+04 | 7% | 0% | 223 | cpuidle_get_cpu_driver 6%, pvclock_clocksource_read_nowd 6% | sleep (busy 0%) |
| aim7-xfs-creat-clo | 1.203e+05 | 2.009e+05 | 1% | 0% | 220 | arch_cpu_idle 6%, asm_sysvec_apic_timer_interrupt 5% | sleep (busy 0%) |
| aim7-xfs-sync_disk_rw | 3.232e+04 | 2.446e+04 | 2% | 0% | 283 | unmap_page_range 6%, asm_sysvec_apic_timer_interrupt 6% | fall 0.76; sleep (busy 0%) |
| aim7-xfs-disk_rd | 3.428e+05 | 4.242e+05 | 4% | 0% | 227 | __switch_to_asm 8%, pvclock_clocksource_read_nowd 6% | sleep (busy 0%) |
| fsmark-xfs-nosync | 2.57e+05 | 1.173e+05 | 6% | 27% | 23716 | _raw_spin_lock 4%, memcpy 3% | fall 0.46; sleep (busy 27%) |
| fsmark-xfs-fsync | 5.914e+04 | 4.893e+04 | 13% | 53% | 792894 | _raw_spin_lock 4%, memcpy 4% | lock 13%; fall 0.83; sleep (busy 53%) |
| dbench-xfs | 1.117e+04 | 7303 | 4% | 76% | 515310 | _copy_to_iter 5%, xlog_cil_commit 3% | fall 0.65 |
| aim7-btrfs-disk_cp | 2.981e+04 | 3.463e+04 | 5% | 0% | 263 | pvclock_clocksource_read_nowd 8%, asm_sysvec_apic_timer_interrupt 7% | sleep (busy 0%) |
| aim7-btrfs-disk_rr | 2.737e+04 | 0 | 14% | 0% | 306 | _raw_spin_lock_irqsave 9%, native_apic_msr_eoi 7% | no value |
| aim7-btrfs-disk_rw | 1.41e+04 | 0 | 3% | 0% | 184 | do_user_addr_fault 8%, collect_percpu_times 5% | no value |
| fsmark-btrfs-nosync | - | 3.644e+04 | 43% | 50% | 200815 | native_queued_spin_lock_slowpath 25%, _raw_spin_lock 5% | lock 43%; sleep (busy 50%) |
| fsmark-btrfs-fsync | - | 6991 | 0% | - | 65888 |  | no |
| dbench-btrfs | - | 529.3 | 6% | 99% | 59092 | entry_SYSCALL_64 12%, do_syscall_64 11% | no |
| wis-brk1 | - | 4.79e+05 | 15% | 99% | 8131 | osq_lock 12%, entry_SYSCALL_64 11% | lock 15% |
| wis-brk2 | - | 3.247e+05 | 22% | 98% | 11284 | fdget 26%, fput 23% | lock 22% |
| wis-mmap1 | - | 1.561e+05 | 0% | - | 6686 |  | no |
| wis-mmap2 | - | 2.267e+05 | 0% | - | 22901 |  | no |
| wis-page_fault1 | - | 2.921e+06 | 0% | - | 3338 |  | no |
| wis-page_fault2 | - | 2.853e+06 | 0% | - | 86992 |  | no |
| wis-page_fault3 | - | 9.969e+06 | 0% | - | 5230 |  | no |
| wis-tlb_flush1 | - | 3.302e+05 | 2% | 100% | 10892 | smp_call_function_many_cond 40%, _copy_to_iter 8% | no |
| wis-tlb_flush2 | - | 5.436e+05 | 2% | 100% | 126732 | smp_call_function_many_cond 26%, _copy_to_iter 7% | no |
| wis-tlb_flush3 | - | 2.349e+05 | 2% | 100% | 10913 | smp_call_function_many_cond 46%, entry_SYSCALL_64 6% | no |
| wis-signal1 | - | 5.984e+05 | 0% | - | 8944 |  | no |
| wis-dup1 | - | 9.323e+05 | 0% | - | 16404 |  | no |
| wis-lock2 | - | 2.471e+06 | 0% | - | 11200 |  | no |
| wis-open1 | - | 1.308e+06 | 0% | - | 10993 |  | no |
| wis-open3 | - | 1.107e+06 | 0% | - | 8119 |  | no |
| wis-unlink1 | - | 1.34e+05 | 41% | 100% | 17228 | native_queued_spin_lock_slowpath 33%, osq_lock 5% | lock 41% |
| wis-pwrite2 | - | 6.404e+05 | 33% | 100% | 10622 | native_queued_spin_lock_slowpath 26%, osq_lock 6% | lock 33% |
| wis-pwrite3 | - | 1.381e+06 | 42% | 99% | 7745318 | osq_lock 40%, __raw_callee_save___kvm_vcpu_is_preempted 6% | lock 42% |
| wis-writeseek3 | - | 1.423e+06 | 37% | 99% | 8958 | osq_lock 32%, entry_SYSCALL_64 12% | lock 37% |
| wis-readseek2 | - | 1.403e+06 | 66% | 100% | 86284 | native_queued_spin_lock_slowpath 65%, entry_SYSCALL_64 5% | lock 66% |
| wis-lseek2 | - | 1.59e+08 | 45% | 100% | 11554 | native_queued_spin_lock_slowpath 42%, entry_SYSCALL_64 10% | lock 45% |
| wis-read2 | - | 5.275e+07 | 4% | 100% | 127066 | filemap_get_entry 10%, entry_SYSCALL_64 9% | no |
| wis-pread2 | - | 1.53e+06 | 0% | - | 87374 |  | no |
| wis-futex1 | - | 1.213e+08 | 0% | - | 10604 |  | no |
| wis-futex2 | - | 1.041e+08 | 0% | - | 11118 |  | no |
| wis-pthread_mutex1 | - | 1.138e+07 | 0% | - | 125074 |  | no |
| wis-pthread_mutex3 | - | 1.149e+07 | 0% | - | 119038 |  | no |
| wis-pthread_mutex4 | - | 1.154e+07 | 46% | 100% | 123274 | native_queued_spin_lock_slowpath 46%, entry_SYSCALL_64 11% | lock 46% |
| wis-posix_semaphore1 | - | 1.347e+09 | 0% | 102% | 11486 | testcase 50%, sem_post 23% | no |
| wis-context_switch1 | - | 1.392e+07 | 5% | 100% | 7004701 | testcase 38%, __switch_to 11% | no |
| wis-sched_yield | - | 2.281e+04 | 92% | 100% | 22096 | native_queued_spin_lock_slowpath 91%, percpu_counter_add_batch 1% | lock 92% |
| wis-getppid1 | - | 2.021e+08 | 7% | 100% | 11467 | apparmor_file_free_security 15%, apparmor_file_alloc_security 14% | no |
| wis-read1 | - | 7.368e+07 | 0% | - | 11014 |  | no |
| wisp-lock2 | - | 1.472e+06 | 0% | - | 134232 |  | no |
| wisp-open1 | - | 8.682e+06 | 0% | - | 11364 |  | no |
| wisp-open3 | - | 2.948e+06 | 0% | - | 11018 |  | no |
| wisp-unlink1 | - | 2.013e+05 | 0% | - | 14168 |  | no |
| wisp-pwrite2 | - | 7.111e+05 | 25% | 100% | 9056 | do_sys_poll 26%, osq_lock 24% | lock 25% |
| wisp-pwrite3 | - | 1.342e+06 | 32% | 100% | 9686 | osq_lock 31%, _copy_to_iter 13% | lock 32% |
| wisp-futex1 | - | 1.304e+08 | 32% | 100% | 81844 | native_queued_spin_lock_slowpath 32%, gup_fast_fallback 9% | lock 32% |
| wisp-posix_semaphore1 | - | 1.272e+09 | 0% | 101% | 11612 | sem_post 26%, sem_wait 24% | no |
| sng-dentry | - | 1.076e+05 | 32% | 101% | 9037 | native_queued_spin_lock_slowpath 31%, testcase 21% | lock 32% |
| sng-dir | - | 2.613e+05 | 17% | 99% | 7910 | testcase 18%, pthread_mutex_lock 17% | lock 17% |
| sng-link | - | 38.02 | 0% | - | 9585 |  | no |
| sng-rename | - | 5.098e+05 | 0% | - | 9486 |  | no |
| sng-unlink | - | 636.1 | 78% | 47% | 16031 | native_queued_spin_lock_slowpath 70%, rwsem_spin_on_owner 6% | lock 78%; sleep (busy 47%) |
| sng-getdent | - | 1.324e+06 | 0% | - | 9158 |  | no |
| sng-filerace | - | 1.493e+04 | 0% | - | 77456 |  | no |
| sng-open | - | 1.178e+06 | 5% | 102% | 5908 | copy_folio_from_iter_atomic 11%, entry_SYSCALL_64 7% | no |
| sng-dup | - | 2.196e+04 | 0% | - | 55180 |  | no |
| sng-close | - | 4.305e+05 | 0% | - | 600300 |  | no |
| sng-inotify | - | 299.2 | 2% | 97% | 22683 | _copy_to_iter 15%, filemap_get_entry 11% | no |
| sng-fork | - | 3.866e+04 | 0% | - | 215090 |  | no |
| sng-vfork | - | 7.846e+04 | 0% | - | 357074 |  | no |
| sng-clone | - | 1142 | 59% | 94% | 6796 | native_queued_spin_lock_slowpath 57%, entry_SYSCALL_64 4% | lock 59% |
| sng-exit-group | - | 6350 | 45% | 97% | 2193942 | native_queued_spin_lock_slowpath 41%, sched_balance_find_dst_group 2% | lock 45% |
| sng-zombie | - | 1.9e+06 | 0% | - | 6108 |  | no |
| sng-wait | - | 2.031e+04 | 31% | 98% | 51656 | native_queued_spin_lock_slowpath 27%, entry_SYSCALL_64 7% | lock 31% |
| sng-kill | - | 8937 | 3% | 101% | 35436 | apparmor_task_kill 53%, entry_SYSCALL_64 5% | no |
| sng-signal | - | 4.206e+06 | 0% | - | 10547 |  | no |
| sng-sigq | - | 4.607e+06 | 13% | 98% | 860914 | apparmor_task_kill 26%, native_queued_spin_lock_slowpath 13% | lock 13% |
| sng-sem | - | 8.167e+07 | 3% | 100% | 31271731 | pvclock_clocksource_read_nowd 7%, restore_fpregs_from_fpstate 5% | no |
| sng-sem-sysv | - | 1.167e+05 | 0% | - | 85546 |  | no |
| sng-msg | - | 6.179e+06 | 47% | 99% | 41486 | native_queued_spin_lock_slowpath 46%, asm_exc_page_fault 6% | lock 47% |
| sng-mq | - | 9.627e+06 | 2% | 100% | 1166942 | asm_exc_page_fault 8%, next_uptodate_folio 8% | no |
| sng-shm | - | 3388 | 0% | - | 19606 |  | no |
| sng-shm-sysv | - | 4111 | 45% | 99% | 25248 | native_queued_spin_lock_slowpath 40%, entry_SYSCALL_64 4% | lock 45% |
| sng-futex | - | 1.118e+06 | 0% | 99% | 1150424 | get_futex_key 29%, try_get_folio 26% | no |
| sng-pipe | - | 1.387e+07 | 0% | - | 1347016 |  | no |
| sng-pipeherd | - | 4.903e+07 | 9% | 0% | 2878172 | psi_task_change 10%, assign_work 8% | sleep (busy 0%) |
| sng-sock | - | 1.296e+04 | 4% | 41% | 21116 | _copy_to_iter 46%, kernel_init_pages 18% | sleep (busy 41%) |
| sng-sockpair | - | 1.087e+06 | 0% | - | 526222 |  | no |
| sng-udp | - | 5.116e+06 | 43% | 99% | 4132602 | osq_lock 39%, __raw_callee_save___kvm_vcpu_is_preempted 6% | lock 43% |
| sng-epoll | - | 1.43e+05 | 79% | 100% | 349630 | osq_lock 76%, __raw_callee_save___kvm_vcpu_is_preempted 11% | lock 79% |
| sng-eventfd | - | 6 | 0% | - | 5102228 |  | no |
| sng-switch | - | 9.139e+06 | 0% | - | 19868040 |  | no |
| sng-vm | - | 1.736e+06 | 1% | 95% | 490 | stress_vm_rowhammer.arch_sapphirerapids 38%, stress_vm_walking_flush_data.arch_sapphirerapids 21% | no |
| sng-mmap | - | 4539 | 29% | 29% | 2908 | native_queued_spin_lock_slowpath 27%, __refill_objects_node 4% | lock 29%; sleep (busy 29%) |
| sng-mmapfork | - | 128.9 | 46% | 0% | 18178 | native_queued_spin_lock_slowpath 45%, free_pcppages_bulk 6% | lock 46%; sleep (busy 0%) |
| sng-mremap | - | 6040 | 68% | 76% | 776 | native_queued_spin_lock_slowpath 64%, stress_mmap_check 9% | lock 68% |
| sng-mprotect | - | 53 | 6% | 0% | 12554 | _raw_spin_lock 6%, __memcg_slab_post_alloc_hook 4% | sleep (busy 0%) |
| sng-madvise | - | 55.06 | 0% | - | 540964 |  | no |
| sng-brk | - | 5.484e+04 | 0% | - | 5555 |  | no |
| sng-vma | - | 6.277e+04 | 2% | 0% | 15800 | lapic_next_deadline 8%, 0x00000000000fe357 7% | sleep (busy 0%) |
| sng-flock | - | 6.581e+05 | 33% | 94% | 467854 | native_queued_spin_lock_slowpath 32%, swapcontext 20% | lock 33% |
| sng-fcntl | - | 8.513e+04 | 92% | 90% | 231357 | native_queued_spin_lock_slowpath 91%, _raw_spin_lock 1% | lock 92% |
| sng-lockf | - | 3.516e+04 | 1% | 98% | 8698 | posix_lock_inode 94%, do_syscall_64 1% | no |
| sng-lockofd | - | 8.848e+06 | 25% | 92% | 7112 | posix_lock_inode 60%, native_queued_spin_lock_slowpath 21% | lock 25% |
| sng-tmpfs | - | 1228 | 9% | 87% | 2636 | asm_exc_page_fault 9%, native_queued_spin_lock_slowpath 8% | no |
| vms-anon-w-rand-mt | - | 3189 | 0% | - | 11235 |  | no |
| vms-anon-r-rand-mt | - | 9841 | 0% | - | 520939 |  | no |
| vms-anon-cow-rand-mt | - | 6.686e+06 | 0% | - | 1204 |  | no |
| vms-anon-wx-rand-mt | - | 1.093e+07 | 8% | 0% | 208 | __slab_free 8%, mas_topiary_replace 5% | sleep (busy 0%) |
| vms-small-allocs-mt | - | 0 | 79% | 94% | 46600 | osq_lock 77%, __raw_callee_save___kvm_vcpu_is_preempted 12% | no value |
| vms-anon-w-rand | - | 8.666e+05 | 0% | - | 939 |  | no |
| vms-small-allocs | - | 1.941e+07 | 14% | 100% | 38727 | osq_lock 7%, pvclock_clocksource_read_nowd 5% | lock 14% |
| hb-pipe-process | - | 1.495 | 53% | 0% | 194 | native_queued_spin_lock_slowpath 48%, free_pcppages_bulk 6% | lock 53%; sleep (busy 0%) |
| hb-pipe-threads | - | 1.437 | 4% | 0% | 123 | __tlb_remove_folio_pages 8%, 0x00000000000708d7 7% | sleep (busy 0%) |
| hb-socket-process | - | 2.099e+06 | 0% | - | 637602 |  | no |
| hb-socket-threads | - | 0.8666 | 3% | 0% | 460520 | folio_remove_rmap_ptes 12%, filemap_map_pages 8% | sleep (busy 0%) |
| pbf-hash | - | 2.19e+06 | 9% | 100% | 218 | futex_hash 25%, entry_SYSCALL_64 8% | no |
| pbf-lock-pi | - | 184 | 0% | 40% | 33874 | 0x0000000000001708 5%, 0x00000000000016ee 5% | sleep (busy 40%) |
| pbf-hash-shared | - | 2.163e+06 | 2% | 97% | 196 | futex_hash 18%, gup_fast_fallback 10% | no |
| pbf-wakepar | - | 181.8 | 5% | 0% | 2744 | asm_sysvec_apic_timer_interrupt 20%, __cxa_atexit 8% | sleep (busy 0%) |
| pbms-thread | - | 8.094e+06 | 0% | - | 8092858 |  | no |
| ebizzy | - | 3.162e+06 | 0% | - | 720 |  | no |
| tlbflush | - | 8.737e+05 | 0% | 2% | 485526 | accessmm 88%, lapic_next_deadline 1% | sleep (busy 2%) |
| aim7-creat-clo | - | 4.149e+05 | 8% | 1% | 142 | _raw_spin_lock 5%, __d_lookup_rcu 3% | sleep (busy 1%) |
| aim7-disk_rr | - | 294 | 0% | - | 25029 |  | no |
| aim7-disk_rw | - | 4795 | 0% | - | 11612 |  | no |
| aim7-disk_cp | - | 7.584e+04 | 0% | - | 4988 |  | no |
| aim7-disk_src | - | 9.942e+05 | 0% | - | 621253 |  | no |
| fsmark | - | 1.31e+06 | 10% | 0% | 228 | native_queued_spin_lock_slowpath 7%, 0x00000000003b5e00 6% | lock 10%; sleep (busy 0%) |
| dbench | - | 4.77e+04 | 2% | 100% | 16679 | apparmor_task_kill 37%, audit_signal_info_syscall 7% | no |
| ub-execl | - | 2.605e+04 | 0% | - | 13965 |  | no |
| ub-spawn | - | 4.406e+05 | 0% | - | 453 |  | no |
| ub-shell8 | - | 825.8 | 17% | 100% | 1159 | native_queued_spin_lock_slowpath 8%, 0x00000000001d4d64 4% | lock 17% |
| ub-pipe | - | 7.638e+07 | 0% | - | 10426 |  | no |
| ub-context1 | - | 34 | 0% | - | 688 |  | no |
| ub-syscall | - | 3888 | 12% | 113% | 512 | walk_page_range_mm_unsafe 14%, mt_find 9% | lock 12% |
| ub-fstime | - | 5505 | 0% | - | 530 |  | no |
| wis-eventfd1 | - | 1.183e+08 | 0% | - | 108358 |  | no |
| wis-fallocate1 | - | 9.857e+05 | 97% | 100% | 297812 | native_queued_spin_lock_slowpath 96%, __srcu_read_unlock 0% | lock 97% |
| wis-fallocate2 | - | 5.859e+05 | 96% | 100% | 481 | native_queued_spin_lock_slowpath 95%, __srcu_read_unlock 1% | lock 96% |
| wis-futex3 | - | 3.34e+08 | 0% | - | 14564 |  | no |
| wis-futex4 | - | 2.101e+08 | 0% | - | 11224 |  | no |
| wis-lock1 | - | 5.507e+05 | 94% | 100% | 638 | native_queued_spin_lock_slowpath 93%, _raw_spin_lock 1% | lock 94% |
| wis-lseek1 | - | 7 | 0% | - | 540 |  | no |
| wis-malloc2 | - | 0 | 0% | 102% | 191 | testcase 100%, get_jiffies_update 0% | no value |
| wis-open2 | - | 8.119e+04 | 0% | - | 8706 |  | no |
| wis-pipe1 | - | 14 | 0% | - | 207 |  | no |
| wis-poll1 | - | 2.119e+08 | 0% | - | 4472 |  | no |
| wis-poll2 | - | 1.495e+07 | 0% | - | 150064 |  | no |
| wis-pread1 | - | 34 | 0% | 100% | 532 | _copy_to_iter 17%, entry_SYSCALL_64 9% | no |
| wis-pread3 | - | 1.556e+08 | 0% | - | 703 |  | no |
| wis-pthread_mutex2 | - | 3.078e+09 | 0% | - | 9650 |  | no |
| wis-pthread_mutex5 | - | 3.78e+04 | 0% | - | 268818 |  | no |
| wis-pwrite1 | - | 8893 | 1% | 100% | 182 | copy_folio_from_iter_atomic 12%, entry_SYSCALL_64 7% | no |
| wis-read3 | - | 1.427e+08 | 0% | - | 5720 |  | no |
| wis-read4 | - | 1.792e+04 | 0% | - | 194843 |  | no |
| wis-readseek1 | - | 7.373e+04 | 0% | - | 346 |  | no |
| wis-readseek3 | - | 9.499e+07 | 0% | - | 5940 |  | no |
| wis-unix1 | - | 5.208e+04 | 0% | - | 1927369 |  | no |
| wis-unlink2 | - | 0.1544 | 64% | 100% | 3062 | native_queued_spin_lock_slowpath 62%, inc_rlimit_get_ucounts 3% | lock 64% |
| wis-write1 | - | 1.253e+08 | 0% | - | 6110 |  | no |
| wis-writeseek1 | - | 1.06e+08 | 0% | - | 8123 |  | no |
| wis-writeseek2 | - | 0.8495 | 63% | 92% | 22556 | osq_lock 61%, __raw_callee_save___kvm_vcpu_is_preempted 9% | lock 63% |
| wisp-brk1 | - | 1739 | 0% | - | 8282 |  | no |
| wisp-brk2 | - | 4.752e+07 | 0% | - | 8360 |  | no |
| wisp-context_switch1 | - | 3.475e+07 | 4% | 100% | 17461743 | switch_mm_irqs_off 5%, pvclock_clocksource_read_nowd 5% | no |
| wisp-dup1 | - | 1.778e+08 | 6% | 100% | 670 | entry_SYSCALL_64 20%, do_syscall_64 18% | no |
| wisp-eventfd1 | - | 1.121e+08 | 0% | - | 14804 |  | no |
| wisp-fallocate1 | - | 6.502e+04 | 96% | 100% | 14594 | native_queued_spin_lock_slowpath 96%, __srcu_read_unlock 1% | lock 96% |
| wisp-fallocate2 | - | 0.4551 | 65% | 100% | 486 | native_queued_spin_lock_slowpath 63%, entry_SYSCALL_64 5% | lock 65% |
| wisp-futex2 | - | 1.734e+08 | 0% | - | 5794 |  | no |
| wisp-futex3 | - | 15 | 0% | - | 22690 |  | no |
| wisp-futex4 | - | 2.445e+08 | 3% | 100% | 184 | entry_SYSCALL_64 14%, do_syscall_64 12% | no |
| wisp-getppid1 | - | 3.982e+08 | 0% | - | 24814 |  | no |
| wisp-lock1 | - | 5 | 0% | - | 1378 |  | no |
| wisp-lseek1 | - | 9 | 2% | 100% | 630 | entry_SYSCALL_64 21%, do_syscall_64 18% | no |
| wisp-lseek2 | - | 3.549e+08 | 0% | - | 100751 |  | no |
| wisp-malloc1 | - | 0 | 0% | 102% | 212 | testcase 100%, asm_sysvec_apic_timer_interrupt 0% | no value |
| wisp-malloc2 | - | 6241 | 0% | 100% | 308 | testcase 90%, lapic_next_deadline 2% | no |
| wisp-mmap1 | - | 3.905e+06 | 0% | - | 6584 |  | no |
| wisp-mmap2 | - | 2.647e+06 | 0% | - | 15960 |  | no |
| wisp-open2 | - | 8.493e+06 | 14% | 100% | 13616 | apparmor_file_free_security 35%, apparmor_file_alloc_security 34% | lock 14% |
| wisp-page_fault1 | - | 6.05e+06 | 0% | - | 2024 |  | no |
| wisp-page_fault2 | - | 3.887e+06 | 21% | 100% | 997630 | copy_mc_enhanced_fast_string 24%, native_queued_spin_lock_slowpath 21% | lock 21% |
| wisp-page_fault3 | - | 7.118 | 1% | 100% | 5399 | asm_exc_page_fault 36%, testcase 12% | no |
| wisp-pipe1 | - | 3.527e+04 | 0% | - | 544 |  | no |
| wisp-poll1 | - | 2.546e+08 | 0% | 100% | 208 | do_sys_poll 24%, entry_SYSCALL_64 14% | no |
| wisp-poll2 | - | 5.832e+07 | 0% | - | 714343 |  | no |
| wisp-pread1 | - | 1.572e+08 | 0% | 100% | 217180 | _copy_to_iter 16%, entry_SYSCALL_64 11% | no |
| wisp-pread2 | - | 264 | 91% | 100% | 92122 | native_queued_spin_lock_slowpath 91%, stress_waitcpu_x86_tpause0 2% | lock 91% |
| wisp-pread3 | - | 1.63e+08 | 0% | - | 577 |  | no |
| wisp-pthread_mutex1 | - | 7.818e+09 | 0% | - | 8749 |  | no |
| wisp-pthread_mutex2 | - | 9.202e+09 | 0% | - | 16876 |  | no |
| wisp-pthread_mutex3 | - | 9.124e+09 | 0% | 102% | 190 | pthread_mutex_lock 39%, pthread_mutex_unlock 26% | no |
| wisp-pthread_mutex4 | - | 7.938e+09 | 0% | - | 3520 |  | no |
| wisp-pthread_mutex5 | - | 8.134e+09 | 0% | - | 8372 |  | no |
| wisp-pwrite1 | - | 62 | 0% | 101% | 5940 | copy_folio_from_iter_atomic 17%, entry_SYSCALL_64 9% | no |
| wisp-read1 | - | 1.456e+08 | 0% | - | 580 |  | no |
| wisp-read2 | - | 7.174e+07 | 0% | - | 464309 |  | no |
| wisp-read3 | - | 2 | 0% | 100% | 13574 | _copy_to_iter 18%, entry_SYSCALL_64 10% | no |
| wisp-read4 | - | 1.026e+08 | 6% | 100% | 432374 | filemap_get_entry 21%, _copy_to_iter 11% | no |
| wisp-readseek1 | - | 1.055e+08 | 0% | - | 7916 |  | no |
| wisp-readseek2 | - | 2.976e+05 | 95% | 99% | 107831 | native_queued_spin_lock_slowpath 94%, filemap_get_entry 1% | lock 95% |
| wisp-readseek3 | - | 51 | 16% | 100% | 251 | native_queued_spin_lock_slowpath 16%, entry_SYSCALL_64 11% | lock 16% |
| wisp-sched_yield | - | 1.434e+08 | 0% | - | 27070 |  | no |
| wisp-signal1 | - | 3.827e+04 | 0% | - | 9400 |  | no |
| wisp-tlb_flush1 | - | 686 | 13% | 100% | 478 | native_queued_spin_lock_slowpath 12%, copy_mc_enhanced_fast_string 11% | lock 13% |
| wisp-tlb_flush2 | - | 1.109e+07 | 0% | - | 113560 |  | no |
| wisp-tlb_flush3 | - | 1.603e+07 | 0% | - | 7239 |  | no |
| wisp-unix1 | - | 5045 | 5% | 101% | 209 | posix_lock_inode 12%, entry_SYSCALL_64 6% | no |
| wisp-unlink2 | - | 6.924e+05 | 0% | - | 3439 |  | no |
| wisp-write1 | - | 9.725e+07 | 0% | - | 29416 |  | no |
| wisp-writeseek1 | - | 8 | 0% | 100% | 8432 | entry_SYSCALL_64 13%, copy_folio_from_iter_atomic 12% | no |
| wisp-writeseek2 | - | 6.502e+05 | 23% | 98% | 22286 | osq_lock 22%, ktime_get_coarse_real_ts64_mg 6% | lock 23% |
| wisp-writeseek3 | - | 1.272e+06 | 0% | - | 9934 |  | no |
| sng-acct | - | 2.777e+04 | 13% | 81% | 237860 | __refill_objects_node 5%, native_queued_spin_lock_slowpath 4% | lock 13% |
| sng-affinity | - | 6.509e+05 | 54% | 0% | 1073934 | native_queued_spin_lock_slowpath 51%, smp_call_function_many_cond 3% | lock 54%; sleep (busy 0%) |
| sng-aio | - | 4.451e+05 | 5% | 0% | 12190 | vfs_read 7%, number 6% | sleep (busy 0%) |
| sng-alarm | - | 9.693e+05 | 0% | - | 975464 |  | no |
| sng-bad-altstack | - | 9 | 0% | - | 56918 |  | no |
| sng-bigheap | - | 1.033e+05 | 0% | - | 11470 |  | no |
| sng-cap | - | 0 | 10% | 0% | 128 | lock_vma_under_rcu 9%, seq_read_iter 7% | no value |
| sng-chroot | - | 5.537e+04 | 18% | 99% | 122711 | osq_lock 9%, folios_put_refs 8% | lock 18% |
| sng-clock | - | 2.091e+05 | 68% | 96% | 558 | native_queued_spin_lock_slowpath 63%, ktime_get_update_offsets_now 14% | lock 68% |
| sng-context | - | 2.228e+05 | 0% | - | 160744 |  | no |
| sng-cpu-sched | - | 3137 | 42% | 100% | 4414995 | native_queued_spin_lock_slowpath 36%, raw_local_deliver 19% | lock 42% |
| sng-daemon | - | 3.654e+04 | 25% | 56% | 102327 | osq_lock 18%, unmap_page_range 5% | lock 25%; sleep (busy 56%) |
| sng-dev-shm | - | 120.8 | 74% | 90% | 313 | native_queued_spin_lock_slowpath 73%, copy_mc_enhanced_fast_string 5% | lock 74% |
| sng-dynlib | - | 18 | 0% | - | 7737 |  | no |
| sng-enosys | - | 4.503e+06 | 0% | - | 4397114 |  | no |
| sng-env | - | 4694 | 45% | 100% | 1274 | osq_lock 26%, native_queued_spin_lock_slowpath 9% | lock 45% |
| sng-fault | - | 5.151e+05 | 56% | 100% | 9708 | native_queued_spin_lock_slowpath 53%, _raw_spin_lock 2% | lock 56% |
| sng-fd-abuse | - | 4.651e+07 | 72% | 100% | 15374 | native_queued_spin_lock_slowpath 71%, entry_SYSCALL_64 3% | lock 72% |
| sng-fd-fork | - | 7159 | 2% | 81% | 16958 | fput_close 37%, filp_flush 26% | no |
| sng-fd-race | - | 8.894e+05 | 0% | - | 44854 |  | no |
| sng-fifo | - | 2.897e+07 | 0% | - | 4979557 |  | no |
| sng-filehole | - | 4.292e+06 | 51% | 100% | 2789 | native_queued_spin_lock_slowpath 46%, stress_filehole_io 5% | lock 51% |
| sng-full | - | 1.911e+06 | 82% | 100% | 704 | native_queued_spin_lock_slowpath 76%, osq_lock 5% | lock 82% |
| sng-forkheavy | - | 269.7 | 31% | 4% | 5887 | osq_lock 20%, mas_next_slot 10% | lock 31%; sleep (busy 4%) |
| sng-get | - | 1.208e+06 | 0% | - | 166792 |  | no |
| sng-getrandom | - | 2.827e+06 | 0% | - | 631 |  | no |
| sng-hrtimers | - | 4.044e+06 | 2% | 0% | 5956796 | update_sd_lb_stats.constprop.0 10%, asm_sysvec_apic_timer_interrupt 5% | sleep (busy 0%) |
| sng-io-uring | - | 4.599e+06 | 11% | 100% | 5249548 | native_queued_spin_lock_slowpath 6%, pvclock_clocksource_read_nowd 3% | lock 11% |
| sng-itimer | - | 6.385e+04 | 8% | 98% | 202 | entry_SYSCALL_64 18%, do_syscall_64 15% | no |
| sng-kcmp | - | 3.601e+06 | 7% | 97% | 3955 | entry_SYSCALL_64 10%, do_syscall_64 9% | no |
| sng-key | - | 9.485e+06 | 0% | - | 592 |  | no |
| sng-landlock | - | 498.1 | 0% | - | 42321 |  | no |
| sng-lockmix | - | 2.313e+05 | 0% | 0% | 25568 | __virt_addr_valid 5%, fdget_pos 3% | sleep (busy 0%) |
| sng-malloc | - | 6.043e+07 | 0% | - | 6348 |  | no |
| sng-mcontend | - | 2.877e+06 | 0% | - | 15976 |  | no |
| sng-membarrier | - | 1742 | 45% | 92% | 21174 | osq_lock 38%, __bitmap_weight 16% | lock 45% |
| sng-memfd | - | 2318 | 66% | 101% | 38206 | native_queued_spin_lock_slowpath 65%, shmem_add_to_page_cache 3% | lock 66% |
| sng-mincore | - | 1.138e+05 | 1% | 99% | 271 | asm_exc_page_fault 13%, entry_SYSCALL_64 7% | no |
| sng-min-nanosleep | - | 1814 | 2% | 84% | 614840 | lapic_next_deadline 13%, pv_native_safe_halt 8% | no |
| sng-mlock | - | 1.184e+05 | 48% | 1% | 692 | native_queued_spin_lock_slowpath 46%, unmap_page_range 3% | lock 48%; sleep (busy 1%) |
| sng-mlockmany | - | 0 | 7% | 1% | 136 | lapic_next_deadline 9%, ktime_get 7% | no value |
| sng-mmapaddr | - | 1.077e+06 | 13% | 77% | 11304 | down_read 13%, _raw_spin_lock 9% | lock 13% |
| sng-mmapfiles | - | 1.265e+06 | 6% | 0% | 220752 | down_write 7%, __vma_start_exclude_readers 5% | sleep (busy 0%) |
| sng-mmapfixed | - | 1.034e+05 | 9% | 87% | 13299 | down_read 13%, free_pgd_range 12% | no |
| sng-mmaprandom | - | 0 | 4% | 0% | 226 | asm_sysvec_apic_timer_interrupt 5%, _nohz_idle_balance.isra.0 5% | no value |
| sng-mmaptorture | - | 160.4 | 18% | 19% | 73354 | rwsem_spin_on_owner 7%, unmap_page_range 7% | lock 18%; sleep (busy 19%) |
| sng-mseal | - | 1.554e+07 | 0% | 99% | 219 | entry_SYSCALL_64 12%, do_syscall_64 11% | no |
| sng-msync | - | 1.816e+06 | 83% | 94% | 1580 | native_queued_spin_lock_slowpath 81%, entry_SYSCALL_64 1% | lock 83% |
| sng-msyncmany | - | 2.784e+05 | 2% | 35% | 274 | stress_msyncmany_child 87%, native_queued_spin_lock_slowpath 2% | sleep (busy 35%) |
| sng-mtx | - | 2.738e+09 | 0% | 96% | 26564 | pthread_mutex_unlock 44%, pthread_mutex_lock 40% | no |
| sng-munmap | - | 3.809e+05 | 81% | 97% | 40440 | osq_lock 79%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 81% |
| sng-mutex | - | 7.745e+05 | 5% | 0% | 462008 | smp_call_function_many_cond 10%, unmap_page_range 6% | sleep (busy 0%) |
| sng-loadavg | - | 6.137e+06 | 0% | - | - |  | no |
| sng-mmapmany | - | 5.546e+05 | 63% | 11% | 12222 | native_queued_spin_lock_slowpath 62%, __refill_objects_node 2% | lock 63%; sleep (busy 11%) |
| sng-mmapcow | - | 3.708e+06 | 33% | 71% | 7502 | native_queued_spin_lock_slowpath 32%, shmem_add_to_page_cache 14% | lock 33%; sleep (busy 71%) |
| sng-nanosleep | - | 3.988e+05 | 2% | 99% | 5532452 | pvclock_clocksource_read_nowd 5%, __schedule 4% | no |
| sng-netlink-proc | - | 6675 | 18% | 99% | 83098 | osq_lock 11%, netlink_broadcast_filtered 11% | lock 18% |
| sng-netlink-task | - | 5.55e+05 | 84% | 93% | 4687 | osq_lock 82%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 84% |
| sng-nice | - | 7732 | 5% | 99% | 189878 | entry_SYSCALL_64 9%, clear_bhb_loop 8% | no |
| sng-pthread | - | 2.286e+05 | 27% | 61% | 691765 | native_queued_spin_lock_slowpath 21%, _raw_spin_lock 3% | lock 27%; sleep (busy 61%) |
| sng-poll | - | 4.275e+06 | 5% | 91% | 1090810 | entry_SYSCALL_64 7%, do_syscall_64 6% | no |
| sng-prio-inv | - | 1.086e+07 | 8% | 100% | 5229841 | entry_SYSCALL_64 6%, pvclock_clocksource_read_nowd 6% | no |
| sng-race-sched | - | 4352 | 21% | 52% | 104048 | native_queued_spin_lock_slowpath 13%, _raw_spin_lock_irqsave 6% | lock 21%; sleep (busy 52%) |
| sng-schedmix | - | 4.385e+04 | 2% | 93% | 9079971 | stress_schedmix 7%, pvclock_clocksource_read_nowd 5% | no |
| sng-schedpolicy | - | 5.087e+05 | 81% | 91% | 5420 | osq_lock 79%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 81% |
| sng-seal | - | 7.863e+05 | 86% | 100% | 5826 | native_queued_spin_lock_slowpath 86%, _raw_spin_lock 1% | lock 86% |
| sng-seccomp | - | 8103 | 46% | 91% | 42078 | osq_lock 42%, do_jit 13% | lock 46% |
| sng-secretmem | - | 9.66e+04 | 59% | 89% | 460 | native_queued_spin_lock_slowpath 58%, smp_call_function_many_cond 28% | lock 59% |
| sng-seek | - | 6.433e+05 | 0% | 93% | 288 | mapping_seek_hole_data 73%, xas_find 13% | no |
| sng-sendfile | - | 8.995e+05 | 0% | 98% | 200 | shmem_get_folio_gfp 36%, filemap_get_entry 23% | no |
| sng-session | - | 1.7e+04 | 35% | 99% | 78258 | native_queued_spin_lock_slowpath 14%, osq_lock 10% | lock 35% |
| sng-set | - | 1.36e+05 | 7% | 75% | 103695 | refcount_dec_and_lock_irqsave 33%, prepare_creds 7% | no |
| sng-sigabrt | - | 2.125e+04 | 16% | 96% | 51046 | prb_reserve 26%, desc_read 14% | lock 16% |
| sng-sigbus | - | 8.768e+06 | 1% | 98% | 180 | inc_rlimit_get_ucounts 37%, dec_rlimit_put_ucounts 35% | no |
| sng-sigchld | - | 7.001e+04 | 35% | 98% | 157213 | osq_lock 23%, native_queued_spin_lock_slowpath 4% | lock 35% |
| sng-sigfd | - | 8.442e+06 | 2% | 93% | 4135770 | apparmor_task_kill 28%, dec_rlimit_put_ucounts 17% | no |
| sng-sigfpe | - | 8.765e+06 | 1% | 98% | 172 | inc_rlimit_get_ucounts 30%, dec_rlimit_put_ucounts 29% | no |
| sng-sighup | - | 3.637e+04 | 20% | 98% | 188680 | osq_lock 11%, folios_put_refs 6% | lock 20% |
| sng-sigill | - | 8.691e+06 | 1% | 98% | 184 | inc_rlimit_get_ucounts 30%, dec_rlimit_put_ucounts 28% | no |
| sng-sigio | - | 1.788e+07 | 6% | 100% | 18306460 | switch_mm_irqs_off 6%, pvclock_clocksource_read_nowd 5% | no |
| sng-signest | - | 8.598e+06 | 1% | 96% | 192 | apparmor_task_kill 37%, inc_rlimit_get_ucounts 19% | no |
| sng-sigpending | - | 8.586e+06 | 1% | 97% | 251 | apparmor_task_kill 26%, dec_rlimit_put_ucounts 17% | no |
| sng-sigpipe | - | 8.777e+06 | 1% | 98% | 188 | inc_rlimit_get_ucounts 40%, dec_rlimit_put_ucounts 39% | no |
| sng-sigrt | - | 4.368e+06 | 1% | 44% | 3007089 | apparmor_task_kill 26%, dec_rlimit_put_ucounts 14% | sleep (busy 44%) |
| sng-sigsegv | - | 8.76e+06 | 1% | 98% | 166 | inc_rlimit_get_ucounts 34%, dec_rlimit_put_ucounts 32% | no |
| sng-sigstop | - | 2.46e+06 | 73% | 100% | 2736934 | native_queued_spin_lock_slowpath 72%, inc_rlimit_get_ucounts 3% | lock 73% |
| sng-sigsuspend | - | 6.714e+06 | 2% | 87% | 6402423 | apparmor_task_kill 30%, stress_lock_acquire 3% | no |
| sng-sigtrap | - | 8.771e+06 | 1% | 97% | 316 | inc_rlimit_get_ucounts 37%, dec_rlimit_put_ucounts 35% | no |
| sng-sigurg | - | 1.933e+06 | 5% | 100% | 7228 | entry_SYSCALL_64 9%, do_syscall_64 9% | no |
| sng-sigvtalrm | - | 6.383e+04 | 5% | 99% | 194 | entry_SYSCALL_64 20%, do_syscall_64 17% | no |
| sng-sigxcpu | - | 6.259e+04 | 8% | 100% | 440974 | entry_SYSCALL_64 11%, clear_bhb_loop 10% | no |
| sng-sigxfsz | - | 8.771e+06 | 1% | 97% | 256 | inc_rlimit_get_ucounts 38%, dec_rlimit_put_ucounts 37% | no |
| sng-sleep | - | 5.661e+05 | 75% | 0% | 8371609 | native_queued_spin_lock_slowpath 75%, unmap_page_range 2% | lock 75%; sleep (busy 0%) |
| sng-sockabuse | - | 3342 | 5% | 55% | 147326 | entry_SYSCALL_64 3%, clear_bhb_loop 3% | sleep (busy 55%) |
| sng-sockdiag | - | 8.477e+07 | 88% | 99% | 8933 | native_queued_spin_lock_slowpath 58%, _raw_spin_lock 29% | lock 88% |
| sng-sockfd | - | 9.929e+05 | 92% | 81% | 455148 | native_queued_spin_lock_slowpath 91%, _raw_spin_lock 1% | lock 92% |
| sng-sockmany | - | 7.698e+04 | 44% | 82% | 18292 | __inet_check_established 38%, _raw_spin_lock_bh 25% | lock 44% |
| sng-splice | - | 2.126e+07 | 4% | 97% | 274 | entry_SYSCALL_64 16%, do_syscall_64 14% | no |
| sng-stack | - | 8.753e+06 | 1% | 97% | 219 | inc_rlimit_get_ucounts 32%, dec_rlimit_put_ucounts 30% | no |
| sng-stackmmap | - | 2.207e+04 | 1% | 99% | 47079 | stress_stackmmap_push_msync 79%, asm_exc_page_fault 1% | no |
| sng-statmount | - | 7.596e+04 | 0% | 93% | 255 | lockref_get 43%, lockref_put_return 41% | no |
| sng-syncload | - | 342.5 | 0% | 67% | 580 | 0x000000000000087b 27%, stress_time_now_timespec 7% | sleep (busy 67%) |
| sng-sysbadaddr | - | 6.457e+04 | 8% | 51% | 42764 | next_uptodate_folio 5%, unmap_page_range 5% | sleep (busy 51%) |
| sng-syscall | - | 5256 | 1% | 0% | 146 | default_idle 6%, filemap_map_pages 5% | sleep (busy 0%) |
| sng-sysfs | - | 1464 | 9% | 88% | 137119 | copy_page_range 4%, _raw_spin_lock 4% | no |
| sng-sysinfo | - | 9564 | 74% | 82% | 80558 | native_queued_spin_lock_slowpath 72%, down_read 2% | lock 74% |
| sng-tee | - | 4.721e+05 | 4% | 95% | 649404 | entry_SYSCALL_64 14%, do_syscall_64 12% | no |
| sng-timer | - | 1.045e+07 | 4% | 98% | 204 | lapic_next_deadline 20%, asm_sysvec_apic_timer_interrupt 8% | no |
| sng-timerfd | - | 1.309e+07 | 6% | 99% | 339 | lapic_next_deadline 29%, asm_sysvec_apic_timer_interrupt 12% | no |
| sng-timermix | - | 1.056e+07 | 4% | 100% | 1031079 | lapic_next_deadline 20%, asm_sysvec_apic_timer_interrupt 8% | no |
| sng-tlb-shootdown | - | 2.329e+05 | 0% | 1% | 5944 | stress_tlb_shootdown_child 79%, change_protection 6% | sleep (busy 1%) |
| sng-umask | - | 827.1 | 93% | 92% | 1836 | native_queued_spin_lock_slowpath 92%, __percpu_counter_sum 1% | lock 93% |
| sng-unshare | - | 192 | 8% | 1% | 49214 | _raw_spin_lock 6%, __slab_free 4% | sleep (busy 1%) |
| sng-urandom | - | 1.762e+06 | 1% | 98% | 742 | chacha_permute 46%, _copy_to_iter 10% | no |
| sng-userfaultfd | - | 2.002e+06 | 1% | 89% | 2145234 | stress_atomic_lock_acquire_relax 72%, asm_exc_page_fault 1% | no |
| sng-usersyscall | - | 4.382e+06 | 1% | 98% | 277 | inc_rlimit_get_ucounts 37%, dec_rlimit_put_ucounts 34% | no |
| sng-vdso | - | 3.936e+09 | 0% | 89% | 212 | 0x000000000000087b 56%, __vdso_gettimeofday 9% | no |
| sng-vforkmany | - | 3.566e+05 | 78% | 73% | 415220 | native_queued_spin_lock_slowpath 73%, sched_balance_find_dst_group 1% | lock 78%; sleep (busy 73%) |
| sng-vm-addr | - | 206.3 | 0% | 80% | 430 | stress_vm_addr_revinv.arch_sapphirerapids 56%, stress_vm_addr_rev.arch_sapphirerapids 41% | no |
| sng-vm-rw | - | 2.098e+06 | 4% | 97% | 2151752 | _copy_from_iter 24%, _copy_to_iter 24% | no |
| sng-vm-segv | - | 2.131e+04 | 13% | 87% | 70686 | prb_reserve 26%, desc_read 14% | lock 13% |
| sng-vm-splice | - | 5.066e+07 | 4% | 98% | 266 | entry_SYSCALL_64 12%, do_syscall_64 10% | no |
| sng-waitcpu | - | 3975 | 0% | 86% | 195 | stress_waitcpu_x86_tpause0 50%, stress_waitcpu_x86_tpause1 49% | no |
| sng-x86syscall | - | 3.779e+08 | 0% | 101% | 188 | entry_SYSCALL_64 22%, do_syscall_64 19% | no |
| sng-zero | - | 2.498e+08 | 0% | 97% | 699 | read_zero 20%, entry_SYSCALL_64 14% | no |
| sng-access | - | 5.046e+05 | 0% | 98% | 2481782 | __d_lookup_rcu 10%, entry_SYSCALL_64 7% | no |
| sng-acl | - | 0 | 2% | 0% | 131 | pvclock_clocksource_read_nowd 5%, native_apic_msr_eoi 5% | no value |
| sng-aiol | - | 0 | 17% | 0% | 152 | native_queued_spin_lock_slowpath 11%, idle_cpu 8% | no value |
| sng-chdir | - | 270.3 | 4% | 100% | 468 | lockref_put_return 42%, lockref_get_not_dead 26% | no |
| sng-chmod | - | 5568 | 84% | 92% | 14226 | osq_lock 82%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 84% |
| sng-chown | - | 9.265e+04 | 84% | 91% | 18665 | osq_lock 82%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 84% |
| sng-copy-file | - | 6.044e+04 | 60% | 75% | 588 | native_queued_spin_lock_slowpath 59%, folio_unlock 25% | lock 60% |
| sng-dentrycache | - | 5.75e+06 | 1% | 89% | 544 | lockref_get_not_dead 46%, lockref_put_return 40% | no |
| sng-dirdeep | - | 1.84e+04 | 94% | 97% | 54891 | native_queued_spin_lock_slowpath 94%, __d_lookup_rcu 2% | lock 94% |
| sng-dirmany | - | 8.161e+05 | 89% | 100% | 398 | native_queued_spin_lock_slowpath 87%, _raw_spin_lock 1% | lock 89% |
| sng-dnotify | - | 5.047e+04 | 78% | 97% | 10462 | osq_lock 76%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 78% |
| sng-fiemap | - | 0 | 8% | 0% | 240 | perf_adjust_freq_unthr_context 5%, ct_kernel_enter_state 5% | no value |
| sng-file-ioctl | - | 5.387e+04 | 77% | 90% | 560 | native_queued_spin_lock_slowpath 75%, shmem_get_folio_gfp 4% | lock 77% |
| sng-filename | - | 7.422e+04 | 81% | 96% | 5330 | native_queued_spin_lock_slowpath 80%, lockref_put_return 2% | lock 81% |
| sng-fpunch | - | 1.205e+06 | 50% | 90% | 19976 | native_queued_spin_lock_slowpath 29%, rwsem_spin_on_owner 15% | lock 50% |
| sng-fsize | - | 2.075e+05 | 84% | 92% | 483 | native_queued_spin_lock_slowpath 83%, shmem_add_to_page_cache 1% | lock 84% |
| sng-fstat | - | 10.66 | 98% | 94% | 23707 | native_queued_spin_lock_slowpath 97%, _copy_to_user 0% | lock 98% |
| sng-handle | - | 1.563e+05 | 97% | 93% | 356 | native_queued_spin_lock_slowpath 97%, lockref_put_return 0% | lock 97% |
| sng-inode-flags | - | 8.111e+05 | 8% | 88% | 11632 | apparmor_capable 23%, entry_SYSCALL_64 7% | no |
| sng-io | - | 1.076e+04 | 96% | 92% | 105228 | native_queued_spin_lock_slowpath 96%, down_read 1% | lock 96% |
| sng-iomix | - | 3.892e+06 | 1% | 91% | 136854 | apparmor_capable 42%, entry_SYSCALL_64 8% | no |
| sng-ioprio | - | 2.754e+05 | 74% | 85% | 272 | native_queued_spin_lock_slowpath 51%, _raw_spin_lock 23% | lock 74% |
| sng-lease | - | 9.831e+05 | 3% | 100% | 153786 | apparmor_file_alloc_security 39%, apparmor_file_free_security 39% | no |
| sng-locka | - | 4.839e+06 | 25% | 92% | 7355 | posix_lock_inode 63%, native_queued_spin_lock_slowpath 22% | lock 25% |
| sng-metamix | - | 2.384e+05 | 23% | 0% | 17196 | native_queued_spin_lock_slowpath 21%, asm_sysvec_apic_timer_interrupt 7% | lock 23%; sleep (busy 0%) |
| sng-mknod | - | 3.416e+04 | 97% | 98% | 51514 | native_queued_spin_lock_slowpath 97%, down_read 0% | lock 97% |
| sng-procfs | - | 2437 | 67% | 85% | 134167 | native_queued_spin_lock_slowpath 66%, proc_reg_read_iter 5% | lock 67% |
| sng-sync-file | - | 764.6 | 25% | 52% | 452 | shmem_add_to_page_cache 42%, native_queued_spin_lock_slowpath 24% | lock 25%; sleep (busy 52%) |
| sng-utime | - | 9.677e+05 | 0% | 98% | 189 | ktime_get_coarse_real_ts64_mg 10%, __d_lookup_rcu 7% | no |
| sng-xattr | - | 53.69 | 96% | 97% | 350 | native_queued_spin_lock_slowpath 96%, shmem_xattr_handler_set 0% | lock 96% |
| sng-chattr | - | 6205 | 70% | 86% | 137729 | osq_lock 38%, native_queued_spin_lock_slowpath 27% | lock 70% |
| sng-fanotify | - | 0 | 2% | 0% | 140 | psi_task_change 7%, collect_percpu_times 6% | no value |
| sng-touch | - | 4.435e+05 | 91% | 6% | 12430 | native_queued_spin_lock_slowpath 90%, __percpu_counter_sum 1% | lock 91%; sleep (busy 6%) |
| sng-hdd | - | 5.591e+05 | 2% | 68% | 528 | _copy_to_iter 26%, shmem_add_to_page_cache 23% | sleep (busy 68%) |
| sng-fallocate | - | 657 | 3% | 41% | 524 | shmem_add_to_page_cache 31%, shmem_get_folio_gfp 22% | sleep (busy 41%) |
| sng-epollmany | - | 1.363e+04 | 85% | 97% | 4108 | osq_lock 83%, __raw_callee_save___kvm_vcpu_is_preempted 13% | lock 85% |
| sng-icmp-flood | - | 1.765e+07 | 4% | 97% | 9328 | icmp_out_count 52%, raw_sendmsg 2% | no |
| sng-ping-sock | - | 8.912e+06 | 1% | 99% | 182 | __ip_select_ident 51%, icmp_out_count 12% | no |
| sng-rawpkt | - | 8.133e+04 | 45% | 90% | 7206 | native_queued_spin_lock_slowpath 42%, packet_rcv 39% | lock 45% |
| sng-rawsock | - | 1.147e+07 | 49% | 84% | 9606 | native_queued_spin_lock_slowpath 44%, raw_local_deliver 17% | lock 49% |
| sng-rawudp | - | 7.565e+04 | 58% | 101% | 79984 | native_queued_spin_lock_slowpath 53%, sock_rfree 6% | lock 58% |
| sng-udp-flood | - | 1.368e+07 | 5% | 96% | 416 | icmp_out_count 13%, __ip_select_ident 11% | no |
| sng-pagemove | - | 4.012e+05 | 5% | 95% | 4945 | native_flush_tlb_one_user 7%, mas_walk 5% | no |
| sng-physpage | - | 1.112e+06 | 58% | 98% | 6966 | osq_lock 49%, __raw_callee_save___kvm_vcpu_is_preempted 7% | lock 58% |
| sng-pidfd | - | 6.491e+04 | 33% | 98% | 152543 | osq_lock 21%, native_queued_spin_lock_slowpath 4% | lock 33% |
| sng-pkey | - | 4.775e+06 | 5% | 71% | 3051 | change_protection 6%, native_flush_tlb_one_user 5% | sleep (busy 71%) |
| sng-prctl | - | 5.133e+04 | 15% | 99% | 140266 | folios_put_refs 10%, osq_lock 7% | lock 15% |
| sng-pseek | - | 3.493e+06 | 1% | 100% | 8817890 | stress_peekio_exercise 21%, pseek_fill_buf.arch_sapphirerapids 6% | no |
| sng-ptrace | - | 1.105e+06 | 92% | 87% | 1400555 | native_queued_spin_lock_slowpath 90%, _raw_read_lock 1% | lock 92% |
| sng-pty | - | 494.3 | 83% | 95% | 50076 | osq_lock 81%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 83% |
| sng-ramfs | - | 1.554e+04 | 58% | 62% | 149950 | native_queued_spin_lock_slowpath 41%, rwsem_spin_on_owner 6% | lock 58%; sleep (busy 62%) |
| sng-readahead | - | 6.971e+07 | 0% | 98% | 250 | stress_readahead 25%, entry_SYSCALL_64 12% | no |
| sng-remap | - | 6097 | 3% | 96% | 696 | vma_interval_tree_insert 6%, native_flush_tlb_one_user 4% | no |
| sng-resched | - | 1.038e+07 | 14% | 100% | 2959551 | osq_lock 6%, native_queued_spin_lock_slowpath 3% | lock 14% |
| sng-revio | - | 9.435e+06 | 13% | 64% | 1018 | shmem_add_to_page_cache 36%, native_queued_spin_lock_slowpath 12% | lock 13%; sleep (busy 64%) |
| sng-ring-pipe | - | 1.194e+07 | 25% | 98% | 190 | _raw_spin_lock_irqsave 24%, pipe_poll 14% | lock 25% |
| sng-rlimit | - | 64.04 | 85% | 100% | 2758 | native_queued_spin_lock_slowpath 84%, lockref_put_return 4% | lock 85% |
| sng-rmap | - | 2.237e+05 | 0% | 0% | 12520 | 0x00000000001eeb8c 11%, _find_next_bit 8% | sleep (busy 0%) |
| sng-rseq | - | 1.804e+04 | 0% | 84% | 243 | rseq_test 100%, get_jiffies_update 0% | no |
| sng-personality | - | 5.529e+06 | 0% | 98% | 188 | entry_SYSCALL_64 26%, do_syscall_64 22% | no |
| sng-numa | - | 811.3 | 13% | 77% | 46354 | __bitmap_weight 30%, queue_folios_pte_range 11% | lock 13% |

204 of 451 pass
