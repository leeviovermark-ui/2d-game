"""Exercise real account controls, server selection, and connection indicators."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MenuUITests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('godot'), 'Godot is required for real client UI checks')
    def test_forms_and_loading_use_real_controls(self):
        with tempfile.TemporaryDirectory(prefix='worldforge-menu-') as userdata:
            result = subprocess.run(
                [shutil.which('godot'), '--headless', '--path', str(ROOT),
                 '--script', 'res://tests/menu_runner.gd'],
                capture_output=True, text=True, timeout=30, cwd=ROOT,
                env={**os.environ, 'XDG_DATA_HOME': userdata,
                     'XDG_CONFIG_HOME': userdata, 'XDG_CACHE_HOME': userdata})
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertNotIn('SCRIPT ERROR', output)
        self.assertNotIn('\nERROR:', output)
        payload = next(json.loads(line) for line in result.stdout.splitlines()
                       if line.startswith('{') and '"menu_checks"' in line)
        self.assertGreaterEqual(payload['menu_checks'], 110)
        self.assertEqual(payload['failures'], [])
