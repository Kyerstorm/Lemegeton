"""Image work for Lunar Roles: role icons, the emoji check and the avatar palette.

Everything here is synchronous and CPU-bound; callers run it with asyncio.to_thread.
"""
from __future__ import annotations

import io
import math
import unicodedata
import warnings
from collections import OrderedDict
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageOps

import config

MAX_ICON_BYTES = 256 * 1024     # Discord's limit for the final role icon
MAX_ICON_SIDE = 8192            # refuse anything wider/taller before decoding pixels
MAX_ICON_PIXELS = 16_000_000    # ...or with more pixels than this (decompression bombs; ~64 MB decoded)
ICON_SIZES = (256, 128, 64)     # final icon: the largest of these that fits under MAX_ICON_BYTES
ICON_SIZE = ICON_SIZES[-1]      # Discord's documented minimum role-icon size
MIN_CROP = 16                   # smallest square (in the original's pixels) that can be cut out

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"

PHOTO_HINT = "Try a 12 MP photo or a screenshot."
HEIC_MESSAGE = "iPhone HEIC photos aren't supported. Save it as JPEG or PNG (or take a screenshot) and try again."
TYPE_MESSAGE = "Only PNG or JPEG images work as role icons (checked by the file's content, not its name)."
_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"hevm", b"hevs", b"mif1", b"msf1"}
HEIF_CONTENT_TYPES = {"image/heic", "image/heif", "image/heic-sequence", "image/heif-sequence"}


class ImageError(Exception):
    """A user-facing reason an image or emoji can't be used."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# ------------------------------------------------------
# Role icons
# ------------------------------------------------------

def source_max_bytes() -> int:
    """Largest original image accepted (LUNAR_ICON_SOURCE_MAX_BYTES)."""
    return config.LUNAR_ICON_SOURCE_MAX_BYTES


def format_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB".replace(".0 MB", " MB")
    return f"{max(1, size // 1024)} KB"


def check_declared_size(size: int) -> None:
    """Refuse before downloading, using the size reported for the file."""
    limit = source_max_bytes()
    if size > limit:
        raise ImageError(f"That image is {format_size(size)}. Images can be at most {format_size(limit)}.")


_ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg"}


def check_attachment_metadata(content_type: Optional[str], animated: bool) -> None:
    """Extra refusals from what Discord reports about an upload (never a reason to accept).

    Discord may re-process uploads (an animated PNG can arrive as a still frame, a GIF
    named .png as a real PNG), so its flags and detected type are checked as well as
    the downloaded content.
    """
    if animated:
        raise ImageError("Animated images can't be role icons. Use a still PNG or JPEG.")
    kind = (content_type or "").split(";")[0].strip().lower()
    if kind in HEIF_CONTENT_TYPES:
        raise ImageError(HEIC_MESSAGE)
    if kind.startswith("image/") and kind not in _ALLOWED_CONTENT_TYPES:
        raise ImageError(TYPE_MESSAGE)


def sniff_type(data: bytes) -> Optional[str]:
    """Image type from the file's first bytes (never from its name)."""
    if data.startswith(PNG_SIGNATURE):
        return "PNG"
    if data.startswith(JPEG_SIGNATURE):
        return "JPEG"
    return None


def is_heif(data: bytes) -> bool:
    """True for HEIC/HEIF files (iPhone photos), recognised by their "ftyp" box, not their name.
    AVIF uses the same container and isn't counted."""
    if len(data) < 12 or data[4:8] != b"ftyp":
        return False
    box_end = min(max(int.from_bytes(data[:4], "big"), 16), 256, len(data))
    brands = {data[8:12]} | {data[i:i + 4] for i in range(16, box_end - 3, 4)}  # major + compatible brands
    return not brands & {b"avif", b"avis"} and bool(brands & _HEIF_BRANDS)


def pixel_limit_error(width: int, height: int) -> Optional[str]:
    """The refusal for an image too large in pixels (sizes as displayed), naming the limit hit; None if it's fine."""
    over_total = width * height > MAX_ICON_PIXELS
    if width > MAX_ICON_SIDE and height > MAX_ICON_SIDE:
        message = f"This image is {width}x{height} px; the limit is {MAX_ICON_SIDE} px per side."
    elif height > MAX_ICON_SIDE:
        message = f"This image is {height} px tall; the limit is {MAX_ICON_SIDE} px per side."
    elif width > MAX_ICON_SIDE:
        message = f"This image is {width} px wide; the limit is {MAX_ICON_SIDE} px per side."
    elif over_total:
        millions = math.ceil(width * height / 100_000) / 10  # rounded up, so it never reads as "16.0"
        message = (f"This image is {width}x{height} px ({millions:g} million pixels); "
                   f"the limit is {MAX_ICON_PIXELS // 1_000_000} million pixels.")
    else:
        return None
    return f"{message} {PHOTO_HINT}" if over_total else message


