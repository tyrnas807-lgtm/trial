"""Average-color helpers: compute, sort, and build a mosaic."""
import colorsys
from pathlib import Path

from PIL import Image, ImageDraw


def average_color(path) -> tuple[int, int, int]:
    """Mean RGB of an image (downscaled first for speed)."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((64, 64))
        px = list(im.getdata())
    n = len(px)
    return tuple(round(sum(p[i] for p in px) / n) for i in range(3))


def sort_key(rgb, mode: str = "hue"):
    r, g, b = (c / 255 for c in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if mode == "brightness":
        return 0.299 * r + 0.587 * g + 0.114 * b
    # hue mode: colorful images ordered around the color wheel (red -> violet);
    # near-gray images have no meaningful hue, so they go last, dark -> light.
    if s < 0.12:
        return (1, v, 0)
    return (0, h, v)


def sort_images(paths, mode: str = "hue"):
    """Return [(path, rgb), ...] sorted by average color."""
    items = [(p, average_color(p)) for p in paths]
    items.sort(key=lambda it: sort_key(it[1], mode))
    return items


def hex_of(rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def build_mosaic(items, out_path, cols: int = 5, cell: int = 200):
    """Contact sheet of the sorted images, each with a color strip underneath."""
    strip = 18
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + strip)), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (path, rgb) in enumerate(items):
        x, y = (i % cols) * cell, (i // cols) * (cell + strip)
        with Image.open(path) as im:
            im = im.convert("RGB")
            w, h = im.size
            s = min(w, h)  # center-crop to square
            im = im.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))
            sheet.paste(im.resize((cell, cell)), (x, y))
        draw.rectangle([x, y + cell, x + cell, y + cell + strip], fill=rgb)
    sheet.save(out_path, quality=90)
    return Path(out_path)
