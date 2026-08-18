import asyncio
import time
import uuid
from typing import Dict, Any, List, Optional, Callable
from PIL import Image

from backend.config import config
from backend.vision.screen_capture import screen_capturer
from backend.vision.grounder import grounder
from backend.vision.visual_diff import calculate_screen_diff_percentage
from backend.actions.input_controller import input_controller
from backend.actions.window_manager import window_manager
from backend.actions.system_tools import system_tools
from backend.actions.web_tools import web_tools
from backend.core.safety import safety_guard
from backend.core.memory import memory_store
from backend.core.planner import TaskPlan
from backend.llm import get_llm_provider
from backend.voice.tts import voice_synthesizer
from backend.voice.interrupter import voice_interrupter

class AetherAgent:
    def __init__(self):
        self.is_running = False
        self.current_plan: Optional[TaskPlan] = None
        self.broadcast_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
        self.llm_provider = get_llm_provider()
        self.dry_run = False
        self.voice_feedback = True

    def set_broadcaster(self, cb: Callable[[Dict[str, Any]], Any]):
        self.broadcast_callback = cb

    def set_llm_config(self, provider_name: str, api_key: str = "", model: str = ""):
        self.llm_provider = get_llm_provider(provider_name, api_key, model)

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        if self.broadcast_callback:
            try:
                msg = {"event": event_type, "data": data, "timestamp": time.time()}
                res = self.broadcast_callback(msg)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                print(f"[AetherAgent] Broadcast error: {e}")

    async def stop(self, reason: str = "User stopped agent"):
        safety_guard.trigger_emergency_stop(reason)
        self.is_running = False
        if self.current_plan:
            self.current_plan.status = "stopped"
        await self.broadcast("agent_status", {"status": "STOPPED", "reason": reason})

    async def pause(self):
        safety_guard.pause()
        await self.broadcast("agent_status", {"status": "PAUSED"})

    async def resume(self):
        safety_guard.resume()
        await self.broadcast("agent_status", {"status": "RUNNING"})

    async def run_task(self, goal: str, dry_run: bool = False, voice_enabled: bool = True) -> Dict[str, Any]:
        """Main Autonomous Execution Loop."""
        task_id = str(uuid.uuid4())[:8]
        self.is_running = True
        self.dry_run = dry_run
        self.voice_feedback = voice_enabled
        safety_guard.reset()
        
        self.current_plan = TaskPlan(goal=goal)
        self.current_plan.status = "running"

        await self.broadcast("task_started", {
            "task_id": task_id,
            "goal": goal,
            "dry_run": dry_run
        })
        await self.broadcast("agent_status", {"status": "PLANNING", "thought": "Analyzing screen and formulating initial step..."})

        # Voice acknowledge
        if self.voice_feedback:
            ack_speech = await voice_synthesizer.generate_speech_base64(f"Starting task: {goal[:60]}")
            if ack_speech:
                await self.broadcast("voice_audio", {"audio": ack_speech, "text": f"Starting task: {goal}"})

        # Start non-blocking voice interruption listener
        voice_interrupter.start(on_interrupt=lambda text: asyncio.create_task(self.stop(reason=f"Voice interruption: '{text}'")))

        history: List[Dict[str, Any]] = []
        step_count = 0
        final_summary = ""

        try:
            while self.is_running and step_count < config.MAX_STEPS_PER_TASK:
                # 1. Safety check
                can_continue, msg = safety_guard.check_safe_to_continue(step_count)
                if not can_continue:
                    await self.stop(reason=msg)
                    break

                step_count += 1
                await self.broadcast("agent_status", {"status": "OBSERVING", "step": step_count})

                # 2. Capture Screen
                before_img = screen_capturer.capture_pil()
                b64_img, s_w, s_h = screen_capturer.capture_base64_jpeg(max_dim=1280)
                
                # Gather OS Context
                fg_window = window_manager.get_foreground_window_title()
                clipboard_snip = system_tools.get_clipboard()
                system_ctx = {
                    "foreground_window": fg_window,
                    "clipboard": clipboard_snip
                }

                # 3. LLM Reasoning Step
                await self.broadcast("agent_status", {"status": "REASONING", "step": step_count})
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

                # Record plan step
                current_step_obj = self.current_plan.add_step(thought, action, params, target_label)
                
                await self.broadcast("step_decision", {
                    "step": step_count,
                    "thought": thought,
                    "action": action,
                    "params": params,
                    "target_label": target_label
                })

                # Handle Termination Actions
                if action == "finish":
                    final_summary = params.get("summary", "Goal successfully accomplished.")
                    self.current_plan.status = "completed"
                    current_step_obj["status"] = "success"
                    
                    await self.broadcast("task_completed", {
                        "task_id": task_id,
                        "summary": final_summary,
                        "total_steps": step_count
                    })
                    
                    if self.voice_feedback:
                        speech = await voice_synthesizer.generate_speech_base64(final_summary)
                        if speech:
                            await self.broadcast("voice_audio", {"audio": speech, "text": final_summary})
                    break

                if action == "ask_user":
                    question = params.get("question", "I need clarification on the current state.")
                    self.current_plan.status = "paused"
                    await self.broadcast("agent_question", {"question": question, "step": step_count})
                    if self.voice_feedback:
                        speech = await voice_synthesizer.generate_speech_base64(question)
                        if speech:
                            await self.broadcast("voice_audio", {"audio": speech, "text": question})
                    break

                # 4. Action Execution with Visual Annotation
                await self.broadcast("agent_status", {"status": "EXECUTING", "step": step_count})
                action_result = None
                annotated_b64 = None

                # Coordinate-based Actions
                if action in ["click", "double_click", "right_click", "move_to"]:
                    norm_x = params.get("x", 500)
                    norm_y = params.get("y", 500)
                    px, py = grounder.norm_to_pixel(norm_x, norm_y)

                    # Annotate screenshot for visual ticker
                    annotated_b64 = grounder.annotate_action(
                        image=before_img,
                        action_type=action,
                        target_x=px,
                        target_y=py,
                        box=box,
                        label=target_label
                    )

                    await self.broadcast("screen_annotation", {
                        "image": annotated_b64,
                        "action": action,
                        "x": px,
                        "y": py,
                        "label": target_label
                    })

                    # Safety check corner
                    if safety_guard.check_corner_failsafe(px, py):
                        break

                    if not self.dry_run:
                        if action == "click":
                            action_result = input_controller.click(px, py)
                        elif action == "double_click":
                            action_result = input_controller.double_click(px, py)
                        elif action == "right_click":
                            action_result = input_controller.right_click(px, py)
                        elif action == "move_to":
                            action_result = input_controller.move_to(px, py)
                    else:
                        action_result = True  # Simulated in dry-run

                elif action == "type":
                    text = params.get("text", "")
                    if not self.dry_run:
                        action_result = input_controller.type_text(text)
                        if params.get("press_enter", False):
                            input_controller.press_key("enter")
                    else:
                        action_result = True

                elif action == "press_key":
                    key = params.get("key", "enter")
                    if not self.dry_run:
                        action_result = input_controller.press_key(key)
                    else:
                        action_result = True

                elif action == "hotkey":
                    keys = params.get("keys", [])
                    if not self.dry_run:
                        action_result = input_controller.hotkey(*keys)
                    else:
                        action_result = True

                elif action == "scroll":
                    amount = params.get("amount", -200)
                    norm_x = params.get("x", None)
                    norm_y = params.get("y", None)
                    px, py = grounder.norm_to_pixel(norm_x, norm_y) if norm_x is not None else (None, None)
                    if not self.dry_run:
                        action_result = input_controller.scroll(amount, px, py)
                    else:
                        action_result = True

                elif action == "drag":
                    sx, sy = grounder.norm_to_pixel(params.get("start_x", 0), params.get("start_y", 0))
                    ex, ey = grounder.norm_to_pixel(params.get("end_x", 0), params.get("end_y", 0))
                    if not self.dry_run:
                        action_result = input_controller.drag(sx, sy, ex, ey)
                    else:
                        action_result = True

                elif action == "launch_app":
                    app_name = params.get("app_name", "")
                    if not self.dry_run:
                        action_result = system_tools.launch_app(app_name)
                    else:
                        action_result = {"status": "dry_run", "app": app_name}
                    time.sleep(1.0)  # Give app time to pop up

                elif action == "run_command":
                    cmd = params.get("command", "")
                    if not self.dry_run:
                        action_result = system_tools.run_powershell(cmd)
                    else:
                        action_result = {"status": "dry_run", "command": cmd}

                elif action == "open_url":
                    url = params.get("url", "")
                    if not self.dry_run:
                        action_result = web_tools.open_url_in_browser(url)
                    else:
                        action_result = {"status": "dry_run", "url": url}
                    time.sleep(1.0)

                elif action == "wait":
                    secs = float(params.get("seconds", 1.0))
                    await asyncio.sleep(secs)
                    action_result = True

                # Small cooldown
                await asyncio.sleep(config.ACTION_DELAY)

                # 5. Post-Action Verification & Visual Diff
                after_img = screen_capturer.capture_pil()
                diff_pct = calculate_screen_diff_percentage(before_img, after_img)
                
                # Mark step completed
                self.current_plan.mark_step_done(step_count - 1, action_result, annotated_b64)
                
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

                await self.broadcast("step_executed", {
                    "step": step_count,
                    "result": action_result,
                    "screen_diff": diff_pct
                })

        except Exception as e:
            print(f"[AetherAgent] Error during task execution: {e}")
            self.current_plan.status = "error"
            await self.broadcast("agent_status", {"status": "ERROR", "error": str(e)})

        finally:
            voice_interrupter.stop()
            self.is_running = False
            # Save task to episodic memory
            memory_store.save_task_history(
                task_id=task_id,
                goal=goal,
                status=self.current_plan.status if self.current_plan else "unknown",
                steps=history,
                summary=final_summary
            )

        return {
            "task_id": task_id,
            "status": self.current_plan.status if self.current_plan else "done",
            "steps": history,
            "summary": final_summary
        }

aether_agent = AetherAgent()
