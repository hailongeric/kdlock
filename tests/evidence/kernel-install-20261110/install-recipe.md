# Candidate install and one-shot boot, prepared only

This is a source-reviewed one-off recipe, not an executed receipt. Do not run it
while PID 17106 or any descendant build remains. The helper
`/tmp/kdlock-kdrebuild1-checks.py` writes only fresh receipts and performs reads;
the explicit commands below perform the later authorized installation. Nothing
here deletes a kernel, modules, source, evidence or snapshot. No `make install`,
`grub-set-default`, configuration edit, mitigation change or module load is used.

The controller must first establish full `bzImage modules` completion with return
code 0, exact c6becf81 package and each reviewed overlay, with integration/source/config/tool receipts,
guest idle/no KD module or test job, enough host/guest headroom and a real usable
recovery point. A PID disappearing or a timeout alone is not completion/drain.
Retain the complete full-build log, including the combined-objtool return/indirect
branch warnings; staging or boot does not convert those warnings into a pass.

Run only after that review, from `/root`, on the guest. Copy the helper from the
source host to the fresh receipt first and pin its SHA256. Source edits stay on
the source host. Each command has an explicit bound and a separate retained log;
any failure stops the recipe for review. Do not automatically rerun a partial
install, delete partial artifacts, or expand its namespace.

## 1. Establish fresh paths and before receipts

```sh
KD_INSTALL_BASE=/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f
KD_INSTALL_SOURCE="$KD_INSTALL_BASE/source"
KD_INSTALL_BUILD="$KD_INSTALL_BASE/build"
KD_INSTALL_RELEASE=7.0.0-38-kdrebuild1
KD_INSTALL_STAGE="$KD_INSTALL_BASE/install-stage-kdrebuild1-01a1bc4f-v2"
KD_INSTALL_RECEIPTS="$KD_INSTALL_BASE/receipts/install-kdrebuild1-01a1bc4f-v2"
test ! -e "$KD_INSTALL_STAGE"
test ! -e "$KD_INSTALL_RECEIPTS"
test ! -e "/lib/modules/$KD_INSTALL_RELEASE"
test ! -e "/boot/vmlinuz-$KD_INSTALL_RELEASE"
test ! -e "/boot/System.map-$KD_INSTALL_RELEASE"
test ! -e "/boot/config-$KD_INSTALL_RELEASE"
test ! -e "/boot/initrd.img-$KD_INSTALL_RELEASE"
mkdir -m 700 "$KD_INSTALL_STAGE" "$KD_INSTALL_RECEIPTS"
```

The explicit `test` commands must succeed in a shell that stops on error; do not
paste later phases after a failed check. After securely copying the helper into
`$KD_INSTALL_RECEIPTS/checks.py`, record its checksum and retain the controller's
actual full-build/recovery/idle receipts beside these new receipts.

```sh
sha256sum "$KD_INSTALL_RECEIPTS/checks.py" > "$KD_INSTALL_RECEIPTS/helper.sha256"
timeout 30s python3 "$KD_INSTALL_RECEIPTS/checks.py" idle --output "$KD_INSTALL_RECEIPTS/idle-before.json"
timeout 600s python3 "$KD_INSTALL_RECEIPTS/checks.py" protect --output "$KD_INSTALL_RECEIPTS/protected-before.json"
timeout 120s python3 "$KD_INSTALL_RECEIPTS/checks.py" identity --output "$KD_INSTALL_RECEIPTS/build-identity-before.json"
timeout 30s grub-editenv /boot/grub/grubenv list > "$KD_INSTALL_RECEIPTS/grubenv-before.txt"
cp -- /boot/grub/grub.cfg "$KD_INSTALL_RECEIPTS/grub.cfg-before"
df -B1 / /boot "$KD_INSTALL_BASE" > "$KD_INSTALL_RECEIPTS/df-before.txt"
```

`protect` hashes every existing installed module payload without following
source/build symlinks, all existing kernel/config/map/initrd boot files, boot
aliases and the GRUB default files. `identity` captures bzImage, vmlinux,
configuration, System.map, Module.symvers, module inventories, public signing
certificate, BuildID notes, actual package source and tool binary/version pins.
It never exports private signing-key contents. Full external source/build
receipts remain the controller's proof, not inferred from these hashes alone.

## 2. Stage normal modules off the root filesystem

