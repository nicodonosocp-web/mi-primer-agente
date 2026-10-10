from configuracion import DATA_DIR
import io
import os

from dotenv import load_dotenv
from openai import OpenAI


# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError(
        "No se encontró OPENAI_API_KEY. "
        "Revisa el archivo .env."
    )

client = OpenAI()

MODELO_TRANSCRIPCION = "gpt-4o-mini-transcribe"
MODELO_VOZ = "gpt-4o-mini-tts"

VOZ_PREDETERMINADA = "marin"


# ============================================================
# VOCES DISPONIBLES
# ============================================================

VOCES_DISPONIBLES = {
    "Marin": "marin",
    "Cedar": "cedar",
    "Coral": "coral",
    "Alloy": "alloy",
    "Ash": "ash",
    "Ballad": "ballad",
    "Echo": "echo",
    "Fable": "fable",
    "Nova": "nova",
    "Onyx": "onyx",
    "Sage": "sage",
    "Shimmer": "shimmer",
    "Verse": "verse",
}


# ============================================================
# VOZ -> TEXTO
# ============================================================

def transcribir_audio(
    contenido_audio: bytes,
    nombre_archivo: str = "grabacion.wav",
) -> str:
    """
    Convierte audio a texto.
    """

    if not contenido_audio:
        return ""

    archivo = io.BytesIO(
        contenido_audio
    )

    archivo.name = nombre_archivo

    respuesta = client.audio.transcriptions.create(
        model=MODELO_TRANSCRIPCION,
        file=archivo,
        language="es",
    )

    texto = respuesta.text

    if not texto:
        return ""

    return texto.strip()


# ============================================================
# TEXTO -> VOZ
# ============================================================

def generar_voz(
    texto: str,
    voz: str = VOZ_PREDETERMINADA,
) -> bytes:
    """
    Convierte texto a audio MP3.
    """

    if not texto:
        return b""

    texto = texto.strip()

    if not texto:
        return b""

    # Límite preventivo
    if len(texto) > 4000:
        texto = texto[:4000]

    respuesta = client.audio.speech.create(
        model=MODELO_VOZ,
        voice=voz,
        input=texto,
        response_format="mp3",
        instructions=(
            "Habla en español latino neutro. "
            "Usa un tono profesional, natural y claro. "
            "Pronuncia correctamente nombres propios y siglas. "
            "Mantén una velocidad moderada y pausas naturales."
        ),
    )

    return respuesta.read()


# ============================================================
# PRUEBA DIRECTA
# ============================================================

if __name__ == "__main__":

    print("Módulo de voz cargado correctamente.")
    print()
    print("Voces disponibles:")

    for nombre, codigo in VOCES_DISPONIBLES.items():
        print(
            f"- {nombre}: {codigo}"
        )