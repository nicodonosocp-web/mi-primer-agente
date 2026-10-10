import almacenamiento
from almacenamiento import indice_transaccion
from configuracion import DATA_DIR
import json
import math
import os
import re
import tempfile
import unicodedata

from collections import Counter
from pathlib import Path

import numpy as np

from dotenv import load_dotenv
from openai import OpenAI


# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

INDICE_PATH = DATA_DIR / "indice.json"

MODELO_EMBEDDING = "text-embedding-3-small"

PESO_SEMANTICO = 0.78
PESO_LEXICO = 0.22

CANDIDATOS_INICIALES = 30

SIMILITUD_DUPLICADO = 0.82


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError(
        "No se encontró OPENAI_API_KEY."
    )


client = OpenAI(
    api_key=OPENAI_API_KEY
)


# ============================================================
# STOPWORDS
# ============================================================

STOPWORDS = {
    "a",
    "al",
    "algo",
    "algunos",
    "ante",
    "antes",
    "como",
    "con",
    "contra",
    "cual",
    "cuando",
    "de",
    "del",
    "desde",
    "donde",
    "durante",
    "e",
    "el",
    "ella",
    "ellas",
    "ellos",
    "en",
    "entre",
    "era",
    "es",
    "esa",
    "ese",
    "eso",
    "esta",
    "este",
    "esto",
    "fue",
    "ha",
    "hay",
    "la",
    "las",
    "le",
    "les",
    "lo",
    "los",
    "más",
    "me",
    "mi",
    "mis",
    "no",
    "nos",
    "o",
    "para",
    "pero",
    "por",
    "que",
    "qué",
    "se",
    "si",
    "sin",
    "sobre",
    "su",
    "sus",
    "te",
    "tu",
    "tus",
    "un",
    "una",
    "uno",
    "unos",
    "y",
    "ya",
}


# ============================================================
# NORMALIZACIÓN
# ============================================================

def normalizar_texto(texto: str):

    if not texto:
        return ""

    texto = unicodedata.normalize(
        "NFKD",
        texto
    )

    texto = "".join(
        caracter
        for caracter in texto
        if not unicodedata.combining(caracter)
    )

    texto = texto.lower()

    texto = re.sub(
        r"\s+",
        " ",
        texto,
    )

    return texto.strip()


def tokenizar(texto: str):

    texto = normalizar_texto(texto)

    tokens = re.findall(
        r"[a-z0-9ñ]+",
        texto,
    )

    return [
        token
        for token in tokens
        if (
            len(token) > 1
            and token not in STOPWORDS
        )
    ]


# ============================================================
# ÍNDICE
# ============================================================

def cargar_indice():
    return almacenamiento.cargar_indice()


def guardar_indice(indice):
    return almacenamiento.guardar_indice(indice)


# ============================================================
# EMBEDDINGS
# ============================================================

def crear_embedding(texto: str):

    respuesta = client.embeddings.create(
        model=MODELO_EMBEDDING,
        input=texto,
    )

    return respuesta.data[0].embedding


# ============================================================
# SIMILITUD
# ============================================================

def similitud_coseno(
    vector_a,
    vector_b,
):

    try:

        a = np.asarray(
            vector_a,
            dtype=np.float32,
        )

        b = np.asarray(
            vector_b,
            dtype=np.float32,
        )

        norma_a = np.linalg.norm(a)
        norma_b = np.linalg.norm(b)

        if norma_a == 0 or norma_b == 0:
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

    except Exception:

        return 0.0


def puntuacion_lexica(
    consulta_tokens,
    texto_tokens,
):

    if (
        not consulta_tokens
        or
        not texto_tokens
    ):
        return 0.0

    frecuencia = Counter(
        texto_tokens
    )

    coincidencias = 0.0

    for token in consulta_tokens:

        cantidad = frecuencia.get(
            token,
            0,
        )

        if cantidad > 0:

            coincidencias += (
                1.0
                +
                math.log(
                    1 + cantidad
                )
            )

    denominador = max(
        1,
        len(set(consulta_tokens)),
    )

    return min(
        coincidencias
        /
        denominador,
        2.0,
    ) / 2.0


# ============================================================
# BONIFICACIONES
# ============================================================

