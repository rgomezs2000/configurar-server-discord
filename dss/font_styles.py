"""Conversión de nombres a estilos Unicode tipo Glyphy/Discord."""
from __future__ import annotations

from typing import Callable

# Alfabetos matemáticos Unicode. Se usan mapas explícitos para cubrir los huecos.
_UPPER = {
    "bold": (0x1D400, {}),
    "italic": (0x1D434, {"h": 0x210E}),
    "bold_italic": (0x1D468, {}),
    "script": (0x1D49C, {"B": 0x212C, "E": 0x2130, "F": 0x2131,
                          "H": 0x210B, "I": 0x2110, "L": 0x2112,
                          "M": 0x2133, "R": 0x211B}),
    "bold_script": (0x1D4D0, {}),
    "fraktur": (0x1D504, {"C": 0x212D, "H": 0x210C, "I": 0x2111,
                           "R": 0x211C, "Z": 0x2128}),
    "bold_fraktur": (0x1D56C, {}),
    "double": (0x1D538, {"C": 0x2102, "H": 0x210D, "N": 0x2115,
                          "P": 0x2119, "Q": 0x211A, "R": 0x211D,
                          "Z": 0x2124}),
    "sans": (0x1D5A0, {}),
    "sans_bold": (0x1D5D4, {}),
    "sans_italic": (0x1D608, {}),
    "sans_bold_italic": (0x1D63C, {}),
    "mono": (0x1D670, {}),
}
_LOWER = {
    "bold": (0x1D41A, {}),
    "italic": (0x1D44E, {"h": 0x210E}),
    "bold_italic": (0x1D482, {}),
    "script": (0x1D4B6, {"e": 0x212F, "g": 0x210A, "o": 0x2134}),
    "bold_script": (0x1D4EA, {}),
    "fraktur": (0x1D51E, {}),
    "bold_fraktur": (0x1D586, {}),
    "double": (0x1D552, {}),
    "sans": (0x1D5BA, {}),
    "sans_bold": (0x1D5EE, {}),
    "sans_italic": (0x1D622, {}),
    "sans_bold_italic": (0x1D656, {}),
    "mono": (0x1D68A, {}),
}
_DIGITS = {
    "bold": 0x1D7CE, "double": 0x1D7D8, "sans": 0x1D7E2,
    "sans_bold": 0x1D7EC, "mono": 0x1D7F6,
}
_SMALL_CAPS = {
    "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ꜰ", "g": "ɢ",
    "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ", "m": "ᴍ", "n": "ɴ",
    "o": "ᴏ", "p": "ᴘ", "q": "ǫ", "r": "ʀ", "s": "ꜱ", "t": "ᴛ", "u": "ᴜ",
    "v": "ᴠ", "w": "ᴡ", "x": "x", "y": "ʏ", "z": "ᴢ",
}
_SUPERSCRIPT = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵",
    "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹", "+": "⁺", "-": "⁻",
    "=": "⁼", "(": "⁽", ")": "⁾", "a": "ᵃ", "b": "ᵇ", "c": "ᶜ",
    "d": "ᵈ", "e": "ᵉ", "f": "ᶠ", "g": "ᵍ", "h": "ʰ", "i": "ⁱ",
    "j": "ʲ", "k": "ᵏ", "l": "ˡ", "m": "ᵐ", "n": "ⁿ", "o": "ᵒ",
    "p": "ᵖ", "r": "ʳ", "s": "ˢ", "t": "ᵗ", "u": "ᵘ", "v": "ᵛ",
    "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ",
}
_SUBSCRIPT = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅",
    "6": "₆", "7": "₇", "8": "₈", "9": "₉", "+": "₊", "-": "₋",
    "=": "₌", "(": "₍", ")": "₎", "a": "ₐ", "e": "ₑ", "h": "ₕ",
    "i": "ᵢ", "j": "ⱼ", "k": "ₖ", "l": "ₗ", "m": "ₘ", "n": "ₙ",
    "o": "ₒ", "p": "ₚ", "r": "ᵣ", "s": "ₛ", "t": "ₜ", "u": "ᵤ",
    "v": "ᵥ", "x": "ₓ",
}


