# ☁️ TgCloud - Telegram to Google Drive & Local Storage Bot

Bot interactivo de Telegram desarrollado en Python 3.12 para la descarga y almacenamiento acelerado de archivos pesados hacia Google Drive y/o almacenamiento local del servidor.

---

## 🚀 Características Principales

- ⚡ **Descargas Aceleradas:** Motor `Telethon` optimizado con `FastTelethonhelper` y aceleración criptográfica de C (`tgcrypto`).
- 📤 **Subida Resumible a Google Drive:** Carga fragmentada en bloques de 5MB con indicador de velocidad y progreso en tiempo real.
- 🗂️ **Organización Automática:** Clasificación inteligente por tipo de archivo (`Video`, `Audio`, `Imagenes`, `Documentos`, `Comprimidos`).
- 🤖 **Menú Dinámico Inline:** Selección interactiva de destino (`SERVER`, `GDRIVE`, `AMBOS`, `STOP`).
- ⚠️ **Control de Duplicados:** Detección de colisiones con menú contextual (`REEMPLAZAR`, `DUPLICAR`, `CANCELAR`).
- 🪵 **Logs Rotativos Semanales:** Control de logs con `TimedRotatingFileHandler` comprimidos automáticamente en `.gz` (4 semanas de historial).
- 🛠️ **Gestión con `uv`:** Entorno virtual ultrarrápido y bloqueo determinista de dependencias (`uv.lock`).

---

## 📂 Estructura del Proyecto

```text
tgcloud/
├── auth/                   # Todo lo relacionado a autenticación (IGNORADO en Git)
│   ├── auth_drive.py       # Script interactivo para autorizar Google Drive API
│   ├── credentials.json    # Descargado de Google Cloud Console
│   ├── google_token.json   # Token generado por auth_drive.py
│   └── bot_session.session # Archivo de sesión de Telethon
├── downloads/              # Carpeta de almacenamiento local (IGNORADO en Git)
├── logs/                   # Logs de ejecución con rotación semanal .gz (IGNORADO en Git)
├── src/
│   └── tgcloud/
│       ├── __init__.py
│       └── bot.py          # Lógica principal del Bot
├── .env.example            # Plantilla pública de variables de entorno
├── .gitignore              # Reglas estrictas de exclusión para Git
├── .python-version         # Versión fija de Python (3.12)
├── pyproject.toml          # Declaración de dependencias del proyecto
├── uv.lock                 # Candado de versiones exactas garantizadas por uv
└── README.md               # Manual y documentación técnica
```

---

## 🛠️ Requisitos del Sistema

- **OS:** Linux (Ubuntu 22.04 / 24.04 recomendados)
- **Python:** 3.12+
- **Paquetes de C del SO:** `python3-dev`, `build-essential`

---

## 📦 Guía de Despliegue en un Servidor Nuevo

### 1. Clonar el repositorio e instalar dependencias de compilación

```bash
git clone git@github.com:almagomen/TgCloud.git
cd TgCloud

# Instalar cabeceras de C indispensables para compilar tgcrypto
sudo apt update && sudo apt install -y python3-dev build-essential curl
```

### 2. Instalar `uv` y sincronizar el entorno

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# Instala exactamente las versiones fijadas en uv.lock
uv sync
```

### 3. Configurar variables de entorno (`.env`)

Copia la plantilla `.env.example`:

```bash
cp .env.example .env
```

Edita `.env` con tus credenciales:

```env
API_ID=12345678
API_HASH=tu_api_hash_de_telegram
BOT_TOKEN=tu_token_de_botfather
FOLDER_ID=id_de_la_carpeta_raiz_de_google_drive
OWNERS=123456789
SERVER_DIR=downloads
TOKEN_FILE=auth/google_token.json
SESSION_FILE=auth/bot_session
LOG_DIR=logs
```

---

## 🔐 Configuración de Google Drive API

1. En [Google Cloud Console](https://console.cloud.google.com/), habilita **Google Drive API**.
2. Configura la **Pantalla de Consentimiento de OAuth** como *Externo* y agrega tu correo como *Usuario de Prueba*.
3. Crea un **ID de Cliente de OAuth 2.0** de tipo *Aplicación de Escritorio*.
4. Descarga el JSON y guárdalo en `auth/credentials.json`.
5. Ejecuta el script de autorización:

```bash
uv run python auth/auth_drive.py
```

6. Abre la URL en tu navegador, concede los permisos, copia la URL final de `localhost:8080` y pégala en la terminal.

---

## ⚙️ Servicio de Producción con Systemd

1. Crear el archivo de servicio:

```bash
sudo nano /etc/systemd/system/tgcloud.service
```

2. Configuración optimizada para VPS:

```ini
[Unit]
Description=Telegram to Cloud Bot (UV Modern)
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/projects/tgcloud
ExecStart=/home/ubuntu/.local/bin/uv run python src/tgcloud/bot.py

Environment=PYTHONUNBUFFERED=1
Environment=PYTHONOPTIMIZE=2
EnvironmentFile=/home/ubuntu/projects/tgcloud/.env

Restart=always
RestartSec=5s

LimitNOFILE=4096
MemoryHigh=300M
MemoryMax=400M

[Install]
WantedBy=multi-user.target
```

3. Activar el servicio:

```bash
sudo systemctl daemon-reload
sudo systemctl start tgcloud.service
sudo systemctl enable tgcloud.service
```

---

## 🛠️ Mantenimiento Diario

- **Ver estado del servicio:** `sudo systemctl status tgcloud.service`
- **Ver logs en tiempo real:** `tail -f logs/tgcloud.log`
- **Actualizar código desde GitHub:**
  ```bash
  git pull
  uv sync
  sudo systemctl restart tgcloud.service
  ```
