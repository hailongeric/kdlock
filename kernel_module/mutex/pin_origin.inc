/* SPDX-License-Identifier: GPL-2.0 */
/* Included before queue.inc; the storage and merge implementation follow in
 * pin_diag.inc. Keep per-poll work local and compile every observation out in
 * ordinary builds. The exact READY/CLAIMED/WAIT protocol owns all decisions. */
#if KDLOCK_MUTEX_DIAGNOSTICS == 2
struct kd_mutex_pin_origin {
	u64 expiry_checks;
	u64 withdrawal_reservations;
	bool budget_expired;
	bool withdrawn;
	bool forced_cancel;
};
static void kd_mutex_pin_origin_finish(const struct kd_mutex_pin_origin *origin,
				       bool retained);
#define KD_MUTEX_PIN_WAIT_ENTER() struct kd_mutex_pin_origin pin_origin = { 0 }
#define KD_MUTEX_PIN_BUDGET_EXPIRED() (pin_origin.budget_expired = true)
#define KD_MUTEX_PIN_EXPIRY_CHECK() (pin_origin.expiry_checks++)
#define KD_MUTEX_PIN_WITHDRAW() (pin_origin.withdrawn = true)
#define KD_MUTEX_PIN_WITHDRAW_RESERVED() (pin_origin.withdrawal_reservations++)
#define KD_MUTEX_PIN_FORCED_CANCEL() (pin_origin.forced_cancel = true)
#define KD_MUTEX_PIN_INITIAL_FINISH(retained) \
	kd_mutex_pin_origin_finish(&pin_origin, (retained))
#else
#define KD_MUTEX_PIN_WAIT_ENTER() do { } while (0)
#define KD_MUTEX_PIN_BUDGET_EXPIRED() do { } while (0)
#define KD_MUTEX_PIN_EXPIRY_CHECK() do { } while (0)
#define KD_MUTEX_PIN_WITHDRAW() do { } while (0)
#define KD_MUTEX_PIN_WITHDRAW_RESERVED() do { } while (0)
#define KD_MUTEX_PIN_FORCED_CANCEL() do { } while (0)
#define KD_MUTEX_PIN_INITIAL_FINISH(retained) do { } while (0)
#endif
