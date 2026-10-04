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


# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()

OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY"
)

if not OPENAI_API_KEY:

    raise RuntimeError(
        "No se encontró OPENAI_API_KEY en el archivo .env"
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
    api_key=
        OPENAI_API_KEY
)


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title=
        "Mi Agente IA Multimodal RAG 2.0"
)


# ============================================================
# BASES DE DATOS
# ============================================================

inicializar_db()

inicializar_memoria_largo_plazo()


# ============================================================
# MODELOS
# ============================================================

class ToolRequest(
    BaseModel
):

    name: str
    arguments: dict


class MessageRequest(
    BaseModel
):

    conversacion_id: int
    role: str
    content: str


class DeleteDocumentRequest(
    BaseModel
):

    archivo: str


# ============================================================
# UTILIDADES
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
                fila.get(
                    "id"
                ),

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

        "id":
            None,

        "titulo":
            str(fila),

        "fecha_creacion":
            None,

        "fecha_actualizacion":
            None,
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
            fila.get(
                "role"
            )
            or
            fila.get(
                "rol"
            )
            or
            fila.get(
                "tipo"
            )
        )


        content = (
            fila.get(
                "content"
            )
            or
            fila.get(
                "contenido"
            )
            or
            fila.get(
                "mensaje"
            )
            or
            ""
        )


        return {

            "id":
                fila.get(
                    "id"
                ),

            "role":
                role,

            "content":
                content,

            "fecha":
                (
                    fila.get(
                        "fecha"
                    )
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

        "id":
            None,

        "role":
            None,

        "content":
            str(fila),

        "fecha":
            None,
    }


# ============================================================
# CONVERSACIONES
# ============================================================

@app.get(
    "/conversations"
)
def api_listar_conversaciones():

    try:

        filas = (
            listar_conversaciones()
        )


        conversaciones = []


        for fila in filas or []:

            item = (
                normalizar_conversacion(
                    fila
                )
            )


            if (
                item
                and
                item.get(
                    "id"
                )
                is not None
            ):

                conversaciones.append(
                    item
                )


        return {

            "ok":
                True,

            "result":
                conversaciones,
        }


    except Exception as error:

        return JSONResponse(
            status_code=
                500,

            content={

                "ok":
                    False,

                "error":
                    str(error),
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

            item = (
                normalizar_mensaje(
                    fila
                )
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

            "ok":
                True,

            "conversacion":
                conversacion,

            "mensajes":
                mensajes,
        }


    except Exception as error:

        return JSONResponse(
            status_code=
                500,

            content={

                "ok":
                    False,

                "error":
                    str(error),
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

            "ok":
                True,

            "conversacion_id":
                conversacion_id,
        }


    except Exception as error:

        return JSONResponse(
            status_code=
                500,

            content={

                "ok":
                    False,

                "error":
                    str(error),
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
                status_code=
                    400,

                content={

                    "ok":
                        False,

                    "error":
                        "Role inválido.",
                },
            )


        if not content:

            return {

                "ok":
                    True,

                "guardado":
                    False,
            }


        agregar_mensaje(
            request.conversacion_id,
            role,
            content,
        )


        cantidad = (
            contar_mensajes(
                request.conversacion_id
            )
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

            "ok":
                True,

            "guardado":
                True,

            "mensajes":
                cantidad,
        }


    except Exception as error:

        return JSONResponse(
            status_code=
                500,

            content={

                "ok":
                    False,

                "error":
                    str(error),
            },
        )


# ============================================================
# ÍNDICE BASE
# ============================================================

def cargar_indice():

    if not INDICE_PATH.exists():
        return []


    try:

        with open(
            INDICE_PATH,
            "r",
            encoding=
                "utf-8",
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
            "[ERROR INDICE]",
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
        encoding=
            "utf-8",
    ) as archivo:

        json.dump(
            indice,
            archivo,
            ensure_ascii=
                False,
        )


    temporal.replace(
        INDICE_PATH
    )


def contar_fragmentos_indice():

    return len(
        cargar_indice()
    )


# ============================================================
# RAG 2.0
# ============================================================

def buscar_en_documentos(
    consulta: str,
    limite: int = 6,
    drive_file_id: str = None,
    archivo: str = None,
):

    return (
        buscar_documentos_hibrido(

            consulta=
                consulta,

            limite=
                limite,

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


# ============================================================
# ARCHIVOS
# ============================================================

def limpiar_nombre_archivo(
    nombre: str
):

    nombre = (
        Path(
            nombre
        ).name
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
            encoding=
                "utf-8"
        )


    except UnicodeDecodeError:

        return ruta.read_text(
            encoding=
                "latin-1"
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
        matrix=
            matriz,

        alpha=
            False,
    )


    png_bytes = (
        pixmap.tobytes(
            "png"
        )
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
        f"[OCR] Procesando página {numero_pagina}..."
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
                                    "legible visible en esta página. "
                                    "No resumas. "
                                    "No expliques. "
                                    "No interpretes. "
                                    "Conserva títulos, párrafos, listas, "
                                    "fechas, números y tablas. "
                                    "Si algo no es legible, no lo inventes. "
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


    texto = (
        respuesta.output_text
        or
        ""
    ).strip()


    print(
        f"[OCR] Página {numero_pagina}: "
        f"{len(texto)} caracteres"
    )


    return texto


def extraer_pdf_con_ocr(
    ruta: Path
):

    documento = fitz.open(
        str(ruta)
    )


    textos = []


    total_paginas = len(
        documento
    )


    print(
        f"[OCR] Documento escaneado: "
        f"{total_paginas} páginas"
    )


    try:

        for numero_pagina, pagina in enumerate(
            documento,
            start=
                1,
        ):

            image_data_url = (
                pagina_pdf_a_data_url(
                    pagina
                )
            )


            texto = (
                ocr_imagen_openai(
                    image_data_url,
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
            "OCR completado, pero no fue posible reconocer texto."
        )


    return texto_total


# ============================================================
# PDF
# ============================================================

def extraer_pdf(
    ruta: Path
):

    textos = []

    documento = None


    try:

        documento = fitz.open(
            str(ruta)
        )


        print(
            f"[PDF] PyMuPDF analizando "
            f"{ruta.name}"
        )


        for numero_pagina, pagina in enumerate(
            documento,
            start=
                1,
        ):

            texto = (
                pagina.get_text(
                    "text"
                )
                or
                ""
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

            print(
                "[PDF] Texto extraído con PyMuPDF"
            )

            return texto_total


    except Exception as error:

        print(
            "[PDF] PyMuPDF error:",
            error,
        )


    finally:

        if documento is not None:

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
                or
                ""
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

            print(
                "[PDF] Texto extraído con pypdf"
            )

            return texto_total


    except Exception as error:

        print(
            "[PDF] pypdf error:",
            error,
        )


    print(
        "[PDF] Activando OCR automático..."
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
            or
            ""
        ).strip()


        if texto:

            textos.append(
                texto
            )


    for tabla in documento.tables:

        for fila in tabla.rows:

            celdas = [

                (
                    celda.text
                    or
                    ""
                ).strip()

                for celda
                in fila.cells
            ]


            contenido_fila = (
                " | "
                .join(
                    celda
                    for celda
                    in celdas
                    if celda
                )
            )


            if contenido_fila:

                textos.append(
                    contenido_fila
                )


    return "\n".join(
        textos
    )


# ============================================================
# EXTRACTOR
# ============================================================

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
    lote=
        50,
):

    embeddings = []


    for inicio in range(
        0,
        len(fragmentos),
        lote,
    ):

        bloque = (
            fragmentos[
                inicio:
                inicio + lote
            ]
        )


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
# INDEXAR LOCAL
# ============================================================

def indexar_documento_local(
    ruta: Path,
    sha256: str,
):

    indice = cargar_indice()


    for item in indice:

        if (
            item.get(
                "sha256"
            )
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


    fragmentos = dividir_texto(
        texto
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


    if (
        len(embeddings)
        !=
        len(fragmentos)
    ):

        raise RuntimeError(
            "Error generando embeddings."
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
        start=
            1,
    ):

        nuevos_items.append({

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
        })


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
            len(
                texto
            ),
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

    etapa = "recepcion"


    try:

        nombre = limpiar_nombre_archivo(
            file.filename
            or
            "documento"
        )


        extension = (
            Path(
                nombre
            )
            .suffix
            .lower()
        )


        if (
            extension
            not in
            EXTENSIONES_PERMITIDAS
        ):

            return JSONResponse(
                status_code=
                    400,

                content={

                    "ok":
                        False,

                    "etapa":
                        "validacion",

                    "error":
                        "Solo PDF, DOCX y TXT.",
                },
            )


        etapa = "lectura"


        contenido = await file.read()


        if not contenido:

            return JSONResponse(
                status_code=
                    400,

                content={

                    "ok":
                        False,

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
                status_code=
                    413,

                content={

                    "ok":
                        False,

                    "error":
                        "Archivo supera 25 MB.",
                },
            )


        etapa = "hash"


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

                "ok":
                    True,

                "duplicado":
                    True,

                "archivo":
                    existente.get(
                        "archivo",
                        nombre,
                    ),

                "fragmentos_agregados":
                    0,

                "message":
                    "Documento ya indexado.",
            }


        etapa = "guardado"


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


        etapa = (
            "extraccion_indexacion"
        )


        resultado = (
            indexar_documento_local(
                ruta,
                sha256,
            )
        )


        return {

            "ok":
                True,

            "etapa":
                "completado",

            "message":
                "Documento indexado correctamente.",

            **resultado,
        }


    except Exception as error:

        print(
            "[UPLOAD ERROR]",
            etapa,
            type(error).__name__,
            error,
        )


        return JSONResponse(
            status_code=
                500,

            content={

                "ok":
                    False,

                "etapa":
                    etapa,

                "error":
                    str(error),

                "tipo":
                    type(error).__name__,
            },
        )


# ============================================================
# RAG FILES
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

            "ok":
                True,

            "result":
                estadisticas[
                    "documentos"
                ],
        }


    except Exception as error:

        return JSONResponse(
            status_code=
                500,

            content={

                "ok":
                    False,

                "error":
                    str(error),
            },
        )


# ============================================================
# RAG STATS
# ============================================================

@app.get(
    "/rag/stats"
)
def estadisticas_rag():

    try:

        return {

            "ok":
                True,

            **obtener_estadisticas_indice(),
        }


    except Exception as error:

        return JSONResponse(
            status_code=
                500,

            content={

                "ok":
                    False,

                "error":
                    str(error),
            },
        )


# ============================================================
# RAG DELETE
# ============================================================

@app.post(
    "/rag/delete"
)
def borrar_documento_rag(
    request: DeleteDocumentRequest
):

    try:

        resultado = (
            eliminar_documento_indice(
                request.archivo
            )
        )


        return {

            "ok":
                True,

            **resultado,
        }


    except Exception as error:

        return JSONResponse(
            status_code=
                500,

            content={

                "ok":
                    False,

                "error":
                    str(error),
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
            archivo.get(
                "id"
            ),

        "nombre":
            archivo.get(
                "name"
            ),

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
            int(
                limite
            ),
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


    limite = max(
        1,
        min(
            int(
                limite
            ),
            100,
        ),
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
# DRIVE → RAG
# ============================================================

def analizar_archivo_drive_backend(
    consulta_archivo: str,
    pregunta: str,
    usuario_autorizo_indexacion: bool,
    limite_resultados: int = 5,
):

    if (
        usuario_autorizo_indexacion
        is not True
    ):

        return {

            "ok":
                False,

            "requiere_confirmacion":
                True,

            "message":
                "La indexación requiere autorización explícita.",
        }


    archivos = (
        buscar_drive_backend(

            consulta=
                consulta_archivo,

            limite=
                10,
        )
    )


    if not archivos:

        return {

            "ok":
                True,

            "estado":
                "sin_resultados",

            "result":
                [],
        }


    if len(
        archivos
    ) > 1:

        return {

            "ok":
                True,

            "estado":
                "seleccion_requerida",

            "result":
                archivos,
        }


    archivo = archivos[0]


    file_id = archivo[
        "id"
    ]


    antes = (
        contar_fragmentos_indice()
    )


    resultado_indexacion = (
        indexar_archivo_drive(
            file_id
        )
    )


    despues = (
        contar_fragmentos_indice()
    )


    resultados_rag = (
        buscar_en_documentos(

            consulta=
                pregunta,

            limite=
                limite_resultados,

            drive_file_id=
                file_id,
        )
    )


    return {

        "ok":
            True,

        "estado":
            "analizado",

        "archivo":
            archivo,

        "indexacion": {

            "fragmentos_antes":
                antes,

            "fragmentos_despues":
                despues,

            "fragmentos_agregados":
                despues
                -
                antes,

            "resultado":
                resultado_indexacion,
        },

        "pregunta":
            pregunta,

        "result":
            resultados_rag,
    }


# ============================================================
# WEB
# ============================================================

@app.get(
    "/"
)
def inicio():

    archivo = (
        BASE_DIR
        /
        "realtime.html"
    )


    if not archivo.exists():

        return JSONResponse(
            status_code=
                404,

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


    try:

        obtener_servicio_drive()

        drive_ok = True


    except Exception as error:

        print(
            "[DRIVE HEALTH]",
            error,
        )


    return {

        "status":
            "ok",

        "version":
            "multimodal-rag-2.0",

        "realtime":
            True,

        "multimodal_ui":
            True,

        "fixed_chat_scroll":
            True,

        "text_chat":
            True,

        "file_upload":
            True,

        "pdf_pymupdf":
            True,

        "pdf_pypdf_fallback":
            True,

        "ocr":
            True,

        "ocr_mode":
            "automatic_visual_fallback",

        "ocr_model":
            MODELO_OCR,

        "local_rag_upload":
            True,

        "conversation_history":
            True,

        "conversation_resume":
            True,

        "memory":
            True,

        "tools":
            True,

        "rag":
            True,

        "rag_version":
            "2.0",

        "rag_search":
            "hybrid_semantic_lexical",

        "rag_diversification":
            True,

        "rag_smart_chunking":
            True,

        "rag_fragments":
            contar_fragmentos_indice(),

        "drive":
            drive_ok,

        "drive_mode":
            "read_only",

        "drive_auto_analysis":
            True,

        "index_requires_explicit_request":
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
            headers=
                headers,
            json=
                payload,
            timeout=
                30,
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
            status_code=
                500,

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
        or
        {}
    )


    try:

        if nombre == "recordar":

            contenido = (
                argumentos.get(
                    "contenido",
                    "",
                )
            )


            if not contenido:

                return JSONResponse(
                    status_code=
                        400,

                    content={

                        "ok":
                            False,

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

                "ok":
                    True,

                "result":
                    resultado,
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


            resultados = []


            for memoria in memorias:

                resultados.append({

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
                })


            return {

                "ok":
                    True,

                "result":
                    resultados,
            }


        if nombre == "ver_memorias":

            categoria = (
                argumentos.get(
                    "categoria"
                )
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


            resultados = []


            for memoria in memorias:

                resultados.append({

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
                })


            return {

                "ok":
                    True,

                "result":
                    resultados,
            }


        if nombre == "buscar_documentos":

            limite = max(
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
            )


            resultados = (
                buscar_en_documentos(

                    consulta=
                        argumentos.get(
                            "consulta",
                            "",
                        ),

                    limite=
                        limite,

                    archivo=
                        argumentos.get(
                            "archivo"
                        ),
                )
            )


            return {

                "ok":
                    True,

                "result":
                    resultados,
            }


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

            file_id = (
                argumentos.get(
                    "file_id",
                    "",
                )
            )


            if not file_id:

                return JSONResponse(
                    status_code=
                        400,

                    content={

                        "ok":
                            False,

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
                    status_code=
                        403,

                    content={

                        "ok":
                            False,

                        "error":
                            "La indexación requiere autorización explícita.",
                    },
                )


            file_id = (
                argumentos.get(
                    "file_id",
                    "",
                )
            )


            if not file_id:

                return JSONResponse(
                    status_code=
                        400,

                    content={

                        "ok":
                            False,

                        "error":
                            "Falta file_id.",
                    },
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

                "fragmentos_antes":
                    antes,

                "fragmentos_despues":
                    despues,

                "fragmentos_agregados":
                    despues
                    -
                    antes,

                "result":
                    resultado,
            }


        if nombre == "analizar_archivo_drive":

            return (
                analizar_archivo_drive_backend(

                    consulta_archivo=
                        argumentos.get(
                            "consulta_archivo",
                            "",
                        ),

                    pregunta=
                        argumentos.get(
                            "pregunta",
                            "",
                        ),

                    usuario_autorizo_indexacion=
                        argumentos.get(
                            "usuario_autorizo_indexacion",
                            False,
                        ),

                    limite_resultados=
                        argumentos.get(
                            "limite",
                            5,
                        ),
                )
            )


        return JSONResponse(
            status_code=
                400,

            content={

                "ok":
                    False,

                "error":
                    f"Herramienta desconocida: {nombre}",
            },
        )


    except Exception as error:

        print(
            "[ERROR TOOL]",
            type(error).__name__,
            error,
        )


        return JSONResponse(
            status_code=
                500,

            content={

                "ok":
                    False,

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
        "Mi Agente IA - RAG 2.0"
    )

    print(
        "Ejecuta:"
    )

    print(
        "python -m uvicorn realtime_server:app --reload --port 8000"
    )