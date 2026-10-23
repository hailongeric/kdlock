// SPDX-License-Identifier: GPL-2.0
/* Same narrow boundary fixture; the neighbor creates the leaf table while
 * the shared-table target stays empty until native removal or a real fault. */
#define KD_BOUNDARY_EMPTY 1
#define KD_BOUNDARY_SHARED 1
#include "../boundary_edge/client.c"
