"""
gen_logo.py — Genera el logo de Loveo (módulo isométrico en acero) como .ico (ícono del escritorio)
y .png (favicon de la pestaña). Reproducible: correr y regenera assets/loveo.ico + assets/loveo.png.

  python scripts/gen_logo.py
"""
import pathlib

from PIL import Image, ImageDraw

S = 256
ASSETS = pathlib.Path(__file__).resolve().parent.parent / "assets"

# Paleta: badge azul acero (construcción), módulo con cara superior ámbar (el acento de marca).
NAVY_TOP = (20, 33, 57)
NAVY_BOT = (41, 76, 120)
CARA_TOP = (244, 183, 64)      # ámbar (cara superior del módulo)
CARA_TOP_HI = (255, 205, 96)
CARA_IZQ = (150, 167, 194)     # acero medio (sombra)
CARA_DER = (219, 228, 242)     # acero claro (luz)
BORDE = (17, 26, 43)


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _fondo():
    grad = Image.new("RGB", (S, S))
    d = ImageDraw.Draw(grad)
    for y in range(S):
        d.line([(0, y), (S, y)], fill=_lerp(NAVY_TOP, NAVY_BOT, y / S))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=54, fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    return img


def _modulo(img):
    d = ImageDraw.Draw(img)
    cx, cy = 128, 138
    hw, qh, bh = 68, 35, 60          # medio-ancho, medio-alto del rombo, alto del cuerpo
    ty = cy - bh // 2
    top = (cx, ty - qh)
    right = (cx + hw, ty)
    front = (cx, ty + qh)
    left = (cx - hw, ty)
    b_right = (cx + hw, ty + bh)
    b_front = (cx, ty + qh + bh)
    b_left = (cx - hw, ty + bh)

    # sombra suelo (elipse difusa por capas)
    for i, a in ((16, 40), (10, 60), (4, 90)):
        d.ellipse([cx - hw + 6 - i, b_front[1] - 10 - i // 3, cx + hw - 6 + i, b_front[1] + 14 + i // 3],
                  fill=(10, 16, 28, a))

    d.polygon([left, front, b_front, b_left], fill=CARA_IZQ, outline=BORDE)      # cara izquierda
    d.polygon([right, front, b_front, b_right], fill=CARA_DER, outline=BORDE)    # cara derecha
    d.polygon([top, right, front, left], fill=CARA_TOP, outline=BORDE)          # cara superior (ámbar)
    # brillo en la cara superior (triángulo claro hacia la arista de luz)
    d.polygon([top, right, front], fill=CARA_TOP_HI)
    d.polygon([top, right, front, left], outline=BORDE)
    # líneas de módulo (paneles) en las caras verticales
    for k in (1, 2):
        yy = ty + bh * k // 3
        d.line([(cx - hw, yy), (cx, yy + qh)], fill=(120, 136, 162), width=2)
        d.line([(cx, yy + qh), (cx + hw, yy)], fill=(198, 208, 224), width=2)
    return img


def main():
    ASSETS.mkdir(exist_ok=True)
    img = _modulo(_fondo())
    png = ASSETS / "loveo.png"
    ico = ASSETS / "loveo.ico"
    img.save(png)
    img.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"OK · {png}\nOK · {ico}")


if __name__ == "__main__":
    main()
