import logging
from typing import List, Dict
from mind.prompt_loader import prompt_loader
from mind.web_search import WebSearcher
from mind.proof_snapshot import save_text_snapshot as save_text_snap, capture_url_screenshot
from mind.chroma_manager import CHROMADB_AVAILABLE, ChromaManager
from config.settings import RAG_N_RESULTS, EVIDENCE_TTL
import time

logger = logging.getLogger(__name__)

try:
    from ollama import Client as OllamaClient
    OLLAMA_AVAILABLE = True
except Exception:
    OllamaClient = None
    OLLAMA_AVAILABLE = False

class RAGPipeline:
    def __init__(self):
        self.prompts = prompt_loader
        self.chroma = None
        if CHROMADB_AVAILABLE:
            try:
                self.chroma = ChromaManager()
            except Exception:
                logger.exception("Chroma init failed")
                self.chroma = None
        self.ollama = None
        if OLLAMA_AVAILABLE:
            try:
                # Use OLLAMA_HOST via environment or default in client
                self.ollama = OllamaClient()
            except Exception:
                logger.exception("Ollama client init failed")
                self.ollama = None

        try:
            from config.settings import NEWSAPI_KEY
            self.web = WebSearcher(newsapi_key=NEWSAPI_KEY)
        except Exception:
            logger.exception("WebSearcher init failed")
            self.web = None
            
    def _local_evidence(self, query: str) -> List[Dict]:
        if not self.chroma:
            return []
        res = self.chroma.query(query, n_results=RAG_N_RESULTS)
        docs = res.get("documents", []) or []
        metas = res.get("metadatas", []) or []
        ev = []
        for i, d in enumerate(docs):
            m = metas[i] if i < len(metas) else {}
            ev.append({"type": "local", "source": m.get("source_doc") or m.get("source") or "local", "snippet": d, "meta": m})
        return ev

    def _web_evidence(self, query: str) -> List[Dict]:
        if not self.web:
            return []

        import asyncio
        results = []
        try:
            loop = asyncio.get_event_loop()
            search_res = loop.run_until_complete(self.web.combined_search(query))

            dd = search_res.get("duckduckgo", [])
            wp = [{"snippet": search_res.get("wikipedia"), "title": "Wikipedia"}] if search_res.get("wikipedia") else []
            nw = [{"snippet": n.get("description"), "link": n.get("url")} for n in search_res.get("news", [])]

            for item in dd + wp + nw:
                if item and item.get("snippet"):
                    results.append({
                        "type": "web",
                        "source": item.get("link") or item.get("title") or "web",
                        "snippet": item.get("snippet")
                    })
        except Exception:
            logger.exception("Web evidence fetch failed")

        return results

    def _build_prompt(self, query: str, local_snips: List[str], web_snips: List[str]) -> str:
        system = self.prompts.get_main_prompt() or ""
        agent_loop = self.prompts.get_agent_loop() or ""
        parts = [system]
        if local_snips:
            parts.append("\n\n[Local Knowledge]\n" + "\n---\n".join(local_snips))
        if web_snips:
            parts.append("\n\n[Web Knowledge]\n" + "\n---\n".join(web_snips))
        parts.append(f"\n\n[User Query]\n{query}")
        parts.append("\n\n[Instructions]\n" + agent_loop)
        return "\n\n".join([p.strip() for p in parts if p])

    def _generate(self, prompt: str, temperature: float = 0.2) -> str:
        if self.ollama:
            try:
                resp = self.ollama.generate(model=None, prompt=prompt, options={"temperature": temperature})
                if isinstance(resp, dict):
                    return resp.get("response") or resp.get("text") or str(resp)
                return getattr(resp, "response", str(resp))
            except Exception:
                logger.exception("Ollama generation failed")
                return ""
        return ""

    def run(self, query: str) -> Dict:
        evidence: List[Dict] = []
        # 1. Local-first
        local = self._local_evidence(query)
        if local:
            evidence.extend(local)

        # 2. If no local or local not deep, do web
        if not evidence:
            web = self._web_evidence(query)
            evidence.extend(web)
            # ingest web snippets as temp into chroma for ttl
            if self.chroma and web:
                try:
                    snippets = [{"snippet": w["snippet"], "source": w["source"]} for w in web]
                    self.chroma.add_temp_snippets(snippets, prefix="temp")
                except Exception:
                    logger.exception("Failed to ingest temp snippets")
            # save snapshots (text + screenshot attempts)
            for ev in web:
                try:
                    save_path = save_text_snap(ev.get("source", "web"), ev.get("snippet", ""))
                    # try screenshot (non-fatal)
                    if isinstance(ev.get("source", ""), str) and ev.get("source", "").startswith("http"):
                        try:
                            capture_url_screenshot(ev.get("source", ""), full_page=False)
                        except Exception:
                            pass
                except Exception:
                    logger.exception("Failed saving snapshot")

        # 3. If still no evidence -> try model-only answer
        if not evidence:
            prompt = self._build_prompt(query, [], [])
            gen = self._generate(prompt)
            if gen:
                return {"answer": gen.strip(), "evidence": []}
            return {"answer": "No relevant knowledge found", "evidence": []}

        # 4. Build final prompt with top snippets (limit to keep prompt small)
        local_snips = [e["snippet"] for e in evidence if e["type"] == "local"][:6]
        web_snips = [e["snippet"] for e in evidence if e["type"] == "web"][:8]
        final_prompt = self._build_prompt(query, local_snips, web_snips)
        answer = self._generate(final_prompt)
        if not answer:
            # fallback: merge snippets
            merged = "\n\n".join((local_snips + web_snips)[:8])
            fallback = f"Based on these sources:\n{merged}\n\nUnable to access LLM for final synthesis."
            return {"answer": fallback, "evidence": evidence}
        return {"answer": answer.strip(), "evidence": evidence}


