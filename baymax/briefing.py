"""
briefing.py — Daily morning briefing.

Generates a personalized morning summary:
  - Today's calendar events
  - Open tasks (priority order)
  - Health status (BP trend, meds due)
  - A motivational nudge from Baymax

Run manually: python main.py --briefing
Auto-schedule: configure your OS cron or run schedule_briefing()
"""
import os
import schedule
import time
import threading
from datetime import datetime
from rich.console import Console
from rich.panel import Panel

console = Console()


def generate_briefing_text() -> str:
    from baymax import identity, health, tasks
    from baymax.calendar_client import get_today_summary
    from baymax.health import analyze_mood_patterns, predict_today_mood
    from baymax.cycle import cycle_context_for_prompt, predict_pms_window, is_currently_on_period

    name = identity.get_preferred_name()
    now = datetime.now()
    greeting_time = "Good morning" if now.hour < 12 else "Good afternoon" if now.hour < 17 else "Good evening"

    calendar_str = get_today_summary()
    tasks_str = tasks.format_for_prompt()
    health_str = health.health_context_for_prompt()

    # Mood prediction
    mood_section = ""
    try:
        patterns = analyze_mood_patterns(days=14)
        if patterns["total_mood_logs"] > 0:
            prediction = predict_today_mood(patterns)
            tendency_emoji = {
                "low": "⚠️",
                "good": "✨",
                "mixed": "〰️",
                "unknown": "❓",
            }.get(prediction["predicted_tendency"], "❓")

            tendency_label = {
                "low": "Low energy / stressed day predicted",
                "good": "Positive / energetic day predicted",
                "mixed": "Mixed — keep an eye on how you feel",
                "unknown": "Not enough data yet",
            }.get(prediction["predicted_tendency"], "")

            recs = "\n".join(f"  • {r}" for r in prediction["recommendations"][:3])

            recent_moods = patterns["recent_moods"][:5]
            mood_trend = " → ".join(
                f"{m['day'][:3]}({m['notes'][:10] if m['notes'] else '?'})"
                for m in reversed(recent_moods)
                if m["notes"] or m["score"] is not None
            )

            mood_section = f"""
🧠 MOOD PREDICTION FOR TODAY ({prediction['today_dow'].upper()})
{tendency_emoji} {tendency_label} (confidence: {prediction['confidence']})

Mood trend: {mood_trend or 'No recent logs'}

What might help today:
{recs}
"""
    except Exception:
        pass

    # Cycle section
    cycle_section = ""
    try:
        pms = predict_pms_window()
        on_period = is_currently_on_period()
        if on_period:
            cycle_section = "\n🩸 CYCLE STATUS\nYou're on your period today. Take it easy — self-care first.\n"
        elif pms.get("in_pms_window"):
            cycle_section = (
                f"\n🌙 CYCLE STATUS\n"
                f"You're in your PMS window (period in {pms['days_to_period']} days). "
                f"Mood swings and fatigue are normal right now — be kind to yourself.\n"
            )
        elif pms.get("days_to_pms", 99) <= 3:
            cycle_section = (
                f"\n🌙 CYCLE STATUS\n"
                f"PMS window starts in {pms['days_to_pms']} days. "
                f"Stock up on comfort essentials if needed.\n"
            )
    except Exception:
        pass

    closing = _closing_nudge(mood_section)

    return f"""{greeting_time}, {name}!

Here's your daily briefing for {now.strftime('%A, %B %d')}:

📅 CALENDAR TODAY
{calendar_str}

✅ OPEN TASKS
{tasks_str}

❤️ HEALTH STATUS
{health_str}
{cycle_section}{mood_section}
{closing}
"""


def _closing_nudge(mood_section: str) -> str:
    """Return a contextual closing message based on mood prediction."""
    if "Low energy" in mood_section or "stressed" in mood_section:
        return "Today might be tough — be kind to yourself. Small wins count. 💙"
    elif "Positive" in mood_section or "energetic" in mood_section:
        return "You're set up for a great day. Make it count! 🌟"
    else:
        return "Remember to stay hydrated and take your medications on time. You've got this!"


