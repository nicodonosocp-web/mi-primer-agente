"""Copia consistente de SQLite y del índice. Ejecutar antes de actualizar."""
from datetime import datetime
import sqlite3
from configuracion import DATA_DIR
from almacenamiento import LOCK, cargar_indice

def main():
    destino = DATA_DIR / 'backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    with LOCK:
        indice = DATA_DIR / 'indice.json'
        if indice.exists():
            cargar_indice()  # Rechazar corrupción sin sobrescribirla.
        destino.mkdir(parents=True, exist_ok=False)
        db = DATA_DIR / 'memoria.db'
        if db.exists():
            origen = sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)
            copia = sqlite3.connect(destino / 'memoria.db')
            try:
                origen.backup(copia)
            finally:
                copia.close(); origen.close()
        if indice.exists():
            (destino / 'indice.json').write_bytes(indice.read_bytes())
    print('Respaldo creado en:', destino)

if __name__ == '__main__':
    main()
