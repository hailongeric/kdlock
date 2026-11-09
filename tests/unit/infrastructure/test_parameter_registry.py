"""VM-only parameter snapshots retain a complete current Native API table."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
from source_text import ROOT
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as runtime

class ParameterRegistry(unittest.TestCase):
    def test_old_and_paged_provider_snapshots(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            row = '1 ffffffff81000100 1 1 2 api_one\n'
            (directory/'service_call_table').write_text(row)
            (directory/'bench_quiet').write_text('1\n')
            with patch.object(runtime, 'Path', return_value=directory):
                self.assertEqual(runtime.parameters()['service_call_table'], row.strip())
            (directory/'service_call_table_state').write_text('1 1 1\n')
            (directory/'service_call_table').write_text('old table is not the current snapshot')
            for page in range(8):
                (directory/f'service_call_page_{page}').write_text(row if page==0 else '')
            with patch.object(runtime, 'Path', return_value=directory):
                result = runtime.parameters()
                self.assertEqual(result['service_call_table'], row.strip())
                self.assertEqual(result['bench_quiet'], '1')
            (directory/'service_call_page_7').unlink()
            with patch.object(runtime, 'Path', return_value=directory):
                with self.assertRaises(FileNotFoundError): runtime.parameters()

if __name__ == '__main__': unittest.main()
