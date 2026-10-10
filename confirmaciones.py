"""Propuestas de Calendar ligadas a sesión; confirmación y ejecución separadas."""
import secrets
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

class PropuestaEvento(BaseModel):
    titulo: str = Field(min_length=1, max_length=500)
    inicio_iso: str
    fin_iso: str
    descripcion: str = Field(default='', max_length=10000)
    ubicacion: str = Field(default='', max_length=1000)
    zona_horaria: str = 'America/Santiago'

class Confirmacion(BaseModel):
    propuesta_id: str
    confirmar: bool = False

_propuestas = {}
_lock = threading.Lock()

def validar_evento(value):
    data = value.model_dump() if isinstance(value, PropuestaEvento) else dict(value)
    data['titulo'] = data['titulo'].strip()
    if not data['titulo']:
        raise ValueError('El título no puede estar vacío.')
    ZoneInfo(data['zona_horaria'])
    start = datetime.fromisoformat(data['inicio_iso'].replace('Z', '+00:00'))
    end = datetime.fromisoformat(data['fin_iso'].replace('Z', '+00:00'))
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise ValueError('Las fechas requieren zona horaria y un fin posterior al inicio.')
    return data

def instalar_confirmaciones(app, crear):
    @app.post('/calendar/proposals')
    def proponer(evento: PropuestaEvento, request: Request):
        try:
            data = validar_evento(evento)
        except (ValueError, KeyError):
            return JSONResponse({'ok': False, 'error': 'Título, fechas o zona horaria inválidos.'}, status_code=400)
        with _lock:
            now = time.time()
            for key in list(_propuestas):
                if _propuestas[key]['expires'] < now:
                    del _propuestas[key]
            if len(_propuestas) >= 500:
                return JSONResponse({'ok': False, 'error': 'Demasiadas propuestas pendientes.'}, status_code=429)
            key = secrets.token_hex(24)
            _propuestas[key] = {'session': request.state.grifo_session, 'data': data,
                               'expires': now + 600, 'status': 'pending'}
        return {'ok': True, 'propuesta_id': key, 'evento': data}

    @app.post('/calendar/confirm')
    def confirmar(body: Confirmacion, request: Request):
        with _lock:
            proposal = _propuestas.get(body.propuesta_id)
            if not proposal or proposal['session'] != request.state.grifo_session or proposal['expires'] < time.time():
                return JSONResponse({'ok': False, 'error': 'Propuesta inexistente o vencida.'}, status_code=404)
            if proposal['status'] == 'done':
                return {'ok': True, 'result': proposal['result'], 'repetido': True}
            if proposal['status'] != 'pending':
                return JSONResponse({'ok': False, 'error': 'Propuesta ya procesada. Revisa la agenda antes de repetir.'}, status_code=409)
            if not body.confirmar:
                proposal['status'] = 'cancelled'
                return {'ok': False, 'cancelado_por_usuario': True}
            proposal['status'] = 'running'
        try:
            result = crear(**proposal['data'])
        except Exception:
            with _lock:
                proposal['status'] = 'uncertain'
            return JSONResponse({'ok': False, 'error': 'No se pudo confirmar el resultado. Revisa la agenda antes de crear otro evento.'}, status_code=502)
        with _lock:
            proposal['result'] = result
            proposal['status'] = 'done'
        return {'ok': True, 'result': result}
