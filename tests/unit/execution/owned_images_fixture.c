/* SPDX-License-Identifier: GPL-2.0 */
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/mman.h>
#include "kd_image.h"
#define KD_CODE_BLOCK_POOL 64
#define READ_ONCE(x) (x)
#define smp_load_acquire(p) __atomic_load_n(p, __ATOMIC_ACQUIRE)
#define smp_store_release(p,v) __atomic_store_n(p,v,__ATOMIC_RELEASE)
#define try_cmpxchg(p,o,v) __atomic_compare_exchange_n(p,o,v,0,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST)
#define BUG_ON(x) assert(!(x))
#define __user
#define KD_PR_INFO(...)
#define KD_PR_ERR(...)
static struct kd_exe_info entries[KD_MAX_EXE], *kd_exes = entries;
static struct kd_jit_image kd_images[64];
static const struct kd_jit_image *kd_published_images[KD_MAX_EXE];
static void *kd_code_block_pool[64], *allocations[64];
static int kd_code_block_free, gate;
static bool source_open = true, copy_fault;
static unsigned long kd_code_block_gate_lock(void) { assert(!gate); gate = 1; return 0; }
static void kd_code_block_gate_unlock(unsigned long flags) { (void)flags;assert(gate); gate = 0; }
static bool kd_source_is_open(void) { return source_open; }
static int copy_from_user(void *d, const void *s, size_t n) {
 if(copy_fault) return 1;
 memcpy(d,s,n); return 0;
}
struct kd_exec_frame {
 bool owned_mutex; const struct kd_jit_image *image;
 unsigned int entry_abi; const struct kd_origin_guard *origin;
};
static int raw_smp_processor_id(void) { return 1; }
static int preempt_count(void) { return 1; }
#include "production.h"
static struct { struct kd_recv_pkt head; unsigned char code[128]; } packet;
static struct kd_image_upload upload;
static struct kd_exe_info *entry;
/* Synthetic code bodies exercise executable-storage lifetime, independently
 * of the kernel wrapper/GS admission tests. The old version waits until the
 * publisher releases it; the replacement declares the origin requirement and
 * returns immediately. Actual GS operations are covered by the live tests. */
