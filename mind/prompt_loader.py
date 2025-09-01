
# mind/prompt_loader.py
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)
PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

REQUIRED = {
    "main_prompt": "Advanced_Prompt.txt",
    "agent_loop": "Advanced_Agent.txt"
}
OPTIONAL = {
    "modules": "Advanced_Modules.txt",
    "tools_json": "tools.json"
}

class PromptLoader:
    def __init__(self):
        self._prompts = {}
        self._loaded = False
        self._load()

    def _load(self):
        if self._loaded:
            return
        # required
        missing = []
        for k, fn in REQUIRED.items():
            p = PROMPT_DIR / fn
            if not p.exists():
                missing.append(fn)
                continue
            self._prompts[k] = p.read_text(encoding="utf-8").strip()
        if missing:
            logger.error("Missing required prompt files: %s", missing)
            raise FileNotFoundError(f"Required prompt files missing: {missing}")

        # optional
        for k, fn in OPTIONAL.items():
            p = PROMPT_DIR / fn
            if not p.exists():
                logger.warning("Optional prompt missing: %s", fn)
                continue
            if p.suffix == ".json":
                try:
                    self._prompts[k] = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    logger.exception("Failed to parse %s", fn)
                    self._prompts[k] = {}
            else:
                self._prompts[k] = p.read_text(encoding="utf-8").strip()
        self._loaded = True

    def get_main_prompt(self) -> str:
        return self._prompts.get("main_prompt", "")

    def get_agent_loop(self) -> str:
        return self._prompts.get("agent_loop", "")

    def get_modules(self) -> str:
        return self._prompts.get("modules", "")

    def get_tools(self) -> dict:
        return self._prompts.get("tools_json", {})

# single global loader
prompt_loader = PromptLoader()
