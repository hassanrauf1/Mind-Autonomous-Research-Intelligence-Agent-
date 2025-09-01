# mind/validation.py
import re
import logging
from typing import List, Dict
from mind.rag_pipeline import RAGPipeline
from mind.proof_snapshot import save_text_snapshot, capture_url_screenshot
from config.settings import CONFIDENCE_THRESHOLD

logger = logging.getLogger(__name__)

class MindValidator:
    def __init__(self):
        self.pipeline = RAGPipeline()
        self.threshold = CONFIDENCE_THRESHOLD

    def extract_claims(self, text: str) -> List[str]:
        parts = re.split(r'(?<=[.!?])\s+', text.strip())
        return [p.strip() for p in parts if p.strip()]

    def score_confidence(self, claim: str, evidence: List[Dict]) -> float:
        """
        Simple, conservative scoring:
          - 0 evidence -> 0
          - 1 unique source -> 0.35
          - 2 unique sources -> 0.65
          - 3+ -> 0.95
        """
        if not evidence:
            return 0.0
        sources = {ev.get("source") for ev in evidence if ev.get("source")}
        n = len(sources)
        if n >= 3:
            return 0.95
        if n == 2:
            return 0.65
        if n == 1:
            return 0.35
        return 0.0

    def triangulate(self, claim: str) -> Dict:
        # First try RAGPipeline (uploaded docs)
        res = self.pipeline.run(claim)
        evidence = res.get("evidence", []) if isinstance(res, dict) else []

        # If no evidence found in docs, fall back to web search
        if not evidence:
            from mind.web_search import WebSearcher   # import only when needed
            searcher = WebSearcher()
            res = searcher.search(claim)
            evidence = res.get("evidence", []) if isinstance(res, dict) else []

        snapshot = None
        if evidence:
            try:
                top = evidence[0]
                snapshot = save_text_snapshot(top.get("source", "unknown"), top.get("snippet", ""))
                src = top.get("source", "")
                if isinstance(src, str) and src.startswith("http"):
                    ss = capture_url_screenshot(src, full_page=False)
                    if ss:
                        snapshot = ss
            except Exception:
                logger.exception("Failed creating snapshot")

        verified = bool(evidence)
        return {
            "verified": verified,
            "evidence": evidence,
            "snapshot": snapshot,
            "agent_answer": res.get("answer")
        }