def _open_checked(data: bytes) -> Tuple[Image.Image, str]:
    """Open and fully decode an original image after every safety check. Returns (image, "PNG"|"JPEG")."""
    check_declared_size(len(data))
    kind = sniff_type(data)
    if kind is None:
        raise ImageError(HEIC_MESSAGE if is_heif(data) else TYPE_MESSAGE)

    with warnings.catch_warnings():
        # Opening reads the header only, so Pillow's own bomb warning is ignored here: our pixel
        # check below refuses with the real size. Pillow still refuses absurd sizes outright.
        warnings.simplefilter("ignore", Image.DecompressionBombWarning)
        try:
            image = Image.open(io.BytesIO(data))
        except Image.DecompressionBombError:
            raise ImageError(_too_many_pixels())
        except (OSError, ValueError, SyntaxError):
            raise ImageError("I couldn't read that image. It may be damaged.")

        # Phone cameras often save "MPO" (a JPEG with extra frames); its first frame is a normal JPEG.
        detected = "JPEG" if image.format == "MPO" else image.format
        if detected != kind:
            raise ImageError("That file's content doesn't match a normal PNG or JPEG image.")
        width, height = _displayed_size(image)
        error = pixel_limit_error(width, height)
        if error:
            raise ImageError(error)
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        if kind == "PNG" and (getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) > 1):
            raise ImageError("Animated images can't be role icons. Use a still PNG or JPEG.")
        try:
            image.load()
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise ImageError(_too_many_pixels())
        except (OSError, ValueError, SyntaxError):
            raise ImageError("I couldn't read that image. It may be damaged or cut off.")
    return image, kind


def inspect_source(data: bytes) -> Tuple[str, int, int]:
    """Check an original image without making an icon. Returns (kind, width, height) as displayed
    (phone photos turned the right way up, matching what browsers show)."""
    image, kind = _open_checked(data)
    return (kind, *_displayed_size(image))


def _displayed_size(image: Image.Image) -> Tuple[int, int]:
    """(width, height) as shown, with a phone photo's EXIF rotation applied (read from the header)."""
    width, height = image.size
    try:
        turned = image.getexif().get(0x0112) in (5, 6, 7, 8)  # EXIF orientation: rotated a quarter turn
    except Exception:
        turned = False
    return (height, width) if turned else (width, height)


@dataclass
class Icon:
    png: bytes                       # the final icon for Discord (at most MAX_ICON_BYTES)
    side: int                        # its width and height
    crop: Tuple[int, int, int]       # (x, y, size) cut from the original, in its displayed pixels


def make_icon(data: bytes, crop: Optional[Tuple[int, int, int]] = None) -> Icon:
    """Validate an original PNG/JPEG and cut a square icon from it.

    crop is (x, y, size) in the original's pixels (after EXIF rotation); None = the centre square.
    The result is the largest of ICON_SIZES (never larger than the crop, at least 64) that
    fits under Discord's 256 KB limit, resized with LANCZOS and saved as PNG.
    """
    image, _ = _open_checked(data)
    image = ImageOps.exif_transpose(image).convert("RGBA")
    width, height = image.size
    if crop is None:
        size = min(width, height)
        x, y = (width - size) // 2, (height - size) // 2
    else:
        try:
            x, y, size = (int(v) for v in crop)
        except (TypeError, ValueError):
            raise ImageError("That crop isn't valid. Try cropping again.")
        if size < MIN_CROP or x < 0 or y < 0 or x + size > width or y + size > height:
            raise ImageError("That crop doesn't fit inside the image. Try cropping again.")
    region = image.crop((x, y, x + size, y + size))

    targets = [t for t in ICON_SIZES if t <= size] or [ICON_SIZES[-1]]
    for side in targets:
        out = io.BytesIO()
        region.resize((side, side), Image.Resampling.LANCZOS).save(out, format="PNG", optimize=True)
        if out.tell() <= MAX_ICON_BYTES:
            return Icon(out.getvalue(), side, (x, y, size))
    raise ImageError("That image is still too large after resizing.")  # can't really happen at 64x64


def prepare_icon(data: bytes) -> bytes:
    """The centre-square icon for an original image (for callers that only need the PNG)."""
    return make_icon(data).png


def _too_many_pixels() -> str:
    """For images so large Pillow refuses them before their size can be read."""
    return (f"This image is far too large in pixels; the limit is {MAX_ICON_SIDE} px per side and "
            f"{MAX_ICON_PIXELS // 1_000_000} million pixels in total. {PHOTO_HINT}")


# ------------------------------------------------------
# Emoji icons
# ------------------------------------------------------

_EMOJI_JOINERS = {"‍", "️", "︎", "⃣"}


def _is_emoji_char(ch: str) -> bool:
    cp = ord(ch)
    if ch in _EMOJI_JOINERS:
        return True
    if 0x1F3FB <= cp <= 0x1F3FF or 0x1F1E6 <= cp <= 0x1F1FF or 0xE0020 <= cp <= 0xE007F:
        return True  # skin tones, flags, tag sequences
    return unicodedata.category(ch) == "So" or 0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF


