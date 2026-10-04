import hashlib
import json
from pathlib import Path

from rag_drive import (
    extraer_documento,
    dividir_texto,
    crear_embedding,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

ARCHIVO_INDICE = Path("indice.json")

CARPETA_SUBIDOS = Path(
    "documentos_subidos"
)


# ============================================================
# UTILIDADES
# ============================================================

def cargar_indice():
    """
    Carga indice.json.
    """

    if not ARCHIVO_INDICE.exists():
        return []

    try:

        with ARCHIVO_INDICE.open(
            "r",
            encoding="utf-8",
        ) as archivo:

            return json.load(
                archivo
            )

    except Exception:

        return []


def guardar_indice(
    indice,
):
    """
    Guarda indice.json.
    """

    with ARCHIVO_INDICE.open(
        "w",
        encoding="utf-8",
    ) as archivo:

        json.dump(
            indice,
            archivo,
            ensure_ascii=False,
        )


def calcular_hash(
    ruta,
):
    """
    Calcula SHA-256 de un archivo.
    """

    sha256 = hashlib.sha256()

    with open(
        ruta,
        "rb",
    ) as archivo:

        while True:

            bloque = archivo.read(
                1024 * 1024
            )

            if not bloque:
                break

            sha256.update(
                bloque
            )

    return sha256.hexdigest()


def archivo_ya_indexado(
    indice,
    hash_archivo,
):
    """
    Comprueba si un archivo idéntico ya está indexado.
    """

    for item in indice:

        if (
            item.get("file_hash")
            == hash_archivo
        ):
            return True

    return False


# ============================================================
# GUARDAR ARCHIVO SUBIDO
# ============================================================

def guardar_archivo_subido(
    nombre,
    contenido,
):
    """
    Guarda un archivo recibido desde Streamlit.
    """

    CARPETA_SUBIDOS.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Evita rutas tipo ../../archivo
    nombre_seguro = Path(
        nombre
    ).name

    ruta = (
        CARPETA_SUBIDOS
        / nombre_seguro
    )

    ruta.write_bytes(
        contenido
    )

    return ruta


# ============================================================
# INDEXACIÓN
# ============================================================

def indexar_archivo_local(
    ruta,
):
    """
    Indexa PDF, DOCX o TXT y lo agrega al RAG.
    """

    ruta = Path(
        ruta
    )

    if not ruta.exists():

        return {
            "estado": "error",
            "mensaje": (
                "El archivo no existe."
            ),
        }

    extensiones_permitidas = {
        ".pdf",
        ".docx",
        ".txt",
    }

    if (
        ruta.suffix.lower()
        not in extensiones_permitidas
    ):

        return {
            "estado": "error",
            "mensaje": (
                f"Formato no soportado: "
                f"{ruta.suffix}"
            ),
        }

    indice = cargar_indice()

    hash_archivo = calcular_hash(
        ruta
    )

    if archivo_ya_indexado(
        indice,
        hash_archivo,
    ):

        return {
            "estado": "existente",
            "mensaje": (
                "Este archivo ya estaba "
                "indexado."
            ),
            "archivo": ruta.name,
        }

    # --------------------------------------------------------
    # EXTRAER TEXTO
    # --------------------------------------------------------

    try:

        texto = extraer_documento(
            ruta
        )

    except Exception as error:

        return {
            "estado": "error",
            "mensaje": (
                "No fue posible extraer "
                f"el texto: {error}"
            ),
        }

    if not texto.strip():

        return {
            "estado": "error",
            "mensaje": (
                "No se encontró texto "
                "extraíble en el documento."
            ),
        }

    # --------------------------------------------------------
    # FRAGMENTAR
    # --------------------------------------------------------

    fragmentos = dividir_texto(
        texto
    )

    if not fragmentos:

        return {
            "estado": "error",
            "mensaje": (
                "No se generaron fragmentos."
            ),
        }

    print(
        f"[LOCAL] Indexando "
        f"{ruta.name}"
    )

    print(
        f"[LOCAL] Fragmentos: "
        f"{len(fragmentos)}"
    )

    # --------------------------------------------------------
    # EMBEDDINGS
    # --------------------------------------------------------

    for numero, fragmento in enumerate(
        fragmentos,
        start=1,
    ):

        print(
            f"[LOCAL] Embedding "
            f"{numero}/"
            f"{len(fragmentos)}"
        )

        embedding = crear_embedding(
            fragmento
        )

        indice.append({
            "archivo": ruta.name,
            "fragmento": numero,
            "texto": fragmento,
            "embedding": embedding,
            "origen": "carga_manual",
            "file_hash": hash_archivo,
        })

    # --------------------------------------------------------
    # GUARDAR
    # --------------------------------------------------------

    guardar_indice(
        indice
    )

    return {
        "estado": "ok",
        "mensaje": (
            "Archivo indexado "
            "correctamente."
        ),
        "archivo": ruta.name,
        "fragmentos": len(
            fragmentos
        ),
        "hash": hash_archivo,
    }