import sqlite3
from pathlib import Path


# ============================================================
# CONFIGURACIÓN
# ============================================================

ARCHIVO_DB = Path("memoria.db")


# ============================================================
# CONEXIÓN
# ============================================================

def conectar():
    """
    Crea una conexión con la base de datos SQLite.
    """
    return sqlite3.connect(
        ARCHIVO_DB
    )


# ============================================================
# INICIALIZACIÓN
# ============================================================

def inicializar_db():
    """
    Crea las tablas necesarias si todavía no existen.
    """

    with conectar() as conexion:

        cursor = conexion.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS conversaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
                actualizado_en DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS mensajes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversacion_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (conversacion_id)
                    REFERENCES conversaciones(id)
                    ON DELETE CASCADE
            )
            """
        )

        conexion.commit()


# ============================================================
# CONVERSACIONES
# ============================================================

def crear_conversacion(
    titulo="Nueva conversación"
):
    """
    Crea una conversación y devuelve su ID.
    """

    with conectar() as conexion:

        cursor = conexion.cursor()

        cursor.execute(
            """
            INSERT INTO conversaciones (titulo)
            VALUES (?)
            """,
            (titulo,)
        )

        conexion.commit()

        return cursor.lastrowid


def listar_conversaciones(
    limite=20
):
    """
    Devuelve las conversaciones más recientes.
    """

    with conectar() as conexion:

        conexion.row_factory = sqlite3.Row

        cursor = conexion.cursor()

        cursor.execute(
            """
            SELECT
                id,
                titulo,
                creado_en,
                actualizado_en
            FROM conversaciones
            ORDER BY actualizado_en DESC
            LIMIT ?
            """,
            (limite,)
        )

        filas = cursor.fetchall()

        return [
            dict(fila)
            for fila in filas
        ]


def obtener_conversacion(
    conversacion_id
):
    """
    Obtiene una conversación específica.
    """

    with conectar() as conexion:

        conexion.row_factory = sqlite3.Row

        cursor = conexion.cursor()

        cursor.execute(
            """
            SELECT
                id,
                titulo,
                creado_en,
                actualizado_en
            FROM conversaciones
            WHERE id = ?
            """,
            (conversacion_id,)
        )

        fila = cursor.fetchone()

        if fila is None:
            return None

        return dict(fila)


def actualizar_titulo(
    conversacion_id,
    titulo
):
    """
    Actualiza el título de una conversación.
    """

    with conectar() as conexion:

        cursor = conexion.cursor()

        cursor.execute(
            """
            UPDATE conversaciones
            SET
                titulo = ?,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                titulo,
                conversacion_id
            )
        )

        conexion.commit()


def eliminar_conversacion(
    conversacion_id
):
    """
    Elimina una conversación y sus mensajes.
    """

    with conectar() as conexion:

        cursor = conexion.cursor()

        cursor.execute(
            """
            DELETE FROM mensajes
            WHERE conversacion_id = ?
            """,
            (conversacion_id,)
        )

        cursor.execute(
            """
            DELETE FROM conversaciones
            WHERE id = ?
            """,
            (conversacion_id,)
        )

        conexion.commit()


# ============================================================
# MENSAJES
# ============================================================

def agregar_mensaje(
    conversacion_id,
    role,
    content
):
    """
    Guarda un mensaje en la conversación.
    """

    with conectar() as conexion:

        cursor = conexion.cursor()

        cursor.execute(
            """
            INSERT INTO mensajes (
                conversacion_id,
                role,
                content
            )
            VALUES (?, ?, ?)
            """,
            (
                conversacion_id,
                role,
                content
            )
        )

        cursor.execute(
            """
            UPDATE conversaciones
            SET actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (conversacion_id,)
        )

        conexion.commit()


def obtener_mensajes(
    conversacion_id
):
    """
    Obtiene todos los mensajes de una conversación.
    """

    with conectar() as conexion:

        conexion.row_factory = sqlite3.Row

        cursor = conexion.cursor()

        cursor.execute(
            """
            SELECT
                role,
                content
            FROM mensajes
            WHERE conversacion_id = ?
            ORDER BY id ASC
            """,
            (conversacion_id,)
        )

        filas = cursor.fetchall()

        return [
            {
                "role": fila["role"],
                "content": fila["content"]
            }
            for fila in filas
        ]


def contar_mensajes(
    conversacion_id
):
    """
    Cuenta los mensajes de una conversación.
    """

    with conectar() as conexion:

        cursor = conexion.cursor()

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM mensajes
            WHERE conversacion_id = ?
            """,
            (conversacion_id,)
        )

        resultado = cursor.fetchone()

        return resultado[0]