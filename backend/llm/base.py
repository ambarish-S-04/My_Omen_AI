from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from PIL import Image

class BaseLLMProvider(ABC):
    @abstractmethod
    async def decide_next_action(
        self,
        goal: str,
        history: List[Dict[str, Any]],
        screenshot_base64: str,
        screen_width: int,
        screen_height: int,
        system_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Receives the task goal, execution history, current screenshot, and OS context.
        Returns a structured action dictionary with:
        {
            "thought": "What I observe and why I'm taking this step",
            "action": "click" | "double_click" | "right_click" | "type" | "hotkey" | "press_key" | "scroll" | "drag" | "launch_app" | "run_command" | "open_url" | "wait" | "finish" | "ask_user",
            "params": { ... },
            "target_coordinate": [x, y] (normalized 0-1000 or absolute),
            "target_label": "Submit Button" / "Search Box",
            "bounding_box": [ymin, xmin, ymax, xmax] (optional)
        }
        """
        pass
