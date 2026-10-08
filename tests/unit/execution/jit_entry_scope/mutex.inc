/* Entry-scope fixture cases; shared stubs live in jit_entry_scope_fixture.c. */
static void poison_mutex_routing(struct kd_exec_frame *frame)
{
 frame->continuation_ip=0xdead;
 frame->logical_pid=-97;
 frame->delegated_lock_addr=0xbeef;
 frame->resume_target=(void *)1;
 frame->remote_request=(void *)2;
 frame->control_call.phase=KD_CALL_ENTERED;
 frame->native_request=(void *)3;
 frame->remote_result=KD_EXEC_REMOTE_WAITING;
 frame->native_link.next=(void *)4;
 frame->native_link.prev=(void *)5;
}
static bool mutex_routing_poisoned(const struct kd_exec_frame *frame)
{
 return frame->continuation_ip==0xdead && frame->logical_pid==-97 &&
  frame->delegated_lock_addr==0xbeef && frame->resume_target==(void *)1 &&
  frame->remote_request==(void *)2 && frame->control_call.phase==KD_CALL_ENTERED &&
  frame->native_request==(void *)3 && frame->remote_result==KD_EXEC_REMOTE_WAITING &&
  frame->native_link.next==(void *)4 && frame->native_link.prev==(void *)5;
}
static bool mutex_routing_initialized(const struct kd_exec_frame *frame)
{
 return !frame->continuation_ip && frame->logical_pid==frame->logical_task->pid &&
  !frame->delegated_lock_addr && !frame->resume_target && !frame->remote_request &&
  frame->control_call.phase==KD_CALL_NONE && !frame->native_request &&
  frame->remote_result==KD_EXEC_REMOTE_IDLE &&
  frame->native_link.next==&frame->native_link && frame->native_link.prev==&frame->native_link;
}

/* Real ABI2 batch admission and the actual pending dispatcher. Machine-code
 * completion and poisoned CALL fallbacks are exercised by test_clobber_abi. */
