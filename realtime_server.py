import json
import os
from pathlib import Path

import numpy as np
import requests

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from openai import OpenAI
from pydantic import BaseModel

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


BASE_DIR = Path(__file__).resolve().parent

INDICE_PATH = (
    BASE_DIR / "indice.json"
)

MODELO_EMBEDDING = (
    "text-embedding-3-small"
)


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
    title="Mi Agente IA - Realtime"
)


# ============================================================
# BASES DE DATOS
# ============================================================

inicializar_db()
inicializar_memoria_largo_plazo()


# ============================================================
# MODELOS API
# ============================================================

class ToolRequest(BaseModel):
    name: str
    arguments: dict


class MessageRequest(BaseModel):
    conversacion_id: int
    role: str
    content: str


# ============================================================
# HELPERS DE NORMALIZACIÓN
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
                clave: fila[clave]
                for clave in fila.keys()
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
            or fila.get("rol")
            or fila.get("tipo")
        )

        content = (
            fila.get("content")
            or fila.get("contenido")
            or fila.get("mensaje")
            or ""
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
                fila.get(
                    "fecha"
                )
                or fila.get(
                    "fecha_creacion"
                )
                or fila.get(
                    "created_at"
                ),
        }


    if isinstance(
        fila,
        (list, tuple),
    ):

        # Estructura esperada habitual:
        # id, conversacion_id, role, content, fecha

        if len(fila) >= 5:

            return {
                "id": fila[0],
                "role": fila[2],
                "content": fila[3],
                "fecha": fila[4],
            }

        if len(fila) >= 3:

            return {
                "id": fila[0],
                "role": fila[1],
                "content": fila[2],
                "fecha":
                    fila[3]
                    if len(fila) > 3
                    else None,
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

@app.get("/conversations")
def api_listar_conversaciones():

    try:

        conversaciones_raw = (
            listar_conversaciones()
        )

        conversaciones = []

        for fila in (
            conversaciones_raw
            or []
        ):

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

        print(
            "[ERROR LISTANDO CONVERSACIONES]",
            error,
        )

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

        conversacion_raw = (
            obtener_conversacion(
                conversacion_id
            )
        )

        conversacion = (
            normalizar_conversacion(
                conversacion_raw
            )
        )


        mensajes_raw = (
            obtener_mensajes(
                conversacion_id
            )
        )

        mensajes = []

        for fila in (
            mensajes_raw
            or []
        ):

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

        print(
            "[ERROR OBTENIENDO CONVERSACIÓN]",
            error,
        )

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": str(error),
            },
        )


@app.post("/conversation/start")
def iniciar_conversacion():

    try:

        conversacion_id = (
            crear_conversacion()
        )

        print()
        print(
            "[REALTIME CONVERSATION]"
        )

        print(
            "Nueva conversación:",
            conversacion_id,
        )


        return {
            "ok": True,
            "conversacion_id":
                conversacion_id,
        }


    except Exception as error:

        print(
            "[ERROR CREANDO CONVERSACIÓN]",
            error,
        )

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": str(error),
            },
        )


@app.post("/conversation/message")
def guardar_mensaje_realtime(
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
                    + "..."
                )


            if titulo:

                try:

                    actualizar_titulo(
                        request.conversacion_id,
                        titulo,
                    )

                except Exception as error:

                    print(
                        "[AVISO TITULO]",
                        error,
                    )


        print(
            "[REALTIME MESSAGE]",
            request.conversacion_id,
            role,
        )


        return {
            "ok": True,
            "guardado": True,
            "mensajes": cantidad,
        }


    except Exception as error:

        print(
            "[ERROR GUARDANDO MENSAJE]",
            error,
        )

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": str(error),
            },
        )


# ============================================================
# RAG
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


        if not isinstance(
            datos,
            list,
        ):
            return []


        return datos


    except Exception as error:

        print(
            "[ERROR CARGANDO INDICE]",
            error,
        )

        return []


def contar_fragmentos_indice():

    return len(
        cargar_indice()
    )


def crear_embedding_consulta(
    texto: str
):

    respuesta = (
        client.embeddings.create(
            model=
                MODELO_EMBEDDING,

            input=
                texto,
        )
    )


    return (
        respuesta
        .data[0]
        .embedding
    )


def similitud_coseno(
    vector_a,
    vector_b,
):

    a = np.array(
        vector_a,
        dtype=float,
    )

    b = np.array(
        vector_b,
        dtype=float,
    )


    norma_a = (
        np.linalg.norm(a)
    )

    norma_b = (
        np.linalg.norm(b)
    )


    if (
        norma_a == 0
        or
        norma_b == 0
    ):

        return 0.0


    return float(
        np.dot(a, b)
        /
        (
            norma_a
            *
            norma_b
        )
    )


