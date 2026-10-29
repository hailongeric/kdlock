/* Userspace ABI test of the actual selected-call macros and tail bridges.
 * It proves forwarding/spills only, not physical KD locking or kernel context. */
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
typedef uint32_t u32;
typedef uint32_t __u32;
typedef int32_t __s32;
typedef uint64_t __u64;
typedef struct { int word; } spinlock_t;
struct mutex { unsigned long words[4]; };
typedef struct { int word; } kd_spinlock_t;
struct kd_mutex { unsigned long words[4]; };
#include "api_types.h"
struct files_struct { kd_api_spinlock_t file_lock; const struct kd_api_provider *kd_lock_provider; };
struct pipe_inode_info { kd_api_mutex_t mutex; const struct kd_api_provider *kd_lock_provider; };
register unsigned long current_stack_pointer asm("rsp");
#include <linux/kd_api_lock.h>

unsigned long captured[7];
extern void fixture_spin_lock(kd_spinlock_t *, unsigned long, unsigned long, unsigned long);
extern void fixture_spin_unlock(kd_spinlock_t *, unsigned long, unsigned long, unsigned long);
extern void fixture_mutex_lock(struct kd_mutex *, unsigned long, unsigned long, unsigned long);
extern void fixture_mutex_unlock(struct kd_mutex *, unsigned long, unsigned long, unsigned long);
extern void fixture_mutex_local(struct kd_mutex *);
static unsigned int checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr,"FAIL %d %s\n",__LINE__,#x); exit(1); } } while (0)
static void verify(unsigned long target, void *word)
{
	CHECK(captured[0] == target);
	CHECK(captured[1] == (unsigned long)word);
	CHECK(captured[2] == captured[5] + 8); /* no intermediate C/tail frame */
	CHECK(captured[3] == captured[6]); /* captured continuation == actual CALL word */
	CHECK(captured[4] != 0);
}

int main(void)
{
	const struct kd_api_provider ops = {.spin_lock = fixture_spin_lock,
		.spin_unlock = fixture_spin_unlock, .mutex_lock = fixture_mutex_lock,
		.mutex_unlock = fixture_mutex_unlock, .mutex_local_lock = fixture_mutex_local};
	struct files_struct files = {.kd_lock_provider = &ops};
	struct pipe_inode_info pipe = {.kd_lock_provider = &ops};
	KD_API_FILES_LOCK(&files); verify(1, &files.file_lock);
	KD_API_FILES_UNLOCK(&files); verify(2, &files.file_lock);
	KD_API_PIPE_LOCK(&pipe, 1, 2); verify(3, &pipe.mutex);
	KD_API_PIPE_UNLOCK(&pipe); verify(4, &pipe.mutex);
	KD_API_PIPE_LOCK(&pipe, 0, 3); verify(5, &pipe.mutex);
	KD_API_PIPE_UNLOCK(&pipe); verify(4, &pipe.mutex);
	files.kd_lock_provider = NULL;
	pipe.kd_lock_provider = NULL;
	KD_API_FILES_LOCK(&files); verify(10, &files.file_lock);
	KD_API_FILES_UNLOCK(&files); verify(11, &files.file_lock);
	KD_API_PIPE_LOCK(&pipe, 1, 2); verify(12, &pipe.mutex);
	KD_API_PIPE_UNLOCK(&pipe); verify(13, &pipe.mutex);
	KD_API_PIPE_LOCK(&pipe, 0, 3); verify(12, &pipe.mutex);
	printf("tail bridge checks=%u\n", checks);
	return 0;
}
