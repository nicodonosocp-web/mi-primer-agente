import json
import os
from pathlib import Path
from configuracion import DATA_DIR

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

from agents import Agent, Runner, function_tool, ModelSettings


# .env se carga desde configuracion antes de crear clientes.

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError(
        "No se encontró OPENAI_API_KEY."
    )

client = OpenAI()

ARCHIVO_INDICE = DATA_DIR / "indice.json"

MODELO_EMBEDDING = "text-embedding-3-small"


def cargar_indice():
    if not ARCHIVO_INDICE.exists():
        raise RuntimeError(
            "No existe indice.json. "
            "Ejecuta primero: python indexar.py"
        )

    with ARCHIVO_INDICE.open(
        "r",
        encoding="utf-8"
    ) as archivo:
        return json.load(archivo)


INDICE = cargar_indice()


def similitud_coseno(vector_a, vector_b):
    a = np.array(vector_a)
    b = np.array(vector_b)

    denominador = (
        np.linalg.norm(a)
        * np.linalg.norm(b)
    )

    if denominador == 0:
        return 0.0

    return float(
        np.dot(a, b) / denominador
    )


def embedding_consulta(texto):
    respuesta = client.embeddings.create(
        model=MODELO_EMBEDDING,
        input=texto
    )

    return respuesta.data[0].embedding


@function_tool
def buscar_semanticamente(
    consulta: str,
    cantidad_resultados: int = 5,
) -> str:
    """
    Busca los fragmentos semánticamente más relevantes
    dentro del índice documental.
    """

    print(
        f"[TOOL] buscar_semanticamente -> "
        f"{consulta}"
    )

    vector_consulta = embedding_consulta(
        consulta
    )

    resultados = []

    for item in INDICE:
        similitud = similitud_coseno(
            vector_consulta,
            item["embedding"]
        )

        resultados.append({
            "similitud": similitud,
            "archivo": item["archivo"],
            "fragmento": item["fragmento"],
            "texto": item["texto"],
        })

    resultados.sort(
        key=lambda x: x["similitud"],
        reverse=True,
    )

    mejores = resultados[
        :cantidad_resultados
    ]

    salida = []

    for resultado in mejores:
        salida.append(
            f"Archivo: "
            f"{resultado['archivo']}\n"
            f"Fragmento: "
            f"{resultado['fragmento']}\n"
            f"Similitud: "
            f"{resultado['similitud']:.3f}\n"
            f"Contenido:\n"
            f"{resultado['texto']}"
        )

    return "\n\n---\n\n".join(salida)


agent = Agent(
    name="Agente documental RAG",
    instructions="""
Eres un agente documental profesional con búsqueda semántica.

Cuando el usuario pregunte por información contenida
en los documentos:

1. Usa buscar_semanticamente.
2. Analiza los fragmentos recuperados.
3. Basa la respuesta en esos fragmentos.
4. Menciona los archivos utilizados.
5. Si la evidencia documental es insuficiente,
   indícalo claramente.
6. No inventes contenido documental.
7. Mantén el contexto de la conversación.
8. Responde de forma clara, precisa y profesional.
""",
    tools=[
        buscar_semanticamente
    ],
    model_settings=ModelSettings(
        tool_choice="required"
    ),
)


historial = []

print()
print("=" * 65)
print("AGENTE DOCUMENTAL RAG")
print("=" * 65)
print()
print(
    f"Fragmentos indexados: {len(INDICE)}"
)
print()
print(
    "Escribe 'salir' para terminar."
)
print()
print("=" * 65)
print()


while True:
    mensaje = input("Tú: ").strip()

    if not mensaje:
        continue

    if mensaje.lower() == "salir":
        print()
        print("Agente: Hasta luego.")
        break

    historial.append({
        "role": "user",
        "content": mensaje,
    })

    try:
        resultado = Runner.run_sync(
            agent,
            historial,
        )

        respuesta = resultado.final_output

        historial.append({
            "role": "assistant",
            "content": respuesta,
        })

        print()
        print(
            f"Agente: {respuesta}"
        )
        print()

    except Exception as error:
        print()
        print(
            "Se produjo un error:"
        )
        print(error)
        print()