def _math(text: str, style: str) -> str:
    upper = _UPPER[style]
    lower = _LOWER[style]
    digits = _DIGITS.get(style)
    out = []
    for char in text:
        if "A" <= char <= "Z":
            base, holes = upper
            out.append(chr(holes.get(char, base + ord(char) - ord("A"))))
        elif "a" <= char <= "z":
            base, holes = lower
            out.append(chr(holes.get(char, base + ord(char) - ord("a"))))
        elif digits is not None and "0" <= char <= "9":
            out.append(chr(digits + ord(char) - ord("0")))
        else:
            out.append(char)
    return "".join(out)


def _fullwidth(text: str) -> str:
    out = []
    for char in text:
        code = ord(char)
        if char == " ":
            out.append("\u3000")
        elif 0x21 <= code <= 0x7E:
            out.append(chr(code + 0xFEE0))
        else:
            out.append(char)
    return "".join(out)


def _mapped(text: str, mapping: dict[str, str]) -> str:
    return "".join(mapping.get(char.lower(), char) for char in text)


def _circled(text: str) -> str:
    out = []
    for char in text:
        if "A" <= char <= "Z":
            out.append(chr(0x24B6 + ord(char) - ord("A")))
        elif "a" <= char <= "z":
            out.append(chr(0x24D0 + ord(char) - ord("a")))
        elif "1" <= char <= "9":
            out.append(chr(0x2460 + ord(char) - ord("1")))
        elif char == "0":
            out.append("⓪")
        else:
            out.append(char)
    return "".join(out)


def _squared(text: str) -> str:
    out = []
    for char in text:
        if "A" <= char <= "Z":
            out.append(chr(0x1F130 + ord(char) - ord("A")))
        elif "a" <= char <= "z":
            out.append(chr(0x1F130 + ord(char.upper()) - ord("A")))
        else:
            out.append(char)
    return "".join(out)


def _combining(mark: str) -> Callable[[str], str]:
    return lambda text: "".join(char + mark for char in text)


STYLES: dict[str, Callable[[str], str]] = {
    "Normal": lambda text: text,
    "Negrita": lambda text: _math(text, "bold"),
    "Cursiva": lambda text: _math(text, "italic"),
    "Negrita cursiva": lambda text: _math(text, "bold_italic"),
    "Manuscrita": lambda text: _math(text, "script"),
    "Manuscrita negrita": lambda text: _math(text, "bold_script"),
    "Gótica": lambda text: _math(text, "fraktur"),
    "Gótica negrita": lambda text: _math(text, "bold_fraktur"),
    "Doble trazo": lambda text: _math(text, "double"),
    "Sans": lambda text: _math(text, "sans"),
    "Sans negrita": lambda text: _math(text, "sans_bold"),
    "Sans cursiva": lambda text: _math(text, "sans_italic"),
    "Sans negrita cursiva": lambda text: _math(text, "sans_bold_italic"),
    "Monoespaciada": lambda text: _math(text, "mono"),
    "Ancho completo": _fullwidth,
    "Versalitas": lambda text: _mapped(text, _SMALL_CAPS),
    "Superíndice": lambda text: _mapped(text, _SUPERSCRIPT),
    "Subíndice": lambda text: _mapped(text, _SUBSCRIPT),
    "Círculos": _circled,
    "Cuadrados": _squared,
    "Tachado": _combining("\u0336"),
    "Subrayado": _combining("\u0332"),
}

STYLE_NAMES = list(STYLES)


def apply_font_style(text: str, style: str) -> str:
    converter = STYLES.get(style)
    return converter(text) if converter else text
