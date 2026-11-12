# Source-only provider build draft at 0798c1ab

This leaf has not been staged or executed. Root peer review and an actual fresh
three-image recovery receipt are required before operator staging. The argv
file is a template; its recovery digest is intentionally unresolved.

The controller derives from f560a221 and retains its 16 linked-output pins,
78 core-source hashes, protected source/output/boot checks, ten original module
artifacts and client. It additionally pins the previous provider build receipt
21d6d90b and its distinct signed and unsigned outputs before and after the run.
The fresh output and signed copy have exclusive new paths and separate inodes.
Only one external Kbuild directory is used. Its Kbuild declares only
kd_mmap_api_provider.ko; exactly one resulting *.ko is required. The proven make
`modules` entry is retained for that one provider. No kernel/client/other-module
build, check suite, load or runtime command is present.

The nine commands are the prior seven build/sign/modinfo commands plus two GNU
objdump invocations bound to SHA-256 44f07f8d. Each disassembles only jit_ioctl
from one exact unsigned module, uses a 60-second deadline and a 262144-byte log
bound. The parser preserves raw instructions and reports the first fixed entry
RSP reservation plus preceding callee-save pushes. Unresolved/dynamic prologue
shapes fail and retain their evidence. A strictly smaller new reservation is
required. This does not infer complete call-chain stack use. All compiler
warnings remain recorded independently.

Both source transports contain the same 143 regular members. Against 5c14,
only RWSEM.md, the killable README and mmap_jit_profile.inc changed. Against the
previous de76 provider source, the killable runner also changed. Of the exact
provider build inputs, only mmap_jit_profile.inc differs; the ABI, provider.c,
Kbuild and shared context-boundary include are unchanged.

No AST parse, project import, build, test or VM command ran during preparation.
The frozen source export remains separate and is copied byte-identically here.
The controller and recipe diffs retain every proposed change from their exact
closed parents. plan.json records prospective guest paths and current hashes.
