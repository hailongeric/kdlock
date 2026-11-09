#!/usr/bin/env python3
"""Compile the actual reader release against an exact final-access boundary."""
from pathlib import Path
import os
import resource
import shlex
import subprocess
import tempfile


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    root = Path(__file__).resolve().parents[3]
    source = (root / 'kernel_module/kd_rwsem.c').read_text()
    start = source.index('void kd_up_read(struct kd_rwsem *sem)\n{')
    end = source.index('\nEXPORT_SYMBOL_GPL(kd_up_read);', start)
    release = source[start:end]
    fixture = r'''
#define _GNU_SOURCE
/* This fixture owns ordinary local reader credits, with no retained route. */
#define KD_RWSEM_LOCAL_BACKEND 1
#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>
typedef struct { long value; } atomic_long_t;
struct kd_rwsem { atomic_long_t readers; long reader_drain; };
static size_t page_size;
static struct kd_rwsem *mapping;
static unsigned int decrements;
static inline bool atomic_long_dec_and_test(atomic_long_t *value)
{
    assert(value == &mapping->readers && value->value > 0);
    bool final = --value->value == 0;
    ++decrements;
    if (final)
        assert(!mprotect(mapping, page_size, PROT_NONE));
    return final;
}
/* Keep the previous implementation compilable for the negative control. */
static inline bool irqs_disabled(void) { return false; }
static inline bool in_atomic(void) { return false; }
static inline void kd_rwsem_wake(struct kd_rwsem *sem, long *condition)
{
    (void)sem;
    (void)condition;
    abort();
}
RELEASE
int main(void)
{
    page_size = (size_t)sysconf(_SC_PAGESIZE);
    mapping = mmap(NULL, page_size, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(mapping != MAP_FAILED);
    mapping->readers.value = 2;
    kd_up_read(mapping);
    assert(decrements == 1 && mapping->readers.value == 1);
    kd_up_read(mapping);
    /* The object is now inaccessible; only independent state may be used. */
    assert(decrements == 2);
    assert(!munmap(mapping, page_size));
    return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix='kd-read-release-') as directory:
        directory = Path(directory)
        for name, body in [
            ('production', release),
            ('post_final_notification', release.replace(
                '(void)atomic_long_dec_and_test(&sem->readers);',
                'if (atomic_long_dec_and_test(&sem->readers)) '
                'kd_rwsem_wake(sem, &sem->reader_drain);')),
        ]:
            path = directory / (name + '.c')
            binary = directory / name
            path.write_text(fixture.replace('RELEASE', body))
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                str(path), '-o', str(binary),
            ], check=True)
            result = subprocess.run([str(binary)], capture_output=True)
            assert (result.returncode == 0) == (name == 'production'), (
                name, result.returncode, result.stdout, result.stderr)
    print('PASS production reader release: last credit is final object access; '
          'post-final notification negative control detected')


if __name__ == '__main__':
    main()
