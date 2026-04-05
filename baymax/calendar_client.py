"""
calendar_client.py — Google Calendar OAuth + event fetching.

First run: python scripts/setup.py --connect-calendar
This will open a browser for Google OAuth and save token.json.
"""
import os
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

TOKEN_PATH = Path(__file__).parent.parent / "data" / "google_token.json"
CREDS_PATH = Path(__file__).parent.parent / "data" / "google_credentials.json"
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def _get_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_PATH.exists():
                raise FileNotFoundError(
                    "Google credentials not found. Run: python scripts/setup.py --connect-calendar"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def get_events_today() -> list[dict]:
    """Fetch today's calendar events."""
    service = _get_service()
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()

    result = service.events().list(
        calendarId="primary",
        timeMin=start,
        timeMax=end,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return result.get("items", [])


def get_events_tomorrow() -> list[dict]:
    """Fetch tomorrow's calendar events."""
    service = _get_service()
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end = tomorrow.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()

    result = service.events().list(
        calendarId="primary",
        timeMin=start,
        timeMax=end,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return result.get("items", [])


def _format_event(event: dict) -> str:
    summary = event.get("summary", "Untitled")
    start = event.get("start", {})
    time_str = start.get("dateTime", start.get("date", ""))
    if "T" in time_str:
        dt = datetime.fromisoformat(time_str)
        time_str = dt.strftime("%I:%M %p")
    return f"{time_str} — {summary}"


def get_today_summary() -> str:
    try:
        events = get_events_today()
        if not events:
            return "Nothing on the calendar today."
        return "\n".join(f"  • {_format_event(e)}" for e in events)
    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"Calendar unavailable: {e}"
