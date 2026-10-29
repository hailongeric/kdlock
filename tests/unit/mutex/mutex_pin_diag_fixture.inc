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
    for(unsigned int i=0;i<=KD_MUTEX_PIN_WINDOW;i++) {
        before_sum+=kd_mutex_pin_totals.occupancy_before[i];
        after_sum+=kd_mutex_pin_totals.occupancy_after[i];
    }
    for(unsigned int i=0;i<KD_MUTEX_PIN_REASON_COUNT;i++)
        reason_sum+=kd_mutex_pin_totals.refill_stop[i];
    CHECK(kd_mutex_pin_totals.selections==before_sum && before_sum==after_sum && after_sum==reason_sum);
    CHECK(kd_mutex_pin_totals.claims==kd_mutex_pin_totals.retired_claims+kd_mutex_pin_totals.cancelled_claims);
    CHECK(kd_mutex_pin_totals.batches==kd_mutex_combiner_count);
    CHECK(kd_mutex_pin_totals.occupancy_after[8]>0 && kd_mutex_pin_totals.occupancy_before[7]>0);
    /* Real accumulator/merge code, distinct from the actual wait-helper
     * interleavings exercised by the companion generated origin fixture. */
    { KD_MUTEX_PIN_WAIT_ENTER();KD_MUTEX_PIN_INITIAL_FINISH(true); }
    { KD_MUTEX_PIN_WAIT_ENTER();KD_MUTEX_PIN_BUDGET_EXPIRED();
      KD_MUTEX_PIN_EXPIRY_CHECK();KD_MUTEX_PIN_EXPIRY_CHECK();
      KD_MUTEX_PIN_WITHDRAW();KD_MUTEX_PIN_INITIAL_FINISH(false); }
    { KD_MUTEX_PIN_WAIT_ENTER();KD_MUTEX_PIN_FORCED_CANCEL();KD_MUTEX_PIN_INITIAL_FINISH(false); }
    { KD_MUTEX_PIN_WAIT_ENTER();KD_MUTEX_PIN_BUDGET_EXPIRED();
      KD_MUTEX_PIN_EXPIRY_CHECK();KD_MUTEX_PIN_INITIAL_FINISH(true); }
    CHECK(kd_mutex_pin_totals.wait_episodes==4);
    CHECK(kd_mutex_pin_totals.initial_pin_retained==2 && kd_mutex_pin_totals.initial_pin_dropped==2);
    CHECK(kd_mutex_pin_totals.initial_budget_completed==1 && kd_mutex_pin_totals.budget_expired_episodes==2);
    CHECK(kd_mutex_pin_totals.expiry_checks==3 && kd_mutex_pin_totals.withdrawals==1);
    CHECK(kd_mutex_pin_totals.forced_cancellations==1);
    CHECK(diag_stats_get(pin_json)>0);printf("PIN %s",pin_json);

    /* Each stop has one selection receipt. Terminal requests remain eligible;
     * no-link stops the refill without waiting for another producer. */
    for(unsigned int stop=0;stop<KD_MUTEX_PIN_REASON_COUNT;stop++) {
        struct kd_mutex_batch observed={.lock=&lock,.numa_node=0,.pin_budget=KD_MUTEX_PIN_WINDOW};
        bool ahead=true,accepted;
        reset(stop==KD_MUTEX_PIN_NO_LINK?1:stop==KD_MUTEX_PIN_DEFERRED_TAIL?2:12);
        switch(stop) {
        case KD_MUTEX_PIN_SELF_CURRENT: nodes[0].tail=65536U<<4;break;
        case KD_MUTEX_PIN_SINGLE: ahead=false;break;
        case KD_MUTEX_PIN_BUDGET: observed.pin_budget=2;break;
        case KD_MUTEX_PIN_WINDOW_FULL: break;
        case KD_MUTEX_PIN_NO_LINK: break;
        case KD_MUTEX_PIN_DEFERRED_TAIL: observed.deferred_head=&nodes[11];break;
        case KD_MUTEX_PIN_ENTRY: nodes[1].regs.ip=0xbad;break;
        case KD_MUTEX_PIN_NUMA: nodes[1].numa_node=1;break;
        case KD_MUTEX_PIN_DUPLICATE_CPU: nodes[1].tail=nodes[0].tail;break;
        case KD_MUTEX_PIN_SELF_FUTURE: nodes[1].tail=65536U<<4;break;
        case KD_MUTEX_PIN_CURRENT_NOT_READY: nodes[0].locked=KD_MUTEX_WAIT;break;
        case KD_MUTEX_PIN_FUTURE_NOT_READY: nodes[1].locked=KD_MUTEX_WAIT;break;
        default: CHECK(false);
        }
        accepted=kd_mutex_batch_pin_select(&observed,&nodes[0],ahead);
        CHECK(accepted==(stop!=KD_MUTEX_PIN_SELF_CURRENT && stop!=KD_MUTEX_PIN_CURRENT_NOT_READY));
        CHECK(observed.diag.selections==1 && observed.diag.occupancy_before[0]==1);
        CHECK(observed.diag.refill_stop[stop]==1);
        CHECK(observed.diag.occupancy_after[observed.nr_pins]==1);
        CHECK(observed.diag.claims==observed.nr_pins && !polls);
        kd_mutex_batch_unpin(&observed,false);
        CHECK(!observed.nr_pins && observed.diag.claims==observed.diag.cancelled_claims && !polls);
    }

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
