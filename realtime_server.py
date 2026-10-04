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
    BASE_DIR
    /
    "indice.json"
)

UPLOAD_DIR = (
    BASE_DIR
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
    title="Mi Agente IA Multimodal V2.3"
)


# ============================================================
# BASES DE DATOS
# ============================================================

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
                fila.get(
                    "fecha_creacion"
                ),

            "fecha_actualizacion":
                fila.get(
                    "fecha_actualizacion"
                ),
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
                "error": str(error),
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
                "error": str(error),
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
                "error": str(error),
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
                "error": str(error),
            },
        )


# ============================================================
# ÍNDICE
# ============================================================

def cargar_indice():

    if not INDICE_PATH.exists():
        return []

    try:

        with open(
            INDICE_PATH,
            "r",
            encoding="utf-8",
        ) as archivo:

            datos = json.load(
                archivo
            )

        if isinstance(
            datos,
            list,
        ):

            return datos

    except Exception as error:

        print(
            "[INDICE ERROR]",
            error,
        )

    return []


def guardar_indice(
    indice
):

    temporal = (
        INDICE_PATH.with_suffix(
            ".tmp"
        )
    )

    with open(
        temporal,
        "w",
        encoding="utf-8",
    ) as archivo:

        json.dump(
            indice,
            archivo,
            ensure_ascii=False,
        )

    temporal.replace(
        INDICE_PATH
    )


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

def extraer_txt(
    ruta: Path
):

    try:

        return ruta.read_text(
            encoding="utf-8"
        )

    except UnicodeDecodeError:

        return ruta.read_text(
            encoding="latin-1"
        )


# ============================================================
# OCR
# ============================================================

def pagina_pdf_a_data_url(
    pagina,
    zoom: float = 2.0,
):

    matriz = fitz.Matrix(
        zoom,
        zoom,
    )

    pixmap = pagina.get_pixmap(
        matrix=matriz,
        alpha=False,
    )

    png_bytes = pixmap.tobytes(
        "png"
    )

    base64_png = (
        base64
        .b64encode(
            png_bytes
        )
        .decode(
            "utf-8"
        )
    )

    return (
        "data:image/png;base64,"
        +
        base64_png
    )


def ocr_imagen_openai(
    image_data_url: str,
    numero_pagina: int,
):

    print(
        f"[OCR] Página {numero_pagina}"
    )

    respuesta = (
        client.responses.create(
            model=
                MODELO_OCR,

            input=[
                {
                    "role":
                        "user",

                    "content": [
                        {
                            "type":
                                "input_text",

                            "text":
                                (
                                    "Transcribe fielmente todo el texto "
                                    "legible de esta página. "
                                    "No resumas, no expliques y no inventes. "
                                    "Mantén títulos, listas, fechas, números "
                                    "y tablas de manera legible. "
                                    "Devuelve solamente la transcripción."
                                ),
                        },
                        {
                            "type":
                                "input_image",

                            "image_url":
                                image_data_url,

                            "detail":
                                "high",
                        },
                    ],
                }
            ],
        )
    )

    return (
        respuesta.output_text
        or ""
    ).strip()


def extraer_pdf_con_ocr(
    ruta: Path
):

    documento = fitz.open(
        str(ruta)
    )

    textos = []

    try:

        for numero_pagina, pagina in enumerate(
            documento,
            start=1,
        ):

            imagen = (
                pagina_pdf_a_data_url(
                    pagina
                )
            )

            texto = (
                ocr_imagen_openai(
                    imagen,
                    numero_pagina,
                )
            )

            if texto:

                textos.append(
                    (
                        f"[Página {numero_pagina}]\n"
                        f"{texto}"
                    )
                )

    finally:

        documento.close()

    texto_total = (
        "\n\n"
        .join(
            textos
        )
        .strip()
    )

    if not texto_total:

        raise ValueError(
            "OCR completado pero no encontró texto."
        )

    return texto_total


# ============================================================
# PDF
# ============================================================

