<div align="center">

![Mikasa Banner](docs/00-hero.png)

<p>
  <img src="https://img.shields.io/badge/Billing-100%25%20Free%20Tier-2DE2A0?style=for-the-badge" alt="100% Free Tier" />
  <img src="https://img.shields.io/badge/Dependencies-Only%204%20Packages-FF5E8A?style=for-the-badge" alt="4 Packages" />
  <img src="https://img.shields.io/badge/Cloud%20Database-NONE%20(Local%20JSON)-38BDF8?style=for-the-badge" alt="Local Memory" />
  <img src="https://img.shields.io/badge/Python-3.9%2B%20%C2%B7%20PyQt6-F5B855?style=for-the-badge" alt="Python 3.9+ PyQt6" />
  <img src="https://img.shields.io/badge/License-GPLv3-64748B?style=for-the-badge" alt="GPLv3 License" />
</p>

<h3>
  <a href="#quick-start-windows-1-click">1-Click Setup</a>
  &nbsp;&middot;&nbsp;
  <a href="#inside-her-room">Live Screenshots</a>
  &nbsp;&middot;&nbsp;
  <a href="#01--the-0-immortal-model-ladder">Free-Tier Model Ladder</a>
  &nbsp;&middot;&nbsp;
  <a href="#02--12-mood-faces--studio-voice-director">12 Faces &amp; Voice</a>
  &nbsp;&middot;&nbsp;
  <a href="#03--consent-eyes-verbatim-memory--live-clock">Eyes &amp; Memory</a>
</h3>

</div>

---

## Another Room — Not Another Assistant

Most AI companions are either **bloated 6 GB local setups** that melt normal laptops, **generic web wrappers** that forget you tomorrow, or **"free" voice apps** that die silently the second a preview API hits a rate limit.

**Mikasa is built as a separate quiet room on your desktop:**
- **She is not here to manage your tasks.** No *"How can I assist you today?"*, no bullet-point lectures, no fake customer-service cheerfulness. When you bring a heavy night in, she answers *you* — in short, natural **Hinglish or English** (`"hmm... badi der baad aaye."`).
- **100% Free Forever via the Model Ladder:** Runs entirely on a free personal Google AI Studio key (`$0`, no credit card) — engineered with automatic multi-model fallbacks so rate limits or socket drops never turn into dead air.
- **Zero Cloud Surveillance:** Every memory, note, setting, and passphrase hash lives strictly inside your local `config/` folder. Delete the folder and nothing remains anywhere on your machine.

---

## Inside Her Room

| Pitch-Black Room, Live Waveform & Natural Hinglish | Live Controls — Voice, Acting Mode, Language & Consent |
| :---: | :---: |
| <img src="docs/ss-room.png" width="460" alt="Mikasa Room" /> | <img src="docs/ss-controls.png" width="460" alt="Mikasa Controls" /> |

> **95% Obsidian UI (`ui.py`):** Opens as a distraction-free dark room (`F11` / `Esc` toggles fullscreen anytime). While she speaks, her portrait subtly breathes and the rose-gold dot waveform moves live underneath.

---

## 01 &middot; The $0 Immortal Model Ladder
*How we made unstable free-tier preview models behave like a rock-solid, zero-cost production line (`live.py` + `voice.py` + `netwatch.py`).*

Free-tier real-time voice APIs have three fatal traps: **per-minute quota spikes**, **server-enforced WebSocket age limits (`go_away`)**, and **preview models having a bad hour**. Single-model apps freeze on `"reconnecting..."` forever. Mikasa climbs down a **3-layer self-healing ladder** automatically:

1. **Dual Live Brain Ladder (`live.py`):**
   - Connects on **`gemini-3.1-flash-live-preview`** first for ultra-low latency real-time listening and affective dialog.
   - If that model is rate-limited, retired, or unresponsive, she **automatically steps down to `gemini-2.5-flash-native-audio-latest`** while keeping the exact same **`Leda`** voice.
   - **Silent Context Replay:** When switching rungs or recovering from a drop, she injects your last 8 turns silently behind the scenes — she picks up mid-thought and **never greets you twice**.
