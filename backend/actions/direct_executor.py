"""
DirectExecutor — Instant PC command execution layer for OMEN.

Instead of navigating the screen visually, this module executes actions
programmatically via subprocess, OS APIs, and Python stdlib.
Result: 200ms execution vs 15 seconds of vision-based navigation.
"""
import os
import re
import json
import shutil
import socket
import subprocess
import webbrowser
from pathlib import Path
from typing import Dict, Any, List, Optional
from backend.config import config, BASE_DIR

# Well-known Windows app launch commands
APP_COMMANDS = {
    # Editors & IDEs
    "vs code": "code", "vscode": "code", "visual studio code": "code",
    "notepad": "notepad", "notepad++": "notepad++",
    "sublime": "subl", "sublime text": "subl",
    
    # Browsers
    "chrome": "chrome", "google chrome": "chrome",
    "firefox": "firefox", "brave": "brave",
    "edge": "msedge", "microsoft edge": "msedge",
    
    # System & Utils
    "calculator": "calc", "calc": "calc",
    "file explorer": "explorer", "explorer": "explorer",
    "task manager": "taskmgr", "taskmgr": "taskmgr",
    "command prompt": "cmd", "cmd": "cmd",
    "powershell": "powershell", "terminal": "wt",
    "windows terminal": "wt",
    "paint": "mspaint", "mspaint": "mspaint",
    "snipping tool": "snippingtool",
    "control panel": "control",
    "settings": "ms-settings:",
    "disk management": "diskmgmt.msc",
    "device manager": "devmgmt.msc",
    "regedit": "regedit",
    "wordpad": "wordpad",
    
    # Media
    "spotify": "spotify", "vlc": "vlc",
    "obs": "obs64", "obs studio": "obs64",
    
    # Productivity
    "word": "winword", "microsoft word": "winword",
    "excel": "excel", "microsoft excel": "excel",
    "powerpoint": "powerpnt", "microsoft powerpoint": "powerpnt",
    "outlook": "outlook", "microsoft outlook": "outlook",
    "teams": "ms-teams:", "microsoft teams": "ms-teams:",
    "onenote": "onenote",
    
    # Communication
    "discord": "discord", "slack": "slack",
    "zoom": "zoom", "telegram": "telegram",
    "whatsapp": "whatsapp:",
    
    # Dev Tools
    "git bash": "git-bash", "postman": "postman",
    "docker": "docker", "docker desktop": "docker",
    "android studio": "studio64",
}

# URL shortcuts for common web actions  
WEB_SHORTCUTS = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "chatgpt": "https://chat.openai.com",
    "twitter": "https://twitter.com", "x": "https://x.com",
    "reddit": "https://www.reddit.com",
    "stackoverflow": "https://stackoverflow.com",
    "linkedin": "https://www.linkedin.com",
    "instagram": "https://www.instagram.com",
    "whatsapp web": "https://web.whatsapp.com",
    "amazon": "https://www.amazon.in",
    "netflix": "https://www.netflix.com",
    "maps": "https://maps.google.com",
}


