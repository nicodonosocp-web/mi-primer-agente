from pathlib import Path
from dotenv import load_dotenv
from agents import Agent, Runner, function_tool

load_dotenv()

@function_tool
def leer_archivo(nombre_archivo: str) -> str:
    """
    Lee un archivo de texto dentro de la carpeta documentos.
    """
    ruta = Path("documentos") / nombre_archivo

    if not ruta.exists():
        return f"No existe el archivo: {nombre_archivo}"

    if ruta.suffix.lower() != ".txt":
        return "Solo se permiten archivos .txt"

    return ruta.read_text(encoding="utf-8")


agent = Agent(
    name="Mi primer agente",
    instructions="""
    Responde de forma clara y profesional.

    Puedes usar la herramienta leer_archivo cuando el usuario
    necesite información contenida en archivos de la carpeta documentos.

    Mantén el contexto de la conversación.
    """,
    tools=[leer_archivo]
)

historial = []

print("Agente iniciado.")
print("Escribe 'salir' para terminar.\n")

while True:
    mensaje = input("Tú: ")

    if mensaje.lower() == "salir":
        print("Agente: Hasta luego.")
        break

    historial.append({
        "role": "user",
        "content": mensaje
    })

    resultado = Runner.run_sync(
        agent,
        historial
    )

    respuesta = resultado.final_output

    historial.append({
        "role": "assistant",
        "content": respuesta
    })

    print(f"\nAgente: {respuesta}\n")