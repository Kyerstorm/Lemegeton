"""Generate test_images/ for testing /custom-role icon by hand in Discord (not an automated test).

Usage (from the repo root): .venv/Scripts/python.exe -I tests/custom_roles/make_test_images.py test_images
File 11 is a decompression bomb: never open it in an image viewer.
"""
import io
import os
import sys

from PIL import Image, ImageDraw

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
# Files from older milestones that would now be misleading: over 256 KB has been fine since
# Milestone 8, and 5000 px wide since Milestone 9 (the limit is 8192 px a side).
for old in ("04_too_big_over_256kb.png", "10_too_wide_5000px.png"):
    if os.path.exists(os.path.join(out, old)):
        os.remove(os.path.join(out, old))


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

# A big but valid photo-like original (a few MB): accepted, cropped, sent to Discord under 256 KB
photo = Image.blend(gradient(600, 400).resize((3000, 2000)), Image.effect_noise((3000, 2000), 60).convert("RGB"), 0.35)
ImageDraw.Draw(photo).ellipse((1200, 700, 1800, 1300), fill=(250, 240, 120))
photo.save(path("12_ok_big_photo.jpg"), quality=97)

# Milestone 9: up to 8192 px a side is fine, as long as the total stays under 16 million pixels
long = gradient(800, 40).resize((8000, 400))
ImageDraw.Draw(long).ellipse((3800, 0, 4200, 400), fill=(250, 240, 120))
long.save(path("13_ok_long_8000px.png"))

# A typical 12 MP phone photo (4032x3024), saved upright with the camera's EXIF rotation
phone = Image.blend(gradient(400, 300).resize((4032, 3024)), Image.effect_noise((4032, 3024), 40).convert("RGB"), 0.2)
ImageDraw.Draw(phone).ellipse((1600, 1100, 2400, 1900), fill=(250, 240, 120))
upright = Image.Exif()
upright[0x0112] = 6
phone.save(path("17_ok_12mp_phone_photo.jpg"), quality=85, exif=upright.tobytes())

# Refused
noise = Image.frombytes("RGB", (1700, 1700), os.urandom(1700 * 1700 * 3))  # ~8.7 MB, can't compress
noise.save(path("04_too_big_over_8mb.png"))

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

Image.new("RGB", (9000, 50), (90, 90, 200)).save(path("10_too_wide_9000px.png"))

# A 48 MP photo's size (8064x6048): "This image is 8064x6048 px (48.8 million pixels)... Try a 12 MP photo"
gradient(160, 120).resize((8064, 6048)).save(path("14_too_many_pixels_48mp.jpg"), quality=60)

# Stored 9000x200 but shown upright by its EXIF rotation, so it's refused as "9000 px tall"
turned = Image.Exif()
turned[0x0112] = 6
Image.new("RGB", (9000, 200), (200, 90, 90)).save(path("15_too_tall_9000px_rotated.jpg"), exif=turned.tobytes())

# Not a real photo: just the "ftyp heic" header an iPhone HEIC file starts with, which is all the bot checks
with open(path("16_iphone_photo.heic"), "wb") as f:
    f.write(b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + os.urandom(4096))

# Decompression bomb: tiny file, 20000 x 20000 = 400 million pixels when decoded.
# Saved as .png.bin so Discord's upload dialog (and file browsers) won't try to preview it;
# the bot still detects it as a PNG from its content.
Image.new("1", (20000, 20000), 0).save(path("11_BOMB_decompression_DO_NOT_OPEN.png.bin"), format="PNG", optimize=True)

for name in sorted(os.listdir(out)):
    print(f"{os.path.getsize(path(name)) / 1024:8.1f} KB  {name}")
