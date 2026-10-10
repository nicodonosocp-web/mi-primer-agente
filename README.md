# GRIFO · Asistente personal multimodal

V2.4 RC1, basada en `fe9ae0a`. Mantiene FastAPI/WebRTC y la interfaz alternativa Streamlit. La versión candidata requiere validación de audio y servicios reales en Windows antes de declararse estable.

## Instalación en Windows

Python 3.12 y PowerShell. Desde la carpeta del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip check
```

Conserva tu `.env` con `OPENAI_API_KEY`, `credentials.json`, `token.json`, `calendar_token.json`, `indice.json` y `memoria.db` localmente. No los subas a Git ni al chat.

Antes de actualizar, detén las interfaces y respalda tus datos:

```powershell
python respaldar.py
```

El respaldo incluye SQLite mediante su API de copia y el índice JSON; no copia credenciales. Conserva también tus carpetas de documentos. Los respaldos se guardan en `backups/` y quedan excluidos de Git.

## Arranque

```powershell
python -m uvicorn realtime_server:app --host 127.0.0.1 --port 8000
```

Abre http://127.0.0.1:8000. Usa **un solo proceso**: las sesiones y propuestas pendientes son temporales en memoria y caducan al reiniciar. No publiques este servidor en Internet ni lo enlaces a `0.0.0.0`; es una aplicación personal local, no un servicio multiusuario.

Alternativa conservada:

```powershell
python -m streamlit run app.py --server.address 127.0.0.1
```

También siguen disponibles `python agente.py` y `python indexar.py`. El indexador CLI conserva los documentos de otros orígenes; ya no reemplaza todo el índice.

## Datos y compatibilidad

Los archivos se buscan junto al proyecto, independientemente de la carpeta desde la que se lance Python. Si tus datos ya viven en otra carpeta, puedes definir `MI_AGENTE_DATA_DIR` con su ruta absoluta. No se mueven archivos automáticamente.

Se conservan las tablas `conversaciones`, `mensajes`, `memoria_largo_plazo` y el formato de lista JSON del índice. Se reconocen `sha256`/`file_hash` y `drive`/`google_drive`. Las escrituras del índice están serializadas entre procesos y conservan la última versión válida en `backups/indice.anterior.json`. Ante corrupción se detienen: no se interpreta el índice como vacío.

Para recuperar un índice dañado, detén ambas interfaces, conserva una copia del archivo dañado y restaura un respaldo válido. No mezcles procesos de V2.3 y V2.4 sobre los mismos datos: V2.3 no respeta el bloqueo nuevo.

## Funciones

- Interfaz GRIFO blanca y verde, con desplazamiento dentro de paneles y diseño adaptable.
- Chat escrito sin solicitar micrófono; voz activada con el botón correspondiente.
- Historial persistente, memoria, búsqueda híbrida, biblioteca, fuentes y documento activo.
- PDF, DOCX y TXT: 25 MB por carga. PDF: hasta 100 páginas; OCR por página sin texto. El OCR envía esas páginas a OpenAI y consume API. `GRIFO_MODELO_OCR` permite configurar el modelo sin editar código.
- Drive solo lectura. Calendar se consulta al solicitarlo, no durante el arranque ni el diagnóstico.
- Calendar: propuesta de diez minutos, revisión explícita de todos sus datos, confirmación desde la misma sesión y ejecución única. Si el resultado externo es incierto, no hay reintento automático: consulta la agenda antes de proponer otro evento.
- Proyectos, tareas y automatizaciones se muestran como próximos, sin datos simulados.

Al cambiar conversación, la sesión de voz se desconecta para evitar mezclar historiales. En pantalla pequeña, el historial está en el panel Sistema.

## Pruebas

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
node tests/calendar_confirmation.cjs
```

Los tests usan una copia temporal, SQLite sintético y APIs simuladas. Bloquean sockets externos. No abren OAuth ni usan datos personales.

Pruebas de interfaz opcionales (requieren Node.js y Chromium de Playwright):

```powershell
npm install
npx playwright install chromium
npm test
```

`CHROME_EXECUTABLE` permite señalar un Chromium existente. No se realizan llamadas reales: las rutas HTTP, WebRTC y micrófono son simulados.

## Comprobación final en Windows

1. Respaldar, instalar y ejecutar las pruebas anteriores.
2. Abrir GRIFO; escribir sin permiso de micrófono y recuperar historial tras reiniciar.
3. Activar voz, hablar, interrumpir y desconectar; comprobar que el micrófono se libera.
4. Cargar TXT/DOCX/PDF textual, escaneado y mixto. Seleccionar documento activo, buscar, reindexar y quitar del RAG.
5. Consultar Drive y Calendar. Cancelar una propuesta y verificar que no se crea el evento.
6. Solo si autorizas un evento real de prueba: confirmar una propuesta y verificar una única creación.

No hay validación real de Windows/WebRTC/Google realizada desde el entorno de desarrollo. Revisa `CAMBIOS_V2_4.md` para conocer alcance y límites.
