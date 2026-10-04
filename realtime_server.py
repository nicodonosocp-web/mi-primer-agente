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

    respuesta = (
        client.embeddings.create(
            model=MODELO_EMBEDDING,
            input=texto,
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


    norma_a = np.linalg.norm(
        a
    )

    norma_b = np.linalg.norm(
        b
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
):

    consulta = (
        consulta
        .strip()
    )


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
                    "fragmento",
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


    return resultados[
        :limite
    ]


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
    }


# ============================================================
# TOKEN EFÍMERO
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

    print(
        "=" * 60
    )

    print(
        f"[REALTIME TOOL] {nombre}"
    )

    print(
        "Argumentos:",
        argumentos
    )

    print(
        "=" * 60
    )


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
                        "ok":
                            False,

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
        # BUSCAR DOCUMENTOS
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


            try:

                limite = int(
                    limite
                )

            except Exception:

                limite = 5


            limite = max(
                1,
                min(
                    limite,
                    8,
                ),
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


            resultados = (
                buscar_en_documentos(
                    consulta=consulta,
                    limite=limite,
                )
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


            if not resultados:

                return {

                    "ok":
                        True,

                    "message":
                        "No se encontraron fragmentos en el índice documental.",

                    "result":
                        [],
                }


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
        "Fragmentos indexados:",
        contar_fragmentos_indice(),
    )