2. **3-Stage Studio Voice Director (`voice.py`):**
   - Native realtime audio sounds the same whether she is teasing or whispering. Mikasa intercepts her own live transcription clauses (`Splitter`) and routes each sentence through **`gemini-2.5-flash-preview-tts` → `gemini-2.5-flash-tts`** with mood-specific acting prompts.
   - **Zero-Silence Quota Fallback:** The exact second free TTS quota runs out, she whispers one dim status note and **hands her mouth straight back to the Live session's native audio** — zero crash, zero awkward silence.
3. **8-Minute Turn-Boundary Rotation & Honest Diagnostics (`netwatch.py`):**
   - Live sockets eventually get cut by the server, often mid-sentence. Mikasa proactively rotates her session at **8 minutes — strictly between turns, never mid-sentence**.
   - Every hiccup is classified honestly (`network`, `her side`, `usage limit`, `the key`, `the voice model`, `a silent line`) with exponential jitter backoff (`0.5s → 15s`) and a 24-hour health log inside `setup → THE LINE`. Typed messages while offline are held in queue and delivered automatically on reconnect.

![Free-Tier Model Ladder](docs/01-ladder.png)

---

## 02 &middot; 12 Mood Faces & Studio Voice Director
*Inside `assets/faces/` + `voice.py` — her drawing and her mouth never disagree.*

Mikasa owns a `set_mood` tool and changes her own expression mid-conversation with a smooth **`180ms` crossfade**. Whatever mood is on her face simultaneously directs how the TTS engine performs her next line:

- **3 Curated Soft Voices (Hot-Swappable):** **`Leda`** *(default — softest, youthful)*, **`Sulafat`** *(lower, slower, warm)*, and **`Callirrhoe`** *(easy, unhurried for 2 a.m.)*. Changing voices in `setup` takes **1 second live** — no app restart.
- **Spoken, Not Read:** Her persona (`prompt.txt`) forbids robotic lists, emojis, or `(laughs)` stage directions. Hesitations (`"hmm... haan."`, `"tum... kab aaye. huh."`), stretched vowels (`achaaaa`), and question rationing (never ending two turns in a row with a question mark) make every turn sound human.

![12 Mood Faces and Vocal Direction](docs/02-faces.png)

---

## 03 &middot; Consent Eyes, Verbatim Memory & Live Clock

1. **Consent-Only Camera (`camera.py`):**
   - She **never** watches you in the background. When a moment calls for it, she asks out loud (*`"ruko. ek second. dekh lu tumhe."`*).
   - Only if you say **`haan` / yes** does `QtMultimedia` open the webcam, capture **one single frame** (skipping blank warmup frames), send it, release the camera LED immediately, and **delete the file from disk**. Turn Camera `off` in Controls and her prompt explicitly knows she has no eyes.
2. **Verbatim Memory Without Asking (`memory.py`):**
   - Assistants ask *"Should I save this to memory?"* — people just remember. Mikasa writes down facts, ongoing threads, and nightly notes in **your own words** inside `config/memory/facts.json` and `journal.json`, bringing back a small throwaway detail weeks later when it matters.
   - On **The First Night**, she knows nothing about you and never fakes familiarity.
3. **Live Per-Turn Clock & 6 Nightly Registers (`app.py`):**
   - Most system prompts freeze the timestamp at launch. Mikasa receives the real local time (`[[02:14 · Sunday · Agra]]`) fresh on every turn, carries a `get_time` tool, rotates across **6 distinct nightly moods** (clingy, tired, quietly annoyed, playful, quiet, close), and can offer to set a morning alarm when you stay up late.
4. **Her Shelf & Irreversible Passcode Door (`shelf.py` + `settings.py`):**
   - Drop `.txt` or `.md` letters, notes, or poetry into `shelf/` — she reads them **word-for-word** without paraphrasing.
   - Lock the window with a personal passphrase (`setup → CODE`) stored strictly as a **salted SHA-256 hash** — never stored in plaintext, never visible even to the model.

![Eyes, Memory, Clock and Privacy](docs/03-organs.png)

---

## Quick Start (Windows 1-Click)

