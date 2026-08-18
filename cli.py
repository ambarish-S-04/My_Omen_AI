import asyncio
import sys
import os
import time
from typing import Dict, Any, Optional

from backend.config import config
from backend.core.agent import aether_agent
from backend.core.safety import safety_guard
from backend.core.memory import memory_store
from backend.actions.system_tools import system_tools
from backend.actions.window_manager import window_manager
from backend.vision.screen_capture import screen_capturer
from backend.voice.tts import voice_synthesizer

# Speech Recognition for Terminal Microphone
try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False

# ANSI Color Codes
CYAN = "\033[96m"
MAGENTA = "\033[95m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

BANNER = f"""{CYAN}{BOLD}
    ___     ______ _____ _   _ _____ ____        ___  ____  
   / \ \   / / ___|_   _| | | | ____|  _ \      / _ \/ ___| 
  / _ \ \ / /|  _|  | | | |_| |  _| | |_) |____| | | \___ \ 
 / ___ \ V / | |___ | | |  _  | |___|  _ <_____| |_| |___) |
/_/   \_\_/  |_____||_| |_| |_|_____|_| \_\     \___/|____/ 
{RESET}{MAGENTA}  [ AUTONOMOUS MULTIMODAL DESKTOP & OS COPILOT // TUI + VOICE ]{RESET}
{DIM}  Powered by Gemini 3.5/3.7 Flash | D: Drive Environment | 100% Free{RESET}
"""

def print_telemetry():
    stats = system_tools.get_system_stats()
    fg = window_manager.get_foreground_window_title() or "Desktop"
    w, h = screen_capturer.get_screen_size()
    print(f"{DIM}--------------------------------------------------------------------------------{RESET}")
    print(f" {CYAN}SCREEN:{RESET} {w}x{h}  |  {CYAN}CPU:{RESET} {stats.get('cpu_percent')}%  |  {CYAN}RAM:{RESET} {stats.get('ram_percent')}%  |  {CYAN}ACTIVE APP:{RESET} {fg[:30]}")
    print(f" {YELLOW}FAILSAFE:{RESET} Press {BOLD}ESC{RESET} or flick mouse to any corner to emergency abort.")
    print(f"{DIM}--------------------------------------------------------------------------------{RESET}\n")

def listen_to_microphone() -> Optional[str]:
    """Captures microphone audio from terminal, detects silence, and returns text."""
    if not HAS_SR:
        print(f"{RED}SpeechRecognition / PyAudio is not available.{RESET}")
        return None

    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 1.2  # Silence pause duration before ending speech
    recognizer.energy_threshold = 300  # Adjust for room mic sensitivity
    recognizer.dynamic_energy_threshold = True

    try:
        with sr.Microphone() as source:
            print(f"\n{GREEN}{BOLD}🎙️ LISTENING... (Speak your instruction, stops on silence){RESET}")
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=8, phrase_time_limit=15)

        print(f"{MAGENTA}⏳ Transcribing speech...{RESET}")
        text = recognizer.recognize_google(audio)
        print(f"{CYAN}{BOLD}✔ Heard:{RESET} \"{text}\"")
        return text

    except sr.WaitTimeoutError:
        print(f"{DIM}No speech detected.{RESET}")
        return None
    except sr.UnknownValueError:
        print(f"{YELLOW}Could not understand speech audio. Try again.{RESET}")
        return None
    except Exception as e:
        print(f"{RED}Microphone error: {e}{RESET}")
        return None

async def run_cli_task(goal: str, dry_run: bool = False):
    print(f"\n{GREEN}{BOLD}>>> DISPATCHING GOAL:{RESET} \"{goal}\"")
    print(f"{DIM}Mode: {'GHOST (DRY-RUN)' if dry_run else 'LIVE NATIVE OS CONTROL'}{RESET}\n")

    # CLI event callback
    async def cli_broadcaster(event_data: Dict[str, Any]):
        event = event_data.get("event")
        data = event_data.get("data", {})

        if event == "agent_status":
            status = data.get("status")
            step = data.get("step")
            if status in ["PLANNING", "OBSERVING", "REASONING"]:
                print(f" {MAGENTA}[{status}]{RESET} Analyzing screen...", end="\r")
            elif status == "EXECUTING":
                print(f" {GREEN}[EXECUTING]{RESET} Running action for Step {step}...", end="\r")
            elif status == "STOPPED":
                print(f"\n {RED}{BOLD}[EMERGENCY STOP]{RESET} {data.get('reason', 'User aborted.')}")

        elif event == "step_decision":
            step = data.get("step")
            thought = data.get("thought")
            action = data.get("action")
            params = data.get("params", {})
            label = data.get("target_label") or ""

            print(f"\n{CYAN}{BOLD}--- [STEP {step}] ---{RESET}")
            print(f" {BOLD}Thought:{RESET} {thought}")
            print(f" {GREEN}Action:{RESET}  {BOLD}{action.upper()}{RESET} {DIM}{params}{RESET} {YELLOW}{'(' + label + ')' if label else ''}{RESET}")

        elif event == "step_executed":
            step = data.get("step")
            diff = data.get("screen_diff", 0)
            res = data.get("result")
            print(f" {DIM}Result: {res} | Screen Delta: {diff}%{RESET}")

        elif event == "task_completed":
            summary = data.get("summary", "Done.")
            steps = data.get("total_steps", 0)
            print(f"\n{GREEN}{BOLD}================================================================{RESET}")
            print(f" {GREEN}{BOLD}✔ TASK COMPLETED in {steps} steps!{RESET}")
            print(f" {BOLD}Summary:{RESET} {summary}")
            print(f"{GREEN}{BOLD}================================================================{RESET}\n")

        elif event == "agent_question":
            q = data.get("question")
            print(f"\n{YELLOW}{BOLD}[AGENT NEEDS CLARIFICATION]{RESET} {q}")

    aether_agent.set_broadcaster(cli_broadcaster)

    # Run the autonomous ReAct task
    result = await aether_agent.run_task(goal=goal, dry_run=dry_run, voice_enabled=True)
    return result

