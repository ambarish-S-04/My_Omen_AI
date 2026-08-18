import os
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)

class Config(BaseModel):
    APP_NAME: str = "OMEN"
    VERSION: str = "3.0.0"
    
    # LLM Provider: "gemini", "ollama", "openai"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")
    
    # Google Gemini Settings (Free Tier — Workers & Chat)
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    
    # Ollama Settings (100% Local / Offline)
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5-vl:7b")
    
    # OpenAI / Compatible Settings (Groq, LocalAI)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    
    # OpenRouter Settings (Cortex Orchestrator)
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
    
    # Automation & Safety Settings
    FAILSAFE_ENABLED: bool = True
    MAX_STEPS_PER_TASK: int = 25
    MOUSE_MOVE_DURATION: float = 0.35  # Smooth cursor movement in seconds
    ACTION_DELAY: float = 0.5          # Delay between consecutive actions
    CONFIRM_SENSITIVE_ACTIONS: bool = True
    
    # Screen Vision Settings
    SCREENSHOT_MAX_DIMENSION: int = 1280
    SCREENSHOT_QUALITY: int = 80
    
    # Voice Settings (edge-tts)
    DEFAULT_VOICE: str = "en-US-ChristopherNeural"  # Free high quality neural voice
    VOICE_RATE: str = "+0%"
    VOICE_PITCH: str = "+0Hz"
    
    # Multi-Agent Orchestration
    MAX_PARALLEL_AGENTS: int = int(os.getenv("MAX_PARALLEL_AGENTS", "3"))

config = Config()
