import json
import os
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

from agents import (
    Agent,
    Runner,
    function_tool,
    ModelSettings,
)

from drive_tools import (
    listar_archivos_drive,
    buscar_archivos_drive,
    descargar_archivo_drive,
)

from rag_drive import indexar_archivo_drive

from memoria_largo_plazo import (
    inicializar_memoria_largo_plazo,
    guardar_memoria,
    buscar_memorias,
    listar_memorias,
    desactivar_memoria,
)


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

load_dotenv()

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError(
        "No se encontró OPENAI_API_KEY. "
        "Revisa el archivo .env."
    )

client = OpenAI()

ARCHIVO_INDICE = Path("indice.json")

MODELO_EMBEDDING = "text-embedding-3-small"

inicializar_memoria_largo_plazo()


# ============================================================
# RAG LOCAL
# ============================================================

def cargar_indice():
    """
    Carga el índice semántico desde indice.json.
    """

    if not ARCHIVO_INDICE.exists():
        return []

    try:

        with ARCHIVO_INDICE.open(
            "r",
            encoding="utf-8",
        ) as archivo:

            return json.load(
                archivo
            )

    except Exception as error:

        print(
            f"[ERROR] No fue posible cargar "
            f"indice.json: {error}"
        )

        return []


def recargar_indice():
    """
    Recarga el índice desde disco.
    """

    global INDICE

    INDICE = cargar_indice()


INDICE = cargar_indice()


def similitud_coseno(
    vector_a,
    vector_b,
):
    """
    Calcula similitud coseno entre dos vectores.
    """

    a = np.array(
        vector_a,
        dtype=float,
    )

    b = np.array(
        vector_b,
        dtype=float,
    )

    denominador = (
        np.linalg.norm(a)
        * np.linalg.norm(b)
    )

    if denominador == 0:
        return 0.0

    return float(
        np.dot(a, b)
        / denominador
    )


def embedding_consulta(
    texto,
):
    """
    Genera el embedding de una consulta.
    """

    respuesta = client.embeddings.create(
        model=MODELO_EMBEDDING,
        input=texto,
    )

    return respuesta.data[0].embedding


@function_tool
def buscar_semanticamente(
    consulta: str,
    cantidad_resultados: int = 5,
) -> str:
    """
    Busca información dentro del índice documental RAG.
    """

    print(
        f"[TOOL] buscar_semanticamente -> "
        f"{consulta}"
    )

    recargar_indice()

    if not INDICE:
        return (
            "No existe información documental "
            "indexada actualmente."
        )

    try:

        cantidad_resultados = int(
            cantidad_resultados
        )

    except Exception:

        cantidad_resultados = 5

    cantidad_resultados = max(
        1,
        min(
            cantidad_resultados,
            10,
        ),
    )

    try:

        vector_consulta = (
            embedding_consulta(
                consulta
            )
        )

    except Exception as error:

        return (
            "No fue posible generar "
            f"el embedding: {error}"
        )

    resultados = []

    for item in INDICE:

        embedding = item.get(
            "embedding"
        )

        if not embedding:
            continue

        try:

            similitud = similitud_coseno(
                vector_consulta,
                embedding,
            )

        except Exception:
            continue

        resultados.append({
            "similitud": similitud,
            "archivo": item.get(
                "archivo",
                "Desconocido",
            ),
            "fragmento": item.get(
                "fragmento",
                "N/D",
            ),
            "texto": item.get(
                "texto",
                "",
            ),
            "origen": item.get(
                "origen",
                "local",
            ),
            "drive_file_id": item.get(
                "drive_file_id"
            ),
        })

    if not resultados:

        return (
            "No se encontraron resultados "
            "utilizables en el índice."
        )

    resultados.sort(
        key=lambda x: x["similitud"],
        reverse=True,
    )

    mejores = resultados[
        :cantidad_resultados
    ]

    salida = []

    for resultado in mejores:

        bloque = (
            f"Archivo: "
            f"{resultado['archivo']}\n"
            f"Origen: "
            f"{resultado['origen']}\n"
            f"Fragmento: "
            f"{resultado['fragmento']}\n"
            f"Similitud: "
            f"{resultado['similitud']:.3f}\n"
        )

        if resultado[
            "drive_file_id"
        ]:

            bloque += (
                f"Drive File ID: "
                f"{resultado['drive_file_id']}\n"
            )

        bloque += (
            f"Contenido:\n"
            f"{resultado['texto']}"
        )

        salida.append(
            bloque
        )

    return (
        "\n\n---\n\n".join(
            salida
        )
    )


