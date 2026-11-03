"""Add numbered step markers to the Hello FPGA GUI screenshot (board page, "Flashing").

    python annotate_gui.py <hello_gui.png> <hello_fpga_gui_programmer.png>

The input is the original 745x684 screenshot of Hello FPGA GUI V1.3 (FPGA
Programmer tab). The boxes are the controls of the steps in index.rst:
1 COM port + Connect, 2 DAT file, 3 Action PROGRAM, 4 Run. Convert the result
with to_webp.py. Needs Pillow.
"""

import sys

from PIL import Image, ImageDraw, ImageFont

ORANGE = (232, 113, 10)
WHITE = (255, 255, 255)

# step: (box left, top, right, bottom), badge centre
STEPS = {
    1: ((530, 40, 694, 76), (516, 58)),
    2: ((24, 136, 719, 165), (92, 128)),
    3: ((24, 187, 224, 214), (82, 179)),
    4: ((244, 181, 346, 216), (360, 198)),
}
BADGE_R = 12


def font(size):
    for name in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main():
    img = Image.open(sys.argv[1]).convert("RGB")
    draw = ImageDraw.Draw(img)
    f = font(15)
    for n, (box, (cx, cy)) in STEPS.items():
        draw.rounded_rectangle(box, radius=4, outline=ORANGE, width=3)
        draw.ellipse((cx - BADGE_R, cy - BADGE_R, cx + BADGE_R, cy + BADGE_R),
                     fill=ORANGE, outline=WHITE, width=2)
        draw.text((cx, cy), str(n), fill=WHITE, font=f, anchor="mm")
    img.save(sys.argv[2])


if __name__ == "__main__":
    main()