def calcular_bonificaciones(
    consulta: str,
    item: dict,
):

    consulta_norm = normalizar_texto(
        consulta
    )

    archivo_norm = normalizar_texto(
        item.get(
            "archivo",
            "",
        )
    )

    texto_norm = normalizar_texto(
        item.get(
            "texto",
            "",
        )
    )

    bonus = 0.0

    palabras_archivo = tokenizar(
        archivo_norm
    )

    if palabras_archivo:

        coincidencias = sum(
            1
            for palabra in palabras_archivo
            if palabra in consulta_norm
        )

        bonus += min(
            0.08,
            coincidencias * 0.025,
        )

    anos_consulta = set(
        re.findall(
            r"\b(?:19|20)\d{2}\b",
            consulta_norm,
        )
    )

    anos_texto = set(
        re.findall(
            r"\b(?:19|20)\d{2}\b",
            texto_norm,
        )
    )

    if anos_consulta & anos_texto:
        bonus += 0.06

    numeros = set(
        re.findall(
            r"\b\d{2,}\b",
            consulta_norm,
        )
    )

    encontrados = sum(
        1
        for numero in numeros
        if numero in texto_norm
    )

    if encontrados:

        bonus += min(
            0.05,
            encontrados * 0.015,
        )

    return bonus


# ============================================================
# DIVERSIFICACIÓN
# ============================================================

def similitud_jaccard(
    texto_a: str,
    texto_b: str,
):

    tokens_a = set(
        tokenizar(texto_a)
    )

    tokens_b = set(
        tokenizar(texto_b)
    )

    if not tokens_a or not tokens_b:
        return 0.0

    union = len(
        tokens_a | tokens_b
    )

    if union == 0:
        return 0.0

    return (
        len(tokens_a & tokens_b)
        /
        union
    )


def diversificar_resultados(
    candidatos,
    limite,
):

    seleccionados = []

    for candidato in candidatos:

        repetido = False

        for seleccionado in seleccionados:

            parecido = similitud_jaccard(
                candidato.get(
                    "texto",
                    "",
                ),
                seleccionado.get(
                    "texto",
                    "",
                ),
            )

            if parecido >= SIMILITUD_DUPLICADO:

                repetido = True
                break

        if not repetido:

            seleccionados.append(
                candidato
            )

        if len(seleccionados) >= limite:
            break

    return seleccionados


# ============================================================
# BÚSQUEDA HÍBRIDA
# ============================================================

def buscar_documentos_hibrido(
    consulta: str,
    limite: int = 6,
    archivo: str = None,
    drive_file_id: str = None,
):

    consulta = (
        consulta
        or ""
    ).strip()

    if not consulta:
        return []

    indice = cargar_indice()

    if not indice:
        return []

    embedding_consulta = crear_embedding(
        consulta
    )

    consulta_tokens = tokenizar(
        consulta
    )

    archivo_objetivo = (
        normalizar_texto(archivo)
        if archivo
        else None
    )

    candidatos = []

    for item in indice:

        if drive_file_id:

            if (
                item.get("drive_file_id")
                != drive_file_id
            ):
                continue

        if archivo_objetivo:

            nombre_item = normalizar_texto(
                item.get(
                    "archivo",
                    "",
                )
            )

            if nombre_item != archivo_objetivo:
                continue

        texto = (
            item.get(
                "texto",
                ""
            )
            or ""
        )

        embedding = item.get(
            "embedding"
        )

        if not texto or not embedding:
            continue

        score_semantico = similitud_coseno(
            embedding_consulta,
            embedding,
        )

        score_lexico = puntuacion_lexica(
            consulta_tokens,
            tokenizar(texto),
        )

        bonus = calcular_bonificaciones(
            consulta,
            item,
        )

        score_final = (
            PESO_SEMANTICO
            *
            score_semantico
            +
            PESO_LEXICO
            *
            score_lexico
            +
            bonus
        )

        resultado = {k: v for k, v in item.items() if k != "embedding"}

        resultado[
            "score_semantico"
        ] = float(score_semantico)

        resultado[
            "score_lexico"
        ] = float(score_lexico)

        resultado[
            "bonus"
        ] = float(bonus)

        resultado[
            "score_final"
        ] = float(score_final)

        resultado[
            "similitud"
        ] = float(score_final)

        resultado[
            "origen"
        ] = item.get(
            "origen",
            (
                "drive"
                if item.get(
                    "drive_file_id"
                )
                else "local"
            ),
        )

        candidatos.append(
            resultado
        )

    candidatos.sort(
        key=lambda item:
            item["score_final"],
        reverse=True,
    )

    candidatos = candidatos[
        :CANDIDATOS_INICIALES
    ]

    return diversificar_resultados(
        candidatos,
        limite,
    )


# ============================================================
# FRAGMENTACIÓN INTELIGENTE
# ============================================================

