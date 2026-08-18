import json
import re
import httpx
from typing import Dict, Any, List, Optional
from backend.config import config
from backend.llm.base import BaseLLMProvider
from backend.llm.gemini_provider import SYSTEM_PROMPT

class OpenAICompatProvider(BaseLLMProvider):
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or config.OPENAI_API_KEY
        self.base_url = base_url or config.OPENAI_BASE_URL
        self.model = model or config.OPENAI_MODEL

    async def decide_next_action(
        self,
        goal: str,
        history: List[Dict[str, Any]],
        screenshot_base64: str,
        screen_width: int,
        screen_height: int,
        system_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        history_summary = "\n".join([
            f"Step {h.get('step', i+1)}: Action={h.get('action')} | Thought={h.get('thought')}"
            for i, h in enumerate(history[-5:])
        ]) if history else "Step 1"

        user_prompt = f"""Current Goal: "{goal}"
Screen Resolution: {screen_width}x{screen_height}
Foreground Window: "{system_context.get('foreground_window', 'Unknown')}"

Recent History:
{history_summary}

Determine the single next action. Output strictly valid JSON."""

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{screenshot_base64}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(url, headers=headers, json=payload)

            if res.status_code != 200:
                return {
                    "thought": f"API Error {res.status_code}: {res.text[:200]}",
                    "action": "ask_user",
                    "params": {"question": f"API error: {res.text[:200]}"}
                }

            data = res.json()
            raw_text = data["choices"][0]["message"]["content"].strip()
            return json.loads(raw_text)

        except Exception as e:
            return {
                "thought": f"OpenAI Provider Error: {str(e)}",
                "action": "ask_user",
                "params": {"question": f"Error: {str(e)}"}
            }
