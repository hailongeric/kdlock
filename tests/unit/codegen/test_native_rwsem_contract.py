"""VM-only execution of production Native writer custody transitions.

The fixture supplies Native-return observations; live blocked acquisition and
the actual Native API are checked separately by the kernel helper fixture.
"""
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
    runtime = (ROOT / 'kernel_module/kd_service.c').read_text()
    native = (ROOT / 'kernel_module/service_native.inc').read_text()
    return enums + '\n'.join(definition(runtime, name) for name in (
        'kd_service_scope_released', 'kd_service_native_depth',
        'kd_service_native_pins', 'kd_service_native_find')) + '\n'.join(
            definition(native, name) for name in ('kd_service_native_reserve',
                'kd_service_schedule_origin_allowed', 'kd_service_native_executor_pinned',
                'kd_service_native_prepare', 'kd_service_native_finish'))


def main():
    code = production_code()
    variants = (
        ('production', None),
        ('rwsem-lock-not-admitted', (
            'case KD_SERVICE_CALL_RWSEM_WRITE_LOCK:\n\t\t/* Native down_write',
            'case 999:\n\t\t/* Native down_write')),
        ('rwsem-wrong-object', ('kind != KD_NATIVE_OWNER_RCU &&',
                                 '(kind == KD_NATIVE_OWNER_SPIN || kind == KD_NATIVE_OWNER_PREEMPT) &&')),
        ('rwsem-not-held', ('owner->held = rwsem_grant;', 'owner->held = false;')),
        ('rwsem-release-not-retired', (
            'if (!rwsem_grant)\n\t\t\towner->kind = KD_NATIVE_OWNER_FREE;',
            'if (!rwsem_grant)\n\t\t\towner->kind = KD_NATIVE_OWNER_RWSEM_WRITE;')),
        ('sleeping-under-native-pin', ('if (spins || rcu)\n\t\t\treturn -EOPNOTSUPP;',
                                        'if (spins && rcu)\n\t\t\treturn -EOPNOTSUPP;')),
        ('rwsem-unlocks-root-too-early', ('if (owner->held)\n\t\t\treturn false;',
                                          'if (owner->held && owner->kind != KD_NATIVE_OWNER_RWSEM_WRITE)\n\t\t\treturn false;')),
        ('rwsem-becomes-cpu-pin', (
            'kd_service_native_depth(root, KD_NATIVE_OWNER_PREEMPT);',
            'kd_service_native_depth(root, KD_NATIVE_OWNER_PREEMPT) +\n'
            '\t\tkd_service_native_depth(root, KD_NATIVE_OWNER_RWSEM_WRITE);')),
    )
    with tempfile.TemporaryDirectory(prefix='kd-native-rwsem-contract-') as name:
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
                '-I', str(directory), str(Path(__file__).with_name('native_rwsem_contract_fixture.c')),
                '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
            if mutation:
                assert result.returncode == 1 and 'FAIL line=' in result.stderr, (
                    label, result.returncode, result.stdout, result.stderr)
                print('Native writer policy mutation detected:', label)
            else:
                assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
                print(result.stdout, end='')


if __name__ == '__main__':
    main()
