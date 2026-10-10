from file_safety import ruta_archivo_segura
import almacenamiento
from almacenamiento import indice_transaccion
from configuracion import DATA_DIR
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

ARCHIVO_INDICE = (DATA_DIR / "indice.json")

CARPETA_SUBIDOS = (DATA_DIR / "documentos_subidos")


# ============================================================
# UTILIDADES
# ============================================================

def cargar_indice():
    return almacenamiento.cargar_indice()


def guardar_indice(indice):
    return almacenamiento.guardar_indice(indice)


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
            (item.get("file_hash") or item.get("sha256"))
            == hash_archivo
        ):
            return True

    return False


# ============================================================
# GUARDAR ARCHIVO SUBIDO
# ============================================================

def guardar_archivo_subido(nombre, contenido):
    if not contenido or len(contenido) > 25 * 1024 * 1024:
        raise ValueError('El archivo debe contener entre 1 byte y 25 MB.')
    CARPETA_SUBIDOS.mkdir(parents=True, exist_ok=True)
    ruta = ruta_archivo_segura(CARPETA_SUBIDOS, nombre, {'.pdf', '.docx', '.txt'})
    if ruta.exists():
        ruta = ruta_archivo_segura(CARPETA_SUBIDOS, f'{ruta.stem}_{hashlib.sha256(contenido).hexdigest()[:12]}{ruta.suffix}')
    with ruta.open('xb') as out:
        out.write(contenido)
    return ruta


# ============================================================
# INDEXACIÓN
# ============================================================

@indice_transaccion
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