# mind/chroma_manager.py
import logging
import time
from pathlib import Path
from config.settings import CHROMA_DB_PATH, EMBED_MODEL, EMBED_BATCH_SIZE
import numpy as np

logger = logging.getLogger(__name__)

try:
    from chromadb import PersistentClient
    CHROMADB_AVAILABLE = True
except Exception:
    PersistentClient = None
    CHROMADB_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    ST_AVAILABLE = True
except Exception:
    SentenceTransformer = None
    ST_AVAILABLE = False

class ChromaManager:
    def __init__(self, collection_name: str = "mind_docs"):
        if not CHROMADB_AVAILABLE or not ST_AVAILABLE:
            raise RuntimeError("chromadb or sentence-transformers not available.")
        self.db_path = Path(CHROMA_DB_PATH)
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.client = PersistentClient(path=str(self.db_path))
        self.collection = self.client.get_or_create_collection(collection_name)
        self.embedder = SentenceTransformer(EMBED_MODEL)
        self.batch_size = max(1, int(EMBED_BATCH_SIZE))

    def ingest_document(self, doc_id: str, pages: list[str], metadata: dict | None = None):
        """
        Ingest a list of text chunks (pages/chunks) with metadata.
        This function avoids loading PDFs itself; OCR/loader should supply pages.
        """
        if not pages:
            logger.warning("No pages to ingest for %s", doc_id)
            return
        embeddings = []
        for i in range(0, len(pages), self.batch_size):
            batch = pages[i:i+self.batch_size]
            emb = self.embedder.encode(batch, convert_to_numpy=True, show_progress_bar=False)
            if isinstance(emb, np.ndarray):
                for v in emb:
                    embeddings.append(v.tolist())
            else:
                embeddings.extend([list(v) for v in emb])
        ids = [f"{doc_id}_{i}" for i in range(len(pages))]
        ts = time.time()
        metadatas = []
        for i, _ in enumerate(pages):
            md = {"source_doc": doc_id, "page": i, "ingested_at": ts}
            if metadata:
                md.update(metadata)
            metadatas.append(md)
        self.collection.add(documents=pages, embeddings=embeddings, ids=ids, metadatas=metadatas)
        self.client.persist()
        logger.info("Ingested %d chunks for %s", len(pages), doc_id)

    def add_temp_snippets(self, snippets: list[dict], prefix: str = "temp"):
        """
        snippets: [{"snippet": str, "source": str}]
        Adds snippets to collection with metadata temp=True and ts.
        """
        if not snippets:
            return
        docs = [s["snippet"] for s in snippets]
        ids = [f"{prefix}_{int(time.time())}_{i}" for i in range(len(docs))]
        embeddings = []
        for i in range(0, len(docs), self.batch_size):
            batch = docs[i:i+self.batch_size]
            emb = self.embedder.encode(batch, convert_to_numpy=True, show_progress_bar=False)
            if isinstance(emb, np.ndarray):
                for v in emb:
                    embeddings.append(v.tolist())
            else:
                embeddings.extend([list(v) for v in emb])
        ts = time.time()
        metadatas = [{"source": snippets[i].get("source", "web"), "temp": True, "ts": ts} for i in range(len(docs))]
        self.collection.add(documents=docs, embeddings=embeddings, ids=ids, metadatas=metadatas)
        self.client.persist()
        logger.info("Added %d temporary snippets", len(docs))

    def remove_expired_temp(self, ttl_seconds: int):
        """
        Remove documents where metadata.temp == True and now - ts > ttl_seconds.
        This implementation fetches ids in batches and deletes expired ones.
        """
        now = time.time()
        try:
            out = self.collection.get(include=["metadatas"])

            ids = out.get("ids", [])
            metas = out.get("metadatas", [])
            expired = []
            for _id, md in zip(ids, metas):
                if not md:
                    continue
                if md.get("temp") and md.get("ts") and now - float(md.get("ts")) > ttl_seconds:
                    expired.append(_id)
            if expired:
                self.collection.delete(ids=expired)
                self.client.persist()
                logger.info("Deleted %d expired temp docs", len(expired))
        except Exception:
            logger.exception("Failed cleaning temp docs.")

    def query(self, query: str, n_results: int = 4):
        try:
            q_emb = self.embedder.encode([query], convert_to_numpy=True)
            q_vec = q_emb[0].tolist()
        except Exception:
            logger.exception("Embedding error")
            return {"documents": [], "metadatas": [], "ids": []}
        try:
            res = self.collection.query(query_embeddings=[q_vec], n_results=n_results)
        except Exception:
            logger.exception("Chroma query exception")
            return {"documents": [], "metadatas": [], "ids": []}
        docs = res.get("documents", []) if isinstance(res, dict) else getattr(res, "documents", [])
        metas = res.get("metadatas", []) if isinstance(res, dict) else getattr(res, "metadatas", [])
        ids = res.get("ids", []) if isinstance(res, dict) else getattr(res, "ids", [])
        # flatten if nested
        if docs and isinstance(docs[0], list):
            docs = docs[0]
        if metas and isinstance(metas[0], list):
            metas = metas[0]
        if ids and isinstance(ids[0], list):
            ids = ids[0]
        return {"documents": docs or [], "metadatas": metas or [], "ids": ids or []}
