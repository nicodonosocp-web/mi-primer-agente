from configuracion import DATA_DIR
from file_safety import ruta_archivo_segura
import documentos
from starlette.concurrency import run_in_threadpool
import almacenamiento
from almacenamiento import indice_transaccion
import base64
import hashlib
import json
import os
import re
from pathlib import Path

import fitz
import requests

from docx import Document
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from openai import OpenAI
from pydantic import BaseModel
from pypdf import PdfReader

from memoria import (
    inicializar_db,
    crear_conversacion,
    listar_conversaciones,
    obtener_conversacion,
    actualizar_titulo,
    agregar_mensaje,
    obtener_mensajes,
    contar_mensajes,
)

from memoria_largo_plazo import (
    inicializar_memoria_largo_plazo,
    guardar_memoria,
    buscar_memorias,
    listar_memorias,
)

from drive_tools import (
    obtener_servicio_drive,
)
from drive_navegacion import consultar_carpetas

from rag_drive import (
    indexar_archivo_drive,
)

from rag_mejorado import (
    buscar_documentos_hibrido,
    dividir_texto_inteligente,
    obtener_estadisticas_indice,
    eliminar_documento_indice,
)

from calendar_tools import (
    obtener_servicio_calendar,
    listar_calendarios,
    listar_eventos,
    eventos_entre,
    buscar_eventos,
    consultar_disponibilidad,
    crear_evento,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()

OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY"
)

if not OPENAI_API_KEY:
    raise RuntimeError(
        "No se encontró OPENAI_API_KEY en .env"
    )


BASE_DIR = Path(
    __file__
).resolve().parent

INDICE_PATH = (
    DATA_DIR
    /
    "indice.json"
)

UPLOAD_DIR = (
    DATA_DIR
    /
    "documentos_subidos"
)

UPLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


MODELO_EMBEDDING = (
    "text-embedding-3-small"
)

MODELO_OCR = (
    "gpt-5.6-luna"
)

TAMANO_FRAGMENTO = 1200

SOLAPAMIENTO = 180

MAX_ARCHIVO_BYTES = (
    25
    *
    1024
    *
    1024
)

EXTENSIONES_PERMITIDAS = {
    ".pdf",
    ".docx",
    ".txt",
}


# ============================================================
# OPENAI
# ============================================================

client = OpenAI(
    api_key=OPENAI_API_KEY
)


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="GRIFO V2.4 RC1"
)


# ============================================================
# BASES DE DATOS
# ============================================================

from seguridad import instalar_seguridad
from confirmaciones import instalar_confirmaciones
from confirmaciones_drive import instalar_confirmaciones_drive
instalar_seguridad(app)
instalar_confirmaciones(app, lambda **kwargs: crear_evento(**kwargs))
instalar_confirmaciones_drive(app, lambda file_id: obtener_archivo_drive_backend(file_id),
                             lambda file_id: indexar_archivo_drive(file_id))

inicializar_db()

inicializar_memoria_largo_plazo()


# ============================================================
# MODELOS
# ============================================================

class ToolRequest(BaseModel):
    name: str
    arguments: dict


class MessageRequest(BaseModel):
    conversacion_id: int
    role: str
    content: str


class DeleteDocumentRequest(BaseModel):
    archivo: str


class ReindexDocumentRequest(BaseModel):
    archivo: str


class RagSearchRequest(BaseModel):
    consulta: str
    archivo: str | None = None
    limite: int = 6


class PreviewDocumentRequest(BaseModel):
    archivo: str
    limite: int = 8


class UnifiedSearchRequest(BaseModel):
    consulta: str
    limite_rag: int = 6
    limite_drive: int = 8
    incluir_drive: bool = True


# ============================================================
# UTILIDADES SQLITE
# ============================================================

def convertir_fila_a_dict(
    fila
):

    if fila is None:
        return None

    if isinstance(
        fila,
        dict,
    ):
        return fila

    if hasattr(
        fila,
        "keys",
    ):

        try:

            return {
                clave:
                    fila[clave]

                for clave
                in fila.keys()
            }

        except Exception:
            pass

    return fila


def normalizar_conversacion(
    fila
):

    fila = convertir_fila_a_dict(
        fila
    )

    if fila is None:
        return None

    if isinstance(
        fila,
        dict,
    ):

        return {
            "id":
                fila.get("id"),

            "titulo":
                fila.get(
                    "titulo",
                    "Sin título",
                ),

            "fecha_creacion":
                (fila.get("fecha_creacion") or fila.get("creado_en")),

            "fecha_actualizacion":
                (fila.get("fecha_actualizacion") or fila.get("actualizado_en")),
        }

    if isinstance(
        fila,
        (list, tuple),
    ):

        return {
            "id":
                fila[0]
                if len(fila) > 0
                else None,

            "titulo":
                fila[1]
                if len(fila) > 1
                else "Sin título",

            "fecha_creacion":
                fila[2]
                if len(fila) > 2
                else None,

            "fecha_actualizacion":
                fila[3]
                if len(fila) > 3
                else None,
        }

    return {
        "id": None,
        "titulo": str(fila),
        "fecha_creacion": None,
        "fecha_actualizacion": None,
    }


