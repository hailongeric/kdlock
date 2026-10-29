/* These are exact C-call targets, not lock controls or proxy services.
 * Core/selected built-in symbols are boot-stable. Each actual continuation
 * independently pins its target and return text through the retained frame. */
struct kd_native_terminal {
	const char *symbol;
	unsigned long address;
};
#define KD_NATIVE_TERMINAL(symbol, purpose) { #symbol, 0 },
static struct kd_native_terminal kd_native_terminals[] = {
#include "kd_native_terminals.def"
};
#undef KD_NATIVE_TERMINAL

static void kd_native_terminal_init(void)
{
	unsigned int i;

	for (i = 0; i < ARRAY_SIZE(kd_native_terminals); i++)
		kd_native_terminals[i].address =
			kallsyms_lookup_name(kd_native_terminals[i].symbol);
}

static inline bool kd_native_terminal_target(unsigned long target)
{
	unsigned int i;

	if (!target)
		return false;
	for (i = 0; i < ARRAY_SIZE(kd_native_terminals); i++)
		if (kd_native_terminals[i].address == target)
			return true;
	return false;
}
