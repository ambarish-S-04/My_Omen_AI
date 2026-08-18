import ctypes
import time
from typing import List, Dict, Any, Optional

class WindowManager:
    def __init__(self):
        self.user32 = ctypes.windll.user32

    def get_foreground_window_title(self) -> str:
        """Returns the title of the active foreground window."""
        hwnd = self.user32.GetForegroundWindow()
        length = self.user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            self.user32.GetWindowTextW(hwnd, buff, length + 1)
            return buff.value
        return ""

    def list_windows(self) -> List[Dict[str, Any]]:
        """Returns a list of visible top-level windows with their handles and titles."""
        windows = []

        def enum_windows_callback(hwnd, extra):
            if self.user32.IsWindowVisible(hwnd):
                length = self.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    self.user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value
                    if title and title != "Program Manager":
                        windows.append({
                            "hwnd": hwnd,
                            "title": title
                        })
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        self.user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)
        return windows

    def focus_window_by_title(self, query: str) -> bool:
        """Finds the first window matching `query` (case-insensitive) and brings it to the foreground."""
        query = query.lower().strip()
        windows = self.list_windows()
        for win in windows:
            if query in win["title"].lower():
                hwnd = win["hwnd"]
                # If minimized, restore first
                if self.user32.IsIconic(hwnd):
                    self.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                self.user32.SetForegroundWindow(hwnd)
                time.sleep(0.2)
                return True
        return False

    def minimize_window(self, query: Optional[str] = None) -> bool:
        """Minimizes the specified window or foreground window."""
        if query:
            for win in self.list_windows():
                if query.lower() in win["title"].lower():
                    self.user32.ShowWindow(win["hwnd"], 6)  # SW_MINIMIZE
                    return True
            return False
        else:
            hwnd = self.user32.GetForegroundWindow()
            self.user32.ShowWindow(hwnd, 6)
            return True

    def maximize_window(self, query: Optional[str] = None) -> bool:
        """Maximizes the specified window or foreground window."""
        if query:
            for win in self.list_windows():
                if query.lower() in win["title"].lower():
                    self.user32.ShowWindow(win["hwnd"], 3)  # SW_MAXIMIZE
                    return True
            return False
        else:
            hwnd = self.user32.GetForegroundWindow()
            self.user32.ShowWindow(hwnd, 3)
            return True

window_manager = WindowManager()
