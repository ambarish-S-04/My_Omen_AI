import subprocess
import os
import shutil
import psutil
import pyperclip
from pathlib import Path
from typing import Dict, Any, List, Optional

class SystemTools:
    def launch_app(self, app_name: str, args: Optional[List[str]] = None) -> Dict[str, Any]:
        """Launches an application or executable by name or command."""
        try:
            cmd = [app_name]
            if args:
                cmd.extend(args)
            proc = subprocess.Popen(cmd, shell=True)
            return {"status": "success", "pid": proc.pid, "message": f"Launched {app_name}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def run_powershell(self, script: str, timeout: int = 30) -> Dict[str, Any]:
        """Executes a PowerShell script or command with timeout."""
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return {
                "status": "success" if res.returncode == 0 else "error",
                "return_code": res.returncode,
                "stdout": res.stdout.strip(),
                "stderr": res.stderr.strip()
            }
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": f"Command timed out after {timeout} seconds"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def read_file(self, file_path: str, max_chars: int = 10000) -> Dict[str, Any]:
        """Reads text content of a local file."""
        try:
            p = Path(file_path).resolve()
            if not p.exists():
                return {"status": "error", "message": f"File not found: {file_path}"}
            content = p.read_text(encoding="utf-8", errors="replace")
            if len(content) > max_chars:
                content = content[:max_chars] + f"\n... [Truncated: {len(content)} total characters]"
            return {"status": "success", "path": str(p), "content": content}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def write_file(self, file_path: str, content: str, mode: str = "w") -> Dict[str, Any]:
        """Writes text content to a local file."""
        try:
            p = Path(file_path).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            if mode == "a":
                with open(p, "a", encoding="utf-8") as f:
                    f.write(content)
            else:
                p.write_text(content, encoding="utf-8")
            return {"status": "success", "path": str(p), "size": len(content)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def list_directory(self, dir_path: str = ".") -> Dict[str, Any]:
        """Lists files and folders in a directory."""
        try:
            p = Path(dir_path).resolve()
            if not p.exists():
                return {"status": "error", "message": f"Directory not found: {dir_path}"}
            items = []
            for item in p.iterdir():
                items.append({
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "size": item.stat().st_size if item.is_file() else 0
                })
            return {"status": "success", "path": str(p), "items": items}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_clipboard(self) -> str:
        """Gets current clipboard text."""
        try:
            return pyperclip.paste()
        except Exception:
            return ""

    def set_clipboard(self, text: str) -> bool:
        """Sets clipboard text."""
        try:
            pyperclip.copy(text)
            return True
        except Exception:
            return False

    def get_system_stats(self) -> Dict[str, Any]:
        """Returns CPU, RAM, Disk and battery status."""
        try:
            cpu_usage = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            battery = psutil.sensors_battery()
            return {
                "cpu_percent": cpu_usage,
                "ram_percent": ram.percent,
                "ram_used_gb": round(ram.used / (1024**3), 2),
                "ram_total_gb": round(ram.total / (1024**3), 2),
                "disk_percent": disk.percent,
                "battery_percent": battery.percent if battery else None,
                "power_plugged": battery.power_plugged if battery else None
            }
        except Exception as e:
            return {"error": str(e)}

system_tools = SystemTools()
