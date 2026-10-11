"""Consultas de carpetas de Drive de solo lectura, con paginación explícita."""


def escapar_consulta(valor):
    return valor.replace('\\', '\\\\').replace("'", "\\'")


def consultar_carpetas(servicio, *, nombre='', carpeta_id=None, limite=20, pagina=None):
    filtros = ['trashed = false']
    if carpeta_id is None:
        filtros.append("mimeType = 'application/vnd.google-apps.folder'")
        if nombre.strip():
            filtros.append("name contains '" + escapar_consulta(nombre.strip()) + "'")
    else:
        if not carpeta_id.strip():
            raise ValueError('Se requiere el ID de la carpeta.')
        filtros.append("'" + escapar_consulta(carpeta_id.strip()) + "' in parents")
    opciones = dict(
        q=' and '.join(filtros), pageSize=max(1, min(int(limite), 100)),
        fields='nextPageToken,incompleteSearch,files(id,name,mimeType,webViewLink)',
        orderBy='folder,name', supportsAllDrives=True, includeItemsFromAllDrives=True,
    )
    if pagina:
        opciones['pageToken'] = pagina
    respuesta = servicio.files().list(**opciones).execute()
    return {
        'archivos': respuesta.get('files', []),
        'siguiente_pagina': respuesta.get('nextPageToken'),
        'busqueda_incompleta': respuesta.get('incompleteSearch', False),
    }
