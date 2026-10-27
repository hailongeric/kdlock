# Pinned Miasm on Python 3.14

The Ubuntu 26.04 interpreter is Python 3.14.4. The existing `miasm==0.1.5`
package imports its decoder but fails when constructing the x86 semantic lifter:
`core/sembuilder.py` still references `ast.Str` and `ast.Num`. Python 3.14
[removed those deprecated AST classes](https://docs.python.org/3.14/whatsnew/3.14.html#removed).
The upstream project also addressed this in
[PR 1519](https://github.com/cea-sec/miasm/pull/1519); the installed 0.1.5 package
does not contain that change.

[The local patch](miasm-0.1.5-python314.patch) changes only four sites in the
semantic builder. Integer nodes become `ast.Constant`; former string-node
checks require both `ast.Constant` and a `str` value. Numeric, bytes and other
constants do not become string operations or accepted docstrings. Decoding,
semantic lifting, instruction admission and generated-code checks remain active.

After installing [the pinned dependencies](../requirements.txt), apply in an
idle guest using the designated isolated environment:

```sh
/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3 \
  disassem/miasm_python314.py --apply --receipt /absolute/new/patch-receipt.json
/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3 \
  disassem/miasm_python314.py
```

The helper requires the exact original dependency hash or the already patched
hash, verifies that its four substitutions equal the maintained patch, and
preserves original bytes beside the first receipt. It refuses other virtual
environments and unexpected source bytes. Reapplying produces an idempotent
receipt without changing the dependency. It does not modify Python's standard
library or dependency package metadata.

| Identity | SHA256 |
| --- | --- |
| Original `sembuilder.py` | `fc3baced219615c2227a5a5cd50ee3a62b2f1c990aa366bbedd709ae22801fd6` |
| Patched `sembuilder.py` | `cc4e07d6820a8fe461df71ac47bad434d918c68d3c0473508ebe78657e45fcc6` |
| Versioned patch | `b2e64a61950fbf22b9d1acc6fd1f0f8d80efa08c468d04e7cccd340ac09be820` |

On Python 3.14, translator startup verifies the installed file and patch hashes
before semantic analysis and records the dependency identity in its CLI log.
Missing or changed patch bytes raise an environment error; they are never
converted into a native-only admission result. The unchanged package version
alone is insufficient evidence. Earlier Python environments keep their existing
behavior. This narrowly scoped patch does not claim compatibility for every
Miasm feature or future Python release.
