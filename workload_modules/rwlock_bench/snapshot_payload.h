/* SPDX-License-Identifier: GPL-2.0 */
/* Extracted from __get_task_comm and get_mm_cmdline in Linux 6.1.159.
 * References/lifetime and procfs I/O stay outside this synthetic lock test.
 * Optional mutations stress snapshot consistency; the performance profile is
 * read-only, like many concurrent ps readers of one task/mm. */
#include <linux/string.h>
struct rb_slot { u64 value; } __aligned(64);
static struct rb_slot rb_values[RB_SLOTS];

#ifdef RB_TASKNAME
static char rb_comm[16] __aligned(64) = "aaaaaaaaaaaaaaa";

static __attribute__((noipa)) bool rb_read(void)
{
	char result[64];
	unsigned int i, length = 0;
	bool bad = false;
	char first;
	RB_READ_LOCK();
	strscpy_pad(result, rb_comm, sizeof(result));
	RB_READ_UNLOCK();
	/* Validate every destination byte after unlock, without another shared
	 * access. Both short and maximum-length names must be fully padded. */
	first = result[0];
	bad |= first < 'a' || first > 'z';
	while (length < sizeof(result) && result[length]) {
		bad |= result[length] != first;
		length++;
	}
	bad |= length != 3 && length != 15;
	for (i = length; i < sizeof(result); i++)
		bad |= result[i] != 0;
	return bad;
}

static __attribute__((noipa)) void rb_write(void)
{
	u64 generation;
	unsigned int i, length;
	char value;
	RB_WRITE_LOCK();
	generation = ++rb_values[0].value;
	length = generation & 1 ? 3 : 15;
	value = 'a' + generation % 26;
	for (i = 0; i < sizeof(rb_comm); i++)
		WRITE_ONCE(rb_comm[i], i < length ? value : 0);
	RB_WRITE_UNLOCK();
}
#else
static unsigned long rb_args[4] __aligned(64) = { 0x1000, 0x1100, 0x1200, 0x1300 };

static __attribute__((noipa)) bool rb_read(void)
{
	unsigned long arg_start, arg_end, env_start, env_end;
	RB_READ_LOCK();
	arg_start = READ_ONCE(rb_args[0]);
	arg_end = READ_ONCE(rb_args[1]);
	env_start = READ_ONCE(rb_args[2]);
	env_end = READ_ONCE(rb_args[3]);
	RB_READ_UNLOCK();
	return !arg_start || (arg_start & 4095) || arg_end != arg_start + 0x100 ||
		env_start != arg_start + 0x200 || env_end != arg_start + 0x300;
}

static __attribute__((noipa)) void rb_write(void)
{
	unsigned long start;
	RB_WRITE_LOCK();
	start = (++rb_values[0].value + 1) << 12;
	WRITE_ONCE(rb_args[0], start);
	WRITE_ONCE(rb_args[1], start + 0x100);
	WRITE_ONCE(rb_args[2], start + 0x200);
	WRITE_ONCE(rb_args[3], start + 0x300);
	RB_WRITE_UNLOCK();
}
#endif
