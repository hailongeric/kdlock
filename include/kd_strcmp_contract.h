/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_STRCMP_CONTRACT_H
#define KD_STRCMP_CONTRACT_H

/* Audited ordinary kernel strings must remain valid and unchanged while the
 * physical source lock is held. The service checks for a NUL within this
 * bound before invoking the original strcmp; it never substitutes its result.
 * This covers Linux's 255-byte xattr names and their terminating byte.
 */
#define KD_STRCMP_MAX_BYTES 256U
#define KD_STRCMP_MAX_CALLS 128U
#define KD_STRCMP_CODE_BYTES 42U
#define KD_STRCMP_TAIL1_DISP 31U
#define KD_STRCMP_TAIL2_DISP 38U

/* Exact captured implementation: two ordinary pointer reads, scalar compares,
 * and returns. A tail is either a jump to the actual __x86_return_thunk or
 * the kernel's captured alternative: RET followed by four INT3 padding bytes.
 * No other tail or helper-body changes are accepted.
 */
#define KD_STRCMP_RETURN_TEMPLATE { 0xc3, 0xcc, 0xcc, 0xcc, 0xcc }
#define KD_STRCMP_CODE_TEMPLATE { \
  0xf3, 0x0f, 0x1e, 0xfa, 0x31, 0xc0, 0xeb, 0x08, \
  0x48, 0x83, 0xc0, 0x01, 0x84, 0xd2, 0x74, 0x13, \
  0x0f, 0xb6, 0x14, 0x07, 0x3a, 0x14, 0x06, 0x74, \
  0xef, 0x19, 0xc0, 0x83, 0xc8, 0x01, 0xe9, 0x00, \
  0x00, 0x00, 0x00, 0x31, 0xc0, 0xe9, 0x00, 0x00, \
  0x00, 0x00 }

#endif
