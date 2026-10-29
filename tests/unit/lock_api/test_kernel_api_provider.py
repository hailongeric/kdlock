"""Guest-only actual-provider opt-in admission and disabled control coverage."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'tests/unit/spin'))
sys.path.insert(0, str(ROOT/'tests/unit/infrastructure'))
from test_spin_shadow import definition


def main():
    source = (ROOT/'kernel_module/kd_api_provider.c').read_text()
    assert 'static bool api_bind;' in source
    assert 'module_param(api_bind, bool, 0444);' in source
    markers = ('int kd_api_provider_init(void)', 'void kd_api_provider_exit(void)',
               'void kd_api_provider_release(struct file *file)',
               'long kd_api_provider_ioctl(struct file *file, unsigned int command, unsigned long arg)')
    body = ('unsigned long kd_api_spin_unlock_target, kd_api_mutex_unlock_target;\n'
            'static bool kd_api_registered, api_bind;\n' +
            '\n'.join(definition(source, marker) for marker in markers))
    control = (ROOT/'include/kd_api_control.h').read_text()
    control = re.sub(r'^#include.*\n', '', control, flags=re.M)
    mutations = (
        ('default-registers', 'if (!api_bind)\n\t\treturn 0;', 'if (false)\n\t\treturn 0;'),
        ('disabled-controls', 'if (!kd_api_registered)\n\t\treturn -ENODEV;', 'if (false)\n\t\treturn -ENODEV;'),
        ('failed-register-active', 'if (!ret)\n\t\tkd_api_registered = true;', 'kd_api_registered = true;'),
    )
    with tempfile.TemporaryDirectory(prefix='kd-api-provider-') as name:
        path = Path(name)
        (path/'api_control.h').write_text(control)
        cc = shlex.split(os.environ.get('CC', 'gcc'))
        for label, text in [('production', body), *[(name, body.replace(old, new))
                                                  for name, old, new in mutations]]:
            if label != 'production':
                old = next(old for name, old, _ in mutations if name == label)
                assert body.count(old) == 1, label
            (path/'api_provider_production.h').write_text(text)
            subprocess.run([*cc, '-O2', '-Wall', '-Wextra', '-Werror', '-I'+str(path),
                            str(Path(__file__).with_name('api_provider_fixture.c')), '-o', str(path/'fixture')],
                           check=True, capture_output=True, text=True, timeout=30)
            result = subprocess.run([str(path/'fixture')], capture_output=True, text=True, timeout=10)
            assert result.returncode == (0 if label == 'production' else 1), (label, result)
            if label == 'production': print(result.stdout.strip())
            else: assert 'FAIL' in result.stderr, (label, result)
    print('[PASS] provider admission; 3 fail-closed mutations')


if __name__ == '__main__':
    main()
