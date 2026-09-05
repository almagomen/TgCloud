import os
import time
import json
import asyncio
import mimetypes
import shutil
import tempfile
import logging
from typing import Tuple

from telethon import TelegramClient, events, Button
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from FastTelethonhelper import fast_download
from dotenv import load_dotenv

# ==================== CONFIGURACIÓN DE LOGS ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Silenciar los logs informativos de Telethon (solo mostrará WARNING o ERROR)
logging.getLogger('telethon').setLevel(logging.WARNING)
# Silenciar también la librería de Google si genera mucho texto
logging.getLogger('googleapiclient').setLevel(logging.WARNING)

# ==================== CONFIGURACIÓN DE ENTORNO ====================
load_dotenv()

# Validación consolidada de variables obligatorias sin repetición de código
required_vars = ["API_ID", "API_HASH", "BOT_TOKEN", "FOLDER_ID", "OWNERS", "SERVER_DIR"]
env_vars = {var: os.getenv(var) for var in required_vars}
missing_vars = [var for var, val in env_vars.items() if not val]

if missing_vars:
    raise ValueError(f"Error crítico: Faltan definir en el .env las variables: {', '.join(missing_vars)}")

# Asignaciones limpias tras la validación
API_ID = int(env_vars["API_ID"])
API_HASH = env_vars["API_HASH"]
BOT_TOKEN = env_vars["BOT_TOKEN"]
FOLDER_ID = env_vars["FOLDER_ID"]
SERVER_DIR = env_vars["SERVER_DIR"]
OWNERS_IDS = [int(x.strip()) for x in env_vars["OWNERS"].split(",") if x.strip()]

TOKEN_FILE = os.getenv("TOKEN_FILE", os.path.expanduser("~/.hermes/google_token.json"))

os.makedirs(SERVER_DIR, exist_ok=True)

# Límite de tareas concurrentes de descarga/subida activa
MAX_CONCURRENT = 3
semaphore = asyncio.Semaphore(MAX_CONCURRENT)

client = TelegramClient("bot_session", API_ID, API_HASH)

# ==================== SERVICIO DE GOOGLE DRIVE ====================
drive_service = None
drive_folder_cache = {}
_drive_service_lock = asyncio.Lock()

async def get_drive_service():
    """Instancia y retorna el servicio de Google Drive de manera segura y reutilizable."""
    global drive_service
    if drive_service:
        return drive_service

    async with _drive_service_lock:
        if drive_service:
            return drive_service

        if not os.path.exists(TOKEN_FILE):
            raise FileNotFoundError(f"No se encontró el archivo de credenciales de Google en {TOKEN_FILE}")

        with open(TOKEN_FILE, "r") as f:
            creds_data = json.load(f)

        # Se evitan argumentos inesperados como 'type' limitando las llaves del constructor
        creds = Credentials(
            token=creds_data.get('token'),
            refresh_token=creds_data.get('refresh_token'),
            token_uri=creds_data.get('token_uri'),
            client_id=creds_data.get('client_id'),
            client_secret=creds_data.get('client_secret'),
            scopes=creds_data.get('scopes')
        )
        drive_service = build("drive", "v3", credentials=creds)
        return drive_service


# ==================== CLASES Y UTILIDADES ====================