# ============================================================
# GOOGLE DRIVE
# ============================================================

@function_tool
def listar_drive(
    limite: int = 20,
) -> str:
    """
    Lista archivos recientes de Google Drive.
    """

    print(
        f"[TOOL] listar_drive -> "
        f"{limite}"
    )

    try:

        limite = int(
            limite
        )

    except Exception:

        limite = 20

    limite = max(
        1,
        min(
            limite,
            100,
        ),
    )

    try:

        archivos = (
            listar_archivos_drive(
                limite
            )
        )

    except Exception as error:

        return (
            "No fue posible acceder "
            f"a Google Drive: {error}"
        )

    if not archivos:

        return (
            "No se encontraron archivos "
            "en Google Drive."
        )

    salida = []

    for archivo in archivos:

        salida.append(
            f"Nombre: "
            f"{archivo.get('name')}\n"
            f"ID: "
            f"{archivo.get('id')}\n"
            f"Tipo: "
            f"{archivo.get('mimeType')}\n"
            f"Modificado: "
            f"{archivo.get('modifiedTime', 'N/D')}"
        )

    return (
        "\n\n".join(
            salida
        )
    )


@function_tool
def buscar_drive(
    consulta: str,
    limite: int = 20,
) -> str:
    """
    Busca archivos de Google Drive por nombre.
    """

    print(
        f"[TOOL] buscar_drive -> "
        f"{consulta}"
    )

    try:

        limite = int(
            limite
        )

    except Exception:

        limite = 20

    limite = max(
        1,
        min(
            limite,
            100,
        ),
    )

    try:

        archivos = (
            buscar_archivos_drive(
                consulta,
                limite,
            )
        )

    except Exception as error:

        return (
            "No fue posible buscar "
            f"en Google Drive: {error}"
        )

    if not archivos:

        return (
            "No se encontraron archivos "
            f"relacionados con '{consulta}'."
        )

    salida = []

    for archivo in archivos:

        salida.append(
            f"Nombre: "
            f"{archivo.get('name')}\n"
            f"ID: "
            f"{archivo.get('id')}\n"
            f"Tipo: "
            f"{archivo.get('mimeType')}\n"
            f"Modificado: "
            f"{archivo.get('modifiedTime', 'N/D')}"
        )

    return (
        "\n\n".join(
            salida
        )
    )


@function_tool
def descargar_drive(
    file_id: str,
) -> str:
    """
    Descarga un archivo de Google Drive.
    """

    print(
        f"[TOOL] descargar_drive -> "
        f"{file_id}"
    )

    try:

        ruta = (
            descargar_archivo_drive(
                file_id
            )
        )

    except Exception as error:

        return (
            "No fue posible descargar "
            f"el archivo: {error}"
        )

    return (
        "Archivo descargado correctamente.\n"
        f"Ruta local: {ruta}"
    )


@function_tool
def indexar_drive(
    file_id: str,
) -> str:
    """
    Descarga un archivo de Google Drive
    y lo agrega al sistema RAG.
    """

    print(
        f"[TOOL] indexar_drive -> "
        f"{file_id}"
    )

    try:

        resultado = (
            indexar_archivo_drive(
                file_id
            )
        )

        recargar_indice()

        return resultado

    except Exception as error:

        return (
            "No fue posible indexar "
            f"el archivo: {error}"
        )


