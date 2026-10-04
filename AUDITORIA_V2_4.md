# Auditoría y evolución a V2.4

Actualización: los módulos faltantes ya se recuperaron y las pruebas de
integración pasan. La sección inicial conserva los hallazgos del commit base;
consultar el segundo incremento al final para el estado vigente.

Fecha: 2026-10-04. Base: `24ece1b` (V2.3), rama `main`.
Revisión estática de todos los archivos de código versionados, README,
dependencias, reglas Git e historial de nombres de archivos. Del índice se
inspeccionó únicamente estructura y cantidad, sin reproducir contenido.
No se accedió a credenciales, cuentas externas ni bases de datos del usuario.

## Estado y arquitectura

La versión Windows reportada como funcional no es reproducible con este clon:
faltan `memoria.py`, `memoria_largo_plazo.py` y `rag_drive.py`, importados por
el servidor y ausentes también del historial Git disponible. No se debe inventar
su implementación ni el esquema SQLite. No hay suite automatizada en la base.

| Componente | Responsabilidad y dependencias |
|---|---|
| `realtime.html` | Pantalla única CSS/JS, chat, historial, biblioteca, documento activo, agenda y confirmación visual de eventos. WebRTC directo a OpenAI con secreto efímero de `/token`; herramientas por `/tool`. El chat escrito también abre micrófono y Realtime. |
| `realtime_server.py` | FastAPI monolítico: historial, memoria, uploads, extracción, OCR, RAG, biblioteca, Drive, Calendar y emisión de secretos efímeros. Inicializa clientes y BD durante importación. |
| `rag_mejorado.py` | Índice JSON compartido, embeddings, ranking 78% semántico + 22% léxico, bonificaciones, diversificación, fragmentación y borrado. |
| `indexar.py` | Indexador CLI anterior, sustituye el índice completo con documentos locales; extracción sin OCR. |
| `agente.py` | CLI Agents SDK; índice cargado al arrancar, búsqueda solo semántica, historial en RAM. No es el motor del frontend Realtime. |
| `drive_tools.py`, `drive_test.py` | OAuth Drive readonly, listado, búsqueda, descarga y exportación. El segundo es un script manual, no una prueba automatizada. |
| `calendar_tools.py` | OAuth Calendar, consultas y creación; incluye eliminación no expuesta por `/tool`. |
| Módulos ausentes | SQLite de conversaciones y memoria duradera; indexación de archivos Drive. Compatibilidad no verificable hasta recuperarlos. |

El índice versionado contiene 47 registros con `archivo`, `fragmento`, `texto`
y `embedding`. El servidor añade opcionalmente `origen` y `sha256`; el RAG
admite `drive_file_id`. Se mantendrá este formato. No se inspeccionó `memoria.db`:
no está en el clon y no se necesita su contenido para recuperar el código.

## Riesgos comprobados

