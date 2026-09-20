"""Native PNG engine: decode, trim, resize, pad, write, and shape masks.

Pure stdlib. Used for exact pixel work on PNGs and for generating masks
(rounded corners, circles, arches) that ffmpeg composites onto any format.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

PNG_SIG = b"\x89PNG\r\n\x1a\n"


# ------------------------------- decode -------------------------------

def read_png(path: str | Path):
    """Return (width, height, pixels_rgba, has_alpha)."""
    data = Path(path).read_bytes()
    if data[:8] != PNG_SIG:
        raise ValueError(f"not a PNG: {path}")
    pos, idat = 8, b""
    w = h = ct = bd = interlace = None
    palette = trns = b""
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, bd, ct, _comp, _filt, interlace = struct.unpack(">IIBBBBB", chunk)
        elif typ == b"IDAT":
            idat += chunk
        elif typ == b"PLTE":
            palette = chunk
        elif typ == b"tRNS":
            trns = chunk
        elif typ == b"IEND":
            break
        pos += 12 + ln
    if bd != 8 or interlace != 0:
        raise ValueError(f"unsupported PNG (bit depth {bd}, interlace {interlace})")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    raw = zlib.decompress(idat)
    stride = w * channels
    buf = bytearray(h * stride)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        ft = raw[p]; p += 1
        row = bytearray(raw[p:p + stride]); p += stride
        if ft == 1:
            for i in range(channels, stride):
                row[i] = (row[i] + row[i - channels]) & 255
        elif ft == 2:
            for i in range(stride):
                row[i] = (row[i] + prev[i]) & 255
        elif ft == 3:
            for i in range(stride):
                a = row[i - channels] if i >= channels else 0
                row[i] = (row[i] + ((a + prev[i]) >> 1)) & 255
        elif ft == 4:
            for i in range(stride):
                a = row[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                pp = a + b - c
                pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                row[i] = (row[i] + pr) & 255
        buf[y * stride:(y + 1) * stride] = row
        prev = row
    return w, h, _to_rgba(w, h, channels, buf, ct, palette, trns), ct in (4, 6)


def _to_rgba(w, h, channels, buf, ct, palette, trns):
    px = bytearray(w * h * 4)
    if ct == 3:
        for i in range(w * h):
            idx = buf[i]
            o = i * 4
            if idx * 3 + 2 < len(palette):
                px[o] = palette[idx * 3]; px[o + 1] = palette[idx * 3 + 1]; px[o + 2] = palette[idx * 3 + 2]
            px[o + 3] = trns[idx] if idx < len(trns) else 255
        return px
    for i in range(w * h):
        o = i * 4
        if channels == 4:
            px[o:o + 4] = buf[i * 4:i * 4 + 4]
        elif channels == 3:
            px[o:o + 3] = buf[i * 3:i * 3 + 3]; px[o + 3] = 255
        elif channels == 2:
            g = buf[i * 2]; px[o] = px[o + 1] = px[o + 2] = g; px[o + 3] = buf[i * 2 + 1]
        else:
            g = buf[i]; px[o] = px[o + 1] = px[o + 2] = g; px[o + 3] = 255
    return px


# ------------------------------- write -------------------------------

def write_png(path: str | Path, w: int, h: int, px: bytes | bytearray) -> None:
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)
        raw += px[y * stride:(y + 1) * stride]
    out = PNG_SIG
    out += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    out += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    out += chunk(b"IEND", b"")
    Path(path).write_bytes(out)


# ------------------------------- geometry -------------------------------

def trim_box(w: int, h: int, px: bytearray, threshold: int = 12, white: bool = True):
    """Bounding box of non-transparent (and, optionally, non-white) pixels."""
    minx, miny, maxx, maxy = w, h, -1, -1
    for y in range(h):
        base = y * w * 4
        for x in range(w):
            o = base + x * 4
            a = px[o + 3]
            if a < threshold:
                continue
            if white and px[o] > 247 and px[o + 1] > 247 and px[o + 2] > 247 and a == 255:
                continue
            if x < minx: minx = x
            if x > maxx: maxx = x
            if y < miny: miny = y
            if y > maxy: maxy = y
    if maxx < 0:
        return 0, 0, w, h
    return minx, miny, maxx + 1, maxy + 1


def crop_rgba(px, w, h, x0, y0, cw, ch):
    out = bytearray(cw * ch * 4)
    for y in range(ch):
        src = ((y0 + y) * w + x0) * 4
        out[y * cw * 4:(y + 1) * cw * 4] = px[src:src + cw * 4]
    return out


def resize_rgba(px, w, h, nw, nh):
    out = bytearray(nw * nh * 4)
    sx, sy = w / nw, h / nh
    for y in range(nh):
        fy = min(h - 1, int(y * sy)); fy2 = min(h - 1, fy + 1); wy = y * sy - fy
        for x in range(nw):
            fx = min(w - 1, int(x * sx)); fx2 = min(w - 1, fx + 1); wx = x * sx - fx
            o = (y * nw + x) * 4
            for c in range(4):
                p00 = px[(fy * w + fx) * 4 + c]; p10 = px[(fy * w + fx2) * 4 + c]
                p01 = px[(fy2 * w + fx) * 4 + c]; p11 = px[(fy2 * w + fx2) * 4 + c]
                out[o + c] = int(p00 * (1 - wx) * (1 - wy) + p10 * wx * (1 - wy) + p01 * (1 - wx) * wy + p11 * wx * wy)
    return out


def place_on_canvas(px, w, h, cw, ch, ox, oy, bg=(0, 0, 0, 0)):
    canvas = bytearray(bytes(bg) * (cw * ch))
    for y in range(h):
        if oy + y < 0 or oy + y >= ch:
            continue
        row_src = y * w * 4
        row_dst = ((oy + y) * cw + max(0, ox)) * 4
        xs = max(0, -ox)
        n = min(w - xs, cw - max(0, ox))
        if n <= 0:
            continue
        canvas[row_dst:row_dst + n * 4] = px[row_src + xs * 4:row_src + (xs + n) * 4]
    return canvas


# ------------------------------- masks -------------------------------

def _mask_canvas(w, h):
    return bytearray(w * h * 4)


def _set(px, w, x, y, a=255):
    o = (y * w + x) * 4
    px[o] = px[o + 1] = px[o + 2] = 255
    px[o + 3] = a


def rounded_mask(w: int, h: int, radius: int) -> bytearray:
    px = _mask_canvas(w, h)
    r = max(0, min(radius, min(w, h) // 2))
    for y in range(h):
        for x in range(w):
            cx = cy = None
            if x < r and y < r: cx, cy = r, r
            elif x >= w - r and y < r: cx, cy = w - r - 1, r
            elif x < r and y >= h - r: cx, cy = r, h - r - 1
            elif x >= w - r and y >= h - r: cx, cy = w - r - 1, h - r - 1
            if cx is None:
                _set(px, w, x, y)
            else:
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    _set(px, w, x, y)
    return px


def circle_mask(w: int, h: int) -> bytearray:
    px = _mask_canvas(w, h)
    cx, cy = (w - 1) / 2, (h - 1) / 2
    rr = min(cx, cy) ** 2
    for y in range(h):
        for x in range(w):
            if (x - cx) ** 2 + (y - cy) ** 2 <= rr:
                _set(px, w, x, y)
    return px


def arch_mask(w: int, h: int, top_ratio: float = 0.55) -> bytearray:
    """Mihrab-style arch: semicircular top, square base."""
    px = _mask_canvas(w, h)
    r = w / 2
    top = r
    for y in range(h):
        for x in range(w):
            if y >= top:
                _set(px, w, x, y)
            else:
                if (x - (w - 1) / 2) ** 2 + (y - top) ** 2 <= r * r:
                    _set(px, w, x, y)
    return px


def write_mask(path, w, h, kind: str, radius: int = 0) -> None:
    if kind == "circle":
        px = circle_mask(w, h)
    elif kind == "arch":
        px = arch_mask(w, h)
    else:
        px = rounded_mask(w, h, radius)
    write_png(path, w, h, px)
