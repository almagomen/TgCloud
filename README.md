# ☁️ TgCloud - Personal Telegram Cloud & VPS Offloader Bot

Bot interactivo de Telegram desarrollado en Python 3.12 y gestionado con **`uv`**. Diseñado para actuar como un **puente de descarga remota en la nube**, permitiendo recibir archivos pesados reenviados desde Telegram y almacenarlos directamente en Google Drive o en tu servidor VPS sin consumir ancho de banda local ni espacio en tu dispositivo (móvil o PC).

---

## 💡 Caso de Uso Principal (¿Por qué usar TgCloud?)

Cuando te comparten archivos pesados por Telegram (vídeos en 4K, documentos de varios GB, cursos, discos, etc.):
1. **Cero consumo de datos/disco local:** No necesitas descargar el archivo a tu teléfono o computadora personal.
2. **Reenvío instantáneo:** Basta con reenviar el mensaje con el archivo al bot.
3. **Procesamiento Gigabit en la nube:** La VPS (con conexión de alta velocidad) descarga el archivo a decenas de MB/s y lo sube automáticamente a tu Google Drive u organización local.

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
TgCloud/
├── auth/                   # Carpeta de autenticación
│   ├── auth_drive.py       # Script interactivo para autorizar Google Drive API (Versionado)
│   ├── credentials.json    # Descargado de Google Cloud Console (IGNORADO)
│   ├── google_token.json   # Token generado por auth_drive.py (IGNORADO)
│   └── bot_session.session # Archivo de sesión de Telethon (IGNORADO)
├── downloads/              # Carpeta de almacenamiento local (IGNORADO)
├── logs/                   # Logs de ejecución con rotación semanal .gz (IGNORADO)
├── src/
│   └── tgcloud/
│       ├── __init__.py
│       └── bot.py          # Lógica principal del Bot
├── .env.example            # Plantilla pública de variables de entorno
├── .gitignore              # Reglas strictly de exclusión para Git
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

## 📱 Paso 1: Configuración de Credenciales de Telegram

Para que el bot pueda conectarse a la API de Telegram necesitas 4 valores:

### A. Obtener `API_ID` y `API_HASH`
1. Entra a [my.telegram.org](https://my.telegram.org) e inicia sesión con tu número de teléfono.
2. Ve a **API development tools**.
3. Completa los campos del formulario (puedes colocar cualquier nombre corto en *App title* y *Short name*).
4. Copia tu `api_id` y `api_hash`.

### B. Crear el Bot y obtener el `BOT_TOKEN`
1. Abre Telegram y busca al bot oficial [@BotFather](https://t.me/BotFather).
2. Envía el comando `/newbot`.
3. Asigna un nombre y un usuario a tu bot (el usuario debe terminar en `bot`, ej: `MiTgCloud_bot`).
4. BotFather te entregará un **HTTP API Token** (ej: `123456789:ABCdefGhIJKlmNoPQRstuVWXyz`). Copia este valor.

### C. Obtener tu ID de usuario (`OWNERS`)
1. Busca al bot [@userinfobot](https://t.me/userinfobot) en Telegram y envíale un mensaje.
2. Te responderá con tu número de `Id` (ej: `123456789`). Este número le indica al bot que tú eres el único usuario autorizado a usarlo.

---

## 🔐 Paso 2: Configuración de Google Drive API

1. En [Google Cloud Console](https://console.cloud.google.com/), crea un proyecto y habilita **Google Drive API**.
2. Configura la **Pantalla de Consentimiento de OAuth** como *Externo* y agrega tu correo como *Usuario de Prueba (Test User)*.
3. En **Credenciales**, crea un **ID de Cliente de OAuth 2.0** de tipo *Aplicación de Escritorio (Desktop App)*.
4. Descarga el archivo JSON y guárdalo en `auth/credentials.json`.

---

## 📦 Paso 3: Guía de Despliegue en el Servidor

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

Edita `.env` con los valores que obtuviste en los Pasos 1 y 2:

```env
API_ID=tu_api_id_de_my_telegram_org
API_HASH=tu_api_hash_de_my_telegram_org
BOT_TOKEN=tu_bot_token_de_botfather
FOLDER_ID=id_de_la_carpeta_raiz_de_google_drive
OWNERS=tu_user_id_de_userinfobot
SERVER_DIR=downloads
TOKEN_FILE=auth/google_token.json
SESSION_FILE=auth/bot_session
LOG_DIR=logs
```

### 4. Generar el Token de Google Drive

Ejecuta el script interactivo de autorización:

```bash
uv run python auth/auth_drive.py
```

Abre la URL en tu navegador, concede los permisos, copia la URL final que cargue en `localhost:8080` y pégala en la terminal.

---

## ⚙️ Paso 4: Servicio de Producción con Systemd (Despliegue Automático)

Para instalar el servicio de fondo 24/7 de forma agnóstica y automática en cualquier servidor o usuario, ejecuta este bloque único dentro de la carpeta del proyecto:

```bash
cat << EOF | sudo tee /etc/systemd/system/tgcloud.service
[Unit]
Description=Telegram to Cloud Bot (TgCloud)
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(which uv) run python src/tgcloud/bot.py

Environment=PYTHONUNBUFFERED=1
Environment=PYTHONOPTIMIZE=2
EnvironmentFile=$(pwd)/.env

Restart=always
RestartSec=5s

LimitNOFILE=4096
MemoryHigh=300M
MemoryMax=400M

[Install]
WantedBy=multi-user.target
EOF
```

Activar e iniciar el servicio:

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
