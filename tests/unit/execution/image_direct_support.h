/* Primitive substitutes for production immutable-image publication fixtures.
 * Relocation validation and actual private code patching remain production. */
#include "kd_hostcall.h"
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
static void *kd_near_block_pool[64], *kd_near_block_allocations[64];
static int kd_near_block_free;
static struct {
 enum kd_hostcall_id id;
 unsigned long addr;
} kd_hostcalls[] = {
 { KD_HOSTCALL_STRCMP, 0 }, { KD_HOSTCALL_STRSCPY_PAD, 0 }
};
static unsigned int get_unaligned_le32(const void *source) {
 unsigned int result;
 memcpy(&result, source, sizeof(result));
 return result;
}

/* This fixture does not execute declared Native helpers. */
static inline int kd_service_calls_pin(void) { return 0; }

int kd_image_validate_memory_sites(const struct kd_jit_image *image)
{
 /* Memory-instruction tables have a separate production-validator fixture. */
 assert(!(image->requirements & KD_IMAGE_REQUIRE_ORIGIN_MEMORY));
 return 0;
}
