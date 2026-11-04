# -*- coding: utf-8 -*-
"""生成 icon.ico：深色圆角方块里一个「秒」字。"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SIZE = 512
FONTS = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
]


def font(px):
    for path in FONTS:
        try:
            return ImageFont.truetype(path, px)
        except OSError:
            continue
    return ImageFont.load_default()


img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)
draw.rounded_rectangle((16, 16, SIZE - 16, SIZE - 16), radius=120, fill=(29, 26, 22, 255))
f = font(300)
box = draw.textbbox((0, 0), "秒", font=f)
w, h = box[2] - box[0], box[3] - box[1]
draw.text(((SIZE - w) / 2 - box[0], (SIZE - h) / 2 - box[1] - 6), "秒", font=f, fill=(246, 241, 232, 255))
draw.ellipse((SIZE - 150, SIZE - 150, SIZE - 96, SIZE - 96), fill=(64, 168, 112, 255))
img.save(HERE / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(HERE / "icon.ico")
