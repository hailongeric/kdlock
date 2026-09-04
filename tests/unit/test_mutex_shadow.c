/*
 * test_mutex_shadow.c — verify mutex shadow-table lookup semantics.
 *
 * Unlocking a kernel mutex that never entered the kd_mutex delegation path must
 * not allocate a kd_mutex shadow entry.  Otherwise ordinary unlock traffic can
 * permanently consume slots in the fixed-size shadow table.
 */
#include "mock_kernel.h"
#include "test_harness.h"

#define KD_MUTEX_SHADOW_TABLE_SIZE 8

struct kd_mutex {
	int initialized;
};

struct kd_mutex_shadow_entry {
	unsigned long mutex_addr;
	struct kd_mutex kd_mtx;
	int delegated;
};

static struct kd_mutex_shadow_entry shadows[KD_MUTEX_SHADOW_TABLE_SIZE];

static void init_shadows(void)
{
	memset(shadows, 0, sizeof(shadows));
}

static int used_shadow_slots(void)
{
	int used = 0;
	for (int i = 0; i < KD_MUTEX_SHADOW_TABLE_SIZE; i++) {
		if (shadows[i].mutex_addr)
			used++;
	}
	return used;
}

static void kd_mutex_init(struct kd_mutex *lock)
{
	lock->initialized = 1;
}

static struct kd_mutex *get_kd_mutex_shadow(unsigned long mutex_addr)
{
	int start = mutex_addr % KD_MUTEX_SHADOW_TABLE_SIZE;
	int pos = start;

	do {
		if (shadows[pos].mutex_addr == mutex_addr)
			return &shadows[pos].kd_mtx;
		if (shadows[pos].mutex_addr == 0) {
			shadows[pos].mutex_addr = mutex_addr;
			kd_mutex_init(&shadows[pos].kd_mtx);
			return &shadows[pos].kd_mtx;
		}
		pos = (pos + 1) % KD_MUTEX_SHADOW_TABLE_SIZE;
	} while (pos != start);

	return NULL;
}

static struct kd_mutex *find_kd_mutex_shadow(unsigned long mutex_addr)
{
	int start = mutex_addr % KD_MUTEX_SHADOW_TABLE_SIZE;
	int pos = start;

	do {
		if (shadows[pos].mutex_addr == mutex_addr)
			return &shadows[pos].kd_mtx;
		if (shadows[pos].mutex_addr == 0)
			return NULL;
		pos = (pos + 1) % KD_MUTEX_SHADOW_TABLE_SIZE;
	} while (pos != start);

	return NULL;
}

TEST(lock_path_creates_shadow_entry)
{
	init_shadows();

	struct kd_mutex *shadow = get_kd_mutex_shadow(0x1000);

	ASSERT(shadow != NULL);
	ASSERT_EQ(shadow->initialized, 1);
	ASSERT_EQ(used_shadow_slots(), 1);
}

TEST(unlock_lookup_existing_entry_does_not_create_extra_entry)
{
	init_shadows();

	struct kd_mutex *created = get_kd_mutex_shadow(0x1000);
	struct kd_mutex *found = find_kd_mutex_shadow(0x1000);

	ASSERT(created != NULL);
	ASSERT_EQ(found, created);
	ASSERT_EQ(used_shadow_slots(), 1);
}

TEST(unlock_lookup_missing_entry_does_not_create_shadow_entry)
{
	init_shadows();

	struct kd_mutex *found = find_kd_mutex_shadow(0x2000);

	ASSERT_EQ(found, NULL);
	ASSERT_EQ(used_shadow_slots(), 0);
}

int main(void)
{
	printf("=== test_mutex_shadow ===\n");
	RUN_TEST(lock_path_creates_shadow_entry);
	RUN_TEST(unlock_lookup_existing_entry_does_not_create_extra_entry);
	RUN_TEST(unlock_lookup_missing_entry_does_not_create_shadow_entry);
	REPORT();
}