def normalizar_mensaje(
    fila
):

    fila = convertir_fila_a_dict(
        fila
    )

    if fila is None:
        return None

    if isinstance(
        fila,
        dict,
    ):

        role = (
            fila.get("role")
            or
            fila.get("rol")
            or
            fila.get("tipo")
        )

        content = (
            fila.get("content")
            or
            fila.get("contenido")
            or
            fila.get("mensaje")
            or
            ""
        )

        return {
            "id":
                fila.get("id"),

            "role":
                role,

            "content":
                content,

            "fecha":
                (
                    fila.get("fecha")
                    or
                    fila.get(
                        "fecha_creacion"
                    )
                    or
                    fila.get(
                        "created_at"
                    )
                ),
        }

    if isinstance(
        fila,
        (list, tuple),
    ):

        if len(fila) >= 5:

            return {
                "id":
                    fila[0],

                "role":
                    fila[2],

                "content":
                    fila[3],

                "fecha":
                    fila[4],
            }

        if len(fila) >= 3:

            return {
                "id":
                    fila[0],

                "role":
                    fila[1],

                "content":
                    fila[2],

                "fecha":
                    (
                        fila[3]
                        if len(fila) > 3
                        else None
                    ),
            }

    return {
        "id": None,
        "role": None,
        "content": str(fila),
        "fecha": None,
    }


# ============================================================
# CONVERSACIONES
# ============================================================

@app.get(
    "/conversations"
)
def api_listar_conversaciones():

    try:

        filas = listar_conversaciones()

        conversaciones = []

        for fila in filas or []:

            item = normalizar_conversacion(
                fila
            )

            if (
                item
                and
                item.get("id")
                is not None
            ):

                conversaciones.append(
                    item
                )

        return {
            "ok": True,
            "result": conversaciones,
        }

    except Exception as error:

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "La operación no pudo completarse. Revisa los datos y el estado de la integración.",
            },
        )


@app.get(
    "/conversation/{conversacion_id}"
)
def api_obtener_conversacion(
    conversacion_id: int
):

    try:

        conversacion = (
            normalizar_conversacion(
                obtener_conversacion(
                    conversacion_id
                )
            )
        )

        mensajes_raw = (
            obtener_mensajes(
                conversacion_id
            )
        )

        mensajes = []

        for fila in mensajes_raw or []:

            item = normalizar_mensaje(
                fila
            )

            if (
                item
                and
                item.get(
                    "content"
                )
            ):

                mensajes.append(
                    item
                )

        return {
            "ok": True,
            "conversacion":
                conversacion,
            "mensajes":
                mensajes,
        }

    except Exception as error:

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "La operación no pudo completarse. Revisa los datos y el estado de la integración.",
            },
        )


@app.post(
    "/conversation/start"
)
def iniciar_conversacion():

    try:

        conversacion_id = (
            crear_conversacion()
        )

        return {
            "ok": True,
            "conversacion_id":
                conversacion_id,
        }

    except Exception as error:

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "La operación no pudo completarse. Revisa los datos y el estado de la integración.",
            },
        )


@app.post(
    "/conversation/message"
)
def guardar_mensaje_api(
    request: MessageRequest
):

    try:

        role = (
            request.role
            .strip()
            .lower()
        )

        content = (
            request.content
            .strip()
        )

        if role not in (
            "user",
            "assistant",
        ):

            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "error":
                        "Role inválido.",
                },
            )

        if not content:

            return {
                "ok": True,
                "guardado": False,
            }

        agregar_mensaje(
            request.conversacion_id,
            role,
            content,
        )

        cantidad = contar_mensajes(
            request.conversacion_id
        )

        if (
            role == "user"
            and
            cantidad <= 2
        ):

            titulo = (
                content
                .replace(
                    "\n",
                    " ",
                )
                .strip()
            )

            if len(titulo) > 60:

                titulo = (
                    titulo[:57]
                    +
                    "..."
                )

            if titulo:

                try:

                    actualizar_titulo(
                        request.conversacion_id,
                        titulo,
                    )

                except Exception:
                    pass

        return {
            "ok": True,
            "guardado": True,
            "mensajes": cantidad,
        }

    except Exception as error:

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "La operación no pudo completarse. Revisa los datos y el estado de la integración.",
            },
        )


# ============================================================
# ÍNDICE
# ============================================================

def cargar_indice():
    return almacenamiento.cargar_indice()


def guardar_indice(indice):
    return almacenamiento.guardar_indice(indice)


def contar_fragmentos_indice():

    return len(
        cargar_indice()
    )


# ============================================================
# RAG
# ============================================================

