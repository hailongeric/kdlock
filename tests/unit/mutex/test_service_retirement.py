"""VM-only synchronous service retirement with supplied CPU/continuation APIs.

Run the production callback, CPU dispatch and node retirement. Task/source puts
and CPU-hotplug/work scheduling are substitutes; focused kernel checks are
still required for their real concurrent behavior.
"""
import os
import resource
import shlex
import signal
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source
from test_spin_shadow import definition


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    queue = read_source(ROOT / 'kernel_module/mutex/queue.inc')
    service = read_source(ROOT / 'kernel_module/kd_service.c')
    code = '\n'.join(definition(queue, name) for name in (
        'static inline u32 kd_mutex_encode_tail(int cpu, int idx)',
        'static void kd_mutex_check_node_retirement(struct kd_mutex_node *node)',
        'static void kd_mutex_clear_retired_node(struct kd_mutex_node *node)',
        'static void kd_mutex_release_node(struct kd_mutex_node *node)',
    )) + '\n' + '\n'.join(definition(service, name) for name in (
        'static void kd_service_check_pooled_root(struct kd_service_root *root)',
        'static void kd_service_release_offline_node(struct kd_service_root *root)',
        'static long kd_service_retire_handoff(void *argument)',
        'static void kd_service_finish_handoff(struct kd_service_root *root)',
    ))
    with tempfile.TemporaryDirectory(prefix='kd-service-retirement-') as directory:
        path = Path(directory)
        (path / 'retirement_production.h').write_text(code)
        binary = path / 'retirement'
        subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
            '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-UNDEBUG', '-pthread',
            '-I', str(path), str(ROOT / 'tests/unit/mutex/service_retirement_fixture.c'),
            '-o', str(binary)], check=True, timeout=30)
        for mode in ('online', 'offline', 'spill', 'offline_pair', 'wrong_home', 'wrong_tail',
                     'wrong_root', 'live_request', 'queue', 'selection', 'count', 'osq', 'missing_slot'):
            result = subprocess.run([str(binary), mode], capture_output=True, text=True, timeout=15)
            if mode in ('online', 'offline', 'spill', 'offline_pair'):
                assert result.returncode == 0, (mode, result.returncode, result.stdout, result.stderr)
                print(result.stdout, end='')
            else:
                assert result.returncode == -signal.SIGABRT and 'Assertion' in result.stderr, (
                    mode, result.returncode, result.stdout, result.stderr)
                print('service retirement rejected inconsistent state:', mode)


if __name__ == '__main__':
    main()
