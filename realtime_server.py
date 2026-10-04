import os
from pathlib import Path

import requests

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
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


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="Mi Agente IA - Realtime"
)


# ============================================================
# INICIALIZAR MEMORIA
# ============================================================

inicializar_memoria_largo_plazo()


# ============================================================
# MODELO PARA LAS TOOL CALLS
# ============================================================

class ToolRequest(BaseModel):
    name: str
    arguments: dict


# ============================================================
# PÁGINA PRINCIPAL
# ============================================================

@app.get("/")
def inicio():

    archivo = BASE_DIR / "realtime.html"

    if not archivo.exists():

        return JSONResponse(
            status_code=404,
            content={
                "error": "No se encontró realtime.html"
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
        "status": "ok",
        "realtime": True,
        "memory": True,
        "tools": True,
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
                        "error": (
                            "No se recibió contenido "
                            "para guardar."
                        ),
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
                        "ok": False,
                        "error": (
                            "La consulta está vacía."
                        ),
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
                f"[MEMORIAS ENCONTRADAS] "
                f"{len(resultados)}"
            )


            return {

                "ok":
                    True,

                "result":
                    resultados,
            }


        # ====================================================
        # VER TODAS LAS MEMORIAS
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
        # TOOL DESCONOCIDA
        # ====================================================

        return JSONResponse(
            status_code=400,
            content={
                "ok":
                    False,

                "error":
                    f"Herramienta desconocida: {nombre}",
            },
        )


    except Exception as error:

        print()
        print(
            "[ERROR REALTIME TOOL]"
        )

        print(
            type(error).__name__,
            error
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
        "Endpoint POST /tool activo."
    )