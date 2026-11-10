#include <linux/module.h>
#include <linux/export-internal.h>
#include <linux/compiler.h>

MODULE_INFO(name, KBUILD_MODNAME);

__visible struct module __this_module
__section(".gnu.linkonce.this_module") = {
	.name = KBUILD_MODNAME,
	.init = init_module,
#ifdef CONFIG_MODULE_UNLOAD
	.exit = cleanup_module,
#endif
	.arch = MODULE_ARCH_INIT,
};



static const struct modversion_info ____versions[]
__used __section("__versions") = {
	{ 0x40a621c5, "scnprintf" },
	{ 0x6874e31b, "kd_jit_runtime_leave_current" },
	{ 0x28311fd0, "kd_jit_runtime_create" },
	{ 0xcb8b6ec6, "kfree" },
	{ 0x6ac784f4, "schedule_timeout_interruptible" },
	{ 0x5e505530, "kthread_should_stop" },
	{ 0xda9d005d, "kd_jit_runtime_destroy" },
	{ 0xd27020bd, "kd_jit_source_provider_create" },
	{ 0xc230afd5, "wake_up_process" },
	{ 0x5a844b26, "__x86_indirect_thunk_rax" },
	{ 0xbd03ed67, "__ref_stack_chk_guard" },
	{ 0xd272d446, "__stack_chk_fail" },
	{ 0xff0106da, "refcount_warn_saturate" },
	{ 0x9479a1e8, "strnlen" },
	{ 0x2475f1fb, "kd_mutex_init" },
	{ 0x90a48d82, "__ubsan_handle_out_of_bounds" },
	{ 0x952f9665, "kd_jit_runtime_enter_current" },
	{ 0x8b3bd1e5, "kd_task_storage_root" },
	{ 0xbd03ed67, "random_kmalloc_seed" },
	{ 0x9aa6980d, "mutex_lock" },
	{ 0xf42bccd1, "const_current_task" },
	{ 0x2a280842, "kthread_stop" },
	{ 0x173ec8da, "sscanf" },
	{ 0xe54e0a6b, "__fortify_panic" },
	{ 0x9dd6ec3d, "default_llseek" },
	{ 0x06237697, "kd_jit_source_provider_destroy" },
	{ 0x48dcca1c, "misc_register" },
	{ 0x92495a4d, "param_ops_charp" },
	{ 0x62cbec20, "wait_for_completion" },
	{ 0xd272d446, "__x86_return_thunk" },
	{ 0x62cbec20, "complete_all" },
	{ 0x775eeed4, "kthread_create_on_node" },
	{ 0x5ea962e6, "pv_ops" },
	{ 0x06237697, "kd_jit_source_provider_close" },
	{ 0x7ec472ba, "__preempt_count" },
	{ 0xb9fcd065, "call_rcu" },
	{ 0x9aa6980d, "mutex_unlock" },
	{ 0x92495a4d, "param_ops_bool" },
	{ 0xfe16dc1b, "__kmalloc_cache_noprof" },
	{ 0x5cb46e6d, "validate_usercopy_range" },
	{ 0xe298e85d, "kd_mutex_lock_entry_asm" },
	{ 0x7851be11, "__SCT__cond_resched" },
	{ 0x1cf09ab5, "__put_task_struct_rcu_cb" },
	{ 0xe4de56b4, "__ubsan_handle_load_invalid_value" },
	{ 0x43a349ca, "strlen" },
	{ 0xe298e85d, "kd_mutex_unlock_entry_asm" },
	{ 0x437e81c7, "simple_read_from_buffer" },
	{ 0xd272d446, "BUG_func" },
	{ 0x8e167a49, "kmalloc_caches" },
	{ 0xa61fd7aa, "__check_object_size" },
	{ 0x5a2cb4b8, "misc_deregister" },
	{ 0x92495a4d, "param_ops_uint" },
	{ 0x92495a4d, "param_ops_ulong" },
	{ 0x092a35a2, "_copy_from_user" },
	{ 0xd710adbf, "__kmalloc_noprof" },
	{ 0xdd45951a, "sysfs_streq" },
	{ 0xd272d446, "__SCT__preempt_schedule" },
	{ 0xc2ccdd1e, "__init_swait_queue_head" },
	{ 0x27fab36f, "module_layout" },
};

