# Pictly

Image toolkit for agents. Resize, crop, trim, normalize, shape, enhance, compress,
convert, and generate responsive sets — from one MCP server or CLI.

**Zero Python dependencies.** A native PNG engine (stdlib only) does exact pixel work:
alpha/white trimming, uniform canvases, rounded/circle/arch masks. An ffmpeg adapter
covers every other format (jpeg, webp, avif, gif) and filters.

## Tools

| Tool | What it does |
|---|---|
| `inspect` | dimensions, aspect, format, alpha, bytes, megapixels |
| `resize` | contain, exact (pad to box), cover (crop to fill), stretch |
| `crop` | rectangle crop |
| `trim` | auto-trim transparent or solid borders, optional padding |
| `normalize` | trim then place on a uniform canvas with equal margins |
| `shape` | rounded corners, circle, mihrab arch, optional background |
| `effects` | brightness, contrast, saturation, gamma, blur, sharpen, denoise, grayscale, sepia, vignette, rotate, flip, deband, grain |
| `enhance` | presets: product, photo, clarity, soft, document, bw |
| `auto_quality` | automatic pass: auto levels, white balance, denoise, vibrance, adaptive sharpening (web, product, photo, art, max) |
| `upscale` | high quality 2x/3x/4x: two-step lanczos with adaptive sharpening, or xbr for pixel art |
| `denoise` | hqdn3d, nlmeans (best for photos), atadenoise |
| `sharpen` | cas (contrast adaptive, no halos) or unsharp |
| `deband` | remove gradient banding before compression |
| `convert` | png, jpg, webp, avif, gif with quality control |
| `compress` | target quality and report savings |
| `responsive` | width set plus JSON manifest |
| `palette` | dominant colors as hex |
| `placeholder` | solid or two-color gradient placeholder |
| `pipeline` | chain operations in one call |

## CLI

```bash
PYTHONPATH=src python3 -m pictly list
PYTHONPATH=src python3 -m pictly inspect photo.jpg
PYTHONPATH=src python3 -m pictly tool resize --json '{"path":"a.png","out":"a.webp","width":800,"fit":"contain","format":"webp","quality":82}'
PYTHONPATH=src python3 -m pictly tool normalize --json '{"path":"cover.png","out":"cover-norm.png","canvas_width":800,"canvas_height":1240}'
PYTHONPATH=src python3 -m pictly tool pipeline --json '{"path":"raw.jpg","out":"final.webp","steps":[{"op":"trim"},{"op":"resize","width":900},{"op":"shape","kind":"rounded","radius":24},{"op":"enhance","preset":"product"},{"op":"convert","format":"webp","quality":80}]}'
PYTHONPATH=src python3 -m pictly mcp
```

Optional install: `pip install -e .` (then `pictly ...`).

## MCP config

```json
{
  "mcp": {
    "pictly": {
      "type": "local",
      "command": ["python3", "-m", "pictly", "mcp"],
      "environment": { "PYTHONPATH": "/path/to/pictly/src" },
      "enabled": true
    }
  }
}
```

## Requirements

- Python 3.10+
- ffmpeg and ffprobe on PATH for non-PNG formats and filters (PNG workflows run without them)

## Tests

```bash
python3 tests/test_pictly.py
```

46 checks covering every tool against real images, plus the MCP handshake.

## Roadmap

- Watermark and text overlay with bundled font
- Background removal via chroma key and edge-aware matte
- Sprite sheets and multi-image montage
- Directory batch mode with a pipeline applied to every file

MIT.