class DirectExecutor:
    """Executes PC tasks directly via commands instead of visual navigation."""

    def execute_command(self, tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Master dispatcher: routes to the correct direct execution method."""
        try:
            if tool == "launch_app":
                return self.launch_app(params.get("name", ""))
            elif tool == "run_shell":
                return self.run_shell(params.get("cmd", ""))
            elif tool == "open_url":
                return self.open_url(params.get("url", ""))
            elif tool == "search_web":
                return self.search_web(params.get("query", ""), params.get("engine", "google"))
            elif tool == "create_file":
                return self.create_file(params.get("path", ""), params.get("content", ""))
            elif tool == "read_file":
                return self.read_file(params.get("path", ""))
            elif tool == "create_folder":
                return self.create_folder(params.get("path", ""))
            elif tool == "delete_path":
                return self.delete_path(params.get("path", ""))
            elif tool == "copy_path":
                return self.copy_path(params.get("source", ""), params.get("destination", ""))
            elif tool == "move_path":
                return self.move_path(params.get("source", ""), params.get("destination", ""))
            elif tool == "kill_process":
                return self.kill_process(params.get("name", ""))
            elif tool == "list_processes":
                return self.list_processes(params.get("filter", ""))
            elif tool == "get_system_info":
                return self.get_system_info()
            elif tool == "set_clipboard":
                return self.set_clipboard(params.get("text", ""))
            elif tool == "get_clipboard":
                return self.get_clipboard()
            elif tool == "shutdown":
                return self.shutdown(params.get("mode", "shutdown"), params.get("delay", 0))
            elif tool == "type_text":
                return self.type_text_direct(params.get("text", ""))
            elif tool == "press_hotkey":
                return self.press_hotkey(params.get("keys", []))
            else:
                return {"status": "error", "message": f"Unknown tool: {tool}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def launch_app(self, name: str) -> Dict[str, Any]:
        """Launches an application by friendly name or executable command."""
        clean = name.lower().strip()
        
        # Check our known app registry
        cmd = APP_COMMANDS.get(clean, None)
        
        if not cmd:
            # Try direct execution (user may have given exact exe name)
            cmd = clean
        
        # Handle ms-settings: and ms-teams: URI schemes
        if cmd.endswith(":"):
            try:
                os.startfile(cmd)
                return {"status": "success", "method": "uri_scheme", "app": name, "command": cmd}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        
        try:
            proc = subprocess.Popen(
                cmd, shell=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            return {"status": "success", "method": "subprocess", "app": name, "command": cmd, "pid": proc.pid}
        except Exception:
            # Fallback: try os.startfile (handles .lnk, registered apps)
            try:
                os.startfile(name)
                return {"status": "success", "method": "startfile", "app": name}
            except Exception:
                # Fallback: try Start-Process via PowerShell
                try:
                    res = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", f'Start-Process "{name}"'],
                        capture_output=True, text=True, timeout=10,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                    )
                    if res.returncode == 0:
                        return {"status": "success", "method": "powershell", "app": name}
                    return {"status": "error", "message": res.stderr.strip()}
                except Exception as e:
                    return {"status": "error", "message": str(e)}

    def run_shell(self, cmd: str) -> Dict[str, Any]:
        """Runs a PowerShell command and returns output."""
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                capture_output=True, text=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            return {
                "status": "success" if res.returncode == 0 else "error",
                "stdout": res.stdout.strip()[:2000],
                "stderr": res.stderr.strip()[:500],
                "return_code": res.returncode
            }
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "Command timed out (30s)"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def open_url(self, url: str) -> Dict[str, Any]:
        """Opens a URL in the default browser."""
        # Check shortcuts
        clean = url.lower().strip()
        resolved = WEB_SHORTCUTS.get(clean, None)
        if resolved:
            url = resolved
        elif not url.startswith("http") and "." in url:
            url = "https://" + url
        
        try:
            webbrowser.open(url)
            return {"status": "success", "url": url}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def search_web(self, query: str, engine: str = "google") -> Dict[str, Any]:
        """Opens a web search directly."""
        engines = {
            "google": f"https://www.google.com/search?q={query}",
            "bing": f"https://www.bing.com/search?q={query}",
            "youtube": f"https://www.youtube.com/results?search_query={query}",
            "duckduckgo": f"https://duckduckgo.com/?q={query}",
            "github": f"https://github.com/search?q={query}",
            "stackoverflow": f"https://stackoverflow.com/search?q={query}",
            "amazon": f"https://www.amazon.in/s?k={query}",
        }
        url = engines.get(engine.lower(), engines["google"])
        webbrowser.open(url)
        return {"status": "success", "engine": engine, "query": query, "url": url}

    def create_file(self, path: str, content: str = "") -> Dict[str, Any]:
        """Creates or overwrites a file with content."""
        try:
            p = Path(path).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return {"status": "success", "path": str(p), "size": len(content)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def read_file(self, path: str) -> Dict[str, Any]:
        """Reads text content of a file."""
        try:
            p = Path(path).resolve()
            if not p.exists():
                return {"status": "error", "message": f"File not found: {path}"}
            content = p.read_text(encoding="utf-8", errors="replace")
            if len(content) > 5000:
                content = content[:5000] + "\n...[truncated]"
            return {"status": "success", "path": str(p), "content": content}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def create_folder(self, path: str) -> Dict[str, Any]:
        """Creates a directory (and parents)."""
        try:
            p = Path(path).resolve()
            p.mkdir(parents=True, exist_ok=True)
            return {"status": "success", "path": str(p)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def delete_path(self, path: str) -> Dict[str, Any]:
        """Deletes a file or directory."""
        try:
            p = Path(path).resolve()
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                shutil.rmtree(p)
            else:
                return {"status": "error", "message": f"Path not found: {path}"}
            return {"status": "success", "deleted": str(p)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def copy_path(self, source: str, destination: str) -> Dict[str, Any]:
        """Copies a file or directory."""
        try:
            src = Path(source).resolve()
            dst = Path(destination).resolve()
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            elif src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                return {"status": "error", "message": f"Source not found: {source}"}
            return {"status": "success", "source": str(src), "destination": str(dst)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def move_path(self, source: str, destination: str) -> Dict[str, Any]:
        """Moves/renames a file or directory."""
        try:
            src = Path(source).resolve()
            dst = Path(destination).resolve()
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            return {"status": "success", "source": str(src), "destination": str(dst)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def kill_process(self, name: str) -> Dict[str, Any]:
        """Kills a running process by name."""
        try:
            clean = name.lower().strip()
            if not clean.endswith(".exe"):
                clean += ".exe"
            res = subprocess.run(
                ["taskkill", "/IM", clean, "/F"],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            return {
                "status": "success" if res.returncode == 0 else "error",
                "output": (res.stdout + res.stderr).strip()
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def list_processes(self, filter_name: str = "") -> Dict[str, Any]:
        """Lists running processes, optionally filtered."""
        try:
            import psutil
            procs = []
            for p in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
                info = p.info
                if filter_name and filter_name.lower() not in info['name'].lower():
                    continue
                procs.append({
                    "pid": info['pid'],
                    "name": info['name'],
                    "memory_mb": round(info['memory_info'].rss / (1024*1024), 1) if info['memory_info'] else 0
                })
            procs.sort(key=lambda x: x.get("memory_mb", 0), reverse=True)
            return {"status": "success", "count": len(procs), "processes": procs[:30]}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_system_info(self) -> Dict[str, Any]:
        """Returns comprehensive system info."""
        try:
            import psutil
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            battery = psutil.sensors_battery()
            return {
                "status": "success",
                "hostname": hostname,
                "ip": ip,
                "cpu_percent": cpu,
                "ram_percent": mem.percent,
                "ram_used_gb": round(mem.used / (1024**3), 2),
                "ram_total_gb": round(mem.total / (1024**3), 2),
                "disk_percent": disk.percent,
                "battery": battery.percent if battery else None,
                "plugged_in": battery.power_plugged if battery else None
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def set_clipboard(self, text: str) -> Dict[str, Any]:
        """Copies text to system clipboard."""
        try:
            import pyperclip
            pyperclip.copy(text)
            return {"status": "success", "length": len(text)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_clipboard(self) -> Dict[str, Any]:
        """Gets current clipboard content."""
        try:
            import pyperclip
            text = pyperclip.paste()
            return {"status": "success", "content": text[:2000]}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def shutdown(self, mode: str = "shutdown", delay: int = 0) -> Dict[str, Any]:
        """Shutdown, restart, or sleep the PC."""
        cmds = {
            "shutdown": f"shutdown /s /t {delay}",
            "restart": f"shutdown /r /t {delay}",
            "logoff": "shutdown /l",
            "lock": "rundll32.exe user32.dll,LockWorkStation",
            "sleep": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
            "cancel": "shutdown /a",
        }
        cmd = cmds.get(mode.lower(), cmds["shutdown"])
        try:
            subprocess.run(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            return {"status": "success", "mode": mode}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def type_text_direct(self, text: str) -> Dict[str, Any]:
        """Types text into whatever is currently focused using pyautogui."""
        try:
            import pyautogui
            pyautogui.typewrite(text, interval=0.02) if text.isascii() else pyautogui.write(text)
            return {"status": "success", "typed": text[:100]}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def press_hotkey(self, keys: List[str]) -> Dict[str, Any]:
        """Presses a keyboard hotkey combination."""
        try:
            import pyautogui
            pyautogui.hotkey(*keys)
            return {"status": "success", "keys": keys}
        except Exception as e:
            return {"status": "error", "message": str(e)}


# Singleton
direct_executor = DirectExecutor()