```sh
timeout 900s make -C "$KD_INSTALL_SOURCE" O="$KD_INSTALL_BUILD" KERNELRELEASE="$KD_INSTALL_RELEASE" INSTALL_MOD_PATH="$KD_INSTALL_STAGE" INSTALL_MOD_STRIP=1 modules_install > "$KD_INSTALL_RECEIPTS/modules-install-stage.log" 2>&1
timeout 900s python3 "$KD_INSTALL_RECEIPTS/checks.py" modules --root "$KD_INSTALL_STAGE" --output "$KD_INSTALL_RECEIPTS/modules-stage.json"
timeout 120s python3 "$KD_INSTALL_RECEIPTS/checks.py" identity --output "$KD_INSTALL_RECEIPTS/build-identity-after-stage.json"
cmp "$KD_INSTALL_RECEIPTS/build-identity-before.json" "$KD_INSTALL_RECEIPTS/build-identity-after-stage.json"
du -s -B1 "$KD_INSTALL_STAGE/lib/modules/$KD_INSTALL_RELEASE" > "$KD_INSTALL_RECEIPTS/module-stage-bytes.txt"
```

Actual vendor `scripts/Makefile.modinst` copies, strips debug data, then signs.
`CONFIG_MODULE_COMPRESS_ZSTD=y` does not compress installation when
`CONFIG_MODULE_COMPRESS_ALL` is off; expect `.ko`, not `.ko.zst`. The normal
vendor signing script permits unsigned staging drivers excluded by its inclusion
list. Record signer/key/hash-algorithm counts exactly; do not invent a new
unsigned-module rejection, force signing, or suppress a real installation error.
The helper enforces the exact modules.order inventory, candidate vermagic and no
remaining DWARF debug sections, while preserving BTF and actual vendor signatures.

## 3. Check root budget, install only the fresh candidate namespace

Choose and record explicit remaining-root reserve and initrd temporary-space
budget from the measured stage and current free bytes. For this observed root
filesystem, a reviewed example is 1 GiB left free and 256 MiB for the new initrd;
these are install budgets, not runtime capacities or guarantees. Verify root and
/boot are still the same filesystem, and require free bytes to exceed stage
allocated bytes + bzImage/config/map bytes + that initrd budget + the reserve.
Stop if this does not fit; do not reclaim unrelated files.

After the controller explicitly chooses both budget values, the numerical check
is concrete (the two values below are the reviewable example, not hidden defaults):

```sh
KD_INSTALL_ROOT_RESERVE_BYTES=1073741824
KD_INSTALL_INITRD_BUDGET_BYTES=268435456
timeout 30s python3 - "$KD_INSTALL_STAGE" "$KD_INSTALL_BUILD" "$KD_INSTALL_ROOT_RESERVE_BYTES" "$KD_INSTALL_INITRD_BUDGET_BYTES" "$KD_INSTALL_RECEIPTS/root-budget.json" <<'PY'
import json, os, sys
from pathlib import Path
stage, build = Path(sys.argv[1]), Path(sys.argv[2])
reserve, initrd = int(sys.argv[3]), int(sys.argv[4])
if reserve <= 0 or initrd <= 0: raise RuntimeError('explicit positive budgets required')
if os.stat('/').st_dev != os.stat('/boot').st_dev: raise RuntimeError('root/boot layout changed')
allocated = 0
for directory, dirs, names in os.walk(stage, followlinks=False):
    dirs[:] = [n for n in dirs if not (Path(directory)/n).is_symlink()]
    for name in names: allocated += (Path(directory)/name).lstat().st_blocks * 512
boot = sum((build/p).stat().st_size for p in ('arch/x86/boot/bzImage','System.map','.config'))
fs = os.statvfs('/'); free = fs.f_bavail * fs.f_frsize
needed = allocated + boot + initrd + reserve
if free <= needed: raise RuntimeError('root budget does not fit: '+str((free,needed)))
with open(sys.argv[5], 'x') as f:
    json.dump(dict(free=free,modules=allocated,boot=boot,initrd_budget=initrd,reserve=reserve,needed=needed),f)
    f.write('\n'); f.flush(); os.fsync(f.fileno())
PY
```

After the numerical check and another `idle` receipt:

```sh
timeout 30s python3 "$KD_INSTALL_RECEIPTS/checks.py" idle --output "$KD_INSTALL_RECEIPTS/idle-before-root-install.json"
test ! -e "/lib/modules/$KD_INSTALL_RELEASE"
timeout 180s cp -a -- "$KD_INSTALL_STAGE/lib/modules/$KD_INSTALL_RELEASE" "/lib/modules/$KD_INSTALL_RELEASE"
timeout 120s depmod -a -e -F "$KD_INSTALL_BUILD/System.map" "$KD_INSTALL_RELEASE" > "$KD_INSTALL_RECEIPTS/depmod-installed.log" 2>&1
timeout 900s python3 "$KD_INSTALL_RECEIPTS/checks.py" modules --root / --output "$KD_INSTALL_RECEIPTS/modules-installed.json"
```

Compare relative module names, sizes and SHA256 from `modules-stage.json` and
`modules-installed.json`; only the root prefix may differ. A successful copy or
depmod return alone is not that comparison. Preserve every warning in its log.
The exact comparison is:

