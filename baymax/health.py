"""
health.py — Log and query health metrics from Supabase.

Handles: blood pressure, medications, mood, weight, symptoms, sleep, exercise.
"""
from __future__ import annotations
import os
from datetime import date, datetime, timedelta
from supabase import create_client, Client

_client: Client | None = None


def _db() -> Client:
    global _client
    if _client is None:
        _client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    return _client


# ─── Blood Pressure ───────────────────────────────────────────

def log_bp(systolic: int, diastolic: int, notes: str = "") -> dict:
    row = _db().table("health_logs").insert({
        "log_type": "bp",
        "value": {"systolic": systolic, "diastolic": diastolic},
        "notes": notes,
    }).execute()
    return row.data[0] if row.data else {}


def get_recent_bp(days: int = 7) -> list[dict]:
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    result = (
        _db().table("health_logs")
        .select("value, notes, logged_at")
        .eq("log_type", "bp")
        .gte("logged_at", since)
        .order("logged_at", desc=True)
        .execute()
    )
    return result.data or []


def bp_summary_for_prompt() -> str:
    readings = get_recent_bp(days=7)
    if not readings:
        return "No BP readings in the last 7 days."
    latest = readings[0]
    v = latest["value"]
    last_str = f"{v['systolic']}/{v['diastolic']} (logged {latest['logged_at'][:10]})"

    if len(readings) >= 2:
        systolics = [r["value"]["systolic"] for r in readings]
        diastolics = [r["value"]["diastolic"] for r in readings]
        avg_s = round(sum(systolics) / len(systolics))
        avg_d = round(sum(diastolics) / len(diastolics))
        return f"Last BP: {last_str} | 7-day avg: {avg_s}/{avg_d} ({len(readings)} readings)"
    return f"Last BP: {last_str}"


# ─── Medications ──────────────────────────────────────────────

def log_medication(name: str, dose: str = "", notes: str = "") -> dict:
    """Find matching medication by name and log a dose taken."""
    meds = (
        _db().table("medications")
        .select("id, name, dosage")
        .eq("active", True)
        .ilike("name", f"%{name}%")
        .execute()
    )
    med = meds.data[0] if meds.data else None

    row = _db().table("medication_logs").insert({
        "medication_id": med["id"] if med else None,
        "dose_taken": dose or (med["dosage"] if med else ""),
        "notes": f"Matched: {med['name']}" if med else f"Unmatched med: {name}",
    }).execute()
    return {"logged": True, "medication": med["name"] if med else name}


def get_todays_meds() -> str:
    """Return which active meds are scheduled today and whether each was taken."""
    meds = _db().table("medications").select("*").eq("active", True).execute().data or []
    if not meds:
        return "No medications set up."

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    logs = (
        _db().table("medication_logs")
        .select("medication_id, taken_at")
        .gte("taken_at", today_start)
        .execute()
        .data or []
    )
    taken_ids = {log["medication_id"] for log in logs}

    lines = []
    for med in meds:
        times = ", ".join(med.get("schedule_times") or [])
        status = "✓ taken" if med["id"] in taken_ids else "⚠ not yet taken"
        lines.append(f"- {med['name']} {med.get('dosage','')} [{times}]: {status}")
    return "\n".join(lines)


def get_missed_meds_this_week() -> list[str]:
    """Return list of days/meds missed in the last 7 days (simplified)."""
    # Full implementation would cross-reference schedule_times with logs per day
    # Simplified: return meds not logged today
    return []


# ─── Mood / Symptoms / Weight ─────────────────────────────────

def log_mood(notes: str, score: int | None = None) -> dict:
    row = _db().table("health_logs").insert({
        "log_type": "mood",
        "value": {"score": score, "notes": notes},
    }).execute()
    return row.data[0] if row.data else {}


def log_symptom(name: str, severity: int | None = None, notes: str = "") -> dict:
    row = _db().table("health_logs").insert({
        "log_type": "symptom",
        "value": {"name": name, "severity": severity},
        "notes": notes,
    }).execute()
    return row.data[0] if row.data else {}


def log_weight(kg: float, notes: str = "") -> dict:
    row = _db().table("health_logs").insert({
        "log_type": "weight",
        "value": {"kg": kg},
        "notes": notes,
    }).execute()
    return row.data[0] if row.data else {}


def health_context_for_prompt() -> str:
    bp = bp_summary_for_prompt()
    meds = get_todays_meds()
    checkin = checkin_context_for_prompt()
    return f"BP Status: {bp}\n\nMedications today:\n{meds}\n\nToday's schedule load: {checkin}"


# ─── Daily Check-in ──────────────────────────────────────────

def log_checkin(busy: bool, notes: str = "") -> dict:
    """Log whether today is a busy day, with optional context."""
    row = _db().table("health_logs").insert({
        "log_type": "checkin",
        "value": {"busy": busy, "notes": notes},
    }).execute()
    return row.data[0] if row.data else {}