def buscar_en_documentos(
    consulta: str,
    limite: int = 6,
    drive_file_id: str = None,
    archivo: str = None,
):

    return (
        buscar_documentos_hibrido(
            consulta=consulta,
            limite=limite,
            drive_file_id=
                drive_file_id,
            archivo=
                archivo,
        )
    )


def dividir_texto(
    texto: str,
    tamano: int = TAMANO_FRAGMENTO,
    solapamiento: int = SOLAPAMIENTO,
):

    return (
        dividir_texto_inteligente(
            texto=
                texto,
            tamano_objetivo=
                tamano,
            solapamiento=
                solapamiento,
        )
    )


def obtener_items_documento(
    archivo: str
):

    objetivo = (
        archivo
        .strip()
        .lower()
    )

    return [
        item
        for item
        in cargar_indice()
        if (
            item.get(
                "archivo",
                "",
            )
            .strip()
            .lower()
            ==
            objetivo
        )
    ]


def obtener_info_documento(
    archivo: str
):

    items = obtener_items_documento(
        archivo
    )

    if not items:
        return None

    primero = items[0]

    origen = primero.get(
        "origen"
    )

    if primero.get("drive_file_id") or origen == "google_drive":
        origen = "drive"

    if not origen:

        origen = (
            "drive"
            if primero.get(
                "drive_file_id"
            )
            else "local"
        )

    return {
        "archivo":
            archivo,

        "origen":
            origen,

        "fragmentos":
            len(items),

        "drive_file_id":
            primero.get(
                "drive_file_id"
            ),

        "sha256":
            primero.get(
                "sha256"
            ),
    }


# ============================================================
# ARCHIVOS
# ============================================================

def limpiar_nombre_archivo(
    nombre: str
):

    nombre = (
        Path(nombre).name
    )

    nombre = re.sub(
        r"[^A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ._ ()\-]",
        "_",
        nombre,
    )

    nombre = nombre.strip()

    if not nombre:
        nombre = "documento"

    return nombre


def calcular_sha256(
    contenido: bytes
):

    return (
        hashlib
        .sha256(
            contenido
        )
        .hexdigest()
    )


# ============================================================
# TXT
# ============================================================

def extraer_txt(ruta):
    return documentos.extraer_txt(ruta)


# ============================================================
# OCR
# ============================================================

def pagina_pdf_a_data_url(pagina, zoom=2.0):
    return documentos.pagina_pdf_a_data_url(pagina, zoom)


def ocr_imagen_openai(image_data_url, numero_pagina):
    return documentos.ocr_imagen_openai(image_data_url, numero_pagina)


def extraer_pdf_con_ocr(ruta):
    return documentos.extraer_pdf_con_ocr(ruta)


# ============================================================
# PDF
# ============================================================

def extraer_pdf(ruta):
    return documentos.extraer_pdf(ruta)


# ============================================================
# DOCX
# ============================================================

def extraer_docx(ruta):
    return documentos.extraer_docx(ruta)


def extraer_texto_documento(ruta):
    return documentos.extraer_texto_documento(ruta)


# ============================================================
# EMBEDDINGS
# ============================================================

def crear_embeddings_lote(
    fragmentos,
    lote=50,
):

    embeddings = []

    for inicio in range(
        0,
        len(fragmentos),
        lote,
    ):

        bloque = fragmentos[
            inicio:
            inicio + lote
        ]

        respuesta = (
            client.embeddings.create(
                model=
                    MODELO_EMBEDDING,

                input=
                    bloque,
            )
        )

        embeddings.extend(
            item.embedding
            for item
            in respuesta.data
        )

    return embeddings


# ============================================================
# INDEXACIÓN LOCAL
# ============================================================

@indice_transaccion
def indexar_documento_local(
    ruta: Path,
    sha256: str,
):

    indice = cargar_indice()

    for item in indice:

        if (
            (item.get("sha256") or item.get("file_hash"))
            ==
            sha256
        ):

            return {
                "duplicado":
                    True,

                "archivo":
                    item.get(
                        "archivo",
                        ruta.name,
                    ),

                "fragmentos_agregados":
                    0,

                "texto_extraido_caracteres":
                    0,
            }

    texto = (
        extraer_texto_documento(
            ruta
        )
    )

    if not texto.strip():

        raise ValueError(
            "No fue posible extraer texto."
        )

    fragmentos = (
        dividir_texto(
            texto
        )
    )

    if not fragmentos:

        raise ValueError(
            "No fue posible crear fragmentos."
        )

    embeddings = (
        crear_embeddings_lote(
            fragmentos
        )
    )

    if len(embeddings) != len(fragmentos):
        raise RuntimeError("Embeddings incompletos; el índice no se modificó.")

    nuevos_items = []

    for numero, (
        fragmento,
        embedding,
    ) in enumerate(
        zip(
            fragmentos,
            embeddings,
        ),
        start=1,
    ):

        nuevos_items.append(
            {
                "archivo":
                    ruta.name,

                "fragmento":
                    numero,

                "texto":
                    fragmento,

                "embedding":
                    embedding,

                "origen":
                    "local",

                "sha256":
                    sha256,
            }
        )

    indice.extend(
        nuevos_items
    )

    guardar_indice(
        indice
    )

    return {
        "duplicado":
            False,

        "archivo":
            ruta.name,

        "fragmentos_agregados":
            len(
                nuevos_items
            ),

        "texto_extraido_caracteres":
            len(texto),
    }


