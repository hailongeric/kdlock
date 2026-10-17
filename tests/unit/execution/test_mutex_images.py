"""Guest userspace checks of production upload/publication and generation rules."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from source_text import ROOT
from test_spin_shadow import definition as extract_definition


def definition(source, prefix):
    return extract_definition(source, next(line for line in source.splitlines() if line.startswith(prefix)))


def main():
    lifecycle = (ROOT / 'kernel_module/execution/registry_lifecycle.inc').read_text()
    device = (ROOT / 'kernel_module/sys.c').read_text()
    code = definition((ROOT / 'include/exe.h').read_text(),
                      'static inline unsigned int zz_hash(')
    for signature in ('struct kd_exe_info *kd_get_exe(',
                      'bool kd_exe_publish_status('):
        code += definition(lifecycle, signature)
    code += (ROOT / 'kernel_module/execution/images.inc').read_text()
    code += definition(device, 'static ssize_t kd_dev_write_locked(')
    wrapper = (ROOT / 'kernel_module/execution/wrapper_entry.inc').read_text()
    code += definition(wrapper, 'static void *kd_jit_bound_code(')
    code += definition(wrapper, 'static bool kd_jit_bind_image(')
    with tempfile.TemporaryDirectory(prefix='kd-mutex-images-') as tmp:
        tmp = Path(tmp)
        (tmp / 'production.h').write_text(code)
        binary = tmp / 'check'
        subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
            '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-sign-compare',
            '-I', str(ROOT / 'include'), '-I', str(tmp),
            str(ROOT / 'tests/unit/execution/mutex_images_fixture.c'),
            '-o', str(binary)], check=True, timeout=30)
        subprocess.run([str(binary)], check=True, timeout=20)


if __name__ == '__main__':
    main()
