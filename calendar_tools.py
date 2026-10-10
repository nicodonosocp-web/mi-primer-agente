import os
from datetime import datetime, timedelta
from pathlib import Path
from configuracion import DATA_DIR

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


# ============================================================
# CONFIGURACIÓN
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

CREDENTIALS_PATH = DATA_DIR / "credentials.json"

TOKEN_PATH = DATA_DIR / "calendar_token.json"

SCOPES = [
    "https://www.googleapis.com/auth/calendar"
]


# ============================================================
# AUTENTICACIÓN
# ============================================================

def obtener_servicio_calendar():

    credenciales = None

    if TOKEN_PATH.exists():

        credenciales = Credentials.from_authorized_user_file(
            str(TOKEN_PATH),
            SCOPES,
        )


    if (
        not credenciales
        or
        not credenciales.valid
    ):

        if (
            credenciales
            and
            credenciales.expired
            and
            credenciales.refresh_token
        ):

            credenciales.refresh(
                Request()
            )

        else:

            if not CREDENTIALS_PATH.exists():

                raise FileNotFoundError(
                    "No se encontró credentials.json"
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH),
                SCOPES,
            )

            credenciales = flow.run_local_server(
                port=0
            )


        TOKEN_PATH.write_text(
            credenciales.to_json(),
            encoding="utf-8",
        )


    return build(
        "calendar",
        "v3",
        credentials=credenciales,
    )


# ============================================================
# CALENDARIOS
# ============================================================

def listar_calendarios():

    servicio = obtener_servicio_calendar()

    resultado = (
        servicio.calendarList()
        .list()
        .execute()
    )

    calendarios = []

    for item in resultado.get(
        "items",
        [],
    ):

        calendarios.append(
            {
                "id":
                    item.get("id"),

                "nombre":
                    item.get(
                        "summary"
                    ),

                "principal":
                    item.get(
                        "primary",
                        False,
                    ),

                "zona_horaria":
                    item.get(
                        "timeZone"
                    ),
            }
        )

    return calendarios


# ============================================================
# NORMALIZACIÓN
# ============================================================

def normalizar_evento(
    evento
):

    inicio = evento.get(
        "start",
        {},
    )

    fin = evento.get(
        "end",
        {},
    )

    return {
        "id":
            evento.get("id"),

        "titulo":
            evento.get(
                "summary",
                "(Sin título)",
            ),

        "descripcion":
            evento.get(
                "description",
                "",
            ),

        "ubicacion":
            evento.get(
                "location",
                "",
            ),

        "inicio":
            (
                inicio.get(
                    "dateTime"
                )
                or
                inicio.get(
                    "date"
                )
            ),

        "fin":
            (
                fin.get(
                    "dateTime"
                )
                or
                fin.get(
                    "date"
                )
            ),

        "estado":
            evento.get(
                "status"
            ),

        "enlace":
            evento.get(
                "htmlLink"
            ),

        "organizador":
            (
                evento
                .get(
                    "organizer",
                    {},
                )
                .get(
                    "email"
                )
            ),
    }


# ============================================================
# PRÓXIMOS EVENTOS
# ============================================================

def listar_eventos(
    limite=20,
    calendar_id="primary",
):

    servicio = obtener_servicio_calendar()

    ahora = (
        datetime.utcnow()
        .isoformat()
        +
        "Z"
    )

    resultado = (
        servicio.events()
        .list(
            calendarId=calendar_id,
            timeMin=ahora,
            maxResults=max(
                1,
                min(
                    int(limite),
                    100,
                ),
            ),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    return [
        normalizar_evento(
            evento
        )
        for evento
        in resultado.get(
            "items",
            [],
        )
    ]


# ============================================================
# EVENTOS POR RANGO
# ============================================================

def eventos_entre(
    inicio_iso,
    fin_iso,
    calendar_id="primary",
):

    servicio = obtener_servicio_calendar()

    resultado = (
        servicio.events()
        .list(
            calendarId=calendar_id,
            timeMin=inicio_iso,
            timeMax=fin_iso,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    return [
        normalizar_evento(
            evento
        )
        for evento
        in resultado.get(
            "items",
            [],
        )
    ]


# ============================================================
# BUSCAR EVENTOS
# ============================================================

def buscar_eventos(
    consulta,
    limite=20,
    calendar_id="primary",
):

    consulta = (
        consulta
        or ""
    ).strip()

    if not consulta:
        return []

    servicio = obtener_servicio_calendar()

    ahora = (
        datetime.utcnow()
        -
        timedelta(
            days=365
        )
    ).isoformat() + "Z"

    futuro = (
        datetime.utcnow()
        +
        timedelta(
            days=730
        )
    ).isoformat() + "Z"

    resultado = (
        servicio.events()
        .list(
            calendarId=calendar_id,
            q=consulta,
            timeMin=ahora,
            timeMax=futuro,
            singleEvents=True,
            orderBy="startTime",
            maxResults=max(
                1,
                min(
                    int(limite),
                    100,
                ),
            ),
        )
        .execute()
    )

    return [
        normalizar_evento(
            evento
        )
        for evento
        in resultado.get(
            "items",
            [],
        )
    ]


# ============================================================
# DISPONIBILIDAD
# ============================================================

def consultar_disponibilidad(
    inicio_iso,
    fin_iso,
    calendar_id="primary",
):

    servicio = obtener_servicio_calendar()

    cuerpo = {
        "timeMin":
            inicio_iso,

        "timeMax":
            fin_iso,

        "items": [
            {
                "id":
                    calendar_id
            }
        ],
    }

    resultado = (
        servicio.freebusy()
        .query(
            body=cuerpo
        )
        .execute()
    )

    calendario = (
        resultado
        .get(
            "calendars",
            {},
        )
        .get(
            calendar_id,
            {},
        )
    )

    if calendario.get("errors") or "busy" not in calendario:
        raise RuntimeError("No se pudo comprobar la disponibilidad del calendario.")

    ocupados = calendario.get(
        "busy",
        [],
    )

    return {
        "disponible":
            len(ocupados) == 0,

        "ocupados":
            ocupados,
    }


# ============================================================
# CREAR EVENTO
# ============================================================

def crear_evento(
    titulo,
    inicio_iso,
    fin_iso,
    descripcion="",
    ubicacion="",
    calendar_id="primary",
    zona_horaria="America/Santiago",
):

    servicio = obtener_servicio_calendar()

    cuerpo = {
        "summary":
            titulo,

        "description":
            descripcion,

        "location":
            ubicacion,

        "start": {
            "dateTime":
                inicio_iso,

            "timeZone":
                zona_horaria,
        },

        "end": {
            "dateTime":
                fin_iso,

            "timeZone":
                zona_horaria,
        },
    }

    evento = (
        servicio.events()
        .insert(
            calendarId=calendar_id,
            body=cuerpo,
        )
        .execute()
    )

    return normalizar_evento(
        evento
    )


# ============================================================
# ELIMINAR EVENTO
# ============================================================

def eliminar_evento(
    event_id,
    calendar_id="primary",
):

    servicio = obtener_servicio_calendar()

    servicio.events().delete(
        calendarId=calendar_id,
        eventId=event_id,
    ).execute()

    return {
        "eliminado":
            True,

        "event_id":
            event_id,
    }