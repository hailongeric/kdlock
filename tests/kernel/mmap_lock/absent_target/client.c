// SPDX-License-Identifier: GPL-2.0
/* Share the exact mapping, queue, ownership and cleanup observations. The
 * absent-target variant never accesses the target during initial setup. */
#define KD_TEST_ABSENT 1
#include "../zero_target/client.c"