def run_briefing(speak: bool = False) -> None:
    text = generate_briefing_text()
    console.print(Panel(text, title="[bold cyan]Baymax Morning Briefing[/bold cyan]", border_style="cyan"))

    if speak:
        try:
            from baymax.voice import VoiceInterface
            v = VoiceInterface()
            v.speak(text)
        except Exception as e:
            console.print(f"[yellow]Voice unavailable:[/yellow] {e}")

    _ask_busy_day(speak=speak)


def _ask_busy_day(speak: bool = False) -> None:
    """Ask if today is a busy day and log the response."""
    from baymax.health import get_todays_checkin, log_checkin

    # Don't ask again if already checked in today
    if get_todays_checkin():
        return

    question = "Is today going to be a busy day for you?"
    console.print(f"\n[bold cyan]Baymax:[/bold cyan] {question}")

    if speak:
        try:
            from baymax.voice import VoiceInterface
            v = VoiceInterface()
            v.speak(question)
            answer = v.listen()
            console.print(f"[dim]You:[/dim] {answer}")
        except Exception:
            answer = ""
    else:
        try:
            from prompt_toolkit import prompt
            answer = prompt("You: ").strip()
        except Exception:
            answer = ""

    if not answer:
        return

    # Detect yes/no from the answer
    busy_keywords = {"yes", "busy", "hectic", "packed", "back to back", "meetings", "slammed", "crazy", "full"}
    free_keywords = {"no", "not really", "quiet", "free", "chill", "light", "easy", "relaxed", "slow"}

    answer_lower = answer.lower()
    is_busy = any(kw in answer_lower for kw in busy_keywords)
    is_free = any(kw in answer_lower for kw in free_keywords)

    if is_busy or is_free:
        log_checkin(busy=is_busy, notes=answer)
        if is_busy:
            response = (
                "Got it — busy day ahead. I'll keep my check-ins brief. "
                "Remember to take short breaks and don't skip your meds!"
            )
        else:
            response = (
                "Nice — a lighter day. Good time to tackle something you've been putting off, "
                "or just recharge a bit."
            )
        console.print(f"[bold cyan]Baymax:[/bold cyan] {response}")
        if speak:
            try:
                v.speak(response)
            except Exception:
                pass
    else:
        # Ambiguous — store as-is with unknown busy state, let Claude handle it
        log_checkin(busy=False, notes=answer)


def _briefing_job() -> None:
    console.print("\n[bold cyan]⏰ Morning briefing time![/bold cyan]")
    run_briefing(speak=False)


def schedule_briefing(time_str: str = "07:00") -> None:
    """Schedule daily briefing at a given time (HH:MM). Runs in background thread."""
    schedule.every().day.at(time_str).do(_briefing_job)
    console.print(f"[dim]Daily briefing scheduled at {time_str}[/dim]")

    def _run():
        while True:
            schedule.run_pending()
            time.sleep(30)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def schedule_med_reminders() -> None:
    """Schedule medication reminders based on active meds in Supabase."""
    try:
        from supabase import create_client
        db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
        meds = db.table("medications").select("name, dosage, schedule_times").eq("active", True).execute().data or []

        for med in meds:
            for t in (med.get("schedule_times") or []):
                def _remind(med_name=med["name"], dose=med.get("dosage", "")):
                    console.print(f"\n[bold yellow]⏰ Medication Reminder:[/bold yellow] Time to take {med_name} {dose}")

                schedule.every().day.at(t).do(_remind)
                console.print(f"[dim]Reminder set for {med['name']} at {t}[/dim]")
    except Exception as e:
        console.print(f"[yellow]Could not schedule med reminders:[/yellow] {e}")
