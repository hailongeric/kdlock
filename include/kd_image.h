/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_IMAGE_H
#define KD_IMAGE_H
#include "exe_info.h"

/* Construct privately, then publish once. Published descriptors and executable
 * blocks survive every frame/continuation until terminal session teardown. */
struct kd_jit_image {
	void *code;
	unsigned long length;
	unsigned long generation;
	unsigned int requirements;
	unsigned int entry_abi;
	struct kd_exe_info *entry;
};

struct kd_image_upload {
	struct kd_jit_image *image;
	struct kd_recv_pkt identity;
	unsigned long covered;
};

struct kd_jit_image *kd_image_alloc(void);
void kd_image_discard(struct kd_jit_image *image);
int kd_image_publish(struct kd_exe_info *entry, struct kd_jit_image *image,
		     unsigned long base_generation);
const struct kd_jit_image *kd_image_current(const struct kd_exe_info *entry);
void kd_image_report(struct kd_exe_info *entry, const struct kd_jit_image *image,
		     int status, unsigned long target, unsigned long from);
void kd_exe_snapshot(const struct kd_exe_info *entry, struct kd_exe_info *snapshot);
#endif
