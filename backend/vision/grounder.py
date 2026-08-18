from typing import Tuple, Dict, Any, List, Optional
from PIL import Image, ImageDraw, ImageFont
import io
import base64
from backend.vision.screen_capture import screen_capturer

class CoordinateGrounder:
    def __init__(self):
        self.screen_width, self.screen_height = screen_capturer.get_screen_size()

    def update_resolution(self):
        self.screen_width, self.screen_height = screen_capturer.get_screen_size()

    def norm_to_pixel(self, norm_x: float, norm_y: float, scale_range: float = 1000.0) -> Tuple[int, int]:
        """
        Converts normalized coordinates (e.g. 0-1000 or 0.0-1.0) to absolute screen pixels (X, Y).
        """
        self.update_resolution()
        if scale_range == 1.0 or (norm_x <= 1.0 and norm_y <= 1.0 and norm_x > 0 and norm_y > 0):
            pixel_x = int(norm_x * self.screen_width)
            pixel_y = int(norm_y * self.screen_height)
        else:
            pixel_x = int((norm_x / scale_range) * self.screen_width)
            pixel_y = int((norm_y / scale_range) * self.screen_height)
        
        # Clamp within screen bounds
        pixel_x = max(0, min(self.screen_width - 1, pixel_x))
        pixel_y = max(0, min(self.screen_height - 1, pixel_y))
        return pixel_x, pixel_y

    def pixel_to_norm(self, pixel_x: int, pixel_y: int, scale_range: float = 1000.0) -> Tuple[int, int]:
        """
        Converts pixel coordinates to normalized range (0-1000).
        """
        self.update_resolution()
        norm_x = int((pixel_x / self.screen_width) * scale_range)
        norm_y = int((pixel_y / self.screen_height) * scale_range)
        return norm_x, norm_y

    def annotate_action(
        self,
        image: Image.Image,
        action_type: str,
        target_x: int,
        target_y: int,
        box: Optional[List[int]] = None,
        label: str = ""
    ) -> str:
        """
        Draws glowing laser reticle, bounding box, and label on the image.
        Returns base64 data URL for frontend live display.
        """
        annotated = image.copy()
        draw = ImageDraw.Draw(annotated)
        
        # Convert absolute coordinates to current image coordinates
        img_w, img_h = annotated.size
        scale_x = img_w / self.screen_width
        scale_y = img_h / self.screen_height
        
        ix = int(target_x * scale_x)
        iy = int(target_y * scale_y)
        
        # Draw bounding box if present [ymin, xmin, ymax, xmax] or [x, y, w, h]
        if box and len(box) == 4:
            if box[0] <= 1000 and box[2] <= 1000:  # 0-1000 normalized format [ymin, xmin, ymax, xmax]
                by1 = int((box[0] / 1000.0) * img_h)
                bx1 = int((box[1] / 1000.0) * img_w)
                by2 = int((box[2] / 1000.0) * img_h)
                bx2 = int((box[3] / 1000.0) * img_w)
            else:
                bx1 = int(box[0] * scale_x)
                by1 = int(box[1] * scale_y)
                bx2 = int(box[2] * scale_x)
                by2 = int(box[3] * scale_y)
            draw.rectangle([bx1, by1, bx2, by2], outline="#00f3ff", width=3)
        
        # Draw Target Reticle (Cyan + Magenta Cyberpunk Glow)
        radius = 16
        draw.ellipse([ix - radius, iy - radius, ix + radius, iy + radius], outline="#00f3ff", width=2)
        draw.ellipse([ix - 6, iy - 6, ix + 6, iy + 6], fill="#bd00ff")
        draw.line([ix - radius - 8, iy, ix + radius + 8, iy], fill="#00f3ff", width=2)
        draw.line([ix, iy - radius - 8, ix, iy + radius + 8], fill="#00f3ff", width=2)
        
        # Draw Action Label
        tag = f"[{action_type.upper()}] {label}" if label else f"[{action_type.upper()}] ({target_x}, {target_y})"
        draw.rectangle([ix + 18, iy - 12, ix + 18 + len(tag) * 8 + 12, iy + 14], fill="#0d1117", outline="#00ff9d", width=1)
        draw.text((ix + 24, iy - 8), tag, fill="#00ff9d")
        
        buffer = io.BytesIO()
        annotated.save(buffer, format="JPEG", quality=85)
        return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("utf-8")

grounder = CoordinateGrounder()