static void check_mutex_batch(void)
{
 unsigned char code[64]={0};
 struct kd_jit_batch_call call, before;
 struct kd_regs borrowed, saved_borrowed;
 unsigned long saved_lock_addr=direct_mutex_lock_addr, saved_unlock_addr=direct_mutex_unlock_addr;
 struct kd_exec_frame saved, rejected;
 struct kd_exec_outer_unlock hook={0};
 memcpy(code+25,"KDWC002",7); memcpy(code+41,"KDAB",4);
 code[45]=KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
 for (int timing=0;timing<2;timing++) {
  reset(); borrowed=active.regs;
  /* Packet selection must use the borrowed waiter packet, not frame storage. */
  borrowed.sp+=8; saved_borrowed=borrowed;
  active.mutex_backend=active.batch_lease=active.regs_borrowed=true;
  active.borrowed_regs=&borrowed;
  active.entry_abi=entry->entry_abi=KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
  active.packet_state=KD_PACKET_MINIMAL;
  entry->lock_kind=KD_EXE_LOCK_MUTEX; entry->code_block=code;
  kd_jit_timing=timing; timing_clock_active=timing; timing_clock=1;
  CHECK(kd_exe_mutex_batch_prepare(entry,&active,&call));
  CHECK(call.regs==&borrowed && call.entry_abi==2 && call.complete &&
        call.unlock==direct_mutex_unlock_addr && call.lock==active.outer_lock_addr &&
        call.entry_sp==borrowed.sp && call.entry_sp!=active.regs.sp &&
        call.code==code+32 && call.args[0]==active.gsbase &&
        call.args[1]==(unsigned long)&waiter && call.packet_state==&active.packet_state);
  CHECK(timing_reads==(timing?2U:0U));
  saved=active;
  /* Each pristine-frame discriminator stays an admission requirement;
   * refusal must not partially publish transport or modify the frame. */
  for (int bad=0;bad<33;bad++) {
   switch(bad) {
   case 0: source_open=false;break;
   case 1: entry->status_code=KD_EXE_NATIVE_ONLY;break;
   case 2: entry->lock_kind=KD_EXE_LOCK_SPIN;break;
   case 3: code[45]=KD_ENTRY_ABI_SPIN_CLOBBER_V1;break;
   case 4: active.entry_abi=KD_ENTRY_ABI_LEGACY;break;
   case 5: active.packet_state=KD_PACKET_FULL;break;
   case 6: active.mutex_backend=false;break;
   case 7: active.batch_lease=false;break;
   case 8: active.regs_borrowed=false;break;
   case 9: active.executed=true;break;
   case 10: active.jit_lock_depth=2;break;
   case 11: active.jit_lock_released[0]=true;break;
   case 12: active.control_call.phase=KD_CALL_ENTERED;break;
   case 13: active.parent=&parent;break;
   case 14: active.depth=1;break;
   case 15: active.complex_ready=false;break;
   case 16: active.spin_simple=true;break;
   case 17: active.request_frame=true;break;
   case 18: active.outer_unlock_seen=true;break;
   case 19: active.completion_seen=true;break;
   case 20: active.outer_lock_index=1;break;
   case 21: active.remote_result=KD_EXEC_REMOTE_WAITING;break;
   case 22: active.remote_result=KD_EXEC_REMOTE_NATIVE;break;
   case 23: active.gsbase=0;break;
   case 24: active.logical_task=NULL;break;
   case 25: borrowed.ip++;break;
   case 26: borrowed.sp=0;break;
   case 27: active.state=KD_EXEC_FRAME_COMPLETE;break;
   case 28: active.outer_lock_addr=0;break;
   case 29: entry->entry_abi=KD_ENTRY_ABI_LEGACY;break;
   case 30: code[25]^=1;break;
   case 31: direct_mutex_lock_addr=0;break;
   case 32: direct_mutex_unlock_addr=0;break;
   }
   before=call; rejected=active;
   CHECK(!kd_exe_mutex_batch_prepare(entry,&active,&call));
   CHECK(!memcmp(&call,&before,sizeof(call)));
   CHECK(!memcmp(&active,&rejected,sizeof(active)));
   active=saved; borrowed=saved_borrowed; source_open=true;
   entry->status_code=KD_EXE_NORMAL; entry->entry_abi=KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
   entry->lock_kind=KD_EXE_LOCK_MUTEX; code[45]=2; code[25]='K';
   direct_mutex_lock_addr=saved_lock_addr;direct_mutex_unlock_addr=saved_unlock_addr;
  }
  call.args[0]=KD_EXE_CALL_MISS;
  CHECK(!kd_exe_mutex_batch_completed(&call,&active));
  call.args[0]=KD_EXE_CLOBBER_COMPLETE;
  CHECK(!kd_exe_mutex_batch_completed(&call,&active));
  active.packet_state=KD_PACKET_COMPLETE; call.args[1]=1;
  CHECK(kd_exe_mutex_batch_completed(&call,&active));
  CHECK(calls==0 && timing_reads==(timing?4U:0U));
 }
 for (int lazy=0;lazy<2;lazy++) for (int refuse=0;refuse<2;refuse++) {
  reset(); borrowed=active.regs;
  active.mutex_backend=active.batch_lease=active.regs_borrowed=true;
  active.borrowed_regs=&borrowed;
  active.entry_abi=entry->entry_abi=KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
  active.packet_state=KD_PACKET_MINIMAL;
  entry->lock_kind=KD_EXE_LOCK_MUTEX;entry->code_block=code;
  active.jit_lock_node[0]=&active; active.outer_unlock_hook=&hook;
  if (lazy) { active.complex_ready=false; poison_mutex_routing(&active); }
  CHECK(kd_exe_mutex_batch_prepare(entry,&active,&call));
  if (lazy) CHECK(mutex_routing_poisoned(&active));
  active.executed=true;
  steps[0]=refuse ? (struct step){KD_EXE_ENTRY_REFUSED,0,0,0} :
                   (struct step){KD_EXE_CALL_MISS,0x9870,1,-8};
  translated(call.regs,call.args); /* One already-returned body. */
  if (!refuse) active.packet_state=KD_PACKET_FULL;
  known_result=0;
  CHECK(kd_exe_mutex_batch_resume(entry,&call)==(refuse?KD_EXE_NO_RUN:KD_EXE_RUN_NATIVE));
  CHECK(calls==1 && active.executed==!refuse && !complex_preparations);
  CHECK(active.mutex_backend && active.batch_lease && active.complex_ready);
  CHECK(active.jit_lock_node[0]==&active && active.outer_unlock_hook==&hook);
  if (lazy) CHECK(mutex_routing_initialized(&active));
  CHECK(active.regs_borrowed==(bool)refuse);
  if (!refuse) {
   CHECK(kd_exec_frame_regs(&active)==&active.regs && active.regs.ip==0x9870);
   memset(&borrowed,0xaf,sizeof(borrowed));
   CHECK(active.regs.ip==0x9870 && source_calls==1);
  }
 }
 /* A failed fast preparation reaches the same materialization before the
  * generic readiness rejection. It must not execute or copy MINIMAL bytes. */
 reset(); borrowed=active.regs;
 active.mutex_backend=active.batch_lease=active.regs_borrowed=true;
 active.borrowed_regs=&borrowed; active.complex_ready=false;
 active.jit_lock_node[0]=&active; active.outer_unlock_hook=&hook;
 active.entry_abi=entry->entry_abi=KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
 active.packet_state=KD_PACKET_MINIMAL;
 entry->lock_kind=KD_EXE_LOCK_MUTEX; entry->code_block=code;
 poison_mutex_routing(&active); source_open=false;
 CHECK(!kd_exe_mutex_batch_prepare(entry,&active,&call));
 CHECK(mutex_routing_poisoned(&active));
 CHECK(kd_exe_on_call_hl_entry(entry,&borrowed,active.entry_ip,
                             active.outer_lock_addr)==KD_EXE_NO_RUN);
 CHECK(active.complex_ready && mutex_routing_initialized(&active));
 CHECK(!calls && !active.executed && active.regs_borrowed &&
       active.packet_state==KD_PACKET_MINIMAL && kd_exec_frame_regs(&active)==&borrowed);
 CHECK(active.outer_unlock_hook==&hook && active.jit_lock_node[0]==&active);
 source_open=true;
}