```sh
timeout 30s python3 - "$KD_INSTALL_RECEIPTS" <<'PY'
import json, sys
from pathlib import Path
r=Path(sys.argv[1])
def table(name):
    data=json.loads((r/name).read_text()); root=Path(data['root'])
    return sorted((str(Path(x['path']).relative_to(root)),x['size'],x['sha256'],x['mode']) for x in data['modules'])
if table('modules-stage.json') != table('modules-installed.json'): raise RuntimeError('installed copy differs')
PY
```

Copy exactly the following three files with exclusive creation (`open(...,'xb')`),
mode 0644 and file/directory fsync; refuse an existing destination:

| Built input | New destination |
| --- | --- |
| build/arch/x86/boot/bzImage | /boot/vmlinuz-7.0.0-38-kdrebuild1 |
| build/System.map | /boot/System.map-7.0.0-38-kdrebuild1 |
| build/.config | /boot/config-7.0.0-38-kdrebuild1 |

Verify those destination hashes against the captured build identity. Keep
vmlinux and Module.symvers in the separate build/receipt namespace; there is no
reason to spend root space on a second vmlinux. Then use the existing tools:

```sh
timeout 60s python3 - "$KD_INSTALL_BUILD" "$KD_INSTALL_RECEIPTS" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
b,r=Path(sys.argv[1]),Path(sys.argv[2]); release='7.0.0-38-kdrebuild1'
identity=json.loads((r/'build-identity-after-stage.json').read_text())
pins={x['path']:x['sha256'] for x in identity['artifacts']}
pairs=(('arch/x86/boot/bzImage','vmlinuz'),('System.map','System.map'),('.config','config'))
for relative,prefix in pairs:
    source=b/relative; target=Path('/boot')/(prefix+'-'+release)
    data=source.read_bytes()
    if hashlib.sha256(data).hexdigest()!=pins[str(source)]: raise RuntimeError('built input changed')
    with open(target,'xb') as out:
        os.fchmod(out.fileno(),0o644); out.write(data); out.flush(); os.fsync(out.fileno())
    if hashlib.sha256(target.read_bytes()).hexdigest()!=pins[str(source)]: raise RuntimeError('boot copy differs')
fd=os.open('/boot',os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
PY
```

```sh
timeout 300s update-initramfs -c -k "$KD_INSTALL_RELEASE" > "$KD_INSTALL_RECEIPTS/update-initramfs.log" 2>&1
test -s "/boot/initrd.img-$KD_INSTALL_RELEASE"
timeout 120s update-grub > "$KD_INSTALL_RECEIPTS/update-grub.log" 2>&1
timeout 30s grub-script-check /boot/grub/grub.cfg > "$KD_INSTALL_RECEIPTS/grub-script-check.log" 2>&1
timeout 120s lsinitramfs "/boot/initrd.img-$KD_INSTALL_RELEASE" > "$KD_INSTALL_RECEIPTS/initrd-contents.txt"
timeout 600s python3 "$KD_INSTALL_RECEIPTS/checks.py" verify-protected --snapshot "$KD_INSTALL_RECEIPTS/protected-before.json" --output "$KD_INSTALL_RECEIPTS/protected-after.json"
timeout 30s python3 "$KD_INSTALL_RECEIPTS/checks.py" grub --output "$KD_INSTALL_RECEIPTS/grub-installed.json"
df -B1 / /boot "$KD_INSTALL_BASE" > "$KD_INSTALL_RECEIPTS/df-after.txt"
```

The machine's actual root is ext4 on virtio-SCSI. Before arming, run only
`modprobe -S "$KD_INSTALL_RELEASE" --show-depends` (never load) separately for
`virtio_pci`, `virtio_scsi`, `sd_mod`, `ext4` and `virtio_net`, retaining each
output. Resolve every `insmod` dependency to a valid installed candidate module.
For the four root drivers, also verify every exact relative module path occurs
in `initrd-contents.txt`; an actual built-in dependency needs no initrd module
file. `virtio_net` can load from the installed modules after the local ext4 root
mounts, so its valid installed dependencies need not occur in this initrd. Refuse
missing/ambiguous closure, not just a missing top-level module name. Confirm candidate initrd existence/hash/size,
root reserve and unchanged normal/recovery boot files. Retain an install summary
of file hashes and these dependency checks before proceeding.

