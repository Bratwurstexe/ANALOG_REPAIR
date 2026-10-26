"""Rasterize the app mark (a VHS cassette, the static form of docs/media/logo.svg)
for the desktop packages: Assets/app.png and Assets/app.ico. The launcher uses the same files.

The geometry matches desktop/AnalogRepair.Desktop/Assets/app.svg on a 256 grid.
Needs Pillow: python desktop/make_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
SCALE = SIZE / 256

BACKGROUND = "#252B31"
BODY = "#30363C"
EDGE = "#5A646D"
FLAP = "#1A1E22"
WINDOW = "#7A7672"
WINDOW_EDGE = "#121518"
TAPE = "#3D2418"
HUB = "#F3F3F0"
LABEL = "#F3E3C7"
STRIPE = "#F08A3A"
INK = "#5B4636"


def pt(*values: float) -> tuple[int, ...]:
    return tuple(round(value * SCALE) for value in values)


def draw_mark() -> Image.Image:
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(pt(8, 8, 248, 248), radius=round(56 * SCALE), fill=BACKGROUND)
    # Body, about 1.8 : 1, with the dust flap along the top edge
    draw.rounded_rectangle(pt(20, 68, 236, 188), radius=round(8 * SCALE), fill=BODY,
                           outline=EDGE, width=round(4 * SCALE))
    draw.rounded_rectangle(pt(22, 70, 234, 88), radius=round(6 * SCALE), fill=FLAP)
    draw.rectangle(pt(20, 88, 236, 90), fill=EDGE)
    # Wide window: a full tape pack on the left, a nearly empty spool on the right
    window = pt(62, 98, 194, 142)
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle(window, radius=round(5 * SCALE), fill=255)
    inside = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    inner = ImageDraw.Draw(inside)
    inner.rectangle(window, fill=WINDOW)
    for cx, radius in ((96, 30), (160, 13)):
        inner.ellipse(pt(cx - radius, 120 - radius, cx + radius, 120 + radius), fill=TAPE)
    canvas.paste(inside, (0, 0), mask)
    draw.rounded_rectangle(window, radius=round(5 * SCALE), outline=WINDOW_EDGE, width=round(3 * SCALE))
    for cx in (96, 160):
        draw.ellipse(pt(cx - 9, 111, cx + 9, 129), fill=HUB)
        draw.ellipse(pt(cx - 3, 117, cx + 3, 123), fill=BODY)
    # Paper label with its orange stripe, and the PLAY triangle
    draw.rounded_rectangle(pt(36, 152, 150, 178), radius=round(3 * SCALE), fill=LABEL)
    draw.rectangle(pt(36, 156, 150, 161), fill=STRIPE)
    draw.line([pt(46, 170), pt(110, 168)], fill=INK, width=round(3 * SCALE))
    draw.polygon([pt(186, 156), pt(204, 165), pt(186, 174)], fill=STRIPE)
    return canvas


def main() -> None:
    canvas = draw_mark()
    asset_dir = Path(__file__).parent / "AnalogRepair.Desktop" / "Assets"
    canvas.resize((256, 256), Image.Resampling.LANCZOS).save(asset_dir / "app.png")
    canvas.save(asset_dir / "app.ico", format="ICO",
                sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    main()
