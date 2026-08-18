import asyncio
import sys
import os
import io
import time
import re
from typing import Dict, Any, Optional

from backend.config import config
from backend.core.agent import aether_agent
from backend.core.cortex import cortex
from backend.core.safety import safety_guard
from backend.core.memory import memory_store
from backend.actions.system_tools import system_tools
from backend.actions.window_manager import window_manager
from backend.actions.phone_controller import phone_controller
from backend.vision.screen_capture import screen_capturer
from backend.llm import get_llm_provider

# Native Audio Mixer
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
try:
    import pygame
    pygame.mixer.init()
    HAS_PYGAME = True
except Exception:
    HAS_PYGAME = False

try:
    import edge_tts
    HAS_EDGE_TTS = True
except Exception:
    HAS_EDGE_TTS = False

# Speech Recognition for Terminal Microphone
try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False

# ANSI Cyberpunk Colors
CYAN = "\033[96m"
MAGENTA = "\033[95m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
WHITE = "\033[97m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

# Worker color assignments
WORKER_COLORS = {
    "ALPHA": "\033[96m",     # Cyan
    "BRAVO": "\033[93m",     # Yellow
    "CHARLIE": "\033[95m",   # Magenta
    "DELTA": "\033[92m",     # Green
    "ECHO": "\033[94m",      # Blue
    "PRIMARY": "\033[92m",   # Green
    "PHONE": "\033[92m",     # Bright Green
}

OMEN_BANNER = f"""{CYAN}{BOLD}
 ██████╗ ███╗   ███╗███████╗███╗   ██╗
██╔═══██╗████╗ ████║██╔════╝████╗  ██║
██║   ██║██╔████╔██║█████╗  ██╔██╗ ██║
██║   ██║██║╚██╔╝██║██╔══╝  ██║╚██╗██║
╚██████╔╝██║ ╚═╝ ██║███████╗██║ ╚████║
 ╚═════╝ ╚═╝     ╚═╝╚══════╝╚═╝  ╚═══╝
{RESET}{MAGENTA}{BOLD} [ MULTI-AGENT AUTONOMOUS AI COMPANION & OS OPERATOR ]{RESET}
{DIM} Cortex: Nemotron 550B | Workers: Gemini Flash | Voice: Active | $0{RESET}
"""


