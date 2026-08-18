import asyncio
import uuid
import time
from typing import Dict, Any, List, Optional, Callable

from backend.config import config
from backend.vision.screen_capture import screen_capturer
from backend.vision.grounder import grounder
from backend.vision.visual_diff import calculate_screen_diff_percentage
from backend.actions.input_controller import input_controller
from backend.actions.window_manager import window_manager
from backend.actions.system_tools import system_tools
from backend.actions.web_tools import web_tools
from backend.core.safety import safety_guard
from backend.core.planner import TaskPlan
from backend.llm import get_llm_provider

# UI action mutex — only one agent can control mouse/keyboard at a time
_ui_mutex = asyncio.Lock()

# Worker name pool
WORKER_NAMES = ["ALPHA", "BRAVO", "CHARLIE", "DELTA", "ECHO"]


class WorkerAgent:
    """Lightweight worker agent for multi-agent orchestration.
    
    Each worker has its own identity, task plan, and execution history.
    Workers share the physical screen/mouse/keyboard via a mutex lock
    for UI actions. Non-UI actions (PowerShell, web) run truly in parallel.
    """
    
    def __init__(self, worker_id: str, worker_name: str):
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
                    "data": {**data, "worker_id": self.worker_id, "worker_name": self.worker_name},
                    "timestamp": time.time()
                }
                res = self.broadcast_callback(msg)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                print(f"[Worker-{self.worker_name}] Broadcast error: {e}")
    
    async def run_task(self, goal: str, task_type: str = "ui_action", dry_run: bool = False) -> Dict[str, Any]:
        """Execute a single subtask. Returns result dict."""
        task_id = f"{self.worker_name}-{str(uuid.uuid4())[:6]}"
        self.is_running = True
        self.current_plan = TaskPlan(goal=goal)
        self.current_plan.status = "running"
        
        await self.broadcast("worker_started", {
            "task_id": task_id,
            "goal": goal,
            "task_type": task_type
        })
        
        history: List[Dict[str, Any]] = []
        step_count = 0
        final_summary = ""
        
        try:
            while self.is_running and step_count < config.MAX_STEPS_PER_TASK:
                # Safety check
                if safety_guard.is_stopped:
                    await self.broadcast("worker_status", {"status": "STOPPED", "reason": "Emergency stop triggered"})
                    self.current_plan.status = "stopped"
                    break
                
                step_count += 1
                await self.broadcast("worker_status", {"status": "OBSERVING", "step": step_count})
                
                # Acquire UI mutex for screen capture (shared resource)
                async with _ui_mutex:
                    before_img = screen_capturer.capture_pil()
                    b64_img, s_w, s_h = screen_capturer.capture_base64_jpeg(max_dim=1280)
                    fg_window = window_manager.get_foreground_window_title()
                    clipboard_snip = system_tools.get_clipboard()
                
                system_ctx = {
                    "foreground_window": fg_window,
                    "clipboard": clipboard_snip
                }
                
                # LLM Reasoning
                await self.broadcast("worker_status", {"status": "REASONING", "step": step_count})
                decision = await self.llm_provider.decide_next_action(
                    goal=goal,
                    history=history,
                    screenshot_base64=b64_img,
                    screen_width=s_w,
                    screen_height=s_h,
                    system_context=system_ctx
                )
                
                thought = decision.get("thought", "Determining next action.")
                action = decision.get("action", "wait")
                params = decision.get("params", {})
                target_label = decision.get("target_label", "")
                box = decision.get("bounding_box", None)
                
                self.current_plan.add_step(thought, action, params, target_label)
                
                await self.broadcast("worker_step", {
                    "step": step_count,
                    "thought": thought,
                    "action": action,
                    "params": params,
                    "target_label": target_label
                })
                
                # Handle finish
                if action == "finish":
                    final_summary = params.get("summary", "Subtask completed.")
                    self.current_plan.status = "completed"
                    await self.broadcast("worker_completed", {
                        "task_id": task_id,
                        "summary": final_summary,
                        "total_steps": step_count
                    })
                    break
                
                if action == "ask_user":
                    question = params.get("question", "Need clarification.")
                    self.current_plan.status = "paused"
                    await self.broadcast("worker_question", {"question": question, "step": step_count})
                    break
                
                # Execute action — UI actions need mutex, non-UI can run freely
                is_ui_action = action in ["click", "double_click", "right_click", "move_to", "type", 
                                          "press_key", "hotkey", "scroll", "drag"]
                
                action_result = None
                
                if is_ui_action:
                    async with _ui_mutex:
                        action_result = await self._execute_action(action, params, dry_run, before_img, box, target_label)
                else:
                    action_result = await self._execute_action(action, params, dry_run, before_img, box, target_label)
                
                # Cooldown
                await asyncio.sleep(config.ACTION_DELAY)
                
                # Post-action diff
                async with _ui_mutex:
                    after_img = screen_capturer.capture_pil()
                diff_pct = calculate_screen_diff_percentage(before_img, after_img)
                
                step_record = {
                    "step": step_count,
                    "thought": thought,
                    "action": action,
                    "params": params,
                    "result": action_result,
                    "screen_diff_pct": diff_pct,
                    "status": "done" if action_result else "failed"
                }
                history.append(step_record)
                
                await self.broadcast("worker_step_done", {
                    "step": step_count,
                    "result": str(action_result)[:100] if action_result else "failed",
                    "screen_diff": diff_pct
                })
        
        except Exception as e:
            print(f"[Worker-{self.worker_name}] Error: {e}")
            self.current_plan.status = "error"
            await self.broadcast("worker_status", {"status": "ERROR", "error": str(e)})
        
        finally:
            self.is_running = False
        
        return {
            "task_id": task_id,
            "worker_id": self.worker_id,
            "worker_name": self.worker_name,
            "goal": goal,
            "status": self.current_plan.status if self.current_plan else "unknown",
            "steps": history,
            "summary": final_summary,
            "total_steps": step_count
        }
    
    async def _execute_action(self, action, params, dry_run, before_img, box, target_label):
        """Execute a single action. Extracted to keep run_task clean."""
        action_result = None
        
        if action in ["click", "double_click", "right_click", "move_to"]:
            norm_x = params.get("x", 500)
            norm_y = params.get("y", 500)
            px, py = grounder.norm_to_pixel(norm_x, norm_y)
            
            if safety_guard.check_corner_failsafe(px, py):
                return None
            
            if not dry_run:
                if action == "click":
                    action_result = input_controller.click(px, py)
                elif action == "double_click":
                    action_result = input_controller.double_click(px, py)
                elif action == "right_click":
                    action_result = input_controller.right_click(px, py)
                elif action == "move_to":
                    action_result = input_controller.move_to(px, py)
            else:
                action_result = True
        
        elif action == "type":
            text = params.get("text", "")
            if not dry_run:
                action_result = input_controller.type_text(text)
                if params.get("press_enter", False):
                    input_controller.press_key("enter")
            else:
                action_result = True
        
        elif action == "press_key":
            key = params.get("key", "enter")
            if not dry_run:
                action_result = input_controller.press_key(key)
            else:
                action_result = True
        
        elif action == "hotkey":
            keys = params.get("keys", [])
            if not dry_run:
                action_result = input_controller.hotkey(*keys)
            else:
                action_result = True
        
        elif action == "scroll":
            amount = params.get("amount", -200)
            norm_x = params.get("x", None)
            norm_y = params.get("y", None)
            px, py = grounder.norm_to_pixel(norm_x, norm_y) if norm_x is not None else (None, None)
            if not dry_run:
                action_result = input_controller.scroll(amount, px, py)
            else:
                action_result = True
        
        elif action == "drag":
            sx, sy = grounder.norm_to_pixel(params.get("start_x", 0), params.get("start_y", 0))
            ex, ey = grounder.norm_to_pixel(params.get("end_x", 0), params.get("end_y", 0))
            if not dry_run:
                action_result = input_controller.drag(sx, sy, ex, ey)
            else:
                action_result = True
        
        elif action == "launch_app":
            app_name = params.get("app_name", "")
            if not dry_run:
                action_result = system_tools.launch_app(app_name)
            else:
                action_result = {"status": "dry_run", "app": app_name}
            await asyncio.sleep(1.0)
        
        elif action == "run_command":
            cmd = params.get("command", "")
            if not dry_run:
                action_result = system_tools.run_powershell(cmd)
            else:
                action_result = {"status": "dry_run", "command": cmd}
        
        elif action == "open_url":
            url = params.get("url", "")
            if not dry_run:
                action_result = web_tools.open_url_in_browser(url)
            else:
                action_result = {"status": "dry_run", "url": url}
            await asyncio.sleep(1.0)
        
        elif action == "wait":
            secs = float(params.get("seconds", 1.0))
            await asyncio.sleep(secs)
            action_result = True
        
        return action_result