async def continuous_voice_mode():
    """Continuous Hands-Free voice loop in terminal."""
    print(f"\n{GREEN}{BOLD}=== CONTINUOUS HANDS-FREE VOICE MODE ENGAGED ==={RESET}")
    print(f"{DIM}Speak anytime. When you pause, AETHER-OS will automatically execute.{RESET}")
    print(f"{DIM}Press Ctrl+C to exit voice mode.{RESET}\n")

    while True:
        try:
            spoken_text = listen_to_microphone()
            if spoken_text:
                clean_text = spoken_text.lower().strip().rstrip(".")
                if clean_text in ["stop", "cancel", "abort", "exit", "quit", "halt"]:
                    print(f"\n{RED}{BOLD}🛑 Voice STOP keyword received. Halting voice mode.{RESET}")
                    safety_guard.trigger_emergency_stop(reason="Voice STOP command")
                    break
                await run_cli_task(spoken_text, dry_run=False)
                # Small pause after task before listening again
                print(f"\n{DIM}Waiting for next voice command...{RESET}")
                await asyncio.sleep(1.0)
            else:
                await asyncio.sleep(0.5)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print(f"\n{YELLOW}Exited continuous voice mode.{RESET}")
            break

async def main_tui_loop():
    # Enable ANSI color support on Windows
    os.system("")
    print(BANNER)
    print_telemetry()

    print(f"{BOLD}Commands:{RESET}")
    print(f"  • {GREEN}voice{RESET} or {GREEN}v{RESET}    - 🎙️ Single voice input (Speaks ➜ auto-runs on silence)")
    print(f"  • {GREEN}handsfree{RESET}    - 🗣️ Continuous hands-free voice loop (Never touch keyboard)")
    print(f"  • Type any text goal directly (e.g. {CYAN}open notepad and write hello{RESET})")
    print(f"  • {YELLOW}ghost <goal>{RESET} - Run in simulation / dry-run mode")
    print(f"  • {YELLOW}windows{RESET}      - List all currently open Windows apps")
    print(f"  • {YELLOW}history{RESET}      - View past task records")
    print(f"  • {YELLOW}clear{RESET}        - Clear terminal & refresh telemetry")
    print(f"  • {YELLOW}exit{RESET}         - Quit TUI\n")

    while True:
        try:
            print(f"{CYAN}{BOLD}AETHER-OS ❯{RESET} ", end="")
            user_input = input().strip()

            if not user_input:
                continue

            cmd_lower = user_input.lower()

            if cmd_lower in ["exit", "quit", "q"]:
                print(f"{YELLOW}Shutting down AETHER-OS TUI. Goodbye!{RESET}")
                break

            elif cmd_lower in ["clear", "cls"]:
                os.system("cls" if os.name == "nt" else "clear")
                print(BANNER)
                print_telemetry()
                continue

            elif cmd_lower in ["voice", "v"]:
                spoken = listen_to_microphone()
                if spoken:
                    await run_cli_task(spoken, dry_run=False)
                continue

            elif cmd_lower in ["handsfree", "hf", "listen"]:
                await continuous_voice_mode()
                continue

            elif cmd_lower == "windows":
                wins = window_manager.list_windows()
                print(f"\n{CYAN}{BOLD}Active Windows ({len(wins)}):{RESET}")
                for i, w in enumerate(wins):
                    print(f"  [{i+1}] {w['title']}")
                print()
                continue

            elif cmd_lower == "history":
                tasks = memory_store.get_recent_tasks(limit=5)
                print(f"\n{CYAN}{BOLD}Recent Task History ({len(tasks)}):{RESET}")
                for t in tasks:
                    print(f"  • [{t['status'].upper()}] {t['goal']} ({len(t['steps'])} steps)")
                print()
                continue

            elif cmd_lower.startswith("ghost "):
                goal = user_input[6:].strip()
                await run_cli_task(goal, dry_run=True)

            else:
                await run_cli_task(user_input, dry_run=False)

        except (KeyboardInterrupt, EOFError):
            print(f"\n{YELLOW}Interrupted. Use 'exit' to quit.{RESET}")
            safety_guard.trigger_emergency_stop()

if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1] in ["--voice", "-v", "voice"]:
            os.system("")
            print(BANNER)
            asyncio.run(continuous_voice_mode())
        else:
            asyncio.run(main_tui_loop())
    except KeyboardInterrupt:
        print("\nExited.")
