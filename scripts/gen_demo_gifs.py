"""
Capture animated GIFs of demo pages.

Outputs:
  site/demo/gifs/governed-python-agent.gif   — animation of the namespace violation loop
  site/demo/gifs/adr-compiler.gif            — animation of the storage violation loop
  site/demo/gifs/multi-agent-governance.gif  — scroll through the three actor steps

Usage:
  python scripts/gen_demo_gifs.py
"""

import asyncio
import io
import os
from pathlib import Path
from PIL import Image
from playwright.async_api import async_playwright

ROOT   = Path(__file__).parent.parent
OUTDIR = ROOT / "site/demo/gifs"

VIEWPORT = {"width": 1280, "height": 900}
FPS      = 10
FRAME_MS = 1000 // FPS  # ms between frames


# ── helpers ──────────────────────────────────────────────────────────────────

def save_gif(frames: list[Image.Image], out: Path) -> None:
    base = frames[0].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    palette_img = base.convert("P")
    quantized = [
        f.quantize(colors=128, palette=palette_img, method=Image.Quantize.MEDIANCUT)
        for f in frames
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    quantized[0].save(
        out,
        save_all=True,
        append_images=quantized[1:],
        loop=0,
        duration=FRAME_MS,
        optimize=True,
        disposal=2,
    )
    size_kb = out.stat().st_size // 1024
    rel = out.relative_to(ROOT)
    print(f"   saved {rel}  ({size_kb} KB, {len(frames)} frames)")


async def grab_frames(el, n: int, page) -> list[Image.Image]:
    frames = []
    for i in range(n):
        raw = await el.screenshot()
        frames.append(Image.open(io.BytesIO(raw)).convert("RGB"))
        if i < n - 1:
            await page.wait_for_timeout(FRAME_MS)
    return frames


# ── animated demos (demo-wrap element) ───────────────────────────────────────

async def capture_animated(page, url: str, duration_ms: int, out: Path) -> None:
    print(f"\n> {url}")
    await page.goto(url, wait_until="networkidle", timeout=30_000)
    await page.wait_for_timeout(2000)   # fonts + animation start

    el = page.locator(".demo-wrap").first
    await el.wait_for(state="visible", timeout=5000)

    n = duration_ms // FRAME_MS
    print(f"   capturing {n} frames …", flush=True)
    frames = await grab_frames(el, n, page)
    save_gif(frames, out)


# ── scroll demos ─────────────────────────────────────────────────────────────

async def capture_scroll(page, url: str, out: Path,
                          start_selector: str, end_selector: str,
                          hold_start_ms: int = 1200,
                          scroll_ms_per_px: float = 0.28,
                          hold_end_ms: int = 1500) -> None:
    print(f"\n> {url}")
    await page.goto(url, wait_until="networkidle", timeout=30_000)
    await page.wait_for_timeout(1500)

    start_el = page.locator(start_selector).first
    await start_el.scroll_into_view_if_needed()
    await page.wait_for_timeout(300)

    start_box  = await start_el.bounding_box()
    end_box    = await page.locator(end_selector).first.bounding_box()
    scroll_px  = end_box["y"] - start_box["y"]
    scroll_dur = int(scroll_px * scroll_ms_per_px)

    # Viewport crop: centre on start element, full width
    crop_top  = max(0, int(start_box["y"]) - 32)
    crop_h    = VIEWPORT["height"]

    frames: list[Image.Image] = []

    async def snapshot():
        raw = await page.screenshot()
        full = Image.open(io.BytesIO(raw)).convert("RGB")
        w = full.width
        # Crop to the viewport strip at the current scroll position
        frames.append(full.crop((0, 0, w, crop_h)))

    # Hold at top
    n_hold_start = max(1, hold_start_ms // FRAME_MS)
    for _ in range(n_hold_start):
        await snapshot()
        await page.wait_for_timeout(FRAME_MS)

    # Scroll down frame-by-frame
    steps = max(1, scroll_dur // FRAME_MS)
    per_step = scroll_px / steps
    current_y = crop_top
    for _ in range(steps):
        current_y += per_step
        await page.evaluate(f"window.scrollTo({{top: {current_y}, behavior: 'instant'}})")
        await snapshot()
        await page.wait_for_timeout(FRAME_MS)

    # Hold at end
    n_hold_end = max(1, hold_end_ms // FRAME_MS)
    for _ in range(n_hold_end):
        await snapshot()
        await page.wait_for_timeout(FRAME_MS)

    print(f"   captured {len(frames)} frames …", flush=True)
    save_gif(frames, out)


# ── main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport=VIEWPORT)

        # 1. Governed Python agent — animated
        await capture_animated(
            page,
            url="https://mnemehq.com/demo/governed-python-agent/",
            duration_ms=9500,
            out=OUTDIR / "governed-python-agent.gif",
        )

        # 2. ADR compiler — animated (storage/database violation)
        await capture_animated(
            page,
            url="https://mnemehq.com/demo/adr-compiler/",
            duration_ms=8000,
            out=OUTDIR / "adr-compiler.gif",
        )

        # 3. Multi-agent governance — scroll through the three actor steps
        await capture_scroll(
            page,
            url="https://mnemehq.com/demo/multi-agent-governance/",
            out=OUTDIR / "multi-agent-governance.gif",
            start_selector="h2:has-text('With the governance layer')",
            end_selector=".callout",   # the "What stayed coherent" callout after Actor C
            hold_start_ms=1200,
            scroll_ms_per_px=0.30,    # ~3.3 px/ms → ~300px/s → readable
            hold_end_ms=2000,
        )

        await browser.close()

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
