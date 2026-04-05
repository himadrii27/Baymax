"""
main.py — Baymax CLI entrypoint.

Usage:
  python main.py              # text chat mode
  python main.py --voice      # voice mode (Hey Baymax wake word)
  python main.py --briefing   # run morning briefing now
  python main.py --setup      # run onboarding setup
"""
import sys
import os
import warnings
import argparse
from pathlib import Path
from dotenv import load_dotenv

warnings.filterwarnings("ignore", category=DeprecationWarning)

load_dotenv(Path(__file__).parent / ".env")

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich import print as rprint
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style

from baymax import brain, health, tasks, memory, cycle
from baymax.commands import parse, CommandType

console = Console()
HISTORY_FILE = Path(__file__).parent / ".baymax_history"
BAYMAX_IMAGE = Path("/Users/himadrisinha/.claude/image-cache/cd98a004-3fff-4795-9719-302ac66161ca/1.png")

PROMPT_STYLE = Style.from_dict({
    "prompt": "ansicyan bold",
})

BANNER = """[bold cyan]
  ██████╗  █████╗ ██╗   ██╗███╗   ███╗ █████╗ ██╗  ██╗
  ██╔══██╗██╔══██╗╚██╗ ██╔╝████╗ ████║██╔══██╗╚██╗██╔╝
  ██████╔╝███████║ ╚████╔╝ ██╔████╔██║███████║ ╚███╔╝
  ██╔══██╗██╔══██║  ╚██╔╝  ██║╚██╔╝██║██╔══██║ ██╔██╗
  ██████╔╝██║  ██║   ██║   ██║ ╚═╝ ██║██║  ██║██╔╝ ██╗
  ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝
[/bold cyan]
[dim]Your personal healthcare companion[/dim]
[dim]Type [bold]help[/bold] for commands, [bold]quit[/bold] to exit[/dim]
"""


def display_baymax_image() -> None:
    """Display Baymax image in terminal. Tries iTerm2 protocol first, falls back to block art."""
    if not BAYMAX_IMAGE.exists():
        return

    # Try iTerm2 inline image protocol (only in supported terminals)
    term_program = os.environ.get("TERM_PROGRAM", "")
    if term_program in ("iTerm.app", "WarpTerminal", "ghostty"):
        try:
            import base64
            data = base64.b64encode(BAYMAX_IMAGE.read_bytes()).decode()
            sys.stdout.write(f"\033]1337;File=inline=1;width=20;preserveAspectRatio=1:{data}\a\n")
            sys.stdout.flush()
            return
        except Exception:
            pass

    # Fallback: Pillow block art
    try:
        from PIL import Image as PILImage
        img = PILImage.open(BAYMAX_IMAGE).convert("RGBA")
        w, h = 36, 18
        img = img.resize((w, h))
        lines = []
        for y in range(h):
            row = ""
            for x in range(w):
                r, g, b, a = img.getpixel((x, y))
                if a < 80:
                    row += "  "
                else:
                    row += f"\x1b[48;2;{r};{g};{b}m  \x1b[0m"
            lines.append(row)
        print("\n".join(lines))
    except Exception:
        pass  # Image display is non-critical


