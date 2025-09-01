import asyncio
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import logging
import time

logger = logging.getLogger(__name__)

# Directory to store snapshots
EVIDENCE_DIR = "./evidence_snapshots"
EVD = Path(EVIDENCE_DIR)
EVD.mkdir(parents=True, exist_ok=True)

def _hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]

def cleanup_old_snapshots(max_age_seconds: int = 86400):
    """Delete snapshots older than max_age_seconds (default 24h)."""
    now = time.time()
    deleted_files = 0
    for f in EVD.glob("snapshot_*.txt"):
        if now - f.stat().st_mtime > max_age_seconds:
            try:
                f.unlink()
                deleted_files += 1
                logger.info(f"Deleted old text snapshot: {f}")
            except Exception as e:
                logger.error(f"Failed to delete {f}: {e}")
    for f in EVD.glob("shot_*.png"):
        if now - f.stat().st_mtime > max_age_seconds:
            try:
                f.unlink()
                deleted_files += 1
                logger.info(f"Deleted old screenshot: {f}")
            except Exception as e:
                logger.error(f"Failed to delete {f}: {e}")
    logger.info(f"Cleanup complete. Total deleted files: {deleted_files}")

async def save_text_snapshot(source: str, snippet: str) -> str:
    """
    Save a text snippet as a snapshot with source metadata.
    """
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    name = _hash(source + snippet + ts)
    fn = EVD / f"snapshot_{name}.txt"
    content = f"Source: {source}\nTime: {ts}\n\n{snippet}"
    fn.write_text(content, encoding="utf-8")
    logger.info(f"Saved text snapshot: {fn}")
    return str(fn.resolve())

async def capture_url_screenshot(url: str, full_page: bool = True) -> str | None:
    """
    Async capture of a webpage screenshot.
    Tries pyppeteer first (lighter), then playwright fallback.
    """
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    name = _hash(url + ts)
    out = EVD / f"shot_{name}.png"

    # Attempt pyppeteer
    try:
        from pyppeteer import launch
        browser = await launch(headless=True, args=['--no-sandbox'])
        page = await browser.newPage()
        await page.setViewport({'width': 1280, 'height': 800})
        await page.goto(url, {'timeout': 30000})
        await asyncio.sleep(1)  # wait for page load
        if full_page:
            await page.screenshot({'path': str(out), 'fullPage': True})
        else:
            await page.screenshot({'path': str(out)})
        await browser.close()
        logger.info(f"Captured screenshot with pyppeteer: {out}")
        return str(out.resolve())
    except Exception as e:
        logger.debug(f"pyppeteer failed: {e}")

    # Fallback to playwright (sync wrapped in executor)
    try:
        import concurrent.futures
        from playwright.sync_api import sync_playwright

        def _playwright_capture():
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_viewport_size({"width": 1280, "height": 800})
                page.goto(url, timeout=30000)
                page.wait_for_load_state("networkidle", timeout=15000)
                if full_page:
                    page.screenshot(path=str(out), full_page=True)
                else:
                    page.screenshot(path=str(out))
                browser.close()
            return str(out.resolve())

        loop = asyncio.get_event_loop()
        path = await loop.run_in_executor(None, _playwright_capture)
        logger.info(f"Captured screenshot with playwright: {path}")
        return path
    except Exception as e:
        logger.debug(f"playwright failed: {e}")

    logger.error(f"Failed to capture screenshot for url: {url}")
    return None

# Stub async method for document snapshot (e.g. PDF page or OCR snippet)
async def capture_document_snapshot(doc_path: str, page_number: int | None = None, region: tuple | None = None) -> str | None:
    """
    Capture an image snapshot from a document (PDF, image).
    page_number: PDF page index (1-based).
    region: (left, top, right, bottom) in pixels, optional.
    Returns path to saved image or None.
    """
    # TODO: implement PDF rendering with pdf2image or similar,
    # crop region if specified, save to evidence dir.
    logger.info(f"Stub: capture document snapshot from {doc_path} page {page_number} region {region}")
    return None

# Stub async method for video snapshot (frame capture)
async def capture_video_snapshot(video_url: str, timestamp_sec: float | None = None) -> str | None:
    """
    Capture a snapshot image from a video player at given timestamp.
    video_url: URL or local path of video.
    timestamp_sec: time position in seconds.
    Returns path to saved image or None.
    """
    # TODO: implement video frame capture using e.g. ffmpeg or Selenium + headless browser.
    logger.info(f"Stub: capture video snapshot from {video_url} at {timestamp_sec}s")
    return None

# Unified async interface to Mind pipeline
async def capture_evidence_snapshot(
    content_type: str,
    source_reference: str,
    highlight_selector: str | None = None,
    **kwargs
) -> str | None:
    """
    Capture snapshot based on content type.
    content_type: "webpage", "document", "video", "text"
    source_reference: URL, filepath, or text source string.
    highlight_selector: CSS selector or text snippet, optional.
    Additional kwargs for stubs.
    """
    if content_type == "webpage":
        return await capture_url_screenshot(source_reference, full_page=True)
    elif content_type == "document":
        page_number = kwargs.get("page_number")
        region = kwargs.get("region")
        return await capture_document_snapshot(source_reference, page_number, region)
    elif content_type == "video":
        timestamp_sec = kwargs.get("timestamp_sec")
        return await capture_video_snapshot(source_reference, timestamp_sec)
    elif content_type == "text":
        snippet = kwargs.get("snippet", "")
        return await save_text_snapshot(source_reference, snippet)
    else:
        logger.warning(f"Unknown content_type for snapshot: {content_type}")
        return None

cleanup_old_snapshots()
