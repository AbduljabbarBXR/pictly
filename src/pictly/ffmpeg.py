"""ffmpeg adapter: probe, capability detection and command helpers.

Pictly shells out to ffmpeg for every format that is not PNG (jpeg, webp,
avif, gif) and for filters (effects, enhancement, compression).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")

_CAPS: dict | None = None

ENCODER_FOR = {
    "jpg": "mjpeg",
    "jpeg": "mjpeg",
    "png": "png",
    "webp": "libwebp",
    "avif": "libaom-av1",
    "gif": "gif",
    "bmp": "bmp",
    "tiff": "tiff",
}

FILTERS_NEEDED = ["scale", "crop", "pad", "palettegen", "unsharp", "gblur", "eq",
                  "hqdn3d", "vignette", "cropdetect", "hue", "colorchannelmixer",
                  "alphamerge", "format", "transpose"]


def caps() -> dict:
    global _CAPS
    if _CAPS is not None:
        return _CAPS
    out = {"ffmpeg": bool(FFMPEG), "ffprobe": bool(FFPROBE), "encoders": {}, "filters": {}}
    if FFMPEG:
        try:
            enc = subprocess.run([FFMPEG, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=20).stdout
            for name, key in {v: k for k, v in ENCODER_FOR.items()}.items():
                out["encoders"][key] = name in enc
            filt = subprocess.run([FFMPEG, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=20).stdout
            for f in FILTERS_NEEDED:
                out["filters"][f] = (f" {f} " in filt) or (f" {f}," in filt) or (f"\n {f} " in filt)
        except Exception:
            pass
    try:
        from . import png  # noqa: F401  (native engine always available)
        out["native_png"] = True
    except Exception:
        out["native_png"] = False
    _CAPS = out
    return out


def require_ffmpeg():
    if not FFMPEG:
        raise RuntimeError("ffmpeg not found on PATH. Install ffmpeg or use PNG-only operations.")


def run(args: list[str], timeout: int = 120) -> str:
    require_ffmpeg()
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        tail = (p.stderr or "").strip().splitlines()[-3:]
        raise RuntimeError("ffmpeg failed: " + " | ".join(tail))
    return p.stdout


def probe(path: str | Path) -> dict:
    info = {"path": str(path), "bytes": Path(path).stat().st_size if Path(path).exists() else 0}
    if not FFPROBE:
        # fall back to native PNG
        try:
            from .png import read_png
            w, h, px, alpha = read_png(path)
            info.update({"width": w, "height": h, "format": "png", "has_alpha": alpha})
            return info
        except Exception:
            raise RuntimeError("need ffprobe or a PNG file to inspect images")
    cmd = [FFPROBE, "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=width,height,pix_fmt,codec_name,has_alpha,color_space",
           "-show_entries", "format=format_name,duration,bit_rate",
           "-of", "json", str(path)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if p.returncode != 0:
        raise RuntimeError("ffprobe failed: " + (p.stderr or "").strip()[-200:])
    data = json.loads(p.stdout or "{}")
    st = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    info.update({
        "width": st.get("width"), "height": st.get("height"),
        "format": ((fmt.get("format_name") or st.get("codec_name") or "").split(",")[0]).replace("_pipe", ""),
        "pix_fmt": st.get("pix_fmt"), "has_alpha": st.get("has_alpha") or (st.get("pix_fmt") or "").endswith("a"),
        "duration": float(fmt["duration"]) if fmt.get("duration") else None,
    })
    return info


def quality_args(fmt: str, quality: int | None) -> list[str]:
    """quality is 1-100 (100 = best). Mapped per encoder."""
    if quality is None:
        return []
    q = max(1, min(100, int(quality)))
    f = fmt.lower().lstrip(".")
    if f in ("jpg", "jpeg"):
        # mjpeg qscale: 2 (best) .. 31 (worst)
        qs = round(2 + (100 - q) * 29 / 99)
        return ["-q:v", str(max(2, min(31, qs)))]
    if f == "webp":
        return ["-quality", str(q), "-compression_level", "6"]
    if f == "png":
        level = max(0, min(9, round((100 - q) / 100 * 9)))
        return ["-compression_level", str(level)]
    if f == "avif":
        crf = max(0, min(63, round((100 - q) * 63 / 100)))
        return ["-crf", str(crf), "-cpu-used", "6"]
    if f == "gif":
        return []
    return []


def out_args(fmt: str, quality: int | None = None, strip: bool = True) -> list[str]:
    f = fmt.lower().lstrip(".")
    args: list[str] = []
    if f != "gif":
        args += ["-frames:v", "1"]
    if strip:
        args += ["-map_metadata", "-1"]
    if f in ("jpg", "jpeg"):
        args += ["-f", "image2", "-pix_fmt", "yuvj420p"]
    elif f == "png":
        args += ["-f", "image2", "-pix_fmt", "rgba"]
    elif f == "webp":
        args += ["-c:v", "libwebp", "-pix_fmt", "yuva420p"]
    elif f == "avif":
        args += ["-c:v", "libaom-av1", "-pix_fmt", "yuv420p", "-still-picture", "1"]
    elif f in ("bmp", "tiff", "gif"):
        args += ["-f", "image2"]
    args += quality_args(f, quality)
    return args


def to_rgba_png(src: str | Path, dst: str | Path) -> Path:
    """Convert any image to an RGBA PNG so the native engine can measure it."""
    run(["-i", str(src), "-pix_fmt", "rgba", "-frames:v", "1", str(dst)], timeout=120)
    return Path(dst)


def cropdetect(src: str | Path, limit: int = 24) -> tuple[int, int, int, int] | None:
    """Detect solid borders (e.g. white background around a photo)."""
    p = subprocess.run(
        [FFMPEG, "-hide_banner", "-nostdin", "-i", str(src), "-vf", f"cropdetect=limit={limit}:round=2:reset=0",
         "-frames:v", "8", "-f", "null", "-"],
        capture_output=True, text=True, timeout=60)
    import re
    last = None
    for m in re.finditer(r"crop=(\d+):(\d+):(\d+):(\d+)", p.stderr or ""):
        last = tuple(int(g) for g in m.groups())
    return last  # (w, h, x, y)
