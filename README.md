# Mi primer agente IA

Asistente local para Windows con Python, FastAPI, voz Realtime por WebRTC,
chat escrito, conversaciones SQLite, memoria de largo plazo, RAG híbrido,
PDF/DOCX/TXT, OCR, biblioteca documental, Drive de lectura y Google Calendar.
La interfaz está contenida en `realtime.html`, en una sola pantalla.

La versión estable de referencia es **V2.3**. La rama
`codex/v2.4-audit-hardening` contiene incrementos de **V2.4 en desarrollo**;
no es todavía una versión validada en Windows con servicios reales.

## Preparar el entorno en Windows

Usar una copia de desarrollo; conservar la instalación V2.3 y una copia privada
externa de sus datos antes de probar una versión nueva. No sobrescribir ni
volver a generar `indice.json` o `memoria.db` para instalar estos cambios.

En PowerShell, desde la raíz del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip check
```

Configurar `OPENAI_API_KEY` en el `.env` local de la raíz. Mantener los archivos
OAuth `credentials.json`, `token.json` y `calendar_token.json` únicamente en
el equipo. Nunca incluirlos en commits, adjuntos ni capturas.

Arranque para uso local:

```powershell
python -m uvicorn realtime_server:app --host 127.0.0.1 --port 8000
```

Abrir `http://127.0.0.1:8000`. La creación de eventos conserva la confirmación
visual antes de llamar a Calendar. El backend todavía requiere mejoras de
verificación de autorización, descritas en la auditoría; no exponer el servidor
públicamente. Las llamadas reales de voz, embeddings y OCR utilizan OpenAI.

## Datos y compatibilidad

Todos los módulos usan la misma carpeta de datos: por defecto, la raíz del
proyecto. Así arrancar desde otro directorio no crea una segunda `memoria.db`
ni un índice diferente. No hay migración de tablas ni conversión del JSON.

Opcionalmente `MI_AGENTE_DATA_DIR` permite elegir una carpeta existente. Si es
relativa, se interpreta respecto al proyecto. La variable cambia la ubicación
buscada, **no mueve datos**. Incluye SQLite, índice, documentos y archivos OAuth;
`.env` e interfaz permanecen en la raíz del proyecto.

Si antes se iniciaba el programa desde una carpeta diferente, localizar la base
utilizada por V2.3 y seleccionar esa carpeta explícitamente antes de probar.

`indice.json` sigue versionado por la historia previa aunque esté en `.gitignore`.
No agregar nuevos contenidos documentales a Git. Su retirada y el saneamiento
histórico requieren revisión y autorización del propietario.

## Pruebas de desarrollo

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
node tests/calendar_confirmation.cjs
```

Node.js solo se necesita para las pruebas JavaScript. Las pruebas de integración
copian el código a una carpeta temporal, crean una clave ficticia y bloquean
conexiones de red. Usan FastAPI y SQLite reales; OpenAI y Google están simulados.
No leen los archivos OAuth ni la base del usuario. El entorno de pruebas Linux
con Python 3.12 se instaló desde cero y pasó `pip check`; Windows/Python 3.14
requiere validación adicional.

El historial CLI de `agente.py` es en memoria y su RAG solo semántico; el flujo
web usa el servidor Realtime y RAG híbrido. `indexar.py` es un indexador antiguo
que reemplaza el índice: no ejecutarlo sobre un índice existente sin respaldo.

Consultar [AUDITORIA_V2_4.md](AUDITORIA_V2_4.md) para arquitectura, riesgos y
trabajo pendiente.
