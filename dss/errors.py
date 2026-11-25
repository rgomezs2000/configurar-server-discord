"""Errores de Discord traducidos a mensajes accionables en español."""
from __future__ import annotations

from typing import Any

# Códigos de error JSON de Discord que merecen un mensaje específico.
CODE_MESSAGES: dict[int, str] = {
    0: "Error genérico de la API de Discord.",
    10003: "El canal no existe o fue eliminado.",
    10004: "El servidor no existe o la aplicación no está en él.",
    10007: "El miembro no existe en este servidor.",
    10008: "El mensaje no existe o ya fue eliminado.",
    10009: "No se puede enviar mensajes directos a este usuario (tiene los MD cerrados).",
    10011: "El usuario no existe.",
    10013: "El rol no existe o fue eliminado.",
    10014: "El emoji no existe.",
    10015: "El webhook no existe.",
    10026: "La invitación no existe o ya expiró.",
    20001: "Esta acción solo funciona con tokens de bot.",
    30001: "Se alcanzó el límite de servidores.",
    30005: "Se alcanzó el límite de roles del servidor.",
    30010: "Se alcanzó el límite de canales del servidor.",
    30013: "Se alcanzó el límite de emojis del servidor.",
    30035: "Se alcanzó el límite de reglas de automod.",
    30037: "Se alcanzó el límite de invitaciones.",
    40001: "Token no válido.",
    40002: "Debes verificar la cuenta para hacer esto.",
    40005: "El archivo es demasiado grande.",
    40006: "La solicitud fue bloqueada por el límite de peticiones.",
    50001: "Falta acceso a este recurso (revisa los permisos del bot en el servidor).",
    50002: "Tipo de cuenta no válido para esta acción.",
    50005: "No puedes editar un mensaje de otro usuario.",
    50013: "Faltan permisos para esta acción.",
    50024: "Discord no permite esa acción en ese canal o el miembro ya no está "
           "conectado a la sala de voz.",
    50016: "El canal ya tiene demasiados webhooks.",
    50035: "Datos no válidos: revisa el formulario.",
    50036: "El cuerpo de la solicitud no es válido.",
    50074: "No se puede eliminar este canal: es el canal de reglas o del sistema.",
    60003: "El servidor exige 2FA para las acciones de moderación.",
    90001: "El bot no puede banear al propietario del servidor.",
}

STATUS_MESSAGES: dict[int, str] = {
    400: "La solicitud no es válida.",
    401: ("Token inválido o expirado. Revisa que hayas elegido el tipo de token correcto "
          "(Bot o Cuenta) y que el token siga activo."),
    403: "Faltan permisos para esta acción.",
    404: "Recurso no encontrado.",
    405: "Método no permitido.",
    413: "El archivo supera el tamaño máximo permitido.",
    429: "Demasiadas peticiones: Discord pidió esperar.",
    500: "Discord tuvo un error interno. Inténtalo de nuevo.",
    502: "Discord no está disponible en este momento.",
    503: "Discord está en mantenimiento.",
}


class DiscordError(Exception):
    """Error de API con contexto suficiente para mostrarlo en la interfaz."""

    def __init__(self, message: str, *, status: int = 0, code: int | None = None,
                 details: list[str] | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.details = details or []
        self.retry_after = retry_after

    @property
    def is_auth_error(self) -> bool:
        return self.status == 401 or self.code in (40001, 0) and "token" in self.message.lower()

    def __str__(self) -> str:
        text = self.message
        if self.code and self.code not in (0,):
            text = f"{text} (código {self.code})"
        if self.details:
            text = f"{text}\n• " + "\n• ".join(self.details[:4])
        return text


def _collect_errors(node: Any, prefix: str = "") -> list[str]:
    """Extrae errores de formulario del campo ``errors`` de la respuesta 50035."""
    found: list[str] = []
    if not isinstance(node, dict):
        return found
    for key, value in node.items():
        if key == "_errors" and isinstance(value, list):
            for item in value:
                message = item.get("message") if isinstance(item, dict) else None
                if message:
                    found.append(f"{prefix or 'general'}: {message}")
        elif isinstance(value, dict):
            found.extend(_collect_errors(value, f"{prefix}{key}." if prefix else f"{key}."))
    return found


def from_http_error(status: int, payload: Any) -> DiscordError:
    payload = payload if isinstance(payload, dict) else {}
    raw_message = str(payload.get("message") or "").strip()
    code = payload.get("code")
    code_int = int(code) if isinstance(code, (int, float)) else None

    if code_int is not None and code_int in CODE_MESSAGES and code_int != 0:
        message = CODE_MESSAGES[code_int]
    elif status in STATUS_MESSAGES:
        message = STATUS_MESSAGES[status]
    elif raw_message:
        message = raw_message
    else:
        message = f"Error {status} al hablar con Discord."

    details = _collect_errors(payload.get("errors")) if status == 400 else []
    retry = payload.get("retry_after")
    return DiscordError(message, status=status, code=code_int, details=details,
                        retry_after=float(retry) if isinstance(retry, (int, float)) else None)
