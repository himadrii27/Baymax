"""
cycle.py — Period tracking and cycle prediction for Baymax.

Tracks: period start/end, flow intensity, daily symptoms, mood, pain level.
Predicts: next period, ovulation window, fertile window, PMS window.
Correlates: with mood logs, BP, sleep, medication adherence.
"""
from __future__ import annotations
import os
from datetime import date, datetime, timedelta
from statistics import mean
from supabase import create_client, Client

_client: Client | None = None

DEFAULT_CYCLE_LENGTH = 28
DEFAULT_PERIOD_LENGTH = 5
DEFAULT_PMS_DAYS_BEFORE = 7


def _db() -> Client:
    global _client
    if _client is None:
        _client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    return _client


# ─── Logging ──────────────────────────────────────────────────

def log_period_start(start_date: date | None = None, notes: str = "") -> dict:
    """Log the start of a new period. Closes previous open cycle if any."""
    today = start_date or date.today()

    open_cycle = _get_open_cycle()
    if open_cycle:
        _close_cycle(open_cycle["id"], today - timedelta(days=1))

    previous = get_cycle_history(limit=1)
    cycle_length = None
    if previous:
        prev_start = date.fromisoformat(previous[0]["start_date"])
        cycle_length = (today - prev_start).days

    row = _db().table("period_cycles").insert({
        "start_date": today.isoformat(),
        "cycle_length": cycle_length,
        "notes": notes,
    }).execute()
    return row.data[0] if row.data else {}


def log_period_end(end_date: date | None = None, notes: str = "") -> dict:
    """Log the end of the current period."""
    today = end_date or date.today()
    open_cycle = _get_open_cycle()
    if not open_cycle:
        return {"error": "No active period found. Log period start first."}
    return _close_cycle(open_cycle["id"], today, notes)


def _close_cycle(cycle_id: str, end_date: date, notes: str = "") -> dict:
    cycle = _db().table("period_cycles").select("start_date").eq("id", cycle_id).execute().data
    if not cycle:
        return {}
    start = date.fromisoformat(cycle[0]["start_date"])
    period_length = (end_date - start).days + 1
    row = _db().table("period_cycles").update({
        "end_date": end_date.isoformat(),
        "period_length": period_length,
        "notes": notes or None,
    }).eq("id", cycle_id).execute()
    return row.data[0] if row.data else {}


def log_daily(
    flow: str | None = None,
    symptoms: list[str] | None = None,
    mood: str | None = None,
    pain_level: int | None = None,
    notes: str = "",
    log_date: date | None = None,
) -> dict:
    """Log today's period symptoms, flow, and mood."""
    today = log_date or date.today()
    open_cycle = _get_open_cycle()

    valid_flows = ("spotting", "light", "medium", "heavy", "none")
    if flow and flow.lower() not in valid_flows:
        flow = None

    row = _db().table("period_logs").insert({
        "log_date": today.isoformat(),
        "cycle_id": open_cycle["id"] if open_cycle else None,
        "flow": flow.lower() if flow else None,
        "symptoms": symptoms or [],
        "mood": mood,
        "pain_level": pain_level,
        "notes": notes,
    }).execute()
    return row.data[0] if row.data else {}


# ─── Queries ──────────────────────────────────────────────────

