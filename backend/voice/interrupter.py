import time
import re
import threading
from typing import Callable, Optional

try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False

INTERRUPT_KEYWORDS = [
    "stop", "cancel", "abort", "halt", "freeze", 
    "don't", "dont", "nevermind", "wait", "hold on", "shut up"
]

class VoiceInterrupter:
    def __init__(self):
        self.recognizer = sr.Recognizer() if HAS_SR else None
        self.stop_listening_fn = None
        self.is_active = False
        self.on_interrupt_callback: Optional[Callable[[str], None]] = None

        if self.recognizer:
            self.recognizer.pause_threshold = 0.6
            self.recognizer.energy_threshold = 300
            self.recognizer.dynamic_energy_threshold = True

    def _audio_callback(self, recognizer, audio):
        """Processes background audio stream during task execution."""
        if not self.is_active:
            return

        try:
            from backend.core.safety import safety_guard
            if safety_guard.is_stopped:
                return

            text = recognizer.recognize_google(audio).lower().strip()

            # Check for interrupt keywords in spoken phrase
            for kw in INTERRUPT_KEYWORDS:
                if re.search(r"\b" + re.escape(kw) + r"\b", text):
                    print(f"\n\033[91m\033[1m🛑 [VOICE INTERRUPTION DETECTED]\033[0m Heard: \"{text}\"")
                    safety_guard.trigger_emergency_stop(reason=f"Voice cancellation: '{text}'")
                    if self.on_interrupt_callback:
                        try:
                            self.on_interrupt_callback(text)
                        except Exception:
                            pass
                    self.stop()
                    break

        except sr.UnknownValueError:
            pass
        except Exception:
            pass

    def start(self, on_interrupt: Optional[Callable[[str], None]] = None):
        """Starts background microphone listening thread while agent is running."""
        if not HAS_SR or not self.recognizer:
            return

        self.stop() # Ensure previous watcher is cleaned up
        self.is_active = True
        self.on_interrupt_callback = on_interrupt

        try:
            mic = sr.Microphone()
            with mic as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.2)
            
            # Non-blocking background thread
            self.stop_listening_fn = self.recognizer.listen_in_background(
                mic, 
                self._audio_callback, 
                phrase_time_limit=4
            )
        except Exception as e:
            self.is_active = False

    def stop(self):
        """Stops background listening thread."""
        self.is_active = False
        if self.stop_listening_fn:
            try:
                self.stop_listening_fn(wait_for_stop=False)
            except Exception:
                pass
            self.stop_listening_fn = None

voice_interrupter = VoiceInterrupter()
