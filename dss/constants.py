"""Catálogos de datos de Discord usados por la interfaz (en español).

Todo el programa es Python puro: estos catálogos evitan dependencias externas y
centralizan las etiquetas para que la UI hable un único idioma.
"""
from __future__ import annotations

APP_NAME = "Discord Server Studio"
APP_VERSION = "1.0.0"
API_BASE = "https://discord.com/api/v10"
USER_AGENT = f"DiscordServerStudio/{APP_VERSION} (desktop; python)"

# Permisos recomendados para invitar el bot (sin Administrador):
# crear invitaciones, expulsar, banear, gestionar canales/servidor/roles/webhooks/
# emojis/apodos, ver auditoría, moderar miembros, ver canales, enviar mensajes,
# leer historial, conectarse y usar comandos.
BOT_RECOMMENDED_PERMISSIONS = 1101526019263  # incluye Administrador (bit 3)

# --------------------------------------------------------------------------- #
# Permisos
# --------------------------------------------------------------------------- #

PERMISSION_CATEGORIES = [
    ("general", "General"),
    ("members", "Miembros"),
    ("text", "Texto"),
    ("voice", "Voz"),
    ("apps", "Aplicaciones"),
]

# (clave, bit, categoría, etiqueta, descripción)
PERMISSIONS: list[tuple[str, int, str, str, str]] = [
    ("VIEW_CHANNEL", 10, "general", "Ver canales",
     "Permite ver los canales de texto y de voz."),
    ("MANAGE_CHANNELS", 4, "general", "Gestionar canales",
     "Crear, editar y borrar canales, y ajustar sus permisos."),
    ("MANAGE_ROLES", 28, "general", "Gestionar roles",
     "Crear, editar y borrar roles por debajo del rol propio."),
    ("MANAGE_GUILD", 5, "general", "Gestionar servidor",
     "Cambiar el nombre, icono, nivel de verificación y ajustes del servidor."),
    ("VIEW_AUDIT_LOG", 7, "general", "Ver registro de auditoría",
     "Consultar el historial de acciones administrativas."),
    ("MANAGE_WEBHOOKS", 29, "general", "Gestionar webhooks",
     "Crear, editar y borrar webhooks."),
    ("MANAGE_GUILD_EXPRESSIONS", 30, "general", "Gestionar emojis y stickers",
     "Añadir o quitar emojis y stickers del servidor."),
    ("MANAGE_EVENTS", 33, "general", "Gestionar eventos",
     "Crear y editar eventos programados."),
    ("VIEW_GUILD_INSIGHTS", 19, "general", "Ver análisis",
     "Acceder a las estadísticas del servidor."),
    ("CREATE_INSTANT_INVITE", 0, "general", "Crear invitaciones",
     "Crear invitaciones para el servidor."),
    ("CHANGE_NICKNAME", 26, "general", "Cambiar apodo",
     "Cambiar el propio apodo en el servidor."),
    ("ADMINISTRATOR", 3, "general", "Administrador",
     "Concede todos los permisos y omite las restricciones de canal."),

    ("KICK_MEMBERS", 1, "members", "Expulsar miembros",
     "Expulsar miembros del servidor."),
    ("BAN_MEMBERS", 2, "members", "Banear miembros",
     "Banear miembros y consultar la lista de baneos."),
    ("MODERATE_MEMBERS", 40, "members", "Aislar temporalmente",
     "Aplicar timeout: silenciar a un miembro durante un tiempo."),
    ("MANAGE_NICKNAMES", 27, "members", "Gestionar apodos",
     "Cambiar el apodo de otros miembros."),
    ("MANAGE_THREADS", 34, "members", "Gestionar hilos",
     "Borrar y archivar hilos de otros usuarios."),
    ("CREATE_PUBLIC_THREADS", 35, "members", "Crear hilos públicos",
     "Crear hilos públicos."),
    ("CREATE_PRIVATE_THREADS", 36, "members", "Crear hilos privados",
     "Crear hilos privados."),

    ("SEND_MESSAGES", 11, "text", "Enviar mensajes",
     "Enviar mensajes en canales de texto."),
    ("SEND_MESSAGES_IN_THREADS", 38, "text", "Enviar mensajes en hilos",
     "Enviar mensajes dentro de hilos."),
    ("READ_MESSAGE_HISTORY", 16, "text", "Leer historial",
     "Ver mensajes anteriores a la apertura del canal."),
    ("MANAGE_MESSAGES", 13, "text", "Gestionar mensajes",
     "Borrar y fijar mensajes de otros usuarios."),
    ("EMBED_LINKS", 14, "text", "Insertar enlaces",
     "Previsualizar enlaces automáticamente."),
    ("ATTACH_FILES", 15, "text", "Adjuntar archivos",
     "Subir archivos e imágenes."),
    ("ADD_REACTIONS", 6, "text", "Añadir reacciones",
     "Reaccionar a los mensajes."),
    ("MENTION_EVERYONE", 17, "text", "Mencionar @everyone",
     "Mencionar a todos y a los roles."),
    ("SEND_TTS_MESSAGES", 12, "text", "Enviar mensajes TTS",
     "Enviar mensajes de texto a voz."),
    ("USE_EXTERNAL_EMOJIS", 18, "text", "Usar emojis externos",
     "Usar emojis de otros servidores."),
    ("USE_EXTERNAL_STICKERS", 37, "text", "Usar stickers externos",
     "Usar stickers de otros servidores."),
    ("SEND_POLLS", 47, "text", "Crear encuestas",
     "Crear encuestas en canales de texto."),
    ("SEND_VOICE_MESSAGES", 46, "text", "Enviar notas de voz",
     "Enviar mensajes de voz."),

    ("CONNECT", 20, "voice", "Conectarse",
     "Entrar a canales de voz."),
    ("SPEAK", 21, "voice", "Hablar",
     "Hablar en canales de voz."),
    ("STREAM", 9, "voice", "Transmitir",
     "Compartir pantalla o cámara."),
    ("USE_VAD", 25, "voice", "Usar detección de voz",
     "Hablar sin pulsar para hablar."),
    ("PRIORITY_SPEAKER", 8, "voice", "Prioridad al hablar",
     "Bajar el volumen del resto al hablar."),
    ("MUTE_MEMBERS", 22, "voice", "Silenciar miembros",
     "Silenciar a otros en voz."),
    ("DEAFEN_MEMBERS", 23, "voice", "Ensordecer miembros",
     "Ensordecer a otros en voz."),
    ("MOVE_MEMBERS", 24, "voice", "Mover miembros",
     "Mover miembros entre canales de voz."),
    ("REQUEST_TO_SPEAK", 32, "voice", "Pedir la palabra",
     "Solicitar hablar en un escenario."),
    ("USE_EMBEDDED_ACTIVITIES", 39, "voice", "Usar actividades",
     "Usar actividades integradas en voz."),
    ("USE_SOUNDBOARD", 42, "voice", "Usar soundboard",
     "Reproducir sonidos del soundboard."),
    ("USE_EXTERNAL_SOUNDS", 45, "voice", "Usar sonidos externos",
     "Usar sonidos de otros servidores."),

    ("USE_APPLICATION_COMMANDS", 31, "apps", "Usar comandos",
     "Usar comandos de aplicaciones."),
    ("USE_EXTERNAL_APPS", 48, "apps", "Usar apps externas",
     "Usar aplicaciones que no están instaladas."),
    ("CREATE_GUILD_EXPRESSIONS", 43, "apps", "Crear expresiones",
     "Crear emojis y stickers del servidor."),
    ("CREATE_EVENTS", 44, "apps", "Crear eventos",
     "Crear eventos programados."),
    ("VIEW_CREATOR_MONETIZATION_ANALYTICS", 41, "apps", "Ver monetización",
     "Ver los análisis de monetización del creador."),
]

