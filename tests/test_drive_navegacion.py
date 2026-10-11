import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from drive_navegacion import consultar_carpetas


class CarpetasTest(unittest.TestCase):
    def setUp(self):
        self.service = Mock()
        self.service.files.return_value.list.return_value.execute.return_value = {
            'files': [{'id': 'carpeta-prueba', 'name': 'MBA'}],
            'nextPageToken': 'pagina-2', 'incompleteSearch': True,
        }

    def opciones(self):
        return self.service.files.return_value.list.call_args.kwargs

    def test_busqueda_carpetas_y_resultado_parcial(self):
        result = consultar_carpetas(self.service, nombre='MBA')
        self.assertIn("mimeType = 'application/vnd.google-apps.folder'", self.opciones()['q'])
        self.assertIn("name contains 'MBA'", self.opciones()['q'])
        self.assertIn('trashed = false', self.opciones()['q'])
        self.assertEqual(result['siguiente_pagina'], 'pagina-2')
        self.assertTrue(result['busqueda_incompleta'])

    def test_contenido_y_paginacion(self):
        consultar_carpetas(self.service, carpeta_id='carpeta-prueba', pagina='pagina-2', limite=200)
        self.assertEqual(self.opciones()['q'], "trashed = false and 'carpeta-prueba' in parents")
        self.assertEqual(self.opciones()['pageToken'], 'pagina-2')
        self.assertEqual(self.opciones()['pageSize'], 100)

    def test_nombre_con_comillas_y_barras(self):
        consultar_carpetas(self.service, nombre="O'Brien\\MBA")
        self.assertIn("name contains 'O\\'Brien\\\\MBA'", self.opciones()['q'])

    def test_carpeta_vacia_no_consulta_google(self):
        with self.assertRaises(ValueError):
            consultar_carpetas(self.service, carpeta_id=' ')
        self.service.files.assert_not_called()

    def test_error_google_no_se_presenta_como_lista_vacia(self):
        self.service.files.return_value.list.return_value.execute.side_effect = RuntimeError('Google no disponible')
        with self.assertRaises(RuntimeError):
            consultar_carpetas(self.service)
