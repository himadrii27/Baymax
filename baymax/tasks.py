"""
tasks.py — Task CRUD via Supabase.
"""
from __future__ import annotations
import os
from supabase import create_client, Client

_client: Client | None = None


def _db() -> Client:
    global _client
    if _client is None:
        _client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    return _client


def add_task(title: str, description: str = "", priority: int = 3, due_date: str | None = None) -> dict:
    row = _db().table("tasks").insert({
        "title": title,
        "description": description,
        "priority": priority,
        "due_date": due_date,
    }).execute()
    return row.data[0] if row.data else {}


def get_open_tasks() -> list[dict]:
    result = (
        _db().table("tasks")
        .select("*")
        .in_("status", ["open", "in_progress"])
        .order("priority")
        .order("due_date", nullsfirst=False)
        .limit(10)
        .execute()
    )
    return result.data or []


def complete_task(task_id: str) -> dict:
    row = _db().table("tasks").update({"status": "done"}).eq("id", task_id).execute()
    return row.data[0] if row.data else {}


def complete_task_by_num(num: int) -> str:
    """Complete the Nth open task (1-indexed) from the open task list."""
    tasks = get_open_tasks()
    if num < 1 or num > len(tasks):
        return f"No task #{num} found. You have {len(tasks)} open tasks."
    task = tasks[num - 1]
    complete_task(task["id"])
    return f"Done: {task['title']}"


def format_for_prompt() -> str:
    tasks = get_open_tasks()
    if not tasks:
        return "No open tasks."
    PRIORITY_LABEL = {1: "URGENT", 2: "High", 3: "Normal", 4: "Low"}
    lines = []
    for i, t in enumerate(tasks, 1):
        pri = PRIORITY_LABEL.get(t["priority"], "Normal")
        due = f" — due {t['due_date']}" if t.get("due_date") else ""
        lines.append(f"{i}. [{pri}] {t['title']}{due}")
    return "\n".join(lines)
