#ifndef KD_SOURCE_H
#define KD_SOURCE_H

/* Internal residency/retirement API. Root and native target pins require text;
 * read-range pins can include resident data. A frame get/put spans the entire
 * native/remote suffix, independently of userspace writer descriptions. */
#include <linux/types.h>
#include <linux/compiler.h>
#include "kd_source_api.h"

/* Internal to the provider (not exported). Lifecycle/dependency mutations use
 * the source lock. frames is filled only in kd_source_info() from the atomic
 * admission/count word; do not read kd_sources.frames. This readiness hint is
 * revalidated by frame admission, which linearizes against session closure. */
extern struct kd_source_info kd_sources;
static __always_inline bool kd_source_is_open(void)
{
	return READ_ONCE(kd_sources.state) == KD_SOURCE_OPEN;
}

int kd_source_init(void);
void kd_source_exit(void);
bool kd_source_writer_get(void);
void kd_source_writer_put(void);
/* Immutable bound objects may make future calls after an individual root
 * retires. Their matched leases prevent source closure, not just text free. */
bool kd_source_binding_get(void);
void kd_source_binding_put(void);
u64 kd_source_binding_count(void);
bool kd_source_frame_get(void);
void kd_source_frame_put(void);
int kd_source_pin_root(unsigned long address);
int kd_source_pin_range(unsigned long address, unsigned long size);
int kd_source_pin_target(unsigned long address);
/* Reached decoding needs every fetched instruction byte retained as text.
 * Existing frame admission remains valid while source admission is draining. */
int kd_source_pin_text_range(unsigned long address, unsigned long size);
void kd_source_info(struct kd_source_info *info);
int kd_source_begin_retire(void);
void kd_source_finish_retire(void);

#endif