# ============================================================
# MEMORIA DE LARGO PLAZO
# ============================================================

@function_tool
def recordar(
    categoria: str,
    clave: str,
    contenido: str,
    importancia: int = 3,
) -> str:
    """
    Guarda o actualiza información útil
    en la memoria de largo plazo.
    """

    print(
        f"[TOOL] recordar -> "
        f"{categoria} | {clave}"
    )

    try:

        resultado = guardar_memoria(
            categoria=categoria,
            clave=clave,
            contenido=contenido,
            importancia=importancia,
        )

        return (
            f"Memoria {resultado['accion']}.\n"
            f"Categoría: "
            f"{resultado['categoria']}\n"
            f"Clave: "
            f"{resultado['clave']}\n"
            f"Contenido: "
            f"{resultado['contenido']}"
        )

    except Exception as error:

        return (
            "No fue posible guardar "
            f"la memoria: {error}"
        )


@function_tool
def buscar_memoria(
    consulta: str,
    limite: int = 10,
) -> str:
    """
    Busca información en la memoria
    persistente de largo plazo.
    """

    print(
        f"[TOOL] buscar_memoria -> "
        f"{consulta}"
    )

    try:

        memorias = buscar_memorias(
            consulta,
            limite,
        )

    except Exception as error:

        return (
            "No fue posible consultar "
            f"la memoria: {error}"
        )

    if not memorias:

        return (
            "No existen memorias de "
            "largo plazo relacionadas "
            f"con '{consulta}'."
        )

    salida = []

    for memoria in memorias:

        salida.append(
            f"ID: "
            f"{memoria['id']}\n"
            f"Categoría: "
            f"{memoria['categoria']}\n"
            f"Clave: "
            f"{memoria['clave']}\n"
            f"Contenido: "
            f"{memoria['contenido']}\n"
            f"Importancia: "
            f"{memoria['importancia']}"
        )

    return (
        "\n\n---\n\n".join(
            salida
        )
    )


@function_tool
def ver_memorias(
    categoria: str = "",
    limite: int = 20,
) -> str:
    """
    Lista memorias persistentes activas.
    """

    print(
        f"[TOOL] ver_memorias -> "
        f"{categoria}"
    )

    categoria_real = (
        categoria.strip()
        if categoria
        else None
    )

    try:

        memorias = listar_memorias(
            limite=limite,
            categoria=categoria_real,
        )

    except Exception as error:

        return (
            "No fue posible listar "
            f"las memorias: {error}"
        )

    if not memorias:

        return (
            "No existen memorias "
            "guardadas."
        )

    salida = []

    for memoria in memorias:

        salida.append(
            f"ID: {memoria['id']}\n"
            f"Categoría: {memoria['categoria']}\n"
            f"Clave: {memoria['clave']}\n"
            f"Contenido: {memoria['contenido']}\n"
            f"Importancia: {memoria['importancia']}"
        )

    return (
        "\n\n---\n\n".join(
            salida
        )
    )


@function_tool
def olvidar_memoria(
    memoria_id: int,
) -> str:
    """
    Desactiva una memoria persistente.
    Solo debe usarse cuando el usuario
    lo solicite expresamente.
    """

    print(
        f"[TOOL] olvidar_memoria -> "
        f"{memoria_id}"
    )

    try:

        resultado = (
            desactivar_memoria(
                memoria_id
            )
        )

        if resultado:

            return (
                f"Memoria {memoria_id} "
                "desactivada correctamente."
            )

        return (
            "No se encontró la "
            "memoria indicada."
        )

    except Exception as error:

        return (
            "No fue posible desactivar "
            f"la memoria: {error}"
        )


# ============================================================
# AGENTE
# ============================================================

