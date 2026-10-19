/* SPDX-License-Identifier: GPL-2.0 */
/* Actual upload, relocation and shared descriptor lifetime; native helper
 * addresses and source leases are primitives, no helper code is inspected. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include "kd_image.h"
#define KD_CODE_BLOCK_POOL 64
#define READ_ONCE(x) (x)
#define smp_load_acquire(p) __atomic_load_n(p, __ATOMIC_ACQUIRE)
#define smp_store_release(p,v) __atomic_store_n(p,v,__ATOMIC_RELEASE)
#define try_cmpxchg(p,o,v) __atomic_compare_exchange_n(p,o,v,0,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST)
#define BUG_ON(x) assert(!(x))
#define __user
#define KD_PR_INFO(...) do { } while (0)
#define KD_PR_ERR(...) do { } while (0)
#include "image_direct_support.h"
static struct kd_exe_info entries[KD_MAX_EXE], *kd_exes = entries;
static struct kd_jit_image kd_images[64];
static const struct kd_jit_image *kd_published_images[KD_MAX_EXE];
static void *kd_code_block_pool[64], *allocations[64];
static int kd_code_block_free, gate, source_error, source_calls;
static unsigned long pinned[4];
static bool source_open = true;
static unsigned long kd_code_block_gate_lock(void) { assert(!gate); gate = 1; return 0; }
static void kd_code_block_gate_unlock(unsigned long flags) { (void)flags; assert(gate); gate = 0; }
static bool kd_source_is_open(void) { return source_open; }
static int copy_from_user(void *d, const void *s, size_t n) { memcpy(d,s,n); return 0; }
static int kd_source_pin_root(unsigned long ip) {
 assert(source_calls < 4); pinned[source_calls++] = ip;
 return ip ? source_error : -EINVAL;
}
static int copy_from_kernel_nofault(void *d, const void *s, size_t n) {
 /* These direct-only cases must never read helper/source instruction bytes. */
 (void)d; (void)s; (void)n; abort();
}
struct kd_exec_frame { bool mutex_backend; const struct kd_jit_image *image; unsigned int entry_abi; };
#include "production.h"
static struct { struct kd_recv_pkt head; unsigned char code[160]; } packet;
static struct kd_image_upload upload;
static struct kd_exe_info *entry;
static void start(unsigned long generation) {
 memset(&packet,0,sizeof(packet)); source_calls=0; source_error=0;
 packet.head=(struct kd_recv_pkt){.status_code=KD_EXE_NORMAL,.RIP=0x1000,
  .version=KD_IMAGE_PROTOCOL,.entry_abi=1,
  .requirements=KD_IMAGE_REQUIRE_DIRECT_STRINGS|KD_IMAGE_REQUIRE_STRING_SERVICES|KD_IMAGE_REQUIRE_STRING_WRITE,
  .image_length=sizeof(packet.code),.upload_id=generation+1,.base_generation=generation};
 memcpy(packet.code+9,"KDWB002",7); memcpy(packet.code+25,"KDWC002",7);
 memcpy(packet.code+41,"KDAB",4); packet.code[45]=1; packet.code[46]=2;
 packet.code[47]=packet.head.requirements;
 packet.code[64]=packet.code[80]=0xe8;
 struct kd_direct_call_site *site=(void*)(packet.code+112);
 site[0]=(struct kd_direct_call_site){64,KD_HOSTCALL_STRCMP,0x2000};
 site[1]=(struct kd_direct_call_site){80,KD_HOSTCALL_STRSCPY_PAD,0x3000};
 struct kd_direct_call_footer *footer=(void*)(packet.code+144);
 memcpy(footer->magic,"KDNC0001",8); footer->offset=112; footer->count=2;
 /* Both signed displacement directions are exercised in a bounded arena. */
 kd_hostcalls[0].addr=(unsigned long)kd_near_block_pool[kd_near_block_free-1]+256;
 kd_hostcalls[1].addr=(unsigned long)kd_near_block_pool[kd_near_block_free-1]+16;
}
static ssize_t send_packet(void) {
 ssize_t ret=kd_dev_write_locked(&upload,(const char*)&packet,sizeof(packet));
 if(ret<0) { kd_image_discard(upload.image); upload.image=NULL; upload.covered=0; }
 return ret;
}
int main(void) {
 assert(sizeof(struct kd_jit_image)==48 && sizeof(struct kd_direct_call_site)==16);
 for(int i=0;i<KD_MAX_EXE;i++) entries[i].status_code=KD_EXE_UNUSED;
 for(int i=0;i<64;i++) {
  allocations[i]=kd_code_block_pool[kd_code_block_free++]=calloc(1,KD_CODE_BLOCK_SIZE);
  kd_near_block_allocations[i]=kd_near_block_pool[kd_near_block_free++]=calloc(1,KD_CODE_BLOCK_SIZE);
 }
 assert(kd_image_direct_available());
 entry=kd_get_exe(0,0x1000);
 *entry=(struct kd_exe_info){.status_code=KD_EXE_UNINIT,.RIP=0x1000,.lock_kind=1,.entry_abi=1};
 struct kd_jit_image *initial=kd_image_alloc();
 initial->entry=entry; initial->entry_abi=1; initial->immutable=0;
 entry->code_block=initial->code; kd_published_images[entry-entries]=initial;
 for(int bad=0;bad<13;bad++) {
  start(0);
  struct kd_direct_call_site *site=(void*)(packet.code+112);
  struct kd_direct_call_footer *footer=(void*)(packet.code+144);
  switch(bad) {
   case 0: footer->magic[0]=0; break;
   case 1: footer->count=65; break;
   case 2: footer->offset=48; break;
   case 3: site[0].service_id=KD_HOSTCALL_INT_SQRT; break;
   case 4: site[0].call_offset=47; break;
   case 5: site[0].call_offset=108; break;
   case 6: site[1].call_offset=64; break;
   case 7: packet.code[64]=0xff; break;
   case 8: packet.code[65]=1; break;
   case 9: site[0].return_ip=0; break;
   case 10: kd_hostcalls[0].addr=0; break;
   case 11: kd_hostcalls[0].addr=(unsigned long)kd_near_block_pool[63]+0x80000100UL; break;
   case 12: source_error=-ESTALE; break;
  }
  assert(send_packet()<0 && kd_near_block_free==64 && kd_code_block_free==63);
  assert(kd_image_current(entry)==initial && !initial->near_text);
 }
 start(0); assert(send_packet()>0);
 const struct kd_jit_image *old=kd_image_current(entry);
 assert(old!=initial && old->near_text && old->immutable && old->generation==1);
 assert(kd_near_block_free==63 && kd_code_block_free==63 && source_calls==4);
 assert(pinned[0]==kd_hostcalls[0].addr && pinned[1]==0x2000 &&
        pinned[2]==kd_hostcalls[1].addr && pinned[3]==0x3000);
 int forward, backward;
 memcpy(&forward,(char*)old->code+65,4); memcpy(&backward,(char*)old->code+81,4);
 assert((unsigned long)old->code+69+forward==kd_hostcalls[0].addr && forward>0);
 assert((unsigned long)old->code+85+backward==kd_hostcalls[1].addr && backward<0);
 unsigned char saved[160]; memcpy(saved,old->code,sizeof(saved));
 struct kd_exec_frame bound={.entry_abi=1};
 assert(kd_jit_bind_image(entry,&bound) && bound.image==old);
 for(unsigned int generation=1;generation<63;generation++) {
  start(generation); assert(send_packet()>0);
 }
 assert(kd_near_block_free==1 && kd_code_block_free==63);
 start(63); assert(send_packet()==-ENOSPC); /* shared 64 descriptors, spare pools */
 assert(kd_image_direct_available() && kd_near_block_free==1);
 assert(!memcmp(old->code,saved,sizeof(saved)) && kd_jit_bound_code(entry,&bound)==old->code);
 assert(!kd_image_alloc() && !kd_image_alloc_direct());
 kd_image_disable(entry); start(63); assert(send_packet()==-EPERM);
 for(int i=0;i<64;i++) { free(allocations[i]); free(kd_near_block_allocations[i]); }
 puts("direct images: generated slots, source pins, rel32 range, immutable lifetime and shared 64-image ceiling passed");
}
