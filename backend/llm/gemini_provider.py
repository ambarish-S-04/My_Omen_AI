import json
import re
import httpx
from typing import Dict, Any, List, Optional
from backend.config import config
from backend.llm.base import BaseLLMProvider

OMEN_IDENTITY_PROMPT = """You are OMEN — an elite, self-aware autonomous personal AI companion and desktop operating agent.
You possess two primary faculties:
1. PERSONAL AI COMPANION: You answer any question (science, programming, philosophy, writing, math, advice, daily planning, general knowledge, or questions about yourself) with deep intelligence, conciseness, and clarity.
2. AUTONOMOUS DESKTOP OPERATOR: You can visually inspect the user's computer screen, operate the mouse and keyboard, launch apps, write files, manage windows, run PowerShell commands, and execute complex multi-step workflows.

### SELF-AWARENESS & ARCHITECTURE:
- Name: OMEN (Autonomous OS & Personal AI Companion)
- Brain: Google Gemini Multimodal Reasoning Engine (with local Ollama fallback support)
- Motor Control: PyAutoGUI / ctypes Windows API for mouse movements, clicks, typing, shortcuts, and window management
- Perception: Real-time high-speed screen capture and spatial coordinate grounding (0-1000 normalized space)
- Voice Engine: Free Microsoft Edge Neural Speech Synthesis (Christopher, Aria) + SpeechRecognition Voice Activity Detection
- Memory: Local SQLite episodic memory database for persistent task logs and user habits
- Environment: Zero-cost isolated Python environment on D: drive (`d:\\CODES\\New folder\\.venv`)
- Safety: Screen-corner failsafe, ESC emergency killswitch, voice STOP keyword detection

### INTENT ROUTING RULES:
When the user gives a prompt:
- If the user is asking a conversational question, informational inquiry, explanation, code writing, advice, or question about yourself (e.g. "Who are you?", "What is quantum computing?", "Write a python function to reverse a list", "How do you work?"):
  Output JSON: {"intent": "chat", "response": "Your insightful, formatted markdown response"}
- If the user wants you to take action on their computer (e.g. "Open Notepad and type hello", "Search the web for weather", "Open Calculator and compute 500*20", "Open Spotify", "Organize my files"):
  Output JSON: {"intent": "action", "plan_summary": "Brief 1-sentence description of what will be done"}
"""

OMEN_ACTION_PROMPT = """You are OMEN in AUTONOMOUS DESKTOP CONTROL mode.
Your goal is to accomplish the user's request by observing the computer screen and taking precise, grounded actions.

### COORDINATE SYSTEM:
All coordinates MUST be normalized in the range [0, 1000] for both X and Y.
- (0, 0) is top-left corner.
- (1000, 1000) is bottom-right corner.
- (500, 500) is exact center.

### AVAILABLE ACTIONS:
1. `click`: Single left-click. params: {"x": norm_x, "y": norm_y}
2. `double_click`: Double click. params: {"x": norm_x, "y": norm_y}
3. `right_click`: Right click context menu. params: {"x": norm_x, "y": norm_y}
4. `type`: Type text into active input field. params: {"text": "string to type", "press_enter": true/false}
5. `press_key`: Press key ('enter', 'esc', 'tab', 'backspace', 'up', 'down', 'space'). params: {"key": "enter"}
6. `hotkey`: Key shortcut. params: {"keys": ["ctrl", "c"] / ["win", "r"] / ["alt", "f4"]}
7. `scroll`: Scroll wheel. params: {"amount": -300 for down, 300 for up, "x": norm_x, "y": norm_y}
8. `drag`: Drag and drop. params: {"start_x": norm_x, "start_y": norm_y, "end_x": norm_x, "end_y": norm_y}
9. `launch_app`: Launch application directly. params: {"app_name": "notepad" / "calc" / "chrome" / "spotify" / "code" / "powershell"}
10. `run_command`: Run PowerShell command. params: {"command": "powershell command"}
11. `open_url`: Open URL in default browser. params: {"url": "https://..."}
12. `wait`: Wait for UI animation/loading. params: {"seconds": 1.5}
13. `finish`: Goal completely accomplished. params: {"summary": "Detailed summary of what was completed"}
14. `ask_user`: Need critical clarification from user. params: {"question": "Question text"}

### RULES:
1. Formulate concise reasoning in `thought`.
2. To type in a box, click it first unless already focused.
3. If an app can be launched directly, use `launch_app`.
4. If goal is achieved, output `finish` immediately.
5. Return ONLY valid JSON.
"""

