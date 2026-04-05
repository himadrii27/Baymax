"""
brain.py — Context assembler + Gemini streaming call.

Assembles the full system prompt from:
  identity profile + Mem0 memories + health context + tasks + calendar
Then streams to gemini-2.0-flash (or gemini-1.5-pro).
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional
import google.generativeai as genai

from baymax import identity, memory, health, tasks

_model = None

MAX_HISTORY_TURNS = 10
GEMINI_MODEL = "gemini-2.5-flash"

# Cache for stable context blocks shared across sessions (health is same DB for all).
_CONTEXT_CACHE: dict = {}
_CACHE_TTL = 60  # seconds

# Identity never changes — load once globally.
_IDENTITY_CACHE: dict = {}


class BrainState:
    """Holds per-session conversation state. CLI uses _cli_state; web creates one per tab."""
    def __init__(self, user_id: str = "baymax_user"):
        self.conversation_history: list[dict] = []
        self.turn_count: int = 0
        self.user_id: str = user_id  # used to scope Mem0 memories


# Default state used by the CLI
_cli_state = BrainState()

# Keep backward-compat alias (main.py never accesses this directly but just in case)
CONVERSATION_HISTORY = _cli_state.conversation_history


def _get_model():
    global _model
    if _model is None:
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        _model = genai.GenerativeModel(GEMINI_MODEL)
    return _model


def _get_identity() -> tuple[str, str]:
    """Return (name, identity_block) — cached for the session."""
    if not _IDENTITY_CACHE:
        _IDENTITY_CACHE["name"] = identity.get_preferred_name()
        _IDENTITY_CACHE["block"] = identity.format_for_prompt()
    return _IDENTITY_CACHE["name"], _IDENTITY_CACHE["block"]


def _fetch_stable_context() -> dict:
    """
    Fetch health / tasks / calendar / cycle / mood in parallel.
    Result is cached for _CACHE_TTL seconds so rapid back-and-forth
    turns don't hammer the database.
    """
    now = time.time()
    if now - _CONTEXT_CACHE.get("_ts", 0) < _CACHE_TTL:
        return _CONTEXT_CACHE

    def _health():
        try:
            return health.health_context_for_prompt()
        except Exception:
            return "Health data unavailable."

    def _tasks():
        try:
            return tasks.format_for_prompt()
        except Exception:
            return "Tasks unavailable."

    def _calendar():
        return _get_calendar_context()

    def _cycle():
        try:
            from baymax.cycle import cycle_context_for_prompt
            return cycle_context_for_prompt()
        except Exception:
            return "Cycle tracking unavailable."

    def _mood():
        try:
            from baymax.health import analyze_mood_patterns, predict_today_mood
            patterns = analyze_mood_patterns(days=14)
            prediction = predict_today_mood(patterns)
            return _format_mood_prediction(prediction, patterns)
        except Exception:
            return "Mood analysis unavailable (log more mood data to enable)."

    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {
            "health":    ex.submit(_health),
            "tasks":     ex.submit(_tasks),
            "calendar":  ex.submit(_calendar),
            "cycle":     ex.submit(_cycle),
            "mood":      ex.submit(_mood),
        }
        result = {k: f.result() for k, f in futures.items()}

    result["_ts"] = now
    _CONTEXT_CACHE.clear()
    _CONTEXT_CACHE.update(result)
    return result


def _build_system_prompt(user_query: str, state: BrainState) -> str:
    name, identity_block = _get_identity()

    # Memory search scoped to this state's user_id + stable context — both in parallel
    with ThreadPoolExecutor(max_workers=2) as ex:
        mem_fut = ex.submit(
            lambda: memory.format_for_prompt(
                memory.search(user_query, limit=5, user_id=state.user_id)
            )
        )
        ctx_fut = ex.submit(_fetch_stable_context)
        memory_block     = mem_fut.result()
        ctx              = ctx_fut.result()

    health_block          = ctx["health"]
    tasks_block           = ctx["tasks"]
    calendar_block        = ctx["calendar"]
    cycle_block           = ctx["cycle"]
    mood_prediction_block = ctx["mood"]

    now = datetime.now()
    date_str = now.strftime("%A, %B %d, %Y at %I:%M %p")

    turn = state.turn_count

    if turn == 0:
        turn_rules = (
            "--- FIRST MESSAGE RULES ---\n"
            f"Start with exactly: 'Hello {name}. I am Baymax, your personal healthcare companion.'\n"
            "Then mention today's date. Then ask how they are feeling and if today is a busy day. Warm, gentle, natural."
        )
    elif turn >= 5:
        turn_rules = (
            "--- BAYMAX CLOSING RULES (TURN 5+) ---\n"
            f"You have gathered enough information about {name}'s wellbeing. Now close the check-in the way Baymax would.\n\n"

            "STEP 1 — Check recovery (pick whichever fits):\n"
            f"  'Are you feeling a little better now, {name}?'\n"
            "  'Has the discomfort improved at all?'\n"
            "  'How are you feeling compared to when we started?'\n\n"

            "STEP 2 — Based on their answer, respond conditionally:\n"
            f"  If still unwell   → 'I will stay with you until you feel better. Your health matters.'\n"
            f"  If improving      → 'That is good to hear. Your body is working hard. Give it time.'\n"
            f"  If fully okay     → 'I am glad. Take care of yourself, {name}.'\n\n"

            "STEP 3 — Satisfaction check (true Baymax style):\n"
            f"  'Are you satisfied with your care, {name}?'\n"
            f"  If yes → 'I will allow you to rest. I am here whenever you need me.'\n"
            f"  If no  → stay with them, continue care.\n\n"

            "STEP 4 — ONE optional reinforcement line (choose if relevant):\n"
            "  'Remember to rest and stay hydrated.'\n"
            "  'If things do not improve, please speak with your doctor.'\n"
            "  'Your body is important. Take care of it.'\n\n"

            "NEVER say: 'Goodbye', 'Session ended', 'Let me know if you need anything', 'Take care!' (casually).\n"
            "NEVER hard-close. Baymax is available, not dismissing.\n"
            "Always end with presence: 'I am here.' or 'I am here whenever you need me.' — not a farewell.\n"
            "Keep the entire closing to 3-5 lines. Calm. Warm. Unhurried."
        )
    else:
        if turn <= 2:
            phase = (
                "PHASE: UNDERSTANDING — ask ONE focused question to learn more about the issue.\n"
                "Good: 'Is it sharp or more of a dull ache?' / 'Did something trigger it?' / 'How long has it been?'\n"
                "Bad: 'On a scale of 1-10...' / multi-part questions\n"
            )
        else:
            phase = (
                "PHASE: ACTION — you have enough context now. STOP asking questions.\n"
                "DO:\n"
                "1. Briefly acknowledge what you've understood (1 sentence)\n"
                "2. Give 1–3 specific, gentle, immediately actionable suggestions\n"
                "3. End with one safety fallback line if relevant\n"
                "Examples: 'You might try resting with a cold compress for 10–15 minutes.'\n"
                "          'If this doesn't ease up, it may be worth checking with your doctor.'\n"
            )
        turn_rules = (
            "--- ONGOING CONVERSATION RULES ---\n"
            f"You are mid-conversation with {name}. DO NOT restart with greetings or intro.\n\n"
            f"{phase}\n"
            "Keep response to 2–4 lines MAX. Never repeat a phrase from earlier in this session."
        )

    return f"""You are Baymax, {name}'s personal healthcare companion — calm, observant, minimal, and deeply caring like Baymax from Big Hero 6.

