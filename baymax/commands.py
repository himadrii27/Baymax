"""
commands.py — Detect and parse special commands from user input.

Handles:
  - Health logging (BP, meds, mood, weight, symptoms)
  - Explicit memory commands ("remember: ...", "forget: ...")
  - Task commands ("add task ...", "done task N")
"""
import re
from dataclasses import dataclass
from enum import Enum


class CommandType(Enum):
    LOG_BP = "log_bp"
    LOG_MED = "log_med"
    LOG_MOOD = "log_mood"
    LOG_WEIGHT = "log_weight"
    LOG_SYMPTOM = "log_symptom"
    REMEMBER = "remember"
    FORGET = "forget"
    LIST_MEMORIES = "list_memories"
    ADD_TASK = "add_task"
    LIST_TASKS = "list_tasks"
    DONE_TASK = "done_task"
    BRIEFING = "briefing"
    LOG_CHECKIN = "log_checkin"
    PERIOD_START = "period_start"
    PERIOD_END = "period_end"
    PERIOD_LOG = "period_log"
    PERIOD_QUERY = "period_query"
    NONE = "none"


@dataclass
class ParsedCommand:
    type: CommandType
    data: dict


_BP_RE = re.compile(
    r"\b(?:bp|blood\s+pressure)\s+(?:was\s+|is\s+)?(\d{2,3})\s+(?:over|/)\s+(\d{2,3})",
    re.IGNORECASE,
)
_MED_RE = re.compile(
    r"\b(?:took|taken|had)\s+(?:my\s+)?([\w\s]+?)(?:\s+(\d+\s*mg|\d+\s*mcg|\d+\s*ml))?\s*(?:$|\.|,)",
    re.IGNORECASE,
)
_MOOD_RE = re.compile(
    r"\b(?:feeling|feel)\s+([\w\s,]+?)(?:\s+today|\s+right now|\.|$)",
    re.IGNORECASE,
)
_WEIGHT_RE = re.compile(
    r"\bweigh(?:t|ed)?\s+(\d+\.?\d*)\s*(kg|kgs|lbs|pounds)?",
    re.IGNORECASE,
)
_SYMPTOM_RE = re.compile(
    r"\b(headache|migraine|tired|fatigue|dizzy|dizziness|nauseous|nausea|pain|anxious|anxiety|fever|cough|breathless)\b",
    re.IGNORECASE,
)
_REMEMBER_RE = re.compile(r"^\s*remember\s*[:—]\s*(.+)$", re.IGNORECASE)
_FORGET_RE = re.compile(r"^\s*forget\s*[:—]\s*(.+)$", re.IGNORECASE)
_LIST_MEM_RE = re.compile(r"^\s*(?:list|show)\s+(?:my\s+)?memories\s*$", re.IGNORECASE)
_ADD_TASK_RE = re.compile(r"^\s*(?:add|create|new)\s+task\s*[:—]?\s*(.+)$", re.IGNORECASE)
_LIST_TASK_RE = re.compile(r"^\s*(?:list|show)\s+(?:my\s+)?tasks\s*$", re.IGNORECASE)
_DONE_TASK_RE = re.compile(r"^\s*(?:done|complete|finish)\s+task\s*#?(\d+)\s*$", re.IGNORECASE)
_BRIEFING_RE = re.compile(r"^\s*(?:morning\s+)?briefing\s*$", re.IGNORECASE)

# Period tracking
_PERIOD_START_RE = re.compile(
    r"\b(?:my\s+)?period\s+(?:started|start|has\s+started|came|arrived|is\s+here|began)"
    r"|\bI(?:'m|\s+am)\s+(?:on\s+my\s+period|having\s+my\s+period)"
    r"|\bperiod\s+start(?:ed)?\s+today"
    r"|\bgot\s+my\s+period",
    re.IGNORECASE,
)
_PERIOD_END_RE = re.compile(
    r"\b(?:my\s+)?period\s+(?:ended|stopped|is\s+over|finished|done)"
    r"|\bno\s+more\s+period"
    r"|\bperiod\s+end(?:ed)?\s+today",
    re.IGNORECASE,
)
_PERIOD_FLOW_RE = re.compile(
    r"\b(spotting|light|medium|heavy)\s+(?:flow|bleeding)",
    re.IGNORECASE,
)
_PERIOD_SYMPTOM_RE = re.compile(
    r"\b(cramps?|bloating|bloated|mood\s+swings?|fatigue|tired|cravings?|"
    r"breast\s+tenderness|back\s+pain|nausea|acne|headache|pms)\b",
    re.IGNORECASE,
)
_PERIOD_QUERY_RE = re.compile(
    r"\b(?:when\s+is\s+(?:my\s+)?(?:next\s+period|period\s+due)"
    r"|am\s+i\s+in\s+(?:my\s+)?(?:fertile|pms)\s+window"
    r"|(?:when\s+(?:am|will)\s+i\s+(?:ovulate|be\s+fertile))"
    r"|period\s+tracker?|cycle\s+(?:info|status|summary|history))\b",
    re.IGNORECASE,
)