PERMISSION_BY_KEY = {p[0]: p for p in PERMISSIONS}

DANGEROUS_PERMISSIONS = {"ADMINISTRATOR", "MANAGE_GUILD", "MANAGE_ROLES",
                          "MANAGE_CHANNELS", "BAN_MEMBERS", "KICK_MEMBERS",
                          "MANAGE_WEBHOOKS"}

# --------------------------------------------------------------------------- #
# Canales
# --------------------------------------------------------------------------- #

CHANNEL_TYPES = {
    0: "Texto",
    2: "Voz",
    4: "Categoría",
    5: "Anuncios",
    10: "Hilo de anuncios",
    11: "Hilo público",
    12: "Hilo privado",
    13: "Escenario",
    14: "Directorio",
    15: "Foro",
    16: "Media",
}

TEXT_CHANNEL_TYPES = {0, 5, 15, 16}
VOICE_CHANNEL_TYPES = {2, 13}
THREAD_TYPES = {10, 11, 12}
CATEGORY_TYPE = 4
CREATABLE_TEXT_TYPES = [(0, "Texto"), (5, "Anuncios"), (15, "Foro"), (16, "Media")]
CREATABLE_CHANNEL_TYPES = CREATABLE_TEXT_TYPES + [(2, "Voz"), (13, "Escenario")]

