"""VM-only C checks of the production episode collection function excerpts.

External source/image/request operations are controlled stand-ins; these checks
do not replace a kernel build or live ownership and retirement validation.
See episode_collection/README.md for configuration and the validation handoff.
"""

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = (
    "finish_user", "frame_init", "kd_episode_resources_init", "put_image",
    "finish_image_actor", "start_grant_actor", "finish_grant_actor",
    "kd_episode_collect",
)


def function_excerpt(source, name):
    match = re.search(r"^(?:static )?(?:int|void) " + name + r"\(", source, re.M)
    if match is None:
        raise ValueError(f"missing production function {name}")
    end = source.index("\n}", match.start()) + 2
    return source[match.start():end] + "\n"


class EpisodeCollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config_path = os.environ.get("KDLOCK_COLLECTION_TEST_CONFIG")
        if not config_path:
            raise RuntimeError("KDLOCK_COLLECTION_TEST_CONFIG is required; VM execution only")
        config = json.loads(Path(config_path).read_text())
        if platform.release() != config["expected_release"]:
            raise RuntimeError("running kernel does not match the supplied VM release")
        parent, compiler = Path(config["scratch_parent"]), Path(config["compiler"])
        if not parent.is_absolute() or not parent.is_dir():
            raise ValueError("scratch_parent must be an existing absolute VM directory")
        if not compiler.is_absolute() or not compiler.is_file():
            raise ValueError("compiler must name an existing absolute executable")
        cls.output = Path(tempfile.mkdtemp(prefix="episode-collection-", dir=parent))
        source_path, header_path = ROOT / "kernel/episode.c", ROOT / "kernel/episode.h"
        source, header = source_path.read_text(), header_path.read_text()
        excerpts = "\n".join(function_excerpt(source, name) for name in FUNCTIONS)
        structs = []
        for name in ("kd_episode_resources", "kd_episode_frame"):
            match = re.search(r"^struct " + name + r" \{.*?^};", header, re.M | re.S)
            if match is None:
                raise ValueError(f"missing production struct {name}")
            structs.append(match.group())
        (cls.output / "episode_functions.h").write_text(excerpts)
        (cls.output / "episode_types.h").write_text("\n".join(structs) + "\n")
        fixture = ROOT / "tests/episode_collection/collection_check.c"
        (cls.output / "collection_check.c").write_bytes(fixture.read_bytes())
        cls.binary = cls.output / "collection_check"
        command = [str(compiler), "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                   "-fno-strict-aliasing", str(cls.output / "collection_check.c"),
                   "-o", str(cls.binary)]
        receipt = {"command": command, "release": platform.release(), "functions": FUNCTIONS,
                   "inputs": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in (source_path, header_path, fixture)}}
        (cls.output / "build.json").write_text(json.dumps(receipt, indent=2) + "\n")
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        (cls.output / "build.stdout").write_text(result.stdout)
        (cls.output / "build.stderr").write_text(result.stderr)
        receipt["returncode"] = result.returncode
        (cls.output / "build.json").write_text(json.dumps(receipt, indent=2) + "\n")
        if result.returncode:
            raise RuntimeError(f"focused C build failed; retained output: {cls.output}")

    def check_case(self, name):
        result = subprocess.run([str(self.binary), name], capture_output=True, text=True, timeout=10)
        (self.output / f"{name}.json").write_text(json.dumps({
            "command": [str(self.binary), name], "returncode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr,
        }, indent=2) + "\n")
        self.assertEqual(result.returncode, 0, f"{name}: {result.stderr}; output: {self.output}")
        self.assertEqual(result.stdout, f"PASS {name}\n")

    def test_current_source_is_required_even_for_empty_index(self):
        self.check_case("authority")

    def test_unstarted_and_linked_requests_remain_retained(self):
        self.check_case("pending")

    def test_slot_order_and_immediate_frame_reuse(self):
        self.check_case("order_reuse")

    def test_return_image_outlives_grant_collection(self):
        self.check_case("return_image")

    def test_source_put_failure_retains_collection_entry(self):
        self.check_case("source_failure")

    def test_image_finish_failure_retains_collection_entry(self):
        self.check_case("image_failure")

    def test_grant_finish_failure_restores_original_position(self):
        self.check_case("grant_failure")

    def test_final_finish_has_no_later_frame_access(self):
        self.check_case("final_access")
