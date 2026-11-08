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
    code += definition(device, 'static void kd_learning_clear_view(')
    code += definition(device, 'static bool kd_learning_upload_matches(')
    code += definition(device, 'static ssize_t kd_dev_write_locked(')
    wrapper = (ROOT / 'kernel_module/execution/wrapper_entry.inc').read_text()
    # The image consumer queries only retained-frame eligibility here. Actual
    # continuation/task lifetimes belong to the separate execution fixtures.
    code += '''
struct kd_exec_continuation { const void *service_ops; };
static bool fixture_service_frame;
static struct kd_exec_continuation *
kd_exec_frame_continuation(const struct kd_exec_frame *frame)
{
    static struct kd_exec_continuation service = { .service_ops = (void *)1 };
    (void)frame;
    return fixture_service_frame ? &service : NULL;
}
'''
    code += definition(wrapper, 'static void *kd_jit_bound_code(')
    code += definition(wrapper, 'static const struct kd_jit_image *kd_jit_select_image(')
    code += definition(wrapper, 'static inline bool kd_jit_bind_image(')
    with tempfile.TemporaryDirectory(prefix='kd-mutex-images-') as tmp:
        tmp = Path(tmp)
        (tmp / 'production.h').write_text(code)
        for fixture in ('mutex_images_fixture.c', 'spin_guard_images_fixture.c',
                        'direct_images_fixture.c', 'origin_images_fixture.c'):
            binary = tmp / fixture.removesuffix('.c')
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-sign-compare',
                '-I', str(ROOT / 'include'), '-I', str(tmp),
                str(ROOT / 'tests/unit/execution' / fixture),
                '-o', str(binary)], check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=20)
        # Exercise the actual private relocation writer, including source
        # lifetime pins and generated displacement rather than a model of it.
        mutations = {
            'missing-helper-pin': ('ret = kd_source_pin_root(target);', 'ret = 0;'),
            'missing-return-pin': ('ret = kd_source_pin_root(sites[i].return_ip);', 'ret = 0;'),
            'wrong-relocation-origin': ('displacement = (int)(target - next);',
                                        'displacement = (int)(target - next + 1);'),
            'missing-generated-opcode': ('code[sites[i].call_offset] != 0xe8 ||',
                                        'false ||'),
            'wrong-pool-selection': ('return kd_image_alloc_pool(true);',
                                     'return kd_image_alloc_pool(false);'),
        }
        for name, (before, after) in mutations.items():
            assert code.count(before) == 1, (name, code.count(before))
            (tmp / 'production.h').write_text(code.replace(before, after))
            binary = tmp / name
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-sign-compare',
                '-I', str(ROOT / 'include'), '-I', str(tmp),
                str(ROOT / 'tests/unit/execution/direct_images_fixture.c'),
                '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=20)
            assert result.returncode != 0 and 'Assertion' in result.stderr, (name, result)

        # The same upload path must validate the immutable instruction table
        # and both retained source endpoints before publishing an image.
        for name, before, after in (
            ('origin-validation-omitted',
             'ret = kd_image_validate_origin_sites(upload->image);', 'ret = 0;'),
            ('origin-source-pin-omitted',
             'ret = kd_source_pin_root(sites[i].ip);\n\t\tif (!ret)\n\t\t\tret = kd_source_pin_root(sites[i].next_ip);',
             'ret = 0;\n\t\tif (!ret)\n\t\t\tret = kd_source_pin_root(sites[i].next_ip);'),
            ('origin-successor-pin-omitted',
             'ret = kd_source_pin_root(sites[i].next_ip);', 'ret = 0;'),
        ):
            assert code.count(before) == 1, (name, code.count(before))
            (tmp / 'production.h').write_text(code.replace(before, after))
            binary = tmp / name
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-sign-compare',
                '-I', str(ROOT / 'include'), '-I', str(tmp),
                str(ROOT / 'tests/unit/execution/origin_images_fixture.c'),
                '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=20)
            assert result.returncode != 0 and 'Assertion' in result.stderr, (name, result)


if __name__ == '__main__':
    main()