def extraer_pdf(
    ruta: Path
):

    documento = None

    textos = []

    try:

        documento = fitz.open(
            str(ruta)
        )

        for pagina in documento:

            texto = (
                pagina.get_text(
                    "text"
                )
                or ""
            ).strip()

            if texto:

                textos.append(
                    texto
                )

        texto_total = (
            "\n\n"
            .join(
                textos
            )
            .strip()
        )

        if texto_total:
            return texto_total

    except Exception as error:

        print(
            "[PDF PyMuPDF]",
            error,
        )

    finally:

        if documento:

            try:
                documento.close()
            except Exception:
                pass

    textos = []

    try:

        lector = PdfReader(
            str(ruta)
        )

        for pagina in lector.pages:

            texto = (
                pagina.extract_text()
                or ""
            ).strip()

            if texto:

                textos.append(
                    texto
                )

        texto_total = (
            "\n\n"
            .join(
                textos
            )
            .strip()
        )

        if texto_total:
            return texto_total

    except Exception as error:

        print(
            "[PDF pypdf]",
            error,
        )

    return (
        extraer_pdf_con_ocr(
            ruta
        )
    )


# ============================================================
# DOCX
# ============================================================

def extraer_docx(
    ruta: Path
):

    documento = Document(
        str(ruta)
    )

    textos = []

    for parrafo in documento.paragraphs:

        texto = (
            parrafo.text
            or ""
        ).strip()

        if texto:

            textos.append(
                texto
            )

    for tabla in documento.tables:

        for fila in tabla.rows:

            celdas = []

            for celda in fila.cells:

                contenido = (
                    celda.text
                    or ""
                ).strip()

                if contenido:

                    celdas.append(
                        contenido
                    )

            if celdas:

                textos.append(
                    " | ".join(
                        celdas
                    )
                )

    return "\n".join(
        textos
    )


def extraer_texto_documento(
    ruta: Path
):

    extension = (
        ruta.suffix
        .lower()
    )

    if extension == ".txt":
        return extraer_txt(
            ruta
        )

    if extension == ".pdf":
        return extraer_pdf(
            ruta
        )

    if extension == ".docx":
        return extraer_docx(
            ruta
        )

    raise ValueError(
        f"Extensión no soportada: {extension}"
    )


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

def indexar_documento_local(
    ruta: Path,
    sha256: str,
):

    indice = cargar_indice()

    for item in indice:

        if (
            item.get("sha256")
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

@app.post(
    "/upload-rag"
)
async def upload_rag(
    file: UploadFile = File(...)
):

    try:

        nombre = limpiar_nombre_archivo(
            file.filename
            or
            "documento"
        )

        extension = (
            Path(nombre)
            .suffix
            .lower()
        )

        if extension not in EXTENSIONES_PERMITIDAS:

            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "error":
                        "Solo PDF, DOCX y TXT.",
                },
            )

        contenido = await file.read()

        if not contenido:

            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "error":
                        "Archivo vacío.",
                },
            )

        if (
            len(contenido)
            >
            MAX_ARCHIVO_BYTES
        ):

            return JSONResponse(
                status_code=413,
                content={
                    "ok": False,
                    "error":
                        "El archivo supera 25 MB.",
                },
            )

        sha256 = calcular_sha256(
            contenido
        )

        indice = cargar_indice()

        existente = next(
            (
                item
                for item
                in indice
                if (
                    item.get(
                        "sha256"
                    )
                    ==
                    sha256
                )
            ),
            None,
        )

        if existente:

            return {
                "ok": True,
                "duplicado": True,
                "archivo":
                    existente.get(
                        "archivo",
                        nombre,
                    ),
                "fragmentos_agregados":
                    0,
            }

        ruta = (
            UPLOAD_DIR
            /
            nombre
        )

        if ruta.exists():

            ruta = (
                UPLOAD_DIR
                /
                (
                    f"{ruta.stem}_"
                    f"{sha256[:8]}"
                    f"{ruta.suffix}"
                )
            )

        ruta.write_bytes(
            contenido
        )

        resultado = (
            indexar_documento_local(
                ruta,
                sha256,
            )
        )

        return {
            "ok": True,
            **resultado,
        }

    except Exception as error:

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": str(error),
            },
        )


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
                "error": str(error),
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
                "error": str(error),
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
                "error": str(error),
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
                "error": str(error),
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
                "error": str(error),
            },
        )


