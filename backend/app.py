import os
import json
import asyncio
from pathlib import Path
from typing import Set, Dict, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.config import config, BASE_DIR, FRONTEND_DIR
from backend.core.agent import aether_agent
from backend.core.safety import safety_guard
from backend.core.memory import memory_store
from backend.vision.screen_capture import screen_capturer
from backend.actions.system_tools import system_tools
from backend.actions.window_manager import window_manager
from backend.voice.tts import voice_synthesizer

app = FastAPI(title="AETHER-OS Autonomous Desktop Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active WebSocket connections
active_connections: Set[WebSocket] = set()

async def ws_broadcast_handler(message: Dict[str, Any]):
    """Broadcasts events to all connected clients."""
    if not active_connections:
        return
    payload = json.dumps(message)
    disconnected = set()
    for ws in list(active_connections):
        try:
            await ws.send_text(payload)
        except Exception:
            disconnected.add(ws)
    for dead_ws in disconnected:
        active_connections.discard(dead_ws)

# Register broadcaster with the agent
aether_agent.set_broadcaster(ws_broadcast_handler)

# Safety emergency callback to notify clients
def on_emergency_triggered(reason: str):
    asyncio.create_task(ws_broadcast_handler({
        "event": "emergency_stop",
        "data": {"reason": reason}
    }))

safety_guard.register_emergency_callback(on_emergency_triggered)

# Pydantic Request Models
class TaskRequest(BaseModel):
    goal: str
    dry_run: bool = False
    voice_enabled: bool = True

class ConfigUpdateRequest(BaseModel):
    provider: Optional[str] = None
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = None
    ollama_model: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_model: Optional[str] = None
    voice_enabled: Optional[bool] = None
    mouse_speed: Optional[float] = None

class SpeakRequest(BaseModel):
    text: str
    voice: Optional[str] = None

# Background system telemetry loop
async def telemetry_background_task():
    while True:
        try:
            if active_connections:
                stats = system_tools.get_system_stats()
                fg = window_manager.get_foreground_window_title()
                await ws_broadcast_handler({
                    "event": "telemetry",
                    "data": {
                        "stats": stats,
                        "foreground_window": fg,
                        "agent_running": aether_agent.is_running,
                        "safety_paused": safety_guard.is_paused,
                        "safety_stopped": safety_guard.is_stopped
                    }
                })
        except Exception as e:
            print(f"[Telemetry] error: {e}")
        await asyncio.sleep(2.0)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(telemetry_background_task())

# WebSocket Endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)
    try:
        # Send initial state snapshot
        b64_screen, sw, sh = screen_capturer.capture_base64_jpeg(max_dim=1280)
        await websocket.send_text(json.dumps({
            "event": "init_state",
            "data": {
                "screen": f"data:image/jpeg;base64,{b64_screen}",
                "screen_size": [sw, sh],
                "voices": voice_synthesizer.get_available_voices(),
                "config": {
                    "provider": config.LLM_PROVIDER,
                    "gemini_model": config.GEMINI_MODEL,
                    "has_gemini_key": bool(config.GEMINI_API_KEY),
                    "ollama_model": config.OLLAMA_MODEL
                },
                "recent_tasks": memory_store.get_recent_tasks(limit=5)
            }
        }))

        while True:
            text_data = await websocket.receive_text()
            data = json.loads(text_data)
            action = data.get("action")

            if action == "start_task":
                goal = data.get("goal", "")
                dry_run = data.get("dry_run", False)
                voice_enabled = data.get("voice_enabled", True)
                if goal and not aether_agent.is_running:
                    asyncio.create_task(aether_agent.run_task(goal, dry_run=dry_run, voice_enabled=voice_enabled))

            elif action == "stop_task":
                await aether_agent.stop(reason="User clicked Stop")

            elif action == "pause_task":
                await aether_agent.pause()

            elif action == "resume_task":
                await aether_agent.resume()

            elif action == "capture_screen":
                b64, w, h = screen_capturer.capture_base64_jpeg()
                await websocket.send_text(json.dumps({
                    "event": "screen_frame",
                    "data": {"image": f"data:image/jpeg;base64,{b64}", "width": w, "height": h}
                }))

            elif action == "update_config":
                cfg = data.get("config", {})
                if "gemini_api_key" in cfg:
                    config.GEMINI_API_KEY = cfg["gemini_api_key"]
                if "provider" in cfg:
                    config.LLM_PROVIDER = cfg["provider"]
                if "gemini_model" in cfg:
                    config.GEMINI_MODEL = cfg["gemini_model"]
                if "ollama_model" in cfg:
                    config.OLLAMA_MODEL = cfg["ollama_model"]
                aether_agent.set_llm_config(config.LLM_PROVIDER, config.GEMINI_API_KEY, config.GEMINI_MODEL)
                await websocket.send_text(json.dumps({
                    "event": "config_saved",
                    "data": {"status": "success"}
                }))

    except WebSocketDisconnect:
        active_connections.discard(websocket)
    except Exception as e:
        active_connections.discard(websocket)
        print(f"[WebSocket] error: {e}")

# REST Endpoints
@app.post("/api/task/start")
async def start_task_api(req: TaskRequest):
    if aether_agent.is_running:
        raise HTTPException(status_code=400, detail="Agent is already running a task.")
    asyncio.create_task(aether_agent.run_task(req.goal, dry_run=req.dry_run, voice_enabled=req.voice_enabled))
    return {"status": "started", "goal": req.goal}

@app.post("/api/task/stop")
async def stop_task_api():
    await aether_agent.stop(reason="API Stop Request")
    return {"status": "stopped"}

@app.get("/api/screen/preview")
async def get_screen_preview():
    b64, w, h = screen_capturer.capture_base64_jpeg()
    return {"image": f"data:image/jpeg;base64,{b64}", "width": w, "height": h}

@app.get("/api/system/stats")
async def get_system_stats_api():
    return system_tools.get_system_stats()

@app.get("/api/system/windows")
async def get_windows_api():
    return {"windows": window_manager.list_windows()}

@app.get("/api/memory/tasks")
async def get_past_tasks_api():
    return {"tasks": memory_store.get_recent_tasks(limit=15)}

@app.get("/api/memory/recipes")
async def get_recipes_api():
    return {"recipes": memory_store.list_recipes()}

@app.post("/api/voice/speak")
async def speak_text_api(req: SpeakRequest):
    audio_b64 = await voice_synthesizer.generate_speech_base64(req.text, voice=req.voice)
    if not audio_b64:
        raise HTTPException(status_code=500, detail="Failed to synthesize voice")
    return {"audio": audio_b64}

@app.post("/api/config/update")
async def update_config_api(req: ConfigUpdateRequest):
    if req.gemini_api_key is not None:
        config.GEMINI_API_KEY = req.gemini_api_key
    if req.provider is not None:
        config.LLM_PROVIDER = req.provider
    if req.gemini_model is not None:
        config.GEMINI_MODEL = req.gemini_model
    if req.ollama_model is not None:
        config.OLLAMA_MODEL = req.ollama_model
    if req.mouse_speed is not None:
        config.MOUSE_MOVE_DURATION = req.mouse_speed
    aether_agent.set_llm_config(config.LLM_PROVIDER, config.GEMINI_API_KEY, config.GEMINI_MODEL)
    return {"status": "updated", "provider": config.LLM_PROVIDER}

# Serve Frontend static files
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(FRONTEND_DIR / "index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host=config.HOST, port=config.PORT, reload=False)