# ============================================================
# UPLOAD
# ============================================================

@app.post('/upload-rag')
async def upload_rag(file: UploadFile = File(...)):
    try:
        nombre = limpiar_nombre_archivo(file.filename or 'documento')
        ruta_archivo_segura(UPLOAD_DIR, nombre, EXTENSIONES_PERMITIDAS)
        contenido = bytearray()
        while True:
            bloque = await file.read(1024 * 1024)
            if not bloque:
                break
            contenido.extend(bloque)
            if len(contenido) > MAX_ARCHIVO_BYTES:
                return JSONResponse(status_code=413, content={'ok': False, 'error': 'El archivo supera 25 MB.'})
        if not contenido:
            return JSONResponse(status_code=400, content={'ok': False, 'error': 'Archivo vacío.'})
        return await run_in_threadpool(procesar_carga, nombre, bytes(contenido))
    except ValueError as error:
        return JSONResponse(status_code=400, content={'ok': False, 'error': str(error)})
    except Exception:
        return JSONResponse(status_code=500, content={'ok': False, 'error': 'No se pudo procesar el documento. El índice anterior se conserva.'})
    finally:
        await file.close()

@indice_transaccion
def procesar_carga(nombre, contenido):
    sha256 = calcular_sha256(contenido)
    existente = next((x for x in cargar_indice() if (x.get('sha256') or x.get('file_hash')) == sha256), None)
    if existente:
        return {'ok': True, 'duplicado': True, 'archivo': existente['archivo'], 'fragmentos_agregados': 0}
    ruta = ruta_archivo_segura(UPLOAD_DIR, nombre, EXTENSIONES_PERMITIDAS)
    if ruta.exists():
        ruta = ruta_archivo_segura(UPLOAD_DIR, f'{ruta.stem}_{sha256[:12]}{ruta.suffix}', EXTENSIONES_PERMITIDAS)
    with ruta.open('xb') as out:
        out.write(contenido)
    return {'ok': True, **indexar_documento_local(ruta, sha256)}


# ============================================================
# BIBLIOTECA
# ============================================================

@app.get(
    "/library"
)
def biblioteca():

    try:

        stats = (
            obtener_estadisticas_indice()
        )

        indexados = {
            documento[
                "archivo"
            ].lower():
                documento

            for documento
            in stats[
                "documentos"
            ]
        }

        biblioteca_items = []

        vistos = set()

        if UPLOAD_DIR.exists():

            for ruta in sorted(
                UPLOAD_DIR.iterdir(),
                key=lambda p:
                    p.name.lower(),
            ):

                if (
                    not ruta.is_file()
                    or
                    ruta.suffix.lower()
                    not in EXTENSIONES_PERMITIDAS
                ):

                    continue

                nombre = ruta.name

                clave = nombre.lower()

                indexado = (
                    indexados.get(
                        clave
                    )
                )

                biblioteca_items.append(
                    {
                        "archivo":
                            nombre,

                        "origen":
                            "local",

                        "fisico":
                            True,

                        "indexado":
                            bool(indexado),

                        "fragmentos":
                            (
                                indexado.get(
                                    "fragmentos",
                                    0,
                                )
                                if indexado
                                else 0
                            ),

                        "caracteres":
                            (
                                indexado.get(
                                    "caracteres",
                                    0,
                                )
                                if indexado
                                else 0
                            ),

                        "size_bytes":
                            ruta.stat().st_size,

                        "drive_file_id":
                            None,
                    }
                )

                vistos.add(
                    clave
                )

        for documento in stats[
            "documentos"
        ]:

            clave = (
                documento[
                    "archivo"
                ]
                .lower()
            )

            if clave in vistos:
                continue

            biblioteca_items.append(
                {
                    "archivo":
                        documento[
                            "archivo"
                        ],

                    "origen":
                        documento.get(
                            "origen",
                            "drive"
                            if documento.get(
                                "drive_file_id"
                            )
                            else "local",
                        ),

                    "fisico":
                        False,

                    "indexado":
                        True,

                    "fragmentos":
                        documento.get(
                            "fragmentos",
                            0,
                        ),

                    "caracteres":
                        documento.get(
                            "caracteres",
                            0,
                        ),

                    "size_bytes":
                        None,

                    "drive_file_id":
                        documento.get(
                            "drive_file_id"
                        ),
                }
            )

        biblioteca_items.sort(
            key=lambda x:
                x[
                    "archivo"
                ].lower()
        )

        return {
            "ok": True,

            "documentos":
                biblioteca_items,

            "documentos_indexados":
                stats[
                    "documentos_totales"
                ],

            "fragmentos_totales":
                stats[
                    "fragmentos_totales"
                ],
        }

    except Exception as error:

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "La operación no pudo completarse. Revisa los datos y el estado de la integración.",
            },
        )


