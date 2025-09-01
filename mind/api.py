import logging
import uvicorn
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from pydantic import BaseModel
import psutil
from config.settings import MAX_RAM_PERCENT, WARN_RAM_PERCENT, EVIDENCE_TTL, CLEANUP_INTERVAL
from mind.rag_pipeline import RAGPipeline
from mind.validation_engine import MindValidator
from mind.ttl_manager import start_periodic_cleanup, cleanup_once
from mind.chroma_manager import CHROMADB_AVAILABLE, ChromaManager
from mind.ocr_processor import pdf_to_text_pages
from pathlib import Path
import shutil
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mind.api")

app = FastAPI(title="Mind Agent API")

# instantiate pipeline & validator
pipeline = RAGPipeline()
validator = MindValidator()

# cleanup at startup and schedule
cleanup_once(EVIDENCE_TTL)
start_periodic_cleanup(EVIDENCE_TTL, CLEANUP_INTERVAL)

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

class AskRequest(BaseModel):
    query: str
    validate: bool = False

@app.middleware("http")
async def ram_guard(request: Request, call_next):
    used = psutil.virtual_memory().percent
    if used >= MAX_RAM_PERCENT:
        raise HTTPException(status_code=503, detail="System memory too high. Try again later.")
    if used >= WARN_RAM_PERCENT:
        logger.warning("Memory usage high: %s%%", used)
    return await call_next(request)

@app.post("/ask")
async def ask(req: AskRequest):
    """
    Main entrypoint: user asks a query. Mind runs local-first -> web fallback -> merge -> LLM -> validate (optional)
    """
    try:
        logger.info("Received query: %s", req.query)
        res = pipeline.run(req.query)
        # construct split results
        evidence = res.get("evidence", [])
        local_snips = [e["snippet"] for e in evidence if e.get("type") == "local"]
        web_snips = [e["snippet"] for e in evidence if e.get("type") == "web"]
        response = {
            "answer": res.get("answer"),
            "from_docs": local_snips,
            "from_web": web_snips,
            "evidence": evidence
        }
        if req.validate:
            v = validator.validate(req.query, res)
            response["validation"] = v
        return response
    except Exception:
        logger.exception("Ask error")
        raise HTTPException(status_code=500, detail="Internal agent error.")

@app.post("/ingest")
async def ingest(file: UploadFile = File(...), doc_id: str = Form(...)):
    """
    Upload a PDF and ingest its pages into Chroma (local DB).
    OCR is used when PyMuPDF text extraction yields empty page text.
    """
    if not CHROMADB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Chroma not available.")
    filename = Path(file.filename).name
    target = UPLOAD_DIR / filename
    with target.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    # extract pages
    try:
        pages = pdf_to_text_pages(str(target))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed extracting PDF pages.")
    try:
        cm = ChromaManager()
        cm.ingest_document(doc_id, pages, metadata={"uploaded_at": time.time()})
        return {"status": "ingested", "doc_id": doc_id, "pages": len(pages)}
    except Exception:
        logger.exception("Ingest failed")
        raise HTTPException(status_code=500, detail="Ingest failed.")

if __name__ == "__main__":
    uvicorn.run("mind.api:app", host="0.0.0.0", port=8000, reload=True)
