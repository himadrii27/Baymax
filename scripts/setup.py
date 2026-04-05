"""
setup.py — Guided onboarding for Baymax.

Commands:
  python scripts/setup.py              # full onboarding wizard
  python scripts/setup.py --add-med   # add a medication
  python scripts/setup.py --connect-calendar  # Google Calendar OAuth
  python scripts/setup.py --test      # test all connections
"""
import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel

console = Console()


def run_setup():
    console.print(Panel(
        "[bold cyan]Welcome to Baymax Setup![/bold cyan]\n"
        "Let's get you configured in a few steps.",
        border_style="cyan"
    ))

    _check_env()
    _onboard_identity()
    if Confirm.ask("Connect Google Calendar?", default=False):
        connect_calendar()
    if Confirm.ask("Add your first medication?", default=False):
        add_medication()
    _test_connections()

    console.print("\n[bold green]✓ Setup complete![/bold green] Run [bold]python main.py[/bold] to start Baymax.")


def _check_env():
    console.print("\n[bold]Step 1: API Keys[/bold]")
    env_path = Path(__file__).parent.parent / ".env"

    required = {
        "ANTHROPIC_API_KEY": "Anthropic API key (from console.anthropic.com)",
        "SUPABASE_URL": "Supabase project URL (from Supabase dashboard)",
        "SUPABASE_KEY": "Supabase service role key",
        "SUPABASE_DB_URL": "Supabase DB connection string (for Mem0 pgvector)",
        "VOYAGE_API_KEY": "Voyage AI API key (from voyageai.com — for memory embeddings)",
    }

    lines = []
    missing = []
    for key, description in required.items():
        val = os.environ.get(key, "")
        if val:
            console.print(f"  [green]✓[/green] {key}")
        else:
            console.print(f"  [red]✗[/red] {key} — {description}")
            new_val = Prompt.ask(f"  Enter {key}", default="", password="KEY" in key)
            if new_val:
                lines.append(f"{key}={new_val}")
                missing.append(key)
            else:
                console.print(f"  [yellow]Skipping {key} — some features won't work[/yellow]")

    if lines:
        with open(env_path, "a") as f:
            f.write("\n" + "\n".join(lines) + "\n")
        console.print(f"[green]✓ Saved {len(lines)} key(s) to .env[/green]")


def _onboard_identity():
    console.print("\n[bold]Step 2: Your Identity Profile[/bold]")
    import yaml
    profile_path = Path(__file__).parent.parent / "data" / "identity_profile.yaml"

    with open(profile_path) as f:
        profile = yaml.safe_load(f)

    fields = [
        ("personal.full_name", "Your full name"),
        ("personal.preferred_name", "What should Baymax call you?"),
        ("personal.age", "Your age"),
        ("personal.location", "Your city and country"),
        ("personal.timezone", "Your timezone (e.g. Asia/Kolkata, America/New_York)"),
        ("professional.current_role", "Your current job/role"),
        ("professional.company", "Company or project name"),
    ]

    for path, label in fields:
        keys = path.split(".")
        current = profile
        for k in keys:
            current = current.get(k, {}) if isinstance(current, dict) else ""
        current_val = current if isinstance(current, str) else ""

        new_val = Prompt.ask(f"  {label}", default=current_val)
        if new_val:
            node = profile
            for k in keys[:-1]:
                node = node[k]
            node[keys[-1]] = new_val

    # Health conditions
    cond_str = Prompt.ask("  Any health conditions? (comma-separated, or leave blank)", default="")
    if cond_str:
        profile["health"]["conditions"] = [c.strip() for c in cond_str.split(",")]

    bp_target = Prompt.ask("  Target blood pressure (e.g. 120/80)", default="120/80")
    profile["health"]["bp_target"] = bp_target

    with open(profile_path, "w") as f:
        yaml.dump(profile, f, default_flow_style=False, allow_unicode=True)

    console.print("[green]✓ Identity profile saved.[/green]")


def connect_calendar():
    console.print("\n[bold]Connecting Google Calendar[/bold]")
    creds_path = Path(__file__).parent.parent / "data" / "google_credentials.json"

    if not creds_path.exists():
        console.print(
            "  1. Go to [link]https://console.cloud.google.com[/link]\n"
            "  2. Create a project → Enable Google Calendar API\n"
            "  3. Create OAuth 2.0 credentials (Desktop app)\n"
            "  4. Download credentials.json and save it to:\n"
            f"     [bold]{creds_path}[/bold]"
        )
        if not Confirm.ask("  Done? Continue?", default=False):
            return

    try:
        from baymax.calendar_client import get_events_today
        events = get_events_today()
        console.print(f"[green]✓ Google Calendar connected! Found {len(events)} event(s) today.[/green]")
    except Exception as e:
        console.print(f"[red]Calendar connection failed:[/red] {e}")


def add_medication():
    console.print("\n[bold]Add a Medication[/bold]")

    load_dotenv(Path(__file__).parent.parent / ".env")
    from supabase import create_client
    db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    name = Prompt.ask("  Medication name (e.g. Metoprolol)")
    dosage = Prompt.ask("  Dosage (e.g. 50mg)", default="")
    times_str = Prompt.ask("  Scheduled times, comma-separated (e.g. 08:00, 20:00)", default="")
    times = [t.strip() for t in times_str.split(",") if t.strip()] if times_str else []
    notes = Prompt.ask("  Notes (optional)", default="")

    db.table("medications").insert({
        "name": name,
        "dosage": dosage,
        "schedule_times": times,
        "notes": notes,
    }).execute()

    console.print(f"[green]✓ {name} {dosage} added. Scheduled: {', '.join(times) or 'No schedule set'}[/green]")


def _test_connections():
    console.print("\n[bold]Testing connections...[/bold]")

    # Test Anthropic
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        client.models.list()
        console.print("  [green]✓[/green] Anthropic API")
    except Exception as e:
        console.print(f"  [red]✗[/red] Anthropic API: {e}")

    # Test Supabase
    try:
        from supabase import create_client
        db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
        db.table("tasks").select("id").limit(1).execute()
        console.print("  [green]✓[/green] Supabase")
    except Exception as e:
        console.print(f"  [red]✗[/red] Supabase: {e}")
        console.print("  [dim]→ Run the SQL in supabase/migrations/001_schema.sql in your Supabase SQL editor[/dim]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--add-med", action="store_true")
    parser.add_argument("--connect-calendar", action="store_true")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    if args.add_med:
        load_dotenv(Path(__file__).parent.parent / ".env")
        add_medication()
    elif args.connect_calendar:
        connect_calendar()
    elif args.test:
        load_dotenv(Path(__file__).parent.parent / ".env")
        _test_connections()
    else:
        run_setup()
