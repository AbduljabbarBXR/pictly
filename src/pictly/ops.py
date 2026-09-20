"""Pictly operations: resize, crop, trim, normalize, shape, effects, enhance,
compress, convert, responsive sets, palette, placeholder, pipeline.

Native PNG engine for exact pixel work; ffmpeg for other formats and filters.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from . import ffmpeg as ff
from . import png as P

TMPDIR = Path(tempfile.gettempdir()) / "pictly"
TMPDIR.mkdir(exist_ok=True)


def _tmp(suffix=".png") -> Path:
    f = tempfile.NamedTemporaryFile(prefix="pictly-", suffix=suffix, dir=TMPDIR, delete=False)
    f.close()
    return Path(f.name)


def _hex(color: str) -> str:
    c = (color or "#000000").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return "#" + c


def _result(path) -> dict:
    p = Path(path)
    out = {"file": str(p), "bytes": p.stat().st_size if p.exists() else 0}
    try:
        out.update({k: v for k, v in ff.probe(p).items() if k in ("width", "height", "format", "has_alpha")})
        if out.get("width") and out.get("height"):
            out["aspect"] = round(out["height"] / out["width"], 4)
    except Exception:
        pass
    return out


# ------------------------------- inspect -------------------------------

def inspect(path: str) -> dict:
    info = ff.probe(path)
    if info.get("width") and info.get("height"):
        info["aspect"] = round(info["height"] / info["width"], 4)
        info["megapixels"] = round(info["width"] * info["height"] / 1e6, 2)
    info["caps"] = {k: v for k, v in ff.caps().items() if k in ("ffmpeg", "ffprobe")}
    return info


# ------------------------------- resize / crop -------------------------------

def resize(src, out, width=None, height=None, fit="contain", background="#ffffff",
           format=None, quality=None, allow_upscale=True) -> dict:
    info = ff.probe(src)
    sw, sh = info.get("width"), info.get("height")
    if not sw:
        raise RuntimeError("cannot read image dimensions")
    if fit not in ("contain", "exact", "cover", "stretch"):
        raise ValueError("fit must be contain, exact, cover or stretch")
    if fit == "stretch":
        if not (width and height):
            raise ValueError("stretch needs width and height")
        vf = f"scale={int(width)}:{int(height)}:flags=lanczos"
    elif fit in ("contain", "exact"):
        w = int(width) if width else -1
        h = int(height) if height else -1
        flags = "decrease" if allow_upscale else "decrease"
        vf = f"scale={w}:{h}:force_original_aspect_ratio={flags}:flags=lanczos"
        if fit == "exact":
            vf += f",pad={int(width)}:{int(height)}:(ow-iw)/2:(oh-ih)/2:color={_hex(background)}"
    else:  # cover
        w = int(width) if width else sw
        h = int(height) if height else sh
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h}"
    fmt = (format or Path(out).suffix.lstrip(".") or "png")
    ff.run(["-i", str(src), "-vf", vf, *ff.out_args(fmt, quality), str(out)])
    return _result(out)


def crop(src, out, x, y, width, height, format=None, quality=None) -> dict:
    fmt = format or Path(out).suffix.lstrip(".") or "png"
    ff.run(["-i", str(src), "-vf", f"crop={int(width)}:{int(height)}:{int(x)}:{int(y)}",
            *ff.out_args(fmt, quality), str(out)])
    return _result(out)


# ------------------------------- trim / normalize -------------------------------

def _to_rgba(src) -> tuple[Path, int, int, bytearray]:
    tmp = _tmp(".png")
    ff.to_rgba_png(src, tmp)
    w, h, px, _ = P.read_png(tmp)
    return tmp, w, h, px


def trim(src, out=None, threshold=12, trim_white=True, padding=0, format=None, quality=None) -> dict:
    tmp, w, h, px = _to_rgba(src)
    x0, y0, x1, y1 = P.trim_box(w, h, px, threshold=threshold, white=trim_white)
    cw, ch = x1 - x0, y1 - y0
    if padding:
        x0 = max(0, x0 - padding); y0 = max(0, y0 - padding)
        cw = min(w - x0, cw + 2 * padding); ch = min(h - y0, ch + 2 * padding)
    out = Path(out or (Path(src).with_name(Path(src).stem + "-trimmed.png")))
    fmt = format or out.suffix.lstrip(".") or "png"
    if fmt == "png":
        P.write_png(out, cw, ch, P.crop_rgba(px, w, h, x0, y0, cw, ch))
    else:
        cropped = _tmp(".png")
        P.write_png(cropped, cw, ch, P.crop_rgba(px, w, h, x0, y0, cw, ch))
        ff.run(["-i", str(cropped), *ff.out_args(fmt, quality), str(out)])
    tmp.unlink(missing_ok=True)
    r = _result(out)
    r["trimmed_from"] = {"width": w, "height": h, "box": [x0, y0, cw, ch]}
    return r


def normalize(src, out=None, canvas_width=800, canvas_height=1240, margin=40,
              background="transparent", format=None, quality=None, threshold=12,
              trim_white=True) -> dict:
    """Trim borders, then fit onto a uniform canvas with equal margins."""
    tmp, w, h, px = _to_rgba(src)
    x0, y0, x1, y1 = P.trim_box(w, h, px, threshold=threshold, white=trim_white)
    cw, ch = x1 - x0, y1 - y0
    maxw, maxh = canvas_width - 2 * margin, canvas_height - 2 * margin
    scale = min(maxw / cw, maxh / ch)
    nw, nh = max(1, round(cw * scale)), max(1, round(ch * scale))
    small = P.resize_rgba(P.crop_rgba(px, w, h, x0, y0, cw, ch), cw, ch, nw, nh)
    bg = (0, 0, 0, 0) if background in ("transparent", None) else _rgba(background)
    canvas = P.place_on_canvas(small, nw, nh, canvas_width, canvas_height,
                               (canvas_width - nw) // 2, (canvas_height - nh) // 2, bg)
    staged = _tmp(".png")
    P.write_png(staged, canvas_width, canvas_height, canvas)
    out = Path(out or (Path(src).with_name(Path(src).stem + "-normalized.png")))
    fmt = format or out.suffix.lstrip(".") or "png"
    if fmt == "png":
        Path(out).write_bytes(staged.read_bytes())
    else:
        ff.run(["-i", str(staged), *ff.out_args(fmt, quality), str(out)])
    tmp.unlink(missing_ok=True)
    r = _result(out)
    r["placed"] = {"width": nw, "height": nh, "canvas": [canvas_width, canvas_height], "margin": margin}
    return r


def _rgba(color: str):
    c = _hex(color).lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), 255)


# ------------------------------- shape -------------------------------

def shape(src, out, kind="rounded", radius=24, width=None, height=None,
          background=None, format=None, quality=None) -> dict:
    info = ff.probe(src)
    tw, th = int(width or info["width"]), int(height or info["height"])
    staged = _tmp(".png")
    vf = f"scale={tw}:{th}:force_original_aspect_ratio=decrease:flags=lanczos,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:color=#00000000,format=rgba"
    ff.run(["-i", str(src), "-vf", vf, str(staged)])
    mask = _tmp(".png")
    P.write_mask(mask, tw, th, "circle" if kind == "circle" else ("arch" if kind == "arch" else "rounded"), radius=int(radius))
    fmt = format or Path(out).suffix.lstrip(".") or "png"
    if background:
        args = ["-i", str(staged), "-i", str(mask),
                "-f", "lavfi", "-i", f"color=c={_hex(background)}:s={tw}x{th}",
                "-filter_complex", "[1]format=gray[m];[0][m]alphamerge[fg];[2][fg]overlay=format=auto",
                *ff.out_args(fmt, quality), str(out)]
    else:
        args = ["-i", str(staged), "-i", str(mask),
                "-filter_complex", "[1]format=gray[m];[0][m]alphamerge",
                *ff.out_args(fmt, quality), str(out)]
    ff.run(args)
    staged.unlink(missing_ok=True); mask.unlink(missing_ok=True)
    r = _result(out)
    r["shape"] = kind
    return r


# ------------------------------- effects / enhance -------------------------------

def effects(src, out, brightness=0.0, contrast=1.0, saturation=1.0, gamma=1.0,
            blur=0.0, sharpen=0.0, denoise=False, grayscale=False, sepia=False,
            vignette=False, rotate=0, flip=None, deband=0.0, grain=0.0,
            format=None, quality=None) -> dict:
    chain = []
    if deband:
        t = max(0.001, float(deband))
        chain.append(f"deband=1thr={t}:2thr={t}:3thr={t}:4thr={t}:range=16")
    if grain:
        chain.append(f"noise=alls={max(0, int(grain))}:allf=u")
    if any([brightness, contrast != 1.0, saturation != 1.0, gamma != 1.0]):
        chain.append(f"eq=brightness={brightness}:contrast={contrast}:saturation={saturation}:gamma={gamma}")
    if denoise:
        chain.append("hqdn3d=4:3:6:4.5")
    if blur:
        chain.append(f"gblur=sigma={blur}")
    if sharpen:
        chain.append(f"unsharp=5:5:{sharpen}:5:5:0")
    if grayscale:
        chain.append("hue=s=0")
    if sepia:
        chain.append("colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131")
    if vignette:
        chain.append("vignette")
    if rotate == 90:
        chain.append("transpose=1")
    elif rotate == 180:
        chain.append("transpose=1,transpose=1")
    elif rotate == 270:
        chain.append("transpose=2")
    if flip == "horizontal":
        chain.append("hflip")
    elif flip == "vertical":
        chain.append("vflip")
    if not chain:
        raise ValueError("no effect parameters given")
    fmt = format or Path(out).suffix.lstrip(".") or "png"
    ff.run(["-i", str(src), "-vf", ",".join(chain), *ff.out_args(fmt, quality), str(out)])
    r = _result(out)
    r["effects"] = chain
    return r


PRESETS = {
    "product": dict(contrast=1.06, saturation=1.12, sharpen=0.7, denoise=True),
    "photo": dict(contrast=1.04, saturation=1.05, gamma=1.02, sharpen=0.5, denoise=True),
    "clarity": dict(contrast=1.05, sharpen=1.1),
    "soft": dict(contrast=1.02, saturation=1.04, blur=0.6),
    "document": dict(contrast=1.15, saturation=0.9, sharpen=0.4),
    "bw": dict(contrast=1.08, sharpen=0.5, grayscale=True),
}

# ------------------------------- quality suite -------------------------------

_SCALES = {"lanczos": "lanczos", "bicubic": "bicubic", "neighbor": "neighbor", "bilinear": "bilinear"}


def upscale(src, out, factor=None, width=None, height=None, method="lanczos",
            sharpen=True, sharpen_strength=0.55, format=None, quality=None) -> dict:
    """High quality upscale. Two-step scaling plus contrast-adaptive sharpening
    for factors of 3x and above. method=xbr is for pixel art."""
    info = ff.probe(src)
    sw, sh = info["width"], info["height"]
    if not (factor or width or height):
        raise ValueError("give factor (e.g. 2) or width/height")
    f = float(factor) if factor else max((width or 0) / sw, (height or 0) / sh)
    f = max(1.0, f)
    tw, th = int(width or round(sw * f)), int(height or round(sh * f))
    tw -= tw % 2
    th -= th % 2
    chain: list[str] = []
    if method == "xbr":
        n = 4 if f >= 4 else (3 if f >= 3 else 2)
        chain.append(f"xbr=n={n}")
        chain.append(f"scale={tw}:{th}:flags=neighbor")
    elif f >= 3:
        mid_w, mid_h = int(round(sw * (f ** 0.5))), int(round(sh * (f ** 0.5)))
        mid_w -= mid_w % 2; mid_h -= mid_h % 2
        chain.append(f"scale={mid_w}:{mid_h}:flags={_SCALES.get(method, 'lanczos')}")
        chain.append("unsharp=5:5:0.4:5:5:0")
        chain.append(f"scale={tw}:{th}:flags={_SCALES.get(method, 'lanczos')}")
    else:
        chain.append(f"scale={tw}:{th}:flags={_SCALES.get(method, 'lanczos')}")
    if sharpen:
        chain.append(f"cas=strength={float(sharpen_strength):.2f}")
    fmt = format or Path(out).suffix.lstrip(".") or "png"
    ff.run(["-i", str(src), "-vf", ",".join(chain), *ff.out_args(fmt, quality), str(out)])
    r = _result(out)
    r.update({"upscaled_from": [sw, sh], "factor": round(f, 2), "method": method, "chain": chain})
    return r


def denoise(src, out, method="hqdn3d", strength=1.0, format=None, quality=None) -> dict:
    """Denoise: hqdn3d (fast), nlmeans (best for photos), atadenoise (temporal-lite)."""
    s = max(0.1, float(strength))
    if method == "hqdn3d":
        filt = f"hqdn3d={3*s:.1f}:{2*s:.1f}:{4.5*s:.1f}:{3.5*s:.1f}"
    elif method == "nlmeans":
        filt = f"nlmeans=s={2.5*s:.1f}:p=5:r=12"
    elif method == "atadenoise":
        filt = f"atadenoise=0a={0.02*s:.3f}:0b={0.04*s:.3f}"
    else:
        raise ValueError("method must be hqdn3d, nlmeans or atadenoise")
    fmt = format or Path(out).suffix.lstrip(".") or "png"
    ff.run(["-i", str(src), "-vf", filt, *ff.out_args(fmt, quality), str(out)])
    r = _result(out)
    r.update({"method": method, "strength": strength})
    return r


def sharpen(src, out, method="cas", strength="standard", amount=None, format=None, quality=None) -> dict:
    """Sharpening: cas (contrast adaptive, no halos) or unsharp (classic)."""
    levels = {"subtle": 0.4, "standard": 0.7, "strong": 1.1}
    if amount is None:
        amount = levels.get(strength, 0.7)
    if method == "cas":
        filt = f"cas=strength={min(1.0, amount):.2f}"
    elif method == "unsharp":
        filt = f"unsharp=5:5:{amount:.2f}:5:5:0"
    else:
        raise ValueError("method must be cas or unsharp")
    fmt = format or Path(out).suffix.lstrip(".") or "png"
    ff.run(["-i", str(src), "-vf", filt, *ff.out_args(fmt, quality), str(out)])
    r = _result(out)
    r.update({"method": method, "amount": amount})
    return r


QUALITY_PRESETS = {
    "web": ["normalize=independence=0", "vibrance=intensity=0.10", "cas=strength=0.45"],
    "product": ["normalize=independence=0", "hqdn3d=2:1.5:3:2.5", "vibrance=intensity=0.16", "cas=strength=0.65"],
    "photo": ["normalize=independence=0", "grayworld", "nlmeans=s=2.2:p=5:r=12", "vibrance=intensity=0.12", "cas=strength=0.5"],
    "art": ["normalize=independence=0", "deband=1thr=0.02:2thr=0.02:3thr=0.02:4thr=0.02:range=16", "vibrance=intensity=0.2", "cas=strength=0.8"],
    "max": ["normalize=independence=0", "grayworld", "nlmeans=s=3:p=7:r=15",
            "deband=1thr=0.02:2thr=0.02:3thr=0.02:4thr=0.02:range=16",
            "vibrance=intensity=0.18", "cas=strength=1.0", "unsharp=5:5:0.35:5:5:0"],
}


def auto_quality(src, out, preset="product", grain=0.0, format=None, quality=None) -> dict:
    """Automatic quality pass: auto levels, white balance, denoise, vibrance,
    contrast-adaptive sharpening. Presets: web, product, photo, art, max."""
    if preset not in QUALITY_PRESETS:
        raise ValueError(f"preset must be one of: {', '.join(QUALITY_PRESETS)}")
    chain = list(QUALITY_PRESETS[preset])
    if grain:
        chain.append(f"noise=alls={max(0, int(grain))}:allf=u")
    fmt = format or Path(out).suffix.lstrip(".") or "png"
    ff.run(["-i", str(src), "-vf", ",".join(chain), *ff.out_args(fmt, quality), str(out)])
    r = _result(out)
    r.update({"preset": preset, "chain": chain})
    return r


def deband(src, out, strength=0.02, format=None, quality=None) -> dict:
    t = max(0.001, float(strength))
    fmt = format or Path(out).suffix.lstrip(".") or "png"
    ff.run(["-i", str(src), "-vf",
            f"deband=1thr={t}:2thr={t}:3thr={t}:4thr={t}:range=16",
            *ff.out_args(fmt, quality), str(out)])
    r = _result(out)
    r["strength"] = strength
    return r


def enhance(src, out, preset="product", format=None, quality=None) -> dict:
    if preset not in PRESETS:
        raise ValueError(f"preset must be one of: {', '.join(PRESETS)}")
    r = effects(src, out, format=format, quality=quality, **PRESETS[preset])
    r["preset"] = preset
    return r


# ------------------------------- convert / compress -------------------------------

def convert(src, out, format, quality=None, strip_metadata=True) -> dict:
    fmt = format.lower().lstrip(".")
    ff.run(["-i", str(src), *ff.out_args(fmt, quality, strip=strip_metadata), str(out)])
    r = _result(out)
    r["converted_to"] = fmt
    return r


def compress(src, out, quality=80, format=None) -> dict:
    fmt = (format or Path(out).suffix.lstrip(".") or "webp").lower()
    before = Path(src).stat().st_size
    convert(src, out, fmt, quality=quality)
    r = _result(out)
    r.update({"quality": quality, "input_bytes": before,
              "saved_percent": round((1 - r["bytes"] / before) * 100, 1) if before else None})
    return r


# ------------------------------- responsive / palette / placeholder -------------------------------

def responsive(src, out_dir, widths=(320, 480, 640, 960, 1280), format="webp",
               quality=80, manifest=True) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(src).stem
    info = ff.probe(src)
    made = []
    for w in widths:
        w = int(w)
        if w > info["width"]:
            continue
        target = out_dir / f"{stem}-{w}.{format}"
        resize(src, target, width=w, fit="contain", format=format, quality=quality, allow_upscale=False)
        made.append({"width": w, **{k: v for k, v in _result(target).items() if k in ("file", "bytes", "height")}})
    result = {"file": str(out_dir), "variants": made, "format": format, "quality": quality}
    if manifest and made:
        mpath = out_dir / f"{stem}-manifest.json"
        mpath.write_text(json.dumps(result, indent=2))
        result["manifest"] = str(mpath)
    return result


def palette(src, colors=6) -> dict:
    """Dominant colors as hex. Alpha flattened onto white; colors grouped in 16 steps."""
    tmp = _tmp(".png")
    ff.to_rgba_png(src, tmp)
    w, h, px, _ = P.read_png(tmp)
    counts: dict[tuple, int] = {}
    total = w * h
    step = max(1, total // 40000)
    for i in range(0, total, step):
        o = i * 4
        a = px[o + 3] / 255.0
        r = int(px[o] * a + 255 * (1 - a))
        g = int(px[o + 1] * a + 255 * (1 - a))
        b = int(px[o + 2] * a + 255 * (1 - a))
        key = (r // 16 * 16, g // 16 * 16, b // 16 * 16)
        counts[key] = counts.get(key, 0) + 1
    top = sorted(counts.items(), key=lambda kv: -kv[1])[: int(colors)]
    hexes = ["#%02x%02x%02x" % k for k, _ in top]
    shares = [round(v / sum(counts.values()) * 100, 1) for _, v in top]
    tmp.unlink(missing_ok=True)
    return {"file": str(src), "colors": hexes, "shares_percent": shares, "count": len(hexes)}


def placeholder(out, width=800, height=600, color="#3366cc", color2=None,
                label=None, format=None, quality=None) -> dict:
    fmt = format or Path(out).suffix.lstrip(".") or "png"
    w, h = int(width), int(height)
    if color2:
        # native vertical gradient, then convert if needed
        c1, c2 = _rgba(color), _rgba(color2)
        px = bytearray(w * h * 4)
        for y in range(h):
            t = y / max(1, h - 1)
            r = int(c1[0] + (c2[0] - c1[0]) * t)
            g = int(c1[1] + (c2[1] - c1[1]) * t)
            b = int(c1[2] + (c2[2] - c1[2]) * t)
            row = bytes((r, g, b, 255)) * w
            px[y * w * 4:(y + 1) * w * 4] = row
        staged = _tmp(".png")
        P.write_png(staged, w, h, px)
        if fmt == "png":
            Path(out).write_bytes(staged.read_bytes())
        else:
            ff.run(["-i", str(staged), *ff.out_args(fmt, quality), str(out)])
        staged.unlink(missing_ok=True)
    else:
        ff.run(["-f", "lavfi", "-i", f"color=c={_hex(color)}:s={w}x{h}",
                *ff.out_args(fmt, quality), str(out)])
    r = _result(out)
    if label:
        r["note"] = "label skipped (drawtext avoided for font portability)"
    return r


# ------------------------------- pipeline -------------------------------

OPS = {
    "resize": resize, "crop": crop, "trim": trim, "normalize": normalize,
    "shape": shape, "effects": effects, "enhance": enhance, "convert": convert,
    "compress": compress, "palette": palette, "placeholder": placeholder,
    "upscale": upscale, "denoise": denoise, "sharpen": sharpen,
    "auto_quality": auto_quality, "deband": deband,
}


def pipeline(src, out, steps: list[dict]) -> dict:
    if not steps:
        raise ValueError("pipeline needs at least one step")
    current = Path(src)
    applied = []
    for i, step in enumerate(steps):
        name = step.get("op")
        if name not in OPS or name in ("palette", "placeholder"):
            raise ValueError(f"step {i}: unsupported pipeline op '{name}'")
        args = {k: v for k, v in step.items() if k != "op"}
        last = i == len(steps) - 1
        target = Path(out) if last else _tmp(Path(out).suffix or ".png")
        r = OPS[name](str(current), str(target), **args)
        applied.append({"op": name, **{k: r.get(k) for k in ("width", "height", "bytes") if r.get(k)}})
        if current != Path(src) and current.exists():
            current.unlink(missing_ok=True)
        current = target
    r = _result(out)
    r["steps"] = applied
    return r
