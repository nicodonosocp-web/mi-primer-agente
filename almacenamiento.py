"""Índice JSON compatible, con bloqueo interproceso y reemplazo atómico."""
import json
import os
import tempfile
from functools import wraps
from pathlib import Path
from filelock import FileLock
from configuracion import DATA_DIR

INDICE_PATH = DATA_DIR / 'indice.json'
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOCK = FileLock(str(DATA_DIR / 'indice.lock'), timeout=120)

def indice_transaccion(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with LOCK:
            return fn(*args, **kwargs)
    return wrapped

@indice_transaccion
def cargar_indice():
    if not INDICE_PATH.exists():
        return []
    try:
        data = json.loads(INDICE_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError('Índice ilegible. Se conserva el archivo; restaura una copia antes de continuar.') from exc
    if not isinstance(data, list) or any(not isinstance(x, dict) for x in data):
        raise ValueError('Formato de índice inválido. No se sobrescribió el archivo.')
    return data

@indice_transaccion
def guardar_indice(data):
    if not isinstance(data, list) or any(not isinstance(x, dict) for x in data):
        raise ValueError('El índice debe ser una lista de registros.')
    # No reemplazar automáticamente un archivo corrupto.
    if INDICE_PATH.exists():
        cargar_indice()
    encoded = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
    fd, name = tempfile.mkstemp(prefix='indice_', suffix='.json.tmp', dir=DATA_DIR)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        if INDICE_PATH.exists():
            backup = DATA_DIR / 'backups'
            backup.mkdir(exist_ok=True)
            # La última versión válida se conserva sin tocar el esquema.
            (backup / 'indice.anterior.json').write_bytes(INDICE_PATH.read_bytes())
        os.replace(name, INDICE_PATH)
    finally:
        if Path(name).exists():
            Path(name).unlink()
