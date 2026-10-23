// SPDX-License-Identifier: GPL-2.0
/* One survivor shares the private target table; the other crosses the PMD. */
#define KD_BOUNDARY_PRIVATE 1
#define KD_BOUNDARY_SHARED 1
#include "../boundary_edge/client.c"
