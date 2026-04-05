"""
baymax_ctl.py — Control the Baymax background daemon.

Commands:
  python scripts/baymax_ctl.py start    — start the daemon
  python scripts/baymax_ctl.py stop     — stop the daemon
  python scripts/baymax_ctl.py restart  — restart the daemon
  python scripts/baymax_ctl.py status   — check if running
  python scripts/baymax_ctl.py logs     — tail the live log
  python scripts/baymax_ctl.py errors   — tail the error log
"""
import sys
import os
import signal
import subprocess
from pathlib import Path

PLIST_LABEL = "com.baymax.daemon"
PLIST_DEST = Path.home() / "Library" / "LaunchAgents" / "com.baymax.daemon.plist"
BAYMAX_DIR = Path(__file__).parent.parent.resolve()
PID_FILE = BAYMAX_DIR / ".baymax.pid"
LOG_FILE = Path.home() / "Library" / "Logs" / "baymax.log"
ERR_FILE = Path.home() / "Library" / "Logs" / "baymax_error.log"


def _launchctl(cmd: str) -> bool:
    result = subprocess.run(
        ["launchctl", cmd, str(PLIST_DEST)],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def _is_running() -> tuple[bool, str]:
    result = subprocess.run(
        ["launchctl", "list", PLIST_LABEL],
        capture_output=True, text=True,
    )
    running = result.returncode == 0 and PLIST_LABEL in result.stdout
    pid = PID_FILE.read_text().strip() if PID_FILE.exists() else "unknown"
    return running, pid


def cmd_start() -> None:
    if not PLIST_DEST.exists():
        print("✗ Baymax daemon not installed. Run: python scripts/install_daemon.py")
        sys.exit(1)
    running, _ = _is_running()
    if running:
        print("Baymax is already running. Use 'restart' to reload.")
        return
    if _launchctl("load"):
        print("✓ Baymax daemon started. Say 'Hey Baymax' to wake it up!")
    else:
        print("✗ Failed to start. Check: python scripts/baymax_ctl.py logs")


def cmd_stop() -> None:
    running, pid = _is_running()
    if not running:
        print("Baymax is not running.")
        return
    if _launchctl("unload"):
        print(f"✓ Baymax daemon stopped (was PID {pid}).")
        PID_FILE.unlink(missing_ok=True)
    else:
        # Try killing by PID directly
        if pid != "unknown":
            try:
                os.kill(int(pid), signal.SIGTERM)
                PID_FILE.unlink(missing_ok=True)
                print(f"✓ Baymax daemon killed (PID {pid}).")
            except ProcessLookupError:
                print("Process already dead.")
        else:
            print("✗ Could not stop daemon.")


def cmd_restart() -> None:
    print("Restarting Baymax...")
    cmd_stop()
    import time
    time.sleep(2)
    cmd_start()


def cmd_status() -> None:
    running, pid = _is_running()
    if running:
        print(f"● Baymax daemon is RUNNING (PID: {pid})")
        print(f"  Log:    {LOG_FILE}")
        print(f"  Errors: {ERR_FILE}")
        print(f"\n  Run 'python scripts/baymax_ctl.py logs' to see live output.")
    else:
        print("○ Baymax daemon is STOPPED")
        if PLIST_DEST.exists():
            print("  Installed but not running. Start with: python scripts/baymax_ctl.py start")
        else:
            print("  Not installed. Run: python scripts/install_daemon.py")


def cmd_logs() -> None:
    if not LOG_FILE.exists():
        print(f"No log file yet at {LOG_FILE}")
        return
    print(f"Tailing {LOG_FILE} (Ctrl+C to stop)...\n")
    try:
        subprocess.run(["tail", "-f", "-n", "50", str(LOG_FILE)])
    except KeyboardInterrupt:
        pass


def cmd_errors() -> None:
    if not ERR_FILE.exists():
        print(f"No error log at {ERR_FILE}")
        return
    print(f"Tailing {ERR_FILE} (Ctrl+C to stop)...\n")
    try:
        subprocess.run(["tail", "-f", "-n", "50", str(ERR_FILE)])
    except KeyboardInterrupt:
        pass


COMMANDS = {
    "start": cmd_start,
    "stop": cmd_stop,
    "restart": cmd_restart,
    "status": cmd_status,
    "logs": cmd_logs,
    "errors": cmd_errors,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Usage: python scripts/baymax_ctl.py [start|stop|restart|status|logs|errors]")
        sys.exit(1)
    COMMANDS[sys.argv[1]]()
