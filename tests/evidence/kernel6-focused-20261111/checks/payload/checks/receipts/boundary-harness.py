
import hashlib, importlib.metadata, json, os
from pathlib import Path
import sys, unittest
root, result_file = map(Path, sys.argv[1:])
sys.path.insert(0, str(root))
versions = {name: importlib.metadata.version(name) for name in ('miasm','future','pyparsing')}
expected_versions = {'miasm':'0.1.5','future':'1.0.0','pyparsing':'2.4.7'}
if versions != expected_versions:
    raise RuntimeError('translation dependency versions differ: ' + repr(versions))
suite = unittest.defaultTestLoader.discover(str(root/'tests'), pattern='test_source_boundaries.py')
def flatten(test):
    if isinstance(test, unittest.TestSuite):
        return [item for child in test for item in flatten(child)]
    return [test.id()]
ids = flatten(suite)
expected = {'test_source_boundaries.SourceBoundaryTests.' + name for name in (
    'test_prefixed_native_call_stops_before_call_and_preserves_bytes',
    'test_private_clobber_call_keeps_typed_operation',
    'test_indirect_call_has_no_invented_target_or_call_site_cut',
    'test_version_and_budget_refusal_preserve_original_input')}
if len(ids) != 4 or set(ids) != expected:
    for detail in unittest.defaultTestLoader.errors:
        sys.stderr.write(detail + '\n')
    raise RuntimeError('exact four-test discovery differs: ' + repr(ids))
modules = {}
for name in ('disassem.compiler','disassem.fragment','disassem.source_decode','disassem.source_boundaries'):
    actual = Path(sys.modules[name].__file__).resolve(strict=True)
    expected_path = root/Path(name.replace('.', '/') + '.py')
    if actual != expected_path:
        raise RuntimeError('module was imported outside frozen input: ' + name)
    modules[name] = {'path':str(actual),'sha256':hashlib.sha256(actual.read_bytes()).hexdigest()}
result = unittest.TextTestRunner(verbosity=2).run(suite)
value = {'test_ids':ids,'tests_run':result.testsRun,'skips':[{'test':test.id(),'reason':reason} for test,reason in result.skipped],
         'failures':[{'test':test.id(),'traceback':detail} for test,detail in result.failures],
         'errors':[{'test':test.id(),'traceback':detail} for test,detail in result.errors],
         'expected_failures':[{'test':test.id(),'traceback':detail} for test,detail in result.expectedFailures],
         'unexpected_successes':[test.id() for test in result.unexpectedSuccesses],
         'successful':result.wasSuccessful(),'versions':versions,'modules':modules,
         'python':sys.version,'executable':sys.executable,'prefix':sys.prefix}
with result_file.open('x') as target:
    json.dump(value,target,indent=2,sort_keys=True)
    target.write('\n')
    target.flush()
    os.fsync(target.fileno())
sys.exit(0 if result.wasSuccessful() and result.testsRun == 4 and not result.skipped and
         not result.expectedFailures and not result.unexpectedSuccesses else 1)
