"""Complete compiler process with per-lookup metadata; never publishes code."""
from pathlib import Path
import builtins
import json
import os
import sys

sys.dont_write_bytecode=True
root, entry_text, telemetry_path = sys.argv[1:]
sys.path.insert(0,str(Path(root)/'disassem'))
import disassem as translator

records=[]
opens=0
real_lookup=translator.get_kernel_symbol

def opened(path,*args,**kwargs):
    global opens
    if os.fspath(path)=='/proc/kallsyms':
        opens+=1
    return builtins.open(path,*args,**kwargs)

def lookup(name,default=0):
    value=real_lookup(name,default)
    cache=translator.kernel_symbols.current() if hasattr(translator,'kernel_symbols') else None
    tokens=cache._tokens if cache is not None else None
    eligible=bool(tokens is not None and name in tokens and int(tokens[name],16))
    records.append(dict(name=name,default=default,address=value,core_reused=eligible))
    return value

translator.open=opened
translator.get_kernel_symbol=lookup
entry=int(entry_text,16)
result=dict(returncode=None,requests=records,dependency=translator.DEPENDENCY_IDENTITY)
try:
    translator.diagnostics.begin(0,entry)
    with translator.memread.device_session.session():
        result['returncode']=translator.dis_assem(0,entry,'mutex',body_witness=False,abi=2,trusted_source=True)
    raise SystemExit(result['returncode'])
except Exception as error:
    result['error']=f'{type(error).__name__}: {error}'
    translator.diagnostics.error('TRANSLATION_FAILED','raise',result['error'])
    raise
finally:
    result.update(symbol_opens=opens,lookup_count=len(records),
        core_reused=sum(record['core_reused'] for record in records))
    Path(telemetry_path).write_text(json.dumps(result,indent=2)+'\n')
