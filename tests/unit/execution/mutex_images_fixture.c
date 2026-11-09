/* SPDX-License-Identifier: GPL-2.0 */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <stdint.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
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
static int kd_code_block_free, gate;
static bool source_open = true, copy_fault;
static unsigned long kd_code_block_gate_lock(void) { assert(!gate); gate = 1; return 0; }
static void kd_code_block_gate_unlock(unsigned long flags) { (void)flags;assert(gate); gate = 0; }
static bool kd_source_is_open(void) { return source_open; }
static int copy_from_user(void *d, const void *s, size_t n) {
 if(copy_fault) return 1;
 memcpy(d,s,n); return 0;
}
static int kd_source_pin_root(unsigned long ip) { return ip ? 0 : -EINVAL; }
static int copy_from_kernel_nofault(void *d, const void *s, size_t n) {
 memcpy(d,s,n); return 0;
}
struct kd_exec_frame {
 bool mutex_backend; const struct kd_jit_image *image;
 unsigned int entry_abi;
};
#include "production.h"
static struct { struct kd_recv_pkt head; unsigned char code[128]; } packet;
static struct kd_image_upload upload;
static struct kd_exe_info *entry;
static void start(unsigned long id, unsigned long generation, unsigned int req) {
 memset(&packet,0,sizeof(packet));
 packet.head=(struct kd_recv_pkt){.status_code=KD_EXE_NORMAL,.RIP=0x1000,
  .version=kd_image_protocol(req),.entry_abi=2,.requirements=req,
  .image_length=128,.upload_id=id,.base_generation=generation};
 memcpy(packet.code+9,"KDWB002",7); memcpy(packet.code+25,"KDWC002",7);
 memcpy(packet.code+41,"KDAB",4); packet.code[45]=2; packet.code[46]=2;
 packet.code[46]=kd_image_protocol(req);
 packet.code[47]=req & 0xff;
 if(kd_image_protocol(req)==KD_IMAGE_PROTOCOL_SERVICE_QUEUE)
  for(unsigned int i=0;i<4;i++) packet.code[48+i]=(req >> (8*i)) & 0xff;
}
static ssize_t send_bytes(size_t n) {
 ssize_t ret=kd_dev_write_locked(&upload,(const char *)&packet,sizeof(packet.head)+n);
 if(ret<0) { kd_image_discard(upload.image); upload.image=NULL; upload.covered=0; }
 return ret;
}
static void start_service(unsigned long id, unsigned long generation) {
 const unsigned int req=KD_IMAGE_REQUIRE_SERVICE_QUEUE | KD_IMAGE_REQUIRE_BUDGET_RESUME;
 start(id,generation,req);
 packet.head.version=KD_IMAGE_PROTOCOL_SERVICE_QUEUE;
 packet.code[KD_IMAGE_VERSION_OFFSET]=KD_IMAGE_PROTOCOL_SERVICE_QUEUE;
 packet.code[KD_IMAGE_REQUIREMENTS_OFFSET]=req & 0xff;
 for(unsigned int i=0;i<4;i++)
  packet.code[KD_IMAGE_FULL_REQUIREMENTS_OFFSET+i]=(req >> (8*i)) & 0xff;
}
int main(void) {
 for(int i=0;i<KD_MAX_EXE;i++) entries[i].status_code=KD_EXE_UNUSED;
 for(int i=0;i<64;i++) allocations[i]=kd_code_block_pool[kd_code_block_free++]=calloc(1,KD_CODE_BLOCK_SIZE);
 entry=kd_get_exe(0,0x1000);
 *entry=(struct kd_exe_info){.status_code=KD_EXE_UNINIT,.RIP=0x1000,.lock_kind=2,.entry_abi=2};
 start(1,0,0); assert(send_bytes(128)>0);
 const struct kd_jit_image *old=kd_image_current(entry);
 assert(old && old->generation==1 && !old->requirements && kd_code_block_free==63);
 struct kd_exec_frame bound={.mutex_backend=true,.entry_abi=2};
 assert(kd_jit_bind_image(entry,&bound) && bound.image==old);
 unsigned char saved[128]; memcpy(saved,old->code,128);
 start(2,1,0); packet.head.status_code=KD_EXE_UNINIT;
 assert(send_bytes(64)>0); assert(kd_image_current(entry)==old);
 assert(!memcmp(old->code,saved,128));
 packet.head.offset=65; packet.head.status_code=KD_EXE_NORMAL;
 assert(send_bytes(63)==-EINVAL); assert(kd_code_block_free==63);
 start(3,1,0); packet.head.status_code=KD_EXE_UNINIT; assert(send_bytes(64)>0);
 packet.head.offset=64; packet.head.status_code=KD_EXE_NORMAL; packet.head.upload_id++;
 assert(send_bytes(64)==-ESTALE); assert(kd_image_current(entry)==old);
 start(4,1,0); packet.code[47]=1;
 assert(send_bytes(128)==-EPROTO); assert(kd_image_current(entry)==old);
 start(5,1,0); copy_fault=true; assert(send_bytes(128)==-EFAULT); copy_fault=false;
 start(6,1,0); assert(send_bytes(128)>0);
 const struct kd_jit_image *new=kd_image_current(entry);
 assert(new!=old && new->requirements==0 && new->generation==2);
 assert(kd_jit_bind_image(entry,&bound) && kd_jit_bound_code(entry,&bound)==old->code);
 struct kd_exec_frame fresh={.mutex_backend=true,.entry_abi=2};
 assert(kd_jit_bind_image(entry,&fresh) && fresh.image==new);
 fresh.entry_abi=1; assert(!kd_jit_bind_image(entry,&fresh));
 fresh.entry_abi=2;
 start(7,2,2); assert(send_bytes(128)==-EPROTO);
 assert(!memcmp(old->code,saved,128));
 kd_image_report(entry,old,KD_EXE_CALL_MISS,0xdead,0);
 assert(entry->status_code==KD_EXE_NORMAL && !entry->tgt_addr);
 kd_image_report(entry,new,KD_EXE_IJ_MISS,0xbeef,0xabcd);
 assert(entry->status_code==KD_EXE_IJ_MISS && entry->tgt_addr==0xbeef && entry->jump_from==0xabcd);
 start(7,1,0); assert(send_bytes(128)==-ESTALE);
 start(8,2,0); packet.head.version=1; assert(send_bytes(128)==-EPROTO);
 start(9,2,0); packet.head.image_length=47; assert(send_bytes(47)==-EINVAL);
 /* The instruction-marker requirement is restricted to matching ABI2 mutex
  * images; unrelated/older entries cannot silently accept that contract. */
 assert(!kd_image_requirements_valid(KD_EXE_LOCK_SPIN,1,KD_IMAGE_REQUIRE_NATIVE_ESCAPE));
 assert(!kd_image_requirements_valid(KD_EXE_LOCK_MUTEX,0,KD_IMAGE_REQUIRE_NATIVE_ESCAPE));
 /* Root markers use exactly the paired requirement on ABI1/3 spin objects.
  * No mixed optional service/guard contract or foreign backend is implied. */
 for(unsigned int kind=1;kind<=2;kind++)
  for(unsigned int abi=0;abi<=3;abi++)
   for(unsigned int req=32;req<64;req++)
    assert(!!kd_image_requirements_valid(kind,abi,req) ==
           (kind==KD_EXE_LOCK_SPIN && (abi==1 || abi==3) && req==33));
 start(10,2,KD_IMAGE_REQUIRE_NATIVE_ESCAPE); assert(send_bytes(128)>0);
 fresh.image=NULL;
 assert(kd_jit_bind_image(entry,&fresh) && fresh.image->requirements==KD_IMAGE_REQUIRE_NATIVE_ESCAPE);
 start_service(11,3); assert(send_bytes(128)>0);
 const struct kd_jit_image *service=kd_image_current(entry);
 assert(service->generation==4 && service->requirements==384);
 fresh.image=NULL;
 assert(!kd_jit_bind_image(entry,&fresh) && !fresh.image);
 fixture_service_frame=true;
 assert(kd_jit_bind_image(entry,&fresh) && fresh.image==service);
 fixture_service_frame=false;
 fresh.image=NULL;
 start_service(12,4); packet.head.version=KD_IMAGE_PROTOCOL;
 assert(send_bytes(128)==-EPROTO);
 start_service(13,4); packet.code[KD_IMAGE_REQUIREMENTS_OFFSET]=0;
 assert(send_bytes(128)==-EPROTO);
 start_service(14,4); packet.code[KD_IMAGE_FULL_REQUIREMENTS_OFFSET+1]=0;
 assert(send_bytes(128)==-EPROTO);
 start_service(15,4); packet.head.image_length=63;
 assert(send_bytes(63)==-EINVAL);
 assert(!kd_image_requirements_valid(KD_EXE_LOCK_SPIN,1,KD_IMAGE_REQUIRE_SERVICE_QUEUE));
 assert(!kd_image_requirements_valid(KD_EXE_LOCK_MUTEX,0,KD_IMAGE_REQUIRE_SERVICE_QUEUE));
 assert(!kd_image_requirements_valid(KD_EXE_LOCK_MUTEX,2,
  KD_IMAGE_REQUIRE_SERVICE_QUEUE | KD_IMAGE_REQUIRE_NATIVE_ESCAPE));
 /* A cold ABI2 image has a full handback word without a SERVICE_QUEUE bit. */
 start(16,4,KD_IMAGE_REQUIRE_RETAINED_MISS); assert(send_bytes(128)>0);
 const struct kd_jit_image *cold=kd_image_current(entry);
 assert(cold->generation==5 && cold->requirements==KD_IMAGE_REQUIRE_RETAINED_MISS);
 assert(packet.head.version==KD_IMAGE_PROTOCOL_SERVICE_QUEUE);
 fresh.image=NULL;
 assert(kd_jit_bind_image(entry,&fresh) && fresh.image==cold);
 for(unsigned int gen=5;gen<64;gen++) { start(gen+20,gen,0); assert(send_bytes(128)>0); }
 const struct kd_jit_image *last=kd_image_current(entry);
 start(100,64,0); assert(send_bytes(128)==-ENOSPC);
 assert(kd_image_current(entry)==last && last->generation==64);
 assert(!memcmp(old->code,saved,128));
 /* A marker in an old bound image bans the stable entry, including an upload
  * which was staged before the ban. Publication and ban use the same gate. */
 struct kd_jit_image pending={.code=packet.code,.entry_abi=2};
 kd_image_disable(old->entry);
 assert(entry->status_code==KD_EXE_NATIVE_ONLY && !gate);
 assert(kd_image_publish(entry,&pending,64)==-ESHUTDOWN);
 assert(!pending.entry && kd_image_current(entry)==last);
 kd_image_report(entry,last,KD_EXE_CALL_MISS,0xfeed,0);
 assert(entry->status_code==KD_EXE_NATIVE_ONLY);
 assert(kd_jit_bound_code(entry,&bound)==old->code && !memcmp(old->code,saved,128));
 start(101,64,0); assert(send_bytes(128)==-EPERM);
 source_open=false; assert(send_bytes(128)==-ESHUTDOWN);
 for(int i=0;i<64;i++) free(allocations[i]);
 puts("mutex images: immutable replacement, marker contract, terminal ban, stale misses and 64-block exhaustion passed");
}
