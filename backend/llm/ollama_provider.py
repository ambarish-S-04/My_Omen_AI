import json
import re
import httpx
from typing import Dict, Any, List, Optional
from backend.config import config
from backend.llm.base import BaseLLMProvider
from backend.llm.gemini_provider import SYSTEM_PROMPT

class OllamaProvider(BaseLLMProvider):
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = base_url or config.OLLAMA_BASE_URL
        self.model = model or config.OLLAMA_MODEL

    async def decide_next_action(
        self,
        goal: str,
        history: List[Dict[str, Any]],
        screenshot_base64: str,
        screen_width: int,
        screen_height: int,
        system_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/api/generate"
        
        history_summary = "\n".join([
            f"Step {h.get('step', i+1)}: Action={h.get('action')} | Thought={h.get('thought')}"
            for i, h in enumerate(history[-5:])
        ]) if history else "No previous steps yet. Step 1."

        user_content = f"""Current Goal: "{goal}"
Screen Size: {screen_width}x{screen_height}
Foreground Window: "{system_context.get('foreground_window', 'Unknown')}"

Recent Step History:
{history_summary}

Determine the single next action. Output strictly valid JSON."""

        payload = {
            "model": self.model,
            "system": SYSTEM_PROMPT,
            "prompt": user_content,
            "images": [screenshot_base64],
            "stream": False,
            "format": "json"
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(url, json=payload)

            if res.status_code != 200:
                return {
                    "thought": f"Ollama returned error status {res.status_code}",
                    "action": "ask_user",
                    "params": {"question": f"Ollama connection error. Is Ollama running with model '{self.model}'?"}
                }

            data = res.json()
            raw_response = data.get("response", "").strip()
            return json.loads(raw_response)

        except Exception as e:
            return {
                "thought": f"Local Ollama error: {str(e)}",
                "action": "ask_user",
                "params": {"question": f"Cannot reach Ollama at {self.base_url}. Make sure `ollama serve` is running or switch to Gemini in settings."}
            }
