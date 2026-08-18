import io
import base64
import edge_tts
from typing import List, Dict, Any, Optional
from backend.config import config

VOICES = [
    {"id": "en-US-ChristopherNeural", "name": "Christopher (US Male - Jarvis Style)", "gender": "Male"},
    {"id": "en-US-AriaNeural", "name": "Aria (US Female - Crisp)", "gender": "Female"},
    {"id": "en-US-GuyNeural", "name": "Guy (US Male - Casual)", "gender": "Male"},
    {"id": "en-GB-RyanNeural", "name": "Ryan (UK Male - Polished)", "gender": "Male"},
    {"id": "en-GB-SoniaNeural", "name": "Sonia (UK Female - Smooth)", "gender": "Female"},
    {"id": "en-IN-NeerjaNeural", "name": "Neerja (IN Female - Clear)", "gender": "Female"}
]

class VoiceSynthesizer:
    def __init__(self, default_voice: Optional[str] = None):
        self.default_voice = default_voice or config.DEFAULT_VOICE

    async def generate_speech_base64(self, text: str, voice: Optional[str] = None) -> Optional[str]:
        """
        Synthesizes text using edge-tts and returns base64 MP3 string for web audio playback.
        """
        try:
            chosen_voice = voice or self.default_voice
            communicate = edge_tts.Communicate(text, chosen_voice, rate=config.VOICE_RATE, pitch=config.VOICE_PITCH)
            
            audio_data = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.extend(chunk["data"])

            if not audio_data:
                return None

            b64_audio = base64.b64encode(audio_data).decode("utf-8")
            return f"data:audio/mp3;base64,{b64_audio}"
        except Exception as e:
            print(f"[VoiceSynthesizer] TTS Error: {e}")
            return None

    def get_available_voices(self) -> List[Dict[str, Any]]:
        return VOICES

voice_synthesizer = VoiceSynthesizer()