class OmenTerminalApp:
    def __init__(self):
        self.llm = get_llm_provider()
        self.voice_out_enabled = True
        self.running = True

    def print_telemetry(self):
        stats = system_tools.get_system_stats()
        fg = window_manager.get_foreground_window_title() or "Desktop"
        w, h = screen_capturer.get_screen_size()
        voice_status = f"{GREEN}ON{RESET}" if self.voice_out_enabled else f"{RED}OFF{RESET}"
        print(f"{DIM}────────────────────────────────────────────────────────────────────────────────{RESET}")
        print(f" {CYAN}DISPLAY:{RESET} {w}x{h}  |  {CYAN}CPU:{RESET} {stats.get('cpu_percent')}%  |  {CYAN}VOICE:{RESET} {voice_status}  |  {CYAN}APP:{RESET} {fg[:24]}")
        print(f" {MAGENTA}CORTEX:{RESET} Nemotron 550B (OpenRouter)  |  {GREEN}WORKERS:{RESET} Gemini 3.5 Flash (Google)")
        print(f" {YELLOW}FAILSAFE:{RESET} ESC / Corner Flick / Voice \"Stop\" halts all agents instantly")
        print(f"{DIM}────────────────────────────────────────────────────────────────────────────────{RESET}\n")

    async def speak(self, text: str):
        """Synthesizes text using Edge-TTS and plays directly through pygame audio mixer."""
        if not self.voice_out_enabled or not text or not HAS_EDGE_TTS or not HAS_PYGAME:
            return

        clean_text = re.sub(r"[*_#`\[\]<>]", "", text)
        clean_text = re.sub(r"https?://\S+", "link", clean_text)
        clean_text = clean_text.strip()
        if len(clean_text) > 400:
            clean_text = clean_text[:400] + "..."

        try:
            communicate = edge_tts.Communicate(clean_text, config.DEFAULT_VOICE)
            audio_data = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.extend(chunk["data"])

            if not audio_data:
                return

            if not pygame.mixer.get_init():
                pygame.mixer.init()

            sound_fp = io.BytesIO(audio_data)
            pygame.mixer.music.load(sound_fp)
            pygame.mixer.music.play()

            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.05)

        except Exception:
            pass

    def listen_mic(self) -> Optional[str]:
        if not HAS_SR:
            print(f"{RED}SpeechRecognition / PyAudio is not installed.{RESET}")
            return None

        recognizer = sr.Recognizer()
        recognizer.pause_threshold = 1.2
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True

        try:
            with sr.Microphone() as source:
                print(f"\n{GREEN}{BOLD}🎙️ OMEN LISTENING... (Speak now, auto-processes on silence){RESET}")
                recognizer.adjust_for_ambient_noise(source, duration=0.4)
                audio = recognizer.listen(source, timeout=8, phrase_time_limit=15)

            print(f"{MAGENTA}⏳ Transcribing speech...{RESET}")
            text = recognizer.recognize_google(audio)
            print(f"{CYAN}{BOLD}✔ Heard:{RESET} \"{text}\"")
            return text
        except sr.WaitTimeoutError:
            print(f"{DIM}No speech detected.{RESET}")
            return None
        except sr.UnknownValueError:
            print(f"{YELLOW}Could not understand speech.{RESET}")
            return None
        except Exception as e:
            print(f"{RED}Microphone error: {e}{RESET}")
            return None

    def _get_worker_color(self, worker_name: str) -> str:
        return WORKER_COLORS.get(worker_name, WHITE)

    async def execute_via_cortex(self, goal: str, dry_run: bool = False):
        """Execute a task through the full Cortex multi-agent orchestration pipeline."""
        print(f"\n{MAGENTA}{BOLD}🧠 [CORTEX ENGAGED]{RESET} Analyzing: \"{goal}\"")
        print(f"{DIM}Sending to Nemotron 550B for task decomposition...{RESET}\n")

        await self.speak(f"Analyzing task: {goal[:60]}")

        async def cortex_broadcaster(event_data: Dict[str, Any]):
            event = event_data.get("event")
            data = event_data.get("data", {})
            worker = data.get("worker_name", "")
            wc = self._get_worker_color(worker)

            # ─── CORTEX-LEVEL EVENTS ───
            if event == "cortex_plan":
                strategy = data.get("strategy", "single")
                subtasks = data.get("subtasks", [])
                reasoning = data.get("reasoning", "")
                complexity = data.get("estimated_complexity", "medium")

                strategy_icon = "🔀" if strategy == "parallel" else "▶️"
                strategy_color = YELLOW if strategy == "parallel" else GREEN
                
                print(f"{MAGENTA}{BOLD}┌─────────────────────────────────────────────────────────────┐{RESET}")
                print(f"{MAGENTA}{BOLD}│  CORTEX ANALYSIS COMPLETE                                   │{RESET}")
                print(f"{MAGENTA}{BOLD}└─────────────────────────────────────────────────────────────┘{RESET}")
                print(f"  {BOLD}Strategy:{RESET}    {strategy_color}{BOLD}{strategy_icon} {strategy.upper()}{RESET}")
                print(f"  {BOLD}Complexity:{RESET}  {complexity}")
                print(f"  {BOLD}Reasoning:{RESET}   {reasoning}")
                
                if subtasks:
                    print(f"\n  {BOLD}Subtasks ({len(subtasks)}):{RESET}")
                    for i, st in enumerate(subtasks):
                        st_id = st.get("id", str(i+1))
                        st_goal = st.get("goal", "?")
                        st_type = st.get("type", "ui_action")
                        deps = st.get("depends_on", [])
                        dep_str = f" → depends on [{', '.join(deps)}]" if deps else ""
                        
                        name = ["ALPHA", "BRAVO", "CHARLIE", "DELTA", "ECHO"][i] if i < 5 else f"WORKER-{i+1}"
                        nc = self._get_worker_color(name)
                        
                        connector = "├─" if i < len(subtasks) - 1 else "└─"
                        print(f"  {connector} {nc}{BOLD}[{name}]{RESET} {st_goal} {DIM}({st_type}){dep_str}{RESET}")
                
                print()

            elif event == "cortex_status":
                status = data.get("status", "")
                if status == "DISPATCHING":
                    mode = data.get("mode", "SINGLE")
                    if mode == "PARALLEL":
                        total = data.get("total_agents", 0)
                        print(f"  {MAGENTA}[CORTEX]{RESET} Spawning {BOLD}{total}{RESET} parallel agents...")
                    else:
                        print(f"  {MAGENTA}[CORTEX]{RESET} Dispatching to primary agent...")
                elif status == "SYNTHESIZING":
                    print(f"\n  {MAGENTA}[CORTEX]{RESET} Synthesizing results from all agents...")
                elif status == "ERROR":
                    print(f"\n  {RED}{BOLD}[CORTEX ERROR]{RESET} {data.get('error', 'Unknown error')}")

            elif event == "cortex_worker_spawned":
                wn = data.get("worker_name", "?")
                wgoal = data.get("goal", "?")
                wtype = data.get("task_type", "ui_action")
                nc = self._get_worker_color(wn)
                print(f"  {nc}{BOLD}⚡ [{wn}]{RESET} Spawned → \"{wgoal}\" {DIM}({wtype}){RESET}")

            elif event == "cortex_completed":
                summary = data.get("summary", "All tasks completed.")
                total_w = data.get("total_workers", 0)
                strategy = data.get("strategy", "single")
                results = data.get("results", [])

                print(f"\n{GREEN}{BOLD}╔══════════════════════════════════════════════════════════════╗{RESET}")
                print(f"{GREEN}{BOLD}║  ✔ ALL AGENTS COMPLETED SUCCESSFULLY                         ║{RESET}")
                print(f"{GREEN}{BOLD}╚══════════════════════════════════════════════════════════════╝{RESET}")
                print(f"  {BOLD}Strategy:{RESET} {strategy.upper()} | {BOLD}Agents Used:{RESET} {total_w}")
                
                for r in results:
                    rw = r.get("worker", "?")
                    rc = self._get_worker_color(rw)
                    rs = r.get("status", "?")
                    rg = r.get("goal", "?")
                    rsteps = r.get("steps", 0)
                    status_icon = "✔" if rs in ["completed", "done"] else "✖" if rs == "error" else "⏸"
                    print(f"  {rc}[{rw}]{RESET} {status_icon} {rg} ({rsteps} steps)")
                
                print(f"\n  {BOLD}Summary:{RESET} {summary}\n")

            # ─── WORKER-LEVEL EVENTS ───
            elif event == "worker_started":
                goal = data.get("goal", "?")
                print(f"\n  {wc}{BOLD}[{worker}]{RESET} Starting: \"{goal}\"")

            elif event == "worker_status":
                status = data.get("status", "")
                step = data.get("step", "")
                if status in ["OBSERVING", "REASONING"]:
                    print(f"  {wc}[{worker}]{RESET} {DIM}[{status}]{RESET} Step {step}...", end="\r")
                elif status == "STOPPED":
                    reason = data.get("reason", "Stopped")
                    print(f"\n  {wc}[{worker}]{RESET} {RED}{BOLD}[STOPPED]{RESET} {reason}")
                elif status == "ERROR":
                    print(f"\n  {wc}[{worker}]{RESET} {RED}[ERROR]{RESET} {data.get('error', '')}")

            elif event == "worker_step":
                step = data.get("step", "?")
                thought = data.get("thought", "")
                action = data.get("action", "")
                params = data.get("params", {})
                label = data.get("target_label", "")

                print(f"\n  {wc}{BOLD}[{worker}][STEP {step}]{RESET}")
                print(f"    {BOLD}Thought:{RESET} {thought}")
                print(f"    {GREEN}Action:{RESET}  {BOLD}{action.upper()}{RESET} {DIM}{params}{RESET} {YELLOW}{'(' + label + ')' if label else ''}{RESET}")

            elif event == "worker_step_done":
                step = data.get("step", "?")
                diff = data.get("screen_diff", 0)
                print(f"    {DIM}Done | Screen Δ: {diff}%{RESET}")

            elif event == "worker_completed":
                summary = data.get("summary", "Done.")
                steps = data.get("total_steps", 0)
                print(f"  {wc}{BOLD}[{worker}] ✔ Completed in {steps} steps:{RESET} {summary}")

            elif event == "worker_question":
                q = data.get("question", "")
                print(f"\n  {wc}[{worker}]{RESET} {YELLOW}{BOLD}[NEEDS INPUT]{RESET} {q}")

            # ─── DIRECT EXECUTION EVENTS (instant, no-vision mode) ───
            elif event == "direct_execution_start":
                target = data.get("target", "pc").upper()
                total = data.get("total_commands", 0)
                explanation = data.get("explanation", "")
                print(f"\n  {GREEN}{BOLD}⚡ [DIRECT EXECUTION] [{target}]{RESET} {total} command(s)")
                print(f"    {DIM}Plan: {explanation}{RESET}")

            elif event == "direct_execution_step":
                step = data.get("step", "?")
                total = data.get("total", "?")
                tool = data.get("tool", "?")
                params = data.get("params", {})
                status = data.get("status", "")
                result_summary = data.get("result_summary", "")
                
                if status == "EXECUTING":
                    params_str = ", ".join(f"{k}={v}" for k, v in params.items()) if params else ""
                    print(f"    {GREEN}[{step}/{total}]{RESET} {BOLD}{tool}{RESET}({DIM}{params_str}{RESET})", end="")
                elif status == "DONE":
                    print(f" {GREEN}✔{RESET}")
                elif status == "ERROR":
                    print(f" {RED}✖ {result_summary}{RESET}")
                elif status == "STOPPED":
                    print(f" {RED}⏹ STOPPED{RESET}")

            elif event == "cortex_status":
                status = data.get("status", "")
                if status == "GENERATING_COMMANDS":
                    target = data.get("target", "pc").upper()
                    print(f"\n  {CYAN}[CORTEX]{RESET} Generating direct {target} commands...", end="\r")

            # ─── LEGACY AETHER AGENT EVENTS (single-agent mode) ───
            elif event == "agent_status":
                status = data.get("status")
                step = data.get("step")
                if status in ["PLANNING", "OBSERVING", "REASONING"]:
                    print(f"  {GREEN}[PRIMARY]{RESET} {DIM}[{status}]{RESET} Step {step}...", end="\r")
                elif status == "EXECUTING":
                    print(f"  {GREEN}[PRIMARY][EXECUTING]{RESET} Step {step}...", end="\r")
                elif status == "STOPPED":
                    reason = data.get("reason", "Action aborted.")
                    print(f"\n  {RED}{BOLD}[EMERGENCY STOP]{RESET} {reason}")
                    await self.speak("Action cancelled.")

            elif event == "step_decision":
                step = data.get("step")
                thought = data.get("thought")
                action = data.get("action")
                params = data.get("params", {})
                label = data.get("target_label") or ""

                print(f"\n  {GREEN}{BOLD}[PRIMARY][STEP {step}]{RESET}")
                print(f"    {BOLD}Thought:{RESET} {thought}")
                print(f"    {GREEN}Action:{RESET}  {BOLD}{action.upper()}{RESET} {DIM}{params}{RESET} {YELLOW}{'(' + label + ')' if label else ''}{RESET}")

            elif event == "step_executed":
                diff = data.get("screen_diff", 0)
                print(f"    {DIM}Done | Screen Δ: {diff}%{RESET}")

            elif event == "task_completed":
                summary = data.get("summary", "Goal completed.")
                steps = data.get("total_steps", 0)
                print(f"\n  {GREEN}{BOLD}[PRIMARY] ✔ Completed in {steps} steps:{RESET} {summary}")

            elif event == "agent_question":
                q = data.get("question")
                print(f"\n  {YELLOW}{BOLD}[OMEN NEEDS INPUT]{RESET} {q}")

        cortex.set_broadcaster(cortex_broadcaster)
        result = await cortex.execute(goal, context={"foreground_window": window_manager.get_foreground_window_title() or "Desktop"}, dry_run=dry_run)

        if result.get("summary"):
            await self.speak(result["summary"])

        return result

    async def handle_prompt(self, user_prompt: str):
        if not user_prompt:
            return

        clean = user_prompt.strip()
        cmd_lower = clean.lower()

        # Built-in Commands
        if cmd_lower in ["exit", "quit", "q"]:
            print(f"{YELLOW}Shutting down OMEN. Standby.{RESET}")
            await self.speak("Shutting down. Goodbye.")
            self.running = False
            return

        if cmd_lower in ["clear", "cls"]:
            os.system("cls" if os.name == "nt" else "clear")
            print(OMEN_BANNER)
            self.print_telemetry()
            return

        if cmd_lower in ["mute", "voice off", "audio off"]:
            self.voice_out_enabled = False
            print(f"{YELLOW}Voice responses muted.{RESET}")
            return

        if cmd_lower in ["unmute", "voice on", "audio on"]:
            self.voice_out_enabled = True
            print(f"{GREEN}Voice responses unmuted.{RESET}")
            await self.speak("Voice output enabled.")
            return

        if cmd_lower in ["about", "who are you", "who are you?", "self", "info"]:
            print(f"\n{CYAN}{BOLD}OMEN v{config.VERSION} // System Architecture & Self-Profile:{RESET}")
            info_msg = (
                f"  • {BOLD}Identity:{RESET} OMEN (Multi-Agent Autonomous AI Companion & OS Operator)\n"
                f"  • {BOLD}Cortex (Orchestrator):{RESET} Nemotron 3 Ultra 550B via OpenRouter (task decomposition & analysis)\n"
                f"  • {BOLD}Workers (Execution):{RESET} Google Gemini 3.5/3.7 Flash (vision + action + reasoning)\n"
                f"  • {BOLD}Perception:{RESET} Real-Time Screen Capture + 0-1000 Normalized Coordinate Grounder\n"
                f"  • {BOLD}Actuation:{RESET} Mouse (Bezier), Keyboard, Windows API, PowerShell\n"
                f"  • {BOLD}Multi-Agent:{RESET} Up to {config.MAX_PARALLEL_AGENTS} parallel worker agents with UI mutex safety\n"
                f"  • {BOLD}Voice:{RESET} Edge Neural TTS + SpeechRecognition VAD + Mid-Task Voice Interrupt\n"
                f"  • {BOLD}Memory:{RESET} SQLite Episodic Store with orchestration session logs\n"
                f"  • {BOLD}LLMs Active:{RESET} 11 models across 2 providers (6 OpenRouter + 5 Gemini)\n"
                f"  • {BOLD}Cost:{RESET} $0.00 (Zero-Cost / Free-Tier)\n"
            )
            print(info_msg)
            await self.speak("I am Omen, a multi-agent autonomous AI companion with a Cortex orchestrator brain and parallel worker agents.")
            return

        if cmd_lower == "windows":
            wins = window_manager.list_windows()
            print(f"\n{CYAN}{BOLD}Active Desktop Windows ({len(wins)}):{RESET}")
            for i, w in enumerate(wins):
                print(f"  [{i+1}] {w['title']}")
            print()
            return

        if cmd_lower == "agents":
            active = cortex.active_workers
            print(f"\n{MAGENTA}{BOLD}Active Worker Agents ({len(active)}):{RESET}")
            if not active:
                print(f"  {DIM}No agents currently running.{RESET}")
            for w in active:
                wc = self._get_worker_color(w.worker_name)
                status = "RUNNING" if w.is_running else "IDLE"
                goal = w.current_plan.goal if w.current_plan else "N/A"
                print(f"  {wc}[{w.worker_name}]{RESET} Status: {status} | Goal: {goal}")
            print()
            return

        if cmd_lower == "history":
            tasks = memory_store.get_recent_tasks(limit=4)
            orchestrations = memory_store.get_recent_orchestrations(limit=3)
            print(f"\n{CYAN}{BOLD}Recent Task Log:{RESET}")
            for t in tasks:
                print(f"  • [{t['status'].upper()}] {t['goal']}")
            if orchestrations:
                print(f"\n{MAGENTA}{BOLD}Recent Multi-Agent Sessions:{RESET}")
                for o in orchestrations:
                    print(f"  • [{o['strategy'].upper()}] {o['total_workers']} workers | {len(o.get('subtasks',[]))} subtasks")
            print()
            return

        if cmd_lower in ["phone", "phone status", "phone info"]:
            summary = phone_controller.get_device_summary()
            print(f"\n{GREEN}{BOLD}📱 Android Phone Telemetry & Status:{RESET}")
            if not summary.get("connected"):
                print(f"  {YELLOW}Status:{RESET} Not Connected")
                print(f"  {DIM}Tip: Connect via USB cable or type 'phone hotspot' while connected to phone's Wi-Fi hotspot.{RESET}\n")
            else:
                print(f"  • {BOLD}Device:{RESET} {summary.get('brand')} {summary.get('model')} (Android {summary.get('android_version')})")
                print(f"  • {BOLD}Connection:{RESET} {summary.get('connection_type')} ({summary.get('device_serial')})")
                print(f"  • {BOLD}Resolution:{RESET} {summary.get('resolution')}")
                bat_charging = "⚡ Charging" if summary.get('is_charging') else "Discharging"
                print(f"  • {BOLD}Battery:{RESET} {summary.get('battery_percent')}% ({bat_charging})\n")
            return

        if cmd_lower in ["phone hotspot", "phone connect hotspot"]:
            print(f"{DIM}Discovering phone hotspot gateway IP...{RESET}")
            res = phone_controller.connect_wireless()
            if res.get("status") == "connected":
                print(f"{GREEN}{BOLD}✔ Connected to phone wirelessly at: {res.get('device')}{RESET}\n")
                await self.speak("Phone connected wirelessly.")
            else:
                print(f"{RED}Could not connect to phone: {res.get('output')}{RESET}")
                print(f"{DIM}Make sure 'Wireless Debugging' is enabled in Developer Options on your phone.{RESET}\n")
            return

        if cmd_lower.startswith("phone connect "):
            target_ip = clean[14:].strip()
            res = phone_controller.connect_wireless(ip=target_ip)
            if res.get("status") == "connected":
                print(f"{GREEN}{BOLD}✔ Connected to phone at {target_ip}!{RESET}\n")
                await self.speak("Phone connected.")
            else:
                print(f"{RED}Failed to connect: {res.get('output')}{RESET}\n")
            return

        if cmd_lower.startswith("phone pair "):
            parts = clean[11:].strip().split()
            if len(parts) >= 2:
                ip_port, code = parts[0], parts[1]
                res = phone_controller.pair_device(ip_port, code)
                if res.get("status") == "paired":
                    print(f"{GREEN}{BOLD}✔ Successfully paired with phone at {ip_port}!{RESET}\n")
                    await self.speak("Phone successfully paired.")
                else:
                    print(f"{RED}Pairing failed: {res.get('output')}{RESET}\n")
            else:
                print(f"{YELLOW}Usage: phone pair <ip:port> <6-digit-pairing-code>{RESET}\n")
            return

        if cmd_lower in ["phone tcpip", "phone enable wireless"]:
            res = phone_controller.enable_tcpip(port=5555)
            print(f"{GREEN}{BOLD}✔ {res.get('message', res.get('output'))}{RESET}\n")
            await self.speak("Wireless port 5555 unlocked. You can now unplug the USB cable.")
            return

        if cmd_lower in ["phone lock", "lock phone"]:
            phone_controller.lock_screen()
            print(f"{GREEN}Phone screen locked.{RESET}\n")
            return

        if cmd_lower in ["phone unlock", "unlock phone"]:
            phone_controller.wake_and_unlock()
            print(f"{GREEN}Phone screen unlocked.{RESET}\n")
            return

        # ─── INTELLIGENT INTENT ROUTING (Chat vs Action) ───
        # If prompt explicitly requests a mobile action, route to Cortex
        is_phone_target = any(clean.lower().startswith(p) for p in ["on phone", "on my phone", "on mobile", "in phone", "in my phone"])

        if is_phone_target:
            await self.execute_via_cortex(clean, dry_run=False)
            return

        # First: quick intent check via Gemini (fast, free, no rate limits)
        print(f"{DIM}Thinking...{RESET}", end="\r")
        fg = window_manager.get_foreground_window_title() or "Desktop"
        routing = await self.llm.route_user_prompt(clean, context={"foreground_window": fg})
        
        intent = routing.get("intent", "chat")

        if intent == "chat":
            response = routing.get("response", "I understand.")
            print(f"\n{CYAN}{BOLD}OMEN:{RESET}\n{response}\n")
            await self.speak(response)

        elif intent == "action":
            # Route through CORTEX for multi-agent orchestration
            await self.execute_via_cortex(clean, dry_run=False)

    async def continuous_voice_loop(self):
        print(f"\n{GREEN}{BOLD}=== CONTINUOUS HANDS-FREE VOICE MODE ACTIVATED ==={RESET}")
        print(f"{DIM}Speak any question or desktop command. Pause when done.{RESET}")
        print(f"{DIM}Say 'stop' or 'exit' or press Ctrl+C to return to text prompt.{RESET}\n")

        await self.speak("Continuous voice mode engaged. What can I do for you?")

        while self.running:
            try:
                spoken = self.listen_mic()
                if spoken:
                    clean_spoken = spoken.lower().strip().rstrip(".")
                    if clean_spoken in ["stop", "exit", "quit", "cancel", "abort"]:
                        print(f"\n{YELLOW}Exiting continuous voice mode.{RESET}")
                        await self.speak("Voice mode paused.")
                        break
                    await self.handle_prompt(spoken)
                    print(f"\n{DIM}Ready for next instruction...{RESET}")
                    await asyncio.sleep(0.8)
                else:
                    await asyncio.sleep(0.4)
            except (KeyboardInterrupt, asyncio.CancelledError):
                print(f"\n{YELLOW}Voice mode closed.{RESET}")
                break

    async def run(self):
        os.system("")
        print(OMEN_BANNER)
        self.print_telemetry()

        print(f"{BOLD}How to use OMEN:{RESET}")
        print(f"  • {CYAN}Ask anything:{RESET} 'Who are you?', 'Explain quantum mechanics', 'Help me write code'")
        print(f"  • {GREEN}OS Automation:{RESET} 'Open Notepad and make a to-do list', 'Search weather in Tokyo'")
        print(f"  • {MAGENTA}Multi-Agent:{RESET} 'Open Chrome and search weather, AND open Notepad and write notes'")
        print(f"  • {YELLOW}Voice:{RESET} {BOLD}v{RESET}/{BOLD}voice{RESET} (single) | {BOLD}handsfree{RESET} (continuous) | {BOLD}mute{RESET}/{BOLD}unmute{RESET}")
        print(f"  • {YELLOW}Commands:{RESET} {BOLD}about{RESET} | {BOLD}agents{RESET} | {BOLD}windows{RESET} | {BOLD}stats{RESET} | {BOLD}history{RESET} | {BOLD}ghost <task>{RESET} | {BOLD}clear{RESET} | {BOLD}exit{RESET}\n")

        await self.speak("Omen online. Multi-agent cortex ready.")

        while self.running:
            try:
                print(f"{CYAN}{BOLD}OMEN ❯{RESET} ", end="")
                user_input = input().strip()

                if not user_input:
                    continue

                if user_input.lower() in ["voice", "v"]:
                    spoken = self.listen_mic()
                    if spoken:
                        await self.handle_prompt(spoken)
                    continue

                if user_input.lower() in ["handsfree", "hf", "listen"]:
                    await self.continuous_voice_loop()
                    continue

                await self.handle_prompt(user_input)

            except (KeyboardInterrupt, EOFError):
                print(f"\n{YELLOW}Interrupted. Type 'exit' to quit.{RESET}")
                safety_guard.trigger_emergency_stop()

if __name__ == "__main__":
    app = OmenTerminalApp()
    try:
        if len(sys.argv) > 1 and sys.argv[1] in ["--voice", "-v", "voice"]:
            asyncio.run(app.continuous_voice_loop())
        else:
            asyncio.run(app.run())
    except KeyboardInterrupt:
        print("\nOMEN Terminated.")
