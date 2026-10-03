import os
from pathlib import Path

from dotenv import load_dotenv
from pypdf import PdfReader
from docx import Document

from agents import Agent, Runner, function_tool, ModelSettings


# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError(
        "No se encontró OPENAI_API_KEY. Revisa el archivo .env."
    )

CARPETA_DOCUMENTOS = Path("documentos")

EXTENSIONES_PERMITIDAS = {
    ".txt",
    ".pdf",
    ".docx",
}


# ============================================================
# FUNCIONES INTERNAS
# ============================================================

def obtener_archivos():
    """
    Obtiene todos los documentos compatibles.
    """
    if not CARPETA_DOCUMENTOS.exists():
        return []

    return sorted(
        [
            archivo
            for archivo in CARPETA_DOCUMENTOS.iterdir()
            if archivo.is_file()
            and archivo.suffix.lower() in EXTENSIONES_PERMITIDAS
        ],
        key=lambda x: x.name.lower(),
    )


def validar_ruta(nombre_archivo: str):
    """
    Evita acceder a archivos fuera de la carpeta documentos.
    """

    carpeta_base = CARPETA_DOCUMENTOS.resolve()
    ruta = (CARPETA_DOCUMENTOS / nombre_archivo).resolve()

    if carpeta_base not in ruta.parents:
        raise ValueError(
            "El archivo solicitado está fuera de la carpeta documentos."
        )

    return ruta


def extraer_txt(ruta: Path):
    """
    Extrae texto de un archivo TXT.
    """
    return ruta.read_text(
        encoding="utf-8",
        errors="replace",
    )


def extraer_pdf(ruta: Path):
    """
    Extrae texto de un PDF que contenga texto seleccionable.
    """

    reader = PdfReader(str(ruta))

    paginas = []

    for numero, pagina in enumerate(reader.pages, start=1):

        texto = pagina.extract_text() or ""

        paginas.append(
            f"\n--- PÁGINA {numero} ---\n{texto}"
        )

    return "\n".join(paginas)


def extraer_docx(ruta: Path):
    """
    Extrae texto de un archivo Word DOCX.
    """

    documento = Document(str(ruta))

    bloques = []

    # Párrafos
    for parrafo in documento.paragraphs:
        texto = parrafo.text.strip()

        if texto:
            bloques.append(texto)

    # Tablas
    for numero_tabla, tabla in enumerate(
        documento.tables,
        start=1,
    ):

        bloques.append(
            f"\n--- TABLA {numero_tabla} ---"
        )

        for fila in tabla.rows:

            valores = [
                celda.text.strip()
                for celda in fila.cells
            ]

            bloques.append(
                " | ".join(valores)
            )

    return "\n".join(bloques)


def extraer_documento(ruta: Path):
    """
    Extrae texto según el formato del documento.
    """

    extension = ruta.suffix.lower()

    if extension == ".txt":
        return extraer_txt(ruta)

    if extension == ".pdf":
        return extraer_pdf(ruta)

    if extension == ".docx":
        return extraer_docx(ruta)

    raise ValueError(
        f"Formato no soportado: {extension}"
    )


# ============================================================
# HERRAMIENTAS DEL AGENTE
# ============================================================

@function_tool
def listar_archivos() -> str:
    """
    Lista los documentos disponibles en la carpeta documentos.
    """

    print("[TOOL] listar_archivos")

    archivos = obtener_archivos()

    if not archivos:
        return (
            "No hay documentos compatibles disponibles."
        )

    salida = []

    for archivo in archivos:

        tamaño_kb = archivo.stat().st_size / 1024

        salida.append(
            f"{archivo.name} "
            f"({archivo.suffix.lower()}, "
            f"{tamaño_kb:.1f} KB)"
        )

    return "\n".join(salida)


@function_tool
def leer_documento(nombre_archivo: str) -> str:
    """
    Lee el contenido completo de un archivo TXT, PDF o DOCX.
    """

    print(
        f"[TOOL] leer_documento -> "
        f"{nombre_archivo}"
    )

    try:
        ruta = validar_ruta(nombre_archivo)

    except Exception as error:
        return str(error)

    if not ruta.exists():
        return (
            f"No existe el archivo: "
            f"{nombre_archivo}"
        )

    if ruta.suffix.lower() not in EXTENSIONES_PERMITIDAS:
        return (
            "Formato no permitido. "
            "Se aceptan TXT, PDF y DOCX."
        )

    try:

        contenido = extraer_documento(ruta)

    except Exception as error:

        return (
            f"No fue posible leer "
            f"{nombre_archivo}: {error}"
        )

    if not contenido.strip():

        return (
            f"El archivo {nombre_archivo} "
            "no contiene texto extraíble."
        )

    # Protección frente a documentos enormes
    LIMITE = 40000

    if len(contenido) > LIMITE:

        contenido = (
            contenido[:LIMITE]
            + "\n\n[CONTENIDO RECORTADO]"
        )

    return contenido


