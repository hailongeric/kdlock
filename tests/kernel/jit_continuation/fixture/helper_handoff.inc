/* SPDX-License-Identifier: GPL-2.0 */
/* Ordinary source callees for cold CALL/IJ learning. None is a runtime service.
 * Capture entry SP/return words before the C leaf changes its source frame. */
static struct jit_handoff_slot helper_handoff_slots[JIT_KILLABLE_SLOTS];

unsigned long jit_test_handoff_wrapper(unsigned long index, unsigned long a1,
	unsigned long a2, unsigned long a3, unsigned long a4, unsigned long a5);
unsigned long jit_test_handoff_leaf_root(void);
unsigned long jit_test_handoff_leaf_nested(void);
unsigned long jit_test_handoff_leaf_read(void);

static void *helper_handoff_targets[JIT_KILLABLE_SLOTS] __used = {
	jit_test_handoff_leaf_root, jit_test_handoff_leaf_nested,
	jit_test_handoff_leaf_read, jit_test_handoff_leaf_root,
	jit_test_handoff_leaf_root, jit_test_handoff_leaf_root,
	jit_test_handoff_leaf_root, jit_test_handoff_leaf_root,
};

static __attribute__((noipa, used)) noinline notrace unsigned long
jit_test_handoff_body(unsigned long index, unsigned long a1, unsigned long a2,
	unsigned long a3, unsigned long a4, unsigned long a5)
{
	struct jit_handoff_slot *slot = &helper_handoff_slots[index];
	unsigned long budget = 1UL << 30;
	unsigned long value = 0x7edcba9876543210UL ^ index ^
		(a1 + 3 * a2 + 5 * a3 + 7 * a4 + 11 * a5);

	WRITE_ONCE(slot->pid, current->pid);
	WRITE_ONCE(slot->arguments[0], index);
	WRITE_ONCE(slot->arguments[1], a1);
	WRITE_ONCE(slot->arguments[2], a2);
	WRITE_ONCE(slot->arguments[3], a3);
	WRITE_ONCE(slot->arguments[4], a4);
	WRITE_ONCE(slot->arguments[5], a5);
	WRITE_ONCE(slot->result, value);
	smp_store_release(&slot->calls, READ_ONCE(slot->calls) + 1);
	while (!(READ_ONCE(killable_release) & JIT_KILLABLE_RELEASE_HELPER) && --budget)
		cpu_relax();
	if (!budget)
		atomic_inc(&failures);
	return value;
}

#define JIT_HANDOFF_LEAF(name) \
    ".balign 16\n.globl " #name "\n.type " #name ",@function\n" \
    #name ":\n.byte 0xf3,0x0f,0x1e,0xfa\n" \
    "lea helper_handoff_slots(%rip),%rax\n" \
    "imul $96,%rdi,%r11\nadd %r11,%rax\n" \
    "mov %rsp,16(%rax)\nmov (%rsp),%r10\nmov %r10,24(%rax)\n" \
    "jmp jit_test_handoff_body\n.size " #name ",.-" #name "\n"
asm(".pushsection .text\n.balign 16\n"
    ".globl jit_test_handoff_wrapper\n.type jit_test_handoff_wrapper,@function\n"
    "jit_test_handoff_wrapper:\n.byte 0xf3,0x0f,0x1e,0xfa\n"
    "lea helper_handoff_targets(%rip),%rax\nmov (%rax,%rdi,8),%rax\n"
    ANNOTATE_RETPOLINE_SAFE "\njmp *%rax\n"
    ".size jit_test_handoff_wrapper,.-jit_test_handoff_wrapper\n"
    JIT_HANDOFF_LEAF(jit_test_handoff_leaf_root)
    JIT_HANDOFF_LEAF(jit_test_handoff_leaf_nested)
    JIT_HANDOFF_LEAF(jit_test_handoff_leaf_read)
    ".popsection\n");
#undef JIT_HANDOFF_LEAF

static __always_inline void helper_handoff_call(unsigned long index)
{
	unsigned long value = jit_test_handoff_wrapper(index, JIT_HELPER_A1,
		JIT_HELPER_A2, JIT_HELPER_A3, JIT_HELPER_A4, JIT_HELPER_A5);

	if (value != JIT_HELPER_RESULT(index))
		atomic_inc(&failures);
	WRITE_ONCE(helper_handoff_slots[index].after,
		READ_ONCE(helper_handoff_slots[index].after) + 1);
}

static void helper_handoff_reset(void)
{
	BUILD_BUG_ON(sizeof(struct jit_handoff_slot) != 96);
	BUILD_BUG_ON(offsetof(struct jit_handoff_slot, entry_sp) != 16);
	BUILD_BUG_ON(offsetof(struct jit_handoff_slot, return_word) != 24);
	BUILD_BUG_ON(sizeof(struct jit_handoff_snapshot) != 824);
	memset(helper_handoff_slots, 0, sizeof(helper_handoff_slots));
}

static long helper_handoff_snapshot(void __user *user)
{
	struct jit_handoff_snapshot state = {
		.version = 1, .wrapper = (unsigned long)jit_test_handoff_wrapper,
		.leaves = { (unsigned long)jit_test_handoff_leaf_root,
			(unsigned long)jit_test_handoff_leaf_nested,
			(unsigned long)jit_test_handoff_leaf_read },
		.body = (unsigned long)jit_test_handoff_body,
		.errors = atomic_read(&failures),
	};
	unsigned int i, argument;

	for (i = 0; i < JIT_KILLABLE_SLOTS; ++i) {
		struct jit_handoff_slot *from = &helper_handoff_slots[i];
		struct jit_handoff_slot *to = &state.slots[i];

		to->calls = smp_load_acquire(&from->calls);
		to->pid = READ_ONCE(from->pid);
		to->entry_sp = READ_ONCE(from->entry_sp);
		to->return_word = READ_ONCE(from->return_word);
		for (argument = 0; argument < 6; ++argument)
			to->arguments[argument] = READ_ONCE(from->arguments[argument]);
		to->result = READ_ONCE(from->result);
		to->after = READ_ONCE(from->after);
	}
	return copy_to_user(user, &state, sizeof(state)) ? -EFAULT : 0;
}