# ============================================================
# RAG API
# ============================================================

@app.get(
    "/rag/files"
)
def listar_documentos_rag():

    try:

        estadisticas = (
            obtener_estadisticas_indice()
        )

        return {
            "ok": True,
            "result":
                estadisticas[
                    "documentos"
                ],
        }

    except Exception as error:

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "La operación no pudo completarse. Revisa los datos y el estado de la integración.",
            },
        )


@app.get(
    "/rag/stats"
)
def estadisticas_rag():

    try:

        return {
            "ok": True,
            **obtener_estadisticas_indice(),
        }

    except Exception as error:

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "La operación no pudo completarse. Revisa los datos y el estado de la integración.",
            },
        )


@app.post(
    "/rag/search"
)
def buscar_rag_api(
    request: RagSearchRequest
):

    try:

        return {
            "ok":
                True,

            "result":
                buscar_en_documentos(
                    consulta=
                        request.consulta,

                    archivo=
                        request.archivo,

                    limite=
                        max(
                            1,
                            min(
                                request.limite,
                                10,
                            ),
                        ),
                ),
        }

    except Exception as error:

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "La operación no pudo completarse. Revisa los datos y el estado de la integración.",
            },
        )


@app.post(
    "/rag/preview"
)
def previsualizar_documento(
    request: PreviewDocumentRequest
):

    items = obtener_items_documento(
        request.archivo
    )

    if not items:

        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error":
                    "Documento no indexado.",
            },
        )

    items.sort(
        key=lambda item:
            int(
                item.get(
                    "fragmento",
                    0,
                )
                or
                0
            )
    )

    limite = max(
        1,
        min(
            request.limite,
            20,
        ),
    )

    return {
        "ok":
            True,

        "archivo":
            request.archivo,

        "fragmentos_totales":
            len(items),

        "result":
            [
                {
                    "fragmento":
                        item.get(
                            "fragmento"
                        ),

                    "texto":
                        (
                            item.get(
                                "texto",
                                "",
                            )
                            or
                            ""
                        )[:3000],

                    "origen":
                        item.get(
                            "origen",
                            "local",
                        ),
                }

                for item
                in items[:limite]
            ],
    }


@app.post(
    "/rag/delete"
)
def borrar_documento_rag(
    request: DeleteDocumentRequest
):

    try:

        return {
            "ok": True,

            "archivo_fisico_eliminado":
                False,

            **eliminar_documento_indice(
                request.archivo
            ),
        }

    except Exception as error:

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "La operación no pudo completarse. Revisa los datos y el estado de la integración.",
            },
        )


@app.post('/rag/reindex')
@indice_transaccion
def reindexar_documento_rag(
    request: ReindexDocumentRequest
):

    archivo = (
        request.archivo
        .strip()
    )

    indice_original = cargar_indice()

    info = obtener_info_documento(
        archivo
    )

    # Rechazar antes de restauración: entradas inválidas no escriben el índice.
    ruta_local = None
    if not (info and info.get("origen") == "drive"):
        try:
            ruta_local = ruta_archivo_segura(
                UPLOAD_DIR, archivo, EXTENSIONES_PERMITIDAS,
            )
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "Nombre de documento local inválido."},
            )

    try:

        if (
            info
            and
            info.get("origen")
            ==
            "drive"
        ):

            file_id = info.get(
                "drive_file_id"
            )

            if not file_id:

                raise RuntimeError(
                    "Documento Drive sin drive_file_id."
                )

            eliminar_documento_indice(
                archivo
            )

            resultado = (
                indexar_archivo_drive(
                    file_id
                )
            )

            return {
                "ok": True,
                "archivo":
                    archivo,
                "origen":
                    "drive",
                "result":
                    resultado,
            }

        if not ruta_local.exists():

            raise FileNotFoundError(
                "No se encontró el archivo local."
            )

        if info:

            eliminar_documento_indice(
                archivo
            )

        contenido = (
            ruta_local.read_bytes()
        )

        sha256 = calcular_sha256(
            contenido
        )

        resultado = (
            indexar_documento_local(
                ruta_local,
                sha256,
            )
        )

        return {
            "ok": True,
            "archivo":
                archivo,
            "origen":
                "local",
            "result":
                resultado,
        }

    except Exception as error:

        guardar_indice(
            indice_original
        )

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "La operación no pudo completarse. Revisa los datos y el estado de la integración.",
                "restaurado":
                    True,
            },
        )


