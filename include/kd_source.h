#ifndef KD_SOURCE_H
#define KD_SOURCE_H

/* Internal residency/retirement API. Root and native target pins require text;
 * read-range pins can include resident data. A frame get/put spans the entire
 * native/remote suffix, independently of userspace writer descriptions. */
#include <linux/types.h>
#include <linux/compiler.h>
#include "kd_source_api.h"

/* Internal to the provider (not exported). Mutations remain under the source
 * lock in kd_source.c. Inline this read of the same state, rather than adding
 * an independently synchronized admission flag to every hot hook. */
extern struct kd_source_info kd_sources;
static __always_inline bool kd_source_is_open(void)
{
	return READ_ONCE(kd_sources.state) == KD_SOURCE_OPEN;
}

int kd_source_init(void);
void kd_source_exit(void);
bool kd_source_writer_get(void);
void kd_source_writer_put(void);
bool kd_source_frame_get(void);
void kd_source_frame_put(void);
int kd_source_pin_root(unsigned long address);
int kd_source_pin_range(unsigned long address, unsigned long size);
int kd_source_pin_target(unsigned long address);
void kd_source_info(struct kd_source_info *info);
int kd_source_begin_retire(void);
void kd_source_finish_retire(void);

#endif
