"""Inspect already fetched measured ELF bytes/relocations; never execute them."""
from pathlib import Path
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
import hashlib,json
O=Path(__file__).parent;R=Path('/tmp/kdlock-nano-f7a84065-comparison-20261030')
unit=Path('/tmp/kdlock-continuation-f7a84065-provider.ko');expected='93a892843297888e1a000d41dcc560de4fd9fabd74d3d90f95ef68406b3b3c6d'
def sha(b):return hashlib.sha256(b).hexdigest()
def inspect(p):
 a={'sha256':sha(p.read_bytes()),'path':str(p),'sections':{},'relocations':{}}
 with p.open('rb') as f:
  e=ELFFile(f)
  for s in e.iter_sections():
   if s['sh_flags']&2 and s.name!='.note.gnu.build-id':a['sections'][s.name]={'size':s['sh_size'],'align':s['sh_addralign'],'sha256':sha(s.data())}
   if not isinstance(s,RelocationSection):continue
   target=e.get_section(s['sh_info'])
   if not target['sh_flags']&2:continue
   syms=e.get_section(s['sh_link']);rows=[]
   for r in s.iter_relocations():
    sym=syms.get_symbol(r['r_info_sym']);name=sym.name
    if not name and isinstance(sym['st_shndx'],int):name=e.get_section(sym['st_shndx']).name
    rows.append([r['r_offset'],r['r_info_type'],name,r.entry.get('r_addend',0)])
   a['relocations'][target.name]=rows
 return a
u=inspect(unit);assert u['sha256']==expected;points=json.loads((R/'current/points.json').read_text());profiles=sorted({r['profile'] for r in points});results=[]
for profile in profiles:
 p=R/'current/elfs'/profile/'build/provider/kernel_module/kdlock_km.ko';a=inspect(p);expected_point_sha={r['provider_sha256'] for r in points if r['profile']==profile};assert expected_point_sha=={a['sha256']}
 results.append({'profile':profile,'path':str(p),'sha256':a['sha256'],'point_rows':sum(r['profile']==profile for r in points),'allocated_sections_except_build_id_equal_unit':a['sections']==u['sections'],'allocated_relocations_equal_unit':a['relocations']==u['relocations'],'allocated_relocations':sum(map(len,a['relocations'].values()))})
r={'scope':'Static bytes and relocation recipes; not execution, causation or loaded physical placement proof.','unit_sha256':expected,'unit_text_bytes':u['sections']['.text']['size'],'profiles':results,'all_match':all(x['allocated_sections_except_build_id_equal_unit'] and x['allocated_relocations_equal_unit'] for x in results)}
(O/'measured-elf-proof.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