```sh
timeout 120s python3 - "$KD_INSTALL_RECEIPTS" <<'PY'
import hashlib,json,os,shlex,subprocess,sys
from pathlib import Path
r=Path(sys.argv[1]); release='7.0.0-38-kdrebuild1'
listed=(r/'initrd-contents.txt').read_text().splitlines();closure={}
for module in ('virtio_pci','virtio_scsi','sd_mod','ext4','virtio_net'):
    result=subprocess.run(['modprobe','-S',release,'--show-depends',module],capture_output=True,text=True,timeout=20,check=True)
    dependencies=[]
    for line in result.stdout.splitlines():
        words=shlex.split(line)
        if not words: continue
        if words[0]=='builtin': continue
        if words[0]!='insmod' or len(words)<2: raise RuntimeError('non-file module dependency: '+line)
        path=Path(words[1]); suffix='lib/modules/'+release+'/'+str(path.relative_to('/lib/modules/'+release))
        if not path.is_file(): raise RuntimeError('installed candidate dependency missing: '+str(path))
        if module != 'virtio_net' and not any(name==suffix or name.endswith('/'+suffix) for name in listed):
            raise RuntimeError('root dependency missing from initrd: '+str(path))
        dependencies.append(str(path))
    closure[module]=dict(stdout=result.stdout,stderr=result.stderr,files=dependencies)
initrd=Path('/boot/initrd.img-'+release)
budget=json.loads((r/'root-budget.json').read_text())
fs=os.statvfs('/');free=fs.f_bavail*fs.f_frsize
if free < budget['reserve']: raise RuntimeError('root reserve consumed')
if initrd.stat().st_size > budget['initrd_budget']: raise RuntimeError('initrd exceeded reviewed budget')
with open(r/'boot-dependencies.json','x') as f:
    json.dump(dict(closure=closure,initrd_sha256=hashlib.sha256(initrd.read_bytes()).hexdigest(),initrd_bytes=initrd.stat().st_size,root_free=free),f,sort_keys=True,indent=2)
    f.write('\n'); f.flush(); os.fsync(f.fileno())
PY
```

## 4. Arm only a one-shot entry; reboot remains a separate controller step

The effective normal default comes from the unchanged
`/etc/default/grub.d/99-kdlock-nopvspin.cfg`, not `/etc/default/grub`'s earlier 0:

```text
gnulinux-advanced-aa0bde06-47f6-4049-aaaf-13d052e53961>gnulinux-7.0.0-38-kdlock1-advanced-aa0bde06-47f6-4049-aaaf-13d052e53961
```

The helper verifies this generated default, unique candidate/normal/legacy menu
entries, GRUB syntax and an empty next_entry. Do not edit either default file,
boot aliases, mitigation options or saved_entry. Recheck controller recovery,
console access, guest idle/unloaded status and exact install receipts immediately
before the following one-shot mutation:

```sh
timeout 30s python3 "$KD_INSTALL_RECEIPTS/checks.py" idle --output "$KD_INSTALL_RECEIPTS/idle-before-arm.json"
timeout 30s grub-reboot 'gnulinux-advanced-aa0bde06-47f6-4049-aaaf-13d052e53961>gnulinux-7.0.0-38-kdrebuild1-advanced-aa0bde06-47f6-4049-aaaf-13d052e53961'
timeout 30s python3 "$KD_INSTALL_RECEIPTS/checks.py" grub --armed --output "$KD_INSTALL_RECEIPTS/grub-armed.json"
timeout 30s sync
```

Compare before/after grubenv keys: only next_entry may change, and grub.cfg must
match its installed hash. A GRUB abstraction that cannot persist one-shot clearing
is a blocker; this guest currently uses direct ext4 on /dev/sda1. Retain all
receipts and helper hashes. The controller can then separately issue bounded
`systemctl reboot` under the already-authorized recovery gate and monitor the
console/reconnect. This preparation has not issued that command.

## 5. Reconnect and active CALL_DEPTH gate before any fixture/JIT

Record uname release, changed boot ID, /proc/version, /proc/cmdline, taint,
installed image hashes, actual running kernel BuildID from /sys/kernel/notes,
and complete boot log before claiming a candidate boot. Compare the BuildID to
the captured vmlinux notes, not just the release string. Verify GRUB consumed
next_entry and still pins kdlock1 for the next ordinary boot.

The config has CONFIG_MITIGATION_CALL_DEPTH_TRACKING=y, which only compiles the
capability. Actual X86_FEATURE_CALL_DEPTH activation selects
call_depth_return_thunk and changes flags. Before running any source/fixture/JIT,
read all /proc/cpuinfo flag rows and the retbleed, indirect_target_selection and
spectre_v2 status files. If call_depth is active, refuse this lane; do not disable
mitigations or change boot options to force the test through. Current kdlock1 has
no call_depth flag, Enhanced/Automatic IBRS and aligned ITS thunks, but that does
not substitute for checking the fresh boot. Record full objtool warnings and
unvalidated return/indirect-branch coverage independently of that gate.

Only after this boot/gate receipt may the controller start the separately scoped
fixture. Ordinary boot is not JIT publication, returned execution, T01-T56
acceptance or performance evidence.
