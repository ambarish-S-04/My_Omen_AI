import time
import threading
from typing import Callable, Optional
from pynput import keyboard
from backend.vision.screen_capture import screen_capturer
from backend.config import config

class SafetyGuard:
    def __init__(self):
        self.is_paused = False
        self.is_stopped = False
        self._listener = None
        self.emergency_callbacks = []
        self._start_keyboard_listener()

    def _start_keyboard_listener(self):
        def on_press(key):
            try:
                if key == keyboard.Key.esc:
                    print("[SafetyGuard] EMERGENCY ESC KEY DETECTED! Halting execution.")
                    self.trigger_emergency_stop(reason="ESC Key pressed by user")
            except Exception as e:
                print(f"[SafetyGuard] Listener error: {e}")

        try:
            self._listener = keyboard.Listener(on_press=on_press)
            self._listener.daemon = True
            self._listener.start()
        except Exception as e:
            print(f"[SafetyGuard] Could not start global keyboard hook: {e}")

    def register_emergency_callback(self, cb: Callable[[str], None]):
        self.emergency_callbacks.append(cb)

    def trigger_emergency_stop(self, reason: str = "Manual Emergency Stop"):
        self.is_stopped = True
        self.is_paused = True
        for cb in self.emergency_callbacks:
            try:
                cb(reason)
            except Exception as e:
                print(f"[SafetyGuard] Error in emergency callback: {e}")

    def reset(self):
        self.is_paused = False
        self.is_stopped = False

    def pause(self):
        self.is_paused = True

    def resume(self):
        self.is_paused = False

    def check_corner_failsafe(self, x: int, y: int) -> bool:
        """Returns True if the coordinate is near any screen corner (within 4 pixels)."""
        w, h = screen_capturer.get_screen_size()
        margin = 4
        in_corner = (
            (x <= margin and y <= margin) or
            (x >= w - margin and y <= margin) or
            (x <= margin and y >= h - margin) or
            (x >= w - margin and y >= h - margin)
        )
        if in_corner:
            self.trigger_emergency_stop(reason="Cursor in screen corner fail-safe zone")
            return True
        return False

    def check_safe_to_continue(self, current_step: int, max_steps: Optional[int] = None) -> tuple[bool, str]:
        limit = max_steps or config.MAX_STEPS_PER_TASK
        if self.is_stopped:
            return False, "Agent stopped by emergency trigger."
        if self.is_paused:
            return False, "Agent is currently paused."
        if current_step >= limit:
            return False, f"Maximum steps limit ({limit}) reached."
        return True, "OK"

safety_guard = SafetyGuard()
