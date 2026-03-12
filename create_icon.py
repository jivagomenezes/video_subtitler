"""
Generates icon.icns for the Video Subtitle Mac app.
Requires: pip install Pillow
Run once before building the .app bundle.
"""

import os
import shutil
import subprocess
from PIL import Image, ImageDraw, ImageFont


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = size * 0.06  # margin for rounded rect

    # Background — dark rounded rectangle
    d.rounded_rectangle(
        [m, m, size - m, size - m],
        radius=size * 0.18,
        fill=(28, 28, 30, 255),
    )

    # Blue accent bar at top
    bar_h = size * 0.12
    d.rounded_rectangle(
        [m, m, size - m, m + bar_h],
        radius=size * 0.18,
        fill=(10, 132, 255, 255),
    )
    # Cover bottom corners of accent bar (so only top is rounded)
    d.rectangle(
        [m, m + bar_h * 0.5, size - m, m + bar_h],
        fill=(10, 132, 255, 255),
    )

    # Play triangle
    cx = size * 0.46
    cy = size * 0.46
    r = size * 0.22
    pts = [
        (cx - r * 0.6, cy - r),
        (cx - r * 0.6, cy + r),
        (cx + r,       cy),
    ]
    d.polygon(pts, fill=(255, 255, 255, 230))

    # Subtitle bars (two lines at bottom)
    bar_y1 = size * 0.73
    bar_y2 = size * 0.84
    bar_radius = size * 0.025
    bar_color = (255, 255, 255, 180)
    gap = size * 0.08

    # Long bar
    d.rounded_rectangle(
        [gap, bar_y1, size - gap, bar_y1 + size * 0.07],
        radius=bar_radius,
        fill=bar_color,
    )
    # Short bar (centered)
    short_w = (size - gap * 2) * 0.6
    short_x = (size - short_w) / 2
    d.rounded_rectangle(
        [short_x, bar_y2, short_x + short_w, bar_y2 + size * 0.07],
        radius=bar_radius,
        fill=bar_color,
    )

    return img


def build_icns(output_path: str = "icon.icns"):
    iconset_dir = "icon.iconset"
    os.makedirs(iconset_dir, exist_ok=True)

    sizes = [16, 32, 64, 128, 256, 512, 1024]
    for s in sizes:
        img = draw_icon(s)
        img.save(os.path.join(iconset_dir, f"icon_{s}x{s}.png"))
        # Retina variant (2x) for sizes up to 512
        if s <= 512:
            img2 = draw_icon(s * 2)
            img2.save(os.path.join(iconset_dir, f"icon_{s}x{s}@2x.png"))

    result = subprocess.run(
        ["iconutil", "-c", "icns", iconset_dir, "-o", output_path],
        capture_output=True, text=True,
    )
    shutil.rmtree(iconset_dir)

    if result.returncode == 0:
        print(f"✅ Icon created: {output_path}")
    else:
        print(f"❌ iconutil failed: {result.stderr}")


if __name__ == "__main__":
    build_icns()
