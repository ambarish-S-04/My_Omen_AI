# ⚡ OMEN : Autonomous Personal AI Companion & OS Operator

> **A $0-Cost, Terminal-First, Multimodal Autonomous Personal AI & Desktop Agent** with Grounded Screen Vision, ReAct Planning, Native Windows Automation, Neural Voice, and Deep Conversational Intelligence.

---

## 🌟 Capabilities

### 1. 🧠 Personal AI Companion (Chat & Deep Reasoning)
- Ask any question: science, programming, philosophy, writing, math, advice, daily planning, general knowledge.
- Ask questions about itself: architecture, capabilities, tools, memory, system diagnostics.
- Automatic neural voice responses via Edge-TTS (Jarvis-style Christopher).

### 2. 🦾 Autonomous Desktop OS Operator (Action & Computer-Use)
- Visual screen perception (`mss` / Windows GDI) with normalized spatial grounding (`0-1000` coordinates).
- Autonomous ReAct loop (Sense ➜ Plan ➜ Act ➜ Verify ➜ Self-Correct).
- Native mouse (bezier moves, clicks, double clicks, right clicks, drags), keyboard typing, shortcuts (`Win+R`, `Ctrl+C`, etc.), and PowerShell script execution.

### 3. 📱 Autonomous Android Phone Control (USB & Wireless Hotspot)
- 100% Free & Wireless control over Android devices via ADB / Hotspot network.
- Visual phone screen capture & 0-1000 mobile coordinate grounding via Gemini 3.5 Flash.
- Taps, swipes, typing, app launching (WhatsApp, Spotify, YouTube, Instagram, Camera, etc.), battery monitoring, and lock/unlock.
- Hybrid Multi-Agent: laptop workers and phone workers can execute in parallel!

### 3. 🎙️ Continuous Hands-Free Voice (VAD)
- Real-time speech recognition with automatic silence detection. Speak your command; it auto-executes when you pause.
- Built-in Voice Stop commands: say *"Stop"*, *"Cancel"*, or *"Abort"* anytime to freeze execution.

### 4. 🛡️ Hardware & Hotkey Fail-Safes
- Moving your physical mouse to any screen corner or hitting **`ESC`** immediately halts all automated actions.

---

## 🚀 1-Click Launch

### Option 1: Double-Click Desktop Icon
Double-click **`OMEN`** or **`Launch OMEN.bat`** on your Desktop.

### Option 2: Run via Terminal
```powershell
cd "d:\CODES\New folder"
.\.venv\Scripts\activate
python omen.py
```

---

## 🎮 Interactive Commands in OMEN

```text
OMEN ❯ Who are you and what are your capabilities?
OMEN ❯ Explain how quantum entanglement works
OMEN ❯ Open Notepad and write a poem about artificial intelligence
OMEN ❯ on phone open Spotify and play songs
OMEN ❯ on phone open WhatsApp and send message
OMEN ❯ phone status     (Check connected phone battery & info)
OMEN ❯ phone hotspot    (Auto-connect to phone via Hotspot)
OMEN ❯ voice            (Single voice input)
OMEN ❯ handsfree        (Continuous voice loop)
OMEN ❯ agents           (List active worker agents)
OMEN ❯ windows          (List open desktop apps)
OMEN ❯ history          (Show past memories and tasks)
OMEN ❯ stats            (CPU, RAM, display telemetry)
OMEN ❯ clear            (Clear screen)
OMEN ❯ exit             (Quit OMEN)
```
