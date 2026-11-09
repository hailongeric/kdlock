/* SPDX-License-Identifier: GPL-2.0 */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint64_t u64;
#define TASK_COMM_LEN 16
#define PAGE_SIZE 4096
#define READ_ONCE(v) (v)
#define likely(v) (v)
#define unlikely(v) (v)
#define __percpu
#define alloc_percpu(type) (allocation_calls++, allocation_fails ? NULL : calloc(1, sizeof(type)))
#define free_percpu(value) do { if (value) { ++free_calls; free(value); } } while (0)
#define this_cpu_add(name, amount) ((name) += (amount))
#define per_cpu_ptr(name, cpu) (name)
#define for_each_possible_cpu(cpu) for ((cpu) = 0; (cpu) < 1; ++(cpu))
#define scnprintf snprintf
#define MODULE_PARM_DESC(...)
#define module_param_named(...)
#define module_param_string(...)
#define module_param_array_named(...)
#define module_param_cb(name, ops, arg, mode) \
	static const void * const param_##name __attribute__((used)) = (ops)
struct kernel_param { int unused; };
struct kernel_param_ops { int (*get)(char *, const struct kernel_param *); };
struct kd_service_root { int observe_index; u64 observe_shadow_start; };
enum kd_admission_kind { KD_ADMISSION_MUTEX, KD_ADMISSION_RWSEM };
static unsigned int acquisitions, clock_calls;
static unsigned int allocation_calls, free_calls;
static bool allocation_fails;
static u64 clock_ns = 100;
static int acquisition_result;
static u64 ktime_get_ns(void) { ++clock_calls; return clock_ns += 10; }
static int kd_service_local_acquire(void *object, enum kd_admission_kind kind, unsigned int state)
{
	assert(object == &acquisitions && kind == KD_ADMISSION_RWSEM && state == 7);
	++acquisitions;
	return acquisition_result;
}
#include "observe_production.h"

int main(void)
{
	char buffer[PAGE_SIZE];
	struct kd_service_root root = { .observe_index = -1 };
	u64 *v, start;
	unsigned int i;
	int index;

	strcpy(kd_service_observe_comm, "worker");
	kd_service_observe_entries[0] = 0x1000;
	kd_service_observe_entries[1] = 0x2000;
	kd_service_observe_entry_count = 2;
	assert(!kd_service_observe_init() && !allocation_calls && !kd_service_observed);
	index = kd_service_observe_select(0x1000, "worker");
	assert(index == -1);
	assert(kd_service_observe_start(index) == 0);
	kd_service_observe_event(index, "enter");
	kd_service_observe_shadow_end(&root);
	assert(!kd_service_observe_local(index, true, &acquisitions, KD_ADMISSION_RWSEM, 7));
	assert(acquisitions == 1 && clock_calls == 0);
	assert(kd_service_observe_stats_get(buffer, NULL) > 0 && strstr(buffer, "selected=0 local=0"));

	kd_service_observe = true;
	allocation_fails = true;
	assert(kd_service_observe_init() == -ENOMEM && !kd_service_observed);
	allocation_fails = false;
	assert(!kd_service_observe_init() && allocation_calls == 2 && kd_service_observed);
	v = kd_service_observed->value[0];
	for (i = 0; i < KD_SERVICE_OBSERVE_COUNT; ++i) assert(v[i] == 0);
	assert(kd_service_observe_select(0x3000, "worker") == -1);
	assert(kd_service_observe_select(0x1000, "other") == -1);
	assert(clock_calls == 0);
	for (i = 0; i < 3; ++i) {
		index = kd_service_observe_select(0x1000, "worker");
		assert(index == 0);
		acquisition_result = i == 2 ? -4 : 0;
		assert(kd_service_observe_local(index, i == 0, &acquisitions,
			KD_ADMISSION_RWSEM, 7) == acquisition_result);
	}
	assert(acquisitions == 4 && clock_calls == 6);
	index = kd_service_observe_select(0x1000, "worker");
	kd_service_observe_add(index, KD_SERVICE_OBSERVE_PREPUBLICATION_CANCEL, 1);
	for (i = 0; i < 3; ++i) {
		index = kd_service_observe_select(0x1000, "worker");
		kd_service_observe_add(index, KD_SERVICE_OBSERVE_SUBMITTED, 1);
		if (!i) {
			kd_service_observe_event(index, "cancel");
			continue;
		}
		root.observe_index = index;
		root.observe_shadow_start = kd_service_observe_start(index);
		kd_service_observe_event(index, "enter");
		start = kd_service_observe_start(index);
		kd_service_observe_elapsed(index, KD_SERVICE_OBSERVE_DISPATCH_NS,
			KD_SERVICE_OBSERVE_DISPATCH_SAMPLES, start);
		kd_service_observe_add(index, KD_SERVICE_OBSERVE_JIT_ENTERED, 1);
		if (i == 1) kd_service_observe_event(index, "returned");
		else {
			kd_service_observe_event(index, "handoff_ready");
			kd_service_observe_event(index, "native_release");
			kd_service_observe_event(index, "handoff_finished");
		}
		kd_service_observe_shadow_end(&root);
	}
	assert(v[KD_SERVICE_OBSERVE_SELECTED] == 7 && v[KD_SERVICE_OBSERVE_LOCAL] == 3);
	assert(v[KD_SERVICE_OBSERVE_LOCAL_NO_IMAGE] == 1 && v[KD_SERVICE_OBSERVE_LOCAL_NS] == 30);
	assert(v[KD_SERVICE_OBSERVE_LOCAL_SUCCESS] == 2 && v[KD_SERVICE_OBSERVE_LOCAL_CANCEL] == 1);
	assert(v[KD_SERVICE_OBSERVE_SUBMITTED] == 3 && v[KD_SERVICE_OBSERVE_CANCELED] == 1);
	assert(v[KD_SERVICE_OBSERVE_RETURNED] == 1 && v[KD_SERVICE_OBSERVE_HANDBACK] == 1 &&
		v[KD_SERVICE_OBSERVE_HANDBACK_FINISHED] == 1);
	assert(v[KD_SERVICE_OBSERVE_BOUND] == 2 && v[KD_SERVICE_OBSERVE_JIT_ENTERED] == 2 &&
		v[KD_SERVICE_OBSERVE_DISPATCH_SAMPLES] == 2 && v[KD_SERVICE_OBSERVE_SHADOW_SAMPLES] == 2);
	assert(v[KD_SERVICE_OBSERVE_DISPATCH_NS] == 20 && v[KD_SERVICE_OBSERVE_SHADOW_NS] == 60);
	assert(!v[KD_SERVICE_OBSERVE_INVALID_CLOCK]);
	assert(kd_service_observe_select(0x2000, "worker") == 1);
	kd_service_observe_elapsed(1, KD_SERVICE_OBSERVE_DISPATCH_NS,
		KD_SERVICE_OBSERVE_DISPATCH_SAMPLES, clock_ns + 100);
	assert(kd_service_observed->value[1][KD_SERVICE_OBSERVE_INVALID_CLOCK] == 1);
	assert(kd_service_observe_stats_get(buffer, NULL) > 0);
	assert(strstr(buffer, "entry=1000 selected=7 local=3") &&
	       strstr(buffer, "entry=2000 selected=1") && strstr(buffer, "invalid_clock=1"));
	kd_service_observe_exit();
	assert(!kd_service_observed && free_calls == 1);
	puts("service observation: disabled/enabled, local outcomes, terminal conservation and clocks passed");
	return 0;
}