def _get_open_cycle() -> dict | None:
    result = (
        _db().table("period_cycles")
        .select("*")
        .is_("end_date", "null")
        .order("start_date", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def get_cycle_history(limit: int = 6) -> list[dict]:
    result = (
        _db().table("period_cycles")
        .select("*")
        .not_.is_("end_date", "null")
        .order("start_date", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def get_recent_period_logs(days: int = 10) -> list[dict]:
    since = (date.today() - timedelta(days=days)).isoformat()
    result = (
        _db().table("period_logs")
        .select("*")
        .gte("log_date", since)
        .order("log_date", desc=True)
        .execute()
    )
    return result.data or []


# ─── Predictions ──────────────────────────────────────────────

def _avg_cycle_stats() -> tuple[float, float]:
    history = get_cycle_history(limit=6)
    lengths = [c["cycle_length"] for c in history if c.get("cycle_length")]
    periods = [c["period_length"] for c in history if c.get("period_length")]
    avg_cycle = mean(lengths) if lengths else DEFAULT_CYCLE_LENGTH
    avg_period = mean(periods) if periods else DEFAULT_PERIOD_LENGTH
    return avg_cycle, avg_period


def predict_next_period() -> dict:
    avg_cycle, avg_period = _avg_cycle_stats()
    today = date.today()

    all_cycles = (
        _db().table("period_cycles")
        .select("start_date")
        .order("start_date", desc=True)
        .limit(1)
        .execute()
        .data or []
    )
    if not all_cycles:
        return {"error": "No cycle data yet. Log your first period to enable predictions."}

    last_start = date.fromisoformat(all_cycles[0]["start_date"])
    next_start = last_start + timedelta(days=round(avg_cycle))
    days_until = (next_start - today).days

    return {
        "next_period_date": next_start.isoformat(),
        "days_until": days_until,
        "avg_cycle_length": round(avg_cycle),
        "avg_period_length": round(avg_period),
        "confidence": "high" if len(get_cycle_history()) >= 3 else "low",
    }


def predict_ovulation_window() -> dict:
    pred = predict_next_period()
    if "error" in pred:
        return pred

    avg_cycle = pred["avg_cycle_length"]
    last_cycles = (
        _db().table("period_cycles")
        .select("start_date")
        .order("start_date", desc=True)
        .limit(1)
        .execute()
        .data or []
    )
    last_start = date.fromisoformat(last_cycles[0]["start_date"])

    ovulation_day = last_start + timedelta(days=round(avg_cycle) - 14)
    fertile_start = ovulation_day - timedelta(days=5)
    fertile_end = ovulation_day + timedelta(days=1)
    today = date.today()

    return {
        "ovulation_date": ovulation_day.isoformat(),
        "fertile_window_start": fertile_start.isoformat(),
        "fertile_window_end": fertile_end.isoformat(),
        "in_fertile_window": fertile_start <= today <= fertile_end,
        "days_to_ovulation": (ovulation_day - today).days,
    }


def predict_pms_window() -> dict:
    pred = predict_next_period()
    if "error" in pred:
        return pred

    next_period = date.fromisoformat(pred["next_period_date"])
    pms_start = next_period - timedelta(days=DEFAULT_PMS_DAYS_BEFORE)
    today = date.today()

    return {
        "pms_start": pms_start.isoformat(),
        "pms_end": (next_period - timedelta(days=1)).isoformat(),
        "in_pms_window": pms_start <= today < next_period,
        "days_to_pms": max((pms_start - today).days, 0),
        "days_to_period": pred["days_until"],
    }


# ─── Insights ─────────────────────────────────────────────────

def get_common_symptoms() -> dict[str, int]:
    logs = _db().table("period_logs").select("symptoms").execute().data or []
    counts: dict[str, int] = {}
    for log in logs:
        for s in (log.get("symptoms") or []):
            counts[s] = counts.get(s, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))


def is_currently_on_period() -> bool:
    return _get_open_cycle() is not None


# ─── System Prompt Block ──────────────────────────────────────

def cycle_context_for_prompt() -> str:
    try:
        today = date.today()

        open_cycle = _get_open_cycle()
        if open_cycle:
            start = date.fromisoformat(open_cycle["start_date"])
            day_num = (today - start).days + 1
            status = f"Currently on period — Day {day_num} (started {start.isoformat()})"
        else:
            status = "Not currently on period"

        pred = predict_next_period()
        if "error" in pred:
            return f"{status}\nNo cycle history yet — encourage user to log their first period."

        next_str = (
            f"Next period: ~{pred['next_period_date']} "
            f"({pred['days_until']} days away, avg cycle: {pred['avg_cycle_length']} days)"
        )

        pms = predict_pms_window()
        if pms.get("in_pms_window"):
            pms_str = f"⚠️ IN PMS WINDOW RIGHT NOW (period in {pms['days_to_period']} days) — be extra gentle and supportive"
        elif pms.get("days_to_pms", 99) <= 3:
            pms_str = f"PMS window starts in {pms['days_to_pms']} days — proactively mention self-care"
        else:
            pms_str = f"PMS window: from {pms['pms_start']}"

        ov = predict_ovulation_window()
        if ov.get("in_fertile_window"):
            fertile_str = f"Currently in fertile window (ovulation ~{ov['ovulation_date']})"
        elif 0 < ov.get("days_to_ovulation", 99) <= 5:
            fertile_str = f"Fertile window approaching — ovulation in {ov['days_to_ovulation']} days"
        else:
            fertile_str = f"Ovulation: ~{ov.get('ovulation_date', 'TBD')}"

        top_symptoms = list(get_common_symptoms().items())[:3]
        symptoms_str = (
            ", ".join(f"{s} ({c}x)" for s, c in top_symptoms)
            if top_symptoms else "None logged yet"
        )

        return (
            f"Cycle status: {status}\n"
            f"{next_str}\n"
            f"{pms_str}\n"
            f"{fertile_str}\n"
            f"Recurring symptoms: {symptoms_str}"
        )
    except Exception:
        return "Cycle tracking unavailable."