def dividir_texto_inteligente(
    texto: str,
    tamano_objetivo: int = 1200,
    solapamiento: int = 180,
):

    if tamano_objetivo <= 0 or not 0 <= solapamiento < tamano_objetivo:
        raise ValueError("Fragmentación inválida.")
    if not texto:
        return []

    texto = texto.replace(
        "\r\n",
        "\n",
    )

    texto = re.sub(
        r"[ \t]+",
        " ",
        texto,
    )

    texto = re.sub(
        r"\n{3,}",
        "\n\n",
        texto,
    )

    bloques = re.split(
        r"\n\s*\n",
        texto,
    )

    fragmentos = []

    actual = ""

    for bloque in bloques:

        bloque = bloque.strip()

        if not bloque:
            continue

        if (
            len(actual)
            +
            len(bloque)
            +
            2
            <=
            tamano_objetivo
        ):

            if actual:

                actual += (
                    "\n\n"
                    +
                    bloque
                )

            else:

                actual = bloque

            continue

        if actual:

            fragmentos.append(
                actual.strip()
            )

        if len(bloque) <= tamano_objetivo:

            actual = bloque
            continue

        frases = re.split(
            r"(?<=[.!?;:])\s+",
            bloque,
        )

        actual = ""

        for frase in frases:

            frase = frase.strip()

            if not frase:
                continue

            if (
                len(actual)
                +
                len(frase)
                +
                1
                <=
                tamano_objetivo
            ):

                actual = (
                    (
                        actual
                        +
                        " "
                        +
                        frase
                    )
                    .strip()
                )

            else:

                if actual:

                    fragmentos.append(
                        actual
                    )

                if len(frase) > tamano_objetivo:

                    inicio = 0

                    while inicio < len(frase):

                        fin = min(
                            inicio
                            +
                            tamano_objetivo,
                            len(frase),
                        )

                        fragmentos.append(
                            frase[
                                inicio:fin
                            ].strip()
                        )

                        if fin >= len(frase):
                            break

                        inicio = max(
                            0,
                            fin
                            -
                            solapamiento,
                        )

                    actual = ""

                else:

                    actual = frase

    if actual.strip():

        fragmentos.append(
            actual.strip()
        )

    resultado = []

    anterior = ""

    for fragmento in fragmentos:

        if anterior and solapamiento > 0:

            contexto = anterior[
                -solapamiento:
            ]

            final = (
                contexto
                +
                "\n"
                +
                fragmento
            )

        else:

            final = fragmento

        resultado.append(
            final.strip()
        )

        anterior = fragmento

    return resultado


# ============================================================
# RESUMEN DE DOCUMENTOS
# ============================================================

def obtener_estadisticas_indice():

    indice = cargar_indice()

    archivos = {}

    for item in indice:

        nombre = item.get(
            "archivo",
            "Documento desconocido",
        )

        if nombre not in archivos:

            origen = item.get(
                "origen"
            )

            if not origen:

                origen = (
                    "drive"
                    if item.get(
                        "drive_file_id"
                    )
                    else "local"
                )

            archivos[nombre] = {

                "archivo":
                    nombre,

                "fragmentos":
                    0,

                "caracteres":
                    0,

                "origen":
                    "drive" if origen == "google_drive" else origen,

                "drive_file_id":
                    item.get(
                        "drive_file_id"
                    ),

                "sha256":
                    item.get(
                        "sha256"
                    ),
            }

        archivos[nombre][
            "fragmentos"
        ] += 1

        archivos[nombre][
            "caracteres"
        ] += len(
            item.get(
                "texto",
                "",
            )
        )

        if (
            not archivos[nombre].get(
                "drive_file_id"
            )
            and
            item.get(
                "drive_file_id"
            )
        ):

            archivos[nombre][
                "drive_file_id"
            ] = item.get(
                "drive_file_id"
            )

    documentos = list(
        archivos.values()
    )

    documentos.sort(
        key=lambda item:
            item["archivo"].lower()
    )

    return {

        "fragmentos_totales":
            len(indice),

        "documentos_totales":
            len(documentos),

        "documentos":
            documentos,
    }


# ============================================================
# ELIMINAR DOCUMENTO
# ============================================================

@indice_transaccion
def eliminar_documento_indice(
    archivo: str
):

    objetivo = normalizar_texto(
        archivo
    )

    indice = cargar_indice()

    identidades = {(item.get('drive_file_id') or 'local') for item in indice
                   if normalizar_texto(item.get('archivo', '')) == objetivo}
    if len(identidades) > 1:
        raise ValueError('Hay documentos homónimos de distintos orígenes. No se eliminó ninguno.')

    nuevo_indice = []

    eliminados = 0

    for item in indice:

        nombre = normalizar_texto(
            item.get(
                "archivo",
                "",
            )
        )

        if nombre == objetivo:

            eliminados += 1

        else:

            nuevo_indice.append(
                item
            )

    if eliminados:

        guardar_indice(
            nuevo_indice
        )

    return {

        "archivo":
            archivo,

        "fragmentos_eliminados":
            eliminados,

        "fragmentos_restantes":
            len(nuevo_indice),
    }