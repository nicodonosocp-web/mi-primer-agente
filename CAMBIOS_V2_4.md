# V2.4 RC1 · GRIFO

Base: `fe9ae0a` de `main`. Rama de trabajo: `codex/v2.4-grifo`.

## Resultado

Se conservan FastAPI/WebRTC, Streamlit, CLI, tablas SQLite y formato JSON. No se modificaron cuentas Google, no se crearon eventos y no se publicó la rama durante la implementación.

### Datos y documentos

- Configuración común para datos y credenciales, anclada al proyecto; directorio alternativo opcional.
- Lectura del índice que rechaza corrupción; bloqueo interproceso de ciclos completos de lectura/modificación/escritura, archivo temporal único, `fsync` y reemplazo atómico.
- Copia del índice anterior y herramienta `respaldar.py` para SQLite/JSON.
- El indexador CLI conserva los registros ajenos al documento que actualiza.
- Confinamiento de rutas Windows/Linux y rechazo de enlaces inseguros en cargas y descargas.
- Extracción compartida; OCR por página para PDF mixto; límites de tamaño y páginas; procesamiento de cargas fuera del event loop.
- Compatibilidad con origen `google_drive`, fechas originales SQLite y ambas claves de hash.
- Operaciones de memoria serializadas para evitar inserciones concurrentes duplicadas; claves foráneas activadas sin cambiar tablas.
- Ranking híbrido compartido con Agents; embeddings excluidos de las respuestas de búsqueda.
- Eliminación bloqueada cuando un nombre representa documentos de distintos IDs Drive/orígenes.

### Calendar y servidor local

- Sesión local HttpOnly/SameSite, token CSRF, validación de Host/Origin y rechazo de peticiones cross-site.
- El booleano del modelo ya no habilita creación por `/tool`.
- Propuesta de evento validada y vinculada a sesión; confirmación sobre esos datos; cancelación y ejecución única.
- Repeticiones exitosas devuelven el resultado guardado; fallos inciertos no se reintentan automáticamente.
- Errores de free/busy no se interpretan como disponibilidad.
- `/health` no inicia OAuth y no anuncia integraciones como verificadas.
- Errores del backend reducidos y argumentos completos retirados del log `/tool`.

### Interfaz

- Diseño GRIFO blanco/verde basado en el adjunto: navegación lateral, esfera de estado, conversación y panel contextual.
- Funciones conectadas al servidor, sin respuestas ni agenda simuladas.
- Texto sin micrófono; activación posterior de voz; limpieza de recursos al fallar/desconectar.
- Historial enviado como mensajes a Realtime, no concatenado dentro de instrucciones.
- Fuentes RAG visibles, documento activo, biblioteca, agenda, búsqueda, actividad y diagnóstico local.
- Cambiar de conversación desconecta la sesión activa para no mezclar historial.
- Panel contextual desplegable en pantallas pequeñas; historial móvil en Sistema.
- Proyectos, tareas y automatizaciones permanecen deshabilitados para V2.5.

## Validación realizada

- 23 casos de integración Python en una copia temporal: SQLite, persistencia tras reiniciar, rutas, texto/DOCX/PDF, OCR mixto simulado, Drive simulado, Calendar, CSRF/origen, corrupción, seis escritores en procesos separados, respaldos y arranque Streamlit/CLI.
- 4 pruebas de nombres, rutas, enlaces y `.gitignore`.
- 3 escenarios JavaScript de aprobación/cancelación Calendar; el valor sugerido por el modelo no sustituye el diálogo.
- Navegador Chromium: texto sin micrófono, activación de voz, cierre de pistas, navegación sin perder mensajes, cancelación y ausencia de desbordamiento de página en 1920×1080, 1440×900, 1366×768, 1024×768, 768×1024 y 390×844.
- Sintaxis Python/JavaScript, `pip check`, revisión de diff y control de archivos sensibles.

Las pruebas usan datos sintéticos y servicios externos simulados. No certifican reconocimiento de voz, OCR remoto, OAuth ni audio real. La descarga estándar del navegador falló en este entorno; se utilizó Chromium 133 como ejecutable alternativo para la revisión visual.

## Límites y siguientes pasos

- Validación manual Windows/WebRTC/OpenAI/Google pendiente. RC1 todavía no es la versión estable.
- Sesiones y propuestas en memoria: usar un único worker. Se invalidan al reiniciar. No es una solución de autenticación multiusuario ni para publicar en Internet.
- Bloqueo del índice durante indexación: favorece integridad frente a paralelismo; grandes trabajos pueden hacer esperar otras operaciones. No ejecutar simultáneamente una versión antigua que ignore el bloqueo.
- Biblioteca y selección aún se basan en nombres. Se bloquean borrados ambiguos, pero falta selección completa por identidad documental para homónimos.
- Persisten algunos adaptadores/extractores antiguos por compatibilidad. La extracción utilizada en los flujos principales ya está centralizada; no se hizo una reescritura total del servidor.
- `indice.json` continúa en el historial anterior de Git. No se reescribió historia ni se modificó visibilidad del repositorio.
- La suite no constituye una auditoría exhaustiva de CVE ni una certificación de ausencia de secretos históricos.

Ver README para instalación, respaldo y validación en Windows. Publicar esta rama y cualquier integración en `main` requieren autorización del propietario.
