"""
Capture animated GIFs of the demo panel animations.

Targets:
  - /demo/governed-python-agent/  → site/demo/governed-python-agent/governed-python-agent.gif
  - /demo/adr-compiler/           → site/demo/adr-compiler/adr-compiler.gif

Usage:
  python scripts/gen_demo_gifs.py
"""

import asyncio
import io
import os
from pathlib import Path
from PIL import Image
from playwright.async_api import async_playwright

ROOT = Path(__file__).parent.parent

DEMOS = [
    {
        "url": "https://mnemehq.com/demo/governed-python-agent/",
        "out": ROOT / "site/demo/governed-python-agent/governed-python-agent.gif",
        "duration_ms": 9500,   # animation completes ~8.5s, add buffer
    },
    {
        "url": "https://mnemehq.com/demo/adr-compiler/",
        "out": ROOT / "site/demo/adr-compiler/adr-compiler.gif",
        "duration_ms": 8000,   # adr-compiler animation ~7s
    },
]

VIEWPORT    = {"width": 1280, "height": 900}
FPS         = 10                     # frames per second
FRAME_MS    = 1000 // FPS           # ms between captures
GIF_DELAY   = FRAME_MS // 10        # PIL delay units (10ms ticks)
WAIT_AFTER_LOAD = 1800              # ms to wait after networkidle before capture
PADDING     = 24                    # px padding around element in screenshot


async def capture_gif(page, demo: dict) -> None:
    url  = demo["url"]
    out  = demo["out"]
    dur  = demo["duration_ms"]

    print(f"\n> {url}")
    await page.goto(url, wait_until="networkidle", timeout=30_000)
    # Let fonts render and animation auto-start
    await page.wait_for_timeout(WAIT_AFTER_LOAD)

    # Find the demo wrap element
    el = page.locator(".demo-wrap").first
    await el.wait_for(state="visible", timeout=5000)

    n_frames = dur // FRAME_MS
    frames: list[Image.Image] = []

    print(f"   capturing {n_frames} frames at {FPS}fps …", flush=True)
    for i in range(n_frames):
        raw = await el.screenshot()
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        frames.append(img)
        if i < n_frames - 1:
            await page.wait_for_timeout(FRAME_MS)

    if not frames:
        print("   ⚠ no frames captured")
        return

    # Build palette from all frames (use first frame as reference, then quantize each)
    # Use a common palette derived from the first frame for consistency
    base = frames[0].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    palette_img = base.convert("P")
    quantized = []
    for f in frames:
        q = f.quantize(colors=128, palette=palette_img, method=Image.Quantize.MEDIANCUT)
        quantized.append(q)

    out.parent.mkdir(parents=True, exist_ok=True)
    quantized[0].save(
        out,
        save_all=True,
        append_images=quantized[1:],
        loop=0,            # loop forever
        duration=GIF_DELAY * 10,   # PIL expects ms; GIF_DELAY is in 10ms ticks
        optimize=True,
        disposal=2,
    )
    size_kb = out.stat().st_size // 1024
    print(f"   OK saved {out.relative_to(ROOT)}  ({size_kb} KB, {len(frames)} frames)")


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport=VIEWPORT)

        # Preload fonts so first frame isn't a FOUT
        await page.add_init_script("""
            document.fonts.ready.then(() => window.__fontsReady = true);
        """)

        for demo in DEMOS:
            await capture_gif(page, demo)

        await browser.close()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
