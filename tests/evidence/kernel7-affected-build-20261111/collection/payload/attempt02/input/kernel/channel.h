/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_CHANNEL_H
#define KDLOCK_CHANNEL_H

#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include "../include/kd_control.h"

struct kd_jit_control_session;

/* One persistent configured control session per device and one open fd at a
 * time. These controls and buffers survive fd close and reconnect. The provider
 * retains session/source/image/native dependencies independently; registration
 * does not freeze source or grant code execution. No S_W lookup occurs here.
 */
struct kd_jit_channel {
	struct miscdevice device;
	struct mutex guard;
	struct kd_jit_control_session *session;
	struct module *owner;
	unsigned char *input;
	unsigned char *next_input;
	unsigned char *output;
	size_t frame_capacity;
	size_t input_length;
	size_t output_length;
	u64 sequence;
	u64 operation;
	s64 status;
	bool cached;
	bool opened;
	bool retained;
	bool closing;
	bool registered;
};

/* Fresh private channel, initialized session and immutable name/backing. An
 * explicit finite frame_capacity covers every command/reply; no default count.
 * Allocations occur here, outside source execution. Mode is 0600. owner may be
 * NULL for a built-in provider; loadable-provider control/callback backing must
 * additionally survive all independent source/image/native users. An open fd
 * holds owner, and close preserves that hold if the session is not fully idle.
 */
int kd_jit_channel_register(struct kd_jit_channel *channel, const char *name,
		struct module *owner, struct kd_jit_control_session *session,
		size_t frame_capacity);
/* Caller already stopped provider admission and drained all independent users.
 * Refuse an open fd or non-idle session. A retained disconnected owner hold is
 * dropped only after deregistration and the final channel/backing access. Never
 * force close, discard pending facts or infer provider drain from fd absence.
 */
int kd_jit_channel_unregister(struct kd_jit_channel *channel);

#endif
