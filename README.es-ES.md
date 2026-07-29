<div align="center">

# 🦞 PyClaw

**tu propio asistente personal de IA — el python claw.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

un asistente de IA totalmente asíncrono y extensible que vive en tu terminal y telegram.
impulsado por el enrutamiento de (Gemini, OpenAI, Anthropic, etc.).

</div>

---

## ✨ características

- **Pasarela de bot de Telegram** — Chatea con tu IA desde cualquier lugar, con análisis de fotos y envío de archivos.
- **Chat de terminal** — CLI interactiva con respuestas en streaming.
- **Sistema de herramientas** — Operaciones de archivos, comandos de shell, búsqueda web, gestión de configuración, tareas cron.
- **Habilidades (Skills)** — Sistema de habilidades extensible con paquetes de habilidades `.md` instalables.
- **Identidad** — Personalidad persistente a través de plantillas `SOUL.md` y `AGENTS.md`.
- **Memoria** — Notas diarias + memoria a largo plazo curada.
- **Reacciones** — Auto-reacciones y reacciones con emoji en telegram (modos minimal/massive).
- **Resiliencia de red** — Reconexión automática con backoff exponencial ante pérdida de conexión.
- **Multi-modelo** — Cambia entre modelos de Gemini sobre la marcha.

## 📦 instalación

### requisitos

- **python 3.11+**
- **pip** (o **pipx** para una instalación aislada)
- una **clave de API de Google AI** ([consigue una aquí](https://aistudio.google.com/apikey))
- un **token de bot de telegram** (de [@BotFather](https://t.me/BotFather)) — *opcional, para la pasarela de telegram*

### linux / macOS

```bash
git clone https://github.com/9v2/pyclaw.git
cd pyclaw
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### windows (recomendado WSL)

```bash
# instalar WSL si aún no lo tienes
wsl --install

# luego dentro de WSL:
git clone https://github.com/9v2/pyclaw.git
cd pyclaw
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### windows (nativo)

```powershell
git clone https://github.com/9v2/pyclaw.git
cd pyclaw
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

> [!NOTE]
> la pasarela de telegram utiliza señales de unix para el cierre ordenado. en windows nativo, usa WSL para la pasarela. la CLI funciona correctamente en windows nativo.

## 🚀 inicio rápido

```bash
# configuración inicial — te guía por la autenticación, selección de modelo, telegram y habilidades
pyclaw onboard

# empezar a chatear
pyclaw agent

# lanzar el bot de telegram
pyclaw gateway
```

## 📋 comandos de la CLI

| comando | descripción |
|---|---|
| `pyclaw onboard` | asistente de configuración inicial |
| `pyclaw agent` | chat de IA interactivo en la terminal |
| `pyclaw gateway` | bot de telegram (menú interactivo con start/stop/restart) |
| `pyclaw config show` | mostrar configuración actual |
| `pyclaw config set KEY VALUE` | establecer un valor de configuración |
| `pyclaw config reset` | restablecer configuración a los valores por defecto |
| `pyclaw models` | listar y cambiar modelos de IA |
| `pyclaw skills list` | listar habilidades instaladas |
| `pyclaw skills install URL` | instalar una habilidad desde una URL `.md` |

## ⚙️ configuración

la configuración se encuentra en `~/.pyclaw/config.json`. secciones clave:

| sección | claves | descripción |
|---|---|---|
| `auth` | `google_api_key` | clave de API de Google AI |
| `agent` | `model`, `temperature`, `max_tokens` | ajustes del modelo y generación |
| `gateway` | `telegram_bot_token`, `allowed_users`, `reaction_mode` | ajustes del bot de telegram |
| `search` | `provider`, `perplexity_api_key`, `brave_api_key` | proveedor de búsqueda web |
| `workspace` | `path` | directorio de espacio de trabajo (defecto: `~/.pyclaw/workspace`) |

### modos de reacción

```bash
# sin auto-reacciones (por defecto)
pyclaw config set gateway.reaction_mode null

# reaccionar a saludos + finalización
pyclaw config set gateway.reaction_mode minimal

# reaccionar a cada mensaje
pyclaw config set gateway.reaction_mode massive
```

## 🧠 habilidades (skills)

las habilidades son archivos markdown que extienden las capacidades de la IA. residen en `~/.pyclaw/workspace/skills/<name>/SKILL.md` y se inyectan en el prompt del sistema.

```bash
# instalar una habilidad desde una URL
pyclaw skills install https://example.com/skill.md

# listar habilidades instaladas
pyclaw skills list
```

habilidades integradas: **tmux**, **shell**, **file_management**

## 🛠 herramientas disponibles

la IA tiene acceso a estas herramientas:

| herramienta | descripción |
|---|---|
| `run_command` | ejecutar comandos de shell |
| `write_file` | crear/sobrescribir archivos |
| `read_file` | leer contenido de archivos |
| `list_directory` | listar contenido de directorios |
| `web_search` | buscar en la web (brave/perplexity) |
| `read_webpage` | obtener y leer una URL |
| `send_reaction` | reaccionar a mensajes con emojis |
| `get_config` / `set_config` | leer/escribir configuración |
| `update_identity` | actualizar SOUL.md / AGENTS.md |
| `cron` tools | programar tareas recurrentes |

## 🏗 arquitectura

```
~/.pyclaw/
├── config.json          # todos los ajustes
├── SOUL.md              # personalidad y reglas de la IA
├── AGENTS.md            # pautas de comportamiento
├── MEMORY.md            # memoria a largo plazo curada
├── memory/              # notas diarias (YYYY-MM-DD.md)
├── workspace/
│   ├── skills/          # habilidades instaladas
│   ├── images/          # imágenes generadas
│   ├── files/           # archivos generados
│   └── temp/            # archivos temporales
└── gateway.log          # logs de la pasarela de telegram
```

```
pyclaw/
├── agent/               # agente de IA core, proveedores, herramientas, identidad
├── auth/                # google OAuth
├── cli/                 # comandos CLI de click
├── config/              # gestión de configuración, valores por defecto, modelos
├── gateway/             # pasarela del bot de telegram
└── skills/              # plantillas de habilidades integradas
```

## 🔒 seguridad

- **prompts de confirmación** para comandos destructivos (`rm`, `kill`, etc.)
- **patrones bloqueados** — lista negra de comandos configurable
- **usuarios permitidos** — restringir el bot de telegram a IDs de usuario específicos
- **comandos seguros** — lista blanca para comandos aprobados automáticamente (`ls`, `cat`, `echo`, etc.)

## 🤝 contribución

¡Las contribuciones son bienvenidas! Siéntete libre de abrir issues, sugerir funciones o enviar pull requests.

1. Haz un fork del repositorio
2. Crea tu rama (`git checkout -b feature/cool-thing`)
3. Haz commit de tus cambios (`git commit -m 'add cool thing'`)
4. Haz push a la rama (`git push origin feature/cool-thing`)
5. Abre un Pull Request

Si encuentras PyClaw útil, ¡dale una ⭐; ayuda a otros a descubrir el proyecto!

## 📄 licencia

[MIT](LICENSE)
