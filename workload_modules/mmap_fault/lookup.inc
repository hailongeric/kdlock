/* Included by mapping.c. A lookup writes a sequence as well as selecting a page,
 * so every backend uses writer ownership for this explicit optional mode.
 * Only resident metadata is borrowed. The VFS reference owns the mapping and
 * immutable base page references until the original callback/ioctl returns. */
struct mf_selection {
	struct page *page;
	u64 sequence, epoch, complement;
};

#define MF_SELECT(m, index, result) do { \
	(m)->lookup_sequence++; \
	(result).sequence = (m)->lookup_sequence; \
	(result).epoch = (m)->epoch; \
	(result).complement = (m)->complement; \
	(result).page = (index) < (m)->pages ? (m)->page[index] : NULL; \
} while (0)

static __attribute__((noipa)) void
mf_lookup_local(struct mf_mapping *m, unsigned long index, struct mf_selection *out)
{
	struct mf_selection selected;
	mf_write(m);
	MF_SELECT(m, index, selected);
	mf_write_end(m);
	*out = selected;
}

#if !MF_TC_BUILD
extern const char mf_lookup_entry[];
static __attribute__((noipa)) void
mf_lookup_delegated(struct mf_mapping *m, unsigned long index, struct mf_selection *out)
{
	/* Frame-relative results survive the exact terminal unlock/ACK. The
	 * output pointer is used only after resuming the original caller. */
	volatile struct mf_selection selected;
	struct kd_rwsem_outer_cookie cookie;
	KD_RWSEM_OUTER_WRITE_LOCK(&m->lock.kd, cookie,
		".globl mf_lookup_entry\nmf_lookup_entry:\n\t" ANNOTATE_NOENDBR);
	atomic64_inc(&m->writes);
	MF_SELECT(m, index, selected);
	atomic64_inc(&m->write_ends);
	KD_RWSEM_OUTER_WRITE_UNLOCK(&m->lock.kd, cookie);
	*out = selected;
}
#endif

static struct page *mf_lookup_page(struct mf_mapping *m, unsigned long index,
				  bool origin_only, u64 *sequence)
{
	struct task_struct *origin = current;
	struct mf_selection selected;
	atomic64_inc(&m->lookup_begins);
#if !MF_TC_BUILD
	if (m->backend == MF_KD && (m->features & MF_DELEGATE) && !origin_only) {
		/* This counts candidates, never proof of a returned JIT body. */
		atomic64_inc(&m->lookup_candidates);
		mf_lookup_delegated(m, index, &selected);
	} else
#endif
	{
		if (m->features & MF_DELEGATE)
			atomic64_inc(&m->lookup_fallbacks);
		mf_lookup_local(m, index, &selected);
	}
	if (current != origin)
		atomic64_inc(&m->context_errors);
	if (selected.complement != ~selected.epoch)
		atomic64_inc(&m->data_errors);
	/* No slot can be replaced or freed while this file/VMA callback is live.
	 * Acquire the transferable page reference on the origin after the ACK,
	 * before any mmap drop or final VFS put. No get_page runs on a combiner. */
	if (selected.page)
		get_page(selected.page);
	if (sequence)
		*sequence = selected.sequence;
	atomic64_inc(&m->lookup_ends);
	return selected.page;
}

#undef MF_SELECT