@function_tool
def buscar_en_documentos(consulta: str) -> str:
    """
    Busca una consulta entre todos los documentos TXT, PDF y DOCX.
    """

    print(
        f"[TOOL] buscar_en_documentos -> "
        f"{consulta}"
    )

    archivos = obtener_archivos()

    if not archivos:
        return "No hay documentos disponibles."

    palabras = [
        palabra.lower().strip(
            ".,;:!?()[]{}\"'"
        )
        for palabra in consulta.split()
        if len(palabra.strip()) > 2
    ]

    if not palabras:
        return (
            "La consulta es demasiado corta "
            "para realizar una búsqueda."
        )

    resultados = []

    for archivo in archivos:

        try:

            contenido = extraer_documento(
                archivo
            )

        except Exception:

            continue

        lineas = contenido.splitlines()

        for numero, linea in enumerate(
            lineas,
            start=1,
        ):

            linea_limpia = linea.strip()

            if not linea_limpia:
                continue

            linea_lower = (
                linea_limpia.lower()
            )

            coincidencias = sum(
                1
                for palabra in palabras
                if palabra in linea_lower
            )

            if coincidencias > 0:

                resultados.append(
                    (
                        coincidencias,
                        archivo.name,
                        numero,
                        linea_limpia,
                    )
                )

    if not resultados:

        return (
            "No se encontraron coincidencias "
            "en los documentos."
        )

    resultados.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    mejores = resultados[:20]

    salida = []

    for (
        coincidencias,
        archivo,
        numero,
        linea,
    ) in mejores:

        salida.append(
            f"Archivo: {archivo}\n"
            f"Referencia: {numero}\n"
            f"Coincidencias: "
            f"{coincidencias}\n"
            f"Contenido: {linea}"
        )

    return "\n\n".join(salida)


@function_tool
def obtener_informacion_documento(
    nombre_archivo: str,
) -> str:
    """
    Entrega información básica de un documento.
    """

    print(
        f"[TOOL] obtener_informacion_documento "
        f"-> {nombre_archivo}"
    )

    try:

        ruta = validar_ruta(
            nombre_archivo
        )

    except Exception as error:

        return str(error)

    if not ruta.exists():

        return (
            f"No existe el archivo: "
            f"{nombre_archivo}"
        )

    tamaño_kb = (
        ruta.stat().st_size / 1024
    )

    informacion = [
        f"Nombre: {ruta.name}",
        f"Formato: {ruta.suffix.lower()}",
        f"Tamaño: {tamaño_kb:.1f} KB",
    ]

    if ruta.suffix.lower() == ".pdf":

        try:

            reader = PdfReader(
                str(ruta)
            )

            informacion.append(
                f"Páginas: "
                f"{len(reader.pages)}"
            )

        except Exception:

            pass

    return "\n".join(informacion)


# ============================================================
# DEFINICIÓN DEL AGENTE
# ============================================================

agent = Agent(
    name="Agente documental",
    instructions="""
Eres un agente documental profesional.

Dispones de cuatro herramientas:

1. listar_archivos
   Permite conocer todos los documentos disponibles.

2. buscar_en_documentos
   Permite buscar información dentro de todos los TXT,
   PDF y DOCX disponibles.

3. leer_documento
   Permite consultar el contenido de un documento
   específico.

4. obtener_informacion_documento
   Permite conocer nombre, formato, tamaño y otra
   información básica del documento.

REGLAS:

- Cuando el usuario pregunte qué documentos existen,
  usa listar_archivos.

- Cuando el usuario solicite información que pueda
  estar contenida en documentos, usa primero
  buscar_en_documentos.

- Cuando identifiques un documento especialmente
  relevante, utiliza leer_documento si necesitas
  revisar más contexto.

- Puedes consultar más de un documento antes de
  responder.

- Cuando una respuesta dependa de los documentos,
  basa la respuesta en el contenido encontrado.

- No inventes información documental.

- Si no encuentras la información solicitada,
  indícalo claramente.

- Cuando sea posible, menciona el nombre del archivo
  utilizado como fuente.

- Mantén el contexto de la conversación.

- Responde en español salvo que el usuario solicite
  otro idioma.

- Sé claro, preciso y profesional.
""",
    tools=[
        listar_archivos,
        buscar_en_documentos,
        leer_documento,
        obtener_informacion_documento,
    ],
    model_settings=ModelSettings(
        tool_choice="required"
    ),
)


# ============================================================
# MEMORIA DE LA SESIÓN
# ============================================================

historial = []


# ============================================================
# INTERFAZ DE TERMINAL
# ============================================================

print()
print("=" * 65)
print("AGENTE DOCUMENTAL")
print("=" * 65)
print()
print("Formatos soportados:")
print("  TXT")
print("  PDF")
print("  DOCX")
print()
print(
    "Coloca los documentos dentro "
    "de la carpeta 'documentos'."
)
print()
print(
    "Escribe 'salir' para terminar."
)
print()
print("=" * 65)
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

    historial.append(
        {
            "role": "user",
            "content": mensaje,
        }
    )

    try:

        resultado = Runner.run_sync(
            agent,
            historial,
        )

        respuesta = (
            resultado.final_output
        )

        historial.append(
            {
                "role": "assistant",
                "content": respuesta,
            }
        )

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
            "Se produjo un error "
            "al ejecutar el agente:"
        )
        print(error)
        print()