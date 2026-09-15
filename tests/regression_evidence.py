"""Retain a selected run without relying on mutable daemon or /tmp workspaces.

Only declared local evidence is collected, after callers drain. Archive hashes
describe captured bytes; they are not JIT witnesses or immutable-code versions.
"""

import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

TEMP_ROOT = Path("/tmp")
DECLARATION = re.compile(
    r"^\s*(?:\[INFO\]\s+)?Evidence(?P<file> file)?:\s+(?P<path>\S+)\s*$",
    re.MULTILINE,
)
# Describe the tools used by the existing Makefiles/translator, not an install
# recipe. Never execute an arbitrary CC/MAKEFLAGS value or dump the whole env.
BUILD_ENVIRONMENT = (
    "PATH",
    "CC",
    "HOSTCC",
    "CFLAGS",
    "CPPFLAGS",
    "LDFLAGS",
    "MAKEFLAGS",
    "KDIR",
    "CROSS_COMPILE",
    "ARCH",
    "PYTHONPATH",
    "PYTHONHOME",
    "VIRTUAL_ENV",
    "LC_ALL",
)
TOOLS = ("bash", "gcc", "cc", "make", "as", "ld", "objcopy", "objdump")
PYTHON_METADATA = """
import importlib.metadata as metadata
import json, sys
names = ('miasm', 'pyelftools', 'future', 'pyparsing')
packages = {}
for name in names:
    package = metadata.distribution(name)
    packages[name] = {'version': package.version,
                      'location': str(package.locate_file('')),
                      'requires': package.requires or []}
print(json.dumps({'executable': sys.executable, 'version': sys.version,
                  'prefix': sys.prefix, 'base_prefix': sys.base_prefix,
                  'packages': packages}))
"""


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def regular_bytes(path):
    """Refuse links/devices and detect a file changed while being captured."""
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or path.resolve() != path:
        raise RuntimeError(f"evidence is not a regular local file: {path}")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        opened = os.fstat(source.fileno())
        if not stat.S_ISREG(opened.st_mode) or file_identity(before) != file_identity(
            opened
        ):
            raise RuntimeError(f"evidence replaced before read: {path}")
        data = source.read()
        after = os.fstat(source.fileno())
    if file_identity(before) != file_identity(after):
        raise RuntimeError(f"evidence changed during capture: {path}")
    if (
        file_identity(before) != file_identity(path.lstat())
        or len(data) != before.st_size
    ):
        raise RuntimeError(f"evidence replaced during capture: {path}")
    return data, stat.S_IMODE(before.st_mode)


def tree_files(path, links=None):
    """Never follow an evidence directory's links into unrelated files."""
    if path.is_symlink() or path.resolve() != path or not path.is_dir():
        raise RuntimeError(f"invalid evidence directory: {path}")
    files = []
    for directory, dirs, names in os.walk(path, followlinks=False):
        dirs.sort()
        for name in [*dirs, *sorted(names)]:
            child = Path(directory) / name
            mode = child.lstat().st_mode
            if stat.S_ISLNK(mode) and links is not None:
                # Writer probes link their compiler entry to a frozen helper.
                # Store only the link text; never read an external target or
                # create an actionable symlink when extracting the archive.
                links[str(child.relative_to(TEMP_ROOT))] = str(child.readlink())
                continue
            if stat.S_ISDIR(mode):
                continue
            if not stat.S_ISREG(mode):
                raise RuntimeError(f"unsupported evidence member: {child}")
            files.append(child)
    return sorted(files)


def archive_files(destination, files, expected=None):
    """Publish only a complete archive; keep a failed .partial for diagnosis."""
    partial = destination.with_suffix(destination.suffix + ".partial")
    records = {}
    with tarfile.open(partial, "x:gz") as archive:
        for name, path in sorted(files.items()):
            relative = PurePosixPath(name)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or str(relative) != name
            ):
                raise RuntimeError(f"unsafe archive member: {name}")
            data, mode = regular_bytes(path)
            actual = digest(data)
            if expected is not None and expected.get(name) != actual:
                raise RuntimeError(f"source changed before archive: {name}")
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), mode
            archive.addfile(info, io.BytesIO(data))
            records[name] = actual
    # This is a private, newly created run directory, never an existing archive.
    partial.rename(destination)
    return {"sha256": digest(destination.read_bytes()), "files": records}


