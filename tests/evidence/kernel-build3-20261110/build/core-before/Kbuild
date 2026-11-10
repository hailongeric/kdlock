# SPDX-License-Identifier: GPL-2.0-only
# One in-tree built-in group; CONFIG_KDLOCK_REBUILD is a bool.
obj-$(CONFIG_KDLOCK_REBUILD) += kdlock_rebuild.o

# Apply target gates to C only; assembly retains the kernel's normal flags.
ccflags-y += -I$(src) -I$(src)/include -include $(src)/kernel/target.h
asflags-y += -I$(src)/include

# Keep this explicit list in sync with the private runtime C units.
kdlock_rebuild-y := \
	kernel/mutex.o \
	kernel/mutex_release.o \
	kernel/state.o \
	kernel/task_state.o \
	kernel/request_pool.o \
	kernel/owner_progress.o \
	kernel/source_epoch.o \
	kernel/source_provider.o \
	kernel/feedback.o \
	kernel/feedback_publish.o \
	kernel/control.o \
	kernel/channel.o \
	kernel/compiled_image.o \
	kernel/runtime.o \
	kernel/exports.o \
	kernel/image.o \
	kernel/image_owner.o \
	kernel/jit.o \
	kernel/native_entry.o \
	kernel/episode.o \
	kernel/mutex_api.o \
	kernel/task_progress.o \
	kernel/task_setup.o \
	kernel/task_storage.o \
	kernel/lifecycle.o \
	kernel/source_stack.o \
	include/mutex_api.o \
	include/mutex_entry.o \
	include/native_resume.o

# include/wrapper.S is an unexpanded per-image template, never a core object.
# Generated image assembly/metadata has its own caller-owned build/provider.
