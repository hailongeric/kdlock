/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_IMAGE_POOL_H
#define KD_IMAGE_POOL_H

/* Shared descriptor count for the separately preallocated code pools. */
#ifndef KD_CODE_BLOCK_POOL
#define KD_CODE_BLOCK_POOL 64
#endif

#if KD_CODE_BLOCK_POOL < 1 || KD_CODE_BLOCK_POOL > 256
#error "KD_CODE_BLOCK_POOL must be between 1 and 256"
#endif

#endif
