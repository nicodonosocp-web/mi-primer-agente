"""Pruebas offline: funciones reales aisladas de imports y cuentas ausentes.

No sustituyen las pruebas HTTP, SQLite ni WebRTC de la aplicación completa.
"""
import ast
import asyncio
import hashlib
import io
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from file_safety import ruta_archivo_segura

ROOT = Path(__file__).resolve().parents[1]
EXT = {'.txt', '.pdf', '.docx'}


def funcion_real(archivo, nombre, entorno):
    """Compila el cuerpo original, sin inicializadores OAuth/BD ni decoradores."""
    tree = ast.parse((ROOT / archivo).read_text())
    node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == nombre)
    node.decorator_list = []
    for arg in node.args.args + node.args.kwonlyargs:
        arg.annotation = None
    node.returns = None
    module = ast.Module(body=[node], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), archivo, 'exec'), entorno)
    return entorno[nombre]


def response(**kwargs):
    return SimpleNamespace(**kwargs)


class RutasTest(unittest.TestCase):
    def test_nombres_legitimos(self):
        with tempfile.TemporaryDirectory() as d:
            for nombre in ['Informe 2026.PDF', 'Acta ñ (2).docx', 'datos.txt']:
                self.assertEqual(ruta_archivo_segura(d, nombre, EXT), Path(d).resolve()/nombre)

    def test_escapes_windows_linux_y_secretos(self):
        with tempfile.TemporaryDirectory() as d:
            for nombre in ['../.env', '..\\token.json', '/tmp/a.txt', 'C:\\a.txt',
                           'C:a.txt', '\\\\server\\a.txt', 'a.txt:secreto', 'NUL.txt',
                           'COM1.pdf', 'LPT¹.txt', 'CON .txt', 'a.txt.', '', '.', '..',
                           'a\x00.txt', 'a\n.txt', ' a.txt', 'credentials.json', '.env']:
                with self.subTest(nombre=repr(nombre)), self.assertRaises(ValueError):
                    ruta_archivo_segura(d, nombre, EXT)

    def test_enlace_rechazado(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as e:
            target = Path(e)/'externo.txt'
            target.write_text('sintético')
            try:
                (Path(d)/'enlace.txt').symlink_to(target)
            except OSError:
                self.skipTest('Sistema sin privilegios para symlinks')
            with self.assertRaises(ValueError):
                ruta_archivo_segura(d, 'enlace.txt', EXT)
            self.assertEqual(target.read_text(), 'sintético')

    def test_gitignore(self):
        names = ['.env', '.env.local', 'credentials.json', 'token.json',
                 'calendar_token.json', 'memoria.db', 'memoria.db-wal',
                 'memoria.db-shm', 'indice.json', 'indice.tmp', 'indice_123.json.tmp']
        result = subprocess.run(['git', 'check-ignore', '--no-index', '--stdin'],
                                cwd=ROOT, input='\n'.join(names)+'\n', text=True,
                                capture_output=True, check=True)
        self.assertEqual(set(result.stdout.splitlines()), set(names))



if __name__ == '__main__': unittest.main()