# Busy day check-in detection
_BUSY_YES_RE = re.compile(
    r"\b(yes[\s,]+(?:very\s+)?busy|pretty busy|super busy|really busy|quite busy|"
    r"hectic|packed\s+day|crazy\s+day|back[- ]to[- ]back|lots\s+of\s+meetings?|"
    r"full\s+day|back\s+to\s+back|slammed|swamped|insane\s+day|busy\s+day)\b",
    re.IGNORECASE,
)
_BUSY_NO_RE = re.compile(
    r"\b(not\s+(?:too\s+)?busy|not\s+really|pretty\s+(?:quiet|free|chill|relaxed)|"
    r"quiet\s+day|light\s+day|easy\s+day|free\s+day|chilled?|relaxed\s+day|"
    r"nothing\s+much|not\s+a\s+lot|slow\s+day|not\s+much\s+on)\b",
    re.IGNORECASE,
)


def parse(text: str) -> ParsedCommand:
    """Return the first recognized command in the text, or NONE."""

    if m := _REMEMBER_RE.match(text):
        return ParsedCommand(CommandType.REMEMBER, {"fact": m.group(1).strip()})

    if m := _FORGET_RE.match(text):
        return ParsedCommand(CommandType.FORGET, {"query": m.group(1).strip()})

    if _LIST_MEM_RE.match(text):
        return ParsedCommand(CommandType.LIST_MEMORIES, {})

    if m := _ADD_TASK_RE.match(text):
        return ParsedCommand(CommandType.ADD_TASK, {"title": m.group(1).strip()})

    if _LIST_TASK_RE.match(text):
        return ParsedCommand(CommandType.LIST_TASKS, {})

    if m := _DONE_TASK_RE.match(text):
        return ParsedCommand(CommandType.DONE_TASK, {"task_num": int(m.group(1))})

    if _BRIEFING_RE.match(text):
        return ParsedCommand(CommandType.BRIEFING, {})

    if m := _BP_RE.search(text):
        return ParsedCommand(CommandType.LOG_BP, {
            "systolic": int(m.group(1)),
            "diastolic": int(m.group(2)),
        })

    if m := _MED_RE.search(text):
        return ParsedCommand(CommandType.LOG_MED, {
            "name": m.group(1).strip(),
            "dose": (m.group(2) or "").strip(),
        })

    if m := _MOOD_RE.search(text):
        return ParsedCommand(CommandType.LOG_MOOD, {"notes": m.group(1).strip()})

    if m := _WEIGHT_RE.search(text):
        unit = (m.group(2) or "kg").lower()
        value = float(m.group(1))
        if unit in ("lbs", "pounds"):
            value = round(value * 0.453592, 2)
        return ParsedCommand(CommandType.LOG_WEIGHT, {"kg": value})

    if m := _SYMPTOM_RE.search(text):
        return ParsedCommand(CommandType.LOG_SYMPTOM, {"name": m.group(1).lower()})

    if m := _BUSY_YES_RE.search(text):
        return ParsedCommand(CommandType.LOG_CHECKIN, {"busy": True, "notes": text.strip()})

    if m := _BUSY_NO_RE.search(text):
        return ParsedCommand(CommandType.LOG_CHECKIN, {"busy": False, "notes": text.strip()})

    # Period tracking — check start/end before symptoms to avoid false positives
    if _PERIOD_START_RE.search(text):
        return ParsedCommand(CommandType.PERIOD_START, {"notes": text.strip()})

    if _PERIOD_END_RE.search(text):
        return ParsedCommand(CommandType.PERIOD_END, {"notes": text.strip()})

    if _PERIOD_QUERY_RE.search(text):
        return ParsedCommand(CommandType.PERIOD_QUERY, {})

    # Period daily log — flow or symptom detected
    flow_match = _PERIOD_FLOW_RE.search(text)
    symptom_match = _PERIOD_SYMPTOM_RE.search(text)
    if flow_match or symptom_match:
        symptoms = [m.group(1).lower().replace(" ", "_") for m in _PERIOD_SYMPTOM_RE.finditer(text)]
        flow = flow_match.group(1).lower() if flow_match else None
        return ParsedCommand(CommandType.PERIOD_LOG, {
            "flow": flow,
            "symptoms": symptoms,
            "notes": text.strip(),
        })

    return ParsedCommand(CommandType.NONE, {})
