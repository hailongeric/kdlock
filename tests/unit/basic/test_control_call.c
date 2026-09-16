/* Exercise the same pending-call policy used by the kernel, not a C mirror. */
#include <assert.h>
#include <stdio.h>
#include "kd_call.h"

int main(void)
{
	struct kd_call_state call;
	unsigned long stack[] = { 0x2005, 0xbeef };
	unsigned long ip, sp;
	const int errors[] = { -ENOMEM, -E2BIG,	     -EINVAL, -EDEADLK,
			       -EIO,	-EOPNOTSUPP, 0,	      1 };

	for (int phase = KD_CALL_NONE; phase <= KD_CALL_SPIN_NATIVE; phase++) {
		for (unsigned int i = 0; i < sizeof(errors) / sizeof(errors[0]);
		     i++) {
			assert(!kd_call_begin(&call, 0x1000,
					      (unsigned long)stack, stack[0]));
			call.phase = phase;
			ip = stack[0];
			sp = (unsigned long)(stack + 1);
			int expected =
				phase == KD_CALL_PENDING &&
				(errors[i] == -ENOMEM || errors[i] == -E2BIG);
			assert(kd_call_resume_pending(&call, errors[i], &ip,
						      &sp) == expected);
			assert(ip == (expected ? 0x1000 : stack[0]));
			assert(sp ==
			       (unsigned long)(expected ? stack : stack + 1));
			assert(stack[0] == 0x2005 && stack[1] == 0xbeef);
		}
	}
	assert(kd_call_begin(&call, 0, (unsigned long)stack, stack[0]) ==
	       -EINVAL);
	assert(call.phase == KD_CALL_NONE);
	assert(kd_call_begin(&call, 0x1000, 0, stack[0]) == -EINVAL);
	assert(kd_call_begin(&call, 0x1000, (unsigned long)stack, 0) ==
	       -EINVAL);
	assert(!kd_call_resume_pending(&call, -ENOMEM, &ip, &sp));
	assert(!kd_call_begin(&call, 0x1000, 0x3000, 0x2005));
	assert(kd_call_after_matches(&call, 0x2005, 0x3008));
	assert(!kd_call_after_matches(&call, 0x2006, 0x3008));
	assert(!kd_call_after_matches(&call, 0x2005, 0x3000));
	call.stack = ~0UL - 3;
	assert(!kd_call_after_matches(&call, 0x2005, 4));
	puts("[PASS] test_control_call (56 phase/error combinations, post-CALL bounds)");
	return 0;
}
