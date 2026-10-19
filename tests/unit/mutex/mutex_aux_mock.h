/* Deterministic registry boundary for queue/continuation fixtures. The actual
 * concurrent registry and allocator are exercised by test_mutex_aux.py.
 * This single-thread boundary does not simulate RCU. Keep exact references
 * separate from physical ownership and retain retired bytes solely
 * so existing post-unlock assertions can inspect their final values. */
static struct kd_mutex_aux fixture_aux_records[16];
static bool fixture_aux_failure;
static unsigned int fixture_aux_gets, fixture_aux_puts;

static struct kd_mutex_aux *fixture_aux(struct kd_mutex *lock)
{
	struct kd_mutex_aux *empty = NULL;
	for (unsigned int i = 0; i < 16; i++) {
		struct kd_mutex_aux *aux = &fixture_aux_records[i];
		if (aux->lock == lock)
			return aux;
		if (!aux->lock && !empty)
			empty = aux;
	}
	CHECK(empty && lock);
	empty->lock = lock;
	return empty;
}

static void fixture_aux_reset(void)
{
	memset(fixture_aux_records, 0, sizeof(fixture_aux_records));
	fixture_aux_failure = false;
	fixture_aux_gets = fixture_aux_puts = 0;
}

struct kd_mutex_aux *kd_mutex_aux_get(struct kd_mutex *lock)
{
	fixture_aux_gets++;
	if (fixture_aux_failure)
		return NULL;
	struct kd_mutex_aux *aux = fixture_aux(lock);
	aux->refs.counter++;
	return aux;
}

struct kd_mutex_aux *kd_mutex_aux_lookup(struct kd_mutex *lock)
{
	struct kd_mutex_aux *aux = fixture_aux(lock);
	if (!aux->refs.counter)
		return NULL;
	aux->refs.counter++;
	return aux;
}

void kd_mutex_aux_ref(struct kd_mutex_aux *aux)
{
	CHECK(aux->refs.counter);
	aux->refs.counter++;
}

void kd_mutex_aux_put(struct kd_mutex_aux *aux)
{
	CHECK(aux->refs.counter);
	fixture_aux_puts++;
	if (!--aux->refs.counter)
		CHECK(!aux->physical_owner && !aux->locked && !aux->tail);
}

bool kd_mutex_delegation_owned(struct kd_mutex *lock, struct task_struct *task)
{
	struct kd_mutex_aux *aux = fixture_aux(lock);
	return aux->refs.counter && aux->physical_owner == task;
}
