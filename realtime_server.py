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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError(
        "No se encontró OPENAI_API_KEY en el archivo .env"
    )

BASE_DIR = Path(__file__).resolve().parent
INDICE_PATH = BASE_DIR / "indice.json"

MODELO_EMBEDDING = "text-embedding-3-small"


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
# MEMORIA
# ============================================================

inicializar_memoria_largo_plazo()


# ============================================================
# MODELO TOOL REQUEST
# ============================================================

class ToolRequest(BaseModel):
    name: str
    arguments: dict


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

    respuesta = client.embeddings.create(
        model=MODELO_EMBEDDING,
        input=texto,
    )

    return respuesta.data[0].embedding


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

    norma_a = np.linalg.norm(a)
    norma_b = np.linalg.norm(b)

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
                item_drive_id != drive_file_id
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

        similitud = similitud_coseno(
            embedding_consulta,
            embedding,
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
            archivo.get("id"),

        "nombre":
            archivo.get("name"),

        "tipo":
            archivo.get("mimeType"),

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

    servicio = obtener_servicio_drive()

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
            pageSize=limite,
            fields=(
                "files("
                "id,"
                "name,"
                "mimeType,"
                "modifiedTime,"
                "webViewLink"
                ")"
            ),
            orderBy="modifiedTime desc",
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
        for archivo in archivos
    ]


def buscar_drive_backend(
    consulta: str,
    limite: int = 20,
):

    consulta = consulta.strip()

    if not consulta:
        return []

    servicio = obtener_servicio_drive()

    limite = max(
        1,
        min(
            int(limite),
            100,
        ),
    )

    consulta_segura = consulta.replace(
        "'",
        "\\'",
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
            pageSize=limite,
            fields=(
                "files("
                "id,"
                "name,"
                "mimeType,"
                "modifiedTime,"
                "webViewLink"
                ")"
            ),
            orderBy="modifiedTime desc",
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
        for archivo in archivos
    ]


