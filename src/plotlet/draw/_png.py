"""Minimal PNG encoder — RGB only, stdlib-only.

Used by the raster fallbacks (`imshow`, large heatmaps) to embed images
as a single base64 data URI rather than thousands of `<rect>` elements.
Hand-rolled to avoid a Pillow dep.

The zlib stream is hand-assembled from *stored* (uncompressed) deflate
blocks rather than `zlib.compress`: compressed output is not pinned by
the DEFLATE spec and differs between zlib and zlib-ng (the system zlib
on some distros), which would break byte-identical SVG across machines.
Stored blocks have exactly one encoding. The buffers are cell-count
sized (one pixel per heatmap cell), so forgoing compression costs
little.
"""
from __future__ import annotations

import base64
import struct
import zlib


def encode_rgb(pixels: bytes, width: int, height: int) -> bytes:
    """Encode a packed RGB buffer (`width*height*3` bytes, row-major, top-down).

    Returns the complete PNG file as bytes. Color type 2 (RGB), 8-bit channels,
    no interlacing, all scanlines use filter type 0 (None) — leaves compression
    entirely to zlib.
    """
    expected = width * height * 3
    if len(pixels) != expected:
        raise ValueError(f"pixel buffer is {len(pixels)} bytes, expected {expected}")

    def _chunk(typ: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        raw.extend(pixels[y * stride : (y + 1) * stride])

    return (sig + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", _zlib_stored(bytes(raw)))
            + _chunk(b"IEND", b""))


def _zlib_stored(data: bytes) -> bytes:
    """A zlib stream of stored (BTYPE=00) deflate blocks — one canonical
    encoding, no compressor freedom. 0x78 0x01: CMF = deflate/32K window,
    FLG chosen so (CMF·256 + FLG) % 31 == 0."""
    out = bytearray(b"\x78\x01")
    n = len(data)
    for i in range(0, n or 1, 65535):
        block = data[i:i + 65535]
        final = 1 if i + 65535 >= n else 0
        out.append(final)
        out += struct.pack("<HH", len(block), len(block) ^ 0xFFFF)
        out += block
    out += struct.pack(">I", zlib.adler32(data) & 0xFFFFFFFF)
    return bytes(out)


def image_png(x, y, w, h, pixels, width, height):
    """One `<image>` element with a packed RGB buffer embedded as a
    base64 PNG data URI — the shared raster-fallback emission. `pixels`
    is `width*height*3` bytes, row-major top-down; `x`/`y`/`w`/`h` is the
    pixel bbox the image stretches across (`preserveAspectRatio="none"`,
    nearest-neighbour scaling so cells stay crisp)."""
    png = encode_rgb(bytes(pixels), width, height)
    b64 = base64.b64encode(png).decode("ascii")
    return (f'<image x="{x:.3f}" y="{y:.3f}" '
            f'width="{w:.3f}" height="{h:.3f}" '
            f'preserveAspectRatio="none" image-rendering="pixelated" '
            f'href="data:image/png;base64,{b64}"/>')