| Prioridad | Hallazgo | Consecuencia / medida |
|---|---|---|
| Bloqueante | Tres módulos locales ausentes | No puede arrancarse ni verificarse el producto completo desde Git. Recuperar originales V2.3. |
| Alta | `indice.json` ya está versionado aunque esté ignorado | `.gitignore` no lo retira. El repositorio es público; su historial también contiene documentos eliminados. Evaluar con el propietario retirada y saneamiento histórico; no reescribir historia automáticamente. |
| Alta | `/rag/reindex` une entrada libre con carpeta local | Puede leer/indexar rutas externas, incluyendo secretos. Validar nombre, extensión y confinamiento antes de leer o modificar el índice. |
| Alta | Descarga Drive usa nombres sin confinamiento | Un nombre remoto o argumento puede escapar de la carpeta de descargas. Validar antes de escribir. |
| Alta | Falta FastAPI, PyMuPDF y paquetes Google en requirements | Instalación declarada incompleta. Archivo UTF-16 y pywin32 sin marcador de plataforma. No se ha validado disponibilidad ni compatibilidad de los pins. Recuperar inventario del entorno Windows estable antes de reemplazarlos. |
| Alta | `rag_mejorado` crea OpenAI antes del `load_dotenv()` del servidor | Con clave solo en `.env`, el orden de imports puede impedir iniciar. Centralizar configuración antes de crear clientes y probar arranque limpio. |
| Alta | Calendar confía en booleano recibido; sin autenticación de aplicación | El frontend confirma realmente, pero una llamada directa puede afirmar autorización. Diseñar propuesta inmutable + confirmación desde sesión de usuario + ejecución única; añadir protección de origen/sesión. |
| Alta | Escrituras JSON concurrentes y rollback con instantánea antigua | Actualizaciones pueden perderse; servidor usa temporal fijo, RAG temporal único, CLI escritura directa. Unificar transacciones con bloqueo interproceso y reemplazo atómico sin cambiar esquema. |
| Alta | Lectura de JSON da lista vacía ante corrupción | Una escritura posterior puede ocultar pérdida de datos. Fallar sin sobrescribir y ofrecer recuperación. |
| Media | OCR solo cuando todo el PDF carece de texto | PDFs mixtos pierden páginas escaneadas. OCR selectivo por página con límites de páginas/coste. |
| Media | Upload lee todo antes de aplicar 25 MB; procesamiento síncrono en async | Memoria no acotada por ese control y bloqueo de otras peticiones. Lectura limitada y trabajo fuera del event loop. |
| Media | `/health` llama servicios OAuth | Puede abrir navegador, refrescar tokens o bloquear; declara capacidades como activas sin comprobarlas. Separar diagnóstico local y comprobación explícita de integraciones. |
| Media | Herramientas imprimen argumentos y devuelven excepciones crudas | Riesgo de divulgar información personal o detalles internos en logs/respuestas. Redactar datos y usar errores controlados. |
| Media | Disponibilidad Calendar ignora errores por calendario | Puede informar libre al fallar la consulta. Tratar errores y validar rangos/zonas. |
| Media | Drive tiene rutas relativas y refresco no siempre persistido | Comportamiento depende del directorio de arranque. Anclar rutas y probar renovación. |
| Media | Estadísticas omiten `drive_file_id` | Biblioteca pierde identificador aunque exista en índice; agrupación por nombre mezcla documentos homónimos. |
| Media | UI no maneja todos los errores HTTP/red y conexión fallida no libera recursos | Historial visual puede indicar guardado fallido; micrófono puede seguir abierto. Agregar manejo y limpieza, conservando pantalla única. |
| Media | Fragmentación acepta solapamiento >= tamaño | Puede no avanzar ante frases largas si se usan parámetros inválidos. Validar parámetros. |
| Baja | README incompleto y sin flujo Windows actual | Documentar instalación, arranque, copias, pruebas y recuperación tras validar entorno. |

No aparecieron los cuatro nombres de secretos prohibidos ni `memoria.db` en
los nombres versionados del historial consultado. Esto no es una certificación
de ausencia de secretos embebidos en cualquier contenido histórico.

## Plan V2.4 y criterios de aceptación

1. Primer incremento: reglas Git adicionales, rutas confinadas y pruebas sin
   cuentas. Mantener API, UI, formatos, nombres de BD y versión pública V2.3.
2. Recuperar los tres módulos originales; inventariar dependencias del entorno
   estable; reparar orden de configuración y probar instalación Windows limpia.
3. Pruebas de persistencia sobre fixtures sintéticos y copia de esquema sin
   datos personales: crear, recuperar, reiniciar, recordar y buscar. Diseñar
   backup y transacciones de índice sin migrar su formato.
4. Propuesta/confirmación/ejecución idempotente Calendar, validación temporal,
   errores de disponibilidad y pruebas de denegación/cancelación/reintento.
5. OCR de PDF mixto, límites de upload, robustez UI y diagnóstico sin OAuth.
6. Validación Windows: WebRTC real, texto, historial tras reinicio, memoria,
   ranking híbrido, PDF/DOCX/TXT, escaneado/mixto, biblioteca, documento activo,
   Drive readonly, consultas y evento de prueba únicamente autorizado, una
   pantalla. Solo entonces etiquetar V2.4 estable.

No publicar, hacer push ni modificar Calendar/Drive durante esta auditoría.
Los commits se preparan localmente para revisión. Cambiar visibilidad del repo,
sanear historia o publicar la rama requiere confirmación explícita.

## Primer incremento implementado y verificado

- `file_safety.py`: nombres portables, sin rutas absolutas/relativas, escapes,
  dispositivos Windows ni enlaces simbólicos; extensión permitida para RAG local.
- Aplicado a upload, reindexación local y escritura de descargas Drive. Se
  conserva la reindexación Drive por ID, incluso con título sin extensión.
- `.gitignore`: variantes `.env`, auxiliares SQLite WAL/SHM, temporales del índice
  y carpeta de backups. No se retiró el índice ya versionado ni se alteró historia.
- 12 pruebas Python y 3 escenarios JS aprobados; sintaxis de todos los Python
  y del script HTML válida; `git diff --check` sin errores.
