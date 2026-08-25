"""Draw the chess-pawn app icon and write assets/pawn.ico.

Run once after changing the shape or colours:

    .venv/Scripts/python.exe assets/make_icon.py

Pillow is only needed for this script, never at runtime.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent

SIZE = 1024  # drawn large, then downsampled for crisp small sizes
BACKGROUND = (47, 62, 78, 255)  # the same slate as the sheet header
PAWN = (245, 247, 250, 255)
ICO_SIZES = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]


def _rounded(draw: ImageDraw.ImageDraw, box, radius: float, fill) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def draw_pawn(draw: ImageDraw.ImageDraw, s: int) -> None:
    """A classic pawn silhouette: head, collar, flared body, stepped base."""

    def x(v: float) -> float:
        return v * s

    def y(v: float) -> float:
        return v * s

    # head
    head_cx, head_cy, head_r = 0.5, 0.275, 0.132
    draw.ellipse(
        [x(head_cx - head_r), y(head_cy - head_r), x(head_cx + head_r), y(head_cy + head_r)],
        fill=PAWN,
    )

    # collar just under the head
    _rounded(draw, [x(0.335), y(0.395), x(0.665), y(0.462)], radius=x(0.033), fill=PAWN)

    # body: a curve flaring from the collar down to the base
    top_y, bottom_y = 0.455, 0.70
    top_half, bottom_half = 0.088, 0.225
    steps = 60
    left, right = [], []
    for step in range(steps + 1):
        t = step / steps
        half = top_half + (bottom_half - top_half) * (t**2.3)
        py = top_y + (bottom_y - top_y) * t
        left.append((x(0.5 - half), y(py)))
        right.append((x(0.5 + half), y(py)))
    draw.polygon(left + right[::-1], fill=PAWN)

    # base: a collar above the foot, then the foot itself
    _rounded(draw, [x(0.255), y(0.688), x(0.745), y(0.762)], radius=x(0.030), fill=PAWN)
    _rounded(draw, [x(0.205), y(0.775), x(0.795), y(0.868)], radius=x(0.036), fill=PAWN)


def build() -> Path:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    _rounded(draw, [0, 0, SIZE - 1, SIZE - 1], radius=SIZE * 0.18, fill=BACKGROUND)
    draw_pawn(draw, SIZE)

    target = HERE / "pawn.ico"
    image.save(target, format="ICO", sizes=ICO_SIZES)
    image.resize((256, 256), Image.LANCZOS).save(HERE / "pawn.png")
    return target


if __name__ == "__main__":
    print(f"Wrote {build()}")
