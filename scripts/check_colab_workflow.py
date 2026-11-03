"""Offline checks of benchmark orchestration, never a real benchmark."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('runner', ROOT/'scripts/colab_benchmark.py')
runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)

class ColabWorkflow(unittest.TestCase):
    def test_plan_has_no_execution(self):
        with patch.object(runner.sys,'argv',['runner','--workdir','/content/example']), patch.object(runner,'require_colab_cpu') as guard, patch.object(runner,'monitored') as run:
            self.assertEqual(runner.main(),0)
            guard.assert_not_called(); run.assert_not_called()

    def test_m2_seed_omits_outputs_without_touching_input(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.cache') as temp:
            root=Path(temp); source=root/'original'; source.mkdir()
            (source/'discovery.json').write_text('{}'); (source/'download_status.json').write_text('{}')
            paper=source/'paper'; paper.mkdir(); (paper/'parsed.json').write_text('original')
            (paper/'main.tex').write_text('source'); (source/'parse_status.json').write_text('original')
            runner.seed_m2(source,root/'isolated')
            self.assertFalse((root/'isolated/paper/parsed.json').exists())
            self.assertFalse((root/'isolated/parse_status.json').exists())
            self.assertEqual((paper/'parsed.json').read_text(),'original')
            self.assertEqual((root/'isolated/paper/main.tex').read_text(),'source')

    def test_cpu_guard_rejects_non_colab(self):
        with patch.object(runner.platform,'system',return_value='Windows'):
            with self.assertRaises(RuntimeError):runner.require_colab_cpu()

    def test_monitor_retains_failure_artifacts(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.cache') as temp, patch.object(runner.subprocess,'run',return_value=subprocess.CompletedProcess(['fixture'],2)):
            root=Path(temp)
            self.assertEqual(runner.monitored(['fixture'],root,'test'),2)
            self.assertTrue((root/'test-disk-samples.json').exists())
            self.assertIn('"returncode": 2',(root/'test-runner.json').read_text())

if __name__=='__main__':
    (ROOT/'.cache').mkdir(exist_ok=True)
    unittest.main(verbosity=2)
