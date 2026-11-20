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
| fsmark-btrfs-nosync | - | 3.441e+04 | 41% | 46% | 188578 | native_queued_spin_lock_slowpath 26%, _raw_spin_lock 5% | lock 41%; sleep (busy 46%) |
| fsmark-btrfs-fsync | - | 2.819e+04 | 46% | 90% | 343922 | osq_lock 21%, native_queued_spin_lock_slowpath 16% | lock 46% |
| dbench-btrfs | - | 1265 | 44% | 84% | 283736 | native_queued_spin_lock_slowpath 34%, _raw_spin_lock 2% | lock 44% |
| wis-brk1 | - | 3.897e+05 | 84% | 92% | 68972 | osq_lock 82%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 84% |
| wis-brk2 | - | 3.723e+05 | 84% | 92% | 62403 | osq_lock 82%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 84% |
| wis-mmap1 | - | 1.26e+05 | 83% | 89% | 96242 | osq_lock 81%, __raw_callee_save___kvm_vcpu_is_preempted 13% | lock 83% |
| wis-mmap2 | - | 1.823e+05 | 84% | 91% | 66521 | osq_lock 82%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 84% |
| wis-page_fault1 | - | 4.269e+06 | 31% | 28% | 792 | _raw_spin_lock 30%, charge_memcg 14% | lock 31%; sleep (busy 28%) |
| wis-page_fault2 | - | 3.635e+06 | 2% | 28% | 616 | copy_mc_enhanced_fast_string 29%, xas_load 16% | sleep (busy 28%) |
| wis-page_fault3 | - | 1.188e+07 | 1% | 21% | 786 | asm_exc_page_fault 35%, sync_regs 13% | sleep (busy 21%) |
| wis-tlb_flush1 | - | 1.919e+05 | 4% | 100% | 276 | smp_call_function_many_cond 84%, native_queued_spin_lock_slowpath 4% | no |
| wis-tlb_flush2 | - | 3.611e+05 | 0% | 100% | 7172 | smp_call_function_many_cond 88%, llist_reverse_order 2% | no |
| wis-tlb_flush3 | - | 1.809e+05 | 1% | 100% | 347 | smp_call_function_many_cond 90%, llist_reverse_order 2% | no |
| wis-signal1 | - | 6.134e+05 | 98% | 100% | 195 | native_queued_spin_lock_slowpath 98%, _raw_spin_lock_irq 0% | lock 98% |
| wis-dup1 | - | 1.168e+06 | 99% | 100% | 294 | native_queued_spin_lock_slowpath 98%, _raw_spin_lock 0% | lock 99% |
| wis-lock2 | - | 2.889e+06 | 98% | 100% | 266 | native_queued_spin_lock_slowpath 98%, _raw_spin_lock 1% | lock 98% |
| wis-open1 | - | 1.24e+06 | 98% | 100% | 280 | native_queued_spin_lock_slowpath 97%, _raw_spin_lock 0% | lock 98% |
| wis-open3 | - | 1.181e+06 | 96% | 100% | 334 | native_queued_spin_lock_slowpath 96%, _raw_spin_lock 0% | lock 96% |
| wis-unlink1 | - | 1.757e+05 | 84% | 95% | 58658 | osq_lock 81%, __raw_callee_save___kvm_vcpu_is_preempted 13% | lock 84% |
| wis-pwrite2 | - | 6.326e+05 | 84% | 89% | 36662 | osq_lock 83%, __raw_callee_save___kvm_vcpu_is_preempted 13% | lock 84% |
| wis-pwrite3 | - | 1.239e+06 | 85% | 93% | 17373 | osq_lock 82%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 85% |
| wis-writeseek3 | - | 1.335e+06 | 84% | 92% | 10121 | osq_lock 81%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 84% |
| wis-readseek2 | - | 1.569e+06 | 94% | 100% | 113682 | native_queued_spin_lock_slowpath 94%, filemap_get_entry 1% | lock 94% |
| wis-lseek2 | - | 3.275e+08 | 4% | 100% | 198 | entry_SYSCALL_64 18%, do_syscall_64 16% | no |
| wis-read2 | - | 1.12e+08 | 6% | 100% | 308256 | filemap_get_entry 17%, _copy_to_iter 11% | no |
| wis-pread2 | - | 1.535e+06 | 95% | 99% | 103674 | native_queued_spin_lock_slowpath 94%, filemap_get_entry 1% | lock 95% |
| wis-futex1 | - | 2.619e+08 | 0% | 100% | 202 | gup_fast_fallback 16%, entry_SYSCALL_64 15% | no |
| wis-futex2 | - | 2.009e+08 | 3% | 100% | 199 | gup_fast_fallback 13%, entry_SYSCALL_64 11% | no |
| wis-pthread_mutex1 | - | 1.094e+07 | 94% | 100% | 96670 | native_queued_spin_lock_slowpath 94%, pthread_mutex_lock 1% | lock 94% |
| wis-pthread_mutex3 | - | 1.158e+07 | 96% | 100% | 91212 | native_queued_spin_lock_slowpath 95%, pthread_mutex_lock 1% | lock 96% |
| wis-pthread_mutex4 | - | 1.148e+07 | 96% | 100% | 90990 | native_queued_spin_lock_slowpath 95%, pthread_mutex_lock 1% | lock 96% |
| wis-posix_semaphore1 | - | 2.553e+09 | 0% | 102% | 208 | sem_post 47%, sem_wait 44% | no |
| wis-context_switch1 | - | 1.804e+07 | 2% | 100% | 9059870 | __switch_to 51%, pvclock_clocksource_read_nowd 3% | no |
| wis-sched_yield | - | 1.887e+08 | 5% | 100% | 216 | entry_SYSCALL_64 10%, do_syscall_64 9% | no |
| wis-getppid1 | - | 4.06e+08 | 0% | 99% | 214 | entry_SYSCALL_64 23%, do_syscall_64 20% | no |
| wis-read1 | - | 1.625e+08 | 2% | 99% | 229 | _copy_to_iter 16%, entry_SYSCALL_64 9% | no |
| wisp-lock2 | - | 3.705e+05 | 55% | 91% | 248352 | native_queued_spin_lock_slowpath 49%, _raw_spin_lock 4% | lock 55% |
| wisp-open1 | - | 9.024e+06 | 0% | 99% | 262 | apparmor_file_alloc_security 43%, apparmor_file_free_security 42% | no |
| wisp-open3 | - | 2.875e+06 | 0% | 99% | 268 | lockref_put_return 48%, lockref_get 21% | no |
| wisp-unlink1 | - | 1.743e+05 | 84% | 93% | 53992 | osq_lock 82%, __raw_callee_save___kvm_vcpu_is_preempted 13% | lock 84% |
| wisp-pwrite2 | - | 6.465e+05 | 85% | 85% | 31740 | osq_lock 83%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 85% |
| wisp-pwrite3 | - | 1.28e+06 | 85% | 90% | 8335 | osq_lock 82%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 85% |
| wisp-futex1 | - | 2.608e+08 | 0% | 99% | 200 | gup_fast_fallback 16%, entry_SYSCALL_64 15% | no |
| wisp-posix_semaphore1 | - | 2.553e+09 | 0% | 101% | 220 | sem_post 47%, sem_wait 44% | no |
| sng-dentry | - | 9.884e+04 | 96% | 98% | 1786 | native_queued_spin_lock_slowpath 96%, __percpu_counter_sum 0% | lock 96% |
| sng-dir | - | 1.728e+05 | 59% | 99% | 12994 | native_queued_spin_lock_slowpath 58%, apparmor_file_free_security 5% | lock 59% |
| sng-link | - | 29.47 | 97% | 99% | 652 | native_queued_spin_lock_slowpath 97%, __percpu_counter_sum 0% | lock 97% |
| sng-rename | - | 4.839e+05 | 92% | 97% | 6102 | native_queued_spin_lock_slowpath 65%, osq_lock 26% | lock 92% |
| sng-unlink | - | 665 | 85% | 73% | 15456 | native_queued_spin_lock_slowpath 77%, rwsem_spin_on_owner 6% | lock 85%; sleep (busy 73%) |
| sng-getdent | - | 1.364e+06 | 41% | 99% | 3449 | _raw_read_unlock 40%, _raw_read_lock 39% | lock 41% |
| sng-filerace | - | 1.664e+04 | 47% | 97% | 190062 | native_queued_spin_lock_slowpath 39%, find_positive_dentry 6% | lock 47% |
| sng-open | - | 1.671e+06 | 64% | 99% | 2784 | native_queued_spin_lock_slowpath 61%, lockref_get_not_dead 5% | lock 64% |
| sng-dup | - | 1.946e+06 | 5% | 87% | 166538 | entry_SYSCALL_64 6%, do_syscall_64 6% | no |
| sng-close | - | 3.081e+05 | 1% | 100% | 586014 | do_dup2 26%, filp_flush 19% | no |
| sng-inotify | - | 199.9 | 18% | 66% | 15176 | native_queued_spin_lock_slowpath 13%, ktime_get 6% | lock 18%; sleep (busy 66%) |
| sng-fork | - | 4.939e+04 | 17% | 97% | 111374 | folios_put_refs 10%, osq_lock 8% | lock 17% |
| sng-vfork | - | 1.841e+05 | 82% | 97% | 424048 | native_queued_spin_lock_slowpath 78%, sched_balance_find_dst_group 1% | lock 82% |
| sng-clone | - | 1301 | 15% | 37% | 24116 | copy_page_range 28%, _raw_spin_lock_irqsave 6% | lock 15%; sleep (busy 37%) |
| sng-exit-group | - | 6987 | 36% | 93% | 2449834 | native_queued_spin_lock_slowpath 32%, sched_balance_find_dst_group 2% | lock 36% |
| sng-zombie | - | 1.555e+06 | 95% | 93% | 362 | native_queued_spin_lock_slowpath 94%, put_pid 1% | lock 95% |
| sng-wait | - | 8.351e+04 | 84% | 99% | 3592698 | native_queued_spin_lock_slowpath 83%, apparmor_task_kill 2% | lock 84% |
| sng-kill | - | 9570 | 0% | 59% | 34610 | apparmor_task_kill 96%, get_task_cred 0% | sleep (busy 59%) |
| sng-signal | - | 8.667e+06 | 1% | 100% | 214 | inc_rlimit_get_ucounts 21%, apparmor_task_kill 21% | no |
| sng-sigq | - | 8.856e+06 | 1% | 98% | 7335328 | apparmor_task_kill 31%, inc_rlimit_get_ucounts 4% | no |
| sng-sem | - | 8.411e+07 | 3% | 99% | 25193948 | pvclock_clocksource_read_nowd 7%, stress_sem_thrash 5% | no |
| sng-sem-sysv | - | 6.225e+04 | 4% | 56% | 76458 | pv_native_safe_halt 5%, lapic_next_deadline 4% | sleep (busy 56%) |
| sng-msg | - | 1.762e+07 | 17% | 87% | 109366 | native_queued_spin_lock_slowpath 14%, percpu_counter_add_batch 8% | lock 17% |
| sng-mq | - | 1.074e+07 | 1% | 98% | 10465012 | fdget 17%, fput 10% | no |
| sng-shm | - | 3364 | 91% | 97% | 12708 | native_queued_spin_lock_slowpath 90%, asm_exc_page_fault 1% | lock 91% |
| sng-shm-sysv | - | 1.144e+04 | 52% | 88% | 160204 | osq_lock 42%, __raw_callee_save___kvm_vcpu_is_preempted 6% | lock 52% |
| sng-futex | - | 1.224e+06 | 0% | 85% | 1244954 | get_futex_key 29%, try_get_folio 23% | no |
| sng-pipe | - | 2.179e+07 | 4% | 99% | 15265305 | switch_mm_irqs_off 6%, pvclock_clocksource_read_nowd 5% | no |
| sng-pipeherd | - | 4.196e+07 | 2% | 0% | 3208658 | perf_adjust_freq_unthr_events 7%, smp_call_function_many_cond 5% | sleep (busy 0%) |
| sng-sock | - | 1.306e+04 | 5% | 87% | 18136 | _copy_to_iter 47%, kernel_init_pages 17% | no |
| sng-sockpair | - | 1.629e+06 | 12% | 99% | 819374 | apparmor_socket_post_create 18%, apparmor_sk_free_security 12% | lock 12% |
| sng-udp | - | 1.014e+07 | 4% | 99% | 9660520 | __ip_select_ident 5%, pvclock_clocksource_read_nowd 3% | no |
| sng-epoll | - | 1.137e+06 | 16% | 97% | 339709 | osq_lock 11%, apparmor_sk_free_security 10% | lock 16% |
| sng-eventfd | - | 3.258e+06 | 6% | 99% | 4941092 | pvclock_clocksource_read_nowd 3%, __schedule 3% | no |
| sng-switch | - | 1.972e+07 | 4% | 99% | 20481169 | switch_mm_irqs_off 6%, pvclock_clocksource_read_nowd 6% | no |
| sng-vm | - | 1.742e+06 | 1% | 93% | 553 | stress_vm_rowhammer.arch_sapphirerapids 38%, stress_vm_walking_flush_data.arch_sapphirerapids 23% | no |
| sng-mmap | - | 4586 | 31% | 28% | 2038 | native_queued_spin_lock_slowpath 29%, __refill_objects_node 4% | lock 31%; sleep (busy 28%) |
| sng-mmapfork | - | 127.8 | 54% | 1% | 16366 | native_queued_spin_lock_slowpath 51%, __free_one_page 7% | lock 54%; sleep (busy 1%) |
| sng-mremap | - | 6335 | 70% | 79% | 662 | native_queued_spin_lock_slowpath 67%, stress_mmap_check 10% | lock 70% |
| sng-mprotect | - | 1.616e+07 | 1% | 73% | 12802 | inc_rlimit_get_ucounts 8%, dec_rlimit_put_ucounts 8% | sleep (busy 73%) |
| sng-madvise | - | 56.64 | 1% | 94% | 393422 | memcpy 9%, mangle_path 7% | no |
| sng-brk | - | 2.396e+06 | 4% | 0% | 4499 | lapic_next_deadline 7%, asm_sysvec_apic_timer_interrupt 7% | sleep (busy 0%) |
| sng-vma | - | 6.456e+04 | 8% | 0% | 14444 | _raw_spin_lock_irqsave 8%, update_sd_lb_stats.constprop.0 8% | sleep (busy 0%) |
| sng-flock | - | 1.007e+06 | 71% | 92% | 564726 | native_queued_spin_lock_slowpath 68%, flock_lock_inode 1% | lock 71% |
| sng-fcntl | - | 8.507e+04 | 91% | 91% | 221732 | native_queued_spin_lock_slowpath 91%, _raw_spin_lock 1% | lock 91% |
| sng-lockf | - | 2.023e+06 | 1% | 99% | 5371 | posix_lock_inode 94%, do_syscall_64 1% | no |
| sng-lockofd | - | 1.137e+07 | 26% | 98% | 7431 | posix_lock_inode 57%, native_queued_spin_lock_slowpath 22% | lock 26% |
| sng-tmpfs | - | 1241 | 10% | 87% | 3112 | native_queued_spin_lock_slowpath 10%, asm_exc_page_fault 9% | lock 10% |
| vms-anon-w-rand-mt | - | 3.015e+06 | 0% | 31% | 284 | nrand48_r 62%, lrand48_r 23% | sleep (busy 31%) |
| vms-anon-r-rand-mt | - | 8.679e+07 | 6% | 100% | 220 | asm_exc_page_fault 35%, sync_regs 17% | no |
| vms-anon-cow-rand-mt | - | 9.967e+06 | 1% | 99% | 244 | smp_call_function_many_cond 84%, llist_reverse_order 3% | no |
| vms-anon-wx-rand-mt | - | 1.006e+07 | 8% | 0% | 296 | lapic_next_deadline 8%, __raise_softirq_irqoff 5% | sleep (busy 0%) |
| vms-small-allocs-mt | - | 0 | 79% | 91% | 36758 | osq_lock 77%, __raw_callee_save___kvm_vcpu_is_preempted 12% | no value |
| vms-anon-w-rand | - | 3.46e+06 | 2% | 26% | 392 | nrand48_r 57%, lrand48_r 21% | sleep (busy 26%) |
| vms-small-allocs | - | 1.869e+07 | 72% | 94% | 50378 | osq_lock 70%, __raw_callee_save___kvm_vcpu_is_preempted 11% | lock 72% |
| hb-pipe-process | - | 1.479 | 6% | 0% | 145 | lapic_next_deadline 6%, __intel_pmu_enable_all.isra.0 6% | sleep (busy 0%) |
| hb-pipe-threads | - | 1.502 | 1% | 0% | 139 | idle_cpu 10%, __sysvec_apic_timer_interrupt 6% | sleep (busy 0%) |
| hb-socket-process | - | 0.9124 | 5% | 0% | 419273 | unmap_page_range 8%, pv_native_safe_halt 5% | sleep (busy 0%) |
| hb-socket-threads | - | 0.9337 | 7% | 0% | 123642 | pvclock_clocksource_read_nowd 7%, pick_task_fair 4% | sleep (busy 0%) |
| pbf-hash | - | 2.32e+06 | 17% | 99% | 270 | futex_hash 24%, native_queued_spin_lock_slowpath 14% | lock 17% |
| pbf-lock-pi | - | 203 | 6% | 19% | 28741 | lapic_next_deadline 10%, pv_native_safe_halt 6% | sleep (busy 19%) |
| pbf-hash-shared | - | 2.167e+06 | 2% | 99% | 188 | futex_hash 18%, gup_fast_fallback 9% | no |
| pbf-wakepar | - | 204.1 | 1% | 0% | 2662 | tick_irq_enter 9%, __intel_pmu_enable_all.isra.0 8% | sleep (busy 0%) |
| pbms-thread | - | 2.74 | 4% | 0% | 142 | next_uptodate_folio 5%, asm_sysvec_apic_timer_interrupt 5% | sleep (busy 0%) |
| ebizzy | - | 4.224e+06 | 0% | 93% | 201 | 0x00000000001b0dd2 98%, 0x00000000001b0dd4 0% | no |
| tlbflush | - | 9.808e+05 | 0% | 5% | 518364 | accessmm 87%, lapic_next_deadline 1% | sleep (busy 5%) |
| aim7-creat-clo | - | 4.221e+05 | 2% | 0% | 203 | tick_nohz_stop_idle 5%, update_rq_clock 5% | sleep (busy 0%) |
| aim7-disk_rr | - | 1.074e+06 | 4% | 0% | 144 | pvclock_clocksource_read_nowd 5%, ktime_get 5% | sleep (busy 0%) |
| aim7-disk_rw | - | 1.004e+06 | 8% | 0% | 202 | asm_sysvec_apic_timer_interrupt 9%, _raw_spin_lock 5% | sleep (busy 0%) |
| aim7-disk_cp | - | 9.897e+05 | 7% | 0% | 260 | lapic_next_deadline 7%, asm_sysvec_apic_timer_interrupt 7% | sleep (busy 0%) |
| aim7-disk_src | - | 6.589e+05 | 2% | 0% | 213 | perf_adjust_freq_unthr_events 8%, unmap_page_range 5% | sleep (busy 0%) |
| fsmark | - | 1.325e+06 | 7% | 0% | 258 | timerqueue_add 7%, native_queued_spin_lock_slowpath 6% | sleep (busy 0%) |
| dbench | - | 2.648e+04 | 2% | 99% | 7136 | apparmor_task_kill 33%, audit_signal_info_syscall 9% | no |
| ub-execl | - | 2.615e+04 | 67% | 69% | 169 | osq_lock 64%, __raw_callee_save___kvm_vcpu_is_preempted 10% | lock 67%; sleep (busy 69%) |
| ub-spawn | - | 9.188e+04 | 24% | 73% | 188 | native_queued_spin_lock_slowpath 18%, next_uptodate_folio 12% | lock 24%; sleep (busy 73%) |
| ub-shell8 | - | 5955 | 18% | 74% | 170 | native_queued_spin_lock_slowpath 10%, 0x00000000001d4d64 4% | lock 18%; sleep (busy 74%) |
| ub-pipe | - | 1.165e+08 | 7% | 76% | 172 | entry_SYSCALL_64 13%, do_syscall_64 12% | no |
| ub-context1 | - | 1.569e+07 | 4% | 75% | 164 | switch_mm_irqs_off 5%, pvclock_clocksource_read_nowd 5% | no |
| ub-syscall | - | 7.93e+07 | 2% | 76% | 172 | entry_SYSCALL_64 23%, do_syscall_64 20% | no |
| ub-fstime | - | 3.89e+07 | 18% | 1% | 166 | native_queued_spin_lock_slowpath 13%, _raw_spin_lock 3% | lock 18%; sleep (busy 1%) |
| wis-eventfd1 | - | 1.311e+08 | 4% | 99% | 260 | entry_SYSCALL_64 14%, do_syscall_64 13% | no |
| wis-fallocate1 | - | 1.028e+06 | 98% | 99% | 434 | native_queued_spin_lock_slowpath 97%, __srcu_read_unlock 0% | lock 98% |
| wis-fallocate2 | - | 1.068e+06 | 97% | 99% | 444 | native_queued_spin_lock_slowpath 97%, __srcu_read_unlock 0% | lock 97% |
| wis-futex3 | - | 3.432e+08 | 0% | 99% | 187 | entry_SYSCALL_64 19%, do_syscall_64 17% | no |
| wis-futex4 | - | 2.173e+08 | 8% | 99% | 186 | entry_SYSCALL_64 12%, do_syscall_64 11% | no |
| wis-lock1 | - | 5.81e+06 | 98% | 99% | 268 | native_queued_spin_lock_slowpath 98%, _raw_spin_lock 0% | lock 98% |
| wis-lseek1 | - | 3.271e+08 | 4% | 99% | 202 | entry_SYSCALL_64 18%, do_syscall_64 16% | no |
| wis-malloc2 | - | 0 | 0% | 101% | 213 | testcase 100%, ktime_get_update_offsets_now 0% | no value |
| wis-open2 | - | 1.204e+06 | 98% | 99% | 290 | native_queued_spin_lock_slowpath 98%, _raw_spin_lock 0% | lock 98% |
| wis-pipe1 | - | 1.139e+08 | 7% | 99% | 200 | entry_SYSCALL_64 13%, do_syscall_64 11% | no |
| wis-poll1 | - | 2.328e+08 | 0% | 99% | 200 | do_sys_poll 22%, entry_SYSCALL_64 13% | no |
| wis-poll2 | - | 1.932e+07 | 0% | 100% | 202 | fdget 38%, fput 34% | no |
| wis-pread1 | - | 1.788e+08 | 0% | 99% | 179 | _copy_to_iter 18%, entry_SYSCALL_64 10% | no |
| wis-pread3 | - | 1.721e+08 | 0% | 99% | 198 | _copy_to_iter 18%, entry_SYSCALL_64 9% | no |
| wis-pthread_mutex2 | - | 3.254e+09 | 0% | 101% | 202 | pthread_mutex_lock 46%, pthread_mutex_unlock 44% | no |
| wis-pthread_mutex5 | - | 1.044e+07 | 98% | 99% | 87697 | native_queued_spin_lock_slowpath 97%, pthread_mutex_lock 0% | lock 98% |
| wis-pwrite1 | - | 1.674e+08 | 0% | 99% | 198 | copy_folio_from_iter_atomic 17%, entry_SYSCALL_64 9% | no |
| wis-read3 | - | 1.606e+08 | 2% | 99% | 200 | _copy_to_iter 16%, entry_SYSCALL_64 9% | no |
| wis-read4 | - | 9.861e+07 | 10% | 99% | 413443 | filemap_get_entry 19%, _copy_to_iter 10% | lock 10% |
| wis-readseek1 | - | 1.106e+08 | 3% | 99% | 180 | entry_SYSCALL_64 12%, _copy_to_iter 11% | no |
| wis-readseek3 | - | 1.072e+08 | 3% | 99% | 210 | entry_SYSCALL_64 12%, do_syscall_64 11% | no |
| wis-unix1 | - | 5.965e+07 | 5% | 100% | 202 | entry_SYSCALL_64 7%, do_syscall_64 6% | no |
| wis-unlink2 | - | 7.039e+05 | 94% | 100% | 3022 | native_queued_spin_lock_slowpath 93%, _raw_spin_lock 1% | lock 94% |
| wis-write1 | - | 1.381e+08 | 2% | 99% | 234 | copy_folio_from_iter_atomic 15%, folio_unlock 10% | no |
| wis-writeseek1 | - | 1.059e+08 | 3% | 100% | 269 | entry_SYSCALL_64 12%, copy_folio_from_iter_atomic 11% | no |
| wis-writeseek2 | - | 6.433e+05 | 85% | 86% | 32442 | osq_lock 83%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 85% |
| wisp-brk1 | - | 5.481e+07 | 47% | 100% | 8378 | native_queued_spin_lock_slowpath 47%, __refill_objects_node 3% | lock 47% |
| wisp-brk2 | - | 5.213e+07 | 37% | 100% | 7987 | native_queued_spin_lock_slowpath 36%, __refill_objects_node 3% | lock 37% |
| wisp-context_switch1 | - | 3.551e+07 | 4% | 99% | 17687820 | switch_mm_irqs_off 6%, pvclock_clocksource_read_nowd 5% | no |
| wisp-dup1 | - | 1.803e+08 | 5% | 100% | 205 | entry_SYSCALL_64 20%, do_syscall_64 17% | no |
| wisp-eventfd1 | - | 1.427e+08 | 5% | 99% | 201 | entry_SYSCALL_64 16%, do_syscall_64 14% | no |
| wisp-fallocate1 | - | 1.024e+06 | 97% | 99% | 452 | native_queued_spin_lock_slowpath 97%, __srcu_read_unlock 0% | lock 97% |
| wisp-fallocate2 | - | 1.088e+06 | 97% | 100% | 477 | native_queued_spin_lock_slowpath 97%, __srcu_read_unlock 0% | lock 97% |
| wisp-futex2 | - | 2.018e+08 | 3% | 100% | 201 | gup_fast_fallback 13%, entry_SYSCALL_64 11% | no |
| wisp-futex3 | - | 3.395e+08 | 0% | 100% | 195 | entry_SYSCALL_64 19%, do_syscall_64 17% | no |
| wisp-futex4 | - | 2.452e+08 | 3% | 99% | 203 | entry_SYSCALL_64 14%, do_syscall_64 12% | no |
| wisp-getppid1 | - | 4.061e+08 | 0% | 100% | 200 | entry_SYSCALL_64 23%, do_syscall_64 20% | no |
| wisp-lock1 | - | 1.795e+08 | 7% | 100% | 202 | kmem_cache_alloc_noprof 11%, entry_SYSCALL_64 10% | no |
| wisp-lseek1 | - | 3.965e+08 | 0% | 100% | 200 | entry_SYSCALL_64 22%, do_syscall_64 20% | no |
| wisp-lseek2 | - | 3.939e+08 | 0% | 99% | 228 | entry_SYSCALL_64 23%, do_syscall_64 20% | no |
| wisp-malloc1 | - | 0 | 0% | 102% | 210 | testcase 89%, testcase 10% | no value |
| wisp-malloc2 | - | 0 | 0% | 101% | 206 | testcase 99%, get_jiffies_update 0% | no value |
| wisp-mmap1 | - | 2.338e+06 | 93% | 99% | 1474 | native_queued_spin_lock_slowpath 93%, percpu_counter_add_batch 1% | lock 93% |
| wisp-mmap2 | - | 2.464e+06 | 91% | 99% | 1353 | native_queued_spin_lock_slowpath 91%, percpu_counter_add_batch 1% | lock 91% |
| wisp-open2 | - | 9.035e+06 | 0% | 99% | 266 | apparmor_file_free_security 42%, apparmor_file_alloc_security 42% | no |
| wisp-page_fault1 | - | 7.072e+06 | 48% | 100% | 430 | native_queued_spin_lock_slowpath 25%, _raw_spin_lock 23% | lock 48% |
| wisp-page_fault2 | - | 3.904e+06 | 27% | 89% | 300 | native_queued_spin_lock_slowpath 27%, copy_mc_enhanced_fast_string 24% | lock 27% |
| wisp-page_fault3 | - | 5.883e+07 | 1% | 100% | 446 | asm_exc_page_fault 38%, sync_regs 13% | no |
| wisp-pipe1 | - | 1.228e+08 | 7% | 99% | 186 | entry_SYSCALL_64 14%, do_syscall_64 12% | no |
| wisp-poll1 | - | 2.534e+08 | 0% | 100% | 206 | do_sys_poll 24%, entry_SYSCALL_64 14% | no |
| wisp-poll2 | - | 6.519e+07 | 0% | 100% | 202 | do_sys_poll 37%, fdget 22% | no |
| wisp-pread1 | - | 1.966e+08 | 0% | 99% | 215 | _copy_to_iter 17%, entry_SYSCALL_64 11% | no |
| wisp-pread2 | - | 1.554e+06 | 96% | 99% | 101487 | native_queued_spin_lock_slowpath 96%, shmem_file_read_iter 1% | lock 96% |
| wisp-pread3 | - | 1.907e+08 | 0% | 99% | 201 | _copy_to_iter 16%, entry_SYSCALL_64 10% | no |
| wisp-pthread_mutex1 | - | 9.16e+09 | 0% | 101% | 212 | pthread_mutex_lock 38%, pthread_mutex_unlock 32% | no |
| wisp-pthread_mutex2 | - | 9.238e+09 | 0% | 101% | 238 | testcase 33%, pthread_mutex_lock 28% | no |
| wisp-pthread_mutex3 | - | 9.209e+09 | 0% | 101% | 204 | pthread_mutex_lock 38%, pthread_mutex_unlock 27% | no |
| wisp-pthread_mutex4 | - | 8.75e+09 | 0% | 101% | 210 | pthread_mutex_lock 44%, pthread_mutex_unlock 24% | no |
| wisp-pthread_mutex5 | - | 9.303e+09 | 0% | 101% | 210 | pthread_mutex_lock 33%, testcase 28% | no |
| wisp-pwrite1 | - | 1.735e+08 | 0% | 100% | 205 | copy_folio_from_iter_atomic 18%, entry_SYSCALL_64 10% | no |
| wisp-read1 | - | 1.613e+08 | 0% | 99% | 220 | _copy_to_iter 25%, entry_SYSCALL_64 9% | no |
| wisp-read2 | - | 8.925e+07 | 10% | 99% | 574170 | filemap_get_entry 19%, _copy_to_iter 15% | no |
| wisp-read3 | - | 1.785e+08 | 0% | 100% | 267 | _copy_to_iter 18%, entry_SYSCALL_64 10% | no |
| wisp-read4 | - | 1.058e+08 | 8% | 99% | 435457 | filemap_get_entry 20%, _copy_to_iter 10% | no |
| wisp-readseek1 | - | 1.285e+08 | 0% | 99% | 272 | entry_SYSCALL_64 14%, do_syscall_64 13% | no |
| wisp-readseek2 | - | 1.55e+06 | 96% | 99% | 98444 | native_queued_spin_lock_slowpath 95%, filemap_get_entry 1% | lock 96% |
| wisp-readseek3 | - | 1.248e+08 | 0% | 99% | 267 | entry_SYSCALL_64 14%, _copy_to_iter 13% | no |
| wisp-sched_yield | - | 1.894e+08 | 5% | 99% | 264 | entry_SYSCALL_64 10%, do_syscall_64 9% | no |
| wisp-signal1 | - | 8.746e+06 | 1% | 99% | 209 | inc_rlimit_get_ucounts 25%, dec_rlimit_put_ucounts 23% | no |
| wisp-tlb_flush1 | - | 1.005e+07 | 18% | 100% | 260 | native_queued_spin_lock_slowpath 17%, copy_mc_enhanced_fast_string 10% | lock 18% |
| wisp-tlb_flush2 | - | 1.34e+07 | 52% | 99% | 459 | native_queued_spin_lock_slowpath 51%, asm_exc_page_fault 9% | lock 52% |
| wisp-tlb_flush3 | - | 2.077e+07 | 1% | 99% | 367 | asm_exc_page_fault 13%, next_uptodate_folio 13% | no |
| wisp-unix1 | - | 6.241e+07 | 5% | 99% | 202 | entry_SYSCALL_64 7%, do_syscall_64 6% | no |
| wisp-unlink2 | - | 7.252e+05 | 95% | 100% | 3310 | native_queued_spin_lock_slowpath 94%, _raw_spin_lock 1% | lock 95% |
| wisp-write1 | - | 1.457e+08 | 0% | 99% | 203 | copy_folio_from_iter_atomic 16%, folio_unlock 11% | no |
| wisp-writeseek1 | - | 1.203e+08 | 0% | 99% | 201 | entry_SYSCALL_64 13%, do_syscall_64 12% | no |
| wisp-writeseek2 | - | 6.315e+05 | 85% | 86% | 38100 | osq_lock 83%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 85% |
| wisp-writeseek3 | - | 1.315e+06 | 85% | 91% | 9788 | osq_lock 82%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 85% |
| sng-acct | - | 2.823e+04 | 14% | 85% | 247861 | __refill_objects_node 5%, native_queued_spin_lock_slowpath 5% | lock 14% |
| sng-affinity | - | 6.568e+05 | 4% | 0% | 1102980 | pv_native_safe_halt 4%, idle_cpu 4% | sleep (busy 0%) |
| sng-aio | - | 0 | 2% | 0% | 144 | pv_native_safe_halt 5%, __hrtimer_run_queues 4% | no value |
| sng-alarm | - | 2.061e+06 | 6% | 97% | 2648266 | pvclock_clocksource_read_nowd 5%, pv_native_safe_halt 4% | no |
| sng-bad-altstack | - | 2.15e+04 | 16% | 63% | 47995 | prb_reserve 26%, desc_read 14% | lock 16%; sleep (busy 63%) |
| sng-bigheap | - | 1.037e+05 | 7% | 0% | 20074 | idle_cpu 5%, dequeue_entities 4% | sleep (busy 0%) |
| sng-cap | - | 0 | 5% | 0% | 138 | _nohz_idle_balance.isra.0 5%, pvclock_clocksource_read_nowd 5% | no value |
| sng-chroot | - | 5.206e+04 | 15% | 97% | 118054 | folios_put_refs 11%, unmap_page_range 7% | lock 15% |
| sng-clock | - | 2.135e+05 | 77% | 98% | 500 | native_queued_spin_lock_slowpath 73%, ktime_get_update_offsets_now 9% | lock 77% |
| sng-context | - | 2.233e+05 | 0% | 99% | 266 | swapcontext 37%, entry_SYSCALL_64 13% | no |
| sng-cpu-sched | - | 4322 | 86% | 34% | 2065354 | native_queued_spin_lock_slowpath 76%, osq_lock 10% | lock 86%; sleep (busy 34%) |
| sng-daemon | - | 3.852e+04 | 0% | - | 109660 |  | no |
| sng-dev-shm | - | 127.1 | 76% | 97% | 340 | native_queued_spin_lock_slowpath 75%, copy_mc_enhanced_fast_string 5% | lock 76% |
| sng-dynlib | - | 2.841e+04 | 46% | 98% | 20434 | osq_lock 39%, __raw_callee_save___kvm_vcpu_is_preempted 6% | lock 46% |
| sng-enosys | - | 6.69e+06 | 3% | 98% | 7761486 | do_syscall_64 5%, entry_SYSCALL_64 5% | no |
| sng-env | - | 5056 | 36% | 29% | 1118 | native_queued_spin_lock_slowpath 23%, asm_exc_page_fault 17% | lock 36%; sleep (busy 29%) |
| sng-fault | - | 6.425e+05 | 76% | 99% | 7446 | native_queued_spin_lock_slowpath 74%, asm_exc_page_fault 1% | lock 76% |
| sng-fd-abuse | - | 4.651e+07 | 80% | 97% | 15046 | native_queued_spin_lock_slowpath 79%, entry_SYSCALL_64 2% | lock 80% |
| sng-fd-fork | - | 7259 | 3% | 82% | 17748 | fput_close 37%, filp_flush 26% | no |
| sng-fd-race | - | 9.799e+05 | 12% | 81% | 28256 | entry_SYSCALL_64 12%, native_queued_spin_lock_slowpath 11% | lock 12% |
| sng-fifo | - | 1.557e+07 | 4% | 99% | 13609142 | pvclock_clocksource_read_nowd 6%, switch_mm_irqs_off 4% | no |
| sng-filehole | - | 5.06e+06 | 74% | 99% | 2078 | native_queued_spin_lock_slowpath 73%, stress_filehole_io 3% | lock 74% |
| sng-full | - | 2.202e+06 | 90% | 99% | 671 | native_queued_spin_lock_slowpath 89%, lockref_put_return 2% | lock 90% |
| sng-forkheavy | - | 218.8 | 26% | 4% | 3236 | native_queued_spin_lock_slowpath 14%, mas_next_slot 8% | lock 26%; sleep (busy 4%) |
| sng-get | - | 1.338e+06 | 4% | 59% | 43998 | __do_sys_getpriority 9%, entry_SYSCALL_64 3% | sleep (busy 59%) |
| sng-getrandom | - | 3.607e+06 | 0% | 99% | 196 | 0x0000000000001708 5%, 0x00000000000016ba 5% | no |
| sng-hrtimers | - | 3.963e+06 | 5% | 0% | 1614066 | __queue_work 6%, 0x000000000054e5c5 5% | sleep (busy 0%) |
| sng-io-uring | - | 8.054e+06 | 30% | 99% | 7795109 | native_queued_spin_lock_slowpath 26%, pvclock_clocksource_read_nowd 3% | lock 30% |
| sng-itimer | - | 6.376e+04 | 11% | 99% | 264 | entry_SYSCALL_64 18%, clear_bhb_loop 15% | lock 11% |
| sng-kcmp | - | 4.781e+06 | 7% | 99% | 202 | entry_SYSCALL_64 10%, __do_sys_kcmp 10% | no |
| sng-key | - | 0 | 4% | 0% | 148 | update_rq_clock 10%, asm_sysvec_apic_timer_interrupt 9% | no value |
| sng-landlock | - | 740.5 | 64% | 96% | 116945 | native_queued_spin_lock_slowpath 61%, lockref_get_not_dead 2% | lock 64% |
| sng-lockmix | - | 1.072e+06 | 6% | 66% | 25075 | posix_lock_inode 74%, native_queued_spin_lock_slowpath 4% | sleep (busy 66%) |
| sng-malloc | - | 6.253e+07 | 0% | 87% | 276 | stress_atomic_lock_acquire 52%, stress_lock_acquire 35% | no |
| sng-mcontend | - | 1.843e+04 | 0% | 87% | 16488 | stress_memory_contend.isra.0 97%, shim_clflush_op 2% | no |
| sng-membarrier | - | 2057 | 83% | 92% | 18985 | osq_lock 82%, __raw_callee_save___kvm_vcpu_is_preempted 13% | lock 83% |
| sng-memfd | - | 3217 | 65% | 94% | 4924 | native_queued_spin_lock_slowpath 64%, shmem_add_to_page_cache 4% | lock 65% |
| sng-mincore | - | 1.137e+05 | 1% | 99% | 198 | asm_exc_page_fault 13%, entry_SYSCALL_64 7% | no |
| sng-min-nanosleep | - | 1815 | 2% | 87% | 615974 | lapic_next_deadline 13%, pv_native_safe_halt 8% | no |
| sng-mlock | - | 1.199e+05 | 68% | 1% | 720 | native_queued_spin_lock_slowpath 67%, folio_remove_rmap_ptes 2% | lock 68%; sleep (busy 1%) |
| sng-mlockmany | - | 0 | 4% | 0% | 142 | pvclock_clocksource_read_nowd 6%, update_sd_lb_stats.constprop.0 5% | no value |
| sng-mmapaddr | - | 1.038e+06 | 20% | 93% | 10978 | down_read 12%, native_queued_spin_lock_slowpath 11% | lock 20% |
| sng-mmapfiles | - | 1.276e+06 | 4% | 0% | 214023 | unlink_file_vma_batch_final 8%, __vma_start_exclude_readers 8% | sleep (busy 0%) |
| sng-mmapfixed | - | 1.049e+05 | 11% | 95% | 13472 | down_read 13%, free_pgd_range 13% | lock 11% |
| sng-mmaprandom | - | 0 | 4% | 0% | 142 | update_vsyscall 7%, update_sd_lb_stats.constprop.0 6% | no value |
| sng-mmaptorture | - | 177.1 | 20% | 26% | 89218 | native_queued_spin_lock_slowpath 5%, rwsem_spin_on_owner 4% | lock 20%; sleep (busy 26%) |
| sng-mseal | - | 1.577e+07 | 0% | 99% | 206 | entry_SYSCALL_64 13%, do_syscall_64 11% | no |
| sng-msync | - | 1.909e+06 | 89% | 100% | 1420 | native_queued_spin_lock_slowpath 88%, entry_SYSCALL_64 1% | lock 89% |
| sng-msyncmany | - | 2.782e+05 | 1% | 38% | 209 | stress_msyncmany_child 88%, native_queued_spin_lock_slowpath 1% | sleep (busy 38%) |
| sng-mtx | - | 2.796e+09 | 0% | 76% | 28552 | pthread_mutex_unlock 44%, pthread_mutex_lock 39% | no |
| sng-munmap | - | 3.762e+05 | 82% | 94% | 50449 | osq_lock 80%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 82% |
| sng-mutex | - | 7.881e+05 | 5% | 0% | 482337 | asm_sysvec_apic_timer_interrupt 4%, idle_cpu 4% | sleep (busy 0%) |
| sng-loadavg | - | 6.851e+06 | 0% | - | - |  | no |
| sng-mmapmany | - | 6.148e+05 | 65% | 11% | 7806 | native_queued_spin_lock_slowpath 64%, page_counter_uncharge 2% | lock 65%; sleep (busy 11%) |
| sng-mmapcow | - | 3.908e+06 | 19% | 42% | 1542 | native_queued_spin_lock_slowpath 19%, shmem_add_to_page_cache 18% | lock 19%; sleep (busy 42%) |
| sng-nanosleep | - | 4.017e+05 | 2% | 98% | 5632178 | pvclock_clocksource_read_nowd 5%, __schedule 5% | no |
| sng-netlink-proc | - | 6927 | 19% | 98% | 86759 | netlink_broadcast_filtered 12%, osq_lock 11% | lock 19% |
| sng-netlink-task | - | 5.479e+05 | 85% | 91% | 4597 | osq_lock 83%, __raw_callee_save___kvm_vcpu_is_preempted 13% | lock 85% |
| sng-nice | - | 7732 | 5% | 99% | 482 | entry_SYSCALL_64 9%, clear_bhb_loop 8% | no |
| sng-pthread | - | 2.3e+05 | 28% | 58% | 690748 | native_queued_spin_lock_slowpath 22%, _raw_spin_lock 3% | lock 28%; sleep (busy 58%) |
| sng-poll | - | 4.261e+06 | 5% | 93% | 1076522 | entry_SYSCALL_64 7%, do_syscall_64 6% | no |
| sng-prio-inv | - | 1.053e+07 | 8% | 99% | 5201294 | entry_SYSCALL_64 6%, pvclock_clocksource_read_nowd 6% | no |
| sng-race-sched | - | 3995 | 19% | 32% | 109578 | native_queued_spin_lock_slowpath 11%, _raw_spin_lock_irqsave 6% | lock 19%; sleep (busy 32%) |
| sng-schedmix | - | 4.522e+04 | 2% | 91% | 9964296 | stress_schedmix 7%, lapic_next_deadline 6% | no |
| sng-schedpolicy | - | 5.125e+05 | 81% | 89% | 5723 | osq_lock 79%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 81% |
| sng-seal | - | 8.046e+05 | 88% | 100% | 5784 | native_queued_spin_lock_slowpath 88%, do_syscall_64 0% | lock 88% |
| sng-seccomp | - | 8595 | 47% | 90% | 44130 | osq_lock 43%, do_jit 13% | lock 47% |
| sng-secretmem | - | 9.646e+04 | 53% | 95% | 430 | native_queued_spin_lock_slowpath 53%, smp_call_function_many_cond 33% | lock 53% |
| sng-seek | - | 6.362e+05 | 0% | 93% | 296 | mapping_seek_hole_data 73%, xas_find 14% | no |
| sng-sendfile | - | 8.995e+05 | 0% | 99% | 220 | shmem_get_folio_gfp 36%, filemap_get_entry 23% | no |
| sng-session | - | 1.801e+04 | 38% | 97% | 82219 | native_queued_spin_lock_slowpath 15%, osq_lock 13% | lock 38% |
| sng-set | - | 1.341e+05 | 10% | 81% | 103578 | refcount_dec_and_lock_irqsave 32%, prepare_creds 7% | no |
| sng-sigabrt | - | 2.099e+04 | 15% | 94% | 49770 | prb_reserve 27%, desc_read 15% | lock 15% |
| sng-sigbus | - | 8.747e+06 | 1% | 99% | 186 | inc_rlimit_get_ucounts 32%, dec_rlimit_put_ucounts 31% | no |
| sng-sigchld | - | 6.799e+04 | 36% | 96% | 153532 | osq_lock 24%, native_queued_spin_lock_slowpath 4% | lock 36% |
| sng-sigfd | - | 8.381e+06 | 2% | 89% | 4385288 | apparmor_task_kill 34%, inc_rlimit_get_ucounts 13% | no |
| sng-sigfpe | - | 8.759e+06 | 1% | 99% | 180 | inc_rlimit_get_ucounts 28%, dec_rlimit_put_ucounts 27% | no |
| sng-sighup | - | 3.645e+04 | 23% | 96% | 188349 | osq_lock 13%, folios_put_refs 5% | lock 23% |
| sng-sigill | - | 8.694e+06 | 1% | 99% | 250 | inc_rlimit_get_ucounts 28%, dec_rlimit_put_ucounts 26% | no |
| sng-sigio | - | 1.796e+07 | 6% | 99% | 18358188 | switch_mm_irqs_off 6%, pvclock_clocksource_read_nowd 5% | no |
| sng-signest | - | 8.657e+06 | 1% | 98% | 188 | apparmor_task_kill 25%, inc_rlimit_get_ucounts 24% | no |
| sng-sigpending | - | 8.607e+06 | 1% | 99% | 187 | inc_rlimit_get_ucounts 18%, dec_rlimit_put_ucounts 17% | no |
| sng-sigpipe | - | 8.766e+06 | 1% | 99% | 182 | inc_rlimit_get_ucounts 39%, dec_rlimit_put_ucounts 38% | no |
| sng-sigrt | - | 4.381e+06 | 1% | 82% | 2996788 | apparmor_task_kill 23%, inc_rlimit_get_ucounts 14% | no |
| sng-sigsegv | - | 8.751e+06 | 1% | 99% | 204 | inc_rlimit_get_ucounts 32%, dec_rlimit_put_ucounts 30% | no |
| sng-sigstop | - | 2.605e+06 | 84% | 99% | 2784776 | native_queued_spin_lock_slowpath 83%, inc_rlimit_get_ucounts 1% | lock 84% |
| sng-sigsuspend | - | 6.765e+06 | 1% | 99% | 6426659 | apparmor_task_kill 27%, stress_lock_acquire 4% | no |
| sng-sigtrap | - | 8.759e+06 | 1% | 99% | 184 | inc_rlimit_get_ucounts 35%, dec_rlimit_put_ucounts 34% | no |
| sng-sigurg | - | 1.667e+06 | 5% | 90% | 7356 | entry_SYSCALL_64 10%, do_syscall_64 10% | no |
| sng-sigvtalrm | - | 6.383e+04 | 5% | 99% | 192 | entry_SYSCALL_64 19%, do_syscall_64 17% | no |
| sng-sigxcpu | - | 6.209e+04 | 10% | 99% | 531116 | entry_SYSCALL_64 12%, clear_bhb_loop 11% | no |
| sng-sigxfsz | - | 8.763e+06 | 1% | 99% | 182 | inc_rlimit_get_ucounts 37%, dec_rlimit_put_ucounts 36% | no |
| sng-sleep | - | 6.084e+05 | 4% | 33% | 7334652 | stress_atomic_lock_acquire_relax 6%, switch_mm_irqs_off 5% | sleep (busy 33%) |
| sng-sockabuse | - | 3241 | 5% | 66% | 133702 | entry_SYSCALL_64 3%, do_syscall_64 3% | sleep (busy 66%) |
| sng-sockdiag | - | 8.461e+07 | 91% | 99% | 9230 | native_queued_spin_lock_slowpath 70%, _raw_spin_lock 20% | lock 91% |
| sng-sockfd | - | 1.006e+06 | 94% | 100% | 379281 | native_queued_spin_lock_slowpath 94%, _raw_spin_lock 1% | lock 94% |
| sng-sockmany | - | 7.246e+04 | 47% | 101% | 14994 | __inet_check_established 38%, native_queued_spin_lock_slowpath 25% | lock 47% |
| sng-splice | - | 2.121e+07 | 3% | 99% | 280 | entry_SYSCALL_64 15%, do_syscall_64 14% | no |
| sng-stack | - | 8.758e+06 | 1% | 98% | 198 | inc_rlimit_get_ucounts 30%, dec_rlimit_put_ucounts 28% | no |
| sng-stackmmap | - | 2.207e+04 | 1% | 98% | 47203 | stress_stackmmap_push_msync 80%, asm_exc_page_fault 1% | no |
| sng-statmount | - | 7.484e+04 | 0% | 95% | 256 | lockref_get 42%, lockref_put_return 40% | no |
| sng-syncload | - | 342.5 | 0% | 67% | 632 | 0x000000000000087b 27%, stress_time_now_timespec 7% | sleep (busy 67%) |
| sng-sysbadaddr | - | 6.685e+04 | 10% | 67% | 44618 | unmap_page_range 4%, anon_vma_interval_tree_insert 4% | sleep (busy 67%) |
| sng-syscall | - | 5243 | 8% | 0% | 145 | ktime_get 5%, smp_call_function_many_cond 5% | sleep (busy 0%) |
| sng-sysfs | - | 1464 | 10% | 87% | 136684 | __refill_objects_node 5%, copy_page_range 5% | lock 10% |
| sng-sysinfo | - | 9757 | 73% | 87% | 92174 | native_queued_spin_lock_slowpath 71%, down_read 2% | lock 73% |
| sng-tee | - | 4.79e+05 | 4% | 99% | 660106 | entry_SYSCALL_64 14%, clear_bhb_loop 12% | no |
| sng-timer | - | 1.049e+07 | 4% | 99% | 202 | lapic_next_deadline 20%, asm_sysvec_apic_timer_interrupt 8% | no |
| sng-timerfd | - | 1.315e+07 | 4% | 99% | 358 | lapic_next_deadline 30%, asm_sysvec_apic_timer_interrupt 12% | no |
| sng-timermix | - | 1.062e+07 | 4% | 98% | 915298 | lapic_next_deadline 20%, asm_sysvec_apic_timer_interrupt 8% | no |
| sng-tlb-shootdown | - | 2.553e+05 | 1% | 0% | 10378 | stress_tlb_shootdown_child 40%, unmap_page_range 10% | sleep (busy 0%) |
| sng-umask | - | 610.4 | 95% | 92% | 580 | native_queued_spin_lock_slowpath 94%, __percpu_counter_sum 1% | lock 95% |
| sng-unshare | - | 191.3 | 28% | 64% | 44090 | wait_consider_task 28%, native_queued_spin_lock_slowpath 22% | lock 28%; sleep (busy 64%) |
| sng-urandom | - | 1.756e+06 | 1% | 98% | 682 | chacha_permute 47%, _copy_to_iter 10% | no |
| sng-userfaultfd | - | 1.994e+06 | 1% | 90% | 2090070 | stress_atomic_lock_acquire_relax 72%, asm_exc_page_fault 1% | no |
| sng-usersyscall | - | 4.373e+06 | 1% | 98% | 203 | inc_rlimit_get_ucounts 35%, dec_rlimit_put_ucounts 33% | no |
| sng-vdso | - | 3.937e+09 | 0% | 90% | 224 | 0x000000000000087b 56%, __vdso_gettimeofday 9% | no |
| sng-vforkmany | - | 3.593e+05 | 78% | 66% | 426680 | native_queued_spin_lock_slowpath 74%, sched_balance_find_dst_group 1% | lock 78%; sleep (busy 66%) |
| sng-vm-addr | - | 198.4 | 0% | 82% | 444 | stress_vm_addr_revinv.arch_sapphirerapids 55%, stress_vm_addr_rev.arch_sapphirerapids 43% | no |
| sng-vm-rw | - | 2.048e+06 | 4% | 99% | 2108722 | _copy_to_iter 24%, _copy_from_iter 24% | no |
| sng-vm-segv | - | 2.158e+04 | 14% | 71% | 77566 | prb_reserve 26%, desc_read 14% | lock 14%; sleep (busy 71%) |
| sng-vm-splice | - | 5.05e+07 | 4% | 99% | 242 | entry_SYSCALL_64 11%, do_syscall_64 10% | no |
| sng-waitcpu | - | 3952 | 0% | 87% | 198 | stress_waitcpu_x86_tpause0 50%, stress_waitcpu_x86_tpause1 49% | no |
| sng-x86syscall | - | 3.773e+08 | 0% | 99% | 236 | entry_SYSCALL_64 22%, do_syscall_64 19% | no |
| sng-zero | - | 2.494e+08 | 0% | 99% | 633 | read_zero 20%, entry_SYSCALL_64 14% | no |
| sng-access | - | 5.009e+05 | 0% | 99% | 2332594 | __d_lookup_rcu 9%, entry_SYSCALL_64 7% | no |
| sng-acl | - | 0 | 5% | 0% | 130 | lapic_next_deadline 10%, 0x000000000002c639 6% | no value |
| sng-aiol | - | 0 | 0% | 0% | 210 | unmap_page_range 9%, proc_misc_d_revalidate 7% | no value |
| sng-chdir | - | 247.6 | 3% | 100% | 498 | lockref_put_return 43%, lockref_get_not_dead 26% | no |
| sng-chmod | - | 5686 | 85% | 90% | 12931 | osq_lock 82%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 85% |
| sng-chown | - | 9.133e+04 | 85% | 90% | 17080 | osq_lock 82%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 85% |
| sng-copy-file | - | 5.878e+04 | 67% | 81% | 536 | native_queued_spin_lock_slowpath 66%, folio_unlock 20% | lock 67% |
| sng-dentrycache | - | 5.958e+06 | 1% | 90% | 592 | lockref_get_not_dead 46%, lockref_put_return 38% | no |
| sng-dirdeep | - | 1.837e+04 | 94% | 94% | 55748 | native_queued_spin_lock_slowpath 93%, __d_lookup_rcu 3% | lock 94% |
| sng-dirmany | - | 8.167e+05 | 92% | 100% | 414 | native_queued_spin_lock_slowpath 91%, _raw_spin_lock 1% | lock 92% |
| sng-dnotify | - | 5.037e+04 | 79% | 95% | 11576 | osq_lock 76%, __raw_callee_save___kvm_vcpu_is_preempted 12% | lock 79% |
| sng-fiemap | - | 0 | 12% | 0% | 206 | collect_percpu_times 11%, update_sd_lb_stats.constprop.0 8% | no value |
| sng-file-ioctl | - | 5.368e+04 | 81% | 91% | 475 | native_queued_spin_lock_slowpath 80%, shmem_get_folio_gfp 4% | lock 81% |
| sng-filename | - | 7.855e+04 | 77% | 97% | 6788 | native_queued_spin_lock_slowpath 75%, lockref_put_return 4% | lock 77% |
| sng-fpunch | - | 1.221e+06 | 64% | 81% | 19993 | native_queued_spin_lock_slowpath 43%, rwsem_spin_on_owner 16% | lock 64% |
| sng-fsize | - | 2.079e+05 | 88% | 93% | 478 | native_queued_spin_lock_slowpath 87%, shmem_add_to_page_cache 1% | lock 88% |
| sng-fstat | - | 10.66 | 98% | 100% | 21440 | native_queued_spin_lock_slowpath 98%, _copy_to_user 0% | lock 98% |
| sng-handle | - | 1.655e+05 | 98% | 91% | 260 | native_queued_spin_lock_slowpath 98%, _raw_spin_lock 0% | lock 98% |
| sng-inode-flags | - | 8.179e+05 | 9% | 88% | 11344 | apparmor_capable 19%, entry_SYSCALL_64 8% | no |
| sng-io | - | 1.142e+04 | 96% | 90% | 109838 | native_queued_spin_lock_slowpath 96%, down_read 0% | lock 96% |
| sng-iomix | - | 3.969e+06 | 1% | 94% | 134439 | apparmor_capable 39%, entry_SYSCALL_64 9% | no |
| sng-ioprio | - | 2.757e+05 | 77% | 84% | 284 | native_queued_spin_lock_slowpath 58%, _raw_spin_lock 19% | lock 77% |
| sng-lease | - | 1.001e+06 | 3% | 100% | 75186 | apparmor_file_free_security 38%, apparmor_file_alloc_security 38% | no |
| sng-locka | - | 4.704e+06 | 25% | 94% | 8227 | posix_lock_inode 64%, native_queued_spin_lock_slowpath 22% | lock 25% |
| sng-metamix | - | 2.276e+05 | 5% | 0% | 17328 | asm_sysvec_apic_timer_interrupt 9%, collect_percpu_times 6% | sleep (busy 0%) |
| sng-mknod | - | 3.702e+04 | 97% | 94% | 52566 | native_queued_spin_lock_slowpath 97%, down_read 0% | lock 97% |
| sng-procfs | - | 3055 | 64% | 63% | 153982 | native_queued_spin_lock_slowpath 62%, proc_reg_read_iter 8% | lock 64%; sleep (busy 63%) |
| sng-sync-file | - | 748.5 | 29% | 54% | 462 | shmem_add_to_page_cache 40%, native_queued_spin_lock_slowpath 28% | lock 29%; sleep (busy 54%) |
| sng-utime | - | 9.661e+05 | 0% | 99% | 184 | ktime_get_coarse_real_ts64_mg 9%, __d_lookup_rcu 7% | no |
| sng-xattr | - | 53.35 | 96% | 92% | 312 | native_queued_spin_lock_slowpath 96%, strcmp 0% | lock 96% |
| sng-chattr | - | 6184 | 71% | 88% | 137070 | osq_lock 39%, native_queued_spin_lock_slowpath 26% | lock 71% |
| sng-fanotify | - | 0 | 6% | 0% | 240 | asm_sysvec_apic_timer_interrupt 9%, refresh_cpu_vm_stats 8% | no value |
| sng-touch | - | 3.172e+05 | 95% | 50% | 11442 | native_queued_spin_lock_slowpath 95%, __percpu_counter_sum 1% | lock 95%; sleep (busy 50%) |
| sng-hdd | - | 5.73e+05 | 2% | 70% | 462 | _copy_to_iter 25%, shmem_add_to_page_cache 23% | sleep (busy 70%) |
| sng-fallocate | - | 654.1 | 5% | 62% | 462 | shmem_add_to_page_cache 30%, shmem_get_folio_gfp 22% | sleep (busy 62%) |
| sng-epollmany | - | 1.378e+04 | 85% | 95% | 4067 | osq_lock 83%, __raw_callee_save___kvm_vcpu_is_preempted 13% | lock 85% |
| sng-icmp-flood | - | 1.794e+07 | 3% | 99% | 10726 | icmp_out_count 46%, raw_sendmsg 3% | no |
| sng-ping-sock | - | 9.072e+06 | 1% | 99% | 186 | __ip_select_ident 44%, icmp_out_count 11% | no |
| sng-rawpkt | - | 9.156e+04 | 50% | 91% | 6554 | native_queued_spin_lock_slowpath 49%, packet_rcv 36% | lock 50% |
| sng-rawsock | - | 1.099e+07 | 55% | 90% | 9160 | native_queued_spin_lock_slowpath 51%, raw_local_deliver 19% | lock 55% |
| sng-rawudp | - | 7.926e+04 | 62% | 87% | 101410 | native_queued_spin_lock_slowpath 58%, sock_rfree 5% | lock 62% |
| sng-udp-flood | - | 1.391e+07 | 3% | 98% | 411 | icmp_out_count 12%, __ip_select_ident 11% | no |
| sng-pagemove | - | 3.997e+05 | 3% | 96% | 4880 | native_flush_tlb_one_user 7%, mas_walk 5% | no |
| sng-physpage | - | 1.104e+06 | 59% | 96% | 7762 | osq_lock 49%, __raw_callee_save___kvm_vcpu_is_preempted 7% | lock 59% |
| sng-pidfd | - | 6.649e+04 | 32% | 96% | 153434 | osq_lock 20%, native_queued_spin_lock_slowpath 5% | lock 32% |
| sng-pkey | - | 4.693e+06 | 4% | 70% | 2616 | change_protection 6%, native_flush_tlb_one_user 5% | sleep (busy 70%) |
| sng-prctl | - | 5.378e+04 | 17% | 97% | 149540 | folios_put_refs 9%, osq_lock 9% | lock 17% |
| sng-pseek | - | 3.379e+06 | 3% | 99% | 9146772 | stress_peekio_exercise 20%, pseek_fill_buf.arch_sapphirerapids 6% | no |
| sng-ptrace | - | 1.312e+06 | 96% | 97% | 1412256 | native_queued_spin_lock_slowpath 95%, _raw_read_lock 1% | lock 96% |
| sng-pty | - | 474.4 | 83% | 94% | 49932 | osq_lock 81%, __raw_callee_save___kvm_vcpu_is_preempted 13% | lock 83% |
| sng-ramfs | - | 1.685e+04 | 49% | 66% | 155983 | native_queued_spin_lock_slowpath 33%, rwsem_spin_on_owner 6% | lock 49%; sleep (busy 66%) |
| sng-readahead | - | 6.979e+07 | 0% | 99% | 234 | stress_readahead 25%, entry_SYSCALL_64 12% | no |
| sng-remap | - | 5920 | 0% | 97% | 708 | vma_interval_tree_insert 6%, __get_user_pages 4% | no |
| sng-resched | - | 9.983e+06 | 15% | 100% | 2605456 | osq_lock 6%, native_queued_spin_lock_slowpath 4% | lock 15% |
| sng-revio | - | 9.385e+06 | 19% | 66% | 1139 | shmem_add_to_page_cache 35%, native_queued_spin_lock_slowpath 17% | lock 19%; sleep (busy 66%) |
| sng-ring-pipe | - | 1.205e+07 | 25% | 99% | 182 | _raw_spin_lock_irqsave 24%, pipe_poll 14% | lock 25% |
| sng-rlimit | - | 64.04 | 91% | 99% | 820 | native_queued_spin_lock_slowpath 91%, lockref_put_return 1% | lock 91% |
| sng-rmap | - | 2.318e+05 | 2% | 0% | 12688 | asm_sysvec_apic_timer_interrupt 12%, check_tsc_unstable 7% | sleep (busy 0%) |
| sng-rseq | - | 1.804e+04 | 0% | 85% | 200 | rseq_test 99%, get_jiffies_update 0% | no |
| sng-personality | - | 5.505e+06 | 0% | 99% | 189 | entry_SYSCALL_64 25%, do_syscall_64 22% | no |
| sng-numa | - | 822.5 | 12% | 78% | 47518 | __bitmap_weight 30%, queue_folios_pte_range 11% | lock 12% |

256 of 451 pass
