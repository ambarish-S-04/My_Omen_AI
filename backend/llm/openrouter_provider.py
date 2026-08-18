import json
import re
import asyncio
import httpx
from typing import Dict, Any, List, Optional
from backend.config import config

OPENROUTER_FALLBACK_MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3.5-lightning:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "google/gemma-4-26b-a4b-it:free",
    "openai/gpt-oss-20b:free",
]

CORTEX_SYSTEM_PROMPT = """You are CORTEX — the orchestration intelligence layer of OMEN, an autonomous desktop AI agent system.

Your job is to analyze a user's request and determine the optimal execution strategy:

### STRATEGY RULES:
1. **SINGLE** — Use when:
   - The task is simple or involves only one application
   - Steps are strictly sequential and depend on each other
   - The user asks a question (chat intent — no agents needed)
   - Example: "Open Notepad and write a poem"

2. **PARALLEL** — Use when:
   - The task involves 2+ INDEPENDENT subtasks that can proceed simultaneously
   - Different applications or workflows that don't depend on each other's output
   - Example: "Open Chrome and search weather, and also open Notepad and write meeting notes"
   - Maximum 3 parallel agents allowed

3. **CHAT** — Use when:
   - The user is asking a question, not requesting a desktop action
   - Example: "What is quantum physics?", "Who are you?"

### OUTPUT FORMAT (strict JSON):
{
  "strategy": "single" | "parallel" | "chat",
  "subtasks": [
    {
      "id": "A",
      "goal": "Clear, actionable goal for this subtask",
      "type": "ui_action" | "command" | "research",
      "depends_on": [],
      "priority": 1
    }
  ],
  "reasoning": "Brief explanation of why this strategy was chosen",
  "estimated_complexity": "low" | "medium" | "high",
  "chat_response": "Only if strategy is chat — your direct answer to the user"
}

### RULES:
- Maximum 3 subtasks for parallel strategy
- Each subtask goal must be self-contained and actionable
- Use "depends_on" to specify task IDs that must complete first (e.g. ["A"] means wait for task A)
- If a subtask depends on another, they CANNOT run in parallel — mark the dependency
- "type" helps the worker agent know what tools to prioritize:
  - "phone_action": Actions on mobile phone (e.g. "on phone...", WhatsApp, mobile apps, SMS, Android)
  - "ui_action": Needs desktop screen vision, mouse, keyboard
  - "command": Can be done via PowerShell/terminal without UI interaction
  - "research": Web search, information gathering
- Return ONLY valid JSON, no markdown fences
"""


class OpenRouterProvider:
    """Dedicated OpenRouter provider for the Cortex orchestrator layer."""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or config.OPENROUTER_API_KEY
        self.base_url = config.OPENROUTER_BASE_URL.rstrip("/")
        self.model = model or config.OPENROUTER_MODEL
    
    async def _post(self, messages: List[Dict[str, Any]], temperature: float = 0.1, 
                    max_tokens: int = 800, json_mode: bool = True) -> Optional[str]:
        """Posts to OpenRouter with multi-model fallback cascade."""
        models_to_try = [self.model] + [m for m in OPENROUTER_FALLBACK_MODELS if m != self.model]
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://omen-agent.local",
            "X-Title": "OMEN Autonomous Agent"
        }
        
        for current_model in models_to_try:
            payload = {
                "model": current_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}
            
            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    res = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload
                    )
                
                if res.status_code == 200:
                    data = res.json()
                    text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    if text:
                        return text
                elif res.status_code in [429, 503, 502]:
                    # Rate limited or temporarily unavailable — try next model
                    await asyncio.sleep(0.5)
                    continue
                elif res.status_code == 404:
                    continue
            except Exception:
                continue
        
        return None
    
    async def analyze_task(self, user_prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Cortex task analysis — decomposes a user prompt into an execution plan.
        Returns structured plan with strategy, subtasks, and reasoning.
        """
        ctx_str = ""
        if context:
            ctx_str = f"\nCurrent Context: Foreground Window = '{context.get('foreground_window', 'Desktop')}'"
        
        messages = [
            {"role": "system", "content": CORTEX_SYSTEM_PROMPT},
            {"role": "user", "content": f"User Request: \"{user_prompt}\"{ctx_str}\n\nAnalyze and output your execution plan as JSON:"}
        ]
        
        raw = await self._post(messages, temperature=0.1, max_tokens=800, json_mode=False)
        
        if not raw:
            # Fallback: treat as single task
            return {
                "strategy": "single",
                "subtasks": [{"id": "A", "goal": user_prompt, "type": "ui_action", "depends_on": [], "priority": 1}],
                "reasoning": "Cortex could not be reached. Falling back to single-agent execution.",
                "estimated_complexity": "medium"
            }
        
        try:
            # Strategy 1: Direct parse
            plan = json.loads(raw)
        except json.JSONDecodeError:
            try:
                # Strategy 2: Strip markdown fences
                clean = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
                clean = re.sub(r"\s*```\s*$", "", clean, flags=re.MULTILINE).strip()
                plan = json.loads(clean)
            except json.JSONDecodeError:
                try:
                    # Strategy 3: Extract first JSON object from anywhere in the text
                    match = re.search(r"\{[\s\S]*\}", raw)
                    if match:
                        plan = json.loads(match.group(0))
                    else:
                        raise ValueError("No JSON found")
                except Exception:
                    return {
                        "strategy": "single",
                        "subtasks": [{"id": "A", "goal": user_prompt, "type": "ui_action", "depends_on": [], "priority": 1}],
                        "reasoning": "Failed to parse Cortex response. Falling back to single-agent.",
                        "estimated_complexity": "medium"
                    }
        
        # Enforce max parallel agents cap
        if plan.get("strategy") == "parallel":
            subtasks = plan.get("subtasks", [])
            if len(subtasks) > config.MAX_PARALLEL_AGENTS:
                plan["subtasks"] = subtasks[:config.MAX_PARALLEL_AGENTS]
        
        return plan
    
    async def chat_completion(self, messages: List[Dict[str, Any]], temperature: float = 0.7, 
                               max_tokens: int = 1500) -> Optional[str]:
        """Generic text completion for orchestration reasoning or follow-up questions."""
        return await self._post(messages, temperature=temperature, max_tokens=max_tokens, json_mode=False)
    
    async def synthesize_results(self, original_goal: str, results: List[Dict[str, Any]]) -> str:
        """Synthesizes results from multiple worker agents into a unified summary."""
        results_text = "\n".join([
            f"- Agent {r.get('worker_id', '?')}: Goal=\"{r.get('goal', '?')}\" | Status={r.get('status', '?')} | Summary: {r.get('summary', 'No summary')}"
            for r in results
        ])
        
        messages = [
            {"role": "system", "content": "You are CORTEX. Synthesize the results of multiple worker agents into a clear, concise summary for the user. Be brief (2-3 sentences max)."},
            {"role": "user", "content": f"Original Goal: \"{original_goal}\"\n\nAgent Results:\n{results_text}\n\nSynthesize a unified completion summary:"}
        ]
        
        result = await self._post(messages, temperature=0.3, max_tokens=300, json_mode=False)
        return result or "All subtasks have been processed."


# Singleton
openrouter_provider = OpenRouterProvider()
