/* Actual provider admission and controls; compile and run only in the VM. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <sys/ioctl.h>
typedef uint32_t __u32;
typedef int32_t __s32;
typedef uint64_t __u64;
#include "api_control.h"
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL %d: %s\n", __LINE__, #x); exit(1); } } while (0)
#define READ_ONCE(x) (x)
#define BIT(n) (1UL << (n))
#define __user
#define CAP_SYS_ADMIN 1
#define KD_EXE_UNUSED -2
#define KD_EXE_LOCK_SPIN 1
#define KD_EXE_LOCK_MUTEX 2
#define KD_ENTRY_ABI_SPIN_CLOBBER_V1 1
#define KD_ENTRY_ABI_MUTEX_CLOBBER_V1 2
struct file { int value; };
struct kd_api_provider { int value; };
struct kd_api_site { unsigned long entry; unsigned int site, reserved; };
struct kd_exe_info { int status_code; unsigned long RIP; unsigned int lock_kind, entry_abi; };
static const struct kd_api_provider kd_api_ops;
static struct kd_api_site sites[KD_API_SITE_COUNT];
static struct kd_exe_info entries[KD_API_SITE_COUNT];
static bool privileged = true, source_open = true, copy_fault;
static unsigned int lookups, additions, registrations, unregistrations, selections, cancellations, queries;
static int register_result;
static unsigned long kallsyms_lookup_name(const char *name)
{ CHECK(name && *name); lookups++; return 0x1000 + lookups; }
static const struct kd_api_site *kd_api_sites(unsigned int *count)
{ *count = KD_API_SITE_COUNT; return sites; }
static void kd_exe_add_abi(int pid, unsigned long entry, unsigned int kind, unsigned int abi)
{
	CHECK(!pid && additions < KD_API_SITE_COUNT);
	entries[additions++] = (struct kd_exe_info){0, entry, kind, abi};
}
static struct kd_exe_info *kd_get_exe(int pid, unsigned long entry)
{
	unsigned int i;
	CHECK(!pid);
	for (i = 0; i < additions; i++) if (entries[i].RIP == entry) return &entries[i];
	return NULL;
}
static int kd_api_register_provider(const struct kd_api_provider *ops)
{ CHECK(ops == &kd_api_ops && additions == 3); registrations++; return register_result; }
static void kd_api_unregister_provider(const struct kd_api_provider *ops)
{ CHECK(ops == &kd_api_ops); unregistrations++; }
static bool capable(int capability) { CHECK(capability == CAP_SYS_ADMIN); return privileged; }
static bool kd_source_is_open(void) { return source_open; }
static unsigned long copy_from_user(void *to, const void *from, size_t size)
{ if (copy_fault) return 1; memcpy(to, from, size); return 0; }
static unsigned long copy_to_user(void *to, const void *from, size_t size)
{ return copy_from_user(to, from, size); }
static int kd_api_select_current(struct file *file, const struct kd_api_provider *ops,
				 const struct kd_api_select *selection)
{ CHECK(file && ops == &kd_api_ops && selection->version == 1); selections++; return 0; }
static void kd_api_cancel_selector(struct file *file) { CHECK(file); cancellations++; }
static int kd_api_query_current(struct kd_api_query *query)
{ CHECK(query->version == 1); queries++; query->kind = KD_API_KIND_FILES; return 0; }
#include "api_provider_production.h"

static void reset(void)
{
	unsigned int i;
	api_bind = kd_api_registered = false;
	lookups = additions = registrations = unregistrations = selections = cancellations = queries = 0;
	register_result = 0; privileged = source_open = true; copy_fault = false;
	memset(entries, 0, sizeof(entries));
	for (i = 0; i < KD_API_SITE_COUNT; i++)
		sites[i] = (struct kd_api_site){0x2000 + i * 0x100, i + 1, 0};
}

int main(void)
{
	struct file file = {0};
	struct kd_api_select select = {.version = KD_API_VERSION};
	struct kd_api_query query = {.version = KD_API_VERSION, .fd = -1};
	unsigned int i;
	reset();
	CHECK(kd_api_provider_init() == 0 && !kd_api_registered);
	CHECK(!lookups && !additions && !registrations);
	CHECK(kd_api_provider_ioctl(&file, KD_API_SELECT, (unsigned long)&select) == -ENODEV);
	CHECK(kd_api_provider_ioctl(&file, KD_API_QUERY, (unsigned long)&query) == -ENODEV);
	CHECK(kd_api_provider_ioctl(&file, KD_API_CANCEL, 0) == -ENODEV);
	CHECK(!selections && !queries && !cancellations);
	kd_api_provider_exit(); CHECK(!unregistrations);
	reset(); api_bind = true;
	CHECK(!kd_api_provider_init() && kd_api_registered);
	CHECK(lookups == 2 && additions == 3 && registrations == 1);
	for (i = 0; i < 3; i++)
		CHECK(entries[i].RIP == sites[i].entry && entries[i].lock_kind == (i ? 2U : 1U) &&
		      entries[i].entry_abi == (i ? 2U : 1U));
	CHECK(!kd_api_provider_ioctl(&file, KD_API_SELECT, (unsigned long)&select) && selections == 1);
	CHECK(!kd_api_provider_ioctl(&file, KD_API_QUERY, (unsigned long)&query) && queries == 1 && query.kind == 1);
	CHECK(!kd_api_provider_ioctl(&file, KD_API_CANCEL, 0) && cancellations == 1);
	privileged = false; CHECK(kd_api_provider_ioctl(&file, KD_API_CANCEL, 0) == -EPERM);
	privileged = true; source_open = false;
	CHECK(kd_api_provider_ioctl(&file, KD_API_SELECT, (unsigned long)&select) == -ESHUTDOWN);
	source_open = true; copy_fault = true;
	CHECK(kd_api_provider_ioctl(&file, KD_API_QUERY, (unsigned long)&query) == -EFAULT);
	kd_api_provider_release(&file); CHECK(cancellations == 2);
	kd_api_provider_exit(); CHECK(!kd_api_registered && unregistrations == 1);
	kd_api_provider_exit(); CHECK(unregistrations == 1);
	CHECK(kd_api_provider_ioctl(&file, KD_API_CANCEL, 0) == -ENODEV);
	reset(); api_bind = true; register_result = -EBUSY;
	CHECK(kd_api_provider_init() == -EBUSY && !kd_api_registered);
	CHECK(kd_api_provider_ioctl(&file, KD_API_QUERY, (unsigned long)&query) == -ENODEV);
	kd_api_provider_exit(); CHECK(!unregistrations);
	puts("[PASS] provider opt-in, exact entries, disabled/failed control refusal and lifecycle");
	return 0;
}
