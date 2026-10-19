/* SPDX-License-Identifier: GPL-2.0 */
/* Exercise the first guarded spin publication while an earlier source frame
 * and partial in-place upload still retain their exact prior code block. */
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
static int kd_code_block_free, gate, source_error;
static bool source_open = true;
static unsigned long kd_code_block_gate_lock(void) { assert(!gate); gate = 1; return 0; }
static void kd_code_block_gate_unlock(unsigned long flags) { (void)flags; assert(gate); gate = 0; }
static bool kd_source_is_open(void) { return source_open; }
static int copy_from_user(void *d, const void *s, size_t n) { memcpy(d,s,n); return 0; }
static int kd_source_pin_root(unsigned long ip) { return ip ? source_error : -EINVAL; }
static int copy_from_kernel_nofault(void *d, const void *s, size_t n) { memcpy(d,s,n); return 0; }
struct kd_exec_frame {
 bool mutex_backend; const struct kd_jit_image *image; unsigned int entry_abi;
};
#include "production.h"
static struct { struct kd_recv_pkt head; unsigned char code[128]; } packet;
static struct kd_image_upload upload;
static unsigned char source_opcode[] = { 0x48, 0x8b, 0x00 };
static struct kd_exe_info *entry;
static void start(unsigned long id, unsigned long generation, unsigned int requirements) {
 memset(&packet,0,sizeof(packet));
 packet.head=(struct kd_recv_pkt){.status_code=KD_EXE_NORMAL,.RIP=0x1000,
  .version=KD_IMAGE_PROTOCOL,.entry_abi=1,.requirements=requirements,
  .image_length=128,.upload_id=id,.base_generation=generation};
 memcpy(packet.code+9,"KDWB002",7); memcpy(packet.code+25,"KDWC002",7);
 memcpy(packet.code+41,"KDAB",4); packet.code[45]=1; packet.code[46]=2;
 packet.code[47]=requirements;
 if(requirements & KD_IMAGE_REQUIRE_ADDRESS_GUARD) {
  struct kd_address_guard_site *site=(void*)(packet.code+80);
  struct kd_address_guard_footer *footer=(void*)(packet.code+112);
  site->ip=(unsigned long)source_opcode; site->length=3; site->proof=1;
  memcpy(site->opcode,source_opcode,sizeof(source_opcode));
  memcpy(footer->magic,"KDAG0001",8); footer->offset=80; footer->count=1;
 }
}
static ssize_t send_bytes(size_t n) {
 ssize_t ret=kd_dev_write_locked(&upload,(const char*)&packet,sizeof(packet.head)+n);
 if(ret<0) { kd_image_discard(upload.image); upload.image=NULL; upload.covered=0; }
 return ret;
}
int main(void) {
 for(int i=0;i<KD_MAX_EXE;i++) entries[i].status_code=KD_EXE_UNUSED;
 for(int i=0;i<64;i++) allocations[i]=kd_code_block_pool[kd_code_block_free++]=calloc(1,KD_CODE_BLOCK_SIZE);
 entry=kd_get_exe(0,0x1000);
 *entry=(struct kd_exe_info){.status_code=KD_EXE_UNINIT,.RIP=0x1000,.lock_kind=1,.entry_abi=1};
 struct kd_jit_image *initial=kd_image_alloc();
 initial->entry=entry; initial->entry_abi=1; initial->immutable=0;
 entry->code_block=initial->code; kd_published_images[entry-entries]=initial;
 start(1,0,0); assert(send_bytes(128)>0 && kd_code_block_free==63);
 struct kd_exec_frame old={.entry_abi=1};
 assert(kd_jit_bind_image(entry,&old) && old.image==initial);
 unsigned char saved[128]; memcpy(saved,initial->code,sizeof(saved));
 /* Bad metadata cannot replace the old executable or publish NORMAL. */
 for(int bad=0;bad<5;bad++) {
  start(2+bad,0,KD_IMAGE_REQUIRE_ADDRESS_GUARD);
  struct kd_address_guard_site *site=(void*)(packet.code+80);
  if(bad==0) packet.code[112]=0;
  if(bad==1) site->proof=0;
  if(bad==2) site->opcode[1]=0x89;
  if(bad==3) site->opcode[2]=1;
  if(bad==4) source_error=-ESTALE;
  assert(send_bytes(128)<0 && kd_image_current(entry)==initial && kd_code_block_free==63);
  source_error=0;
 }
 start(10,0,0); packet.head.status_code=KD_EXE_UNINIT;
 assert(send_bytes(64)>0);
 struct kd_image_upload stale=upload;
 memset(&upload,0,sizeof(upload));
 start(11,0,KD_IMAGE_REQUIRE_ADDRESS_GUARD); assert(send_bytes(128)>0);
 const struct kd_jit_image *guarded=kd_image_current(entry);
 assert(guarded!=initial && guarded->immutable && guarded->generation==1);
 assert(kd_code_block_free==62 && !memcmp(initial->code,saved,sizeof(saved)));
 assert(kd_jit_bind_image(entry,&old) && kd_jit_bound_code(entry,&old)==initial->code);
 struct kd_exec_frame fresh={.entry_abi=1};
 assert(kd_jit_bind_image(entry,&fresh) && fresh.image==guarded);
 upload=stale; start(10,0,0); packet.head.offset=64;
 assert(send_bytes(64)==-ESTALE && kd_image_current(entry)==guarded);
 kd_image_report(entry,initial,KD_EXE_CALL_MISS,0xdead,0);
 assert(entry->status_code==KD_EXE_NORMAL && !entry->tgt_addr);
 /* A subsequent ordinary generation cannot reopen in-place mutation. */
 start(12,1,0); assert(send_bytes(128)>0);
 const struct kd_jit_image *latest=kd_image_current(entry);
 assert(latest!=guarded && latest->immutable && latest->generation==2 && kd_code_block_free==61);
 assert(kd_jit_bound_code(entry,&fresh)==guarded->code);
 assert(((unsigned char*)guarded->code)[47]==KD_IMAGE_REQUIRE_ADDRESS_GUARD);
 kd_image_disable(guarded->entry);
 assert(entry->status_code==KD_EXE_NATIVE_ONLY);
 start(13,2,0); assert(send_bytes(128)==-EPERM);
 kd_image_report(entry,latest,KD_EXE_CALL_MISS,0xfeed,0);
 assert(entry->status_code==KD_EXE_NATIVE_ONLY && !gate);
 /* A string-only image also requires its own immutable block, without a
  * pointer-load directory. It cannot mutate the earlier ordinary frame. */
 entry=kd_get_exe(0,0x2000);
 *entry=(struct kd_exe_info){.status_code=KD_EXE_UNINIT,.RIP=0x2000,.lock_kind=1,.entry_abi=1};
 initial=kd_image_alloc(); initial->entry=entry; initial->entry_abi=1; initial->immutable=0;
 entry->code_block=initial->code; kd_published_images[entry-entries]=initial;
 start(20,0,KD_IMAGE_REQUIRE_STRING_SERVICES); packet.head.RIP=entry->RIP;
 assert(send_bytes(128)>0);
 latest=kd_image_current(entry);
 assert(latest!=initial && latest->immutable && latest->requirements==KD_IMAGE_REQUIRE_STRING_SERVICES);
 start(21,1,KD_IMAGE_REQUIRE_STRING_WRITE); packet.head.RIP=entry->RIP;
 assert(send_bytes(128)>0);
 assert(kd_image_current(entry)!=latest && kd_image_current(entry)->immutable &&
        kd_image_current(entry)->requirements==KD_IMAGE_REQUIRE_STRING_WRITE);
 for(int i=0;i<64;i++) free(allocations[i]);
 puts("spin guard images: exact trailer, stable prior image, immutable transition, stale upload/miss and terminal ban passed");
}
