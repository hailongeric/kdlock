"""Retain complete warning classification and current build/runtime boundaries."""
from pathlib import Path
import hashlib,json,re
R=Path('/home/eric/vm/vm-shared/kdlock-main');D=R/'tests/evidence/kernel9-cohort-build-20261111'
P=Path('/tmp/kdlock-kernel9-build-collection-20261111-01/payload/receipts/build-01')
rows=[]
for n,line in enumerate((P/'kernel.log').read_text(errors='replace').splitlines(),1):
 if re.search(r'\b(?:warning|error|WARNING|ERROR):',line):
  kind='objtool' if line.startswith('vmlinux.o: warning: objtool:') else ('locale' if line.startswith('perl: warning:') else 'compiler')
  rows.append({'line':n,'kind':kind,'text':line})
assert len(rows)==54
counts={kind:sum(x['kind']==kind for x in rows) for kind in ['compiler','objtool','locale']}
assert counts=={'compiler':22,'objtool':26,'locale':6}
supplement={'scope':'Saved raw-log classification only; original driver receipt is unchanged.','kernel_log_sha256':hashlib.sha256((P/'kernel.log').read_bytes()).hexdigest(),'original_driver_kernel_rows':22,'complete_warning_lines':54,'kind_counts':counts,'rows':rows,'original_parser_omitted':['vmlinux.o objtool diagnostic prefix','perl locale diagnostic prefix'],'mutex_object_diagnostics':0,'mutex_object_recipe_echoes_excluded':3,'nls_diagnostics':0,'olddefconfig_kconfig_warning_lines':1,'runtime_validation':False}
(D/'warning-supplement.json').write_text(json.dumps(supplement,indent=2,sort_keys=True)+'\n')
audit=json.loads((D/'audit.json').read_text());audit['original_driver_diagnostic_counts']=audit.pop('warnings');audit['complete_kernel_warning_counts']=counts;audit['complete_kernel_warning_lines']=54
(D/'audit.json').write_text(json.dumps(audit,indent=2,sort_keys=True)+'\n')
p=D/'README.md';s=p.read_text()
old="""The mutex-object and NLS logs contain no diagnostic records. The kernel log
retains 22 warnings: one maple-tree frame warning, one unused-variable warning
and twenty fortify fixture diagnostics. Olddefconfig retains one Kconfig
multiline-string warning. None is removed or called a test pass.
[Exact diagnostics](collection/payload/receipts/build-01/result.json.gz)
"""
new="""The mutex-object and NLS logs contain no diagnostic records. The full kernel
log has 54 warning lines: 22 compiler records (one maple-tree frame, one unused
variable and twenty fortify fixture diagnostics), 26 objtool records, and six
locale-warning lines. Objtool reports handwritten returns, an indirect call,
function fallthrough and stack realignment; complete mitigation/unwind coverage
remains unproved. Olddefconfig adds one Kconfig multiline-string warning.
The original driver's diagnostic field counted only the 22 compiler rows;
its raw receipt is unchanged, and the saved-log supplement identifies every
omitted objtool/locale row. Three warning/error strings in the focused build
are echoed shell recipes, not emitted diagnostics.
[Complete warning classification](warning-supplement.json),
[original receipt](collection/payload/receipts/build-01/result.json.gz)
"""
assert s.count(old)==1;p.write_text(s.replace(old,new))
p=R/'README.md';s=p.read_text()
old="""lifetime checks. Static review is complete; corrected-kernel validation is
separate from the failed run.
"""
new="""lifetime checks. Static review and the [corrected kernel9 build](tests/evidence/kernel9-cohort-build-20261111/README.md)
passed. Runtime validation is blocked by platform content review of helper
preparation; kernel9 remains uninstalled. The failed run keeps its own verdict.
"""
assert s.count(old)==1;p.write_text(s.replace(old,new))
p=R/'docs/design/kdlock_redesign/04_evidence_and_reconciliation.md';s=p.read_text();needle='## 1 Active authority and scope\n';assert s.count(needle)==1
addition="""The [corrected kernel9 build](../../../tests/evidence/kernel9-cohort-build-20261111/README.md)
compiled the changed mutex object and full image plus its single NLS module.
All twelve commands returned zero, with the 54 full-kernel warning lines and
one configuration warning retained. Source/core/old-output/boot identities
remained unchanged, and the guest stayed on the recovered normal kernel.
Kernel9 was not installed or booted. Platform content review stopped the
delegated rwsem validation-helper preparation; it was not retried or recreated.
No corrected-core runtime result, deterministic race reproduction or additional
MM workload follows from this build.

"""
p.write_text(s.replace(needle,addition+needle))
p=R/'kernel/integration/RWSEM.md';s=p.read_text()
old="""addresses a post-publication cohort-batch race; the failure's exact queue
interleaving is unrecorded. `do_vmi_munmap` expansion remains proposed.
"""
new="""addresses a post-publication cohort-batch race; the failure's exact queue
interleaving is unrecorded. Its [kernel9 build](../../tests/evidence/kernel9-cohort-build-20261111/README.md)
passed, but runtime validation is blocked by platform content review and the
new image remains uninstalled. `do_vmi_munmap` expansion remains proposed.
"""
assert s.count(old)==1;p.write_text(s.replace(old,new))
(D/'finalize.py').write_bytes(Path(__file__).read_bytes())
files=[p for p in sorted(D.rglob('*')) if p.is_file() and p!=D/'SHA256SUMS']
(D/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(D))+'\n' for p in files))
print(json.dumps({'kernel_warning_lines':54,'categories':counts,'runtime_status':'blocked','installed':False}))

