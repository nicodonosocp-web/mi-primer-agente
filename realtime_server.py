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
# MODELO PARA TOOL CALLS
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

            datos = json.load(archivo)

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

    servicio = obtener_servicio_drive()

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
        for archivo
        in archivos
    ]


def obtener_archivo_drive_backend(
    file_id: str
):

    servicio = obtener_servicio_drive()

    archivo = (
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

    return archivo


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

        drive_ok = False


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

            categoria = argumentos.get(
                "categoria",
                "general",
            )

            clave = argumentos.get(
                "clave",
                "memoria",
            )

            contenido = argumentos.get(
                "contenido",
                "",
            )

            importancia = argumentos.get(
                "importancia",
                3,
            )

            if not contenido:

                return JSONResponse(
                    status_code=400,
                    content={
                        "ok": False,

                        "error":
                            "No se recibió contenido para guardar.",
                    },
                )

            resultado = guardar_memoria(
                categoria=categoria,
                clave=clave,
                contenido=contenido,
                importancia=importancia,
            )

            print(
                "[MEMORIA GUARDADA]"
            )

            print(
                resultado
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

            if not consulta:

                return JSONResponse(
                    status_code=400,
                    content={
                        "ok":
                            False,

                        "error":
                            "La consulta está vacía.",
                    },
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

            print(
                "[MEMORIAS ENCONTRADAS]",
                len(resultados),
            )

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

            limite = argumentos.get(
                "limite",
                20,
            )

            if categoria == "":
                categoria = None

            memorias = listar_memorias(
                limite=limite,
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
        # BUSCAR DOCUMENTOS RAG
        # ====================================================

        if nombre == "buscar_documentos":

            consulta = argumentos.get(
                "consulta",
                "",
            )

            limite = argumentos.get(
                "limite",
                5,
            )

            if not consulta:

                return JSONResponse(
                    status_code=400,
                    content={
                        "ok":
                            False,

                        "error":
                            "La consulta documental está vacía.",
                    },
                )

            try:
                limite = int(limite)

            except Exception:
                limite = 5

            limite = max(
                1,
                min(
                    limite,
                    8,
                ),
            )

            resultados = buscar_en_documentos(
                consulta=consulta,
                limite=limite,
            )

            print(
                "[RAG RESULTADOS]",
                len(resultados),
            )

            for numero, resultado in enumerate(
                resultados,
                start=1,
            ):

                print()

                print(
                    f"Resultado {numero}:",
                    resultado["archivo"],
                )

                print(
                    "Similitud:",
                    round(
                        resultado[
                            "similitud"
                        ],
                        4,
                    ),
                )

            return {

                "ok":
                    True,

                "message":
                    (
                        f"Se encontraron "
                        f"{len(resultados)} "
                        f"fragmentos relevantes."
                    ),

                "result":
                    resultados,
            }


        # ====================================================
        # LISTAR DRIVE
        # ====================================================

        if nombre == "listar_drive":

            limite = argumentos.get(
                "limite",
                20,
            )

            archivos = listar_drive_backend(
                limite=limite
            )

            print(
                "[DRIVE ARCHIVOS]",
                len(archivos),
            )

            return {

                "ok":
                    True,

                "message":
                    (
                        f"Se encontraron "
                        f"{len(archivos)} "
                        f"archivos recientes."
                    ),

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

            limite = argumentos.get(
                "limite",
                20,
            )

            if not consulta:

                return JSONResponse(
                    status_code=400,
                    content={
                        "ok":
                            False,

                        "error":
                            "La consulta está vacía.",
                    },
                )

            archivos = buscar_drive_backend(
                consulta=consulta,
                limite=limite,
            )

            print(
                "[DRIVE RESULTADOS]",
                len(archivos),
            )

            for archivo in archivos:

                print(
                    "-",
                    archivo["nombre"],
                    "|",
                    archivo["id"],
                )

            return {

                "ok":
                    True,

                "message":
                    (
                        f"Se encontraron "
                        f"{len(archivos)} "
                        f"archivos en Google Drive."
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

            archivo = obtener_archivo_drive_backend(
                file_id
            )

            return {

                "ok":
                    True,

                "result":
                    archivo,
            }


        # ====================================================
        # INDEXAR ARCHIVO DE DRIVE
        # ====================================================

        if nombre == "indexar_drive":

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

            antes = contar_fragmentos_indice()

            resultado = indexar_archivo_drive(
                file_id
            )

            despues = contar_fragmentos_indice()

            agregados = despues - antes

            print(
                "[DRIVE INDEXADO]"
            )

            print(
                "Fragmentos antes:",
                antes,
            )

            print(
                "Fragmentos después:",
                despues,
            )

            print(
                "Fragmentos agregados:",
                agregados,
            )

            return {

                "ok":
                    True,

                "message":
                    "Archivo procesado para RAG.",

                "fragmentos_antes":
                    antes,

                "fragmentos_despues":
                    despues,

                "fragmentos_agregados":
                    agregados,

                "result":
                    resultado,
            }


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
        "Memoria persistente activa."
    )

    print(
        "RAG activo."
    )

    print(
        "Google Drive activo en modo lectura."
    )

    print(
        "Fragmentos RAG:",
        contar_fragmentos_indice(),
    )