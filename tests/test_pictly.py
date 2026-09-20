"""Pictly tests: run every tool on a real image. Stdlib only.

    python3 tests/test_pictly.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pictly import ffmpeg as ff          # noqa: E402
from pictly import png as P               # noqa: E402
from pictly.tools import call_tool, tool_catalog  # noqa: E402

PASS = FAIL = 0


def make_fixture(path: Path, width: int = 800, height: int = 1240) -> None:
    """Self-contained test image: a coloured block with transparent margins."""
    px = bytearray(width * height * 4)
    x0, y0, x1, y1 = 160, 300, 640, 940
    for y in range(y0, y1):
        for x in range(x0, x1):
            o = (y * width + x) * 4
            px[o], px[o + 1], px[o + 2], px[o + 3] = 0x33, 0x66, 0xCC, 255
    for y in range(y0 + 60, y0 + 120):
        for x in range(x0 + 40, x1 - 40):
            o = (y * width + x) * 4
            px[o] = px[o + 1] = px[o + 2] = 255
            px[o + 3] = 255
    P.write_png(path, width, height, px)


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def run(name, **args):
    return call_tool(name, args)


def main():
    print(f"pictly tests — {ROOT}")
    print(f"ffmpeg: {'yes' if ff.FFMPEG else 'NO'} | ffprobe: {'yes' if ff.FFPROBE else 'NO'}")

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        src = td / "cover.png"
        make_fixture(src)

        print("catalog")
        names = [t["name"] for t in tool_catalog()]
        check("19 tools registered", len(names) == 19, str(names))

        print("inspect")
        r = run("inspect", path=str(src))
        check("inspect ok", r["ok"], r.get("error"))
        dims = (r["result"].get("width"), r["result"].get("height"))
        check("dimensions read", dims == (800, 1240), str(dims))

        print("trim")
        r = run("trim", path=str(src), out=str(td / "trim.png"))
        check("trim ok", r["ok"], r.get("error"))
        check("trim smaller than canvas", r.get("result", {}).get("width", 9999) <= 800, str(r.get("result")))

        print("normalize")
        r = run("normalize", path=str(src), out=str(td / "norm.png"))
        check("normalize ok", r["ok"], r.get("error"))
        check("normalize canvas exact", (r["result"].get("width"), r["result"].get("height")) == (800, 1240))

        print("resize")
        for fit, out, expect in [("contain", "r-contain.webp", None), ("exact", "r-exact.jpg", (400, 600)),
                                 ("cover", "r-cover.webp", (400, 600))]:
            r = run("resize", path=str(src), out=str(td / out), width=400, height=600, fit=fit, format=out.split(".")[-1], quality=82)
            check(f"resize {fit}", r["ok"], r.get("error"))
            if expect:
                got = (r["result"].get("width"), r["result"].get("height"))
                check(f"resize {fit} dims", got == expect, str(got))

        print("crop")
        r = run("crop", path=str(src), out=str(td / "crop.png"), x=100, y=100, width=300, height=200)
        check("crop ok", r["ok"] and (r["result"].get("width"), r["result"].get("height")) == (300, 200), r.get("error"))

        print("shape")
        for kind in ("rounded", "circle", "arch"):
            r = run("shape", path=str(src), out=str(td / f"shape-{kind}.png"), kind=kind, radius=40, width=320, height=400)
            check(f"shape {kind}", r["ok"], r.get("error"))
        r = run("shape", path=str(src), out=str(td / "shape-bg.jpg"), kind="arch", background="#FFFDF8", width=320, height=400)
        check("shape with background", r["ok"], r.get("error"))

        print("effects / enhance")
        r = run("effects", path=str(src), out=str(td / "fx.png"), blur=1.2, sharpen=0.6, grayscale=True, vignette=True, rotate=90)
        check("effects ok", r["ok"], r.get("error"))
        for preset in ("product", "photo", "clarity", "bw"):
            r = run("enhance", path=str(src), out=str(td / f"enh-{preset}.jpg"), preset=preset, quality=85)
            check(f"enhance {preset}", r["ok"], r.get("error"))

        print("convert / compress")
        r = run("convert", path=str(src), out=str(td / "conv.webp"), format="webp", quality=75)
        check("convert png->webp", r["ok"], r.get("error"))
        r = run("compress", path=str(src), out=str(td / "small.webp"), quality=55)
        check("compress reports savings", r["ok"] and r["result"].get("saved_percent") is not None, r.get("error"))

        print("quality suite")
        small = td / "small.png"
        r = run("resize", path=str(src), out=str(small), width=320, fit="contain", format="png")
        check("quality fixture", r["ok"], r.get("error"))
        r = run("upscale", path=str(small), out=str(td / "up2x.webp"), factor=2, format="webp", quality=85)
        check("upscale 2x dims", r["ok"] and (r["result"].get("width"), r["result"].get("height")) == (640, 992), r.get("error") or str(r.get("result")))
        r = run("denoise", path=str(small), out=str(td / "dn.png"), method="hqdn3d", strength=1.0)
        check("denoise hqdn3d", r["ok"], r.get("error"))
        r = run("denoise", path=str(small), out=str(td / "dn2.png"), method="nlmeans", strength=0.8)
        check("denoise nlmeans", r["ok"], r.get("error"))
        for m in ("cas", "unsharp"):
            r = run("sharpen", path=str(small), out=str(td / f"sh-{m}.png"), method=m, strength="standard")
            check(f"sharpen {m}", r["ok"], r.get("error"))
        for p in ("web", "product", "photo", "art", "max"):
            r = run("auto_quality", path=str(small), out=str(td / f"aq-{p}.webp"), preset=p, quality=82, format="webp")
            check(f"auto_quality {p}", r["ok"], r.get("error"))
        r = run("deband", path=str(small), out=str(td / "db.png"), strength=0.02)
        check("deband", r["ok"], r.get("error"))
        r = run("effects", path=str(small), out=str(td / "fx2.png"), deband=0.02, grain=6)
        check("effects deband+grain", r["ok"], r.get("error"))

        print("responsive")
        r = run("responsive", path=str(src), out_dir=str(td / "set"), widths=[200, 400], format="webp", quality=80)
        check("responsive variants", r["ok"] and len(r["result"].get("variants", [])) == 2, r.get("error"))
        check("responsive manifest", Path(r["result"].get("manifest", "")).exists() if r["ok"] else False)

        print("palette")
        r = run("palette", path=str(src), colors=5)
        check("palette hex colors", r["ok"] and len(r["result"].get("colors", [])) > 0, r.get("error"))

        print("placeholder")
        r = run("placeholder", out=str(td / "ph.png"), width=320, height=200, color="#3366cc")
        check("placeholder solid", r["ok"], r.get("error"))
        r = run("placeholder", out=str(td / "phg.webp"), width=320, height=200, color="#3366cc", color2="#FFCC66")
        check("placeholder gradient", r["ok"], r.get("error"))

        print("pipeline")
        r = run("pipeline", path=str(src), out=str(td / "final.webp"),
                steps=[{"op": "trim"}, {"op": "resize", "width": 300}, {"op": "shape", "kind": "rounded", "radius": 24},
                       {"op": "enhance", "preset": "product"}, {"op": "convert", "format": "webp", "quality": 78}])
        check("pipeline runs", r["ok"], r.get("error"))

        print("mcp handshake")
        payload = "\n".join([
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "inspect", "arguments": {"path": str(src)}}}),
        ]) + "\n"
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        p = subprocess.run([sys.executable, "-m", "pictly", "mcp"], input=payload, capture_output=True, text=True, timeout=60, env=env)
        lines = [json.loads(l) for l in p.stdout.strip().splitlines() if l.strip()]
        check("mcp initialize", any(x.get("id") == 1 and x["result"]["serverInfo"]["name"] == "pictly" for x in lines))
        check("mcp tools/list", any(x.get("id") == 2 and len(x["result"]["tools"]) == 19 for x in lines))
        check("mcp tools/call", any(x.get("id") == 3 and not x["result"].get("isError") for x in lines))

    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