Mikasa needs **Python 3.9+** (`3.11` / `3.12` recommended) and **1 free Gemini API key** from [Google AI Studio](https://aistudio.google.com/apikey). Nothing else — she builds her own isolated `.venv` with only **4 packages** (`PyQt6`, `numpy`, `sounddevice`, `google-genai`).

### Step 1 — Run the Universal `INSTALL.bat`
1. Download & extract the release folder anywhere (`Desktop` or `Documents`).
2. Double-click **`INSTALL.bat`**:
   - **First Run (Guided 1-Click Setup):** Verifies Python, creates `.venv`, installs only missing packages with a live progress bar, runs **43 built-in self-tests**, lets you type `open` to launch Google AI Studio, **verifies your API key live against Google**, optionally tests **Leda's voice** on your speakers, and places the **Mikasa** icon on your Desktop.
   - **Anytime Later (Interactive Control Deck):** Double-clicking `INSTALL.bat` again opens the **Live Status Control Deck**:

```text
╭─ LIVE STATUS ────────────────────────────────────────────────────────────╮
│ Environment : READY ✓          │   Packages : 4/4 INSTALLED ✓            │
│ Gemini Key  : AIzaSy…9xQ ✓     │   Audio    : 3 audio devices ✓          │
╰──────────────────────────────────────────────────────────────────────────╯
  [1] Launch Mikasa Now         — open her room right away
  [2] Set / Test API Key        — paste key + live Google check
  [3] Check & Fix Packages      — scans 4 deps, installs missing
  [4] Diagnostics & Voice Test  — 43 checks + Leda speaker test
  [5] Create Desktop Icon       — puts Mikasa icon on Desktop
  [6] Run Full Guided Setup     — step-by-step from scratch
```

### Step 2 — Open Her Room Everyday
- Double-click the **Mikasa** Desktop icon, **or** double-click **`mikasa.bat`** (launches silently with `pythonw` — zero console window behind her).

<details>
<summary><b>🛠️ Terminal Commands, Voice Auditions & Built-In Test Suites (Linux / macOS / Power Users)</b></summary>

### Manual Run (Any OS)
```bash
python setup.py              # Guided setup (or Control Deck once installed)
python setup.py --menu       # Open Interactive Control Deck directly
python app.py                # Launch Mikasa
```

### Audition Voices & Personality Without Opening the Window
```bash
python voice.py --demo                # Render all 12 acted moods to WAV files
python voice.py --demo love           # Render a single mood
python hear_her.py --voices           # Audition Leda, Sulafat & Callirrhoe side by side
python hear_her.py --probe            # 3-turn persona drift detector (light / heavy / tech)
```

### Run Her Self-Test Suites (Zero Camera or Mic Required)
```bash
python -m tests.test_line             # 11 checks: drop classification, ladder, 8m rotation, replay
python -m tests.test_persona          # 11 checks: live clock, warmth, claim-read-release, hot voice swap
python -m tests.test_camera           #  7 checks: consent gate, busy/blank frame handling, instant delete
python -m tests.test_voice            # 14 checks: clause splitter, 12 mood styles, quota fallback
```

</details>

<details>
<summary><b>📂 Clean Architecture — Every File Has One Job</b></summary>

| File | Responsibility |
| :--- | :--- |
| `INSTALL.bat` / `setup.py` | Universal 1-click `.venv` installer, live API key verifier & Control Deck |
| `mikasa.bat` / `app.py` | Windowless launcher, single-instance lock, live prompt builder & audio loop |
| `prompt.txt` | Her entire soul — one rule per line, spoken Hinglish/English register |
| `live.py` | Gemini Live supervisor, dual-model ladder, 8-min turn rotation & turn replay |
| `voice.py` | Streaming sentence splitter + 12-mood TTS acting director + quota handback |
| `netwatch.py` | Failure classifier, exponential jitter backoff & 24-hour line telemetry |
| `ui.py` | 95% dark PyQt6 room, 12 `180ms` crossfading faces, breathing & waveform |
| `camera.py` | Consent-only single-frame `QtMultimedia` capture + immediate disk wipe |
| `memory.py` | Local verbatim facts, open threads & nightly notes (`config/memory/`) |
| `shelf.py` & `settings.py` | Verbatim reading shelf (`shelf/`) & salted SHA-256 room passcode |

</details>

---

## Credits & License

Built at 2 a.m. by **AM Dimension Company And Creators — AYUSH AND MAYANK**.

Released under the **[GNU General Public License v3.0 (GPLv3)](LICENSE)**. Every personal memory, key, and runtime log is excluded by `.gitignore` and stays strictly on your own machine.
