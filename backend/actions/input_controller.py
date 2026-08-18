import time
import pyautogui
from typing import List, Optional, Union
from backend.config import config

# Configure PyAutoGUI safety settings
pyautogui.FAILSAFE = config.FAILSAFE_ENABLED
pyautogui.PAUSE = 0.05

class InputController:
    def __init__(self):
        self.move_duration = config.MOUSE_MOVE_DURATION

    def move_to(self, x: int, y: int, duration: Optional[float] = None) -> bool:
        """Moves cursor smoothly to the specified (x, y) coordinate."""
        try:
            d = self.move_duration if duration is None else duration
            pyautogui.moveTo(x, y, duration=d, tween=pyautogui.easeInOutQuad)
            return True
        except Exception as e:
            print(f"[InputController] Error moving cursor to ({x}, {y}): {e}")
            return False

    def click(self, x: Optional[int] = None, y: Optional[int] = None, button: str = "left", clicks: int = 1) -> bool:
        """Clicks at the current or specified (x, y) coordinate."""
        try:
            if x is not None and y is not None:
                self.move_to(x, y)
                time.sleep(0.05)
            pyautogui.click(button=button, clicks=clicks)
            return True
        except Exception as e:
            print(f"[InputController] Error clicking at ({x}, {y}): {e}")
            return False

    def double_click(self, x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """Performs a double-click."""
        return self.click(x, y, button="left", clicks=2)

    def right_click(self, x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """Performs a right-click."""
        return self.click(x, y, button="right", clicks=1)

    def drag(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.6) -> bool:
        """Drags mouse from (start_x, start_y) to (end_x, end_y)."""
        try:
            self.move_to(start_x, start_y)
            time.sleep(0.1)
            pyautogui.dragTo(end_x, end_y, duration=duration, button="left", tween=pyautogui.easeInOutQuad)
            return True
        except Exception as e:
            print(f"[InputController] Error dragging from ({start_x}, {start_y}) to ({end_x}, {end_y}): {e}")
            return False

    def scroll(self, amount: int, x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """
        Scrolls the mouse wheel.
        Positive amount = scroll up, Negative amount = scroll down.
        """
        try:
            if x is not None and y is not None:
                self.move_to(x, y)
            pyautogui.scroll(amount)
            return True
        except Exception as e:
            print(f"[InputController] Error scrolling: {e}")
            return False

    def type_text(self, text: str, interval: float = 0.02, use_clipboard_for_long: bool = True) -> bool:
        """
        Types the given text.
        For long or multiline text, pastes via clipboard for high reliability and Unicode support.
        """
        try:
            if use_clipboard_for_long and (len(text) > 30 or "\n" in text or any(ord(c) > 127 for c in text)):
                import pyperclip
                pyperclip.copy(text)
                time.sleep(0.05)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.05)
            else:
                pyautogui.write(text, interval=interval)
            return True
        except Exception as e:
            print(f"[InputController] Error typing text: {e}")
            return False

    def press_key(self, key: str) -> bool:
        """Presses a single special key (e.g. 'enter', 'esc', 'tab', 'backspace', 'up', 'down')."""
        try:
            pyautogui.press(key.lower())
            return True
        except Exception as e:
            print(f"[InputController] Error pressing key '{key}': {e}")
            return False

    def hotkey(self, *keys: str) -> bool:
        """Executes a key combo (e.g. ('ctrl', 'c'), ('win', 'r'), ('alt', 'tab'))."""
        try:
            cleaned_keys = [k.lower().strip() for k in keys]
            pyautogui.hotkey(*cleaned_keys)
            return True
        except Exception as e:
            print(f"[InputController] Error executing hotkey {keys}: {e}")
            return False

    def get_cursor_position(self) -> tuple[int, int]:
        """Returns the current cursor (x, y) coordinates."""
        p = pyautogui.position()
        return p.x, p.y

input_controller = InputController()
