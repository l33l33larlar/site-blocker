"""Draws the extension icons: a red "no entry" disc with a white bar."""
import os
import struct
import sys
import zlib

RED = (196, 43, 34)
WHITE = (255, 255, 255)
SS = 8  # supersampling per axis


def pixel(x, y, size):
    """Colour and coverage of one sub-sample; coordinates in 0..1."""
    cx = cy = 0.5
    dx, dy = x - cx, y - cy
    if dx * dx + dy * dy > 0.47 * 0.47:
        return None
    if abs(dy) <= 0.085 and abs(dx) <= 0.29:
        return WHITE
    return RED


def render(size):
    rows = []
    for py in range(size):
        row = bytearray([0])  # PNG filter type 0
        for px in range(size):
            r = g = b = a = 0
            for sy in range(SS):
                for sx in range(SS):
                    c = pixel((px + (sx + 0.5) / SS) / size, (py + (sy + 0.5) / SS) / size, size)
                    if c:
                        r += c[0]
                        g += c[1]
                        b += c[2]
                        a += 1
            if a:
                row += bytes([r // a, g // a, b // a, round(255 * a / (SS * SS))])
            else:
                row += bytes([0, 0, 0, 0])
        rows.append(bytes(row))
    return b"".join(rows)


def chunk(kind, data):
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def write_png(path, size):
    raw = render(size)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


if __name__ == "__main__":
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for s in (16, 32, 48, 128):
        write_png(os.path.join(out, "icon%d.png" % s), s)
        print("wrote icon%d.png" % s)
