"""
PhoneExecutor — Instant Android phone command execution via ADB intents & shell.

Instead of visually navigating the phone screen with screenshots,
this module sends direct Android intents and shell commands via ADB.
Result: 200ms execution vs 10+ seconds of phone vision-based navigation.
"""
import subprocess
import os
import re
from typing import Dict, Any, List, Optional
from backend.actions.phone_controller import phone_controller

# Android Intent URI shortcuts for common app actions
APP_INTENTS = {
    # Messaging
    "whatsapp": {"package": "com.whatsapp", "action": "android.intent.action.MAIN", "category": "android.intent.category.LAUNCHER"},
    "telegram": {"package": "org.telegram.messenger"},
    "messages": {"package": "com.google.android.apps.messaging"},
    "sms": {"package": "com.google.android.apps.messaging"},
    
    # Social
    "instagram": {"package": "com.instagram.android"},
    "twitter": {"package": "com.twitter.android"},
    "x": {"package": "com.twitter.android"},
    "facebook": {"package": "com.facebook.katana"},
    "snapchat": {"package": "com.snapchat.android"},
    "reddit": {"package": "com.reddit.frontpage"},
    
    # Media & Music
    "spotify": {"package": "com.spotify.music"},
    "youtube": {"package": "com.google.android.youtube"},
    "youtube music": {"package": "com.google.android.apps.youtube.music"},
    "netflix": {"package": "com.netflix.ninja"},
    "prime video": {"package": "com.amazon.avod.thirdpartyclient"},
    
    # Google Suite
    "chrome": {"package": "com.android.chrome"},
    "gmail": {"package": "com.google.android.gm"},
    "maps": {"package": "com.google.android.apps.maps"},
    "google maps": {"package": "com.google.android.apps.maps"},
    "photos": {"package": "com.google.android.apps.photos"},
    "google photos": {"package": "com.google.android.apps.photos"},
    "drive": {"package": "com.google.android.apps.docs"},
    "google drive": {"package": "com.google.android.apps.docs"},
    "calendar": {"package": "com.google.android.calendar"},
    "keep": {"package": "com.google.android.keep"},
    "google keep": {"package": "com.google.android.keep"},
    
    # Utilities
    "settings": {"package": "com.android.settings"},
    "calculator": {"package": "com.google.android.calculator"},
    "clock": {"package": "com.google.android.deskclock"},
    "camera": {"action": "android.media.action.STILL_IMAGE_CAMERA"},
    "file manager": {"package": "com.google.android.documentsui"},
    "files": {"package": "com.google.android.documentsui"},
    "contacts": {"package": "com.google.android.contacts"},
    
    # Communication
    "phone": {"package": "com.google.android.dialer"},
    "dialer": {"package": "com.google.android.dialer"},
    "zoom": {"package": "us.zoom.videomeetings"},
    "discord": {"package": "com.discord"},
    "slack": {"package": "com.Slack"},
    "teams": {"package": "com.microsoft.teams"},
}


