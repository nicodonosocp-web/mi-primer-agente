from configuracion import DATA_DIR
import sqlite3
from pathlib import Path
from datetime import datetime


# ============================================================
# CONFIGURACIÓN
# ============================================================

ARCHIVO_DB = (DATA_DIR / "memoria.db")


# ============================================================
# CONEXIÓN
# ============================================================

def conectar():
    """
    Conecta con la misma base SQLite utilizada
    para las conversaciones.
    """

    conexion = sqlite3.connect(
        ARCHIVO_DB, timeout=30
    )

    conexion.row_factory = sqlite3.Row

    return conexion


# ============================================================
# INICIALIZACIÓN
# ============================================================

def inicializar_memoria_largo_plazo():
    """
    Crea la tabla de memoria de largo plazo.
    """

    with conectar() as conexion:

        cursor = conexion.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS memoria_largo_plazo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                categoria TEXT NOT NULL,

                clave TEXT NOT NULL,

                contenido TEXT NOT NULL,

                fuente_conversacion_id INTEGER,

                importancia INTEGER DEFAULT 3,

                activa INTEGER DEFAULT 1,

                creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,

                actualizado_en DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_memoria_clave
            ON memoria_largo_plazo(clave)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_memoria_categoria
            ON memoria_largo_plazo(categoria)
            """
        )

        conexion.commit()


# ============================================================
# GUARDAR MEMORIA
# ============================================================

def guardar_memoria(
    categoria,
    clave,
    contenido,
    fuente_conversacion_id=None,
    importancia=3,
):
    """
    Guarda o actualiza una memoria.

    Si ya existe una memoria activa con la misma
    categoría y clave, la actualiza.
    """

    categoria = categoria.strip().lower()
    clave = clave.strip()
    contenido = contenido.strip()

    importancia = max(
        1,
        min(int(importancia), 5)
    )

    with conectar() as conexion:

        conexion.execute("BEGIN IMMEDIATE")
        cursor = conexion.cursor()

        cursor.execute(
            """
            SELECT id
            FROM memoria_largo_plazo
            WHERE
                categoria = ?
                AND LOWER(clave) = LOWER(?)
                AND activa = 1
            LIMIT 1
            """,
            (
                categoria,
                clave,
            )
        )

        existente = cursor.fetchone()

        if existente:

            memoria_id = existente["id"]

            cursor.execute(
                """
                UPDATE memoria_largo_plazo
                SET
                    contenido = ?,
                    fuente_conversacion_id = ?,
                    importancia = ?,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    contenido,
                    fuente_conversacion_id,
                    importancia,
                    memoria_id,
                )
            )

            conexion.commit()

            return {
                "accion": "actualizada",
                "id": memoria_id,
                "categoria": categoria,
                "clave": clave,
                "contenido": contenido,
            }

        cursor.execute(
            """
            INSERT INTO memoria_largo_plazo (
                categoria,
                clave,
                contenido,
                fuente_conversacion_id,
                importancia
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                categoria,
                clave,
                contenido,
                fuente_conversacion_id,
                importancia,
            )
        )

        conexion.commit()

        memoria_id = cursor.lastrowid

        return {
            "accion": "creada",
            "id": memoria_id,
            "categoria": categoria,
            "clave": clave,
            "contenido": contenido,
        }


# ============================================================
# BUSCAR MEMORIA
# ============================================================

def buscar_memorias(
    consulta,
    limite=10,
):
    """
    Busca memorias activas por coincidencia
    de texto en clave, contenido o categoría.
    """

    consulta = consulta.strip()

    if not consulta:
        return []

    limite = max(
        1,
        min(int(limite), 50)
    )

    patron = f"%{consulta}%"

    with conectar() as conexion:

        cursor = conexion.cursor()

        cursor.execute(
            """
            SELECT
                id,
                categoria,
                clave,
                contenido,
                fuente_conversacion_id,
                importancia,
                creado_en,
                actualizado_en
            FROM memoria_largo_plazo
            WHERE
                activa = 1
                AND (
                    clave LIKE ?
                    OR contenido LIKE ?
                    OR categoria LIKE ?
                )
            ORDER BY
                importancia DESC,
                actualizado_en DESC
            LIMIT ?
            """,
            (
                patron,
                patron,
                patron,
                limite,
            )
        )

        filas = cursor.fetchall()

        return [
            dict(fila)
            for fila in filas
        ]


# ============================================================
# LISTAR MEMORIAS
# ============================================================

def listar_memorias(
    limite=50,
    categoria=None,
):
    """
    Lista memorias activas.
    """

    limite = max(
        1,
        min(int(limite), 100)
    )

    with conectar() as conexion:

        cursor = conexion.cursor()

        if categoria:

            cursor.execute(
                """
                SELECT
                    id,
                    categoria,
                    clave,
                    contenido,
                    fuente_conversacion_id,
                    importancia,
                    creado_en,
                    actualizado_en
                FROM memoria_largo_plazo
                WHERE
                    activa = 1
                    AND categoria = ?
                ORDER BY
                    importancia DESC,
                    actualizado_en DESC
                LIMIT ?
                """,
                (
                    categoria.strip().lower(),
                    limite,
                )
            )

        else:

            cursor.execute(
                """
                SELECT
                    id,
                    categoria,
                    clave,
                    contenido,
                    fuente_conversacion_id,
                    importancia,
                    creado_en,
                    actualizado_en
                FROM memoria_largo_plazo
                WHERE activa = 1
                ORDER BY
                    importancia DESC,
                    actualizado_en DESC
                LIMIT ?
                """,
                (limite,)
            )

        filas = cursor.fetchall()

        return [
            dict(fila)
            for fila in filas
        ]


# ============================================================
# OBTENER UNA MEMORIA
# ============================================================

def obtener_memoria(
    memoria_id
):
    """
    Obtiene una memoria concreta.
    """

    with conectar() as conexion:

        cursor = conexion.cursor()

        cursor.execute(
            """
            SELECT
                id,
                categoria,
                clave,
                contenido,
                fuente_conversacion_id,
                importancia,
                activa,
                creado_en,
                actualizado_en
            FROM memoria_largo_plazo
            WHERE id = ?
            """,
            (memoria_id,)
        )

        fila = cursor.fetchone()

        if not fila:
            return None

        return dict(fila)


# ============================================================
# ELIMINAR / DESACTIVAR MEMORIA
# ============================================================

def desactivar_memoria(
    memoria_id
):
    """
    Desactiva una memoria sin borrarla físicamente.
    """

    with conectar() as conexion:

        cursor = conexion.cursor()

        cursor.execute(
            """
            UPDATE memoria_largo_plazo
            SET
                activa = 0,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (memoria_id,)
        )

        conexion.commit()

        return cursor.rowcount > 0


# ============================================================
# ESTADÍSTICAS
# ============================================================

def contar_memorias():
    """
    Cuenta memorias activas.
    """

    with conectar() as conexion:

        cursor = conexion.cursor()

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM memoria_largo_plazo
            WHERE activa = 1
            """
        )

        resultado = cursor.fetchone()

        return resultado[0]


# ============================================================
# EJECUCIÓN DIRECTA
# ============================================================

if __name__ == "__main__":

    inicializar_memoria_largo_plazo()

    print(
        "Memoria de largo plazo inicializada."
    )

    print(
        f"Memorias activas: {contar_memorias()}"
    )