#!/usr/bin/env python3
"""Generate docs/images/project.png — fueldesk project banner (Pillow)."""

from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Pillow required: pip install pillow") from exc


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out = root / "docs" / "images" / "project.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    w, h = 1280, 720
    img = Image.new("RGB", (w, h), "#0f1419")
    draw = ImageDraw.Draw(img)

    # Gradient-ish bands
    for y in range(h):
        t = y / h
        r = int(15 + t * 12)
        g = int(20 + t * 18)
        b = int(25 + t * 22)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    # Soft accent orbs
    draw.ellipse([900, -80, 1400, 420], fill="#1a3d32")
    draw.ellipse([-120, 400, 420, 900], fill="#3a2422")

    # Cards
    def card(xy, size, fill="#1c2430", outline="#2a3544"):
        x, y = xy
        cw, ch = size
        draw.rounded_rectangle([x, y, x + cw, y + ch], radius=18, fill=fill, outline=outline, width=2)

    card((80, 160), (360, 420))
    card((470, 160), (360, 420))
    card((860, 160), (340, 420))

    # Accent bars
    draw.rounded_rectangle([110, 200, 250, 214], radius=6, fill="#3ecf8e")
    draw.rounded_rectangle([500, 200, 640, 214], radius=6, fill="#ff7a6e")
    draw.rounded_rectangle([890, 200, 1030, 214], radius=6, fill="#3ecf8e")

    # Fake chart line on middle card
    pts = [(520, 480), (580, 430), (640, 450), (700, 360), (760, 390), (800, 320)]
    draw.line(pts, fill="#3ecf8e", width=4)
    for p in pts:
        draw.ellipse([p[0] - 4, p[1] - 4, p[0] + 4, p[1] + 4], fill="#ff7a6e")

    # Stat blocks left card
    for i, color in enumerate(["#3ecf8e", "#ff7a6e", "#e8eef6", "#8b9bb0"]):
        y0 = 250 + i * 70
        draw.rounded_rectangle([110, y0, 400, y0 + 50], radius=10, fill="#141a22", outline="#2a3544")
        draw.rectangle([110, y0, 118, y0 + 50], fill=color)

    # Training rows right card
    for i in range(5):
        y0 = 250 + i * 55
        draw.rounded_rectangle([890, y0, 1160, y0 + 40], radius=8, fill="#141a22", outline="#2a3544")
        draw.rounded_rectangle([900, y0 + 12, 980, y0 + 28], radius=4, fill="#3ecf8e")

    # Title
    try:
        font_lg = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 64)
        font_md = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 28)
        font_sm = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 22)
    except OSError:
        font_lg = ImageFont.load_default()
        font_md = font_lg
        font_sm = font_lg

    draw.text((80, 48), "fueldesk", fill="#e8eef6", font=font_lg)
    draw.text(
        (80, 118),
        "Personal Fuel & Training Protocol Desk  ·  local-first",
        fill="#8b9bb0",
        font=font_md,
    )

    # Footer chips
    chips = ["BMR/TDEE", "Weekly meals", "Training plan", "Check-ins", "Export JSON"]
    x = 80
    for chip in chips:
        tw = draw.textlength(chip, font=font_sm) if hasattr(draw, "textlength") else 100
        draw.rounded_rectangle([x, 640, x + tw + 28, 680], radius=16, fill="#171d25", outline="#2a3544")
        draw.text((x + 14, 648), chip, fill="#3ecf8e", font=font_sm)
        x += int(tw + 40)

    img.save(out, "PNG")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
