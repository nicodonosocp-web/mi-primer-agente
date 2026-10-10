from pathlib import Path
from configuracion import DATA_DIR
from file_safety import ruta_archivo_segura
import io

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly"
]

CREDENTIALS_FILE = DATA_DIR / "credentials.json"
TOKEN_FILE = DATA_DIR / "token.json"
CARPETA_DESCARGAS = DATA_DIR / "drive_descargas"


def obtener_servicio_drive():
    credenciales = None

    if TOKEN_FILE.exists():
        credenciales = Credentials.from_authorized_user_file(
            TOKEN_FILE,
            SCOPES
        )

    if credenciales and credenciales.expired and credenciales.refresh_token:
        credenciales.refresh(Request())
        TOKEN_FILE.write_text(credenciales.to_json(), encoding="utf-8")

    if not credenciales or not credenciales.valid:
        flujo = InstalledAppFlow.from_client_secrets_file(
            CREDENTIALS_FILE,
            SCOPES
        )

        credenciales = flujo.run_local_server(
            port=0
        )

        TOKEN_FILE.write_text(
            credenciales.to_json(),
            encoding="utf-8"
        )

    return build(
        "drive",
        "v3",
        credentials=credenciales
    )


def listar_archivos_drive(limite=50):
    servicio = obtener_servicio_drive()

    resultado = servicio.files().list(
        pageSize=limite,
        fields=(
            "files("
            "id,"
            "name,"
            "mimeType,"
            "modifiedTime,"
            "size,"
            "parents"
            ")"
        ),
        orderBy="modifiedTime desc"
    ).execute()

    return resultado.get("files", [])


def buscar_archivos_drive(consulta, limite=50):
    servicio = obtener_servicio_drive()

    consulta_segura = consulta.replace("'", "\\'")

    q = (
        f"name contains '{consulta_segura}' "
        "and trashed = false"
    )

    resultado = servicio.files().list(
        q=q,
        pageSize=limite,
        fields=(
            "files("
            "id,"
            "name,"
            "mimeType,"
            "modifiedTime,"
            "size"
            ")"
        ),
        orderBy="modifiedTime desc"
    ).execute()

    return resultado.get("files", [])


def obtener_metadatos_drive(file_id):
    servicio = obtener_servicio_drive()

    return servicio.files().get(
        fileId=file_id,
        fields=(
            "id,"
            "name,"
            "mimeType,"
            "modifiedTime,"
            "size,"
            "parents,"
            "webViewLink"
        )
    ).execute()


def descargar_archivo_drive(file_id, nombre=None):
    servicio = obtener_servicio_drive()

    metadatos = obtener_metadatos_drive(file_id)

    mime_type = metadatos["mimeType"]
    nombre_original = metadatos["name"]

    CARPETA_DESCARGAS.mkdir(
        exist_ok=True
    )

    google_docs = {
        "application/vnd.google-apps.document": (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".docx"
        ),
        "application/vnd.google-apps.spreadsheet": (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xlsx"
        ),
        "application/vnd.google-apps.presentation": (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".pptx"
        ),
    }

    if mime_type in google_docs:
        export_mime, extension = google_docs[mime_type]

        request = servicio.files().export_media(
            fileId=file_id,
            mimeType=export_mime
        )

        nombre_salida = (
            nombre
            or f"{nombre_original}{extension}"
        )

    else:
        request = servicio.files().get_media(
            fileId=file_id
        )

        nombre_salida = (
            nombre
            or nombre_original
        )

    ruta_salida = ruta_archivo_segura(CARPETA_DESCARGAS, nombre_salida)

    archivo_temporal = io.BytesIO()

    downloader = MediaIoBaseDownload(
        archivo_temporal,
        request
    )

    terminado = False

    while not terminado:
        _, terminado = downloader.next_chunk()

    ruta_salida.write_bytes(
        archivo_temporal.getvalue()
    )

    return ruta_salida


def listar_carpetas_drive(limite=100):
    servicio = obtener_servicio_drive()

    resultado = servicio.files().list(
        q=(
            "mimeType = "
            "'application/vnd.google-apps.folder' "
            "and trashed = false"
        ),
        pageSize=limite,
        fields="files(id,name,modifiedTime)",
        orderBy="name"
    ).execute()

    return resultado.get("files", [])


if __name__ == "__main__":
    archivos = listar_archivos_drive(20)

    print()
    print("=" * 70)
    print("ARCHIVOS RECIENTES EN GOOGLE DRIVE")
    print("=" * 70)

    for archivo in archivos:
        print(
            f"{archivo['name']} "
            f"| {archivo['mimeType']} "
            f"| {archivo['id']}"
        )