def check_emoji(raw: str) -> str:
    """Accept exactly one standard Unicode emoji (custom server emojis aren't allowed by Discord)."""
    text = (raw or "").strip()
    if not text:
        raise ImageError("Send an emoji, for example 🌙.")
    if text.startswith("<") and text.endswith(">"):
        raise ImageError("Custom server emojis can't be role icons. Use a standard emoji like 🌙.")
    if text.startswith(":") and text.endswith(":") and len(text) > 2:
        raise ImageError("Pick the emoji from Discord's emoji picker so the emoji itself is sent, not its `:name:`.")
    is_keycap = len(text) in (2, 3) and text[0] in "0123456789#*" and text.endswith("⃣")
    if len(text) > 16 or not (is_keycap or all(_is_emoji_char(ch) for ch in text)):
        raise ImageError("That isn't a single standard emoji. Send just one emoji, like 🌙.")
    if not is_keycap and _emoji_units(text) != 1:
        raise ImageError("Send just one emoji, like 🌙.")
    return text


def _emoji_units(text: str) -> int:
    """How many emojis a string shows (ZWJ sequences, flags and skin tones count as one)."""
    units, after_zwj, flag_halves = 0, False, 0
    for ch in text:
        cp = ord(ch)
        if ch in ("️", "︎", "⃣") or 0x1F3FB <= cp <= 0x1F3FF or 0xE0020 <= cp <= 0xE007F:
            continue  # variation selectors, keycap, skin tones, tag characters modify the previous emoji
        if ch == "‍":
            after_zwj = True
            continue
        if 0x1F1E6 <= cp <= 0x1F1FF:  # regional indicators pair up into one flag
            flag_halves += 1
            if flag_halves % 2 == 1:
                units += 1
            continue
        if after_zwj:
            after_zwj = False
            continue
        units += 1
    return units


# ------------------------------------------------------
# Avatar palette
# ------------------------------------------------------

PALETTE_MAX = 25
_MIN_DISTANCE = 30  # colours closer than this (RGB distance) count as duplicates
_palette_cache: "OrderedDict[str, List[int]]" = OrderedDict()
_PALETTE_CACHE_SIZE = 256


def cached_palette(key: str) -> Optional[List[int]]:
    colors = _palette_cache.get(key)
    if colors is not None:
        _palette_cache.move_to_end(key)
    return colors


def remember_palette(key: str, colors: List[int]) -> None:
    _palette_cache[key] = colors
    _palette_cache.move_to_end(key)
    while len(_palette_cache) > _PALETTE_CACHE_SIZE:
        _palette_cache.popitem(last=False)


def extract_palette(data: bytes, max_colors: int = PALETTE_MAX) -> List[int]:
    """Distinct colours of an avatar (most prominent first) as 0xRRGGBB ints."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        image = Image.open(io.BytesIO(data))
        image.draft("RGB", (128, 128))
        image = image.convert("RGBA")
    image.thumbnail((96, 96))
    opaque = [px[:3] for px in image.getdata() if px[3] >= 128]
    if not opaque:
        return []
    strip = Image.new("RGB", (len(opaque), 1))
    strip.putdata(opaque)
    quantized = strip.quantize(colors=32, method=Image.Quantize.MEDIANCUT)
    raw_palette = quantized.getpalette() or []
    counts = sorted(quantized.getcolors() or [], reverse=True)  # (count, index), most common first

    kept: List[tuple] = []
    for _, index in counts:
        rgb = tuple(raw_palette[index * 3:index * 3 + 3])
        if len(rgb) < 3:
            continue
        if all(_distance(rgb, other) >= _MIN_DISTANCE for other in kept):
            kept.append(rgb)
        if len(kept) >= max_colors:
            break
    return [(r << 16) | (g << 8) | b for r, g, b in kept]


def _distance(a: tuple, b: tuple) -> float:
    # "redmean" weighting: closer to how people see colour differences than plain RGB distance
    rmean = (a[0] + b[0]) / 2
    dr, dg, db = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return ((2 + rmean / 256) * dr * dr + 4 * dg * dg + (2 + (255 - rmean) / 256) * db * db) ** 0.5


def render_swatches(colors: List[int], columns: int = 5) -> bytes:
    """A small PNG grid of the palette, each swatch labelled with its hex code."""
    cell_w, cell_h, gap = 132, 56, 6
    rows = max(1, -(-len(colors) // columns))
    width = columns * cell_w + (columns + 1) * gap
    height = rows * cell_h + (rows + 1) * gap
    canvas = Image.new("RGB", (width, height), (30, 31, 34))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.load_default(size=18)
    except TypeError:  # very old Pillow
        font = ImageFont.load_default()
    for i, value in enumerate(colors):
        r, g, b = (value >> 16) & 255, (value >> 8) & 255, value & 255
        x = gap + (i % columns) * (cell_w + gap)
        y = gap + (i // columns) * (cell_h + gap)
        draw.rounded_rectangle((x, y, x + cell_w, y + cell_h), radius=8, fill=(r, g, b))
        light = (0.299 * r + 0.587 * g + 0.114 * b) > 150
        draw.text((x + cell_w / 2, y + cell_h / 2), f"#{value:06X}", fill=(20, 20, 20) if light else (245, 245, 245),
                  font=font, anchor="mm")
    out = io.BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()
