"""Copied reviewed data-only helpers; no archived code execution."""
from pathlib import Path
import re
import tarfile
import nano_core as a

def apply_exact_patch(patch, git, commit):
    """Same complete-context reconstruction as the retained baseline audit."""
    lines = patch.decode().splitlines(keepends=True)
    i = 0
    patched, hunks = {}, []
    while i < len(lines):
        a.need(lines[i].startswith('diff --git a/'), 'patch diff header')
        i += 1
        a.need(lines[i].startswith('--- a/'), 'patch old header')
        path = lines[i][6:].strip()
        i += 1
        a.need(lines[i] == '+++ b/'+path+'\n', 'patch new header')
        i += 1
        current = git.blob(commit, path).decode().splitlines(keepends=True)
        cursor = 0
        while i < len(lines) and lines[i].startswith('@@ '):
            header = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*\n', lines[i])
            a.need(header is not None, 'patch hunk header')
            old_count, new_count = int(header[2] or 1), int(header[4] or 1)
            i += 1
            old, new = [], []
            while len(old) < old_count or len(new) < new_count:
                line = lines[i]
                a.need(line[:1] in (' ', '+', '-'), 'patch hunk line')
                if line[0] in ' -': old.append(line[1:])
                if line[0] in ' +': new.append(line[1:])
                i += 1
            a.need(len(old) == old_count and len(new) == new_count and old, 'patch hunk lengths')
            matches = [n for n in range(cursor, len(current)-len(old)+1)
                       if current[n:n+len(old)] == old]
            a.need(len(matches) == 1, 'patch needs exactly one full-context match: '+path)
            start = matches[0]
            current[start:start+len(old)] = new
            cursor = start+len(new)
            hunks.append(dict(path=path, applied_line=start+1, header_old_line=int(header[1]),
                              old_lines=old_count, new_lines=new_count))
        a.need(path not in patched, 'duplicate patch file')
        patched[path] = ''.join(current).encode()
    return patched, hunks


def tokens(name):
    result = {name, Path(name).name}
    if name.endswith('.c'):
        result.add(str(Path(name).with_suffix('.o')))
        result.add(Path(name).with_suffix('.o').name)
    return result


def capture_elfs(archive, wanted, out):
    """Copy only independently authenticated module bytes, never tar paths."""
    prefix = a.safe(archive.meta['archive_prefix'])+'/'
    records = {}
    for group in archive.meta['groups']:
        path = archive.directory / group['file']
        a.need(a.file_sha(path) == group['sha256'], 'archive changed before ELF capture')
        with tarfile.open(path, 'r|gz') as tar:
            for member in tar:
                if not member.name.startswith(prefix):
                    continue
                name = member.name[len(prefix):]
                if name not in wanted:
                    continue
                a.need(name not in records and member.isfile(), 'duplicate/nonregular selected ELF')
                a.need(member.size <= 256*1024*1024, 'oversized selected ELF')
                data = tar.extractfile(member).read()
                a.need(len(data) == member.size and a.sha(data) == wanted[name] == archive.hashes[name],
                       'selected ELF differs from actual measured binary map: '+name)
                destination = out/'elfs'/a.safe(name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                records[name] = dict(sha256=wanted[name], bytes=len(data),
                    file=str(destination), archive_group=group['file'], archive_member=member.name,
                    modinfo=archive.modinfo[name], executed=False)
    a.need(set(records) == set(wanted), 'missing actual measured ELF')
    return records
