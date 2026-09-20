"""Pictly tool registry: MCP schemas and dispatch."""

from __future__ import annotations

from . import ops

PATH = {"path": {"type": "string", "description": "input image path"}}
OUT = {"out": {"type": "string", "description": "output image path"}}
FMT = {"format": {"type": "string", "description": "png, jpg, webp, avif, gif"}}
QUALITY = {"quality": {"type": "integer", "description": "1-100, higher is better"}}

TOOLS: list[dict] = [
    {
        "name": "inspect",
        "description": "Image info: dimensions, aspect, format, alpha, bytes, megapixels.",
        "inputSchema": {"type": "object", "properties": {**PATH}, "required": ["path"]},
        "handler": lambda a: ops.inspect(a["path"]),
    },
    {
        "name": "resize",
        "description": "Resize with fit modes: contain, exact (pad to box), cover (crop to fill), stretch.",
        "inputSchema": {"type": "object", "properties": {
            **PATH, **OUT,
            "width": {"type": "integer"}, "height": {"type": "integer"},
            "fit": {"type": "string", "enum": ["contain", "exact", "cover", "stretch"], "default": "contain"},
            "background": {"type": "string", "description": "hex color used by exact"},
            "allow_upscale": {"type": "boolean", "default": True},
            **FMT, **QUALITY,
        }, "required": ["path", "out"]},
        "handler": lambda a: ops.resize(a["path"], a["out"], **{k: v for k, v in a.items() if k not in ("path", "out")}),
    },
    {
        "name": "crop",
        "description": "Crop to a rectangle.",
        "inputSchema": {"type": "object", "properties": {
            **PATH, **OUT, "x": {"type": "integer"}, "y": {"type": "integer"},
            "width": {"type": "integer"}, "height": {"type": "integer"}, **FMT, **QUALITY,
        }, "required": ["path", "out", "x", "y", "width", "height"]},
        "handler": lambda a: ops.crop(a["path"], a["out"], a["x"], a["y"], a["width"], a["height"],
                                      format=a.get("format"), quality=a.get("quality")),
    },
    {
        "name": "trim",
        "description": "Auto-trim transparent or solid borders, optional padding.",
        "inputSchema": {"type": "object", "properties": {
            **PATH, **OUT, "threshold": {"type": "integer", "default": 12},
            "trim_white": {"type": "boolean", "default": True},
            "padding": {"type": "integer", "default": 0}, **FMT, **QUALITY,
        }, "required": ["path"]},
        "handler": lambda a: ops.trim(a["path"], a.get("out"), **{k: v for k, v in a.items() if k not in ("path", "out")}),
    },
    {
        "name": "normalize",
        "description": "Trim borders then fit onto a uniform canvas (equal margins). The catalogue/cover treatment.",
        "inputSchema": {"type": "object", "properties": {
            **PATH, **OUT,
            "canvas_width": {"type": "integer", "default": 800},
            "canvas_height": {"type": "integer", "default": 1240},
            "margin": {"type": "integer", "default": 40},
            "background": {"type": "string", "default": "transparent"},
            "threshold": {"type": "integer", "default": 12},
            "trim_white": {"type": "boolean", "default": True}, **FMT, **QUALITY,
        }, "required": ["path"]},
        "handler": lambda a: ops.normalize(a["path"], a.get("out"), **{k: v for k, v in a.items() if k not in ("path", "out")}),
    },
    {
        "name": "shape",
        "description": "Mask an image: rounded corners, circle, or arch. Optional background color to flatten.",
        "inputSchema": {"type": "object", "properties": {
            **PATH, **OUT, "kind": {"type": "string", "enum": ["rounded", "circle", "arch"], "default": "rounded"},
            "radius": {"type": "integer", "default": 24},
            "width": {"type": "integer"}, "height": {"type": "integer"},
            "background": {"type": "string"}, **FMT, **QUALITY,
        }, "required": ["path", "out"]},
        "handler": lambda a: ops.shape(a["path"], a["out"], **{k: v for k, v in a.items() if k not in ("path", "out")}),
    },
    {
        "name": "effects",
        "description": "Filters: brightness, contrast, saturation, gamma, blur, sharpen, denoise, grayscale, sepia, vignette, rotate, flip.",
        "inputSchema": {"type": "object", "properties": {
            **PATH, **OUT,
            "brightness": {"type": "number", "default": 0.0},
            "contrast": {"type": "number", "default": 1.0},
            "saturation": {"type": "number", "default": 1.0},
            "gamma": {"type": "number", "default": 1.0},
            "blur": {"type": "number", "default": 0.0},
            "sharpen": {"type": "number", "default": 0.0},
            "denoise": {"type": "boolean", "default": False},
            "grayscale": {"type": "boolean", "default": False},
            "sepia": {"type": "boolean", "default": False},
            "vignette": {"type": "boolean", "default": False},
            "rotate": {"type": "integer", "enum": [0, 90, 180, 270], "default": 0},
            "flip": {"type": "string", "enum": ["horizontal", "vertical"]},
            "deband": {"type": "number", "default": 0.0, "description": "gradient debanding threshold"},
            "grain": {"type": "integer", "default": 0, "description": "film grain strength 0-20"},
            **FMT, **QUALITY,
        }, "required": ["path", "out"]},
        "handler": lambda a: ops.effects(a["path"], a["out"], **{k: v for k, v in a.items() if k not in ("path", "out")}),
    },
    {
        "name": "enhance",
        "description": "One-call presets: product, photo, clarity, soft, document, bw.",
        "inputSchema": {"type": "object", "properties": {
            **PATH, **OUT,
            "preset": {"type": "string", "enum": list(ops.PRESETS.keys()), "default": "product"},
            **FMT, **QUALITY,
        }, "required": ["path", "out"]},
        "handler": lambda a: ops.enhance(a["path"], a["out"], **{k: v for k, v in a.items() if k not in ("path", "out")}),
    },
    {
        "name": "convert",
        "description": "Convert between formats (png, jpg, webp, avif, gif) with quality control.",
        "inputSchema": {"type": "object", "properties": {
            **PATH, **OUT, "format": {"type": "string"}, **QUALITY,
            "strip_metadata": {"type": "boolean", "default": True},
        }, "required": ["path", "out", "format"]},
        "handler": lambda a: ops.convert(a["path"], a["out"], a["format"], a.get("quality"), a.get("strip_metadata", True)),
    },
    {
        "name": "compress",
        "description": "Compress to target format/quality and report savings.",
        "inputSchema": {"type": "object", "properties": {
            **PATH, **OUT, **FMT, **QUALITY,
        }, "required": ["path", "out"]},
        "handler": lambda a: ops.compress(a["path"], a["out"], a.get("quality", 80), a.get("format")),
    },
    {
        "name": "upscale",
        "description": "High quality upscale: two-step lanczos for 3x+ with contrast-adaptive sharpening, or xbr for pixel art. Nothing is invented, but edges stay clean.",
        "inputSchema": {"type": "object", "properties": {
            **PATH, **OUT,
            "factor": {"type": "number", "description": "e.g. 1.5, 2, 3"},
            "width": {"type": "integer"}, "height": {"type": "integer"},
            "method": {"type": "string", "enum": ["lanczos", "bicubic", "neighbor", "bilinear", "xbr"], "default": "lanczos"},
            "sharpen": {"type": "boolean", "default": True},
            "sharpen_strength": {"type": "number", "default": 0.55},
            **FMT, **QUALITY,
        }, "required": ["path", "out"]},
        "handler": lambda a: ops.upscale(a["path"], a["out"], **{k: v for k, v in a.items() if k not in ("path", "out")}),
    },
    {
        "name": "denoise",
        "description": "Noise reduction: hqdn3d (fast), nlmeans (best quality for photos), atadenoise.",
        "inputSchema": {"type": "object", "properties": {
            **PATH, **OUT,
            "method": {"type": "string", "enum": ["hqdn3d", "nlmeans", "atadenoise"], "default": "hqdn3d"},
            "strength": {"type": "number", "default": 1.0},
            **FMT, **QUALITY,
        }, "required": ["path", "out"]},
        "handler": lambda a: ops.denoise(a["path"], a["out"], **{k: v for k, v in a.items() if k not in ("path", "out")}),
    },
    {
        "name": "sharpen",
        "description": "Sharpening: cas (contrast adaptive, no halos) or unsharp (classic).",
        "inputSchema": {"type": "object", "properties": {
            **PATH, **OUT,
            "method": {"type": "string", "enum": ["cas", "unsharp"], "default": "cas"},
            "strength": {"type": "string", "enum": ["subtle", "standard", "strong"], "default": "standard"},
            "amount": {"type": "number", "description": "override strength numerically"},
            **FMT, **QUALITY,
        }, "required": ["path", "out"]},
        "handler": lambda a: ops.sharpen(a["path"], a["out"], **{k: v for k, v in a.items() if k not in ("path", "out")}),
    },
    {
        "name": "auto_quality",
        "description": "Automatic quality pass: auto levels, white balance, denoise, vibrance and adaptive sharpening. Presets: web, product, photo, art, max.",
        "inputSchema": {"type": "object", "properties": {
            **PATH, **OUT,
            "preset": {"type": "string", "enum": list(ops.QUALITY_PRESETS.keys()), "default": "product"},
            "grain": {"type": "integer", "default": 0, "description": "optional film grain 0-20"},
            **FMT, **QUALITY,
        }, "required": ["path", "out"]},
        "handler": lambda a: ops.auto_quality(a["path"], a["out"], **{k: v for k, v in a.items() if k not in ("path", "out")}),
    },
    {
        "name": "deband",
        "description": "Remove gradient banding (skies, studio backgrounds) before compression.",
        "inputSchema": {"type": "object", "properties": {
            **PATH, **OUT,
            "strength": {"type": "number", "default": 0.02},
            **FMT, **QUALITY,
        }, "required": ["path", "out"]},
        "handler": lambda a: ops.deband(a["path"], a["out"], **{k: v for k, v in a.items() if k not in ("path", "out")}),
    },
    {
        "name": "responsive",
        "description": "Generate a responsive set of widths plus a JSON manifest.",
        "inputSchema": {"type": "object", "properties": {
            **PATH,
            "out_dir": {"type": "string"},
            "widths": {"type": "array", "items": {"type": "integer"}},
            **FMT, **QUALITY,
        }, "required": ["path", "out_dir"]},
        "handler": lambda a: ops.responsive(a["path"], a["out_dir"],
                                            widths=a.get("widths", (320, 480, 640, 960, 1280)),
                                            format=a.get("format", "webp"),
                                            quality=a.get("quality", 80)),
    },
    {
        "name": "palette",
        "description": "Dominant color palette as hex values.",
        "inputSchema": {"type": "object", "properties": {
            **PATH, "colors": {"type": "integer", "default": 6},
        }, "required": ["path"]},
        "handler": lambda a: ops.palette(a["path"], a.get("colors", 6)),
    },
    {
        "name": "placeholder",
        "description": "Generate a solid or two-color gradient placeholder image.",
        "inputSchema": {"type": "object", "properties": {
            **OUT, "width": {"type": "integer", "default": 800}, "height": {"type": "integer", "default": 600},
            "color": {"type": "string", "default": "#3366cc"},
            "color2": {"type": "string", "description": "second color for a vertical gradient"},
            **FMT, **QUALITY,
        }, "required": ["out"]},
        "handler": lambda a: ops.placeholder(a["out"], **{k: v for k, v in a.items() if k != "out"}),
    },
    {
        "name": "pipeline",
        "description": "Run a chain of operations in one call, e.g. trim, resize, shape, convert.",
        "inputSchema": {"type": "object", "properties": {
            **PATH, **OUT,
            "steps": {"type": "array", "items": {"type": "object",
                "properties": {"op": {"type": "string"}}, "required": ["op"]}},
        }, "required": ["path", "out", "steps"]},
        "handler": lambda a: ops.pipeline(a["path"], a["out"], a["steps"]),
    },
]


def tool_catalog() -> list[dict]:
    return [{k: t[k] for k in ("name", "description", "inputSchema")} for t in TOOLS]


def call_tool(name: str, args: dict) -> dict:
    for t in TOOLS:
        if t["name"] == name:
            try:
                return {"ok": True, "result": t["handler"](args or {})}
            except Exception as exc:
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": False, "error": f"unknown tool: {name}"}
