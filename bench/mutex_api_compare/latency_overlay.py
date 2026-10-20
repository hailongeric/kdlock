"""Exact source transformations for the frozen d21 latency diagnostic.

This module constructs private copies only. Callers verify every original
source hash before transformation and retain old/new maps. No production body,
lock shell, ownership, admission, counter or retirement predicate is replaced.
"""
import hashlib

RUNNER_SHA256 = 'e66b1b5048f9a2a56f75bb245ca8348a2126c7487dd396c40bffb6dc613f929e'
CLIENT_SHA256 = '02b237ce80dbdfa47d63268d07fba0bd55f8b3878ffb7667c1281c67ba720736'


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError('latency overlay needs exactly one source anchor: '+repr(before[:80]))
    return source.replace(before, after)


def synthetic(data):
    if hashlib.sha256(data).hexdigest() != RUNNER_SHA256:
        raise ValueError('synthetic runner differs from frozen original')
    source = data.decode()
    source = replace_once(source, 'static long sc_timed_configure',
                          '#include "latency_kernel.inc"\n\nstatic long sc_timed_configure')
    source = replace_once(source, '\tWRITE_ONCE(sc_timed.deadline_ns, config.deadline_ns);',
                          '\tsc_latency_configure(config.workers);\n'
                          '\tWRITE_ONCE(sc_timed.deadline_ns, config.deadline_ns);')
    before = '''\t\tfor (i = 0; i < SC_TIMED_BATCH; i++) {
#ifdef SC_HASH_PAYLOAD
\t\t\tu32 src = sc_hash_random(&random_state) % SC_HASH_KEY_RANGE;
\t\t\tu32 dst = sc_hash_random(&random_state) % SC_HASH_KEY_RANGE;

\t\t\tsc_body_0(src, dst, &hash_stats);
#else
\t\t\tbody();
#endif
\t\t\tpost_state = sc_post_work(post_state);
\t\t}'''
    after = '''\t\tfor (i = 0; i < SC_TIMED_BATCH; i++) {
\t\t\tstruct kd_latency_slot *latency = &sc_latency[run.worker];
\t\t\tbool sample;
\t\t\tu64 stamp = 0;
#ifdef SC_HASH_PAYLOAD
\t\t\tu32 src = sc_hash_random(&random_state) % SC_HASH_KEY_RANGE;
\t\t\tu32 dst = sc_hash_random(&random_state) % SC_HASH_KEY_RANGE;
#endif
\t\t\t/* Both clocks run on the original caller outside the body. The
\t\t\t * body's return follows physical unlock or completed remote ACK. */
\t\t\tsample = latency_sample &&
\t\t\t\tkd_latency_select(latency, run.completed + i);
\t\t\tif (sample)
\t\t\t\tstamp = ktime_get_ns();
#ifdef SC_HASH_PAYLOAD
\t\t\tsc_body_0(src, dst, &hash_stats);
#else
\t\t\tbody();
#endif
\t\t\tif (sample)
\t\t\t\tkd_latency_record(latency, run.completed + i,
\t\t\t\t\t\t  stamp, ktime_get_ns());
\t\t\tpost_state = sc_post_work(post_state);
\t\t}'''
    source = replace_once(source, before, after)
    source = replace_once(source, '\t} while (run.finished_ns < run.deadline_ns);',
                          '\t} while (run.finished_ns < run.deadline_ns);\n'
                          '\tsc_latency[run.worker].completed = run.completed;')
    source = replace_once(source, '\tswitch (cmd) {\n', '\tswitch (cmd) {\n'
                          '\tcase KD_LATENCY_READ:\n\t\treturn sc_latency_read(user);\n')
    source = replace_once(source, '\treturn misc_register(&sc_device);',
                          '\treturn sc_latency_register(&sc_device);')
    source = replace_once(source, '\tmisc_deregister(&sc_device);',
                          '\tmisc_deregister(&sc_device);\n\tvfree(sc_latency);')
    return source.encode()


def api_client(data):
    if hashlib.sha256(data).hexdigest() != CLIENT_SHA256:
        raise ValueError('API client differs from frozen original')
    source = data.decode()
    source = replace_once(source, 'static int pin(int cpu)',
                          '#include "latency_client.inc"\n\nstatic int pin(int cpu)')
    source = replace_once(source, '\t\tfor (unsigned int i = 0; i < count; i++) {\n',
        '\t\tfor (unsigned int i = 0; i < count; i++) {\n'
        '\t\t\tstruct kd_latency_slot *latency = &latency_slots[w - workers];\n'
        '\t\t\tbool sample = latency_sample && timed &&\n'
        '\t\t\t\tkd_latency_select(latency, w->done);\n'
        '\t\t\tuint64_t stamp = sample ? now(CLOCK_MONOTONIC) : 0;\n')
    source = replace_once(source, '\t\t\tif (w->error) break;\n',
        '\t\t\tif (sample)\n'
        '\t\t\t\tkd_latency_record(latency, w->done, stamp, now(CLOCK_MONOTONIC));\n'
        '\t\t\tif (w->error) break;\n')
    source = replace_once(source, '\tw->finished = now(CLOCK_MONOTONIC);',
        '\tlatency_slots[w - workers].completed = w->done;\n'
        '\tw->finished = now(CLOCK_MONOTONIC);')
    source = replace_once(source, '\t\tworkers[i].cpu = phase_cpus[i];',
        '\t\tkd_latency_reset(&latency_slots[i], i);\n'
        '\t\tworkers[i].cpu = phase_cpus[i];')
    source = replace_once(source, '\tprintf("]}\\n");\n\tfflush(stdout);\n\treturn ok;',
        '\tprintf("]");\n\tlatency_json(cohort);\n'
        '\tprintf("}\\n");\n\tfflush(stdout);\n\treturn ok;')
    source = replace_once(source, '\tif (pin(collector)) die("collector affinity");',
        '\tif (pin(collector)) die("collector affinity");\n\tlatency_initialize();')
    return source.encode()
