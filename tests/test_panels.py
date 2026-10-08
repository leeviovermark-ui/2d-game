"""Exercise asynchronous gameplay panels in the real Godot control tree."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PanelUITests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('godot'), 'Godot is required for real panel checks')
    def test_refresh_drafts_and_account_isolation(self):
        with tempfile.TemporaryDirectory(prefix='worldforge-panels-') as userdata:
            result = subprocess.run(
                [shutil.which('godot'), '--headless', '--path', str(ROOT),
                 '--script', 'res://tests/panels_runner.gd'],
                capture_output=True, text=True, timeout=30, cwd=ROOT,
                env={**os.environ, 'XDG_DATA_HOME': userdata,
                     'XDG_CONFIG_HOME': userdata, 'XDG_CACHE_HOME': userdata})
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertNotIn('SCRIPT ERROR', output)
        self.assertNotIn('\nERROR:', output)
        payload = next(json.loads(line) for line in result.stdout.splitlines()
                       if line.startswith('{') and '"panel_checks"' in line)
        self.assertGreaterEqual(payload['panel_checks'], 26)
        self.assertEqual(payload['status'], 'passed')
