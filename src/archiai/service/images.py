"""Getting a picture from a caller into a grid the tracer can read.

PNG is decoded here with nothing but the standard library, so the service has
no image dependency it cannot guarantee. If Pillow happens to be installed the
other formats a phone produces -- JPEG, HEIC via a plugin, WebP -- go through
it instead. Callers who have neither get told exactly what to send.
"""

import base64
import binascii
import io

from ..engine import trace as T


MAX_BYTES = 12 * 1024 * 1024
MAGIC = {
    b"\x89PNG\r\n\x1a\n": "png",
    b"\xff\xd8\xff": "jpeg",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"RIFF": "webp",
    b"BM": "bmp",
}


def decode_payload(data_or_url):
    """Base64, with or without a data: URL wrapper, to raw bytes."""
    s = (data_or_url or "").strip()
    if s.startswith("data:"):
        head, _, s = s.partition(",")
        if "base64" not in head:
            raise ValueError("data URL must be base64 encoded")
    s = "".join(s.split())
    try:
        raw = base64.b64decode(s, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("image is not valid base64")
    if not raw:
        raise ValueError("image payload is empty")
    if len(raw) > MAX_BYTES:
        raise ValueError("image is larger than %d MB" % (MAX_BYTES // (1024 * 1024)))
    return raw


def sniff(raw):
    for magic, name in MAGIC.items():
        if raw.startswith(magic):
            return name
    return "unknown"


def to_grid(raw):
    """(width, height, rows of luminance) from whatever arrived."""
    kind = sniff(raw)
    if kind == "png":
        return T.read_png(raw)
    try:
        from PIL import Image                       # optional
    except ImportError:
        raise ValueError(
            "this build reads PNG without extra libraries; send a PNG, or "
            "install Pillow on the server to accept %s" % kind)
    # Pillow raises its own family of errors on a truncated or hostile file,
    # and none of them are ValueError, so they would escape as a 500 rather
    # than as a sentence telling the caller what was wrong with their upload.
    try:
        with Image.open(io.BytesIO(raw)) as im:
            w, h = im.size
            if w * h > 40_000_000:
                raise ValueError("image is too large to trace")
            px = list(im.convert("L").getdata())
    except ValueError:
        raise
    except Exception as e:
        raise ValueError("could not read this %s: %s. A PNG always works."
                         % (kind if kind != "unknown" else "image", e))
    if len(px) < w * h:
        raise ValueError("this image is truncated; send it again")
    rows = [[px[r * w + c] / 255.0 for c in range(w)] for r in range(h)]
    return w, h, rows


def footprint_from_upload(payload, area_m2=None, width_m=None,
                          simplify=0.010, straighten=22.0):
    raw = decode_payload(payload)
    w, h, rows = to_grid(raw)
    return T.footprint(rows, w, h, area_m2=area_m2, width_m=width_m,
                       simplify=simplify, straighten=straighten)