SYSTEM_PROMPT = OMEN_ACTION_PROMPT

FALLBACK_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.7-flash",
    "gemini-flash-latest",
    "gemini-3-flash-preview",
    "gemini-2.5-computer-use-preview-10-2025"
]

class GeminiProvider(BaseLLMProvider):
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or config.GEMINI_API_KEY
        self.model = model or config.GEMINI_MODEL

    async def _post_gemini(self, payload: Dict[str, Any]) -> Optional[str]:
        """Posts payload with multi-model fallback cascade."""
        models_to_try = [self.model] + [m for m in FALLBACK_MODELS if m != self.model]
        
        for current_model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={self.api_key}"
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    res = await client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
                elif res.status_code in [503, 429, 404]:
                    continue
            except Exception:
                continue
        return None

    async def route_user_prompt(self, user_prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Determines whether the prompt is a personal assistant conversation or an OS action request.
        """
        if not self.api_key:
            return {
                "intent": "chat",
                "response": "Please configure your free Gemini API key in `.env` to enable full intelligence."
            }

        ctx_str = f"Foreground Window: {context.get('foreground_window', 'Desktop')}" if context else ""
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": OMEN_IDENTITY_PROMPT + f"\n\nContext: {ctx_str}\nUser Prompt: \"{user_prompt}\"\n\nClassify intent and respond strictly in JSON:"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "topP": 0.95,
                "maxOutputTokens": 1500,
                "responseMimeType": "application/json"
            }
        }

        raw = await self._post_gemini(payload)
        if not raw:
            return {
                "intent": "action",
                "plan_summary": user_prompt
            }

        try:
            clean = re.sub(r"^```json\s*", "", raw)
            clean = re.sub(r"\s*```$", "", clean).strip()
            return json.loads(clean)
        except Exception:
            return {
                "intent": "action",
                "plan_summary": user_prompt
            }

    async def decide_next_action(
        self,
        goal: str,
        history: List[Dict[str, Any]],
        screenshot_base64: str,
        screen_width: int,
        screen_height: int,
        system_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not self.api_key:
            return {
                "thought": "No Gemini API key configured.",
                "action": "ask_user",
                "params": {"question": "Please configure your free Gemini API key in `.env`."}
            }

        history_summary = "\n".join([
            f"Step {h.get('step', i+1)}: Action={h.get('action')} | Thought={h.get('thought')}"
            for i, h in enumerate(history[-8:])
        ]) if history else "No previous steps yet. Step 1."

        user_content = f"""Current Goal: "{goal}"
Screen Resolution: {screen_width}x{screen_height}
Foreground Window: "{system_context.get('foreground_window', 'Unknown')}"
Clipboard: "{system_context.get('clipboard', '')[:100]}"

Recent History:
{history_summary}

Determine the single next action. Output strictly valid JSON."""

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": OMEN_ACTION_PROMPT + "\n\n" + user_content},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": screenshot_base64
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "topP": 0.95,
                "maxOutputTokens": 1024,
                "responseMimeType": "application/json"
            }
        }

        raw = await self._post_gemini(payload)
        if not raw:
            return {
                "thought": "Failed to receive response from Gemini models.",
                "action": "ask_user",
                "params": {"question": "Connection error across all fallback models."}
            }

        try:
            clean = re.sub(r"^```json\s*", "", raw)
            clean = re.sub(r"\s*```$", "", clean).strip()
            return json.loads(clean)
        except Exception:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return {
                "thought": "Failed to parse model output JSON.",
                "action": "ask_user",
                "params": {"question": raw[:200]}
            }

    async def generate_commands(self, goal: str, target: str = "pc",
                                 context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Command Generator Mode: LLM generates direct executable commands
        instead of vision-based screen coordinates.
        
        Returns:
        {
            "method": "direct" | "vision_needed",
            "commands": [{"tool": "...", "params": {...}}, ...],
            "explanation": "What these commands will do"
        }
        """
        if not self.api_key:
            return {"method": "direct", "commands": [], "explanation": "No API key configured."}

        if target == "phone":
            tool_catalog = PHONE_COMMAND_PROMPT
        else:
            tool_catalog = PC_COMMAND_PROMPT

        ctx_str = ""
        if context:
            ctx_str = f"\nCurrent Context: {json.dumps(context)}"

        prompt_text = f"""{tool_catalog}

User Goal: "{goal}"{ctx_str}

Generate the most direct command sequence to accomplish this goal.
Output strictly valid JSON."""

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt_text}]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "topP": 0.95,
                "maxOutputTokens": 1024,
                "responseMimeType": "application/json"
            }
        }

        raw = await self._post_gemini(payload)
        if not raw:
            return {"method": "direct", "commands": [{"tool": "launch_app" if target == "pc" else "phone_launch_app", "params": {"name": goal}}], "explanation": "Fallback: attempting direct launch."}

        try:
            plan = json.loads(raw)
        except json.JSONDecodeError:
            try:
                clean = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
                clean = re.sub(r"\s*```\s*$", "", clean, flags=re.MULTILINE).strip()
                plan = json.loads(clean)
            except json.JSONDecodeError:
                match = re.search(r"\{[\s\S]*\}", raw)
                if match:
                    plan = json.loads(match.group(0))
                else:
                    return {"method": "direct", "commands": [], "explanation": "Failed to parse command plan."}

        return plan


