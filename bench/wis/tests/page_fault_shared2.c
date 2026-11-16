// SPDX-License-Identifier: GPL-2.0
/* See page_fault_shared.h. */
#define PF_MPROTECT	1
#define PF_KERNEL_FAULT	0
#include "page_fault_shared.h"

char *testcase_description = "Shared mapping page fault with mprotect splitting the VMA";
