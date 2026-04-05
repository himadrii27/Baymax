# Baymax Architecture

**Analogy:** Think of Baymax like a doctor's clinic where:
- The **reception desk** (`commands.py`) quickly handles routine requests ("log my BP")
- The **doctor** (`brain.py`) handles anything nuanced — but first reads your full medical chart
- The **medical chart** is assembled fresh every visit from 6 different records rooms
- The **clinic** can run as a walk-in (`main.py`), a home-visit voice assistant (`voice.py`), or an always-on monitoring service (`daemon.py`)

---

## The Full Picture

```
┌──────────────────────────────────────────────────────────────────┐
│                        ENTRY POINTS                              │
│                                                                  │
│  python main.py         python main.py --voice    daemon.py      │
│  (text chat loop)       (voice loop)              (background)   │
│        │                      │                       │          │
│        │                RealtimeSTT              Launch Agent    │
│        │                (Whisper mic)            Briefing 7am    │
│        │                Wake word /              Med reminders   │
│        │                Distress detect          Auto-restart    │
└────────┼──────────────────────┼───────────────────────┼──────────┘
         │                      │                       │
         └──────────────────────┴───────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │   commands.py         │
                    │   (regex parser)      │
                    │                       │
                    │  "BP was 120/80"      │
                    │  "took metoprolol"    │
                    │  "period started"     │
                    │  "add task: ..."      │
                    └──────┬────────┬───────┘
                           │        │
                  SPECIAL  │        │  EVERYTHING ELSE
                  COMMAND  │        │
                           │        │
               ┌───────────▼──┐  ┌──▼──────────────────────────────────┐
               │  Direct DB   │  │         brain.py                    │
               │  write +     │  │                                     │
               │  confirm ✓   │  │  Assembles system prompt from:      │
               └──────────────┘  │                                     │
                                 │  ┌─────────────────────────────┐    │
                                 │  │ identity.py   → who you are │    │
                                 │  │ memory.py     → what Baymax │    │
                                 │  │                 remembers   │    │
                                 │  │ health.py     → BP, meds,   │    │
                                 │  │                 mood trends  │    │
                                 │  │ cycle.py      → period/PMS/ │    │
                                 │  │                 fertile window│   │
                                 │  │ tasks.py      → open todos  │    │
                                 │  │ calendar.py   → today's     │    │
                                 │  │                 events      │    │
                                 │  └──────────────┬──────────────┘    │
                                 │                 │                   │
                                 │         GEMINI STREAMING            │
                                 │         (gemini-2.5-flash)          │
                                 │                 │                   │
                                 │    ┌────────────▼─────────────┐     │
                                 │    │  stream_callback()       │     │
                                 │    │  → print to console      │     │
                                 │    │  → speak via ElevenLabs  │     │
                                 │    └──────────────────────────┘     │
                                 │                                     │
                                 │    memory.add_from_messages() ─────►│
                                 │    (fact extraction, non-blocking)  │
                                 └─────────────────────────────────────┘
                                                   │
                         ┌─────────────────────────▼───────────────────────┐
                         │                 SUPABASE                        │
                         │                                                 │
                         │  health_logs   period_cycles   medications      │
                         │  period_logs   medication_logs  tasks           │
                         │  baymax_memories (pgvector — Mem0 embeddings)  │
                         └─────────────────────────────────────────────────┘
```

---

## Module-by-Module

### `identity.py` — The Health Chip
Loads `data/identity_profile.yaml` — your static profile: age, conditions (migraines, anemia, low BP), allergies (dust, eucalyptus), supplements, cycle length. Injected into every Claude call so Baymax always "knows" you.

### `memory.py` — The Learning Brain
Wraps **Mem0** (semantic memory via pgvector). After every exchange, extracts facts ("user said they slept badly", "user takes magnesium") and stores them as vector embeddings. On the next message fetches top-5 most *relevant* memories for that specific query.

### `health.py` — The Medical Records Room
Reads/writes to Supabase for BP, meds, mood, weight, symptoms, check-ins. Runs **mood pattern analysis** — correlates sleep vs mood, BP vs mood, missed meds vs bad days — and generates personalized predictions ("Fridays tend to be low energy for you").