# Canales que Discord solo permite cuando el servidor tiene la comunidad activada.
COMMUNITY_ONLY_CHANNEL_TYPES = {5, 13, 15, 16}


def creatable_channel_types(is_community: bool) -> list[tuple[int, str]]:
    if is_community:
        return list(CREATABLE_CHANNEL_TYPES)
    return [(value, label) for value, label in CREATABLE_CHANNEL_TYPES
            if value not in COMMUNITY_ONLY_CHANNEL_TYPES]


# Boosts necesarios para alcanzar cada nivel de mejora.
BOOST_REQUIREMENTS = {1: 2, 2: 7, 3: 14}

# Sincronización automática (segundos entre ciclos).
LIVE_SYNC_SECONDS = 20.0

CHANNEL_GLYPHS = {
    0: "#", 5: "!", 15: "▤", 16: "▤", 2: "◍", 13: "◎", 4: "▾",
    10: "≡", 11: "≡", 12: "≡", 14: "▤",
}

VERIFICATION_LEVELS = [
    (0, "Ninguno", "Sin restricciones para entrar al servidor."),
    (1, "Bajo", "El correo debe estar verificado."),
    (2, "Medio", "Cuenta con más de 5 minutos de antigüedad."),
    (3, "Alto", "Miembro del servidor desde hace más de 10 minutos."),
    (4, "Muy alto", "Teléfono verificado."),
]

CONTENT_FILTER_LEVELS = [
    (0, "Desactivado", "No se filtra contenido explícito."),
    (1, "Miembros sin rol", "Se filtra para miembros sin roles."),
    (2, "Todos", "Se filtra para todos los miembros."),
]

DEFAULT_NOTIFICATION_LEVELS = [
    (0, "Todos los mensajes", "Notificar cada mensaje nuevo."),
    (1, "Solo menciones", "Notificar únicamente menciones."),
]

MFA_LEVELS = {0: "No requiere 2FA", 1: "Requiere 2FA para moderar"}

NSFW_LEVELS = {0: "Predeterminado", 1: "Explícito", 2: "Seguro", 3: "Restringido por edad"}

PREMIUM_TIERS = {0: "Sin mejoras", 1: "Nivel 1", 2: "Nivel 2", 3: "Nivel 3"}

AFK_TIMEOUTS = [(60, "1 minuto"), (300, "5 minutos"), (900, "15 minutos"),
                (1800, "30 minutos"), (3600, "1 hora")]

