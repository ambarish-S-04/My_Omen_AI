import asyncio
import uuid
import time
from typing import Dict, Any, List, Optional, Callable
from PIL import Image

from backend.config import config
from backend.actions.phone_controller import phone_controller
from backend.core.safety import safety_guard
from backend.core.planner import TaskPlan
from backend.llm import get_llm_provider

PHONE_SYSTEM_PROMPT = """You are OMEN in AUTONOMOUS ANDROID PHONE CONTROL mode.
Your goal is to accomplish the user's mobile request by observing the phone screen and taking precise, grounded actions.

### COORDINATE SYSTEM:
All coordinates MUST be normalized in the range [0, 1000] for both X and Y.
- (0, 0) is top-left of the phone screen.
- (1000, 1000) is bottom-right of the phone screen.
- (500, 500) is the exact center.

### AVAILABLE ACTIONS ON PHONE:
1. `tap`: Single tap on UI element. params: {"x": norm_x, "y": norm_y}
2. `swipe`: Swipe/drag on phone. params: {"start_x": norm_x, "start_y": norm_y, "end_x": norm_x, "end_y": norm_y, "duration_ms": 300}
3. `scroll`: Scroll screen. params: {"direction": "down" | "up", "amount_norm": 400}
4. `type`: Type text into active input field. params: {"text": "string to type", "press_enter": true/false}
5. `press_key`: Press phone button ('home', 'back', 'enter', 'power', 'volume_up', 'volume_down', 'app_switch'). params: {"key": "home"}
6. `launch_app`: Launch app directly. params: {"app_name": "whatsapp" | "spotify" | "youtube" | "instagram" | "chrome" | "camera" | "settings" | "maps" | "messages" | "dialer"}
7. `open_url`: Open URL in phone browser. params: {"url": "https://..."}
8. `wait`: Wait for app loading. params: {"seconds": 1.5}
9. `finish`: Goal completely accomplished on phone. params: {"summary": "Detailed summary of what was completed on the phone"}
10. `ask_user`: Need clarification. params: {"question": "Question text"}

### RULES:
1. If the screen is off or on lockscreen, tap/swipe up or use launch_app to open the target application directly.
2. If an app can be launched directly (e.g. WhatsApp, Spotify), use `launch_app` first.
3. Formulate concise reasoning in `thought`.
4. If goal is achieved, output `finish` immediately.
5. Return ONLY valid JSON.
"""