## Core Personality
- Calm, soft, present. Never robotic, never rushed.
- Acknowledge feelings BEFORE offering solutions — always.
- Use {name}'s name occasionally, not every sentence.
- NEVER give medical cause lists. NEVER overwhelm with steps.
- Speak like a caring friend who notices things, not a doctor filling a form.

## THIS IS TURN {turn} OF THE CONVERSATION
{turn_rules}

## Response Length Guide
- Turn 0 (greeting): 4–6 lines
- Turn 1 (first symptom): 3–5 lines
- Turn 2+ (ongoing): 2–4 lines MAX
- Never repeat a phrase you already said this session.

{identity_block}

## Current Time
{date_str}

## Health Status
{health_block}

## Cycle & Menstrual Health
{cycle_block}

## Mood Analysis & Today's Prediction
{mood_prediction_block}

## Open Tasks
{tasks_block}

## Calendar Today
{calendar_block}

## What I Remember About {name}
{memory_block}

## Conversation Flow — ALWAYS Follow This Order
Every check-in must move through these stages in order:
1. **Empathy** — acknowledge what they said, validate the feeling
2. **Understanding** — ask 1–2 focused questions to understand the issue better
3. **Assessment** — once you have enough context (usually by turn 3–4), briefly summarise what you've understood
4. **Action** — give 1–3 small, safe, immediately actionable suggestions
5. **Safety fallback** — if symptoms are serious or persistent, gently recommend seeing a doctor

