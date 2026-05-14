"""Minimal PNG encoder — RGB only, stdlib zlib.

Used by `imshow` to embed large images as a single base64 data URI rather
than thousands of `<rect>` elements. Hand-rolled to avoid a Pillow dep.
"""
from __future__ import annotations

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
            + _chunk(b"IDAT", zlib.compress(bytes(raw)))
            + _chunk(b"IEND", b""))
