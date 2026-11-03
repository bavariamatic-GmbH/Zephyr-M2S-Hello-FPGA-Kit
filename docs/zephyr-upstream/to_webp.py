"""Convert a screenshot to a WebP that passes Zephyr's ImageSize compliance check.

Zephyr limits images under boards/ to 100 KB and recommends at most 600 px on
the longest side (doc/contribute/documentation/guidelines.rst). Needs Pillow.

    python to_webp.py <input.png> <output.webp> [max_px]
"""

import os
import sys

from PIL import Image

LIMIT = 100 * 1024


def main():
    src, dst = sys.argv[1], sys.argv[2]
    max_px = int(sys.argv[3]) if len(sys.argv) > 3 else 600
    img = Image.open(src).convert("RGB")
    img.thumbnail((max_px, max_px), Image.LANCZOS)
    for quality in (85, 75, 65, 55, 45):
        img.save(dst, "WEBP", quality=quality, method=6)
        size = os.path.getsize(dst)
        if size <= LIMIT:
            print(f"{dst}: {img.width}x{img.height}, quality {quality}, {size // 1024} KB")
            return 0
    print(f"{dst}: still {size // 1024} KB, use a smaller max_px")
    return 1


if __name__ == "__main__":
    sys.exit(main())