class HighSpeedProgressTracker:
    def __init__(self, filename: str, total_size: int, icono: str = "📄"):
        self.filename = filename
        self.total_size = total_size
        self.icono = icono
        self.start_time = time.time()
        # Registramos un único mensaje informativo de inicio de descarga para el log único
        logging.info(f"[Descarga] Iniciando descarga de: {filename} ({total_size/1024/1024:.2f} MB)")

    def __call__(self, current: int, total: int):
        total_bytes = total if total else self.total_size
        elapsed = time.time() - self.start_time
        if elapsed <= 0: elapsed = 0.1
        
        speed_bps = current / elapsed
        speed_kbps = speed_bps / 1024
        
        if speed_kbps >= 1024:
            speed_fmt = f"{speed_kbps / 1024:.2f} MB/s"
        else:
            speed_fmt = f"{speed_kbps:.2f} KB/s"
            
        percent = (current / total_bytes) * 100 if total_bytes else 0
        
        # ELIMINADO: Ya no imprimimos en la consola de Linux para no llenar el archivo de log con spam.

        # Formato de barra de progreso para Telegram (esta sigue funcionando en tiempo real en el chat)
        completed_blocks = int(percent // 10)
        progress_bar = "🟩" * completed_blocks + "⬜" * (10 - completed_blocks)
        
        text = (
            f"{self.icono} `{self.filename}`\n\n"
            f"{progress_bar} {percent:.1f}%\n"
            f"⚡ Speed: {speed_fmt}\n"
            f"📦 {current/1024/1024:.1f} / {total_bytes/1024/1024:.1f} MB"
        )
        return text


def clasificar_archivo(mime: str) -> Tuple[str, str]:
    if not mime: 
        return "📄", "Otros"
    if mime.startswith("audio/"): 
        return "🎵", "Audio"
    if mime.startswith("video/"): 
        return "🎥", "Video"
    if mime.startswith("image/"): 
        return "🖼️", "Imagenes"
    if "zip" in mime or "rar" in mime or "7z" in mime: 
        return "📦", "Comprimidos"
    if "pdf" in mime: 
        return "📕", "Documentos"
    if "msword" in mime or "officedocument" in mime: 
        return "📝", "Documentos"
    return "📄", "Otros"


async def obtener_nombre_unico(
    directorio: str, 
    nombre_archivo: str, 
    check_local: bool, 
    check_drive: bool, 
    service=None, 
    folder_id=None
) -> str:
    """Busca un nombre libre verificando existencia local, en Drive o en ambas de forma asíncrona."""
    nombre, ext = os.path.splitext(nombre_archivo)
    contador = 1
    nuevo_nombre = nombre_archivo
    
    while True:
        conflicto = False
        
        # 1. Comprobar localmente si la acción requiere guardar en el servidor
        if check_local:
            ruta_local = os.path.join(directorio, nuevo_nombre)
            if os.path.exists(ruta_local):
                conflicto = True
                
        # 2. Comprobar en Google Drive si la acción requiere guardar en la nube
        if not conflicto and check_drive and service and folder_id:
            drive_id = await buscar_archivo_drive(service, folder_id, nuevo_nombre)
            if drive_id:
                conflicto = True
                
        if not conflicto:
            break
            
        nuevo_nombre = f"{nombre} ({contador}){ext}"
        contador += 1
        
    return nuevo_nombre


async def run_sync(func, *args, **kwargs):
    """Ejecuta una función síncrona/bloqueante en un executor para no detener el loop principal."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


# ==================== OPERACIONES EN DRIVE (SÍNCRONAS REENVOLVIDAS) ====================

def _obtener_o_crear_carpeta_drive_sync(service, parent_id: str, folder_name: str) -> str:
    if folder_name in drive_folder_cache:
        return drive_folder_cache[folder_name]

    query = (
        f"name = '{folder_name}' and "
        f"'{parent_id}' in parents and "
        f"mimeType = 'application/vnd.google-apps.folder' and "
        f"trashed = false"
    )
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get("files", [])
    
    if files:
        folder_id = files[0]["id"]
    else:
        folder_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id]
        }
        folder = service.files().create(body=folder_metadata, fields="id").execute()
        folder_id = folder.get("id")

    drive_folder_cache[folder_name] = folder_id
    return folder_id


def _buscar_archivo_drive_sync(service, parent_id: str, filename: str) -> str:
    name_safe = filename.replace("'", "\\'")
    query = f"name = '{name_safe}' and '{parent_id}' in parents and trashed = false"
    res = service.files().list(q=query, fields="files(id)").execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None


def _eliminar_archivo_drive_sync(service, file_id: str):
    service.files().delete(fileId=file_id).execute()


async def buscar_archivo_drive(service, folder_id: str, name: str) -> str:
    return await run_sync(_buscar_archivo_drive_sync, service, folder_id, name)


# ==================== SUBIDA ASÍNCRONA CON PROGRESO EN TIEMPO REAL ====================

async def subir_drive_con_progreso(
    service, 
    path: str, 
    filename: str, 
    mime: str, 
    folder_id: str, 
    status_msg, 
    icono: str
) -> str:
    """Sube un archivo a Google Drive en fragmentos de 5MB y actualiza el progreso en Telegram."""
    file_metadata = {"name": filename, "parents": [folder_id]}
    
    # 5MB es el tamaño estándar requerido para subidas resumibles fragmentadas
    media = MediaFileUpload(path, mimetype=mime, resumable=True, chunksize=5*1024*1024)
    request = service.files().create(body=file_metadata, media_body=media)
    
    total_size = os.path.getsize(path)
    start_time = time.time()
    last_edit_time = 0
    
    response = None
    while response is None:
        # Se procesa un único bloque de subida de 5MB en un hilo secundario
        status, response = await run_sync(request.next_chunk)
        
        if status:
            current_bytes = status.resumable_progress
            elapsed = time.time() - start_time
            if elapsed <= 0: elapsed = 0.1
            
            speed_bps = current_bytes / elapsed
            speed_kbps = speed_bps / 1024
            
            if speed_kbps >= 1024:
                speed_fmt = f"{speed_kbps / 1024:.2f} MB/s"
            else:
                speed_fmt = f"{speed_kbps:.2f} KB/s"
                
            percent = (current_bytes / total_size) * 100
            
            # Formato de barra (Se usan bloques azules 🟦 para diferenciar la subida de la descarga 🟩)
            completed_blocks = int(percent // 10)
            progress_bar = "🟦" * completed_blocks + "⬜" * (10 - completed_blocks)
            
            text = (
                f"📤 **Subiendo a Google Drive...**\n"
                f"{icono} `{filename}`\n\n"
                f"{progress_bar} {percent:.1f}%\n"
                f"⚡ Speed: {speed_fmt}\n"
                f"📦 {current_bytes/1024/1024:.1f} / {total_size/1024/1024:.1f} MB"
            )
            
            # Limitador de actualización a 1.5 segundos para evitar límites de tasa (Flood) en Telegram
            now = time.time()
            if now - last_edit_time >= 1.5:
                try:
                    await status_msg.edit(text, buttons=None)
                    last_edit_time = now
                except Exception as e:
                    logging.warning(f"Error actualizando progreso de subida: {e}")
                    
    return response.get("id")


# ==================== CONTROLADOR DE EVENTOS ====================

@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def handler(event):
    if event.sender_id not in OWNERS_IDS:
        return

    if not event.file:
        return

    msg = event.message
    file_name = event.file.name or f"archivo_{msg.id}{event.file.ext or ''}"
    file_size = event.file.size or 0

    if file_size == 0: 
        return

    mime_type, _ = mimetypes.guess_type(file_name)
    if not mime_type:
        mime_type = "application/octet-stream"
        
    icono, subcarpeta = clasificar_archivo(mime_type)

    # 1. Menú de opciones inicial
    resumen_text = (
        f"{icono} **Archivo:**\n`{file_name}`\n"
        f"⚖️ **Tamaño:** {file_size/1024/1024:.2f} MB\n"
        f"🗂️ **Tipo:** {mime_type}\n\n"
        f"🤖 **Selecciona el destino:**"
    )
    
    logging.info(f"[Detectado] Archivo de %s: %s (%s MB)", event.sender_id, file_name, f"{file_size/1024/1024:.2f}")
    
    buttons_menu = [
        [Button.inline('SERVER', b'SERVER'), Button.inline('GDRIVE', b'GDRIVE')],
        [Button.inline('AMBOS', b'AMBOS'), Button.inline('STOP', b'STOP')]
    ]
    
    status_msg = await event.respond(resumen_text, buttons=buttons_menu)

    loop = asyncio.get_running_loop()
    future_decision = loop.create_future()

    async def temp_callback(e):
        if e.message_id == status_msg.id and e.sender_id == event.sender_id:
            data = e.data.decode('utf-8')
            if data in ['SERVER', 'GDRIVE', 'AMBOS', 'STOP']:
                if not future_decision.done():
                    await e.answer()
                    future_decision.set_result(data)

    client.add_event_handler(temp_callback, events.CallbackQuery)

    try:
        decision = await asyncio.wait_for(future_decision, timeout=60)
    except asyncio.TimeoutError:
        decision = "STOP"
        await status_msg.edit("⏱️ **Tiempo de espera agotado.** Proceso cancelado.", buttons=None)
        return
    finally:
        client.remove_event_handler(temp_callback, events.CallbackQuery)

    if decision == "STOP":
        await status_msg.edit("❌ **Proceso cancelado por el usuario.**", buttons=None)
        return

    # 2. Control de concurrencia mediante el Semáforo (solo al descargar/subir de forma activa)
    async with semaphore:
        tmp_dir = None
        try:
            final_server_dir = os.path.join(SERVER_DIR, subcarpeta)

            existe_local = False
            existe_drive = False
            drive_file_id = None
            subcarpeta_drive_id = None
            service = None

            # Comprobar si existe localmente
            if decision in ["SERVER", "AMBOS"]:
                local_check_path = os.path.join(final_server_dir, file_name)
                if os.path.exists(local_check_path):
                    existe_local = True

            # Comprobar si existe en Drive
            if decision in ["GDRIVE", "AMBOS"]:
                try:
                    service = await get_drive_service()
                    subcarpeta_drive_id = await run_sync(_obtener_o_crear_carpeta_drive_sync, service, FOLDER_ID, subcarpeta)
                    drive_file_id = await buscar_archivo_drive(service, subcarpeta_drive_id, file_name)
                    if drive_file_id:
                        existe_drive = True
                except Exception as e:
                    logging.error(f"[Error Verificación Drive] {str(e)}")

            reaccion = "REEMPLAZAR"
            conflicto_detectado = False

            # Si hay conflicto en alguno de los destinos, mostramos menú de resolución
            if existe_local or existe_drive:
                conflicto_detectado = True
                lugares = []
                if existe_local: lugares.append("Servidor")
                if existe_drive: lugares.append("Google Drive")
                lugares_str = " | ".join(lugares)

                exist_text = (
                    f"⚠️ **Archivo existente: {lugares_str}.**\n"
                    f"{icono} `{file_name}`\n\n"
                    f"¿Qué deseas hacer?"
                )

                buttons_exist = [
                    [Button.inline('REEMPLAZAR', b'REEMPLAZAR'), Button.inline('DUPLICAR', b'DUPLICAR')],
                    [Button.inline('STOP', b'CANCELAR')]
                ]

                await status_msg.edit(exist_text, buttons=buttons_exist)

                future_reaccion = loop.create_future()

                async def temp_callback_exist(e):
                    if e.message_id == status_msg.id and e.sender_id == event.sender_id:
                        data = e.data.decode('utf-8')
                        if data in ['REEMPLAZAR', 'DUPLICAR', 'CANCELAR']:
                            if not future_reaccion.done():
                                await e.answer()
                                future_reaccion.set_result(data)

                client.add_event_handler(temp_callback_exist, events.CallbackQuery)

                try:
                    reaccion = await asyncio.wait_for(future_reaccion, timeout=60)
                except asyncio.TimeoutError:
                    reaccion = "CANCELAR"
                    await status_msg.edit("⏱️ **Tiempo de espera agotado.** Proceso cancelado.", buttons=None)
                    return
                finally:
                    client.remove_event_handler(temp_callback_exist, events.CallbackQuery)

                if reaccion == "CANCELAR":
                    await status_msg.edit("❌ **Proceso cancelado por el usuario.**", buttons=None)
                    return

            # Limpiar menús de botones y mostrar respuesta (con formato condicional si hubo conflicto)
            if conflicto_detectado:
                await status_msg.edit(f"⚡ Opción: **{decision}** ({reaccion})", buttons=None)
            else:
                await status_msg.edit(f"⚡ Opción: **{decision}**", buttons=None)
                
            status_msg.reply_markup = None  

            # Determinar nombre final en caso de duplicados verificando tanto local como en nube
            final_file_name = file_name
            if reaccion == "DUPLICAR" and (existe_local or existe_drive):
                final_file_name = await obtener_nombre_unico(
                    directorio=final_server_dir,
                    nombre_archivo=file_name,
                    check_local=(decision in ["SERVER", "AMBOS"]),
                    check_drive=(decision in ["GDRIVE", "AMBOS"]),
                    service=service,
                    folder_id=subcarpeta_drive_id
                )
                logging.info(f"[Duplicado] Renombrado final a: {final_file_name}")

            # Inicializar tracker de progreso detallado (Ahora solo reporta el inicio al log del sistema)
            tracker = HighSpeedProgressTracker(final_file_name, file_size, icono)
            
            # 3. Crear directorio temporal único y asegurar la inclusión de la barra inclinada al final
            tmp_dir = tempfile.mkdtemp()
            tmp_dir_slash = os.path.join(tmp_dir, "") # Forza que termine en '/' (evita archivos sueltos en /tmp)
            
            # --- INTERCEPCIÓN DINÁMICA DE TEXTO DE DESCARGA (MONKEY-PATCHING) ---
            original_client_edit = client.edit_message
            original_msg_edit = status_msg.edit

            def limpiar_texto_descarga(text):
                # Intercepta el texto crudo y traduce "Downloading..." a un formato elegante
                if isinstance(text, str) and text.startswith("Downloading...\n"):
                    return text.replace("Downloading...\n", "📥 **Descargando de Telegram...**\n\n")
                return text

            async def custom_client_edit(entity, message, *args, **kwargs):
                message = limpiar_texto_descarga(message)
                return await original_client_edit(entity, message, *args, **kwargs)

            async def custom_msg_edit(text=None, *args, **kwargs):
                text = limpiar_texto_descarga(text)
                return await original_msg_edit(text, *args, **kwargs)

            # Aplicar parches antes de la descarga
            client.edit_message = custom_client_edit
            status_msg.edit = custom_msg_edit

            try:
                path_temporal = await fast_download(client, msg, status_msg, tmp_dir_slash, tracker)
                logging.info(f"[Éxito] Descarga temporal finalizada en: {path_temporal}")
            except Exception as e:
                logging.error(f"[Error] Error en descarga: {str(e)}")
                # Restauramos funciones originales antes de reportar el error
                client.edit_message = original_client_edit
                status_msg.edit = original_msg_edit
                await status_msg.edit(f"❌ **Error en descarga:**\n`{str(e)}`", buttons=None)
                return
            finally:
                # Restaurar funciones originales inmediatamente después de finalizar la descarga
                client.edit_message = original_client_edit
                status_msg.edit = original_msg_edit

            try:
                await status_msg.edit(
                    f"📥 **Descarga Completada**\n"
                    f"{icono} `{final_file_name}`\n\n"
                    f"🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 100%\n"
                    f"📦 {file_size/1024/1024:.1f} / {file_size/1024/1024:.1f} MB",
                    buttons=None
                )
            except: 
                pass

            path_final = path_temporal

            # Procesar guardado local (SERVER o AMBOS)
            if decision in ["SERVER", "AMBOS"]:
                os.makedirs(final_server_dir, exist_ok=True)
                path_final = os.path.join(final_server_dir, final_file_name)
                # Mover de forma segura usando el pool de hilos de run_sync
                await run_sync(shutil.move, path_temporal, path_final)
                logging.info(f"[Servidor] Archivo movido a destino final: {path_final}")

            elif decision == "GDRIVE" and final_file_name != file_name:
                path_final = os.path.join(tmp_dir_slash, final_file_name)
                await run_sync(os.rename, path_temporal, path_final)

            # 4. Flujo de subida a Google Drive (GDRIVE o AMBOS)
            if decision in ["GDRIVE", "AMBOS"]:
                logging.info(f"[Subida] Iniciando subida a Google Drive...")
                
                try:
                    if not service:
                        service = await get_drive_service()

                    if not subcarpeta_drive_id:
                        subcarpeta_drive_id = await run_sync(_obtener_o_crear_carpeta_drive_sync, service, FOLDER_ID, subcarpeta)

                    # Reemplazar archivo previo en Drive si aplica
                    if reaccion == "REEMPLAZAR" and drive_file_id:
                        logging.info(f"[Drive] Reemplazando archivo anterior (ID anterior: {drive_file_id})...")
                        await run_sync(_eliminar_archivo_drive_sync, service, drive_file_id)

                    # Subir archivo final a Google Drive de manera no bloqueante con progreso real en Telegram
                    file_drive_id = await subir_drive_con_progreso(
                        service=service,
                        path=path_final,
                        filename=final_file_name,
                        mime=mime_type,
                        folder_id=subcarpeta_drive_id,
                        status_msg=status_msg,
                        icono=icono
                    )
                    logging.info(f"[Completado] Archivo subido con éxito. ID de Drive: {file_drive_id}")
                    
                    dest_text = f"Google Drive / {subcarpeta}" if decision == "GDRIVE" else f"Servidor | Google Drive / {subcarpeta}"
                    final_text = (
                        f"✅ **¡Proceso Completado con Éxito!**\n"
                        f"{icono} `{final_file_name}`\n\n"
                        f"📍 **Destino:** `{dest_text}`\n"
                        f"🔗 [Link Drive](https://drive.google.com/file/d/{file_drive_id}/view)"
                    )
                    await status_msg.edit(final_text, buttons=None)

                except Exception as e:
                    logging.error(f"[Error Drive] {str(e)}")
                    await status_msg.edit(f"❌ **Error en Google Drive:**\n`{str(e)}`", buttons=None)
                    
            else:
                # Solo guardar en Servidor
                logging.info(f"[Completado] Archivo guardado localmente en {path_final}")
                final_text = (
                    f"✅ **¡Proceso Completado con Éxito!**\n\n"
                    f"📁 **Ruta:**\n{icono} `{path_final}`"
                )
                await status_msg.edit(final_text, buttons=None)

        finally:
            # 5. Asegurar limpieza total del directorio temporal único y todo su contenido
            if tmp_dir and os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)


# ==================== MAIN ====================

async def main():
    await client.start(bot_token=BOT_TOKEN)
    logging.info("Bot activo y esperando tus mensajes en privado...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())