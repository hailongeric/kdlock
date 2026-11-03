"""Compile the production syscall-observer argument decoder in the VM."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

from source_text import ROOT
from test_spin_shadow import definition


class MmapSyscallArguments(unittest.TestCase):
    def test_wrapper_pointer_six_arguments_and_fd_representation(self):
        module = (ROOT / 'tests/kernel/mmap1_identity/payload/module.c').read_text()
        decoder = definition(module, 'static bool mmap1_arguments(const struct pt_regs *entry)')
        program = r'''
#include <stdbool.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
#define PROT_READ 1
#define PROT_WRITE 2
#define MAP_PRIVATE 2
#define MAP_ANONYMOUS 32
struct pt_regs { unsigned long di, si, dx, cx, r8, r9, r10; };
''' + decoder + r'''
#define CHECK(test) do { if (!(test)) { \
 fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #test); return 1; } } while (0)
int main(void)
{
 struct pt_regs args = {.si=128UL*1024*1024, .dx=3, .r8=ULONG_MAX, .r10=34};
 struct pt_regs entry = {.di=(unsigned long)&args};
 struct pt_regs before = args;
 CHECK(mmap1_arguments(&entry));
 CHECK(!memcmp(&args, &before, sizeof(args)));
 args.r8=0xffffffffUL;
 CHECK(mmap1_arguments(&entry));
 before=args;
 for (unsigned int field=0; field<7; field++) {
  args=before;
  switch (field) {
  case 0:args.di=4096;break;
  case 1:args.si--;break;
  case 2:args.dx=1;break;
  case 3:args.r10=2;break;
  case 4:args.r8=0xfffffffeUL;break;
  case 5:args.r9=4096;break;
  case 6:args.r8=0xffffffff00000000UL;break;
  }
  CHECK(!mmap1_arguments(&entry));
 }
 /* These values fit vm_mmap_pgoff's former C-argument layout, not the
  * userspace syscall layout. They must not be recorded as this invocation. */
 args=(struct pt_regs){.dx=128UL*1024*1024,.cx=3,.r8=34};
 CHECK(!mmap1_arguments(&entry));
 entry.di=0;
 CHECK(!mmap1_arguments(&entry));
 puts("mmap syscall observer argument cases passed");
 return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='kdlock-mmap-syscall-args-') as name:
            directory = Path(name)
            source, binary = directory / 'arguments.c', directory / 'arguments'
            source.write_text(program)
            command = shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary)]
            built = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('argument cases passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