LOCALES = [
    ("es-ES", "Español (España)"), ("es-419", "Español (Latinoamérica)"),
    ("en-US", "Inglés (EE. UU.)"), ("en-GB", "Inglés (Reino Unido)"),
    ("pt-BR", "Portugués (Brasil)"), ("fr", "Francés"), ("de", "Alemán"),
    ("it", "Italiano"), ("nl", "Neerlandés"), ("pl", "Polaco"),
    ("ru", "Ruso"), ("tr", "Turco"), ("ja", "Japonés"), ("ko", "Coreano"),
    ("zh-CN", "Chino simplificado"), ("hi", "Hindi"),
]

GUILD_FEATURES = {
    "ANIMATED_ICON": "Icono animado",
    "BANNER": "Banner",
    "COMMUNITY": "Comunidad",
    "DISCOVERABLE": "Descubrible",
    "FEATURABLE": "Destacable",
    "INVITE_SPLASH": "Fondo de invitación",
    "MEMBER_VERIFICATION_GATE_ENABLED": "Verificación de miembros",
    "MONETIZATION_ENABLED": "Monetización",
    "MORE_STICKERS": "Más stickers",
    "NEWS": "Canales de anuncios",
    "PARTNERED": "Socio de Discord",
    "PREVIEW_ENABLED": "Vista previa",
    "PRIVATE_THREADS": "Hilos privados",
    "ROLE_ICONS": "Iconos de rol",
    "TICKETED_EVENTS_ENABLED": "Eventos con entrada",
    "VANITY_URL": "URL personalizada",
    "VERIFIED": "Verificado",
    "VIP_REGIONS": "Regiones VIP",
    "WELCOME_SCREEN_ENABLED": "Pantalla de bienvenida",
    "INVITES_DISABLED": "Invitaciones desactivadas",
    "HUB": "Hub de estudiantes",
}

# --------------------------------------------------------------------------- #
# Registro de auditoría
# --------------------------------------------------------------------------- #

AUDIT_ACTIONS: dict[int, tuple[str, str]] = {
    1: ("Servidor", "Servidor actualizado"),
    10: ("Canales", "Canal creado"), 11: ("Canales", "Canal actualizado"),
    12: ("Canales", "Canal eliminado"), 13: ("Canales", "Permiso de canal creado"),
    14: ("Canales", "Permiso de canal actualizado"), 15: ("Canales", "Permiso de canal eliminado"),
    20: ("Miembros", "Miembro expulsado"), 21: ("Miembros", "Miembros purgados"),
    22: ("Miembros", "Miembro baneado"), 23: ("Miembros", "Baneo retirado"),
    24: ("Miembros", "Miembro actualizado"), 25: ("Miembros", "Roles de miembro actualizados"),
    26: ("Miembros", "Miembro movido de canal"), 27: ("Miembros", "Miembro desconectado"),
    28: ("Miembros", "Bot añadido"),
    30: ("Roles", "Rol creado"), 31: ("Roles", "Rol actualizado"), 32: ("Roles", "Rol eliminado"),
    40: ("Invitaciones", "Invitación creada"), 41: ("Invitaciones", "Invitación actualizada"),
    42: ("Invitaciones", "Invitación eliminada"),
    50: ("Webhooks", "Webhook creado"), 51: ("Webhooks", "Webhook actualizado"),
    52: ("Webhooks", "Webhook eliminado"),
    60: ("Emojis", "Emoji creado"), 61: ("Emojis", "Emoji actualizado"), 62: ("Emojis", "Emoji eliminado"),
    72: ("Mensajes", "Mensaje eliminado"), 73: ("Mensajes", "Mensajes eliminados en masa"),
    74: ("Mensajes", "Mensaje fijado"), 75: ("Mensajes", "Mensaje despinado"),
    80: ("Integraciones", "Integración creada"), 81: ("Integraciones", "Integración actualizada"),
    82: ("Integraciones", "Integración eliminada"),
    90: ("Stickers", "Sticker creado"), 91: ("Stickers", "Sticker actualizado"),
    92: ("Stickers", "Sticker eliminado"),
    100: ("Escenarios", "Escenario creado"), 101: ("Escenarios", "Escenario actualizado"),
    102: ("Escenarios", "Escenario eliminado"),
    110: ("Hilos", "Hilo creado"), 111: ("Hilos", "Hilo actualizado"), 112: ("Hilos", "Hilo eliminado"),
    140: ("Automod", "Regla de automod creada"), 141: ("Automod", "Regla de automod actualizada"),
    142: ("Automod", "Regla de automod eliminada"), 143: ("Automod", "Mensaje bloqueado"),
    144: ("Automod", "Mensaje marcado"), 145: ("Automod", "Miembro aislado por automod"),
    180: ("Eventos", "Evento creado"), 181: ("Eventos", "Evento actualizado"), 182: ("Eventos", "Evento eliminado"),
}