def freeze_source(root, out, frozen):
    result = archive_files(
        out / "source.tar.gz", {name: root / name for name in frozen}, frozen
    )
    write_json(out / "source-archive.json", result)


def command_observation(command, env, cwd):
    """Bound read-only probes and retain failures instead of silently skipping."""
    record = {"command": command}
    try:
        # Relative PATH components belong to the probe's cwd, not to the
        # runner's caller (which may have invoked it from a different folder).
        search_path = os.pathsep.join(
            str((Path(cwd) / item).resolve())
            for item in env.get("PATH", os.defpath).split(os.pathsep)
        )
        # Follow only the explicitly selected tool's symlink to hash its binary;
        # this is not permission to follow links in workload evidence archives.
        path = shutil.which(command[0], path=search_path)
        if path is None:
            raise FileNotFoundError(f"tool not found: {command[0]}")
        resolved = Path(path).resolve(strict=True)
        data, _ = regular_bytes(resolved)
        record.update(path=path, resolved=str(resolved), sha256=digest(data))
        result = subprocess.run(
            # Execute the selected path, not its resolved target: Python venv
            # selection and some tool modes depend on the symlink/argv[0].
            [path, *command[1:]],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
            check=False,
        )
        record.update(
            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr
        )
        if result.returncode:
            record["error"] = f"probe exited {result.returncode}"
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        record["error"] = str(error)
    return record


def environment(out, env=None, cwd=None):
    """Observe a run's starting environment, not its loaded/JIT image identity."""
    env = dict(os.environ if env is None else env)
    env["LC_ALL"] = "C"
    cwd = Path.cwd() if cwd is None else cwd
    notes = Path("/sys/kernel/notes").read_bytes()
    (out / "kernel.notes").write_bytes(notes)
    uname = os.uname()
    settings, errors = {}, {}
    for name, path in (
        ("randomize_va_space", "/proc/sys/kernel/randomize_va_space"),
        ("numa_balancing", "/proc/sys/kernel/numa_balancing"),
        ("preempt", "/sys/kernel/debug/sched/preempt"),
    ):
        try:
            settings[name] = Path(path).read_text().strip()
        except OSError as error:
            errors[f"runtime_settings.{name}"] = str(error)
    record = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "stage": "before_cases",
        "cwd": str(cwd),
        "uname": {
            name: getattr(uname, name)
            for name in ("sysname", "nodename", "release", "version", "machine")
        },
        "kernel_notes_sha256": digest(notes),
        "cmdline": Path("/proc/cmdline").read_text().strip(),
        "online_cpus": Path("/sys/devices/system/cpu/online").read_text().strip(),
        "numa_cpus": {
            path.parent.name: path.read_text().strip()
            for path in sorted(Path("/sys/devices/system/node").glob("node*/cpulist"))
        },
        "runtime_settings": settings,
        "build_environment": {name: env.get(name) for name in BUILD_ENVIRONMENT},
        "runner_python": {"executable": sys.executable, "version": sys.version},
        "tools": {
            name: command_observation([name, "--version"], env, cwd) for name in TOOLS
        },
    }
    # daemon uses execlp("python3"), which may differ from the runner's Python.
    # Query installed metadata with that interpreter, without importing JIT or
    # accessing its device. Metadata is not a hash of every imported module.
    probes = record["tools"]
    probes["python3"] = command_observation(
        ["python3", "-c", PYTHON_METADATA], env, cwd
    )
    probes["findmnt"] = command_observation(
        ["findmnt", "-J", "-T", str(cwd), "-o", "TARGET,SOURCE,FSTYPE,OPTIONS"],
        env,
        cwd,
    )
    for name, key in (("python3", "python"), ("findmnt", "mount")):
        if "error" not in probes[name]:
            try:
                record[key] = json.loads(probes[name]["stdout"])
            except ValueError as error:
                probes[name]["error"] = f"invalid JSON: {error}"
    errors.update(
        {name: probe["error"] for name, probe in probes.items() if "error" in probe}
    )
    record["errors"] = errors
    write_json(out / "environment.json", record)
    if errors:
        raise RuntimeError(f"environment capture failed: {', '.join(errors)}")


