/* SPDX-License-Identifier: GPL-2.0 */
/* Production private upload/validator/publication, with source lease and
 * allocator primitives. No archived or uploaded generated code executes. */
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
#define smp_load_acquire(p) __atomic_load_n(p,__ATOMIC_ACQUIRE)
#define smp_store_release(p,v) __atomic_store_n(p,v,__ATOMIC_RELEASE)
#define try_cmpxchg(p,o,v) __atomic_compare_exchange_n(p,o,v,0,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST)
#define BUG_ON(x) assert(!(x))
#define __user
#define KD_PR_INFO(...) do {} while (0)
#define KD_PR_ERR(...) do {} while (0)
#include "image_direct_support.h"
static struct kd_exe_info entries[KD_MAX_EXE], *kd_exes = entries;
static struct kd_jit_image kd_images[64];
static const struct kd_jit_image *kd_published_images[KD_MAX_EXE];
static void *kd_code_block_pool[64], *allocations[64];
static int kd_code_block_free, gate, source_error;
static unsigned long pinned[4];
static unsigned int source_calls;
static bool source_open = true, text_fault;
static unsigned long kd_code_block_gate_lock(void) { assert(!gate); gate = 1; return 0; }
static void kd_code_block_gate_unlock(unsigned long flags) { (void)flags; assert(gate); gate = 0; }
static bool kd_source_is_open(void) { return source_open; }
static int copy_from_user(void *d,const void *s,size_t n) { memcpy(d,s,n); return 0; }
static int kd_source_pin_root(unsigned long ip) {
    assert(source_calls < 4); pinned[source_calls++] = ip;
    return source_error;
}
static int copy_from_kernel_nofault(void *d,const void *s,size_t n) {
    if (text_fault) return -EFAULT;
    memcpy(d,s,n); return 0;
}
struct kd_exec_frame { bool mutex_backend; const struct kd_jit_image *image; unsigned int entry_abi; };
#include "production.h"
static struct { struct kd_recv_pkt head; unsigned char code[160]; } packet;
static struct kd_image_upload upload;
static unsigned char source_opcode[2][4] = {{0x0f,0x31,0x90}, {0x0f,0x01,0xf9,0x90}};
static struct kd_exe_info *entry;
static struct kd_origin_site *start(unsigned long generation)
{
    memset(&packet,0,sizeof(packet)); source_calls = 0; source_error = 0; text_fault = false;
    packet.head = (struct kd_recv_pkt){ .status_code = KD_EXE_NORMAL, .RIP = 0x1000,
        .version = KD_IMAGE_PROTOCOL, .entry_abi = 2, .requirements = 65,
        .image_length = sizeof(packet.code), .upload_id = generation + 1, .base_generation = generation };
    memcpy(packet.code+9,"KDWB002",7); memcpy(packet.code+25,"KDWC002",7);
    memcpy(packet.code+41,"KDAB",4); packet.code[45]=2; packet.code[46]=2; packet.code[47]=65;
    struct kd_origin_site *sites = (void *)(packet.code+80);
    for (unsigned int i=0;i<2;i++) {
        sites[i] = (struct kd_origin_site){ .ip = (unsigned long)source_opcode[i],
            .next_ip = (unsigned long)source_opcode[i] + 2 + i,
            .continuation_offset = 64 + 8*i, .kind = i+1, .length = 2+i };
        memcpy(sites[i].opcode,source_opcode[i],2+i);
    }
    struct kd_origin_footer *footer = (void *)(packet.code+144);
    memcpy(footer->magic,"KDOS0001",8); footer->offset=80; footer->count=2;
    return sites;
}
static ssize_t send_packet(void)
{
    ssize_t ret = kd_dev_write_locked(&upload,(const char *)&packet,sizeof(packet));
    if (ret < 0) { kd_image_discard(upload.image); upload.image=NULL; upload.covered=0; }
    return ret;
}
int main(void)
{
    assert(sizeof(struct kd_origin_site)==32 && sizeof(struct kd_origin_footer)==16);
    for (int i=0;i<KD_MAX_EXE;i++) entries[i].status_code=KD_EXE_UNUSED;
    for (int i=0;i<64;i++) allocations[i]=kd_code_block_pool[kd_code_block_free++]=calloc(1,KD_CODE_BLOCK_SIZE);
    entry=kd_get_exe(0,0x1000);
    *entry=(struct kd_exe_info){.status_code=KD_EXE_UNINIT,.RIP=0x1000,.lock_kind=2,.entry_abi=2};
    for (unsigned int kind=1;kind<=2;kind++)
        for (unsigned int abi=0;abi<=3;abi++)
            for (unsigned int req=64;req<128;req++)
                assert(!!kd_image_requirements_valid(kind,abi,req)==(kind==2 && abi==2 && req==65));
    for (unsigned int bad=0;bad<14;bad++) {
        struct kd_origin_site *site=start(0);
        struct kd_origin_footer *footer=(void *)(packet.code+144);
        switch (bad) {
        case 0: footer->magic[0]=0; break;
        case 1: footer->count=65; break;
        case 2: footer->offset=48; break;
        case 3: site[0].reserved[0]=1; break;
        case 4: site[0].next_ip++; break;
        case 5: site[0].continuation_offset=47; break;
        case 6: site[0].continuation_offset=80; break;
        case 7: site[0].opcode[0]=0x66; break;
        case 8: site[0].opcode[7]=1; break;
        case 9: site[1]=site[0]; break;
        case 10: source_error=-ESTALE; break;
        case 11: text_fault=true; break;
        case 12: source_opcode[0][1]=0xa2; break;
        case 13: site[0].kind=3; break;
        }
        assert(send_packet()<0 && !kd_image_current(entry) && kd_code_block_free==64);
        source_opcode[0][1]=0x31;
    }
    start(0); assert(send_packet()>0);
    const struct kd_jit_image *old=kd_image_current(entry);
    assert(old && old->immutable && old->generation==1 && old->requirements==65);
    assert(source_calls==4 && pinned[0]==(unsigned long)source_opcode[0] &&
           pinned[1]==(unsigned long)source_opcode[0]+2 &&
           pinned[2]==(unsigned long)source_opcode[1] && pinned[3]==(unsigned long)source_opcode[1]+3);
    struct kd_exec_frame bound={.mutex_backend=true,.entry_abi=2};
    assert(kd_jit_bind_image(entry,&bound) && bound.image==old);
    unsigned char saved[160]; memcpy(saved,old->code,sizeof(saved));
    start(1); assert(send_packet()>0 && kd_image_current(entry)!=old);
    assert(kd_jit_bind_image(entry,&bound) && kd_jit_bound_code(entry,&bound)==old->code);
    assert(!memcmp(saved,old->code,sizeof(saved)) && kd_code_block_free==62);
    for (int i=0;i<64;i++) free(allocations[i]);
    puts("origin images: exact opcode/successor directory, source pins, malformed upload refusal and immutable generation retention passed");
    return 0;
}
