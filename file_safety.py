"""Confinamiento de archivos portable entre Windows y Linux."""
from pathlib import Path, PureWindowsPath


def ruta_archivo_segura(carpeta, nombre, extensiones=None):
    """Valida sin escribir; rechaza rutas, nombres Windows y enlaces inseguros.

    Los permisos locales siguen siendo necesarios contra cambios concurrentes
    de enlaces por otros procesos.
    """
    if not isinstance(nombre, str) or not nombre or nombre != nombre.strip():
        raise ValueError("Nombre de archivo inválido.")
    if any(ord(c) < 32 or c in '<>:"/\\|?*' for c in nombre):
        raise ValueError("Se requiere un nombre de archivo, no una ruta.")
    if nombre in {".", ".."} or nombre.endswith("."):
        raise ValueError("Nombre de archivo inválido.")
    dispositivo = nombre.split(".", 1)[0].rstrip(" ").upper()
    reservados = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    reservados.update(f"{prefijo}{n}" for prefijo in ("COM", "LPT")
                      for n in "123456789¹²³")
    if dispositivo in reservados or PureWindowsPath(nombre).drive:
        raise ValueError("Nombre reservado por Windows.")
    if extensiones is not None and Path(nombre).suffix.lower() not in extensiones:
        raise ValueError("Solo PDF, DOCX y TXT.")
    base = Path(carpeta).resolve()
    ruta = base / nombre
    if ruta.is_symlink() or ruta.resolve().parent != base:
        raise ValueError("El archivo debe permanecer dentro de su carpeta.")
    return ruta