static unsigned int body_started, body_release, body_finished;
static int body_result;
typedef int (*test_body)(unsigned int *, unsigned int *);
static void *run_bound_body(void *arg) {
 struct kd_exec_frame *frame=arg;
 test_body body=(test_body)((unsigned char *)kd_jit_bound_code(entry,frame)+KD_IMAGE_HEADER_SIZE);
 body_result=body(&body_started,&body_release);
 __atomic_store_n(&body_finished,1,__ATOMIC_RELEASE);
 return NULL;
}
static void start(unsigned long id, unsigned long generation, unsigned int req) {
 memset(&packet,0,sizeof(packet));
 packet.head=(struct kd_recv_pkt){.status_code=KD_EXE_NORMAL,.RIP=0x1000,
  .version=KD_IMAGE_PROTOCOL,.entry_abi=4,.requirements=req,
  .image_length=128,.upload_id=id,.base_generation=generation};
 memcpy(packet.code+9,"KDWB002",7); memcpy(packet.code+25,"KDWC002",7);
 memcpy(packet.code+41,"KDAB",4); packet.code[45]=4; packet.code[46]=2;
 packet.code[47]=req;
 /* x86-64: mark started, PAUSE/load/test until released, then return 1. */
 static const unsigned char waiting[]={0xc7,0x07,1,0,0,0,0xf3,0x90,0x8b,0x06,
  0x85,0xc0,0x74,0xf8,0xb8,1,0,0,0,0xc3};
 static const unsigned char immediate[]={0xb8,2,0,0,0,0xc3};
 if(req) memcpy(packet.code+KD_IMAGE_HEADER_SIZE,immediate,sizeof(immediate));
 else memcpy(packet.code+KD_IMAGE_HEADER_SIZE,waiting,sizeof(waiting));
}
static ssize_t send_bytes(size_t n) {
 ssize_t ret=kd_dev_write_locked(&upload,(const char *)&packet,sizeof(packet.head)+n);
 if(ret<0) { kd_image_discard(upload.image); upload.image=NULL; upload.covered=0; }
 return ret;
}
int main(void) {
 for(int i=0;i<KD_MAX_EXE;i++) entries[i].status_code=KD_EXE_UNUSED;
 for(int i=0;i<64;i++) {
  void *code=mmap(NULL,KD_CODE_BLOCK_SIZE,PROT_READ|PROT_WRITE|PROT_EXEC,
                  MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
  assert(code!=MAP_FAILED);
  allocations[i]=kd_code_block_pool[kd_code_block_free++]=code;
 }
 entry=kd_get_exe(0,0x1000);
 *entry=(struct kd_exe_info){.status_code=KD_EXE_UNINIT,.RIP=0x1000,.lock_kind=3,.entry_abi=4};
 start(1,0,0); assert(send_bytes(128)>0);
 const struct kd_jit_image *old=kd_image_current(entry);
 assert(old && old->generation==1 && !old->requirements && kd_code_block_free==63);
 struct kd_exec_frame bound={.owned_mutex=true,.entry_abi=4};
 assert(kd_jit_bind_image(entry,&bound) && bound.image==old);
 pthread_t executor;
 assert(!pthread_create(&executor,NULL,run_bound_body,&bound));
 while(!__atomic_load_n(&body_started,__ATOMIC_ACQUIRE)) sched_yield();
 unsigned char saved[128]; memcpy(saved,old->code,128);
 start(2,1,1); packet.head.status_code=KD_EXE_UNINIT;
 assert(send_bytes(64)>0); assert(kd_image_current(entry)==old);
 assert(!memcmp(old->code,saved,128));
 packet.head.offset=65; packet.head.status_code=KD_EXE_NORMAL;
 assert(send_bytes(63)==-EINVAL); assert(kd_code_block_free==63);
 start(3,1,1); packet.head.status_code=KD_EXE_UNINIT; assert(send_bytes(64)>0);
 packet.head.offset=64; packet.head.status_code=KD_EXE_NORMAL; packet.head.upload_id++;
 assert(send_bytes(64)==-ESTALE); assert(kd_image_current(entry)==old);
 start(4,1,1); packet.code[47]=0;
 assert(send_bytes(128)==-EPROTO); assert(kd_image_current(entry)==old);
 start(5,1,1); copy_fault=true; assert(send_bytes(128)==-EFAULT); copy_fault=false;
 assert(!__atomic_load_n(&body_finished,__ATOMIC_ACQUIRE));
 start(6,1,1); packet.head.status_code=KD_EXE_UNINIT;
 assert(send_bytes(64)>0 && kd_image_current(entry)==old);
 packet.head.offset=64; packet.head.status_code=KD_EXE_NORMAL;
 memmove(packet.code,packet.code+64,64); assert(send_bytes(64)>0);
 const struct kd_jit_image *new=kd_image_current(entry);
 assert(new!=old && new->requirements==1 && new->generation==2);
 assert(kd_jit_bind_image(entry,&bound) && kd_jit_bound_code(entry,&bound)==old->code);
 struct kd_exec_frame fresh={.owned_mutex=true,.entry_abi=4};
 assert(!kd_jit_bind_image(entry,&fresh)); /* generic dispatch also requires a claim */
 struct kd_origin_guard origin={.readiness=KD_ORIGIN_READY,.cpu=0};
 fresh.origin=&origin;
 assert(!kd_jit_bind_image(entry,&fresh));
 origin.readiness=KD_ORIGIN_CLAIMED;assert(kd_jit_bind_image(entry,&fresh));
 test_body replacement=(test_body)((unsigned char *)kd_jit_bound_code(entry,&fresh)+KD_IMAGE_HEADER_SIZE);
 assert(replacement(NULL,NULL)==2);
 assert(!__atomic_load_n(&body_finished,__ATOMIC_ACQUIRE));
 assert(!__atomic_load_n(&body_release,__ATOMIC_RELAXED));
 __atomic_store_n(&body_release,1,__ATOMIC_RELEASE);
 assert(!pthread_join(executor,NULL) && body_result==1);
 origin.cpu=1;assert(!kd_jit_bind_image(entry,&fresh));
 origin.cpu=0;origin.readiness=KD_ORIGIN_FINISHED;assert(!kd_jit_bind_image(entry,&fresh));
 assert(!memcmp(old->code,saved,128));
 kd_image_report(entry,old,KD_EXE_CALL_MISS,0xdead,0);
 assert(entry->status_code==KD_EXE_NORMAL && !entry->tgt_addr);
 kd_image_report(entry,new,KD_EXE_IJ_MISS,0xbeef,0xabcd);
 assert(entry->status_code==KD_EXE_IJ_MISS && entry->tgt_addr==0xbeef && entry->jump_from==0xabcd);
 start(7,1,0); assert(send_bytes(128)==-ESTALE);
 start(8,2,0); packet.head.version=1; assert(send_bytes(128)==-EPROTO);
 start(9,2,0); packet.head.image_length=47; assert(send_bytes(47)==-EINVAL);
 for(unsigned int gen=2;gen<64;gen++) { start(gen+10,gen,gen&1); assert(send_bytes(128)>0); }
 const struct kd_jit_image *last=kd_image_current(entry);
 start(100,64,1); assert(send_bytes(128)==-ENOSPC);
 assert(kd_image_current(entry)==last && last->generation==64);
 assert(!memcmp(old->code,saved,128));
 source_open=false; assert(send_bytes(128)==-ESHUTDOWN);
 for(int i=0;i<64;i++) assert(!munmap(allocations[i],KD_CODE_BLOCK_SIZE));
 puts("owned images: active old-code execution across origin-sensitive replacement, coverage, identity, metadata, stale misses and 64-block exhaustion passed");
}
