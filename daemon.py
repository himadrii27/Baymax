"""
daemon.py — Baymax always-on background daemon.

Runs continuously in the background:
  - Voice loop: "Hey Baymax" wake word always listening
  - Daily briefing at configured time (default 7:00am)
  - Medication reminders at scheduled times
  - Auto-restarts voice loop on crash (never dies silently)

Managed by macOS Launch Agent — starts on login, restarts on crash.
Logs to: ~/Library/Logs/baymax.log

Usage (via install script):
  python scripts/install_daemon.py   # install + start
  python scripts/baymax_ctl.py start/stop/restart/status/logs
"""
import os
import sys
import time
import signal
import logging
import threading
from pathlib import Path
from datetime import datetime

# ── Bootstrap: load .env before anything else ──────────────────
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

# ── Logging to file ────────────────────────────────────────────
LOG_PATH = Path.home() / "Library" / "Logs" / "baymax.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("baymax.daemon")

PID_FILE = Path(__file__).parent / ".baymax.pid"
VOICE_RESTART_DELAY = 5   # seconds between voice crash restarts
MAX_VOICE_RESTARTS = 10   # give up after this many consecutive crashes


def write_pid() -> None:
    PID_FILE.write_text(str(os.getpid()))


def cleanup_pid() -> None:
    PID_FILE.unlink(missing_ok=True)


def handle_shutdown(signum, frame):
    log.info("Baymax daemon shutting down (signal %d).", signum)
    cleanup_pid()
    sys.exit(0)


# ── Background: briefing + med reminders ──────────────────────

def start_schedulers() -> None:
    """Run daily briefing and medication reminders in a background thread."""
    def _run():
        try:
            from baymax.briefing import schedule_briefing, schedule_med_reminders
            import schedule as sched
            import time as t

            log.info("Starting briefing and medication reminder schedulers.")
            schedule_briefing("07:00")
            schedule_med_reminders()

            while True:
                sched.run_pending()
                t.sleep(30)
        except Exception as e:
            log.error("Scheduler crashed: %s", e)

    t = threading.Thread(target=_run, daemon=True, name="baymax-scheduler")
    t.start()
    log.info("Scheduler thread started.")


# ── Voice loop with auto-restart ──────────────────────────────

def run_voice_loop() -> None:
    """
    Run the voice interface. On crash, wait and restart automatically.
    Gives up after MAX_VOICE_RESTARTS consecutive crashes.
    """
    consecutive_crashes = 0

    while consecutive_crashes < MAX_VOICE_RESTARTS:
        try:
            log.info("Starting voice loop (attempt %d).", consecutive_crashes + 1)
            from baymax.voice import VoiceInterface
            voice = VoiceInterface()
            log.info("Voice interface ready. Listening for 'Hey Baymax' and distress words...")
            voice.run()

            # If run() returned cleanly (e.g. "goodbye"), don't treat as crash
            log.info("Voice loop exited cleanly.")
            consecutive_crashes = 0
            time.sleep(2)

        except KeyboardInterrupt:
            log.info("Voice loop interrupted by user.")
            break

        except Exception as e:
            consecutive_crashes += 1
            log.error(
                "Voice loop crashed (%d/%d): %s — restarting in %ds.",
                consecutive_crashes, MAX_VOICE_RESTARTS, e, VOICE_RESTART_DELAY,
            )
            time.sleep(VOICE_RESTART_DELAY)

    if consecutive_crashes >= MAX_VOICE_RESTARTS:
        log.critical(
            "Voice loop crashed %d times consecutively. "
            "Check microphone permissions and dependencies. Daemon exiting.",
            MAX_VOICE_RESTARTS,
        )
        cleanup_pid()
        sys.exit(1)


# ── Main ──────────────────────────────────────────────────────

def main() -> None:
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    write_pid()
    log.info("=" * 60)
    log.info("Baymax daemon starting. PID: %d", os.getpid())
    log.info("Log file: %s", LOG_PATH)
    log.info("=" * 60)

    # Validate required env vars
    required = ["ANTHROPIC_API_KEY", "SUPABASE_URL", "SUPABASE_KEY"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        log.critical("Missing required env vars: %s — run 'python scripts/setup.py' first.", missing)
        sys.exit(1)

    # Start schedulers in background
    start_schedulers()

    # Run voice loop (blocking, with auto-restart)
    run_voice_loop()


if __name__ == "__main__":
    main()
