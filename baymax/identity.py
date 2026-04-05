"""
identity.py — Load and format the user's identity profile for system prompt injection.
"""
from pathlib import Path
import yaml

PROFILE_PATH = Path(__file__).parent.parent / "data" / "identity_profile.yaml"


def load_profile() -> dict:
    with open(PROFILE_PATH, "r") as f:
        return yaml.safe_load(f)


def _list(items) -> str:
    if not items:
        return "None"
    return ", ".join(str(i) for i in items if i)


def format_for_prompt() -> str:
    p = load_profile()

    personal     = p.get("personal", {})
    professional = p.get("professional", {})
    health       = p.get("health", {})
    emergency    = p.get("emergency", {})

    name = personal.get("preferred_name", "the user")

    # ── Personal ──────────────────────────────────────────────
    personal_block = (
        f"Name: {personal.get('full_name', '')}\n"
        f"Age: {personal.get('age', '')}\n"
        f"Gender: {personal.get('gender', '')}\n"
        f"Location: {personal.get('location', '')} ({personal.get('timezone', '')})"
    )

    # ── Professional ──────────────────────────────────────────
    projects = professional.get("current_projects", [])
    projects_str = "\n".join(
        f"  - {proj['name']}: {proj.get('description', '')} (deadline: {proj.get('deadline', 'TBD')})"
        for proj in projects if proj.get("name")
    ) or "  None listed"

    goals = professional.get("goals_this_year", [])
    goals_str = "\n".join(f"  - {g}" for g in goals if g) or "  None listed"

    professional_block = (
        f"Role: {professional.get('current_role', '')} at {professional.get('company', '')}\n"
        f"Domain: {professional.get('domain', '')}\n"
        f"Working hours: {professional.get('working_hours', '')}\n"
        f"Current Projects:\n{projects_str}\n"
        f"Goals This Year:\n{goals_str}"
    )

    # ── Health Chip ───────────────────────────────────────────
    allergies     = health.get("allergies", {}) or {}
    food_allergy  = _list(allergies.get("food", []))
    drug_allergy  = _list(allergies.get("drug", []))
    env_allergy   = _list(allergies.get("environmental", []))
    other_allergy = _list(allergies.get("other", []))

    conditions    = _list(health.get("conditions", []))
    surgeries     = _list(health.get("past_surgeries", []))
    injuries      = _list(health.get("past_injuries", []))
    family_hx     = _list(health.get("family_history", []))
    supplements   = _list(health.get("supplements", []))

    meds = health.get("medications", []) or []
    meds_lines = [
        f"  - {m['name']} {m.get('dose','')} {m.get('frequency','')} ({m.get('purpose','')})"
        for m in meds if m.get("name")
    ]
    meds_str = "\n".join(meds_lines) or "  None listed"

    health_block = (
        f"Blood type: {health.get('blood_type', 'Unknown')}\n"
        f"Height: {health.get('height_cm', '')} cm  |  Weight: {health.get('weight_kg', '')} kg\n"
        f"Target BP: {health.get('bp_target', '120/80')}  |  Resting HR: {health.get('resting_heart_rate', '')} bpm\n"
        f"Sleep goal: {health.get('sleep_goal_hours', '')} hrs\n\n"
        f"Allergies:\n"
        f"  Food: {food_allergy}\n"
        f"  Drug: {drug_allergy}\n"
        f"  Environmental: {env_allergy}\n"
        f"  Other: {other_allergy}\n\n"
        f"Conditions: {conditions}\n"
        f"Past surgeries: {surgeries}\n"
        f"Past injuries: {injuries}\n"
        f"Family history: {family_hx}\n\n"
        f"Current medications:\n{meds_str}\n"
        f"Supplements: {supplements}\n\n"
        f"Diet: {health.get('diet', '')}\n"
        f"Exercise: {health.get('exercise_frequency', '')}\n"
        f"Cycle avg: {health.get('cycle_length_avg', '')} days  |  Period avg: {health.get('period_duration_avg', '')} days\n\n"
        f"Doctor: {health.get('doctor_name', '')}  {health.get('doctor_contact', '')}\n"
        f"Specialist: {health.get('specialist', '')}\n"
        f"Hospital: {health.get('hospital', '')}"
    )

    # ── Emergency ─────────────────────────────────────────────
    emergency_block = (
        f"Emergency contact: {emergency.get('emergency_contact_name', '')} "
        f"({emergency.get('emergency_contact_relation', '')}) — {emergency.get('emergency_contact_phone', '')}\n"
        f"Critical info: {emergency.get('critical_info', 'None')}"
    )

    return (
        f"## About {name}\n{personal_block}\n\n"
        f"## Professional\n{professional_block}\n\n"
        f"## Health Chip\n{health_block}\n\n"
        f"## Emergency Info\n{emergency_block}"
    )


def get_preferred_name() -> str:
    p = load_profile()
    return p.get("personal", {}).get("preferred_name", "friend")


def get_communication_style() -> str:
    p = load_profile()
    return p.get("preferences", {}).get("communication_style", "direct and concise")
