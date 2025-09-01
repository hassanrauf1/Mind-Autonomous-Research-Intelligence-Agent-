import threading
import time
import logging
from config.settings import EVIDENCE_TTL, CLEANUP_INTERVAL
from pathlib import Path
from mind.chroma_manager import CHROMADB_AVAILABLE, ChromaManager
from config.settings import EVIDENCE_DIR

logger = logging.getLogger(__name__)
EVIDENCE_DIR = Path(EVIDENCE_DIR)

def _cleanup_files(ttl_seconds: int):
    now = time.time()
    for f in EVIDENCE_DIR.iterdir():
        try:
            if now - f.stat().st_mtime > ttl_seconds:
                f.unlink()
                logger.info("Deleted evidence file: %s", f)
        except Exception:
            logger.exception("Failed deleting evidence file: %s", f)

def _cleanup_chroma(ttl_seconds: int):
    if not CHROMADB_AVAILABLE:
        return
    try:
        cm = ChromaManager()
        cm.remove_expired_temp(ttl_seconds)
    except Exception:
        logger.exception("Failed chroma cleanup")

def cleanup_once(ttl_seconds: int = EVIDENCE_TTL):
    _cleanup_files(ttl_seconds)
    _cleanup_chroma(ttl_seconds)

def start_periodic_cleanup(ttl_seconds: int = EVIDENCE_TTL, interval_seconds: int = CLEANUP_INTERVAL):
    def loop():
        while True:
            try:
                cleanup_once(ttl_seconds)
            except Exception:
                logger.exception("Cleanup iteration failed")
            time.sleep(interval_seconds)
    t = threading.Thread(target=loop, daemon=True)
    t.start()

