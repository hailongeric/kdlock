"""Apply the real benchmark overlay and exercise its production completion paths.

Run only in the VM, like the entry-scope fixture. The native helper/wrapper
primitives are doubles; this checks accounting decisions, not live execution.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source
from test_jit_entry_scope import main as run_entry_fixture


def main():
    patch = ROOT / "bench/spin_cacheline/provider/observation.patch"
    with tempfile.TemporaryDirectory(prefix="kdlock-bench-overlay-") as tmp:
        directory = Path(tmp)
        # Copy the actual patch inputs plus private dispatcher components. No
        # source tree is edited, and patch drift must fail before compilation.
        inputs = set(re.findall(r"^--- a/(.+)$", patch.read_text(), re.MULTILINE))
        inputs.update(str(path.relative_to(ROOT))
                      for path in (ROOT / "kernel_module/execution").glob("*.inc"))
        for relative in sorted(inputs):
            destination = directory / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        subprocess.run(
            ["patch", "--batch", "--fuzz=0", "-p1", "-i", str(patch)],
            cwd=directory, check=True, timeout=10,
        )
        executor = read_source(directory / "kernel_module/exe.c")
        run_entry_fixture(executor=executor, benchmark=True)


if __name__ == "__main__":
    main()