def declared_paths(log, out):
    directories, files = set(), set()
    for match in DECLARATION.finditer(log):
        path = Path(match["path"])
        # Test scripts use mktemp under /tmp/kdlock-*. Reject traversal, arbitrary
        # files and the runner's own directory (which would recursively archive).
        try:
            relative = path.relative_to(TEMP_ROOT)
        except ValueError as error:
            raise RuntimeError(f"evidence outside temporary root: {path}") from error
        if (
            not relative.parts
            or not relative.parts[0].startswith("kdlock-")
            or ".." in path.parts
            or path.resolve() != path
            or path.is_relative_to(out)
            or out.is_relative_to(path)
        ):
            raise RuntimeError(f"invalid declared evidence: {path}")
        (files if match["file"] else directories).add(path)
    # A daemon log already inside a declared protocol tree must be stored once.
    directories = {
        path
        for path in directories
        if not any(
            path != other and path.is_relative_to(other) for other in directories
        )
    }
    files = {
        path for path in files if not any(path.is_relative_to(d) for d in directories)
    }
    return sorted(directories), sorted(files)


def collect_case(root, run, case):
    """Called only after idle confirmation, including for a failed test."""
    directories, declared_files = declared_paths((case / "output.log").read_text(), run)
    links = {}
    protocol = {
        str(path.relative_to(TEMP_ROOT)): path
        for directory in directories
        for path in tree_files(directory, links)
    }
    protocol.update({str(path.relative_to(TEMP_ROOT)): path for path in declared_files})
    artifacts = {
        str(path.relative_to(root)): path
        for directory in sorted((root / "daemon").glob("0x*"))
        for path in tree_files(directory)
    }
    # These are post-case build outputs. A selftest may have restored a default
    # build, so never describe their hashes as the identities of loaded images.
    binaries = {
        name: root / name
        for name in (
            "kernel_module/kdlock_km.ko",
            "workload_modules/lock_scenarios/klock_module.ko",
            "workload_modules/lock_scenarios/kd_depth_source.ko",
            "daemon/daemon",
            "bench/klock_test",
        )
        if (root / name).exists() or (root / name).is_symlink()
    }
    result = {
        "directories": list(map(str, directories)),
        "files": list(map(str, declared_files)),
        "symlinks": links,
        "archives": {},
    }
    for name, files in (
        ("artifacts", artifacts),
        ("protocol", protocol),
        ("post-case-builds", binaries),
    ):
        result["archives"][name] = archive_files(case / f"{name}.tar.gz", files)
    # Joining callers is the first condition; stable membership also catches a
    # later writer or a disappearing declaration, without accepting partial logs.
    current_links = {}
    current = {
        str(path.relative_to(TEMP_ROOT)): path
        for directory in directories
        for path in tree_files(directory, current_links)
    }
    current.update({str(path.relative_to(TEMP_ROOT)): path for path in declared_files})
    if current != protocol or current_links != links:
        raise RuntimeError("protocol files changed during capture")
    for name, files in (
        ("artifacts", artifacts),
        ("protocol", protocol),
        ("post-case-builds", binaries),
    ):
        for member, path in files.items():
            data, _ = regular_bytes(path)
            if digest(data) != result["archives"][name]["files"][member]:
                raise RuntimeError(f"evidence changed after capture: {path}")
    write_json(case / "evidence.json", result)
    return result
