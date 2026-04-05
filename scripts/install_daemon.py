"""
install_daemon.py — Install Baymax as a macOS Launch Agent.

What this does:
  1. Fills in your Python path and project directory into the plist template
  2. Copies the plist to ~/Library/LaunchAgents/
  3. Loads it with launchctl (starts immediately + on every login)
  4. Verifies it's running

Run once:
  python scripts/install_daemon.py

To uninstall:
  python scripts/install_daemon.py --uninstall
"""
import os
import sys
import shutil
import subprocess
import argparse
from pathlib import Path

PLIST_NAME = "com.baymax.daemon.plist"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
PLIST_DEST = LAUNCH_AGENTS_DIR / PLIST_NAME
PLIST_TEMPLATE = Path(__file__).parent / PLIST_NAME
BAYMAX_DIR = Path(__file__).parent.parent.resolve()
LOG_FILE = Path.home() / "Library" / "Logs" / "baymax.log"


def get_python_path() -> str:
    """Return the Python interpreter currently running this script."""
    return sys.executable


def install() -> None:
    print("Installing Baymax daemon...\n")

    # 1. Check .env exists
    env_path = BAYMAX_DIR / ".env"
    if not env_path.exists():
        print("✗ .env not found. Run 'python scripts/setup.py' first.")
        sys.exit(1)

    python_path = get_python_path()
    home = str(Path.home())
    baymax_dir = str(BAYMAX_DIR)

    print(f"  Python:      {python_path}")
    print(f"  Project dir: {baymax_dir}")
    print(f"  Log file:    {LOG_FILE}")

    # 2. Read and fill plist template
    template = PLIST_TEMPLATE.read_text()
    filled = (
        template
        .replace("PYTHON_PATH_PLACEHOLDER", python_path)
        .replace("BAYMAX_DIR_PLACEHOLDER", baymax_dir)
        .replace("HOME_PLACEHOLDER", home)
    )

    # 3. Write to LaunchAgents
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_DEST.write_text(filled)
    print(f"\n  ✓ Plist written to: {PLIST_DEST}")

    # 4. Unload first if already loaded (clean reinstall)
    subprocess.run(
        ["launchctl", "unload", str(PLIST_DEST)],
        capture_output=True,
    )

    # 5. Load the agent
    result = subprocess.run(
        ["launchctl", "load", "-w", str(PLIST_DEST)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  ✗ launchctl load failed: {result.stderr}")
        sys.exit(1)

    print("  ✓ Launch Agent loaded and started")
    print("  ✓ Will auto-start on every login\n")

    # 6. Grant microphone permission reminder
    print("⚠️  IMPORTANT: Grant microphone access")
    print("   System Settings → Privacy & Security → Microphone")
    print("   → Enable access for Terminal (or your Python app)\n")

    # 7. Verify running
    _status()

    print("\nBaymax is now running in the background.")
    print(f"Say 'Hey Baymax' anytime to wake it up!")
    print(f"\nManage with: python scripts/baymax_ctl.py [start|stop|restart|status|logs]")


def uninstall() -> None:
    print("Uninstalling Baymax daemon...")

    result = subprocess.run(
        ["launchctl", "unload", "-w", str(PLIST_DEST)],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print("  ✓ Launch Agent unloaded")
    else:
        print(f"  ⚠ launchctl unload: {result.stderr.strip()}")

    if PLIST_DEST.exists():
        PLIST_DEST.unlink()
        print(f"  ✓ Removed {PLIST_DEST}")

    pid_file = BAYMAX_DIR / ".baymax.pid"
    if pid_file.exists():
        pid_file.unlink()

    print("Baymax daemon uninstalled. It will no longer start on login.")


def _status() -> None:
    result = subprocess.run(
        ["launchctl", "list", "com.baymax.daemon"],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and "com.baymax.daemon" in result.stdout:
        pid_file = BAYMAX_DIR / ".baymax.pid"
        pid = pid_file.read_text().strip() if pid_file.exists() else "unknown"
        print(f"  ✓ Baymax daemon is RUNNING (PID: {pid})")
    else:
        print("  ✗ Baymax daemon is NOT running")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--uninstall", action="store_true", help="Remove the Launch Agent")
    args = parser.parse_args()

    if args.uninstall:
        uninstall()
    else:
        install()
