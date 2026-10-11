"""Indexación local con propuesta por sesión y confirmación de un solo uso."""
import secrets
import threading
import time
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StrictBool


class ArchivoDrive(BaseModel):
    file_id: str = Field(min_length=1, max_length=200, pattern=r'^[A-Za-z0-9_-]+$')


class ConfirmarDrive(BaseModel):
    propuesta_id: str
    confirmar: StrictBool = False


TIPOS = {
    'application/pdf', 'text/plain',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.google-apps.document',
}


def instalar_confirmaciones_drive(app, metadatos, indexar):
    propuestas = {}
    lock = threading.Lock()

    @app.post('/drive/proposals')
    def proponer(body: ArchivoDrive, request: Request):
        try:
            archivo = metadatos(body.file_id)
        except Exception:
            return JSONResponse({'ok': False, 'error': 'No se pudo verificar el archivo en Drive. Revisa su acceso.'}, status_code=502)
        if archivo.get('mimeType') not in TIPOS:
            return JSONResponse({'ok': False, 'error': 'Solo se pueden indexar PDF, DOCX, TXT o documentos Google Docs.'}, status_code=400)
        data = {'file_id': body.file_id, 'nombre': archivo.get('name', body.file_id)}
        with lock:
            now = time.time()
            for key in list(propuestas):
                if propuestas[key]['expires'] < now and propuestas[key]['status'] != 'running':
                    del propuestas[key]
            if len(propuestas) >= 500:
                return JSONResponse({'ok': False, 'error': 'Demasiadas propuestas pendientes.'}, status_code=429)
            key = secrets.token_hex(24)
            propuestas[key] = {'session': request.state.grifo_session, 'data': data,
                              'expires': now + 600, 'status': 'pending'}
        return {'ok': True, 'propuesta_id': key, 'archivo': data}

    @app.post('/drive/confirm')
    def confirmar(body: ConfirmarDrive, request: Request):
        with lock:
            propuesta = propuestas.get(body.propuesta_id)
            if not propuesta or propuesta['session'] != request.state.grifo_session or propuesta['expires'] < time.time():
                return JSONResponse({'ok': False, 'error': 'Propuesta inexistente o vencida.'}, status_code=404)
            if propuesta['status'] == 'done':
                return {'ok': True, 'result': propuesta['result'], 'repetido': True}
            if propuesta['status'] != 'pending':
                return JSONResponse({'ok': False, 'error': 'Propuesta ya procesada. Revisa la biblioteca antes de repetir.'}, status_code=409)
            if not body.confirmar:
                propuesta['status'] = 'cancelled'
                return {'ok': False, 'cancelado_por_usuario': True}
            propuesta['status'] = 'running'
        try:
            resultado = indexar(propuesta['data']['file_id'])
        except Exception:
            with lock:
                propuesta['status'] = 'failed'
            return JSONResponse({'ok': False, 'error': 'No se pudo completar la indexación. Revisa la biblioteca antes de volver a intentarlo.'}, status_code=502)
        with lock:
            propuesta['status'] = 'done'
            propuesta['result'] = resultado
        return {'ok': True, 'result': resultado}
