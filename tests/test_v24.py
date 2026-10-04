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


class IntegracionAisladaTest(unittest.TestCase):
    def reindex_env(self, d, info=None):
        return dict(UPLOAD_DIR=Path(d), EXTENSIONES_PERMITIDAS=EXT,
                    ruta_archivo_segura=ruta_archivo_segura, JSONResponse=response,
                    cargar_indice=Mock(return_value=[{'archivo':'original.txt'}]),
                    obtener_info_documento=Mock(return_value=info),
                    guardar_indice=Mock(), eliminar_documento_indice=Mock(),
                    indexar_archivo_drive=Mock(return_value={'ok':True}),
                    indexar_documento_local=Mock(return_value={'fragmentos_agregados':1}),
                    calcular_sha256=lambda b: hashlib.sha256(b).hexdigest())

    def test_reindex_escape_sin_lectura_externa_ni_escritura(self):
        with tempfile.TemporaryDirectory() as d:
            env = self.reindex_env(d)
            fn = funcion_real('realtime_server.py', 'reindexar_documento_rag', env)
            for nombre in ['../secreto.txt', 'C:\\secreto.txt', '.env', 'token.json']:
                self.assertEqual(fn(SimpleNamespace(archivo=nombre)).status_code, 400)
            for name in ['guardar_indice', 'eliminar_documento_indice', 'indexar_documento_local']:
                env[name].assert_not_called()

    def test_reindex_local_y_drive_conservados(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'acta.txt'; path.write_text('acta sintética')
            env = self.reindex_env(d)
            fn = funcion_real('realtime_server.py', 'reindexar_documento_rag', env)
            self.assertTrue(fn(SimpleNamespace(archivo='acta.txt'))['ok'])
            env['indexar_documento_local'].assert_called_once_with(path, hashlib.sha256(path.read_bytes()).hexdigest())
            env = self.reindex_env(d, {'origen':'drive', 'drive_file_id':'fake-id'})
            fn = funcion_real('realtime_server.py', 'reindexar_documento_rag', env)
            self.assertTrue(fn(SimpleNamespace(archivo='Documento Google'))['ok'])
            env['indexar_archivo_drive'].assert_called_once_with('fake-id')

    def test_upload_rechaza_enlace_sin_sobrescribir(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as e:
            target = Path(e)/'externo.txt'; target.write_text('original')
            try:
                (Path(d)/'acta.txt').symlink_to(target)
            except OSError:
                self.skipTest('Sistema sin privilegios para symlinks')
            async def read(): return b'nuevo'
            env = dict(Path=Path, File=lambda *a:None, UPLOAD_DIR=Path(d),
                       EXTENSIONES_PERMITIDAS=EXT, MAX_ARCHIVO_BYTES=25*1024*1024,
                       limpiar_nombre_archivo=lambda s:s, calcular_sha256=lambda b:'hash',
                       cargar_indice=lambda:[], ruta_archivo_segura=ruta_archivo_segura,
                       JSONResponse=response, indexar_documento_local=Mock())
            fn = funcion_real('realtime_server.py', 'upload_rag', env)
            result = asyncio.run(fn(SimpleNamespace(filename='acta.txt', read=read)))
            self.assertFalse(result.content['ok'])
            self.assertEqual(target.read_text(), 'original')
            env['indexar_documento_local'].assert_not_called()

    def test_drive_descarga_rechaza_escape_antes_de_transferir(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ['../externo.txt', 'C:\\externo.txt']:
                downloader = Mock()
                env = dict(CARPETA_DESCARGAS=Path(d), io=io,
                           ruta_archivo_segura=ruta_archivo_segura,
                           obtener_servicio_drive=Mock(),
                           obtener_metadatos_drive=lambda _: {'mimeType':'text/plain','name':name},
                           MediaIoBaseDownload=downloader)
                fn = funcion_real('drive_tools.py', 'descargar_archivo_drive', env)
                with self.assertRaises(ValueError): fn('fake-id')
                downloader.assert_not_called()

    def test_drive_descarga_legitima(self):
        with tempfile.TemporaryDirectory() as d:
            class Downloader:
                def __init__(self, buffer, request): self.buffer = buffer
                def next_chunk(self):
                    self.buffer.write(b'sintetico')
                    return None, True
            env = dict(CARPETA_DESCARGAS=Path(d), io=io,
                       ruta_archivo_segura=ruta_archivo_segura,
                       obtener_servicio_drive=Mock(),
                       obtener_metadatos_drive=lambda _: {'mimeType':'text/plain','name':'acta.txt'},
                       MediaIoBaseDownload=Downloader)
            fn = funcion_real('drive_tools.py', 'descargar_archivo_drive', env)
            result = fn('fake-id')
            self.assertEqual(result, Path(d)/'acta.txt')
            self.assertEqual(result.read_bytes(), b'sintetico')

    def test_upload_legitimo_y_colision(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'acta.txt').write_text('anterior')
            async def read(): return b'nuevo'
            env = dict(Path=Path, File=lambda *a:None, UPLOAD_DIR=Path(d),
                       EXTENSIONES_PERMITIDAS=EXT, MAX_ARCHIVO_BYTES=25*1024*1024,
                       limpiar_nombre_archivo=lambda s:s, calcular_sha256=lambda b:'123456789',
                       cargar_indice=lambda:[], ruta_archivo_segura=ruta_archivo_segura,
                       JSONResponse=response,
                       indexar_documento_local=Mock(return_value={'archivo':'acta_12345678.txt'}))
            fn = funcion_real('realtime_server.py', 'upload_rag', env)
            result = asyncio.run(fn(SimpleNamespace(filename='acta.txt', read=read)))
            self.assertTrue(result['ok'])
            self.assertEqual((Path(d)/'acta.txt').read_text(), 'anterior')
            self.assertEqual((Path(d)/'acta_12345678.txt').read_bytes(), b'nuevo')

    def test_calendar_solo_booleano_true(self):
        env = dict(JSONResponse=response, crear_evento=Mock(return_value={'id':'fake'}))
        fn = funcion_real('realtime_server.py', 'ejecutar_tool', env)
        # Evitar que el logging legado copie argumentos al resultado de pruebas.
        env['print'] = lambda *a: None
        for value in [False, None, 'true', 1, {}]:
            result = fn(SimpleNamespace(name='crear_evento_calendar', arguments={
                'usuario_autorizo_creacion':value}))
            self.assertEqual(result.status_code, 403)
        env['crear_evento'].assert_not_called()
        result = fn(SimpleNamespace(name='crear_evento_calendar', arguments={
            'usuario_autorizo_creacion':True,'titulo':'Prueba sintética',
            'inicio_iso':'2026-10-05T10:00:00-03:00','fin_iso':'2026-10-05T11:00:00-03:00'}))
        self.assertTrue(result['ok'])
        env['crear_evento'].assert_called_once()

    def test_indice_legacy_roundtrip_y_ranking(self):
        import math
        import os
        import unicodedata
        import numpy as np
        from collections import Counter
        with tempfile.TemporaryDirectory() as d:
            env = dict(json=json, math=math, os=os, re=re, tempfile=tempfile,
                       unicodedata=unicodedata, Counter=Counter, np=np,
                       INDICE_PATH=Path(d)/'indice.json', STOPWORDS={'el','de'},
                       PESO_SEMANTICO=.78, PESO_LEXICO=.22, CANDIDATOS_INICIALES=30,
                       SIMILITUD_DUPLICADO=.82, crear_embedding=lambda _: [1.,0.])
            for n in ['normalizar_texto','tokenizar','cargar_indice','guardar_indice',
                      'similitud_coseno','puntuacion_lexica','calcular_bonificaciones',
                      'similitud_jaccard','diversificar_resultados','buscar_documentos_hibrido']:
                funcion_real('rag_mejorado.py',n,env)
            data = [{'archivo':'acta.txt','fragmento':1,'texto':'reunión logística', 'embedding':[1.,0.]},
                    {'archivo':'otro.txt','fragmento':1,'texto':'viaje vacaciones', 'embedding':[0.,1.]}]
            env['guardar_indice'](data)
            self.assertEqual(env['cargar_indice'](), data)
            result = env['buscar_documentos_hibrido']('reunión',archivo='acta.txt')
            self.assertEqual(len(result),1)
            self.assertEqual(result[0]['archivo'],'acta.txt')
            self.assertGreater(result[0]['score_lexico'],0)
            self.assertGreater(result[0]['score_semantico'],0)


if __name__ == '__main__':
    unittest.main()
