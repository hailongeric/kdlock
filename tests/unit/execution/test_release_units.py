"""VM-only production release-unit completion and Native-tail routing.

Run the real KD release consumer, CALL completion, typed Native RPC consumer
and service loop. Physical lock operations and the final Native transport are
supplied primitives; existing test_native_service_join covers that transport's
actual registry/ACCEPT/release/ACK path.
"""
import os
import resource
import shlex
import signal
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source, without_includes
from test_spin_shadow import definition


def production():
    declarations = '\n'.join(without_includes(read_source(ROOT / name)) for name in (
        'include/kd_regs.h', 'include/kd_call.h'))
    declarations += '\n'.join(line for line in read_source(ROOT / 'include/exe.h').splitlines()
                              if line.startswith('#define KD_EXE_')) + '\n'
    for path, names in (
        ('include/kd_wait_queue.h', ('enum kd_wait_state {',)),
        ('include/kd_exec_cont.h', ('enum kd_exec_cont_state {', 'enum kd_exec_cont_wait {',
                                  'enum kd_exec_service_api {', 'struct kd_exec_service_call {')),
        ('include/kd_service_calls.h', ('enum kd_service_call_context {',
                                       'enum kd_origin_call_phase {', 'struct kd_origin_call {')),
    ):
        source = read_source(ROOT / path)
        declarations += '\n'.join(definition(source, name).rstrip() + ';' for name in names) + '\n'
    continuation = read_source(ROOT / 'kernel_module/execution/continuation.inc')
    service = read_source(ROOT / 'kernel_module/kd_service.c')
    code = '\n'.join(definition(continuation, name) for name in (
        'int kd_exec_cont_service_complete(struct kd_exec_continuation *cont,',
        'int kd_exec_cont_native_complete(struct kd_exec_continuation *cont, u64 sequence)'))
    code += '\n' + '\n'.join(definition(service, name) for name in (
        'static bool kd_service_owner_live(const struct kd_service_owner *owner)',
        'static unsigned int kd_service_scope_depth(const void *argument)',
        'static bool kd_service_scope_released(const void *scope)',
        'static bool kd_service_scope_outer_released(const void *argument)',
        'static struct kd_service_owner *\nkd_service_find_owner(struct kd_service_scope *scope, unsigned long object)',
        'static int kd_service_release_boundary(struct kd_service_root *root, int status)',
        'static bool kd_service_native_release_context(unsigned int context)',
        'static int kd_service_primitive_call(struct kd_service_root *root)',
        'static int kd_service_release_call(struct kd_service_root *root)',
        'static int kd_service_handoff(struct kd_service_root *root)',
        'static int kd_service_run_scope(struct kd_service_root *root, int status)'))
    return declarations, code


def replace_once(text, before, after):
    assert text.count(before) == 1, (before, text.count(before))
    return text.replace(before, after, 1)


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    declarations, code = production()
    mutations = {
        'resume_after_kd_release': lambda text: replace_once(text,
            'return kd_service_release_boundary(root,\n\t\tkd_exec_cont_service_complete(cont, NULL, 0));',
            'return kd_exec_cont_service_complete(cont, NULL, 0);'),
        'resume_after_native_release': lambda text: replace_once(text,
            'if (release)\n\t\treturn kd_service_release_boundary(root, result);',
            'if (release && false)\n\t\treturn kd_service_release_boundary(root, result);'),
        'consume_release_call_twice': lambda text: replace_once(text,
            'cont->packet->orig_ax = KD_REG_ORIGIN_SUFFIX_TAG;',
            'cont->packet->sp += sizeof(unsigned long);\n\tcont->packet->orig_ax = KD_REG_ORIGIN_SUFFIX_TAG;'),
        'finish_at_downgrade': lambda text: replace_once(text,
            'case KD_SERVICE_RWSEM_DOWNGRADE:\n\t\tkd_admission_downgrade',
            'case KD_SERVICE_RWSEM_DOWNGRADE:\n\t\towner->released = true;\n\t\tkd_admission_downgrade'),
    }
    with tempfile.TemporaryDirectory(prefix='kd-release-units-') as directory:
        path = Path(directory)
        (path / 'release_types.h').write_text(declarations)
        for name, mutate in [('production', None), *mutations.items()]:
            (path / 'release_production.h').write_text(code if mutate is None else mutate(code))
            binary = path / name
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-UNDEBUG',
                '-I', str(path), str(ROOT / 'tests/unit/execution/release_units_fixture.c'),
                '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
            if mutate is None:
                assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
                print(result.stdout, end='')
                for mode in ('pending', 'unadvanced'):
                    refused = subprocess.run([str(binary), mode], capture_output=True,
                                             text=True, timeout=15)
                    assert refused.returncode == -signal.SIGABRT and 'Assertion' in refused.stderr, (
                        mode, refused.returncode, refused.stdout, refused.stderr)
                    print('release boundary refused incomplete CALL:', mode)
            else:
                assert result.returncode == -signal.SIGABRT and 'Assertion' in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr)
                print('release unit mutation detected:', name)


if __name__ == '__main__':
    main()