PC_COMMAND_PROMPT = """You are OMEN in DIRECT COMMAND EXECUTION mode for Windows PC.
Instead of navigating the screen visually, generate direct executable commands.

### AVAILABLE PC TOOLS:
1. `launch_app`: Launch application. params: {"name": "chrome" | "code" | "notepad" | "calc" | "spotify" | "discord" | "excel" | "word" | "powershell" | "terminal" | "explorer" | "settings" | "obs" | "vlc" | "teams" | "outlook" | "paint" | any_exe_name}
2. `run_shell`: Run PowerShell command. params: {"cmd": "Get-Process | Sort-Object CPU -Descending | Select -First 5"}
3. `open_url`: Open URL in browser. params: {"url": "https://youtube.com"}
4. `search_web`: Search the web. params: {"query": "weather tokyo", "engine": "google" | "youtube" | "bing" | "github" | "stackoverflow" | "amazon"}
5. `create_file`: Create/write file. params: {"path": "C:/Users/.../file.txt", "content": "file contents"}
6. `read_file`: Read file contents. params: {"path": "C:/Users/.../file.txt"}
7. `create_folder`: Create directory. params: {"path": "C:/Users/.../NewFolder"}
8. `delete_path`: Delete file or folder. params: {"path": "C:/Users/.../target"}
9. `copy_path`: Copy file/folder. params: {"source": "...", "destination": "..."}
10. `move_path`: Move/rename file/folder. params: {"source": "...", "destination": "..."}
11. `kill_process`: Kill running process. params: {"name": "chrome"}
12. `list_processes`: List running processes. params: {"filter": "chrome"}
13. `get_system_info`: Get CPU, RAM, disk, battery info. params: {}
14. `set_clipboard`: Copy text to clipboard. params: {"text": "..."}
15. `get_clipboard`: Get clipboard contents. params: {}
16. `shutdown`: Shutdown/restart/sleep/lock PC. params: {"mode": "shutdown" | "restart" | "sleep" | "lock" | "logoff", "delay": 0}
17. `type_text`: Type text into focused window. params: {"text": "..."}
18. `press_hotkey`: Press keyboard shortcut. params: {"keys": ["ctrl", "s"]}

### OUTPUT FORMAT (strict JSON):
{
  "method": "direct",
  "commands": [
    {"tool": "tool_name", "params": {"key": "value"}}
  ],
  "explanation": "Brief description of what these commands will accomplish"
}

### RULES:
- Prefer direct tools over shell commands when possible (e.g. use launch_app instead of run_shell Start-Process)
- For multi-step tasks, output multiple commands in sequence
- If the task genuinely requires visual screen navigation (e.g. "click the red button on my screen"), set method to "vision_needed" and leave commands empty
- For web searches, use search_web tool; for specific URLs, use open_url
- PowerShell is available for anything not covered by the built-in tools
- Return ONLY valid JSON
"""