# ============================================================
# GOOGLE DRIVE
# ============================================================

def normalizar_archivo_drive(
    archivo
):

    return {
        "id":
            archivo.get("id"),

        "nombre":
            archivo.get("name"),

        "tipo":
            archivo.get(
                "mimeType"
            ),

        "fecha_modificacion":
            archivo.get(
                "modifiedTime"
            ),

        "enlace":
            archivo.get(
                "webViewLink"
            ),
    }


def listar_drive_backend(
    limite: int = 20,
):

    servicio = (
        obtener_servicio_drive()
    )

    limite = max(
        1,
        min(
            int(limite),
            100,
        ),
    )

    respuesta = (
        servicio.files()
        .list(
            pageSize=
                limite,

            fields=
                (
                    "files("
                    "id,"
                    "name,"
                    "mimeType,"
                    "modifiedTime,"
                    "webViewLink"
                    ")"
                ),

            orderBy=
                "modifiedTime desc",
        )
        .execute()
    )

    return [
        normalizar_archivo_drive(
            archivo
        )
        for archivo
        in respuesta.get(
            "files",
            [],
        )
    ]


def buscar_drive_backend(
    consulta: str,
    limite: int = 20,
):

    consulta = (
        consulta
        or
        ""
    ).strip()

    if not consulta:
        return []

    servicio = (
        obtener_servicio_drive()
    )

    consulta_segura = (
        consulta.replace(
            "'",
            "\\'",
        )
    )

    query = (
        f"name contains "
        f"'{consulta_segura}' "
        f"and trashed = false"
    )

    respuesta = (
        servicio.files()
        .list(
            q=
                query,

            pageSize=
                max(
                    1,
                    min(
                        int(limite),
                        100,
                    ),
                ),

            fields=
                (
                    "files("
                    "id,"
                    "name,"
                    "mimeType,"
                    "modifiedTime,"
                    "webViewLink"
                    ")"
                ),

            orderBy=
                "modifiedTime desc",
        )
        .execute()
    )

    return [
        normalizar_archivo_drive(
            archivo
        )
        for archivo
        in respuesta.get(
            "files",
            [],
        )
    ]


def obtener_archivo_drive_backend(
    file_id: str
):

    servicio = (
        obtener_servicio_drive()
    )

    return (
        servicio.files()
        .get(
            fileId=
                file_id,

            fields=
                (
                    "id,"
                    "name,"
                    "mimeType,"
                    "modifiedTime,"
                    "webViewLink,"
                    "size"
                ),
        )
        .execute()
    )


# ============================================================
# BÚSQUEDA UNIFICADA
# ============================================================

@app.post(
    "/search/unified"
)
def busqueda_unificada(
    request: UnifiedSearchRequest
):

    consulta = (
        request.consulta
        .strip()
    )

    if not consulta:

        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error":
                    "Consulta vacía.",
            },
        )

    try:

        resultados_rag = (
            buscar_en_documentos(
                consulta=
                    consulta,

                limite=
                    max(
                        1,
                        min(
                            request.limite_rag,
                            10,
                        ),
                    ),
            )
        )

        consulta_lower = (
            consulta.lower()
        )

        tokens = [
            token
            for token
            in re.findall(
                r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+",
                consulta_lower,
            )
            if len(token) >= 2
        ]

        resultados_locales = []

        if UPLOAD_DIR.exists():

            for ruta in UPLOAD_DIR.iterdir():

                if (
                    not ruta.is_file()
                    or
                    ruta.suffix.lower()
                    not in EXTENSIONES_PERMITIDAS
                ):

                    continue

                nombre_lower = (
                    ruta.name.lower()
                )

                score = 0

                if (
                    consulta_lower
                    in nombre_lower
                ):

                    score += 10

                score += sum(
                    1
                    for token
                    in tokens
                    if token
                    in nombre_lower
                )

                if score > 0:

                    resultados_locales.append(
                        {
                            "archivo":
                                ruta.name,

                            "origen":
                                "local",

                            "score":
                                score,

                            "size_bytes":
                                ruta.stat().st_size,

                            "indexado":
                                bool(
                                    obtener_info_documento(
                                        ruta.name
                                    )
                                ),
                        }
                    )

        resultados_locales.sort(
            key=lambda x:
                x["score"],
            reverse=True,
        )

        resultados_drive = []

        drive_error = None

        if request.incluir_drive:

            try:

                resultados_drive = (
                    buscar_drive_backend(
                        consulta=
                            consulta,

                        limite=
                            max(
                                1,
                                min(
                                    request.limite_drive,
                                    15,
                                ),
                            ),
                    )
                )

            except Exception as error:

                drive_error = "No se pudo consultar Drive."

        return {
            "ok":
                True,

            "consulta":
                consulta,

            "rag":
                resultados_rag,

            "local":
                resultados_locales[:10],

            "drive":
                resultados_drive,

            "drive_error":
                drive_error,
        }

    except Exception as error:

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "La operación no pudo completarse. Revisa los datos y el estado de la integración.",
            },
        )