static const u32 ____version_ext_crcs[]
__used __section("__version_ext_crcs") = {
	0x40a621c5,
	0x6874e31b,
	0x28311fd0,
	0xcb8b6ec6,
	0x6ac784f4,
	0x5e505530,
	0xda9d005d,
	0xd27020bd,
	0xc230afd5,
	0x5a844b26,
	0xbd03ed67,
	0xd272d446,
	0xff0106da,
	0x9479a1e8,
	0x2475f1fb,
	0x90a48d82,
	0x952f9665,
	0x8b3bd1e5,
	0xbd03ed67,
	0x9aa6980d,
	0xf42bccd1,
	0x2a280842,
	0x173ec8da,
	0xe54e0a6b,
	0x9dd6ec3d,
	0x06237697,
	0x48dcca1c,
	0x92495a4d,
	0x62cbec20,
	0xd272d446,
	0x62cbec20,
	0x775eeed4,
	0x5ea962e6,
	0x06237697,
	0x7ec472ba,
	0xb9fcd065,
	0x9aa6980d,
	0x92495a4d,
	0xfe16dc1b,
	0x5cb46e6d,
	0xe298e85d,
	0x7851be11,
	0x1cf09ab5,
	0xe4de56b4,
	0x43a349ca,
	0xe298e85d,
	0x437e81c7,
	0xd272d446,
	0x8e167a49,
	0xa61fd7aa,
	0x5a2cb4b8,
	0x92495a4d,
	0x92495a4d,
	0x092a35a2,
	0xd710adbf,
	0xdd45951a,
	0xd272d446,
	0xc2ccdd1e,
	0x27fab36f,
};
static const char ____version_ext_names[]
__used __section("__version_ext_names") =
	"scnprintf\0"
	"kd_jit_runtime_leave_current\0"
	"kd_jit_runtime_create\0"
	"kfree\0"
	"schedule_timeout_interruptible\0"
	"kthread_should_stop\0"
	"kd_jit_runtime_destroy\0"
	"kd_jit_source_provider_create\0"
	"wake_up_process\0"
	"__x86_indirect_thunk_rax\0"
	"__ref_stack_chk_guard\0"
	"__stack_chk_fail\0"
	"refcount_warn_saturate\0"
	"strnlen\0"
	"kd_mutex_init\0"
	"__ubsan_handle_out_of_bounds\0"
	"kd_jit_runtime_enter_current\0"
	"kd_task_storage_root\0"
	"random_kmalloc_seed\0"
	"mutex_lock\0"
	"const_current_task\0"
	"kthread_stop\0"
	"sscanf\0"
	"__fortify_panic\0"
	"default_llseek\0"
	"kd_jit_source_provider_destroy\0"
	"misc_register\0"
	"param_ops_charp\0"
	"wait_for_completion\0"
	"__x86_return_thunk\0"
	"complete_all\0"
	"kthread_create_on_node\0"
	"pv_ops\0"
	"kd_jit_source_provider_close\0"
	"__preempt_count\0"
	"call_rcu\0"
	"mutex_unlock\0"
	"param_ops_bool\0"
	"__kmalloc_cache_noprof\0"
	"validate_usercopy_range\0"
	"kd_mutex_lock_entry_asm\0"
	"__SCT__cond_resched\0"
	"__put_task_struct_rcu_cb\0"
	"__ubsan_handle_load_invalid_value\0"
	"strlen\0"
	"kd_mutex_unlock_entry_asm\0"
	"simple_read_from_buffer\0"
	"BUG_func\0"
	"kmalloc_caches\0"
	"__check_object_size\0"
	"misc_deregister\0"
	"param_ops_uint\0"
	"param_ops_ulong\0"
	"_copy_from_user\0"
	"__kmalloc_noprof\0"
	"sysfs_streq\0"
	"__SCT__preempt_schedule\0"
	"__init_swait_queue_head\0"
	"module_layout\0"
;

MODULE_INFO(depends, "");


MODULE_INFO(srcversion, "53ED7606A850633434116D6");