def obtener_archivo_drive_backend(
    file_id: str
):

    servicio = obtener_servicio_drive()

    return (
        servicio.files()
        .get(
            fileId=file_id,
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
# DRIVE → RAG AUTOMÁTICO
# ============================================================

def analizar_archivo_drive_backend(
    consulta_archivo: str,
    pregunta: str,
    usuario_autorizo_indexacion: bool,
    limite_resultados: int = 5,
):

    if usuario_autorizo_indexacion is not True:

        return {

            "ok":
                False,

            "requiere_confirmacion":
                True,

            "message":
                (
                    "La indexación no fue autorizada "
                    "explícitamente por el usuario."
                ),
        }

    archivos = buscar_drive_backend(
        consulta=consulta_archivo,
        limite=10,
    )

    if not archivos:

        return {

            "ok":
                True,

            "estado":
                "sin_resultados",

            "message":
                (
                    "No se encontró ningún archivo "
                    "coincidente en Google Drive."
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
                    "Se encontraron varios archivos. "
                    "El usuario debe indicar cuál desea analizar."
                ),

            "result":
                archivos,
        }

    archivo = archivos[0]

    file_id = archivo["id"]
    nombre = archivo["nombre"]

    print()
    print("[FLUJO AUTOMÁTICO DRIVE]")
    print("Archivo:", nombre)
    print("ID:", file_id)

    fragmentos_antes = (
        contar_fragmentos_indice()
    )

    resultado_indexacion = (
        indexar_archivo_drive(
            file_id
        )
    )

    fragmentos_despues = (
        contar_fragmentos_indice()
    )

    agregados = (
        fragmentos_despues
        -
        fragmentos_antes
    )

    print(
        "Fragmentos agregados:",
        agregados,
    )

    resultados_rag = (
        buscar_en_documentos(
            consulta=pregunta,
            limite=limite_resultados,
            drive_file_id=file_id,
        )
    )

    if not resultados_rag:

        resultados_rag = (
            buscar_en_documentos(
                consulta=pregunta,
                limite=limite_resultados,
            )
        )

    return {

        "ok":
            True,

        "estado":
            "analizado",

        "archivo": {

            "id":
                file_id,

            "nombre":
                nombre,

            "tipo":
                archivo.get(
                    "tipo"
                ),

            "enlace":
                archivo.get(
                    "enlace"
                ),
        },

        "indexacion": {

            "fragmentos_antes":
                fragmentos_antes,

            "fragmentos_despues":
                fragmentos_despues,

            "fragmentos_agregados":
                agregados,

            "resultado":
                resultado_indexacion,
        },

        "pregunta":
            pregunta,

        "result":
            resultados_rag,
    }


# ============================================================
# PÁGINA PRINCIPAL
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
# TOKEN REALTIME
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

            "instructions": (
                "Eres un asistente personal profesional. "
                "Habla en español salvo que el usuario "
                "solicite otro idioma. "
                "Responde de forma clara, natural y breve."
            ),

            "audio": {

                "output": {
                    "voice": "marin"
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
                status_code=respuesta.status_code,
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
# EJECUTAR TOOLS
# ============================================================

@app.post("/tool")
def ejecutar_tool(
    request: ToolRequest
):

    nombre = request.name
    argumentos = request.arguments

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

        # ====================================================
        # RECORDAR
        # ====================================================

        if nombre == "recordar":

            contenido = argumentos.get(
                "contenido",
                "",
            )

            if not contenido:

                return JSONResponse(
                    status_code=400,
                    content={
                        "ok":
                            False,

                        "error":
                            "No se recibió contenido para guardar.",
                    },
                )

            resultado = guardar_memoria(

                categoria=argumentos.get(
                    "categoria",
                    "general",
                ),

                clave=argumentos.get(
                    "clave",
                    "memoria",
                ),

                contenido=contenido,

                importancia=argumentos.get(
                    "importancia",
                    3,
                ),
            )

            return {

                "ok":
                    True,

                "message":
                    "Memoria guardada correctamente.",

                "result":
                    resultado,
            }


        # ====================================================
        # BUSCAR MEMORIA
        # ====================================================

        if nombre == "buscar_memoria":

            consulta = argumentos.get(
                "consulta",
                "",
            )

            limite = argumentos.get(
                "limite",
                10,
            )

            memorias = buscar_memorias(
                consulta,
                limite,
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

                "ok":
                    True,

                "result":
                    resultados,
            }


        # ====================================================
        # VER MEMORIAS
        # ====================================================

        if nombre == "ver_memorias":

            categoria = argumentos.get(
                "categoria"
            )

            if categoria == "":
                categoria = None

            memorias = listar_memorias(

                limite=argumentos.get(
                    "limite",
                    20,
                ),

                categoria=categoria,
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

                "ok":
                    True,

                "result":
                    resultados,
            }


        # ====================================================
        # RAG
        # ====================================================

        if nombre == "buscar_documentos":

            consulta = argumentos.get(
                "consulta",
                "",
            )

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

            resultados = (
                buscar_en_documentos(
                    consulta=consulta,
                    limite=limite,
                )
            )

            return {

                "ok":
                    True,

                "message":
                    (
                        f"Se encontraron "
                        f"{len(resultados)} fragmentos."
                    ),

                "result":
                    resultados,
            }


        # ====================================================
        # LISTAR DRIVE
        # ====================================================

        if nombre == "listar_drive":

            archivos = listar_drive_backend(

                limite=argumentos.get(
                    "limite",
                    20,
                )
            )

            return {

                "ok":
                    True,

                "result":
                    archivos,
            }


        # ====================================================
        # BUSCAR DRIVE
        # ====================================================

        if nombre == "buscar_drive":

            consulta = argumentos.get(
                "consulta",
                "",
            )

            archivos = buscar_drive_backend(

                consulta=consulta,

                limite=argumentos.get(
                    "limite",
                    20,
                ),
            )

            print(
                "[DRIVE RESULTADOS]",
                len(archivos),
            )

            return {

                "ok":
                    True,

                "message":
                    (
                        f"Se encontraron "
                        f"{len(archivos)} archivos."
                    ),

                "result":
                    archivos,
            }


        # ====================================================
        # OBTENER ARCHIVO DRIVE
        # ====================================================

        if nombre == "obtener_archivo_drive":

            file_id = argumentos.get(
                "file_id",
                "",
            )

            if not file_id:

                return JSONResponse(
                    status_code=400,
                    content={
                        "ok":
                            False,

                        "error":
                            "Falta file_id.",
                    },
                )

            archivo = (
                obtener_archivo_drive_backend(
                    file_id
                )
            )

            return {

                "ok":
                    True,

                "result":
                    archivo,
            }


        # ====================================================
        # INDEXAR DRIVE MANUAL
        # ====================================================

        if nombre == "indexar_drive":

            file_id = argumentos.get(
                "file_id",
                "",
            )

            autorizacion = argumentos.get(
                "usuario_autorizo_indexacion",
                False,
            )

            if not file_id:

                return JSONResponse(
                    status_code=400,
                    content={
                        "ok":
                            False,

                        "error":
                            "Falta file_id.",
                    },
                )

            if autorizacion is not True:

                return JSONResponse(
                    status_code=403,
                    content={

                        "ok":
                            False,

                        "requiere_confirmacion":
                            True,

                        "error":
                            (
                                "La indexación requiere "
                                "una solicitud explícita del usuario."
                            ),
                    },
                )

            antes = contar_fragmentos_indice()

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
                    despues - antes,

                "result":
                    resultado,
            }


        # ====================================================
        # FLUJO AUTOMÁTICO DRIVE → RAG
        # ====================================================

        if nombre == "analizar_archivo_drive":

            consulta_archivo = argumentos.get(
                "consulta_archivo",
                "",
            )

            pregunta = argumentos.get(
                "pregunta",
                "",
            )

            autorizacion = argumentos.get(
                "usuario_autorizo_indexacion",
                False,
            )

            if not consulta_archivo:

                return JSONResponse(
                    status_code=400,
                    content={
                        "ok":
                            False,

                        "error":
                            "Falta consulta_archivo.",
                    },
                )

            if not pregunta:

                return JSONResponse(
                    status_code=400,
                    content={
                        "ok":
                            False,

                        "error":
                            "Falta la pregunta documental.",
                    },
                )

            resultado = (
                analizar_archivo_drive_backend(

                    consulta_archivo=
                        consulta_archivo,

                    pregunta=
                        pregunta,

                    usuario_autorizo_indexacion=
                        autorizacion,

                    limite_resultados=
                        argumentos.get(
                            "limite",
                            5,
                        ),
                )
            )

            return resultado


        # ====================================================
        # TOOL DESCONOCIDA
        # ====================================================

        return JSONResponse(
            status_code=400,
            content={
                "ok":
                    False,

                "error":
                    (
                        f"Herramienta desconocida: "
                        f"{nombre}"
                    ),
            },
        )


    except Exception as error:

        print()
        print(
            "[ERROR REALTIME TOOL]"
        )

        print(
            type(error).__name__,
            error,
        )

        return JSONResponse(
            status_code=500,
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
# EJECUCIÓN DIRECTA
# ============================================================

if __name__ == "__main__":

    print(
        "Servidor Realtime cargado correctamente."
    )

    print(
        "Memoria activa."
    )

    print(
        "RAG activo."
    )

    print(
        "Google Drive activo en modo lectura."
    )

    print(
        "Análisis automático Drive → RAG activo."
    )