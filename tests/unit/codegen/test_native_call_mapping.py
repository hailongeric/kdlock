"""VM-only execution of production map validation, marshaling and owner lifetime.

The fixture substitutes module/source primitives; no allocation API or kernel
workload executes here. Live original-task stacks and bridge returns are separate.
"""
import os
import re
from pathlib import Path
import shlex
import subprocess
import tempfile

from test_native_schedule_contract import definition

ROOT = Path(__file__).resolve().parents[3]


def registry_definition(source, name):
    # Locate the declaration, not an earlier call (get calls put before its
    # definition). Keep the selected production function body byte-identical.
    match = re.search(r'^[A-Za-z_][A-Za-z_0-9 *]*\b' + re.escape(name) + r'\(', source, re.MULTILINE)
    assert match, name
    return definition(source[match.start():], name)


def production_code():
    header = (ROOT / 'include/kd_service_calls.h').read_text()
    source = (ROOT / 'kernel_module/kd_service_calls.c').read_text()
    return (header[header.index('enum kd_service_call_result {'):header.index('enum kd_native_owner_kind {')] +
            header[header.index('struct kd_service_call_desc {'):header.index('enum kd_origin_call_phase {')] +
            source[source.index('#define KD_SERVICE_CALL_MAX'):source.index('static bool kd_service_call_requires_preempt_rcu')] +
            'void kd_service_call_put(struct kd_service_call_entry *entry);\n' +
            '\n'.join(registry_definition(source, name) for name in (
                'kd_service_call_context_valid', 'kd_service_call_valid', 'kd_service_call_mapped_valid',
                'kd_service_call_format', 'kd_service_call_configuration_size', 'kd_service_call_register',
                'kd_service_call_mapped_configuration_size', 'kd_service_call_register_mapped',
                'kd_service_call_unregister', 'kd_service_call_get', 'kd_service_call_put',
                'kd_service_call_matches', 'kd_service_call_invocation_matches',
                'kd_service_call_arguments', 'kd_service_calls_pin')))


def main():
    code = production_code()
    mutations = {
        'wrong-version-admitted': ('desc->version != KD_SERVICE_CALL_MAP_V1 ||', 'false ||'),
        'undeclared-source-argument': ('argument - KD_SERVICE_ARG_SOURCE0 >= desc->source.nargs',
                                     'argument - KD_SERVICE_ARG_SOURCE0 >= 6'),
        'unused-selector-admitted': ('if (argument != KD_SERVICE_ARG_UNUSED)', 'if (false)'),
        'source-return-substituted': ('arguments[i] = return_ip;', 'arguments[i] = packet->ip;'),
        'minus-one-becomes-zero': ('arguments[i] = ~0UL;', 'arguments[i] = 0;'),
        'execution-root-not-pinned': ('result = kd_source_pin_root(kd_service_call_entries[i].execution_target);',
                                      'result = 0;'),
        'execution-target-not-matched': ('entry->execution_target == execution_target;',
                                         '(entry->execution_target || !execution_target);'),
    }
    with tempfile.TemporaryDirectory(prefix='kd-native-call-mapping-') as temporary:
        directory = Path(temporary)
        for name, mutation in [('production', None), *mutations.items()]:
            candidate = code
            if mutation:
                before, after = mutation
                assert candidate.count(before) == 1, (name, candidate.count(before))
                candidate = candidate.replace(before, after)
            (directory / 'production.h').write_text(candidate)
            for buckets in ((1,) if mutation else (1, 0)):
                binary = directory / f'{name}-buckets{buckets}'
                configuration = ['-DCONFIG_SLAB_BUCKETS=1'] if buckets else []
                subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                    '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', *configuration, '-I', str(directory),
                    '-I', str(ROOT / 'include'), str(Path(__file__).with_name('native_call_mapping_fixture.c')),
                    '-o', str(binary)], check=True, timeout=30)
                result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
                if mutation:
                    assert result.returncode == 1 and 'FAIL line=' in result.stderr, (
                        name, buckets, result.returncode, result.stdout, result.stderr)
                    print('Native argument-map negative control detected:', name)
                else:
                    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
                    print(f'CONFIG_SLAB_BUCKETS={buckets}: ' + result.stdout, end='')


if __name__ == '__main__':
    main()