def get_todays_checkin() -> dict | None:
    """Return today's check-in if it exists."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    result = (
        _db().table("health_logs")
        .select("value, logged_at")
        .eq("log_type", "checkin")
        .gte("logged_at", today_start)
        .order("logged_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def checkin_context_for_prompt() -> str:
    """Return a one-line checkin summary for the system prompt."""
    checkin = get_todays_checkin()
    if not checkin:
        return "NOT CHECKED IN YET — ask the user if today is a busy day."
    busy = checkin["value"].get("busy")
    notes = checkin["value"].get("notes", "")
    label = "BUSY DAY" if busy else "LIGHTER DAY"
    return f"{label}{(' — ' + notes) if notes else ''}"


# ─── Mood Analysis & Prediction ───────────────────────────────

def get_recent_logs(log_type: str, days: int = 14) -> list[dict]:
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    result = (
        _db().table("health_logs")
        .select("value, notes, logged_at")
        .eq("log_type", log_type)
        .gte("logged_at", since)
        .order("logged_at", desc=True)
        .execute()
    )
    return result.data or []


def analyze_mood_patterns(days: int = 14) -> dict:
    """
    Analyze mood, symptom, sleep, BP, and medication logs over the past N days.
    Returns a structured insights dict with patterns, correlations, and recommendations.
    """
    moods = get_recent_logs("mood", days)
    symptoms = get_recent_logs("symptom", days)
    sleep_logs = get_recent_logs("sleep", days)
    bp_logs = get_recent_bp(days)

    # Check medication adherence per day
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = (today_start - timedelta(days=7)).isoformat()
    med_logs = (
        _db().table("medication_logs")
        .select("taken_at")
        .gte("taken_at", week_start)
        .execute()
        .data or []
    )
    days_with_meds = {log["taken_at"][:10] for log in med_logs}

    # ── Day-of-week mood pattern ──
    dow_moods: dict[str, list[str]] = {}
    for m in moods:
        dt = datetime.fromisoformat(m["logged_at"].replace("Z", "+00:00"))
        dow = dt.strftime("%A")
        note = m["value"].get("notes", "")
        if note:
            dow_moods.setdefault(dow, []).append(note.lower())

    # ── Symptom frequency ──
    symptom_counts: dict[str, int] = {}
    for s in symptoms:
        name = s["value"].get("name", "unknown")
        symptom_counts[name] = symptom_counts.get(name, 0) + 1

    # ── Sleep vs mood correlation ──
    sleep_mood_pairs = []
    for sl in sleep_logs:
        sl_date = sl["logged_at"][:10]
        sl_hours = sl["value"].get("hours", 0)
        # find mood on same day
        for m in moods:
            if m["logged_at"][:10] == sl_date:
                mood_note = m["value"].get("notes", "")
                score = m["value"].get("score")
                sleep_mood_pairs.append({
                    "hours": sl_hours,
                    "mood": mood_note,
                    "score": score,
                    "date": sl_date,
                })

    # ── BP vs mood correlation ──
    bp_mood_pairs = []
    for bp in bp_logs:
        bp_date = bp["logged_at"][:10]
        sys_val = bp["value"].get("systolic", 0)
        for m in moods:
            if m["logged_at"][:10] == bp_date:
                bp_mood_pairs.append({
                    "systolic": sys_val,
                    "mood": m["value"].get("notes", ""),
                    "date": bp_date,
                })

    # ── Missed meds vs bad mood ──
    bad_mood_days = set()
    for m in moods:
        note = m["value"].get("notes", "").lower()
        score = m["value"].get("score")
        if any(w in note for w in ("anxious", "tired", "low", "bad", "sad", "stress", "exhausted", "drained")):
            bad_mood_days.add(m["logged_at"][:10])
        elif score is not None and score <= 4:
            bad_mood_days.add(m["logged_at"][:10])

    missed_med_on_bad_day = [d for d in bad_mood_days if d not in days_with_meds]

    return {
        "total_mood_logs": len(moods),
        "total_symptom_logs": len(symptoms),
        "dow_moods": dow_moods,
        "symptom_counts": symptom_counts,
        "sleep_mood_pairs": sleep_mood_pairs,
        "bp_mood_pairs": bp_mood_pairs,
        "bad_mood_days": sorted(bad_mood_days),
        "missed_med_on_bad_day": missed_med_on_bad_day,
        "recent_moods": [
            {
                "date": m["logged_at"][:10],
                "day": datetime.fromisoformat(m["logged_at"].replace("Z", "+00:00")).strftime("%A"),
                "notes": m["value"].get("notes", ""),
                "score": m["value"].get("score"),
            }
            for m in moods[:7]
        ],
    }


def predict_today_mood(patterns: dict) -> dict:
    """
    Based on analyzed patterns, predict how the user might feel today
    and generate personalized recommendations.
    """
    today = datetime.now()
    today_dow = today.strftime("%A")
    today_str = today.strftime("%Y-%m-%d")

    # Find what moods were logged on same day-of-week historically
    historical_moods_today_dow = patterns["dow_moods"].get(today_dow, [])

    # Determine mood tendency for today
    negative_keywords = {"anxious", "tired", "low", "bad", "sad", "stressed", "exhausted", "drained", "headache", "pain"}
    positive_keywords = {"good", "great", "happy", "energetic", "calm", "refreshed", "motivated", "productive"}

    neg_count = sum(
        1 for mood in historical_moods_today_dow
        if any(kw in mood for kw in negative_keywords)
    )
    pos_count = sum(
        1 for mood in historical_moods_today_dow
        if any(kw in mood for kw in positive_keywords)
    )

    if not historical_moods_today_dow:
        tendency = "unknown"
        confidence = "low"
    elif neg_count > pos_count:
        tendency = "low"
        confidence = "medium" if neg_count >= 2 else "low"
    elif pos_count > neg_count:
        tendency = "good"
        confidence = "medium" if pos_count >= 2 else "low"
    else:
        tendency = "mixed"
        confidence = "low"

    # Check if today was a bad mood day historically
    missed_meds_recently = len(patterns["missed_med_on_bad_day"]) > 0

    # Build personalized recommendations based on actual patterns
    recommendations = []

    # Sleep-based
    for pair in patterns["sleep_mood_pairs"]:
        if pair["hours"] and pair["hours"] >= 7:
            mood_note = pair.get("mood", "").lower()
            if any(kw in mood_note for kw in positive_keywords):
                recommendations.append("You feel better on days after 7+ hours of sleep — try to rest early tonight.")
                break

    # BP-based
    elevated_bp_bad_mood = [
        p for p in patterns["bp_mood_pairs"]
        if p["systolic"] > 130 and any(kw in p["mood"].lower() for kw in negative_keywords)
    ]
    if elevated_bp_bad_mood:
        recommendations.append("High BP tends to correlate with your low-mood days — monitor your stress levels today.")

    # Missed meds
    if missed_meds_recently:
        recommendations.append("You've had bad mood days when medications were missed — make sure to take them on time today.")

    # Most common symptoms
    top_symptoms = sorted(patterns["symptom_counts"].items(), key=lambda x: x[1], reverse=True)[:2]
    for sym, count in top_symptoms:
        if count >= 2:
            recommendations.append(f"You've logged {sym} {count} times recently — watch out for it today.")

    # Day-of-week pattern
    if tendency == "low" and confidence in ("medium",):
        recommendations.append(
            f"Historically, {today_dow}s tend to be harder for you. "
            "Consider blocking some quiet time in your schedule."
        )
    elif tendency == "good" and confidence in ("medium",):
        recommendations.append(
            f"You tend to feel good on {today_dow}s — a great day to tackle demanding tasks."
        )

    # Fallback
    if not recommendations:
        recommendations.append("Stay hydrated, take your medications on time, and check in with how you're feeling later.")

    return {
        "today_dow": today_dow,
        "predicted_tendency": tendency,
        "confidence": confidence,
        "historical_moods_this_dow": historical_moods_today_dow,
        "recommendations": recommendations,
    }


def mood_analysis_for_prompt() -> str:
    """Return a concise mood analysis block for the system prompt."""
    try:
        patterns = analyze_mood_patterns(days=14)

        if patterns["total_mood_logs"] == 0:
            return "No mood data yet. Ask the user how they're feeling and encourage them to log it."

        recent = patterns["recent_moods"]
        recent_str = ", ".join(
            f"{m['day'][:3]}: {m['notes'] or ('score '+str(m['score']))}"
            for m in recent[:5]
            if m["notes"] or m["score"] is not None
        ) or "No recent moods logged."

        prediction = predict_today_mood(patterns)
        tendency_map = {
            "low": "likely low energy / stressed",
            "good": "likely positive / energetic",
            "mixed": "mixed — could go either way",
            "unknown": "insufficient data to predict",
        }
        tendency_str = tendency_map.get(prediction["predicted_tendency"], "unknown")

        top_symptoms = sorted(patterns["symptom_counts"].items(), key=lambda x: x[1], reverse=True)[:3]
        symptoms_str = ", ".join(f"{s} ({c}x)" for s, c in top_symptoms) if top_symptoms else "None logged"

        recs = "\n".join(f"  • {r}" for r in prediction["recommendations"][:3])

        return (
            f"Recent mood (last 5 logs): {recent_str}\n"
            f"Today ({prediction['today_dow']}) prediction: {tendency_str} (confidence: {prediction['confidence']})\n"
            f"Frequent symptoms: {symptoms_str}\n"
            f"Personalized recommendations:\n{recs}"
        )
    except Exception:
        return "Mood analysis unavailable."
