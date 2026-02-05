#include <linux/init.h>
#include <linux/kallsyms.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/sched.h>
#include <linux/sched/task_stack.h>
#include <linux/string.h>

// HL ADDD
#include <linux/spinlock.h>

#include "exe.h"
#include "sys.h"
#include "kd_lock.h"
#include "utils.h"
#include "komb.h"


//  #include "fault.h" ! check addr in VMALLOC

#define MAX_NAME_CNT 20
#define MAX_NAME_LENGTH 20

MODULE_LICENSE("GPL");

#define rate_int(a,b) b>0?((a*100)/b):0
#define rate_dec(a,b) b>0?(((a*10000)/b)%100):0

extern int velvet_wait_queue;
extern int delegate_election;
module_param(velvet_wait_queue, int, S_IRUGO);
module_param(delegate_election, int, S_IRUGO);

char* target_process = "kd_test";
module_param(target_process, charp, S_IRUGO);
char* target_names[MAX_NAME_CNT] = { 0 };

// extern void (*nf_debug)(char*);
extern int (*is_kd_test)(void);

extern void (*kd_raw_spin_lock)(raw_spinlock_t *lock, unsigned long ret_addr);
extern void (*kd_raw_spin_unlock)(raw_spinlock_t *lock, unsigned long ret_addr);
extern int (*nf_do_int3)(struct pt_regs*);


long nf_success_cnt;
long nf_success_wake_cnt;
long nf_total_cnt;
unsigned long uaddrs[102400];
unsigned long uaddr_cnts[102400];
unsigned long nf_wake_rets[512];
long uaddr_cnt;


// TODO rewrite flag
int __is_kd_test(void) {
	int i;
	if (strcmp(current->comm, target_names[0]) == 0)
		return 2;
	for (i = 0;i < MAX_NAME_CNT;i++) {
		if (target_names[i] == NULL)
			break;
		if (strcmp(current->comm, target_names[i]) == 0)
			return 1;
	}
	return 0;
}

static int __init kdlock_km_init(void) {
	int i;
	char* token;
	exe_init();
	sys_init();
	komb_init();
	i = 0;
	token = strsep(&target_process, " ");
	while (token != NULL) {
		if (i < MAX_NAME_CNT) {
			target_names[i] = (char*)kmalloc(MAX_NAME_LENGTH, GFP_KERNEL);
			strncpy(target_names[i], token, MAX_NAME_LENGTH - 1);
			target_names[i][MAX_NAME_LENGTH - 1] = '\0';
			i++;
		}
		token = strsep(&target_process, " ");
	}

	for (i = 0;i < MAX_NAME_CNT;i++) {
		if (target_names[i] == NULL)
			break;
		KD_PR_INFO("%s", target_names[i]);
	}

	uaddr_cnt = 0;
	nf_success_cnt = 0;
	nf_success_wake_cnt = 0;
	nf_total_cnt = 0;
	for (i = 0;i < NF_CNT_NUM + 2;i++)
		nf_wake_rets[i] = 0;
	is_kd_test = __is_kd_test;
	kd_raw_spin_unlock = __kd_raw_spin_unlock;
	kd_raw_spin_lock = __kd_raw_spin_lock;
	nf_do_int3 = NULL;

	// nf_sys_call_table = kallsyms_lookup_name("sys_call_table");
	KD_PR_INFO( "kd kernel module init\n");
	return 0;
}

static void __exit kdlock_km_exit(void) {
	int i, target_cnt = 0, time_cnt = 0;
	kd_raw_spin_unlock = NULL;
	kd_raw_spin_lock = NULL;
	is_kd_test = NULL;
	nf_do_int3 = NULL;
	KD_PR_INFO("nf_success_cnt:%ld nf_total_cnt:%ld nf_success_wake_cnt:%ld success_rate:%ld.%02ld%% success_wake_rate:%ld.%02ld%%\n", \
		nf_success_cnt, nf_total_cnt, nf_success_wake_cnt, \
		rate_int(nf_success_cnt, nf_total_cnt), rate_dec(nf_success_cnt, nf_total_cnt), \
		rate_int(nf_success_wake_cnt, nf_success_cnt), rate_dec(nf_success_wake_cnt, nf_success_cnt));
	for (i = 0;i < NF_CNT_NUM + 2;i++) {
		target_cnt += i * nf_wake_rets[i];
		time_cnt += nf_wake_rets[i];
		KD_PR_INFO( "ret: %d cnt: %lu\n", i, nf_wake_rets[i]);
	}
	if (time_cnt > 0)
		KD_PR_INFO("average ret: %d", target_cnt / time_cnt);
	KD_PR_INFO("uaddr total: %ld", uaddr_cnt);
	for (i = 0;i < uaddr_cnt;i++)
		// if (uaddr_cnts[i] > 100)
		KD_PR_INFO("%lx --- %ld", uaddrs[i], uaddr_cnts[i]);

	for (i = 0;i < MAX_NAME_CNT;i++)
		if (target_names[i] != NULL)
			kfree(target_names[i]);

	komb_free();
	sys_exit();
	exe_exit();

	KD_PR_INFO( "kd kernel module exit\n");
}

module_init(kdlock_km_init);
module_exit(kdlock_km_exit);
