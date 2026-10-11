import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from seguridad import instalar_seguridad
from confirmaciones_drive import instalar_confirmaciones_drive


class ConfirmacionesDriveTest(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        instalar_seguridad(self.app)
        self.meta = Mock(return_value={'name': 'Prueba.pdf', 'mimeType': 'application/pdf'})
        self.indexar = Mock(return_value='Indexado')
        instalar_confirmaciones_drive(self.app, self.meta, self.indexar)
        self.app.get('/')(lambda: {'ok': True})
        self.client = self.cliente()

    def cliente(self):
        client = TestClient(self.app, base_url='http://localhost')
        client.headers['X-Grifo-CSRF'] = client.get('/session').json()['csrf']
        return client

    def propuesta(self):
        result = self.client.post('/drive/proposals', json={'file_id': 'real-id'})
        self.assertEqual(result.status_code, 200)
        return result.json()['propuesta_id']

    def test_confirmacion_unica_y_repeticion(self):
        key = self.propuesta()
        self.indexar.assert_not_called()
        body = {'propuesta_id': key, 'confirmar': True, 'file_id': 'injected-id'}
        self.assertTrue(self.client.post('/drive/confirm', json=body).json()['ok'])
        self.assertTrue(self.client.post('/drive/confirm', json=body).json()['repetido'])
        self.indexar.assert_called_once_with('real-id')

    def test_cancelacion_terminal(self):
        key = self.propuesta()
        r = self.client.post('/drive/confirm', json={'propuesta_id': key, 'confirmar': False})
        self.assertTrue(r.json()['cancelado_por_usuario'])
        self.assertEqual(self.client.post('/drive/confirm', json={'propuesta_id': key, 'confirmar': True}).status_code, 409)
        self.indexar.assert_not_called()

    def test_sesion_distinta_y_csrf(self):
        key = self.propuesta()
        body = {'propuesta_id': key, 'confirmar': True}
        self.assertEqual(self.cliente().post('/drive/confirm', json=body).status_code, 404)
        self.assertEqual(self.client.post('/drive/confirm', json=body, headers={'X-Grifo-CSRF': 'wrong'}).status_code, 403)
        self.indexar.assert_not_called()

    def test_error_no_se_reintenta(self):
        self.indexar.side_effect = RuntimeError('error sintético')
        body = {'propuesta_id': self.propuesta(), 'confirmar': True}
        self.assertEqual(self.client.post('/drive/confirm', json=body).status_code, 502)
        self.assertEqual(self.client.post('/drive/confirm', json=body).status_code, 409)
        self.assertEqual(self.indexar.call_count, 1)

    def test_formato_no_soportado(self):
        self.meta.return_value['mimeType'] = 'application/vnd.google-apps.folder'
        self.assertEqual(self.client.post('/drive/proposals', json={'file_id': 'folder'}).status_code, 400)
        self.indexar.assert_not_called()

    def test_enlace_externo_solo_entrada_documento(self):
        headers = {'sec-fetch-site': 'cross-site', 'sec-fetch-mode': 'navigate', 'sec-fetch-dest': 'document'}
        self.assertEqual(self.client.get('/', headers=headers).status_code, 200)
        self.assertEqual(self.client.get('/session', headers=headers).status_code, 403)
        self.assertEqual(self.client.post('/drive/proposals', json={'file_id': 'a'}, headers=headers).status_code, 403)
        self.assertEqual(self.client.get('/', headers={**headers, 'sec-fetch-dest': 'iframe'}).status_code, 403)
        self.assertEqual(self.client.get('/', headers={'sec-fetch-site': 'cross-site'}).status_code, 403)
        self.assertEqual(self.client.get('/', headers={**headers, 'origin': 'https://example.com'}).status_code, 403)

    def test_expiracion_y_booleano_estricto(self):
        from unittest.mock import patch
        import time
        key = self.propuesta()
        self.assertEqual(self.client.post('/drive/confirm', json={'propuesta_id': key, 'confirmar': 'true'}).status_code, 422)
        with patch('confirmaciones_drive.time.time', return_value=time.time() + 601):
            self.assertEqual(self.client.post('/drive/confirm', json={'propuesta_id': key, 'confirmar': True}).status_code, 404)
        self.indexar.assert_not_called()