class PhoneWorker:
    """Autonomous Worker Agent specialized for Android Phone automation via ADB/Wireless/Hotspot."""

    def __init__(self, worker_id: str = "PHONE", worker_name: str = "PHONE"):
        self.worker_id = worker_id
        self.worker_name = worker_name
        self.is_running = False
        self.current_plan: Optional[TaskPlan] = None
        self.llm_provider = get_llm_provider()
        self.broadcast_callback: Optional[Callable[[Dict[str, Any]], Any]] = None

    def set_broadcaster(self, cb: Callable[[Dict[str, Any]], Any]):
        self.broadcast_callback = cb

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        if self.broadcast_callback:
            try:
                msg = {
                    "event": event_type,
                    "data": {**data, "worker_id": self.worker_id, "worker_name": self.worker_name, "device": "Android Phone"},
                    "timestamp": time.time()
                }
                res = self.broadcast_callback(msg)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                print(f"[PhoneWorker] Broadcast error: {e}")

    async def run_task(self, goal: str, dry_run: bool = False) -> Dict[str, Any]:
        """Runs autonomous mobile ReAct control loop on Android phone."""
        task_id = f"PHONE-{str(uuid.uuid4())[:6]}"
        self.is_running = True
        self.current_plan = TaskPlan(goal=goal)
        self.current_plan.status = "running"

        # Check phone connection
        devices = phone_controller.get_connected_devices()
        if not devices:
            # Attempt auto hotspot connect
            hotspot_res = phone_controller.connect_wireless()
            if hotspot_res.get("status") != "connected":
                err_msg = "No Android phone connected via USB or Hotspot/Wireless ADB. Please enable USB/Wireless Debugging."
                await self.broadcast("worker_status", {"status": "ERROR", "error": err_msg})
                self.current_plan.status = "error"
                return {
                    "task_id": task_id,
                    "worker_name": "PHONE",
                    "goal": goal,
                    "status": "error",
                    "summary": err_msg,
                    "steps": []
                }

        await self.broadcast("worker_started", {
            "task_id": task_id,
            "goal": goal,
            "task_type": "phone_action"
        })

        # Wake phone screen
        phone_controller.wake_and_unlock()

        history: List[Dict[str, Any]] = []
        step_count = 0
        final_summary = ""

        try:
            while self.is_running and step_count < config.MAX_STEPS_PER_TASK:
                if safety_guard.is_stopped:
                    await self.broadcast("worker_status", {"status": "STOPPED", "reason": "Emergency stop triggered"})
                    self.current_plan.status = "stopped"
                    break

                step_count += 1
                await self.broadcast("worker_status", {"status": "OBSERVING", "step": step_count})

                # Capture phone screen
                b64_img, s_w, s_h = phone_controller.capture_screen_base64(max_dim=1280)
                if not b64_img:
                    # Retry once after 0.5s
                    await asyncio.sleep(0.5)
                    b64_img, s_w, s_h = phone_controller.capture_screen_base64(max_dim=1280)

                if not b64_img:
                    await self.broadcast("worker_status", {"status": "ERROR", "error": "Could not capture phone screen frame via ADB."})
                    break

                # Gather Battery and Device context
                battery = phone_controller.get_battery_status()
                phone_ctx = {
                    "foreground_window": "Android Screen",
                    "device": "Android Phone",
                    "battery": f"{battery.get('battery_percent')}%",
                    "charging": battery.get('is_charging')
                }

                # Multimodal Reasoning Step
                await self.broadcast("worker_status", {"status": "REASONING", "step": step_count})
                
                decision = await self.llm_provider.decide_next_action(
                    goal=goal,
                    history=history,
                    screenshot_base64=b64_img,
                    screen_width=s_w,
                    screen_height=s_h,
                    system_context=phone_ctx
                )

                thought = decision.get("thought", "Analyzing phone screen.")
                action = decision.get("action", "wait")
                params = decision.get("params", {})
                target_label = decision.get("target_label", "")

                self.current_plan.add_step(thought, action, params, target_label)

                await self.broadcast("worker_step", {
                    "step": step_count,
                    "thought": thought,
                    "action": action,
                    "params": params,
                    "target_label": target_label
                })

                if action == "finish":
                    final_summary = params.get("summary", "Phone action accomplished.")
                    self.current_plan.status = "completed"
                    await self.broadcast("worker_completed", {
                        "task_id": task_id,
                        "summary": final_summary,
                        "total_steps": step_count
                    })
                    break

                if action == "ask_user":
                    question = params.get("question", "Clarification needed on phone.")
                    self.current_plan.status = "paused"
                    await self.broadcast("worker_question", {"question": question, "step": step_count})
                    break

                # Execute phone action
                action_result = True
                if not dry_run:
                    if action == "tap":
                        norm_x = params.get("x", 500)
                        norm_y = params.get("y", 500)
                        action_result = phone_controller.tap(norm_x, norm_y)

                    elif action == "swipe":
                        sx = params.get("start_x", 500)
                        sy = params.get("start_y", 700)
                        ex = params.get("end_x", 500)
                        ey = params.get("end_y", 300)
                        dur = int(params.get("duration_ms", 300))
                        action_result = phone_controller.swipe(sx, sy, ex, ey, dur)

                    elif action == "scroll":
                        direction = params.get("direction", "down")
                        amount = float(params.get("amount_norm", 400))
                        action_result = phone_controller.scroll(direction, amount)

                    elif action == "type":
                        text = params.get("text", "")
                        press_enter = params.get("press_enter", False)
                        action_result = phone_controller.type_text(text, press_enter)

                    elif action == "press_key":
                        key = params.get("key", "home")
                        action_result = phone_controller.press_key(key)

                    elif action == "launch_app":
                        app_name = params.get("app_name", "")
                        action_result = phone_controller.launch_app(app_name)
                        await asyncio.sleep(1.2)  # App startup grace period

                    elif action == "open_url":
                        url = params.get("url", "")
                        action_result = phone_controller.open_url(url)
                        await asyncio.sleep(1.0)

                    elif action == "wait":
                        secs = float(params.get("seconds", 1.0))
                        await asyncio.sleep(secs)
                        action_result = True

                await asyncio.sleep(config.ACTION_DELAY)

                step_record = {
                    "step": step_count,
                    "thought": thought,
                    "action": action,
                    "params": params,
                    "result": str(action_result),
                    "status": "done"
                }
                history.append(step_record)

                await self.broadcast("worker_step_done", {
                    "step": step_count,
                    "result": str(action_result)[:100]
                })

        except Exception as e:
            print(f"[PhoneWorker] Error during mobile execution: {e}")
            self.current_plan.status = "error"
            await self.broadcast("worker_status", {"status": "ERROR", "error": str(e)})

        finally:
            self.is_running = False

        return {
            "task_id": task_id,
            "worker_name": "PHONE",
            "goal": goal,
            "status": self.current_plan.status if self.current_plan else "unknown",
            "steps": history,
            "summary": final_summary,
            "total_steps": step_count
        }


# Singleton instance
phone_worker = PhoneWorker()