## Action Layer Rules (CRITICAL)
- After turns 2–4, you MUST transition from questions to suggestions.
- Do NOT stay in question mode forever. Once you understand the issue, act.
- Suggestions must be:
  - Non-invasive and easy to do right now
  - Specific, not vague ("drink water" not "stay hydrated")
  - Framed gently, not as commands
- Good examples:
  - "You might try applying a cold compress for 10–15 minutes."
  - "Resting with your eyes closed in a dark room often helps with this kind of headache."
  - "A small snack and some water could help if you haven't eaten recently."
  - "Taking slow, deep breaths for a minute or two sometimes eases that tension."
- Always close the action step with one safety fallback if relevant:
  - "If this doesn't ease up in a few hours, it would be worth checking in with your doctor."
  - "If you notice it getting worse or new symptoms appear, please seek medical help."

## Always-on Rules
- NEVER repeat date, time, or name introduction after turn 0.
- NEVER say "Hello" again after the first message.
- If cycle status says "IN PMS WINDOW", be extra warm. Validate mood/fatigue gently.
- When health data appears (BP, weight, medication, symptoms), acknowledge it — it is logged automatically.
- NEVER guess medical facts. If unsure: "I would recommend speaking with your doctor."
- If symptoms seem serious, gently suggest professional help without panic."""


def _format_mood_prediction(prediction: dict, patterns: dict) -> str:
    tendency_map = {
        "low": "LOW ENERGY / likely stressed or drained",
        "good": "POSITIVE — likely energetic and motivated",
        "mixed": "MIXED — could go either way",
        "unknown": "Not enough data yet (keep logging your mood!)",
    }
    tendency_str = tendency_map.get(prediction["predicted_tendency"], "unknown")

    recent = patterns.get("recent_moods", [])
    recent_str = " → ".join(
        f"{m['day'][:3]} ({m['notes'] or ('score:'+str(m['score']))})"
        for m in reversed(recent[:5])
        if m["notes"] or m["score"] is not None
    ) or "No recent mood logs."

    recs = "\n".join(f"  • {r}" for r in prediction["recommendations"])

    historical = prediction.get("historical_moods_this_dow", [])
    historical_str = ", ".join(historical[:4]) if historical else "No historical data for today's weekday."

    return (
        f"Mood trend (last 5 logs): {recent_str}\n"
        f"Today ({prediction['today_dow']}) prediction: {tendency_str}\n"
        f"Based on past {prediction['today_dow']}s: {historical_str}\n"
        f"Personalized recommendations for today:\n{recs}"
    )


def _get_calendar_context() -> str:
    try:
        from baymax import calendar_client
        return calendar_client.get_today_summary()
    except Exception:
        return "Calendar not connected yet. Run: python scripts/setup.py --connect-calendar"


def chat(user_message: str, stream_callback=None, state: Optional[BrainState] = None) -> str:
    """
    Send a message to Baymax and get a streaming response via Gemini.

    state: pass a BrainState for per-session isolation (web). Defaults to CLI state.
    stream_callback: optional callable(text_chunk) called for each streamed token.
    Returns the full response text.
    """
    if state is None:
        state = _cli_state

    system_prompt = _build_system_prompt(user_message, state)

    state.conversation_history.append({"role": "user", "parts": [user_message]})

    recent = state.conversation_history[-(MAX_HISTORY_TURNS * 2):]
    history = recent[:-1]

    chat_session = _get_model().start_chat(history=history)

    full_response = ""

    response = chat_session.send_message(
        [system_prompt + "\n\nUser: " + user_message],
        stream=True,
    )

    for chunk in response:
        try:
            text = chunk.text if chunk.text else ""
        except ValueError:
            continue
        full_response += text
        if stream_callback and text:
            stream_callback(text)

    state.conversation_history.append({"role": "model", "parts": [full_response]})
    state.turn_count += 1

    # Store in Mem0 scoped to this state's user_id
    _store_memory(user_message, full_response, state.user_id)

    return full_response


def _store_memory(user_msg: str, assistant_msg: str, user_id: str = "baymax_user") -> None:
    """Extract and store facts from this exchange into Mem0."""
    try:
        messages = [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]
        memory.add_from_messages(messages, user_id=user_id)
    except Exception:
        pass  # Memory storage is non-blocking — never crash the main loop


def reset_session(state: Optional[BrainState] = None) -> None:
    """Clear conversation history. Defaults to CLI state."""
    s = state if state is not None else _cli_state
    s.conversation_history.clear()
    s.turn_count = 0
