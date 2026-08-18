import os
import re
import subprocess
import io
import base64
import socket
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image

from backend.config import BASE_DIR

# Common Android package aliases
APP_PACKAGE_MAP = {
    "whatsapp": "com.whatsapp",
    "spotify": "com.spotify.music",
    "youtube": "com.google.android.youtube",
    "instagram": "com.instagram.android",
    "chrome": "com.android.chrome",
    "maps": "com.google.android.apps.maps",
    "settings": "com.android.settings",
    "telegram": "org.telegram.messenger",
    "photos": "com.google.android.apps.photos",
    "gallery": "com.google.android.apps.photos",
    "messages": "com.google.android.apps.messaging",
    "sms": "com.google.android.apps.messaging",
    "dialer": "com.google.android.dialer",
    "phone": "com.google.android.dialer",
    "calculator": "com.google.android.calculator",
    "clock": "com.google.android.deskclock",
    "camera": "com.google.android.GoogleCamera",
    "netflix": "com.netflix.ninja",
    "twitter": "com.twitter.android",
    "x": "com.twitter.android",
    "gmail": "com.google.android.gm"
}

# Android Key Code Map
KEY_CODE_MAP = {
    "home": 3,
    "back": 4,
    "call": 5,
    "end_call": 6,
    "volume_up": 24,
    "volume_down": 25,
    "power": 26,
    "camera": 27,
    "clear": 28,
    "enter": 66,
    "backspace": 67,
    "del": 67,
    "tab": 61,
    "space": 62,
    "app_switch": 187,
    "recent_apps": 187,
    "wake": 224,
    "sleep": 223
}


