import streamlit as st

from agents import Runner

from agente import (
    agent,
    recargar_indice,
)

from memoria import (
    inicializar_db,
    crear_conversacion,
    listar_conversaciones,
    obtener_conversacion,
    actualizar_titulo,
    eliminar_conversacion,
    agregar_mensaje,
    obtener_mensajes,
    contar_mensajes,
)

from memoria_largo_plazo import (
    inicializar_memoria_largo_plazo,
    listar_memorias,
    buscar_memorias,
    desactivar_memoria,
    contar_memorias,
)

from archivos_locales import (
    guardar_archivo_subido,
    indexar_archivo_local,
)

from voz import (
    transcribir_audio,
    generar_voz,
    VOCES_DISPONIBLES,
)


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

st.set_page_config(
    page_title="Mi Asistente IA",
    page_icon="🤖",
    layout="wide",
)


# ============================================================
# BASES DE DATOS
# ============================================================

inicializar_db()
inicializar_memoria_largo_plazo()


# ============================================================
# ESTILO
# ============================================================

st.markdown(
    """
    <style>

    .block-container {
        max-width: 1250px;
        padding-top: 1.5rem;
    }

    [data-testid="stSidebar"] {
        min-width: 290px;
        max-width: 340px;
    }

    .estado-ok {
        padding: 10px 14px;
        border-radius: 10px;
        background: rgba(0, 180, 100, 0.12);
        border: 1px solid rgba(0, 180, 100, 0.35);
        margin-bottom: 10px;
    }

    .estado-info {
        padding: 10px 14px;
        border-radius: 10px;
        background: rgba(70, 120, 255, 0.10);
        border: 1px solid rgba(70, 120, 255, 0.25);
        margin-bottom: 10px;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# ESTADO DE SESIÓN
# ============================================================

if "conversacion_id" not in st.session_state:

    conversaciones = listar_conversaciones(
        limite=1
    )

    if conversaciones:

        st.session_state.conversacion_id = (
            conversaciones[0]["id"]
        )

    else:

        st.session_state.conversacion_id = (
            crear_conversacion()
        )


if "ultimo_audio_procesado" not in st.session_state:
    st.session_state.ultimo_audio_procesado = None


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def cambiar_conversacion(
    conversacion_id,
):
    st.session_state.conversacion_id = (
        conversacion_id
    )

    st.session_state.ultimo_audio_procesado = None

    st.rerun()


def nueva_conversacion():

    nueva_id = crear_conversacion()

    st.session_state.conversacion_id = (
        nueva_id
    )

    st.session_state.ultimo_audio_procesado = None

    st.rerun()


def generar_titulo(
    texto,
):
    texto = texto.strip()

    if len(texto) <= 45:
        return texto

    return texto[:45] + "..."


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.title(
        "🤖 Mi Agente IA"
    )

    st.caption(
        "Drive + RAG + Memoria + Voz"
    )

    st.divider()

    # --------------------------------------------------------
    # NUEVA CONVERSACIÓN
    # --------------------------------------------------------

    if st.button(
        "➕ Nueva conversación",
        use_container_width=True,
        type="primary",
    ):
        nueva_conversacion()

    st.divider()

    # --------------------------------------------------------
    # ESTADO GOOGLE DRIVE
    # --------------------------------------------------------

    st.markdown(
        """
        <div class="estado-ok">
        🟢 <strong>Google Drive conectado</strong><br>
        Modo solo lectura
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --------------------------------------------------------
    # ESTADO RAG
    # --------------------------------------------------------

    recargar_indice()

    from agente import INDICE as indice_actual

    st.markdown(
        f"""
        <div class="estado-info">
        🧠 <strong>RAG activo</strong><br>
        {len(indice_actual)} fragmentos indexados
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --------------------------------------------------------
    # ESTADO MEMORIA
    # --------------------------------------------------------

    total_memorias = contar_memorias()

    st.markdown(
        f"""
        <div class="estado-info">
        💾 <strong>Memoria</strong><br>
        {total_memorias} memorias activas
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --------------------------------------------------------
    # CONFIGURACIÓN DE VOZ
    # --------------------------------------------------------

    st.divider()

    st.subheader(
        "🎙️ Voz"
    )

    voz_activada = st.toggle(
        "🔊 Respuestas por voz",
        value=True,
    )

    voz_nombre = st.selectbox(
        "Voz del asistente",
        options=list(
            VOCES_DISPONIBLES.keys()
        ),
        index=0,
        disabled=not voz_activada,
    )

    voz_seleccionada = (
        VOCES_DISPONIBLES[
            voz_nombre
        ]
    )

    reproduccion_automatica = st.toggle(
        "▶️ Reproducción automática",
        value=True,
        disabled=not voz_activada,
    )

    if voz_activada:

        st.caption(
            f"Voz activa: {voz_nombre}"
        )

    else:

        st.caption(
            "🔇 Respuestas habladas desactivadas"
        )

    st.divider()

    # --------------------------------------------------------
    # CONVERSACIONES
    # --------------------------------------------------------

    st.subheader(
        "Conversaciones"
    )

    conversaciones = listar_conversaciones(
        limite=20
    )

    for conversacion in conversaciones:

        id_conversacion = (
            conversacion["id"]
        )

        titulo = (
            conversacion["titulo"]
        )

        if (
            id_conversacion
            == st.session_state.conversacion_id
        ):

            texto_boton = (
                f"▶ {titulo}"
            )

        else:

            texto_boton = titulo

        if st.button(
            texto_boton,
            key=f"chat_{id_conversacion}",
            use_container_width=True,
        ):

            cambiar_conversacion(
                id_conversacion
            )

    # --------------------------------------------------------
    # ELIMINAR CONVERSACIÓN
    # --------------------------------------------------------

    st.divider()

    if st.button(
        "🗑️ Eliminar conversación actual",
        use_container_width=True,
    ):

        actual = (
            st.session_state.conversacion_id
        )

        eliminar_conversacion(
            actual
        )

        restantes = listar_conversaciones(
            limite=1
        )

        if restantes:

            st.session_state.conversacion_id = (
                restantes[0]["id"]
            )

        else:

            st.session_state.conversacion_id = (
                crear_conversacion()
            )

        st.session_state.ultimo_audio_procesado = None

        st.rerun()


# ============================================================
# PESTAÑAS PRINCIPALES
# ============================================================

tab_chat, tab_memoria, tab_archivos = st.tabs(
    [
        "💬 Chat",
        "🧠 Memoria",
        "📁 Archivos",
    ]
)


# ============================================================
# TAB CHAT
# ============================================================

with tab_chat:

    conversacion_id = (
        st.session_state.conversacion_id
    )

    conversacion = obtener_conversacion(
        conversacion_id
    )

    mensajes = obtener_mensajes(
        conversacion_id
    )

    st.title(
        "Asistente Personal y Documental"
    )

    if conversacion:

        st.caption(
            f"💬 {conversacion['titulo']}"
        )

    # --------------------------------------------------------
    # BIENVENIDA
    # --------------------------------------------------------

    if not mensajes:

        with st.chat_message(
            "assistant"
        ):

            st.markdown(
                """
Hola. Puedo ayudarte con:

- **Google Drive**
- **documentos indexados**
- **memoria persistente**
- **memoria de largo plazo**
- **archivos cargados manualmente**
- **entrada por voz**
- **respuestas habladas**

Puedes escribir normalmente o utilizar el micrófono.
                """
            )

    # --------------------------------------------------------
    # HISTORIAL
    # --------------------------------------------------------

    for mensaje in mensajes:

        with st.chat_message(
            mensaje["role"]
        ):

            st.markdown(
                mensaje["content"]
            )

    # --------------------------------------------------------
    # ENTRADA POR VOZ AUTOMÁTICA
    # --------------------------------------------------------

    st.divider()

    st.markdown(
        "### 🎙️ Hablar con el asistente"
    )

    st.caption(
        "Graba tu mensaje. Al terminar, "
        "se transcribirá automáticamente."
    )

    audio_grabado = st.audio_input(
        "Presiona el micrófono y habla",
        key="audio_entrada",
    )

    consulta_voz = None

    if audio_grabado is not None:

        audio_bytes = (
            audio_grabado.getvalue()
        )

        audio_id = hash(
            audio_bytes
        )

        if (
            st.session_state.ultimo_audio_procesado
            != audio_id
        ):

            try:

                with st.spinner(
                    "Transcribiendo voz..."
                ):

                    consulta_voz = (
                        transcribir_audio(
                            audio_bytes,
                            nombre_archivo="voz.wav",
                        )
                    )

                st.session_state.ultimo_audio_procesado = (
                    audio_id
                )

                if consulta_voz:

                    st.success(
                        f"🎙️ Entendido: "
                        f"{consulta_voz}"
                    )

                else:

                    st.warning(
                        "No fue posible detectar "
                        "texto en la grabación."
                    )

            except Exception as error:

                st.error(
                    "Error al transcribir "
                    "el audio:\n\n"
                    f"`{error}`"
                )

    # --------------------------------------------------------
    # ENTRADA POR TEXTO
    # --------------------------------------------------------

    consulta_texto = st.chat_input(
        "Escribe tu mensaje..."
    )

    # --------------------------------------------------------
    # DETERMINAR ENTRADA
    # --------------------------------------------------------

    if consulta_voz:

        consulta = consulta_voz

    else:

        consulta = consulta_texto

    # --------------------------------------------------------
    # PROCESAR CONSULTA
    # --------------------------------------------------------

    if consulta:

        cantidad_previa = contar_mensajes(
            conversacion_id
        )

        # ----------------------------------------------------
        # PRIMER MENSAJE = TÍTULO
        # ----------------------------------------------------

        if cantidad_previa == 0:

            nuevo_titulo = generar_titulo(
                consulta
            )

            actualizar_titulo(
                conversacion_id,
                nuevo_titulo,
            )

        # ----------------------------------------------------
        # GUARDAR MENSAJE DEL USUARIO
        # ----------------------------------------------------

        agregar_mensaje(
            conversacion_id,
            "user",
            consulta,
        )

        with st.chat_message(
            "user"
        ):

            st.markdown(
                consulta
            )

        # ----------------------------------------------------
        # OBTENER HISTORIAL COMPLETO
        # ----------------------------------------------------

        historial_agente = obtener_mensajes(
            conversacion_id
        )

        # ----------------------------------------------------
        # EJECUTAR AGENTE
        # ----------------------------------------------------

        with st.chat_message(
            "assistant"
        ):

            with st.spinner(
                "Analizando..."
            ):

                try:

                    resultado = Runner.run_sync(
                        agent,
                        historial_agente,
                    )

                    respuesta = (
                        resultado.final_output
                    )

                    # ----------------------------------------
                    # MOSTRAR TEXTO
                    # ----------------------------------------

                    st.markdown(
                        respuesta
                    )

                    # ----------------------------------------
                    # GUARDAR RESPUESTA
                    # ----------------------------------------

                    agregar_mensaje(
                        conversacion_id,
                        "assistant",
                        respuesta,
                    )

                    # ----------------------------------------
                    # GENERAR RESPUESTA HABLADA
                    # ----------------------------------------

                    if voz_activada:

                        try:

                            with st.spinner(
                                "Generando voz..."
                            ):

                                audio_respuesta = (
                                    generar_voz(
                                        respuesta,
                                        voz=voz_seleccionada,
                                    )
                                )

                            if audio_respuesta:

                                st.audio(
                                    audio_respuesta,
                                    format="audio/mp3",
                                    autoplay=(
                                        reproduccion_automatica
                                    ),
                                )

                        except Exception as error_voz:

                            st.warning(
                                "La respuesta de texto fue "
                                "generada correctamente, pero "
                                "no fue posible crear el audio."
                            )

                            st.caption(
                                f"Detalle: "
                                f"{error_voz}"
                            )

                except Exception as error:

                    st.error(
                        "Se produjo un error "
                        "al ejecutar el agente:\n\n"
                        f"`{error}`"
                    )


# ============================================================
# TAB MEMORIA
# ============================================================

with tab_memoria:

    st.title(
        "Memoria de largo plazo"
    )

    st.caption(
        "Información persistente que el agente puede "
        "recordar entre conversaciones distintas."
    )

    st.divider()

    # --------------------------------------------------------
    # FILTROS
    # --------------------------------------------------------

    col_busqueda, col_categoria = st.columns(
        [2, 1]
    )

    with col_busqueda:

        consulta_memoria = st.text_input(
            "Buscar memoria",
            placeholder=(
                "Proyecto, persona, decisión, pendiente..."
            ),
        )

    with col_categoria:

        categoria = st.text_input(
            "Categoría",
            placeholder="proyecto",
        )

    # --------------------------------------------------------
    # OBTENER MEMORIAS
    # --------------------------------------------------------

    if consulta_memoria.strip():

        memorias = buscar_memorias(
            consulta_memoria,
            limite=50,
        )

        if categoria.strip():

            memorias = [
                memoria
                for memoria in memorias
                if (
                    memoria["categoria"].lower()
                    == categoria.strip().lower()
                )
            ]

    else:

        memorias = listar_memorias(
            limite=100,
            categoria=(
                categoria.strip()
                if categoria.strip()
                else None
            ),
        )

    # --------------------------------------------------------
    # RESUMEN
    # --------------------------------------------------------

    st.metric(
        "Memorias encontradas",
        len(memorias),
    )

    st.divider()

    # --------------------------------------------------------
    # LISTADO
    # --------------------------------------------------------

    if not memorias:

        st.info(
            "No se encontraron memorias."
        )

    else:

        for memoria in memorias:

            memoria_id = (
                memoria["id"]
            )

            with st.container(
                border=True
            ):

                col_info, col_accion = st.columns(
                    [5, 1]
                )

                with col_info:

                    st.markdown(
                        f"### {memoria['clave']}"
                    )

                    st.caption(
                        f"Categoría: "
                        f"{memoria['categoria']} "
                        f"· Importancia: "
                        f"{memoria['importancia']}/5"
                    )

                    st.write(
                        memoria["contenido"]
                    )

                    if memoria.get(
                        "actualizado_en"
                    ):

                        st.caption(
                            f"Actualizado: "
                            f"{memoria['actualizado_en']}"
                        )

                    st.caption(
                        f"ID: {memoria_id}"
                    )

                with col_accion:

                    if st.button(
                        "Eliminar",
                        key=(
                            "eliminar_memoria_"
                            f"{memoria_id}"
                        ),
                        use_container_width=True,
                    ):

                        desactivar_memoria(
                            memoria_id
                        )

                        st.success(
                            "Memoria eliminada."
                        )

                        st.rerun()


# ============================================================
# TAB ARCHIVOS
# ============================================================

with tab_archivos:

    st.title(
        "Archivos"
    )

    st.caption(
        "Carga documentos directamente "
        "desde tu computador al sistema RAG."
    )

    st.divider()

    # --------------------------------------------------------
    # CARGAR DOCUMENTO
    # --------------------------------------------------------

    st.subheader(
        "Cargar documento"
    )

    archivo_subido = st.file_uploader(
        "Arrastra un archivo aquí "
        "o selecciónalo desde tu equipo",
        type=[
            "pdf",
            "docx",
            "txt",
        ],
        accept_multiple_files=False,
    )

    st.caption(
        "Formatos disponibles: PDF, DOCX y TXT."
    )

    if archivo_subido:

        st.success(
            f"Archivo seleccionado: "
            f"{archivo_subido.name}"
        )

        col1, col2 = st.columns(
            [1, 2]
        )

        with col1:

            st.write(
                "**Tamaño**"
            )

            st.write(
                f"{archivo_subido.size / 1024:.1f} KB"
            )

        with col2:

            st.write(
                "**Tipo**"
            )

            st.write(
                archivo_subido.type
                or "No informado"
            )

        st.divider()

        # ----------------------------------------------------
        # INDEXAR
        # ----------------------------------------------------

        if st.button(
            "🧠 Indexar documento",
            type="primary",
            use_container_width=True,
        ):

            try:

                with st.spinner(
                    "Guardando e indexando documento..."
                ):

                    ruta = guardar_archivo_subido(
                        archivo_subido.name,
                        archivo_subido.getvalue(),
                    )

                    resultado = indexar_archivo_local(
                        ruta
                    )

                # --------------------------------------------
                # INDEXADO CORRECTAMENTE
                # --------------------------------------------

                if (
                    resultado["estado"]
                    == "ok"
                ):

                    recargar_indice()

                    st.success(
                        "Documento indexado correctamente."
                    )

                    st.write(
                        f"**Archivo:** "
                        f"{resultado['archivo']}"
                    )

                    st.write(
                        f"**Fragmentos:** "
                        f"{resultado['fragmentos']}"
                    )

                    st.info(
                        "Ya puedes volver a "
                        "💬 Chat y consultar "
                        "este documento."
                    )

                # --------------------------------------------
                # ARCHIVO YA EXISTENTE
                # --------------------------------------------

                elif (
                    resultado["estado"]
                    == "existente"
                ):

                    st.warning(
                        resultado["mensaje"]
                    )

                # --------------------------------------------
                # ERROR
                # --------------------------------------------

                else:

                    st.error(
                        resultado["mensaje"]
                    )

            except Exception as error:

                st.error(
                    "Error durante la indexación:\n\n"
                    f"`{error}`"
                )

    # --------------------------------------------------------
    # INSTRUCCIONES
    # --------------------------------------------------------

    st.divider()

    st.subheader(
        "¿Cómo utilizarlo?"
    )

    st.markdown(
        """
1. Arrastra un **PDF, DOCX o TXT**.
2. Presiona **Indexar documento**.
3. Espera mientras se generan los embeddings.
4. Regresa a **💬 Chat**.
5. Pregunta por el contenido del archivo.

Ejemplo:

> **Busca en mis documentos las principales conclusiones del informe que acabo de cargar.**
        """
    )