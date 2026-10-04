"""Worker de integración; se ejecuta mediante test_runtime, en copia temporal."""
import io
import json
import os
import socket
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

# Denegar conexiones incluso ante un mock olvidado. TestClient no usa sockets.
network_guard = patch.object(socket.socket, 'connect', side_effect=AssertionError('Red prohibida en pruebas'))
network_guard.start()

import fitz
from docx import Document
from fastapi.testclient import TestClient
import configuracion
import memoria
import memoria_largo_plazo as mlp
import rag_drive
import rag_mejorado as rag
import drive_tools
import calendar_tools
import realtime_server as server

DATA = configuracion.DATA_DIR


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(server.app)

    def setUp(self):
        server.guardar_indice([])

    def test_01_arranque_env_y_rutas(self):
        self.assertEqual(os.environ['OPENAI_API_KEY'], 'test-not-a-real-key')
        self.assertEqual(memoria.ARCHIVO_DB, DATA / 'memoria.db')
        self.assertEqual(mlp.ARCHIVO_DB, memoria.ARCHIVO_DB)
        self.assertEqual(rag.INDICE_PATH, server.INDICE_PATH)
        self.assertEqual(rag_drive.ARCHIVO_INDICE, server.INDICE_PATH)
        self.assertEqual(drive_tools.TOKEN_FILE.parent, DATA)
        self.assertEqual(calendar_tools.TOKEN_PATH.parent, DATA)
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('RTCPeerConnection', r.text)

    def test_02_historial_sqlite_y_reinicio(self):
        cid = self.client.post('/conversation/start').json()['conversacion_id']
        r = self.client.post('/conversation/message', json={
            'conversacion_id':cid, 'role':'user', 'content':'Mensaje persistente sintético'})
        self.assertEqual(r.status_code, 200)
        detail = self.client.get(f'/conversation/{cid}').json()
        self.assertEqual(detail['mensajes'][0]['content'], 'Mensaje persistente sintético')
        self.assertTrue(detail['conversacion']['fecha_creacion'])
        self.assertTrue(detail['conversacion']['fecha_actualizacion'])
        self.assertTrue(self.client.get('/conversations').json()['result'])
        result = subprocess.run([sys.executable, '-c',
            'import memoria; memoria.inicializar_db(); '
            f'assert memoria.contar_mensajes({cid}) == 1'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        r = self.client.post('/conversation/message', json={
            'conversacion_id':cid, 'role':'system', 'content':'no permitido'})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(memoria.contar_mensajes(cid),1)

    def test_03_memoria_duradera_y_esquema_original(self):
        r = self.client.post('/tool',json={'name':'recordar','arguments':{
            'categoria':'prueba','clave':'preferencia','contenido':'Contenido sintético'}})
        self.assertTrue(r.json()['ok'])
        first = r.json()['result']['id']
        updated = mlp.guardar_memoria('prueba','PREFERENCIA','Contenido actualizado')
        self.assertEqual(updated['id'], first)
        r = self.client.post('/tool',json={'name':'buscar_memoria','arguments':{'consulta':'actualizado'}})
        self.assertEqual(r.json()['result'][0]['id'],first)
        mlp.inicializar_memoria_largo_plazo()
        self.assertEqual(mlp.obtener_memoria(first)['contenido'], 'Contenido actualizado')
        with sqlite3.connect(memoria.ARCHIVO_DB) as db:
            cols = [x[1] for x in db.execute('PRAGMA table_info(conversaciones)')]
            self.assertEqual(cols,['id','titulo','creado_en','actualizado_en'])
            cols = [x[1] for x in db.execute('PRAGMA table_info(memoria_largo_plazo)')]
            self.assertEqual(cols,['id','categoria','clave','contenido','fuente_conversacion_id',
                                  'importancia','activa','creado_en','actualizado_en'])

    def test_04_upload_txt_docx_pdf(self):
        buf = io.BytesIO(); doc = Document();doc.add_paragraph('Acta sintética DOCX');doc.save(buf)
        pdf = fitz.open();page=pdf.new_page();page.insert_text((50,50),'Acta PDF sintetica')
        contents = [('texto.txt',b'Acta texto sintetica','text/plain'),
                    ('texto.docx',buf.getvalue(),'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
                    ('texto.pdf',pdf.tobytes(),'application/pdf')]
        pdf.close()
        with patch.object(server,'crear_embeddings_lote',side_effect=lambda fragments:[[1.,0.] for _ in fragments]):
            for name, content, mime in contents:
                with self.subTest(name=name):
                    r=self.client.post('/upload-rag',files={'file':(name,content,mime)})
                    self.assertEqual(r.status_code,200,r.text)
                    self.assertGreater(r.json()['fragmentos_agregados'],0)
        library=self.client.get('/library').json()['documentos']
        self.assertTrue(all(any(x['archivo']==name and x['indexado'] for x in library) for name,_,_ in contents))
        with patch.object(rag,'crear_embedding',return_value=[1.,0.]):
            r=self.client.post('/rag/search',json={'consulta':'acta','archivo':'texto.txt'})
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['result'][0]['archivo'],'texto.txt')
        self.assertTrue(self.client.post('/rag/preview',json={'archivo':'texto.txt'}).json()['ok'])

    def test_05_ocr_pdf_escaneado(self):
        pdf=fitz.open();page=pdf.new_page();page.draw_rect(fitz.Rect(10,10,100,100))
        data=pdf.tobytes();pdf.close()
        with patch.object(server,'ocr_imagen_openai',return_value='Transcripción sintética') as ocr, \
             patch.object(server,'crear_embeddings_lote',side_effect=lambda xs:[[1.,0.] for _ in xs]):
            r=self.client.post('/upload-rag',files={'file':('escaneado.pdf',data,'application/pdf')})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(ocr.call_count,1)
        self.assertTrue(ocr.call_args.args[0].startswith('data:image/png;base64,'))

    def test_06_drive_origen_legacy_y_reindex(self):
        legacy=[{'archivo':'remoto.txt','fragmento':1,'texto':'Anterior','embedding':[1.,0.],
                 'origen':'google_drive','drive_file_id':'synthetic-id'}]
        server.guardar_indice(legacy)
        library=self.client.get('/library').json()['documentos']
        item=next(x for x in library if x['archivo']=='remoto.txt')
        self.assertEqual(item['origen'],'drive')
        self.assertEqual(item['drive_file_id'],'synthetic-id')
        remote=DATA/'remoto.txt';remote.write_text('Nuevo contenido sintético')
        with patch.object(rag_drive,'descargar_archivo_drive',return_value=remote), \
             patch.object(rag_drive,'crear_embedding',return_value=[1.,0.]):
            r=self.client.post('/rag/reindex',json={'archivo':'remoto.txt'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(server.cargar_indice()[0]['drive_file_id'],'synthetic-id')
        self.assertEqual(server.cargar_indice()[0]['texto'],'Nuevo contenido sintético')
        self.assertEqual(drive_tools.SCOPES,['https://www.googleapis.com/auth/drive.readonly'])

    def test_07_drive_fallo_no_es_exito(self):
        old=[{'archivo':'fallo.txt','fragmento':1,'texto':'Conservar','embedding':[1.,0.],
              'origen':'google_drive','drive_file_id':'fail-id'}]
        server.guardar_indice(old)
        with patch.object(rag_drive,'descargar_archivo_drive',side_effect=OSError('sintético')):
            r=self.client.post('/rag/reindex',json={'archivo':'fallo.txt'})
        self.assertEqual(r.status_code,500,r.text)
        self.assertEqual(server.cargar_indice(),old)

    def test_08_calendar_denegacion_y_mock(self):
        with patch.object(server,'crear_evento',return_value={'id':'synthetic-event'}) as create:
            r=self.client.post('/tool',json={'name':'crear_evento_calendar','arguments':{}})
            self.assertEqual(r.status_code,403);create.assert_not_called()
            r=self.client.post('/tool',json={'name':'crear_evento_calendar','arguments':{
                'usuario_autorizo_creacion':True,'titulo':'Sintético',
                'inicio_iso':'2026-10-06T10:00:00-03:00','fin_iso':'2026-10-06T11:00:00-03:00'}})
            self.assertEqual(r.status_code,200);create.assert_called_once()
        with patch.object(server,'listar_eventos',return_value=[{'id':'mock'}]):
            self.assertEqual(self.client.get('/calendar/events').json()['result'][0]['id'],'mock')

    def test_09_token_contrato_sin_red(self):
        with patch.object(server.requests,'post',return_value=SimpleNamespace(ok=True,json=lambda:{'value':'fake-ephemeral'})) as post:
            r=self.client.get('/token')
        self.assertEqual(r.json()['value'],'fake-ephemeral')
        self.assertEqual(post.call_args.kwargs['json']['session']['type'],'realtime')

    def test_11_cli_arranque_sin_llamadas(self):
        # El CLI sale antes de Runner; indexar no tiene documentos que procesar.
        for name, stdin in [('agente.py', 'salir\n'), ('indexar.py', '')]:
            with self.subTest(name=name):
                code = (
                    "import runpy,socket; "
                    "socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError('sin red')); "
                    f"runpy.run_path({str(configuracion.BASE_DIR)!r} + '/{name}',run_name='__main__')"
                )
                result = subprocess.run([sys.executable, '-c', code],input=stdin,
                                        capture_output=True,text=True,timeout=20)
                self.assertEqual(result.returncode,0,result.stderr)

    def test_10_reindex_escape_http(self):
        before=server.INDICE_PATH.read_bytes()
        r=self.client.post('/rag/reindex',json={'archivo':'../.env'})
        self.assertEqual(r.status_code,400)
        self.assertEqual(server.INDICE_PATH.read_bytes(),before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
