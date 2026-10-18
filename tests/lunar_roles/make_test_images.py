"""Generate test_images/ for testing /lunar icon by hand in Discord (not an automated test).

Usage (from the repo root): .venv/Scripts/python.exe -I tests/lunar_roles/make_test_images.py test_images
File 11 is a decompression bomb: never open it in an image viewer.
"""
import io
import os
import random
import sys

from PIL import Image, ImageDraw

out = sys.argv[1]
os.makedirs(out, exist_ok=True)


def path(name):
    return os.path.join(out, name)


def gradient(w, h):
    img = Image.new("RGB", (w, h))
    px = img.load()
    for x in range(w):
        for y in range(h):
            px[x, y] = (x * 255 // max(1, w - 1), y * 255 // max(1, h - 1), 180)
    return img


# Valid images (live: "your image is fine, but role icons need Boost Level 2")
sq = gradient(256, 256)
ImageDraw.Draw(sq).ellipse((48, 48, 208, 208), fill=(250, 240, 120))
sq.save(path("01_ok_square.png"))

wide = gradient(1200, 400)
ImageDraw.Draw(wide).ellipse((500, 100, 700, 300), fill=(255, 255, 255))  # moon in the middle survives the crop
wide.save(path("02_ok_wide.jpg"), quality=85)

rot = gradient(300, 200)
exif = Image.Exif()
exif[0x0112] = 6  # "rotate 90° clockwise" camera orientation
rot.save(path("03_ok_rotated_exif.jpg"), exif=exif.tobytes(), quality=85)

# Refused
noise = Image.frombytes("RGB", (420, 420), bytes(random.getrandbits(8) for _ in range(420 * 420 * 3)))
noise.save(path("04_too_big_over_256kb.png"))

frames = [Image.new("RGB", (64, 64), c) for c in ((255, 0, 0), (0, 0, 255))]
frames[0].save(path("05_animated.png"), save_all=True, append_images=frames[1:], duration=300, loop=0)

frames[0].save(path("06_real.gif"))
with open(path("06_real.gif"), "rb") as f:
    gif_bytes = f.read()
with open(path("07_gif_renamed.png"), "wb") as f:
    f.write(gif_bytes)

with open(path("08_text_renamed.png"), "w", encoding="utf-8") as f:
    f.write("This is a text file pretending to be a PNG.\n")

good = io.BytesIO()
sq.save(good, format="PNG")
with open(path("09_damaged_cut_off.png"), "wb") as f:
    f.write(good.getvalue()[: len(good.getvalue()) // 2])

Image.new("RGB", (5000, 50), (90, 90, 200)).save(path("10_too_wide_5000px.png"))

# Decompression bomb: tiny file, 20000 x 20000 = 400 million pixels when decoded.
# Saved as .png.bin so Discord's upload dialog (and file browsers) won't try to preview it;
# the bot still detects it as a PNG from its content.
Image.new("1", (20000, 20000), 0).save(path("11_BOMB_decompression_DO_NOT_OPEN.png.bin"), format="PNG", optimize=True)

for name in sorted(os.listdir(out)):
    print(f"{os.path.getsize(path(name)) / 1024:8.1f} KB  {name}")