### `cycle.py` — Cycle Tracker
Tracks period start/end, daily flow + symptoms. Computes predictions: next period, ovulation window, PMS window. Brain.py uses this to tell Claude "Himadri is currently in PMS window — be extra warm."

### `brain.py` — The Doctor's Brain
The heart of it all. Builds a ~50-line system prompt by pulling context from all 6 modules above, then streams from Gemini. Manages conversation turn count — turn 0 greets, turns 1-4 ask focused questions, turn 5+ *must* conclude with a summary + one recommendation.

### `commands.py` — The Shortcut Layer
Pure regex. Intercepts structured phrases before they reach Claude: "BP was 120 over 80", "took my metoprolol", "add task: buy groceries". Handles them instantly and optionally still lets Claude respond with context.

### `briefing.py` — The Morning Report
Runs at 7am via the daemon. Assembles: today's calendar, open tasks, BP trend, meds due, cycle status, mood prediction. Delivers as a rich terminal panel or speaks via TTS.

### `voice.py` — The Ears and Voice
RealtimeSTT (Whisper small.en) listens always-on. Two activation modes: **wake word** ("hey baymax") and **distress words** ("ouch", "I fell", "I'm bleeding" → triggers a 4-question health scan). Pauses mic during TTS playback to avoid feedback loops.

### `daemon.py` — The Always-On Heartbeat
macOS Launch Agent — starts on login, runs forever. Manages two threads: voice loop (with auto-restart on crash, max 10 attempts) + scheduler (briefing + medication reminders).

---

## Data Flow for a Single Message

```
You type: "I'm feeling really fatigued today"
         │
         ▼
commands.py → matches "feeling" → CommandType.LOG_MOOD
         │
         ├── health.log_mood("fatigued") → Supabase ✓
         │
         └── returns False  ← "let Claude also respond"
         │
         ▼
brain.chat("I'm feeling really fatigued today")
         │
         ├── memory.search("fatigued") → ["user has anemia", "user takes iron supplement"]
         ├── health.health_context_for_prompt() → BP trend, meds status, mood analysis
         ├── cycle.cycle_context_for_prompt() → "Day 18, not in PMS window"
         ├── identity.format_for_prompt() → "Himadri, 23, has migraines, anemia, low BP"
         │
         ▼
Gemini streams response chunk by chunk
         │
         ├── printed live to terminal
         └── memory.add_from_messages() extracts: "user reported fatigue on Friday"
```

---

## External Services

| Service | Purpose | Used In |
|---------|---------|---------|
| **Google Gemini** (gemini-2.5-flash) | LLM for conversation | `brain.py` |
| **Mem0** | Semantic memory extraction + retrieval | `memory.py` |
| **Supabase** | PostgreSQL + pgvector storage | `health.py`, `tasks.py`, `cycle.py`, `memory.py` |
| **Google Calendar** | Today's events for context | `calendar_client.py`, `briefing.py` |
| **ElevenLabs** | Text-to-speech (Adam voice) | `voice.py`, `briefing.py` |
| **RealtimeSTT** | Speech-to-text (Whisper + Silero VAD) | `voice.py` |

---

## Supabase Tables

| Table | What's stored |
|-------|--------------|
| `health_logs` | BP, mood, symptom, weight, sleep, checkin entries |
| `medications` | Standing prescriptions + schedule |
| `medication_logs` | Doses taken (timestamped) |
| `period_cycles` | Period start/end records |
| `period_logs` | Daily flow, symptoms, pain level |
| `tasks` | Todo items with priority + due date |
| `baymax_memories` | pgvector embeddings (Mem0) |

---

## Key Design Decisions

**Turn-based conversation closure:** `brain.py` tracks `_turn_count`. Turn 5+ switches to CONCLUSION RULES — Baymax must summarize, give one recommendation, and close warmly instead of asking more questions.

**Every message rebuilds the full system prompt:** 6 DB calls happen on every chat turn to ensure always-fresh context (health, tasks, cycle, memories, identity, calendar). Intentional but means latency is DB-bound. All wrapped in `try/except` to degrade gracefully.

**Non-blocking memory storage:** `memory.add_from_messages()` is called after each response but never crashes the main loop — failures are silently swallowed.

**Command layer bypasses Claude:** Regex commands fire before Claude, enabling instant acknowledgment (`✓ BP logged`) while still optionally letting Claude respond with contextual commentary.
