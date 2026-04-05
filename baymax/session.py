"""
session.py — Per-session Baymax state for the web dashboard.

Each browser tab gets a BaymaxSession that owns a BrainState.
All prompting, health context, identity, mood, cycle, tasks —
everything is identical to the CLI. Only the conversation history
and Mem0 user_id are isolated per session.
"""
from __future__ import annotations
import time

from baymax.brain import BrainState, chat as brain_chat, reset_session as brain_reset


class BaymaxSession:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        # Each tab gets its own BrainState — isolated history, turn count, and Mem0 scope
        self._state = BrainState(user_id=session_id)
        self.created_at = time.time()
        self.last_active = time.time()

    def chat(self, user_message: str, stream_callback=None) -> str:
        self.last_active = time.time()
        return brain_chat(user_message, stream_callback=stream_callback, state=self._state)

    def reset(self) -> None:
        brain_reset(state=self._state)
        self.last_active = time.time()