# ============================================================
# CALENDAR API
# ============================================================

@app.get(
    "/calendar/events"
)
def api_calendar_eventos(
    limite: int = 10
):

    try:

        return {
            "ok":
                True,

            "result":
                listar_eventos(
                    limite=
                        max(
                            1,
                            min(
                                limite,
                                50,
                            ),
                        )
                ),
        }

    except Exception as error:

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "La operación no pudo completarse. Revisa los datos y el estado de la integración.",
            },
        )


@app.get(
    "/calendar/calendars"
)
def api_calendar_listas():

    try:

        return {
            "ok":
                True,

            "result":
                listar_calendarios(),
        }

    except Exception as error:

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "La operación no pudo completarse. Revisa los datos y el estado de la integración.",
            },
        )


# ============================================================
# HOME
# ============================================================

@app.get("/")
def inicio():

    archivo = (
        BASE_DIR
        /
        "realtime.html"
    )

    if not archivo.exists():

        return JSONResponse(
            status_code=404,
            content={
                "error":
                    "No se encontró realtime.html"
            },
        )

    return FileResponse(
        archivo
    )


# ============================================================
# HEALTH
# ============================================================

@app.get('/health')
def health():
    # Diagnóstico local: nunca inicia OAuth ni efectúa llamadas externas.
    try:
        stats = obtener_estadisticas_indice()
        return {'status': 'ok', 'version': '2.4-rc1', 'rag_documents': stats['documentos_totales'],
                'rag_fragments': stats['fragmentos_totales'], 'drive_mode': 'read_only',
                'integrations': 'not_checked', 'calendar_write_requires_confirmation': True}
    except Exception:
        return JSONResponse(status_code=503, content={'status': 'error', 'error': 'Índice ilegible; requiere recuperación.'})


# ============================================================
# TOKEN REALTIME
# ============================================================

@app.get(
    "/token"
)
def crear_token():

    url = (
        "https://api.openai.com/"
        "v1/realtime/client_secrets"
    )

    headers = {
        "Authorization":
            f"Bearer {OPENAI_API_KEY}",

        "Content-Type":
            "application/json",
    }

    payload = {
        "session": {
            "type":
                "realtime",

            "model":
                "gpt-realtime",

            "instructions":
                (
                    "Eres un asistente personal profesional "
                    "que conversa en español."
                ),

            "audio": {
                "output": {
                    "voice":
                        "marin"
                }
            },
        }
    }

    try:

        respuesta = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30,
        )

        if not respuesta.ok:

            return JSONResponse(
                status_code=
                    respuesta.status_code,

                content={
                    "error":
                        "No se pudo iniciar Realtime."
                },
            )

        return respuesta.json()

    except Exception as error:

        return JSONResponse(
            status_code=500,
            content={
                "error":
                    "La operación no pudo completarse."
            },
        )


# ============================================================
# TOOLS
# ============================================================

