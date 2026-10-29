/* Included at the helper/setup/extra boundaries of the terminal fixture.
 * Exercise the actual dynamic lifecycle and mode-2 selection/drain helpers. */
#if defined(PIN_DIAG_FIXTURE_HELPERS)
static void diag_free_percpu(void *storage)
{
    /* Detach while excluding getters, then drop that exclusion before free. */
    CHECK(!diag_params_locked && !kd_mutex_pin_cpus);
    CHECK(storage && storage==diag_live_storage);
    memset(storage,0xdd,diag_storage_bytes);
    free(storage);diag_live_storage=NULL;diag_storage_bytes=0;diag_frees++;
}

static int diag_stats_get(char *buffer)
{
    int ret;
    /* Match kernel/params.c's externally held lock for the production getter. */
    kernel_param_lock(THIS_MODULE);
    ret=kd_mutex_pin_stats_get(buffer,NULL);
    kernel_param_unlock(THIS_MODULE);
    return ret;
}

static void diag_check_zero(void)
{
    CHECK(kd_mutex_pin_cpus && (void *)kd_mutex_pin_cpus==diag_live_storage);
    CHECK(diag_storage_bytes==sizeof(*kd_mutex_pin_cpus));
    for(size_t i=0;i<diag_storage_bytes;i++)
        CHECK(((const unsigned char *)diag_live_storage)[i]==0);
}
#elif defined(PIN_DIAG_FIXTURE_SETUP)
    char lifecycle_json[PAGE_SIZE];
    memset(lifecycle_json,'#',sizeof(lifecycle_json));
    CHECK(!kd_mutex_pin_cpus && !diag_live_storage);
    CHECK(diag_stats_get(lifecycle_json)==-ENODEV && !diag_cpu_accesses);
    CHECK(lifecycle_json[0]=='#' && lifecycle_json[PAGE_SIZE-1]=='#');
    diag_fail_alloc=true;
    CHECK(KD_MUTEX_PIN_DIAG_INIT()==-ENOMEM);
    CHECK(diag_alloc_attempts==1 && !diag_allocations && !diag_frees);
    CHECK(!kd_mutex_pin_cpus && !diag_live_storage && !diag_params_locked);
    CHECK(diag_stats_get(lifecycle_json)==-ENODEV && !diag_cpu_accesses);
    KD_MUTEX_PIN_DIAG_EXIT();
    CHECK(!diag_frees && !diag_live_storage && !diag_params_locked);
    diag_fail_alloc=false;
    CHECK(!KD_MUTEX_PIN_DIAG_INIT());
    CHECK(diag_alloc_attempts==2 && diag_allocations==1 && !diag_frees);
    diag_check_zero();