- Pruebas Python de funciones originales compiladas de su AST, con colaboradores
  simulados para evitar imports faltantes y OAuth. Prueba RAG con índice sintético
  y embeddings fijos. JS ejecuta funciones originales en VM con confirmación y
  HTTP simulados. **No equivalen a importar/arrancar FastAPI ni probar Windows,
  SQLite real, OCR real, APIs externas o audio WebRTC.**
- No se cambió `realtime.html`, `indice.json`, el formato SQLite ni el archivo de
  dependencias. La etiqueta de producto sigue en V2.3: V2.4 está en desarrollo.
- Persisten los riesgos documentados fuera de este incremento, incluyendo
  concurrencia, autenticación, confirmación del backend e instalación incompleta.

Ejecución desde la raíz (Python con NumPy instalado y Node.js):

```powershell
python -m unittest discover -s tests -v
node tests/calendar_confirmation.cjs
```

Para desbloquear la siguiente etapa hacen falta los originales V2.3 de
`memoria.py`, `memoria_largo_plazo.py` y `rag_drive.py`, sin credenciales ni BD.


## Segundo incremento: integración de originales V2.3

Los tres módulos fueron aportados por el usuario e incorporados primero sin
modificaciones. Se verificaron sus tablas originales: `conversaciones`,
`mensajes` y `memoria_largo_plazo`, dentro de `memoria.db`.

Cambios funcionales acotados:

- `configuracion.py` carga `.env` desde la raíz antes de crear clientes y define
  una carpeta de datos común. Por defecto se conservan nombres y ubicación
  junto al proyecto. `MI_AGENTE_DATA_DIR` permite un directorio alternativo
  existente, sin mover archivos ni modificar el esquema. Todos los flujos CLI,
  web, memoria y Google usan esa misma ubicación.
- El historial reconoce `creado_en` y `actualizado_en`, las columnas originales,
  además de los alias que ya aceptaba. La respuesta mantiene sus nombres API.
- El servidor reconoce `google_drive` y `drive_file_id` como origen Drive.
  La biblioteca conserva ese ID para reindexar los registros antiguos.
- Los fallos de descarga/extracción Drive ahora elevan errores: no se responde
  HTTP 200 como si se hubiera indexado. El rollback existente conserva el índice
  en la prueba secuencial. Su riesgo de concurrencia sigue pendiente.
- `requirements.txt` pasó de UTF-16 a UTF-8, conservando pins anteriores, con
  FastAPI, PyMuPDF y dependencias Google añadidas. `pywin32` queda restringido a
  Windows. `requirements-dev.txt` añade el cliente HTTP de pruebas y soporte
  SOCKS para el proxy del entorno de validación.
- Se normalizaron los finales de línea de los originales en un commit separado,
  para distinguir cambios de formato de cambios funcionales.

Corrección del diagnóstico inicial: el `rag_drive.py` original ejecutaba
`load_dotenv()` antes de importar `rag_mejorado` desde el servidor. Por tanto,
una vez recuperado, ese camino ya cargaba la clave; no se confirmó un fallo de
orden en ese flujo. La configuración compartida elimina esa dependencia lateral
entre módulos y permite importar RAG directamente con el `.env` correcto.

Validación del segundo incremento:

- Instalación desde cero de `requirements-dev.txt` en un venv Linux/Python 3.12,
  sin paquetes del sistema; `pip check`: sin incompatibilidades declaradas.
- 12 pruebas aisladas Python y 11 casos con la aplicación FastAPI completa
  (ejecutados mediante una prueba contenedora): todos aprobados.
- 3 escenarios JS originales de confirmación Calendar: aprobados.
- Arranque desde otra carpeta, carga de `.env` ficticio, historial y persistencia
  tras otro proceso, columnas SQLite originales, upsert de memoria, TXT/DOCX/PDF,
  render PDF escaneado con transcripción simulada, búsqueda con documento activo,
  biblioteca y reindexación de registros `google_drive`, fallo Drive y conservación
  del índice, denegación Calendar y contrato del secreto efímero Realtime.
- Las APIs externas se simulan y se bloquean sockets: no se creó ningún evento,
  no se usaron claves reales ni se leyó la base de datos personal.

Pendiente antes de declarar V2.4 estable: transacciones concurrentes del índice,
confirmación vinculada a sesión en backend, OCR mixto, diagnóstico sin OAuth,
mejoras de errores UI y comprobación real Windows/WebRTC. La UI y etiqueta V2.3
siguen intactas. Los commits permanecen locales hasta autorización de publicación.
