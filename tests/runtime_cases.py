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
import documentos
import almacenamiento
from concurrent.futures import ThreadPoolExecutor

DATA = configuracion.DATA_DIR


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(server.app, base_url="http://localhost")
        csrf = cls.client.get("/session").json()["csrf"]
        cls.client.headers["X-Grifo-CSRF"] = csrf

    def setUp(self):
        server.guardar_indice([])

    def test_drive_carpetas_desde_chat(self):
        servicio = Mock()
        servicio.files.return_value.list.return_value.execute.return_value = {
            'files': [{'id': 'folder-test', 'name': 'MBA'}], 'nextPageToken': 'next-test'}
        with patch.object(server, 'obtener_servicio_drive', return_value=servicio):
            for nombre, argumentos in [
                ('listar_carpetas_drive', {'nombre': 'MBA'}),
                ('listar_contenido_carpeta_drive', {'carpeta_id': 'folder-test'}),
            ]:
                respuesta = self.client.post('/tool', json={'name': nombre, 'arguments': argumentos})
                self.assertEqual(respuesta.status_code, 200, respuesta.text)
                self.assertEqual(respuesta.json()['result']['siguiente_pagina'], 'next-test')
            respuesta = self.client.post('/tool', json={
                'name': 'listar_contenido_carpeta_drive', 'arguments': {}})
            self.assertEqual(respuesta.status_code, 400)

    def test_drive_indexacion_no_autorizable_por_modelo(self):
        with patch.object(server, 'indexar_archivo_drive') as indexar:
            respuesta = self.client.post('/tool', json={'name': 'indexar_drive', 'arguments': {
                'file_id': 'synthetic-id', 'usuario_autorizo_indexacion': True}})
            self.assertEqual(respuesta.status_code, 403)
            indexar.assert_not_called()
        with patch.object(server, 'obtener_archivo_drive_backend', return_value={
            'name': 'Sintetico.pdf', 'mimeType': 'application/pdf'}), patch.object(
                server, 'indexar_archivo_drive', return_value='Indexado') as indexar:
            propuesta = self.client.post('/drive/proposals', json={'file_id': 'synthetic-id'})
            self.assertEqual(propuesta.status_code, 200)
            resultado = self.client.post('/drive/confirm', json={
                'propuesta_id': propuesta.json()['propuesta_id'], 'confirmar': True})
            self.assertEqual(resultado.status_code, 200)
            indexar.assert_called_once_with('synthetic-id')

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
        with patch.object(documentos,'ocr_imagen_openai',return_value='Transcripción sintética') as ocr, \
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

    def test_08_calendar_confirmacion_sesion_repeticion(self):
        data = {'titulo':'Sintético','inicio_iso':'2026-10-06T10:00:00-03:00','fin_iso':'2026-10-06T11:00:00-03:00'}
        with patch.object(server,'crear_evento',return_value={'id':'synthetic-event'}) as create:
            r=self.client.post('/tool',json={'name':'crear_evento_calendar','arguments':dict(data,usuario_autorizo_creacion=True)})
            self.assertEqual(r.status_code,403);create.assert_not_called()
            proposal=self.client.post('/calendar/proposals',json=data).json()
            body={'propuesta_id':proposal['propuesta_id'],'confirmar':True}
            stranger=TestClient(server.app,base_url='http://localhost')
            token=stranger.get('/session').json()['csrf'];stranger.headers['X-Grifo-CSRF']=token
            self.assertEqual(stranger.post('/calendar/confirm',json=body).status_code,404)
            create.assert_not_called()
            for _ in range(2):
                self.assertTrue(self.client.post('/calendar/confirm',json=body).json()['ok'])
            create.assert_called_once()
            proposal=self.client.post('/calendar/proposals',json=data).json()
            body={'propuesta_id':proposal['propuesta_id'],'confirmar':False}
            self.assertTrue(self.client.post('/calendar/confirm',json=body).json()['cancelado_por_usuario'])
            body['confirmar']=True
            self.assertEqual(self.client.post('/calendar/confirm',json=body).status_code,409)
            create.assert_called_once()
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


    def test_12_session_origin_csrf(self):
        outsider=TestClient(server.app,base_url='http://localhost')
        self.assertEqual(outsider.get('/token').status_code,401)
        self.assertEqual(outsider.get('/session',headers={'Origin':'https://evil.invalid'}).status_code,403)
        self.assertEqual(outsider.get('/session',headers={'Host':'evil.invalid'}).status_code,400)
        outsider.get('/session')
        self.assertEqual(outsider.post('/conversation/start').status_code,403)
        self.assertEqual(self.client.post('/conversation/start',headers={'Origin':'https://evil.invalid'}).status_code,403)

    def test_13_health_no_oauth(self):
        with patch.object(server,'obtener_servicio_drive',side_effect=AssertionError('OAuth')), patch.object(server,'obtener_servicio_calendar',side_effect=AssertionError('OAuth')):
            self.assertEqual(self.client.get('/health').status_code,200)

    def test_14_mixed_pdf(self):
        pdf=fitz.open();page=pdf.new_page();page.insert_text((50,50),'Pagina con texto')
        pdf.new_page();content=pdf.tobytes();pdf.close()
        with patch.object(documentos,'ocr_imagen_openai',return_value='Pagina escaneada') as ocr, patch.object(server,'crear_embeddings_lote',side_effect=lambda xs:[[1.,0.] for _ in xs]):
            response=self.client.post('/upload-rag',files={'file':('mixto.pdf',content,'application/pdf')})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(ocr.call_count,1)
        self.assertEqual(ocr.call_args.args[1],2)
        text=' '.join(x['texto'] for x in server.cargar_indice())
        self.assertIn('Pagina con texto',text);self.assertIn('Pagina escaneada',text)

    def test_15_corruption_preserved(self):
        path=server.INDICE_PATH;path.write_text('{invalid')
        try:
            with self.assertRaises(ValueError): almacenamiento.guardar_indice([])
            self.assertEqual(path.read_text(),'{invalid')
            self.assertEqual(self.client.get('/health').status_code,503)
        finally:
            path.unlink()

    def test_16_concurrent_writes_processes(self):
        code = "import almacenamiento as a; from sys import argv\nwith a.LOCK:\n data=a.cargar_indice()\n data.append({'archivo':argv[1]})\n a.guardar_indice(data)"
        processes=[subprocess.Popen([sys.executable,'-c',code,str(i)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for i in range(6)]
        for p in processes:
            out,err=p.communicate(timeout=30);self.assertEqual(p.returncode,0,err)
        self.assertEqual(len(almacenamiento.cargar_indice()),6)
        self.assertTrue((DATA/'backups'/'indice.anterior.json').exists())

    def test_17_invalid_dates_and_freebusy_errors(self):
        bad={'titulo':'Evento','inicio_iso':'2026-10-06T11:00:00-03:00','fin_iso':'2026-10-06T10:00:00-03:00'}
        self.assertEqual(self.client.post('/calendar/proposals',json=bad).status_code,400)
        service=Mock();service.freebusy.return_value.query.return_value.execute.return_value={'calendars':{'primary':{'errors':[{'reason':'notFound'}]}}}
        with patch.object(calendar_tools,'obtener_servicio_calendar',return_value=service):
            with self.assertRaises(RuntimeError):calendar_tools.consultar_disponibilidad(bad['inicio_iso'],bad['fin_iso'])

    def test_18_streamlit_and_local_paths(self):
        import archivos_locales
        self.assertEqual(archivos_locales.ARCHIVO_INDICE,server.INDICE_PATH)
        self.assertEqual(archivos_locales.CARPETA_SUBIDOS,server.UPLOAD_DIR)
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(configuracion.BASE_DIR/'app.py')).run(timeout=20)
        self.assertEqual(len(app.exception),0, str(app.exception))

    def test_19_orphan_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):memoria.agregar_mensaje(999999,'user','synthetic')

    def test_20_calendar_uncertain_no_retry(self):
        data={'titulo':'Prueba','inicio_iso':'2026-10-06T10:00:00-03:00','fin_iso':'2026-10-06T11:00:00-03:00'}
        proposal=self.client.post('/calendar/proposals',json=data).json()
        body={'propuesta_id':proposal['propuesta_id'],'confirmar':True}
        with patch.object(server,'crear_evento',side_effect=TimeoutError('test')) as create:
            self.assertEqual(self.client.post('/calendar/confirm',json=body).status_code,502)
            self.assertEqual(self.client.post('/calendar/confirm',json=body).status_code,409)
            create.assert_called_once()

    def test_21_backup_and_hash_compatibility(self):
        import respaldar
        import archivos_locales
        server.guardar_indice([{'archivo':'antiguo.txt','file_hash':server.calcular_sha256(b'sintetico'),'texto':'Prueba','embedding':[1.,0.]}])
        r=self.client.post('/upload-rag',files={'file':('otro.txt',b'sintetico','text/plain')})
        self.assertTrue(r.json()['duplicado'])
        self.assertTrue(archivos_locales.archivo_ya_indexado([{'sha256':'test-hash'}],'test-hash'))
        respaldar.main()
        copies=list((DATA/'backups').glob('*/memoria.db'))
        self.assertTrue(copies)
        with sqlite3.connect(copies[0]) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_22_upload_limit(self):
        with patch.object(server,'MAX_ARCHIVO_BYTES',8),patch.object(server,'procesar_carga') as process:
            r=self.client.post('/upload-rag',files={'file':('large.txt',b'123456789','text/plain')})
        self.assertEqual(r.status_code,413);process.assert_not_called()

    def test_23_homonyms_protected(self):
        data=[{'archivo':'same.txt','drive_file_id':'one'}, {'archivo':'same.txt','drive_file_id':'two'}]
        server.guardar_indice(data)
        with self.assertRaises(ValueError):rag.eliminar_documento_indice('same.txt')
        self.assertEqual(server.cargar_indice(),data)

if __name__ == '__main__':
    unittest.main(verbosity=2)