class PhoneExecutor:
    """Executes phone tasks directly via ADB intents/shell instead of visual navigation."""
    
    def _adb(self, args: List[str], timeout: float = 10.0) -> str:
        """Run raw ADB command and return output string."""
        return phone_controller._run_adb(args, timeout=timeout)

    def execute_command(self, tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Master dispatcher for phone direct execution."""
        try:
            if tool == "phone_launch_app":
                return self.launch_app(params.get("name", ""))
            elif tool == "phone_open_url":
                return self.open_url(params.get("url", ""))
            elif tool == "phone_search_web":
                return self.search_web(params.get("query", ""), params.get("engine", "google"))
            elif tool == "phone_send_sms":
                return self.send_sms(params.get("number", ""), params.get("message", ""))
            elif tool == "phone_make_call":
                return self.make_call(params.get("number", ""))
            elif tool == "phone_set_alarm":
                return self.set_alarm(params.get("hour", 7), params.get("minute", 0), params.get("label", "OMEN Alarm"))
            elif tool == "phone_set_timer":
                return self.set_timer(params.get("seconds", 60))
            elif tool == "phone_take_photo":
                return self.take_photo()
            elif tool == "phone_toggle":
                return self.toggle_setting(params.get("setting", ""), params.get("state", "on"))
            elif tool == "phone_set_brightness":
                return self.set_brightness(params.get("level", 128))
            elif tool == "phone_set_volume":
                return self.set_volume(params.get("level", 8), params.get("stream", "media"))
            elif tool == "phone_type_text":
                return self.type_text(params.get("text", ""), params.get("press_enter", False))
            elif tool == "phone_press_key":
                return self.press_key(params.get("key", "home"))
            elif tool == "phone_shell":
                return self.run_shell(params.get("cmd", ""))
            elif tool == "phone_screenshot":
                return self.take_screenshot()
            elif tool == "phone_get_battery":
                return self.get_battery()
            elif tool == "phone_get_notifications":
                return self.get_notifications()
            elif tool == "phone_install_apk":
                return self.install_apk(params.get("path", ""))
            elif tool == "phone_file_push":
                return self.push_file(params.get("local", ""), params.get("remote", "/sdcard/"))
            elif tool == "phone_file_pull":
                return self.pull_file(params.get("remote", ""), params.get("local", ""))
            elif tool == "phone_play_media":
                return self.play_media_url(params.get("url", ""))
            elif tool == "phone_navigate_maps":
                return self.navigate_maps(params.get("destination", ""))
            else:
                return {"status": "error", "message": f"Unknown phone tool: {tool}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def launch_app(self, name: str) -> Dict[str, Any]:
        """Launches an Android app by friendly name using direct intents."""
        clean = name.lower().strip()
        intent = APP_INTENTS.get(clean, None)
        
        if intent:
            if "action" in intent and "package" not in intent:
                # Intent-based launch (e.g. camera)
                res = self._adb(["shell", "am", "start", "-a", intent["action"]])
                return {"status": "success", "method": "intent", "app": name, "output": res}
            
            pkg = intent.get("package", "")
            res = self._adb(["shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"])
            if "events injected" in str(res).lower():
                return {"status": "success", "method": "monkey", "app": name, "package": pkg}
            
            # Fallback to am start
            res2 = self._adb(["shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-n", f"{pkg}/.MainActivity"])
            return {"status": "attempted", "method": "am_start", "app": name, "package": pkg, "output": str(res2)}
        
        # Unknown app: try as package name directly
        res = self._adb(["shell", "monkey", "-p", clean, "-c", "android.intent.category.LAUNCHER", "1"])
        if "events injected" in str(res).lower():
            return {"status": "success", "method": "monkey_raw", "app": name}
        return {"status": "error", "message": f"App '{name}' not found in registry."}

    def open_url(self, url: str) -> Dict[str, Any]:
        """Opens a URL on the phone's default browser."""
        if not url.startswith("http"):
            url = "https://" + url
        self._adb(["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url])
        return {"status": "success", "url": url}

    def search_web(self, query: str, engine: str = "google") -> Dict[str, Any]:
        """Opens a web search on the phone browser."""
        urls = {
            "google": f"https://www.google.com/search?q={query}",
            "youtube": f"https://www.youtube.com/results?search_query={query}",
            "maps": f"https://www.google.com/maps/search/{query}",
        }
        url = urls.get(engine.lower(), urls["google"])
        return self.open_url(url)

    def send_sms(self, number: str, message: str) -> Dict[str, Any]:
        """Opens SMS compose screen with pre-filled number and message."""
        self._adb(["shell", "am", "start", "-a", "android.intent.action.SENDTO",
                    "-d", f"sms:{number}", "--es", "sms_body", message])
        return {"status": "success", "to": number, "message": message,
                "note": "SMS app opened with message pre-filled. User must press Send manually for safety."}

    def make_call(self, number: str) -> Dict[str, Any]:
        """Initiates a phone call."""
        clean = re.sub(r"[^0-9+]", "", number)
        self._adb(["shell", "am", "start", "-a", "android.intent.action.CALL", "-d", f"tel:{clean}"])
        return {"status": "success", "calling": clean}

    def set_alarm(self, hour: int, minute: int, label: str = "OMEN Alarm") -> Dict[str, Any]:
        """Sets a clock alarm on the phone."""
        self._adb(["shell", "am", "start", "-a", "android.intent.action.SET_ALARM",
                    "--ei", "android.intent.extra.alarm.HOUR", str(hour),
                    "--ei", "android.intent.extra.alarm.MINUTES", str(minute),
                    "--es", "android.intent.extra.alarm.MESSAGE", label,
                    "--ez", "android.intent.extra.alarm.SKIP_UI", "true"])
        return {"status": "success", "alarm": f"{hour:02d}:{minute:02d}", "label": label}

    def set_timer(self, seconds: int) -> Dict[str, Any]:
        """Sets a countdown timer."""
        self._adb(["shell", "am", "start", "-a", "android.intent.action.SET_TIMER",
                    "--ei", "android.intent.extra.alarm.LENGTH", str(seconds),
                    "--ez", "android.intent.extra.alarm.SKIP_UI", "true"])
        return {"status": "success", "timer_seconds": seconds}

    def take_photo(self) -> Dict[str, Any]:
        """Opens camera and takes a photo."""
        self._adb(["shell", "am", "start", "-a", "android.media.action.STILL_IMAGE_CAMERA"])
        import time; time.sleep(1.5)
        self._adb(["shell", "input", "keyevent", "27"])  # KEYCODE_CAMERA
        return {"status": "success", "action": "photo_captured"}

    def toggle_setting(self, setting: str, state: str = "on") -> Dict[str, Any]:
        """Toggles WiFi, Bluetooth, flashlight, airplane mode, etc."""
        clean = setting.lower().strip()
        enable = state.lower() in ["on", "enable", "true", "1"]
        
        cmds = {
            "wifi": f"svc wifi {'enable' if enable else 'disable'}",
            "bluetooth": f"svc bluetooth {'enable' if enable else 'disable'}",
            "mobile data": f"svc data {'enable' if enable else 'disable'}",
            "data": f"svc data {'enable' if enable else 'disable'}",
            "airplane": f"settings put global airplane_mode_on {'1' if enable else '0'}",
            "airplane mode": f"settings put global airplane_mode_on {'1' if enable else '0'}",
            "location": f"settings put secure location_mode {'3' if enable else '0'}",
            "gps": f"settings put secure location_mode {'3' if enable else '0'}",
            "auto rotate": f"settings put system accelerometer_rotation {'1' if enable else '0'}",
            "rotation": f"settings put system accelerometer_rotation {'1' if enable else '0'}",
        }
        
        cmd = cmds.get(clean)
        if not cmd:
            return {"status": "error", "message": f"Unknown setting: {setting}"}
        
        self._adb(["shell", cmd])
        return {"status": "success", "setting": setting, "state": "on" if enable else "off"}

    def set_brightness(self, level: int) -> Dict[str, Any]:
        """Sets screen brightness (0-255)."""
        level = max(0, min(255, level))
        self._adb(["shell", "settings", "put", "system", "screen_brightness_mode", "0"])  # Manual mode
        self._adb(["shell", "settings", "put", "system", "screen_brightness", str(level)])
        return {"status": "success", "brightness": level, "percent": round(level / 255 * 100)}

    def set_volume(self, level: int, stream: str = "media") -> Dict[str, Any]:
        """Sets volume level (0-15) for a given stream."""
        stream_ids = {"media": "3", "ring": "2", "notification": "5", "alarm": "4", "system": "1"}
        sid = stream_ids.get(stream.lower(), "3")
        self._adb(["shell", "media", "volume", "--set", str(level), "--stream", sid])
        return {"status": "success", "volume": level, "stream": stream}

    def type_text(self, text: str, press_enter: bool = False) -> Dict[str, Any]:
        """Types text into the currently focused input field."""
        phone_controller.type_text(text, press_enter)
        return {"status": "success", "typed": text[:100]}

    def press_key(self, key: str) -> Dict[str, Any]:
        """Presses a phone key."""
        phone_controller.press_key(key)
        return {"status": "success", "key": key}

    def run_shell(self, cmd: str) -> Dict[str, Any]:
        """Runs an arbitrary ADB shell command."""
        output = self._adb(["shell", cmd], timeout=15.0)
        return {"status": "success", "output": str(output)[:2000]}

    def take_screenshot(self) -> Dict[str, Any]:
        """Captures phone screen and saves to PC."""
        remote = "/sdcard/omen_screenshot.png"
        local = str(Path(os.path.expanduser("~")) / "Desktop" / "phone_screenshot.png")
        self._adb(["shell", "screencap", "-p", remote])
        self._adb(["pull", remote, local])
        self._adb(["shell", "rm", remote])
        return {"status": "success", "saved_to": local}

    def get_battery(self) -> Dict[str, Any]:
        """Returns battery info."""
        return phone_controller.get_battery_status()

    def get_notifications(self) -> Dict[str, Any]:
        """Gets active notifications (requires notification access)."""
        output = self._adb(["shell", "dumpsys", "notification", "--noredact"])
        # Extract notification titles
        titles = re.findall(r"android\.title=String \((.+?)\)", str(output))
        texts = re.findall(r"android\.text=String \((.+?)\)", str(output))
        notifs = [{"title": t, "text": texts[i] if i < len(texts) else ""} for i, t in enumerate(titles[:10])]
        return {"status": "success", "count": len(notifs), "notifications": notifs}

    def install_apk(self, path: str) -> Dict[str, Any]:
        """Installs an APK from PC to phone."""
        output = self._adb(["install", "-r", path], timeout=60.0)
        return {"status": "success" if "success" in str(output).lower() else "error", "output": str(output)}

    def push_file(self, local: str, remote: str = "/sdcard/") -> Dict[str, Any]:
        """Pushes a file from PC to phone."""
        output = self._adb(["push", local, remote], timeout=30.0)
        return {"status": "success", "local": local, "remote": remote, "output": str(output)}

    def pull_file(self, remote: str, local: str = "") -> Dict[str, Any]:
        """Pulls a file from phone to PC."""
        if not local:
            local = str(Path(os.path.expanduser("~")) / "Desktop" / Path(remote).name)
        output = self._adb(["pull", remote, local], timeout=30.0)
        return {"status": "success", "remote": remote, "local": local, "output": str(output)}

    def play_media_url(self, url: str) -> Dict[str, Any]:
        """Opens a media URL (YouTube, Spotify, etc.) on phone."""
        if "youtube.com" in url or "youtu.be" in url:
            self._adb(["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url, "-n", "com.google.android.youtube/.UrlActivity"])
        elif "spotify" in url:
            self._adb(["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url])
        else:
            self._adb(["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url])
        return {"status": "success", "url": url}

    def navigate_maps(self, destination: str) -> Dict[str, Any]:
        """Opens Google Maps with navigation to destination."""
        dest_encoded = destination.replace(" ", "+")
        url = f"google.navigation:q={dest_encoded}"
        self._adb(["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url])
        return {"status": "success", "navigating_to": destination}


# Singleton
phone_executor = PhoneExecutor()
