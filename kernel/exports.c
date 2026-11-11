// SPDX-License-Identifier: GPL-2.0-only
/* Narrow source-rebuilt provider and ordinary mutex module boundary. */
#include <linux/export.h>

#include "mutex_api.h"
#include "runtime.h"
#include "source_provider.h"
#include "task_storage.h"
#include "lifecycle.h"

EXPORT_SYMBOL_GPL(kd_mutex_init);
EXPORT_SYMBOL_GPL(kd_mutex_lock_entry_asm);
EXPORT_SYMBOL_GPL(kd_mutex_unlock_entry_asm);
EXPORT_SYMBOL_GPL(kd_spin_init);
EXPORT_SYMBOL_GPL(kd_spin_lock_entry_asm);
EXPORT_SYMBOL_GPL(kd_spin_unlock_entry_asm);
EXPORT_SYMBOL_GPL(kd_rwsem_init);
EXPORT_SYMBOL_GPL(kd_rwsem_down_read_entry_asm);
EXPORT_SYMBOL_GPL(kd_rwsem_up_read_entry_asm);
EXPORT_SYMBOL_GPL(kd_rwsem_down_write_entry_asm);
EXPORT_SYMBOL_GPL(kd_rwsem_up_write_entry_asm);
EXPORT_SYMBOL_GPL(kd_rwsem_downgrade_write_entry_asm);
EXPORT_SYMBOL_GPL(kd_rwlock_init);
EXPORT_SYMBOL_GPL(kd_rwlock_read_lock_entry_asm);
EXPORT_SYMBOL_GPL(kd_rwlock_read_unlock_entry_asm);
EXPORT_SYMBOL_GPL(kd_rwlock_write_lock_entry_asm);
EXPORT_SYMBOL_GPL(kd_rwlock_write_unlock_entry_asm);
EXPORT_SYMBOL_GPL(kd_jit_source_provider_create);
EXPORT_SYMBOL_GPL(kd_jit_source_provider_close);
EXPORT_SYMBOL_GPL(kd_jit_source_provider_destroy);
EXPORT_SYMBOL_GPL(kd_jit_source_native_begin);
EXPORT_SYMBOL_GPL(kd_jit_source_native_release);
EXPORT_SYMBOL_GPL(kd_jit_runtime_create);
EXPORT_SYMBOL_GPL(kd_jit_runtime_enter_current);
EXPORT_SYMBOL_GPL(kd_jit_runtime_leave_current);
EXPORT_SYMBOL_GPL(kd_jit_runtime_destroy);
EXPORT_SYMBOL_GPL(kd_task_storage_root);
EXPORT_SYMBOL_GPL(kd_task_lifecycle_start_current);
EXPORT_SYMBOL_GPL(kd_task_lifecycle_exit_current);