def handle_command(cmd, user_input: str) -> bool:
    """
    Execute a parsed command. Returns True if command was fully handled
    (no need to send to Claude), False if Claude should still respond.
    """
    if cmd.type == CommandType.REMEMBER:
        memory.add_explicit(cmd.data["fact"])
        console.print(f"[green]✓ Remembered:[/green] {cmd.data['fact']}")
        return True

    if cmd.type == CommandType.FORGET:
        mems = memory.search(cmd.data["query"], limit=3)
        if not mems:
            console.print("[yellow]No matching memory found.[/yellow]")
            return True
        for m in mems:
            memory.forget(m["id"])
        console.print(f"[green]✓ Forgotten {len(mems)} memory/memories.[/green]")
        return True

    if cmd.type == CommandType.LIST_MEMORIES:
        mems = memory.list_all()
        if not mems:
            console.print("[dim]No memories stored yet.[/dim]")
            return True
        console.print(Panel(
            "\n".join(f"[dim]{i}.[/dim] {m['memory']}" for i, m in enumerate(mems, 1)),
            title="[bold]My Memories[/bold]",
            border_style="cyan",
        ))
        return True

    if cmd.type == CommandType.ADD_TASK:
        t = tasks.add_task(cmd.data["title"])
        console.print(f"[green]✓ Task added:[/green] {t.get('title', cmd.data['title'])}")
        return True

    if cmd.type == CommandType.LIST_TASKS:
        task_list = tasks.format_for_prompt()
        console.print(Panel(task_list, title="[bold]Open Tasks[/bold]", border_style="cyan"))
        return True

    if cmd.type == CommandType.DONE_TASK:
        result = tasks.complete_task_by_num(cmd.data["task_num"])
        console.print(f"[green]✓ {result}[/green]")
        return True

    if cmd.type == CommandType.BRIEFING:
        from baymax.briefing import run_briefing
        run_briefing(speak=False)
        return True

    # Health commands — log silently, then let Claude respond with context
    if cmd.type == CommandType.LOG_BP:
        health.log_bp(cmd.data["systolic"], cmd.data["diastolic"])
        console.print(f"[green]✓ BP logged:[/green] {cmd.data['systolic']}/{cmd.data['diastolic']}")
        return False  # let Claude also comment on it

    if cmd.type == CommandType.LOG_MED:
        result = health.log_medication(cmd.data["name"], cmd.data.get("dose", ""))
        console.print(f"[green]✓ Medication logged:[/green] {result.get('medication', cmd.data['name'])}")
        return False

    if cmd.type == CommandType.LOG_MOOD:
        health.log_mood(cmd.data["notes"])
        console.print(f"[green]✓ Mood logged:[/green] {cmd.data['notes']}")
        return False

    if cmd.type == CommandType.LOG_WEIGHT:
        health.log_weight(cmd.data["kg"])
        console.print(f"[green]✓ Weight logged:[/green] {cmd.data['kg']} kg")
        return False

    if cmd.type == CommandType.LOG_SYMPTOM:
        health.log_symptom(cmd.data["name"])
        console.print(f"[green]✓ Symptom logged:[/green] {cmd.data['name']}")
        return False

    if cmd.type == CommandType.LOG_CHECKIN:
        busy = cmd.data["busy"]
        health.log_checkin(busy=busy, notes=cmd.data.get("notes", ""))
        label = "Busy day" if busy else "Lighter day"
        console.print(f"[green]✓ Check-in logged:[/green] {label}")
        return False  # let Claude respond with tailored advice

    if cmd.type == CommandType.PERIOD_START:
        result = cycle.log_period_start()
        if result:
            console.print("[green]✓ Period start logged.[/green]")
        return False  # let Claude respond warmly

    if cmd.type == CommandType.PERIOD_END:
        result = cycle.log_period_end()
        if "error" in result:
            console.print(f"[yellow]{result['error']}[/yellow]")
            return True
        console.print("[green]✓ Period end logged.[/green]")
        return False

    if cmd.type == CommandType.PERIOD_LOG:
        cycle.log_daily(
            flow=cmd.data.get("flow"),
            symptoms=cmd.data.get("symptoms", []),
            notes=cmd.data.get("notes", ""),
        )
        parts = []
        if cmd.data.get("flow"):
            parts.append(f"flow: {cmd.data['flow']}")
        if cmd.data.get("symptoms"):
            parts.append(f"symptoms: {', '.join(cmd.data['symptoms'])}")
        console.print(f"[green]✓ Period log saved:[/green] {', '.join(parts) or 'logged'}")
        return False

    if cmd.type == CommandType.PERIOD_QUERY:
        _print_cycle_summary()
        return True

    return False


def _print_cycle_summary() -> None:
    """Print a formatted cycle summary panel."""
    from baymax.cycle import predict_next_period, predict_pms_window, predict_ovulation_window, get_common_symptoms, is_currently_on_period, _get_open_cycle
    from datetime import date

    pred = predict_next_period()
    if "error" in pred:
        console.print("[yellow]No cycle data yet. Say 'my period started today' to begin tracking.[/yellow]")
        return

    pms = predict_pms_window()
    ov = predict_ovulation_window()
    top_symptoms = list(get_common_symptoms().items())[:5]

    lines = []
    if is_currently_on_period():
        open_c = _get_open_cycle()
        start = date.fromisoformat(open_c["start_date"])
        day_num = (date.today() - start).days + 1
        lines.append(f"[bold red]● On period[/bold red] — Day {day_num}")
    else:
        lines.append(f"[dim]Not currently on period[/dim]")

    lines.append(f"\n[bold]Next period:[/bold] {pred['next_period_date']} ({pred['days_until']} days away)")
    lines.append(f"[bold]Avg cycle:[/bold] {pred['avg_cycle_length']} days | [bold]Avg duration:[/bold] {pred['avg_period_length']} days")
    lines.append(f"[bold]PMS window:[/bold] {pms['pms_start']} → {pms['pms_end']}")
    lines.append(f"[bold]Fertile window:[/bold] {ov['fertile_window_start']} → {ov['fertile_window_end']}")
    lines.append(f"[bold]Ovulation:[/bold] ~{ov['ovulation_date']}")
    if top_symptoms:
        lines.append(f"\n[bold]Your common symptoms:[/bold] {', '.join(s for s, _ in top_symptoms)}")

    console.print(Panel("\n".join(lines), title="[bold cyan]Cycle Summary[/bold cyan]", border_style="cyan"))


