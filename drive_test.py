from configuracion import DATA_DIR
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly"
]

CREDENTIALS_FILE = (DATA_DIR / "credentials.json")
TOKEN_FILE = (DATA_DIR / "token.json")


def obtener_servicio_drive():
    credenciales = None

    if TOKEN_FILE.exists():
        credenciales = Credentials.from_authorized_user_file(
            TOKEN_FILE,
            SCOPES
        )

    if credenciales and credenciales.expired and credenciales.refresh_token:
        credenciales.refresh(Request())

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

    servicio = build(
        "drive",
        "v3",
        credentials=credenciales
    )

    return servicio


def listar_archivos():
    servicio = obtener_servicio_drive()

    resultado = servicio.files().list(
        pageSize=20,
        fields="files(id,name,mimeType,modifiedTime)"
    ).execute()

    archivos = resultado.get(
        "files",
        []
    )

    if not archivos:
        print("No se encontraron archivos.")
        return

    print()
    print("=" * 70)
    print("ARCHIVOS EN GOOGLE DRIVE")
    print("=" * 70)

    for archivo in archivos:
        print(
            f"{archivo['name']} "
            f"| {archivo['mimeType']} "
            f"| {archivo['id']}"
        )


if __name__ == "__main__":
    listar_archivos()