class PhoneController:
    """Controls connected Android mobile devices over USB or Wireless ADB / Hotspot."""

    def __init__(self):
        self.adb_path = self._resolve_adb_path()
        self.selected_device: Optional[str] = None
        self._cached_screen_size: Optional[Tuple[int, int]] = None

    def _resolve_adb_path(self) -> str:
        """Finds standalone adb binary in bin/platform-tools or system PATH."""
        local_adb = BASE_DIR / "bin" / "platform-tools" / "adb.exe"
        if local_adb.exists():
            return str(local_adb)
        
        # Check system PATH
        try:
            res = subprocess.run(["where", "adb"], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip().splitlines()[0]
        except Exception:
            pass

        return "adb"

    def _run_adb(self, args: List[str], timeout: float = 15.0, raw_bytes: bool = False) -> Any:
        """Executes an adb command with the currently selected device prefix if set."""
        cmd = [self.adb_path]
        if self.selected_device:
            cmd.extend(["-s", self.selected_device])
        cmd.extend(args)

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            if raw_bytes:
                return res.stdout
            return res.stdout.decode("utf-8", errors="ignore").strip()
        except Exception as e:
            return b"" if raw_bytes else f"Error: {e}"

    def get_connected_devices(self) -> List[Dict[str, str]]:
        """Returns list of connected Android devices with status."""
        output = self._run_adb(["devices", "-l"])
        devices = []
        if isinstance(output, str):
            lines = output.splitlines()
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    serial = parts[0]
                    state = parts[1]
                    model_match = re.search(r"model:(\S+)", line)
                    model = model_match.group(1) if model_match else "Android Device"
                    conn_type = "Wireless/Hotspot" if ":" in serial else "USB"
                    devices.append({
                        "serial": serial,
                        "state": state,
                        "model": model,
                        "connection": conn_type
                    })
        if devices and not self.selected_device:
            self.selected_device = devices[0]["serial"]
        return devices

    def auto_discover_hotspot_ip(self) -> Optional[str]:
        """Discovers phone's hotspot default gateway IP on active network adapters."""
        try:
            res = subprocess.run(["ipconfig"], capture_output=True, text=True, timeout=5.0)
            if res.returncode == 0:
                gateways = re.findall(r"Default Gateway[ .:]*:\s*([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", res.stdout)
                for gw in gateways:
                    if gw not in ["0.0.0.0", "127.0.0.1"]:
                        return gw
        except Exception:
            pass
        return "192.168.43.1"  # Android standard default hotspot gateway

    def enable_tcpip(self, port: int = 5555) -> Dict[str, Any]:
        """Enables wireless ADB port 5555 over USB connection."""
        res = self._run_adb(["tcpip", str(port)])
        if "restarting in tcp mode" in str(res).lower() or "5555" in str(res):
            return {"status": "success", "message": f"Wireless mode unlocked on port {port}. You can now unplug USB!"}
        return {"status": "result", "output": res}

    def pair_device(self, ip_port: str, pairing_code: str) -> Dict[str, Any]:
        """Pairs with Android 11+ Wireless Debugging code."""
        res = self._run_adb(["pair", ip_port, pairing_code])
        if "successfully paired" in str(res).lower():
            return {"status": "paired", "device": ip_port, "output": res}
        return {"status": "failed", "output": res}

    def connect_wireless(self, ip: Optional[str] = None, port: int = 5555) -> Dict[str, Any]:
        """Connects to Android phone over Wi-Fi / Hotspot."""
        target_ip = ip or self.auto_discover_hotspot_ip()
        if not target_ip:
            return {"status": "error", "message": "Could not determine phone IP."}

        target_addr = f"{target_ip}:{port}" if ":" not in str(target_ip) else str(target_ip)
        res = self._run_adb(["connect", target_addr])
        
        if "connected" in res.lower() and "unable" not in res.lower():
            self.selected_device = target_addr
            return {"status": "connected", "device": target_addr, "output": res}
        else:
            return {"status": "failed", "device": target_addr, "output": res}

    def get_screen_size(self) -> Tuple[int, int]:
        """Returns phone screen resolution (width, height)."""
        if self._cached_screen_size:
            return self._cached_screen_size

        output = self._run_adb(["shell", "wm", "size"])
        match = re.search(r"(\d+)x(\d+)", str(output))
        if match:
            w, h = int(match.group(1)), int(match.group(2))
            self._cached_screen_size = (w, h)
            return (w, h)
        return (1080, 2400)  # Common standard fallback

    def capture_screen_pil(self) -> Optional[Image.Image]:
        """Captures live phone screen directly via ADB in ~100ms."""
        raw = self._run_adb(["exec-out", "screencap", "-p"], raw_bytes=True)
        if not raw or len(raw) < 100:
            return None
        try:
            img = Image.open(io.BytesIO(raw))
            img.load()
            return img
        except Exception:
            return None

    def capture_screen_base64(self, max_dim: int = 1280, quality: int = 80) -> Tuple[Optional[str], int, int]:
        """Captures, downscales, and base64 encodes phone screenshot for Gemini vision."""
        img = self.capture_screen_pil()
        if not img:
            return None, 0, 0

        orig_w, orig_h = img.size
        # Resize if larger than max_dim
        scale = min(max_dim / max(orig_w, orig_h), 1.0)
        if scale < 1.0:
            new_w = int(orig_w * scale)
            new_h = int(orig_h * scale)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Convert RGBA to RGB for JPEG
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return b64, orig_w, orig_h

    def norm_to_pixel(self, norm_x: float, norm_y: float) -> Tuple[int, int]:
        """Converts normalized 0-1000 coordinate to phone screen pixel."""
        w, h = self.get_screen_size()
        px = int(round((max(0, min(1000, norm_x)) / 1000.0) * w))
        py = int(round((max(0, min(1000, norm_y)) / 1000.0) * h))
        return px, py

    def tap(self, norm_x: float, norm_y: float) -> bool:
        """Taps normalized 0-1000 coordinate on phone."""
        px, py = self.norm_to_pixel(norm_x, norm_y)
        res = self._run_adb(["shell", "input", "tap", str(px), str(py)])
        return "error" not in str(res).lower()

    def swipe(self, start_x: float, start_y: float, end_x: float, end_y: float, duration_ms: int = 300) -> bool:
        """Swipes or scrolls on phone screen."""
        sx, sy = self.norm_to_pixel(start_x, start_y)
        ex, ey = self.norm_to_pixel(end_x, end_y)
        res = self._run_adb(["shell", "input", "swipe", str(sx), str(sy), str(ex), str(ey), str(duration_ms)])
        return "error" not in str(res).lower()

    def scroll(self, direction: str = "down", amount_norm: float = 400) -> bool:
        """Scrolls up or down on phone screen."""
        w, h = self.get_screen_size()
        cx = 500
        if direction.lower() in ["down", "scroll_down"]:
            return self.swipe(cx, 700, cx, 700 - amount_norm, duration_ms=250)
        else:
            return self.swipe(cx, 300, cx, 300 + amount_norm, duration_ms=250)

    def type_text(self, text: str, press_enter: bool = False) -> bool:
        """Types text into active input field on phone."""
        if not text:
            return True

        # ADB input text requires spaces to be %s and quotes escaped
        escaped = text.replace(" ", "%s").replace("&", "\\&").replace("'", "\\'").replace('"', '\\"')
        self._run_adb(["shell", "input", "text", escaped])

        if press_enter:
            self.press_key("enter")
        return True

    def press_key(self, key: str) -> bool:
        """Presses physical or navigation key on phone."""
        key_lower = str(key).lower().strip()
        code = KEY_CODE_MAP.get(key_lower, None)
        if code is None:
            try:
                code = int(key)
            except ValueError:
                code = 66  # Default ENTER

        res = self._run_adb(["shell", "input", "keyevent", str(code)])
        return "error" not in str(res).lower()

    def launch_app(self, app_name_or_pkg: str) -> Dict[str, Any]:
        """Launches application on phone by friendly name or package."""
        clean = app_name_or_pkg.lower().strip()
        pkg = APP_PACKAGE_MAP.get(clean, clean)

        # Handle Camera Intent
        if clean in ["camera", "cam", "take photo", "take picture"]:
            res = self._run_adb(["shell", "am", "start", "-a", "android.media.action.STILL_IMAGE_CAMERA"])
            return {"status": "launched", "intent": "STILL_IMAGE_CAMERA", "output": res}

        # Handle Direct Package / Monkey Launch
        res = self._run_adb(["shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"])
        if "events injected" in str(res).lower():
            return {"status": "launched", "package": pkg}
        
        # Fallback to standard am start
        res2 = self._run_adb(["shell", "am", "start", "-n", f"{pkg}/.MainActivity"])
        return {"status": "attempted", "package": pkg, "output": str(res2)}

    def open_url(self, url: str) -> bool:
        """Opens URL in phone's default browser."""
        if not url.startswith("http"):
            url = "https://" + url
        res = self._run_adb(["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url])
        return "error" not in str(res).lower()

    def get_battery_status(self) -> Dict[str, Any]:
        """Returns battery percentage, temperature, status, and health."""
        out = self._run_adb(["shell", "dumpsys", "battery"])
        level_m = re.search(r"level:\s*(\d+)", str(out))
        temp_m = re.search(r"temperature:\s*(\d+)", str(out))
        status_m = re.search(r"status:\s*(\d+)", str(out))
        ac_m = re.search(r"AC powered:\s*(\w+)", str(out))
        usb_m = re.search(r"USB powered:\s*(\w+)", str(out))
        
        level = int(level_m.group(1)) if level_m else None
        temp = (int(temp_m.group(1)) / 10.0) if temp_m else None
        is_charging = (ac_m and ac_m.group(1) == "true") or (usb_m and usb_m.group(1) == "true")

        return {
            "battery_percent": level,
            "temperature_celsius": temp,
            "is_charging": is_charging,
            "raw_status": status_m.group(1) if status_m else "unknown"
        }

    def get_device_summary(self) -> Dict[str, Any]:
        """Returns comprehensive device telemetry (model, brand, battery, resolution, conn)."""
        devices = self.get_connected_devices()
        if not devices:
            return {"connected": False, "message": "No Android device detected. Enable USB/Wireless Debugging."}

        model = self._run_adb(["shell", "getprop", "ro.product.model"])
        brand = self._run_adb(["shell", "getprop", "ro.product.brand"])
        android_ver = self._run_adb(["shell", "getprop", "ro.build.version.release"])
        battery = self.get_battery_status()
        res_w, res_h = self.get_screen_size()

        return {
            "connected": True,
            "device_serial": self.selected_device,
            "model": str(model).strip() or devices[0].get("model"),
            "brand": str(brand).strip().capitalize(),
            "android_version": str(android_ver).strip(),
            "resolution": f"{res_w}x{res_h}",
            "battery_percent": battery.get("battery_percent"),
            "is_charging": battery.get("is_charging"),
            "connection_type": devices[0].get("connection")
        }

    def wake_and_unlock(self):
        """Wakes up phone screen and attempts unlock swipe."""
        self.press_key("wake")
        # Swipe up to reveal lock screen / home
        self.swipe(500, 800, 500, 200, duration_ms=200)

    def lock_screen(self):
        """Locks / turns off phone screen."""
        self.press_key("sleep")

    def take_photo(self) -> Dict[str, Any]:
        """Opens camera and takes a picture."""
        self.launch_app("camera")
        subprocess.run(["timeout", "1"], shell=True)
        # Press camera key or volume down to capture
        self.press_key("camera")
        self.press_key("volume_down")
        return {"status": "photo_captured"}


# Singleton instance
phone_controller = PhoneController()