def buscar_en_documentos(
    consulta: str,
    limite: int = 5,
    drive_file_id: str = None,
):

    consulta = consulta.strip()


    if not consulta:
        return []


    indice = cargar_indice()


    if not indice:
        return []


    embedding_consulta = (
        crear_embedding_consulta(
            consulta
        )
    )


    resultados = []


    for item in indice:

        if drive_file_id:

            item_drive_id = item.get(
                "drive_file_id"
            )


            if (
                item_drive_id
                and
                item_drive_id
                != drive_file_id
            ):

                continue


        embedding = item.get(
            "embedding"
        )

        texto = item.get(
            "texto",
            "",
        )


        if (
            not embedding
            or
            not texto
        ):

            continue


        similitud = (
            similitud_coseno(
                embedding_consulta,
                embedding,
            )
        )


        resultados.append({

            "archivo":
                item.get(
                    "archivo",
                    "Documento desconocido",
                ),

            "fragmento":
                item.get(
                    "fragmento"
                ),

            "texto":
                texto,

            "similitud":
                similitud,

            "drive_file_id":
                item.get(
                    "drive_file_id"
                ),
        })


    resultados.sort(
        key=lambda x:
            x["similitud"],
        reverse=True,
    )


    return resultados[:limite]


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
            int(limite),
            100,
        ),
    )


    respuesta = (
        servicio.files()
        .list(
            pageSize=
                limite,

            fields=(
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


    archivos = respuesta.get(
        "files",
        [],
    )


    return [
        normalizar_archivo_drive(
            archivo
        )
        for archivo
        in archivos
    ]


def buscar_drive_backend(
    consulta: str,
    limite: int = 20,
):

    consulta = consulta.strip()


    if not consulta:
        return []


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
            q=query,

            pageSize=
                limite,

            fields=(
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


    archivos = respuesta.get(
        "files",
        [],
    )


    return [
        normalizar_archivo_drive(
            archivo
        )
        for archivo
        in archivos
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

            fields=(
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
                (
                    "La indexación no fue "
                    "autorizada explícitamente."
                ),
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

            "message":
                (
                    "No se encontró ningún "
                    "archivo coincidente."
                ),

            "result":
                [],
        }


    if len(archivos) > 1:

        return {

            "ok":
                True,

            "estado":
                "seleccion_requerida",

            "message":
                (
                    "Se encontraron varios "
                    "archivos coincidentes."
                ),

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


    if not resultados_rag:

        resultados_rag = (
            buscar_en_documentos(
                consulta=
                    pregunta,

                limite=
                    limite_resultados,
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
                despues - antes,

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

@app.get("/")
def inicio():

    archivo = (
        BASE_DIR
        / "realtime.html"
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

@app.get("/health")
def health():

    drive_ok = False


    try:

        obtener_servicio_drive()

        drive_ok = True


    except Exception as error:

        print(
            "[DRIVE HEALTH ERROR]",
            error,
        )


    return {

        "status":
            "ok",

        "realtime":
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
# TOKEN
# ============================================================

@app.get("/token")
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
                    "Eres un asistente personal "
                    "profesional. Habla en español "
                    "salvo que el usuario solicite "
                    "otro idioma."
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

@app.post("/tool")
def ejecutar_tool(
    request: ToolRequest
):

    nombre = request.name

    argumentos = (
        request.arguments
    )


    print()
    print("=" * 60)

    print(
        f"[REALTIME TOOL] {nombre}"
    )

    print(
        "Argumentos:",
        argumentos
    )

    print("=" * 60)


    try:

        if nombre == "recordar":

            contenido = argumentos.get(
                "contenido",
                "",
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


            resultados = []


            for memoria in memorias:

                resultados.append({

                    "id":
                        memoria["id"],

                    "categoria":
                        memoria["categoria"],

                    "clave":
                        memoria["clave"],

                    "contenido":
                        memoria["contenido"],

                    "importancia":
                        memoria["importancia"],
                })


            return {
                "ok": True,
                "result": resultados,
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


            resultados = []


            for memoria in memorias:

                resultados.append({

                    "id":
                        memoria["id"],

                    "categoria":
                        memoria["categoria"],

                    "clave":
                        memoria["clave"],

                    "contenido":
                        memoria["contenido"],

                    "importancia":
                        memoria["importancia"],
                })


            return {
                "ok": True,
                "result": resultados,
            }


        if nombre == "buscar_documentos":

            limite = int(
                argumentos.get(
                    "limite",
                    5,
                )
            )


            limite = max(
                1,
                min(
                    limite,
                    8,
                ),
            )


            resultados = buscar_en_documentos(

                consulta=
                    argumentos.get(
                        "consulta",
                        "",
                    ),

                limite=
                    limite,
            )


            return {
                "ok": True,
                "result": resultados,
            }


        if nombre == "listar_drive":

            archivos = listar_drive_backend(

                limite=
                    argumentos.get(
                        "limite",
                        20,
                    )
            )


            return {
                "ok": True,
                "result": archivos,
            }


        if nombre == "buscar_drive":

            archivos = buscar_drive_backend(

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
            )


            return {
                "ok": True,
                "result": archivos,
            }


        if nombre == "obtener_archivo_drive":

            archivo = (
                obtener_archivo_drive_backend(

                    argumentos.get(
                        "file_id",
                        "",
                    )
                )
            )


            return {
                "ok": True,
                "result": archivo,
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
                        "ok": False,
                        "error":
                            (
                                "La indexación "
                                "requiere autorización."
                            ),
                    },
                )


            antes = (
                contar_fragmentos_indice()
            )


            resultado = (
                indexar_archivo_drive(

                    argumentos.get(
                        "file_id",
                        "",
                    )
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
                    despues - antes,

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
            status_code=400,

            content={
                "ok": False,

                "error":
                    (
                        f"Herramienta desconocida: "
                        f"{nombre}"
                    ),
            },
        )


    except Exception as error:

        print(
            "[ERROR REALTIME TOOL]",
            type(error).__name__,
            error,
        )


        return JSONResponse(
            status_code=500,

            content={
                "ok": False,
                "error": str(error),
                "tipo":
                    type(error).__name__,
            },
        )