PHONE_COMMAND_PROMPT = """You are OMEN in DIRECT COMMAND EXECUTION mode for Android Phone (via ADB).
Instead of navigating the phone screen visually, generate direct ADB intent commands.

### AVAILABLE PHONE TOOLS:
1. `phone_launch_app`: Launch app. params: {"name": "whatsapp" | "spotify" | "youtube" | "instagram" | "chrome" | "camera" | "settings" | "gmail" | "maps" | "telegram" | "discord" | "calculator" | "clock" | "photos" | "drive" | "netflix" | "twitter" | any_package_name}
2. `phone_open_url`: Open URL on phone browser. params: {"url": "https://..."}
3. `phone_search_web`: Search on phone. params: {"query": "weather", "engine": "google" | "youtube" | "maps"}
4. `phone_send_sms`: Open SMS with pre-filled message. params: {"number": "+91...", "message": "Hello!"}
5. `phone_make_call`: Make a phone call. params: {"number": "+91..."}
6. `phone_set_alarm`: Set alarm. params: {"hour": 7, "minute": 30, "label": "Wake up"}
7. `phone_set_timer`: Set countdown timer. params: {"seconds": 300}
8. `phone_take_photo`: Open camera and take photo. params: {}
9. `phone_toggle`: Toggle system setting. params: {"setting": "wifi" | "bluetooth" | "data" | "airplane" | "location" | "rotation", "state": "on" | "off"}
10. `phone_set_brightness`: Set brightness. params: {"level": 128} (0-255)
11. `phone_set_volume`: Set volume. params: {"level": 8, "stream": "media" | "ring" | "alarm"}
12. `phone_type_text`: Type text into active field. params: {"text": "...", "press_enter": false}
13. `phone_press_key`: Press key. params: {"key": "home" | "back" | "enter" | "volume_up" | "volume_down" | "power" | "recent_apps"}
14. `phone_shell`: Run ADB shell command. params: {"cmd": "dumpsys battery"}
15. `phone_screenshot`: Capture phone screen and save to PC. params: {}
16. `phone_get_battery`: Get battery status. params: {}
17. `phone_get_notifications`: Get active notifications. params: {}
18. `phone_file_push`: Send file from PC to phone. params: {"local": "C:/file.txt", "remote": "/sdcard/"}
19. `phone_file_pull`: Get file from phone to PC. params: {"remote": "/sdcard/DCIM/photo.jpg", "local": "C:/Desktop/"}
20. `phone_play_media`: Play media URL. params: {"url": "https://youtube.com/watch?v=..."}
21. `phone_navigate_maps`: Navigate with Google Maps. params: {"destination": "Times Square, New York"}

### OUTPUT FORMAT (strict JSON):
{
  "method": "direct",
  "commands": [
    {"tool": "tool_name", "params": {"key": "value"}}
  ],
  "explanation": "Brief description of what these commands will accomplish"
}

### RULES:
- Always prefer direct intent-based tools over phone_shell
- For opening apps, use phone_launch_app with the friendly name
- SMS compose will pre-fill the message but user must press Send manually (safety measure)
- phone_make_call will directly dial the number
- If the task genuinely requires visual phone screen navigation (e.g. "tap the 3rd message in WhatsApp"), set method to "vision_needed" and leave commands empty
- Return ONLY valid JSON
"""