AUDIT_CATEGORIES = ["Todas", "Servidor", "Canales", "Miembros", "Roles",
                    "Invitaciones", "Webhooks", "Emojis", "Mensajes", "Hilos",
                    "Automod", "Integraciones", "Stickers", "Eventos", "Escenarios"]

def audit_action_label(action_type: int | None) -> str:
    entry = AUDIT_ACTIONS.get(int(action_type or 0))
    return entry[1] if entry else f"Acción #{action_type}"

def audit_action_category(action_type: int | None) -> str:
    entry = AUDIT_ACTIONS.get(int(action_type or 0))
    return entry[0] if entry else "Otras"

# --------------------------------------------------------------------------- #
# Automod
# --------------------------------------------------------------------------- #

AUTOMOD_TRIGGERS = [
    (1, "Palabras clave", "Lista de palabras o frases prohibidas."),
    (3, "Spam", "Mensajes repetidos o demasiado rápidos."),
    (4, "Palabras predefinidas", "Listas listas para usar de Discord."),
    (5, "Menciones masivas", "Demasiadas menciones en un mensaje."),
    (6, "Perfil de miembro", "Apodo o nombre de usuario inapropiado."),
]

AUTOMOD_KEYWORD_PRESETS = [
    ("PROFANITY", "Groserías"), ("SEXUAL_CONTENT", "Contenido sexual"),
    ("SLURS", "Insultos discriminatorios"),
]

AUTOMOD_EVENTS = [(1, "Mensaje enviado"), (2, "Miembro actualizado")]

AUTOMOD_ACTION_TYPES = [
    (1, "Bloquear el mensaje"),
    (2, "Enviar alerta a un canal"),
    (3, "Aislar al autor (timeout)"),
    (4, "Bloquear interacción"),
]

# --------------------------------------------------------------------------- #
# Moderación
# --------------------------------------------------------------------------- #

DELETE_MESSAGE_WINDOWS = [(0, "No borrar nada"), (3600, "Última hora"),
                          (21600, "Últimas 6 horas"), (86400, "Últimas 24 horas"),
                          (259200, "Últimos 3 días"), (604800, "Últimos 7 días")]

TIMEOUT_PRESETS = [("60 segundos", 60), ("5 minutos", 300), ("10 minutos", 600),
                   ("1 hora", 3600), ("1 día", 86400), ("1 semana", 604800)]

INVITE_MAX_AGES = [(0, "Nunca caduca"), (1800, "30 minutos"), (3600, "1 hora"),
                   (21600, "6 horas"), (43200, "12 horas"), (86400, "1 día"),
                   (604800, "7 días")]

ROLE_COLOR_PRESETS = [
    "#1abc9c", "#2ecc71", "#3498db", "#9b59b6", "#e91e63", "#f1c40f",
    "#e67e22", "#e74c3c", "#95a5a6", "#607d8b", "#5865f2", "#eb459e",
]

# Límites prácticos de la API que conviene avisar en la UI.
MAX_ROLES = 250
MAX_CHANNELS = 500
MAX_EMOJIS = {"0": 50, "1": 100, "2": 150, "3": 250}
BULK_DELETE_MAX = 100
MEMBER_FETCH_MAX = 1000
