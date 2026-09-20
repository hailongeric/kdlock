/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_HOTLOCK_H
#define KD_HOTLOCK_H
#include <linux/types.h>
#define KD_HOTLOCK_LOCAL_HASH_V2 1
int kd_hotlock_init(void);
void kd_hotlock_exit(void);
/* CPU pin is confined to this call. No returned value conveys ownership.
 * record returns policy admission; query reports actual local heat only. */
bool kd_hotlock_record_spin(unsigned long address);
bool kd_hotlock_record_mutex(unsigned long address);
bool kd_hotlock_query_spin(unsigned long address);
bool kd_hotlock_query_mutex(unsigned long address);

#ifdef KDLOCK_SELFTEST
int kd_hotlock_lifetime_check(void);
#endif
#endif
