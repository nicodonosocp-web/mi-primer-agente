"""Rutas únicas para UI, SQLite, índice y credenciales locales.

Por defecto se conservan los archivos junto al proyecto. MI_AGENTE_DATA_DIR es
opcional y permite aislar pruebas o elegir una carpeta existente, sin migraciones.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')
DATA_DIR = Path(os.getenv('MI_AGENTE_DATA_DIR') or BASE_DIR).expanduser()
if not DATA_DIR.is_absolute():
    DATA_DIR = BASE_DIR / DATA_DIR
DATA_DIR = DATA_DIR.resolve()
