"""VM-only registry policy execution; never calls a Native terminal target."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from test_native_schedule_contract import definition

ROOT = Path(__file__).resolve().parents[3]


def production_code():
    header = (ROOT / 'include/kd_service_calls.h').read_text()
    enums = header[header.index('enum kd_service_call_result {'):
                   header.index('/* Each live record')]
    desc = header[header.index('struct kd_service_call_desc {'):
                  header.index('enum kd_origin_call_phase {')]
    source = (ROOT / 'kernel_module/kd_service_calls.c').read_text()
    native = (ROOT / 'kernel_module/service_native.inc').read_text()
    storage = source[source.index('#define KD_SERVICE_CALL_MAX'):
                     source.index('static bool kd_service_call_requires_preempt_rcu')]
    return enums + desc + storage + '\n'.join(definition(source, name) for name in (
        'kd_service_call_context_valid', 'kd_service_call_valid',
        'kd_service_call_format', 'kd_service_call_configuration_size',
        'kd_service_call_register', 'kd_service_call_table_get',
        'kd_service_call_state_get', 'kd_service_call_page_get')) + '\n'.join(
            definition(native, name) for name in ('kd_service_schedule_origin_allowed',
                'kd_service_native_executor_pinned', 'kd_service_native_prepare'))


def main():
    code = production_code()
    variants = (
        ('production', None),
        ('terminal-wrong-address', (
            'desc->target == kallsyms_lookup_name("__stack_chk_fail")', 'desc->target != 0')),
        ('terminal-wrong-name', (
            'desc->symbol && !strcmp(desc->symbol, "__stack_chk_fail")', 'desc->symbol != NULL')),
        ('registry-64-slots', ('#define KD_SERVICE_CALL_MAX 128U', '#define KD_SERVICE_CALL_MAX 64U')),
        ('page-window-shifted', ('i = page * KD_SERVICE_CALL_ROWS_PER_PAGE;',
                                  'i = page * KD_SERVICE_CALL_ROWS_PER_PAGE + 1;')),
        ('generation-not-advanced', ('++kd_service_call_generation;', '(void)0;')),
        ('terminal-not-admitted', (
            'case KD_SERVICE_CALL_NONRETURNING_ORIGIN:\n\t\t/* The Native terminal',
            'case 999:\n\t\t/* The Native terminal')),
    )
    with tempfile.TemporaryDirectory(prefix='kd-native-terminal-contract-') as name:
        directory = Path(name)
        for label, mutation in variants:
            transformed = code
            if mutation:
                before, after = mutation
                assert transformed.count(before) == 1, label
                transformed = transformed.replace(before, after)
            (directory / 'production.h').write_text(transformed)
            binary = directory / label
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-I', str(directory), str(Path(__file__).with_name('native_terminal_contract_fixture.c')),
                '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
            if mutation:
                assert result.returncode == 1 and 'FAIL line=' in result.stderr, (
                    label, result.returncode, result.stdout, result.stderr)
                print('Native terminal/registry mutation detected:', label)
            else:
                assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
                print(result.stdout, end='')


if __name__ == '__main__':
    main()