@app.post(
    "/rag/reindex"
)
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

    ruta_local = (
        UPLOAD_DIR
        /
        archivo
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
                "error": str(error),
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

                drive_error = str(
                    error
                )

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
                "error": str(error),
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
                "error": str(error),
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
                "error": str(error),
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

@app.get(
    "/health"
)
def health():

    drive_ok = False

    calendar_ok = False

    try:

        obtener_servicio_drive()

        drive_ok = True

    except Exception:
        pass

    try:

        obtener_servicio_calendar()

        calendar_ok = True

    except Exception:
        pass

    stats = (
        obtener_estadisticas_indice()
    )

    return {
        "status":
            "ok",

        "version":
            "multimodal-rag-2.3",

        "realtime":
            True,

        "memory":
            True,

        "rag":
            True,

        "rag_version":
            "2.3",

        "rag_fragments":
            stats[
                "fragmentos_totales"
            ],

        "rag_documents":
            stats[
                "documentos_totales"
            ],

        "ocr":
            True,

        "drive":
            drive_ok,

        "drive_mode":
            "read_only",

        "calendar":
            calendar_ok,

        "calendar_read":
            True,

        "calendar_write":
            True,

        "calendar_write_requires_confirmation":
            True,

        "document_library":
            True,

        "document_preview":
            True,

        "unified_search":
            True,
    }


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
                        respuesta.text
                },
            )

        return respuesta.json()

    except Exception as error:

        return JSONResponse(
            status_code=500,
            content={
                "error":
                    str(error)
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

    print(
        "[TOOL]",
        nombre,
        argumentos,
    )

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

            if (
                argumentos.get(
                    "usuario_autorizo_indexacion",
                    False,
                )
                is not True
            ):

                return JSONResponse(
                    status_code=403,
                    content={
                        "ok":
                            False,

                        "error":
                            (
                                "La indexación requiere "
                                "autorización explícita."
                            ),
                    },
                )

            file_id = argumentos.get(
                "file_id",
                "",
            )

            antes = (
                contar_fragmentos_indice()
            )

            resultado = (
                indexar_archivo_drive(
                    file_id
                )
            )

            despues = (
                contar_fragmentos_indice()
            )

            return {
                "ok":
                    True,

                "fragmentos_agregados":
                    despues - antes,

                "result":
                    resultado,
            }


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

            autorizado = argumentos.get(
                "usuario_autorizo_creacion",
                False,
            )

            if autorizado is not True:

                return JSONResponse(
                    status_code=403,
                    content={
                        "ok":
                            False,

                        "requiere_confirmacion":
                            True,

                        "error":
                            (
                                "La creación del evento requiere "
                                "confirmación explícita del usuario."
                            ),
                    },
                )

            titulo = argumentos.get(
                "titulo",
                "",
            ).strip()

            inicio_iso = argumentos.get(
                "inicio_iso",
                "",
            ).strip()

            fin_iso = argumentos.get(
                "fin_iso",
                "",
            ).strip()

            if (
                not titulo
                or
                not inicio_iso
                or
                not fin_iso
            ):

                return JSONResponse(
                    status_code=400,
                    content={
                        "ok": False,
                        "error":
                            "Faltan datos del evento.",
                    },
                )

            evento = crear_evento(
                titulo=
                    titulo,

                inicio_iso=
                    inicio_iso,

                fin_iso=
                    fin_iso,

                descripcion=
                    argumentos.get(
                        "descripcion",
                        "",
                    ),

                ubicacion=
                    argumentos.get(
                        "ubicacion",
                        "",
                    ),

                zona_horaria=
                    argumentos.get(
                        "zona_horaria",
                        "America/Santiago",
                    ),
            )

            return {
                "ok":
                    True,

                "result":
                    evento,
            }


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
            error,
        )

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error":
                    str(error),

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