@app.post(
    "/tool"
)
def ejecutar_tool(
    request: ToolRequest
):

    nombre = request.name

    argumentos = (
        request.arguments
        or {}
    )

    print("[TOOL]", nombre)

    try:

        # ====================================================
        # MEMORIA
        # ====================================================

        if nombre == "recordar":

            contenido = (
                argumentos.get(
                    "contenido",
                    "",
                )
            )

            if not contenido:

                return JSONResponse(
                    status_code=400,
                    content={
                        "ok": False,
                        "error":
                            "No se recibió contenido.",
                    },
                )

            resultado = guardar_memoria(
                categoria=
                    argumentos.get(
                        "categoria",
                        "general",
                    ),

                clave=
                    argumentos.get(
                        "clave",
                        "memoria",
                    ),

                contenido=
                    contenido,

                importancia=
                    argumentos.get(
                        "importancia",
                        3,
                    ),
            )

            return {
                "ok": True,
                "result": resultado,
            }


        if nombre == "buscar_memoria":

            memorias = buscar_memorias(
                argumentos.get(
                    "consulta",
                    "",
                ),
                argumentos.get(
                    "limite",
                    10,
                ),
            )

            return {
                "ok":
                    True,

                "result":
                    [
                        {
                            "id":
                                memoria[
                                    "id"
                                ],

                            "categoria":
                                memoria[
                                    "categoria"
                                ],

                            "clave":
                                memoria[
                                    "clave"
                                ],

                            "contenido":
                                memoria[
                                    "contenido"
                                ],

                            "importancia":
                                memoria[
                                    "importancia"
                                ],
                        }

                        for memoria
                        in memorias
                    ],
            }


        if nombre == "ver_memorias":

            categoria = argumentos.get(
                "categoria"
            )

            if categoria == "":
                categoria = None

            memorias = listar_memorias(
                limite=
                    argumentos.get(
                        "limite",
                        20,
                    ),

                categoria=
                    categoria,
            )

            return {
                "ok":
                    True,

                "result":
                    [
                        {
                            "id":
                                memoria[
                                    "id"
                                ],

                            "categoria":
                                memoria[
                                    "categoria"
                                ],

                            "clave":
                                memoria[
                                    "clave"
                                ],

                            "contenido":
                                memoria[
                                    "contenido"
                                ],

                            "importancia":
                                memoria[
                                    "importancia"
                                ],
                        }

                        for memoria
                        in memorias
                    ],
            }


        # ====================================================
        # RAG
        # ====================================================

        if nombre == "buscar_documentos":

            return {
                "ok":
                    True,

                "result":
                    buscar_en_documentos(
                        consulta=
                            argumentos.get(
                                "consulta",
                                "",
                            ),

                        limite=
                            max(
                                1,
                                min(
                                    int(
                                        argumentos.get(
                                            "limite",
                                            6,
                                        )
                                    ),
                                    8,
                                ),
                            ),

                        archivo=
                            argumentos.get(
                                "archivo"
                            ),
                    ),
            }


        # ====================================================
        # DRIVE
        # ====================================================

        if nombre in {"listar_carpetas_drive", "listar_contenido_carpeta_drive"}:
            carpeta_id = None
            if nombre == "listar_contenido_carpeta_drive":
                carpeta_id = argumentos.get("carpeta_id", "")
                if not isinstance(carpeta_id, str) or not carpeta_id.strip():
                    return JSONResponse(status_code=400, content={
                        "ok": False, "error": "Se requiere el ID de la carpeta."})
            return {"ok": True, "result": consultar_carpetas(
                obtener_servicio_drive(),
                nombre=argumentos.get("nombre", ""), carpeta_id=carpeta_id,
                limite=argumentos.get("limite", 20), pagina=argumentos.get("pagina"),
            )}

        if nombre == "listar_drive":

            return {
                "ok":
                    True,

                "result":
                    listar_drive_backend(
                        limite=
                            argumentos.get(
                                "limite",
                                20,
                            )
                    ),
            }


        if nombre == "buscar_drive":

            return {
                "ok":
                    True,

                "result":
                    buscar_drive_backend(
                        consulta=
                            argumentos.get(
                                "consulta",
                                "",
                            ),

                        limite=
                            argumentos.get(
                                "limite",
                                20,
                            ),
                    ),
            }


        if nombre == "obtener_archivo_drive":

            file_id = argumentos.get(
                "file_id",
                "",
            )

            if not file_id:

                return JSONResponse(
                    status_code=400,
                    content={
                        "ok": False,
                        "error":
                            "Falta file_id.",
                    },
                )

            return {
                "ok":
                    True,

                "result":
                    obtener_archivo_drive_backend(
                        file_id
                    ),
            }


        if nombre == "indexar_drive":
            return JSONResponse(status_code=403, content={
                "ok": False, "error": "La indexación requiere confirmación en la interfaz."})


        # ====================================================
        # GOOGLE CALENDAR
        # ====================================================

        if nombre == "listar_eventos_calendar":

            return {
                "ok":
                    True,

                "result":
                    listar_eventos(
                        limite=
                            argumentos.get(
                                "limite",
                                10,
                            )
                    ),
            }


        if nombre == "buscar_eventos_calendar":

            return {
                "ok":
                    True,

                "result":
                    buscar_eventos(
                        consulta=
                            argumentos.get(
                                "consulta",
                                "",
                            ),

                        limite=
                            argumentos.get(
                                "limite",
                                20,
                            ),
                    ),
            }


        if nombre == "eventos_entre_calendar":

            return {
                "ok":
                    True,

                "result":
                    eventos_entre(
                        inicio_iso=
                            argumentos.get(
                                "inicio_iso"
                            ),

                        fin_iso=
                            argumentos.get(
                                "fin_iso"
                            ),
                    ),
            }


        if nombre == "consultar_disponibilidad_calendar":

            return {
                "ok":
                    True,

                "result":
                    consultar_disponibilidad(
                        inicio_iso=
                            argumentos.get(
                                "inicio_iso"
                            ),

                        fin_iso=
                            argumentos.get(
                                "fin_iso"
                            ),
                    ),
            }


        if nombre == "crear_evento_calendar":
            return JSONResponse(status_code=403, content={"ok": False,
                "requiere_confirmacion": True,
                "error": "Crea una propuesta y confírmala desde la interfaz."})

        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error":
                    (
                        "Herramienta desconocida: "
                        +
                        nombre
                    ),
            },
        )

    except Exception as error:

        print(
            "[TOOL ERROR]",
            type(error).__name__,
        )

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error":
                    "La operación no pudo completarse.",

                "tipo":
                    type(error).__name__,
            },
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print(
        "Mi Agente IA V2.3"
    )

    print(
        "python -m uvicorn realtime_server:app --reload --port 8000"
    )
