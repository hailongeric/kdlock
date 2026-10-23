// SPDX-License-Identifier: GPL-2.0
/* The target and untouched near survivor share an actually missing leaf table.
 * A separate anchor creates only required upper levels before publication. */
#define KD_BOUNDARY_SHARED 1
#include "../boundary_edge/client.c"