#else
    char pin_json[PAGE_SIZE];
    unsigned long long before_sum=0,after_sum=0,reason_sum=0;
    for(unsigned int i=0;i<=KD_MUTEX_CLAIM_SLOTS;i++) {
        before_sum+=kd_mutex_pin_totals.occupancy_before[i];
        after_sum+=kd_mutex_pin_totals.occupancy_after[i];
    }
    for(unsigned int i=0;i<KD_MUTEX_PIN_REASON_COUNT;i++)
        reason_sum+=kd_mutex_pin_totals.selection_result[i];
    CHECK(kd_mutex_pin_totals.selections==before_sum && before_sum==after_sum && after_sum==reason_sum);
    CHECK(kd_mutex_pin_totals.claims==kd_mutex_pin_totals.retired_claims+kd_mutex_pin_totals.cancelled_claims);
    CHECK(kd_mutex_pin_totals.batches==kd_mutex_combiner_count);
    CHECK(kd_mutex_pin_totals.occupancy_after[1]>0 && !kd_mutex_pin_totals.occupancy_before[1]);
    CHECK(kd_mutex_pin_totals.occupancy_after[1]==kd_mutex_pin_totals.claims);
    unsigned long long epoch_sum=0;
    for(unsigned int i=0;i<=KD_MUTEX_PIN_READY_LIMIT;i++)
        epoch_sum+=kd_mutex_pin_totals.epoch_ready_candidates[i];
    CHECK(epoch_sum==kd_mutex_pin_totals.epoch_admission_attempts-kd_mutex_pin_totals.epoch_admission_refusals);
    CHECK(kd_mutex_pin_totals.epoch_ready_candidates[8]>0);
    CHECK(kd_mutex_pin_totals.drain_nonempty==kd_mutex_pin_totals.cancelled_claims);
    /* Real accumulator/merge code, distinct from the actual wait-helper
     * interleavings exercised by the companion generated origin fixture. */
    { KD_MUTEX_PIN_WAIT_ENTER();KD_MUTEX_PIN_INITIAL_FINISH(true); }
    { KD_MUTEX_PIN_WAIT_ENTER();KD_MUTEX_PIN_BUDGET_EXPIRED();
      KD_MUTEX_PIN_EXPIRY_CHECK();KD_MUTEX_PIN_EXPIRY_CHECK();
      KD_MUTEX_PIN_WITHDRAW_RESERVED();KD_MUTEX_PIN_WITHDRAW();KD_MUTEX_PIN_INITIAL_FINISH(false); }
    { KD_MUTEX_PIN_WAIT_ENTER();KD_MUTEX_PIN_FORCED_CANCEL();KD_MUTEX_PIN_INITIAL_FINISH(false); }
    { KD_MUTEX_PIN_WAIT_ENTER();KD_MUTEX_PIN_BUDGET_EXPIRED();
      KD_MUTEX_PIN_EXPIRY_CHECK();KD_MUTEX_PIN_INITIAL_FINISH(true); }
    CHECK(kd_mutex_pin_totals.wait_episodes==4);
    CHECK(kd_mutex_pin_totals.initial_pin_retained==2 && kd_mutex_pin_totals.initial_pin_dropped==2);
    CHECK(kd_mutex_pin_totals.initial_budget_completed==1 && kd_mutex_pin_totals.budget_expired_episodes==2);
    CHECK(kd_mutex_pin_totals.expiry_checks==3 && kd_mutex_pin_totals.withdrawals==1);
    CHECK(kd_mutex_pin_totals.forced_cancellations==1 && kd_mutex_pin_totals.withdrawal_reservations==1);
    CHECK(kd_mutex_pin_totals.epoch_admission_attempts>0);
    CHECK(kd_mutex_pin_totals.epoch_admission_refusals<=kd_mutex_pin_totals.epoch_admission_attempts);
    CHECK(diag_stats_get(pin_json)>0);printf("PIN %s",pin_json);

    /* Selection describes only this invocation. Future READY origins stay
     * unchanged even when the separate epoch observation counts eight. */
    for(unsigned int stop=0;stop<KD_MUTEX_PIN_REASON_COUNT;stop++) {
        struct kd_mutex_batch observed={.lock=&lock,.numa_node=0};
        bool accepted;
        reset(12);
        if(stop==KD_MUTEX_PIN_SELF_CURRENT)nodes[0].tail=65536U<<4;
        if(stop==KD_MUTEX_PIN_CURRENT_NOT_READY)nodes[0].locked=KD_MUTEX_WAIT;
        CHECK(kd_mutex_batch_epoch_begin(&observed));
        KD_MUTEX_PIN_EPOCH_READY(&observed,&nodes[0]);
        CHECK(observed.diag.epoch_admission_attempts==1 && !observed.diag.epoch_admission_refusals);
        accepted=kd_mutex_batch_pin_select(&observed,&nodes[0]);
        CHECK(accepted==(stop==KD_MUTEX_PIN_CLAIMED));
        CHECK(observed.diag.selections==1 && observed.diag.occupancy_before[0]==1);
        CHECK(observed.diag.selection_result[stop]==1);
        CHECK(observed.diag.occupancy_after[observed.nr_pins]==1);
        CHECK(observed.diag.claims==observed.nr_pins && !polls);
        for(unsigned int i=1;i<12;i++)CHECK(nodes[i].locked==KD_MUTEX_PROXY_READY);
        if(accepted) {
            /* A logical claim is an exact descriptor, not notification 3. */
            CHECK(nodes[0].locked==KD_MUTEX_PROXY_READY && observed.diag.claims==1);
            KD_MUTEX_PIN_ASSERT(&observed,&nodes[0]);
            kd_mutex_batch_epoch_end(&observed,true);
            CHECK(observed.nr_pins==1 && nodes[0].locked==KD_MUTEX_PROXY_CLAIMED);
            CHECK(observed.diag.retain_current_calls==1 && !observed.diag.drain_nonempty);
            kd_mutex_batch_pin_assert_retained(&observed,&nodes[0]);
            kd_mutex_batch_epoch_end(&observed,true);
            CHECK(nodes[0].locked==KD_MUTEX_PROXY_CLAIMED && observed.diag.claims==1);
            CHECK(observed.diag.retain_current_calls==2 && !observed.diag.cancelled_claims);
        }
        kd_mutex_batch_epoch_end(&observed,false);
        CHECK(!observed.proxy_epoch && !observed.nr_pins && observed.diag.claims==observed.diag.cancelled_claims && !polls);
    }

    /* Bound the separate prefix observation. Incompatible entries stop the
     * sample; it neither claims future nodes nor authorizes a body. A changed
     * exact generation at the second read must not enter the histogram. */
    for(unsigned int boundary=0;boundary<12;boundary++) {
        struct kd_mutex_batch observed={.lock=&lock};
        unsigned int expected=boundary==11?0:boundary?1:8;
        reset(12);
        switch(boundary) {
        case 0: nodes[7].next=(void *)1;break; /* Never read a ninth link. */
        case 1: nodes[1].locked=KD_MUTEX_WAIT;break;
        case 2: nodes[1].entry_abi=KD_ENTRY_ABI_LEGACY;break;
        case 3: nodes[1].packet_state=KD_PACKET_FULL;break;
        case 4: nodes[1].regs.ip++;break;
        case 5: nodes[1].tail=nodes[0].tail;break;
        case 6: nodes[1].tail=65536U<<4;break;
        case 7: nodes[1].counted_lock=NULL;break;
        case 8: nodes[1].count_seq++;break;
        case 9: diag_generation_target=&nodes[1].count_seq;diag_generation_reads=0;break;
        case 10: nodes[1].regs.ip=0;break;
        case 11: nodes[0].regs.ip=0;break;
        default: CHECK(false);
        }
        CHECK(kd_mutex_batch_epoch_begin(&observed));
        KD_MUTEX_PIN_EPOCH_READY(&observed,&nodes[0]);
        CHECK(observed.diag.epoch_ready_candidates[expected]==1);
        CHECK(!observed.nr_pins && !observed.diag.claims && !polls);
        if(boundary==9)CHECK(diag_generation_reads==2);
        diag_generation_target=NULL;
        kd_mutex_batch_epoch_end(&observed,false);
    }
    for(unsigned int length=0;length<8;length++) {
        struct kd_mutex_batch observed={.lock=&lock};
        reset(length?length:1);
        CHECK(kd_mutex_batch_epoch_begin(&observed));
        KD_MUTEX_PIN_EPOCH_READY(&observed,length?&nodes[0]:NULL);
        CHECK(observed.diag.epoch_ready_candidates[length]==1 && !observed.diag.claims);
        kd_mutex_batch_epoch_end(&observed,false);
    }

    /* A real gate reservation refuses one epoch without claiming a node or
     * synthesizing an execution attempt. Release it before retrying admission. */
    reset(2);
    struct kd_mutex_batch refused_epoch={.lock=&lock};
    CHECK(kd_mutex_gate_try_withdraw(&lock));
    CHECK(!kd_mutex_batch_epoch_begin(&refused_epoch));
    CHECK(!refused_epoch.proxy_epoch && !refused_epoch.nr_pins);
    CHECK(refused_epoch.diag.epoch_admission_attempts==1 && refused_epoch.diag.epoch_admission_refusals==1);
    kd_mutex_gate_end_withdraw(&lock);
    CHECK(kd_mutex_batch_epoch_begin(&refused_epoch));
    CHECK(refused_epoch.diag.epoch_admission_attempts==2 && refused_epoch.diag.epoch_admission_refusals==1);
    KD_MUTEX_PIN_EPOCH_READY(&refused_epoch,&nodes[0]);
    CHECK(refused_epoch.diag.epoch_ready_candidates[2]==1);
    kd_mutex_batch_epoch_end(&refused_epoch,false);

    /* Maximal numeric values still serialize as complete JSON within sysfs. */
    memset(&kd_mutex_pin_totals,0xff,sizeof(kd_mutex_pin_totals));
    int pin_length=diag_stats_get(pin_json);
    CHECK(pin_length>0 && pin_length<(int)sizeof(pin_json));printf("PINMAX %s",pin_json);

    /* A final getter cannot outlive detached storage. Reinitialization must
     * discard every old total, even if the allocator reuses the same address. No pointer equality implies reuse. */
    KD_MUTEX_PIN_DIAG_EXIT();
    CHECK(!kd_mutex_pin_cpus && !diag_live_storage && !diag_params_locked);
    CHECK(diag_frees==1 && diag_allocations==1);
    unsigned int detached_accesses=diag_cpu_accesses;
    memset(pin_json,'#',sizeof(pin_json));
    CHECK(diag_stats_get(pin_json)==-ENODEV && diag_cpu_accesses==detached_accesses);
    CHECK(pin_json[0]=='#' && pin_json[PAGE_SIZE-1]=='#');
    KD_MUTEX_PIN_DIAG_EXIT();
    CHECK(diag_frees==1 && !diag_live_storage);
    CHECK(!KD_MUTEX_PIN_DIAG_INIT());
    CHECK(diag_alloc_attempts==3 && diag_allocations==2 && diag_frees==1);
    diag_check_zero();
    CHECK(diag_stats_get(pin_json)>0);printf("PINRESET %s",pin_json);
    KD_MUTEX_PIN_DIAG_EXIT();
    CHECK(!kd_mutex_pin_cpus && !diag_live_storage && !diag_params_locked);
    CHECK(diag_allocations==2 && diag_frees==2);
    CHECK(diag_param_locks==diag_param_unlocks);
    CHECK(diag_stats_get(pin_json)==-ENODEV);
    CHECK(!diag_params_locked && diag_param_locks==diag_param_unlocks);
    puts("PASS pin diagnostic allocation lifecycle: failure, unavailable getter, detach/free and zero reinitialization");
#endif