agent = Agent(
    name="Asistente personal y documental",
    instructions="""
Eres un asistente personal y documental con acceso a:

1. El historial completo de la conversación actual.
2. Una memoria persistente de largo plazo.
3. Un sistema documental RAG.
4. Google Drive en modo solo lectura.
5. Conocimiento general.

Debes distinguir claramente estas fuentes.

============================================================
ORDEN DE PRIORIDAD
============================================================

Cuando respondas, razona siguiendo este orden:

1. Historial de la conversación actual.
2. Memoria de largo plazo.
3. Documentos indexados mediante RAG.
4. Google Drive.
5. Conocimiento general.

No uses herramientas innecesariamente.

Si una pregunta puede responderse directamente desde el historial,
hazlo sin consultar otras fuentes.

============================================================
HISTORIAL DE LA CONVERSACIÓN
============================================================

Los mensajes anteriores recibidos junto con la consulta representan
el historial real de la conversación actual.

Si el usuario pregunta:

- qué dijo anteriormente;
- qué conversaron;
- qué pidió;
- qué indicó;
- qué acordó;
- qué decidió;
- qué tarea mencionó;
- qué información entregó;
- qué quedó pendiente;
- qué se habló antes;

responde primero usando el historial.

Para este tipo de pregunta:

- no uses RAG;
- no uses Google Drive;
- no uses memoria de largo plazo;

si la respuesta ya está claramente disponible en el historial.

Nunca reemplaces información presente en el historial por una búsqueda.

============================================================
MEMORIA DE LARGO PLAZO
============================================================

Dispones de una memoria persistente que puede conservar información
entre conversaciones distintas.

Utiliza buscar_memoria cuando el usuario pregunte por:

- proyectos anteriores;
- decisiones previas;
- preferencias persistentes;
- tareas importantes;
- objetivos;
- configuraciones;
- procedimientos recurrentes;
- información que pueda haber sido guardada en otro chat;

y esa información no aparezca en el historial actual.

Utiliza recordar cuando sea apropiado guardar información duradera.

Son buenos candidatos para recordar:

- proyectos activos;
- objetivos de proyectos;
- decisiones importantes;
- tareas relevantes;
- compromisos;
- preferencias de trabajo;
- procedimientos recurrentes;
- configuraciones técnicas;
- nombres o funciones relevantes para un proyecto;
- datos que el usuario pida expresamente recordar.

Si el usuario dice expresamente:

"recuerda..."
"guarda esto..."
"ten presente..."
"quiero que recuerdes..."

debes utilizar recordar si la información es adecuada para memoria.

Evita guardar automáticamente:

- saludos;
- comentarios casuales;
- respuestas completas del asistente;
- grandes bloques de documentos;
- información sin utilidad futura;
- datos duplicados;
- contraseñas;
- API keys;
- tokens;
- credenciales;
- secretos.

Si una información cambia, intenta actualizar la misma clave en lugar
de crear una memoria duplicada.

Utiliza olvidar_memoria únicamente cuando el usuario solicite
expresamente olvidar, eliminar o dejar de recordar algo.

Nunca elimines una memoria por iniciativa propia.

============================================================
RAG DOCUMENTAL
============================================================

Utiliza buscar_semanticamente cuando el usuario solicite información
que esté o pueda estar contenida en documentos indexados.

Ejemplos:

- "Busca en mis documentos..."
- "¿Qué dice el informe sobre...?"
- "Resume el documento..."
- "Compara estos antecedentes..."
- "Busca referencias a..."
- "¿Qué información contienen mis archivos sobre...?"

No utilices buscar_semanticamente para recordar conversaciones.

Cuando uses RAG:

- menciona los archivos utilizados cuando sea posible;
- no inventes información;
- indica si la evidencia es insuficiente;
- diferencia hechos documentales de conocimiento general.

============================================================
GOOGLE DRIVE
============================================================

Utiliza buscar_drive cuando el usuario solicite localizar archivos
en Google Drive.

Utiliza listar_drive cuando solicite ver archivos recientes.

Nunca inventes:

- nombres de archivos;
- IDs;
- fechas;
- resultados.

Encontrar un archivo en Drive no significa haber leído su contenido.

Si el usuario quiere analizar el contenido de un archivo de Drive:

1. localiza el archivo;
2. identifica su ID real;
3. utiliza indexar_drive;
4. luego utiliza buscar_semanticamente.

Si indexar_drive indica que el archivo ya estaba indexado,
continúa directamente con buscar_semanticamente.

============================================================
DESCARGAS
============================================================

Utiliza descargar_drive cuando el usuario solicite expresamente
descargar un archivo al equipo.

No descargues archivos innecesariamente.

============================================================
LIMITACIONES
============================================================

Google Drive está en modo solo lectura.

No puedes mediante estas herramientas:

- eliminar archivos;
- renombrarlos;
- editarlos;
- reemplazarlos;
- subir archivos.

Nunca afirmes haber realizado una acción que no ejecutaste.

Si una herramienta genera un error, comunícalo claramente.

============================================================
EJEMPLOS
============================================================

Usuario:
"¿Qué te dije antes sobre Proyecto Alfa?"

Si está en el historial actual:
responde directamente.

No uses herramientas.


Usuario:
"En otro chat te hablé de Proyecto Beta. ¿Qué recuerdas?"

Usa:
buscar_memoria.


Usuario:
"Recuerda que Proyecto Beta debe estar terminado en diciembre."

Usa:
recordar.


Usuario:
"Busca en mis documentos información sobre Proyecto Beta."

Usa:
buscar_semanticamente.


Usuario:
"Busca en mi Drive documentos sobre Proyecto Beta."

Usa:
buscar_drive.


Usuario:
"Busca en Drive el último PDF sobre agua y resúmelo."

Flujo:
1. buscar_drive;
2. identificar el archivo real;
3. indexar_drive;
4. buscar_semanticamente;
5. responder indicando la fuente.

============================================================
ESTILO
============================================================

Responde en español salvo que el usuario solicite otro idioma.

Sé claro, preciso, profesional y directo.

Mantén el contexto.

No repitas información innecesariamente.

No uses herramientas cuando ya dispones de la respuesta.
""",
    tools=[
        buscar_semanticamente,
        listar_drive,
        buscar_drive,
        descargar_drive,
        indexar_drive,
        recordar,
        buscar_memoria,
        ver_memorias,
        olvidar_memoria,
    ],
    model_settings=ModelSettings(
        tool_choice="auto"
    ),
)


# ============================================================
# INTERFAZ DE TERMINAL
# ============================================================

def main():

    historial = []

    print()
    print("=" * 70)
    print("ASISTENTE PERSONAL + DRIVE + RAG + MEMORIA")
    print("=" * 70)
    print()

    print(
        f"Fragmentos RAG disponibles: "
        f"{len(INDICE)}"
    )

    print(
        "Google Drive: modo solo lectura."
    )

    print(
        "Memoria de largo plazo: activa."
    )

    print()
    print(
        "Escribe 'salir' para terminar."
    )
    print()

    print("=" * 70)
    print()

    while True:

        mensaje = input(
            "Tú: "
        ).strip()

        if not mensaje:
            continue

        if mensaje.lower() == "salir":

            print()
            print(
                "Agente: Hasta luego."
            )
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

            respuesta = (
                resultado.final_output
            )

            historial.append({
                "role": "assistant",
                "content": respuesta,
            })

            print()
            print(
                f"Agente: {respuesta}"
            )
            print()

        except KeyboardInterrupt:

            print()
            print(
                "Agente: Operación cancelada."
            )
            print()

        except Exception as error:

            print()
            print(
                "Se produjo un error:"
            )
            print(error)
            print()


if __name__ == "__main__":
    main()