def stream_to_console(text: str) -> None:
    """Print streamed text chunks directly to stdout (no newline buffering)."""
    print(text, end="", flush=True)


def chat_loop() -> None:
    session = PromptSession(
        history=FileHistory(str(HISTORY_FILE)),
        auto_suggest=AutoSuggestFromHistory(),
        style=PROMPT_STYLE,
    )

    display_baymax_image()
    console.print(BANNER)
    console.print("[bold cyan]Baymax:[/bold cyan] Hello Himadri! I am Baymax, your personal healthcare companion.")
    console.print("[bold cyan]Baymax:[/bold cyan] How are you feeling today?\n")

    while True:
        try:
            user_input = session.prompt("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Baymax: Goodbye. Take care of yourself.[/dim]")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "bye", "goodbye"):
            console.print("[bold cyan]Baymax:[/bold cyan] Goodbye! Remember to take your medications. Take care!")
            break

        if user_input.lower() == "help":
            _print_help()
            continue

        if user_input.lower() == "reset":
            brain.reset_session()
            console.print("[dim]Session reset. Starting fresh.[/dim]")
            continue

        # Parse for special commands
        cmd = parse(user_input)
        fully_handled = handle_command(cmd, user_input)

        if fully_handled:
            continue

        # Send to Claude and stream response
        console.print()
        console.print("[bold cyan]Baymax:[/bold cyan] ", end="")
        try:
            brain.chat(user_input, stream_callback=stream_to_console)
            print()  # newline after streamed response
            console.print()
        except Exception as e:
            console.print(f"\n[red]Error:[/red] {e}")
            console.print("[dim]Check your API keys in .env[/dim]")


def _print_help() -> None:
    console.print(Panel(
        """[bold]Health Commands[/bold]
  BP was 120 over 80           → logs blood pressure
  took my metoprolol           → logs medication
  I'm feeling tired today      → logs mood/symptom
  weighed 72 kg                → logs weight

[bold]Memory Commands[/bold]
  remember: I prefer mornings  → stores explicit memory
  forget: [topic]              → removes matching memory
  list memories                → shows all stored memories

[bold]Task Commands[/bold]
  add task: Buy groceries      → creates a task
  list tasks                   → shows open tasks
  done task 1                  → marks task #1 complete

[bold]Other[/bold]
  briefing                     → run morning briefing now
  reset                        → clear session history
  quit / exit                  → goodbye""",
        title="[bold]Baymax Commands[/bold]",
        border_style="cyan",
    ))


def voice_loop() -> None:
    try:
        from baymax.voice import VoiceInterface
    except ImportError:
        console.print("[red]Voice dependencies not installed.[/red]")
        console.print("Run: pip install RealtimeSTT openwakeword piper-tts pyaudio")
        return

    display_baymax_image()
    console.print(BANNER)
    console.print("[bold cyan]Voice mode active.[/bold cyan] Say [bold]'Hey Baymax'[/bold] to wake me up.\n")
    voice = VoiceInterface()
    voice.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Baymax — Personal AI Healthcare Companion")
    parser.add_argument("--voice", action="store_true", help="Enable voice mode")
    parser.add_argument("--briefing", action="store_true", help="Run morning briefing")
    parser.add_argument("--setup", action="store_true", help="Run onboarding setup")
    args = parser.parse_args()

    if args.setup:
        from scripts.setup import run_setup
        run_setup()
    elif args.briefing:
        from baymax.briefing import run_briefing
        run_briefing(speak=args.voice)
    elif args.voice:
        voice_loop()
    else:
        chat_loop()


if __name__ == "__main__":
    main()
