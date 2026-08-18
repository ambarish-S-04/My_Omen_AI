import io
import base64
from typing import Tuple, Optional
from PIL import Image, ImageGrab
import mss
from backend.config import config

class ScreenCapturer:
    def __init__(self):
        try:
            self._sct = mss.mss()
            self._monitor = self._sct.monitors[1]
            self.width = self._monitor["width"]
            self.height = self._monitor["height"]
        except Exception:
            self._sct = None
            # Fallback size
            self.width = 1920
            self.height = 1080

    def get_screen_size(self) -> Tuple[int, int]:
        """Returns screen resolution."""
        try:
            img = self.capture_pil()
            self.width, self.height = img.size
        except Exception:
            pass
        return self.width, self.height

    def capture_pil(self) -> Image.Image:
        """Captures full screen as PIL Image (RGB) with robust fallbacks."""
        # 1. Try ImageGrab (standard Windows GDI desktop capture)
        try:
            img = ImageGrab.grab(all_screens=False)
            if img:
                return img.convert("RGB")
        except Exception as e:
            pass

        # 2. Try MSS
        if self._sct:
            try:
                sct_img = self._sct.grab(self._monitor)
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            except Exception:
                pass

        # 3. Fallback dummy placeholder image if running headless
        fallback = Image.new("RGB", (self.width, self.height), color=(15, 20, 30))
        return fallback

    def capture_scaled(self, max_dim: Optional[int] = None) -> Tuple[Image.Image, float, float]:
        if max_dim is None:
            max_dim = config.SCREENSHOT_MAX_DIMENSION

        img = self.capture_pil()
        orig_w, orig_h = img.size

        if max(orig_w, orig_h) <= max_dim:
            return img, 1.0, 1.0

        if orig_w >= orig_h:
            new_w = max_dim
            new_h = int(orig_h * (max_dim / orig_w))
        else:
            new_h = max_dim
            new_w = int(orig_w * (max_dim / orig_h))

        scaled_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        scale_x = orig_w / new_w
        scale_y = orig_h / new_h
        return scaled_img, scale_x, scale_y

    def capture_base64_jpeg(self, max_dim: Optional[int] = None, quality: int = 80) -> Tuple[str, int, int]:
        img, _, _ = self.capture_scaled(max_dim)
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return b64_str, img.width, img.height

    def capture_bytes_jpeg(self, max_dim: Optional[int] = None, quality: int = 80) -> bytes:
        img, _, _ = self.capture_scaled(max_dim)
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        return buffer.getvalue()

screen_capturer = ScreenCapturer()
