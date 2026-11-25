"""Genera el icono de la aplicación (herramienta de desarrollo, usa Pillow)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "dss" / "ui" / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

SIZE = 256
image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)

# Fondo con degradado vertical dentro de un cuadrado redondeado.
mask = Image.new("L", (SIZE, SIZE), 0)
ImageDraw.Draw(mask).rounded_rectangle((8, 8, SIZE - 8, SIZE - 8), radius=60, fill=255)
gradient = Image.new("RGBA", (SIZE, SIZE))
top = (0x58, 0x65, 0xF2)
bottom = (0x8A, 0x3E, 0xE8)
for y in range(SIZE):
    ratio = y / (SIZE - 1)
    color = tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
    ImageDraw.Draw(gradient).line([(0, y), (SIZE, y)], fill=(*color, 255))
image.paste(gradient, (0, 0), mask)

# Brillo sutil en la esquina superior izquierda.
glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
ImageDraw.Draw(glow).ellipse((-90, -140, 170, 120), fill=(255, 255, 255, 26))
image = Image.alpha_composite(image, glow)

draw = ImageDraw.Draw(image)
font = None
for candidate in ("C:/Windows/Fonts/seguisb.ttf", "C:/Windows/Fonts/segoeuib.ttf",
                  "C:/Windows/Fonts/arialbd.ttf"):
    try:
        font = ImageFont.truetype(candidate, 150)
        break
    except OSError:
        continue
if font is None:
    font = ImageFont.load_default()

text = "#"
box = draw.textbbox((0, 0), text, font=font)
width = box[2] - box[0]
height = box[3] - box[1]
draw.text(((SIZE - width) / 2 - box[0], (SIZE - height) / 2 - box[1] - 6), text,
          font=font, fill=(255, 255, 255, 255))

image.save(ASSETS / "app.png")
image.save(ASSETS / "app.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64),
                                      (128, 128), (256, 256)])
print("iconos generados en", ASSETS)
