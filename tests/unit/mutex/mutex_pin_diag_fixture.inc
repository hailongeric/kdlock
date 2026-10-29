/* Included inside the terminal fixture main after its production queue cases.
 * This checks actual mode-2 selection/drain hooks, not a second counter model. */
    char pin_json[PAGE_SIZE];
    unsigned long long before_sum=0,after_sum=0,reason_sum=0;
    for(unsigned int i=0;i<=KD_MUTEX_PIN_WINDOW;i++) {
        before_sum+=kd_mutex_pin_totals.occupancy_before[i];
        after_sum+=kd_mutex_pin_totals.occupancy_after[i];
    }
    for(unsigned int i=0;i<KD_MUTEX_PIN_REASON_COUNT;i++)
        reason_sum+=kd_mutex_pin_totals.refill_stop[i];
    CHECK(kd_mutex_pin_totals.selections==before_sum && before_sum==after_sum && after_sum==reason_sum);
    CHECK(kd_mutex_pin_totals.requested==kd_mutex_pin_totals.consumed+kd_mutex_pin_totals.cancelled);
    CHECK(kd_mutex_pin_totals.cancelled==kd_mutex_pin_totals.cancel_ack_immediate);
    CHECK(!kd_mutex_pin_totals.current_ack_stalled && !kd_mutex_pin_totals.cancel_ack_stalled);
    CHECK(kd_mutex_pin_totals.current_ack_immediate==kd_mutex_pin_totals.selections);
    CHECK(kd_mutex_pin_totals.batches==kd_mutex_combiner_count);
    CHECK(kd_mutex_pin_totals.occupancy_after[4]>0 && kd_mutex_pin_totals.occupancy_before[3]>0);
    CHECK(kd_mutex_pin_stats_get(pin_json,NULL)>0);printf("PIN %s",pin_json);

    /* Each stop has one invocation receipt; pending ACK cancellation settles
     * selections before any batch merge. Selection metadata is never ownership. */
    for(unsigned int stop=0;stop<KD_MUTEX_PIN_REASON_COUNT;stop++) {
        struct kd_mutex_batch observed={.lock=&lock,.numa_node=0,.pin_budget=4};
        bool ahead=true,accepted;
        reset(stop==KD_MUTEX_PIN_NO_LINK?1:stop==KD_MUTEX_PIN_DEFERRED_TAIL?2:8);
        switch(stop) {
        case KD_MUTEX_PIN_SELF_CURRENT: nodes[0].tail=65536U<<4;break;
        case KD_MUTEX_PIN_SINGLE: ahead=false;break;
        case KD_MUTEX_PIN_BUDGET: observed.pin_budget=2;break;
        case KD_MUTEX_PIN_WINDOW_FULL: break;
        case KD_MUTEX_PIN_NO_LINK: break;
        case KD_MUTEX_PIN_ENTRY: nodes[1].regs.ip=0xbad;break;
        case KD_MUTEX_PIN_NUMA: nodes[1].numa_node=1;break;
        case KD_MUTEX_PIN_DEFERRED_TAIL: observed.deferred_head=&nodes[7];break;
        case KD_MUTEX_PIN_DUPLICATE_CPU: nodes[1].tail=nodes[0].tail;break;
        case KD_MUTEX_PIN_SELF_FUTURE: nodes[1].tail=65536U<<4;break;
        default: CHECK(false);
        }
        accepted=kd_mutex_batch_pin_select(&observed,&nodes[0],ahead);
        CHECK(accepted==(stop!=KD_MUTEX_PIN_SELF_CURRENT));
        CHECK(observed.diag.selections==1 && observed.diag.occupancy_before[0]==1);
        CHECK(observed.diag.refill_stop[stop]==1);
        CHECK(observed.diag.occupancy_after[observed.nr_pins]==1);
        CHECK(observed.diag.requested==observed.nr_pins);
        kd_mutex_batch_unpin(&observed,false);
        CHECK(!observed.nr_pins && observed.diag.requested==observed.diag.cancelled);
        CHECK(observed.diag.cancel_ack_immediate==observed.diag.cancelled);
    }

    /* Delayed current and cancellation ACKs count PAUSE iterations separately.
     * No helper reads an origin packet or changes its notification protocol. */
    struct kd_mutex_pin_diag wait_diag={0};
    reset(1);nodes[0].locked=KD_MUTEX_PROXY_PINNED;
#if KDLOCK_MUTEX_PIN_TSC_SHIFT
    kd_mutex_pin_sample_seq=63;
#endif
    kd_mutex_pin_diag_wait(&wait_diag,&nodes[0],false);
    CHECK(wait_diag.current_ack_immediate==1 && !wait_diag.current_ack_loops);
    for(unsigned int cancel=0;cancel<2;cancel++) {
        nodes[0].locked=KD_MUTEX_PROXY_REQUEST;diag_ack_node=&nodes[0];diag_ack_polls=0;
#if KDLOCK_MUTEX_PIN_TSC_SHIFT
        if(!cancel)kd_mutex_pin_sample_seq=63;
#endif
        kd_mutex_pin_diag_wait(&wait_diag,&nodes[0],cancel);
        CHECK(!diag_ack_node && diag_ack_polls==3);
    }
    CHECK(wait_diag.current_ack_stalled==1 && wait_diag.current_ack_loops==3);
    CHECK(wait_diag.cancel_ack_stalled==1 && wait_diag.cancel_ack_loops==3);
#if KDLOCK_MUTEX_PIN_TSC_SHIFT
    CHECK(wait_diag.tsc_samples==2 && wait_diag.tsc_cycles==14);
#else
    CHECK(!wait_diag.tsc_samples && !wait_diag.tsc_cycles);
#endif
    /* Maximal numeric values still serialize as complete JSON within sysfs. */
    memset(&kd_mutex_pin_totals,0xff,sizeof(kd_mutex_pin_totals));
    int pin_length=kd_mutex_pin_stats_get(pin_json,NULL);
    CHECK(pin_length>0 && pin_length<(int)sizeof(pin_json));printf("PINMAX %s",pin_json);
