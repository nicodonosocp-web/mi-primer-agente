"""Arranca la app completa en una copia descartable, nunca sobre datos reales."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RuntimeAisladoTest(unittest.TestCase):
    def test_aplicacion_completa(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / 'app'
            data = root / 'data'
            cwd = root / 'otro-directorio'
            for p in [app, data, cwd]: p.mkdir()
            for p in ROOT.glob('*.py'): shutil.copy2(p, app / p.name)
            shutil.copy2(ROOT / 'realtime.html', app / 'realtime.html')
            (app / '.env').write_text('OPENAI_API_KEY=test-not-a-real-key\n')
            env = dict(os.environ, PYTHONPATH=str(app), MI_AGENTE_DATA_DIR=str(data))
            env.pop('OPENAI_API_KEY', None)
            env.pop('PYTHON_DOTENV_DISABLED', None)
            result = subprocess.run(
                [sys.executable, str(ROOT / 'tests' / 'runtime_cases.py')],
                cwd=cwd, env=env, text=True, capture_output=True, timeout=90,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stderr.strip())
            self.assertFalse((cwd / 'memoria.db').exists())
            self.assertFalse((app / 'memoria.db').exists())
            self.assertTrue((data / 'memoria.db').is_file())
