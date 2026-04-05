"""
api.py — FastAPI backend for Baymax web dashboard.

Usage:
  uvicorn api:app --reload --port 8000
"""
from __future__ import annotations
import asyncio
import os
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from baymax.session import BaymaxSession

app = FastAPI(title="Baymax API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Session store ─────────────────────────────────────────────────
SESSION_STORE: dict[str, BaymaxSession] = {}
SESSION_TTL = 30 * 60  # 30 minutes


def _cleanup_sessions() -> None:
    now = time.time()
    stale = [sid for sid, s in SESSION_STORE.items() if now - s.last_active > SESSION_TTL]
    for sid in stale:
        del SESSION_STORE[sid]


def _get_session(session_id: str) -> BaymaxSession:
    _cleanup_sessions()
    if session_id not in SESSION_STORE:
        raise HTTPException(status_code=404, detail="Session not found. Refresh the page.")
    return SESSION_STORE[session_id]


# ── Routes ────────────────────────────────────────────────────────

class SessionResponse(BaseModel):
    session_id: str


@app.post("/api/session", response_model=SessionResponse)
async def create_session():
    """Create a new demo session. Returns a UUID."""
    session_id = str(uuid.uuid4())
    SESSION_STORE[session_id] = BaymaxSession(session_id)
    return {"session_id": session_id}


@app.get("/api/stream")
async def stream_chat(
    session_id: str = Query(...),
    message: str = Query(...),
):
    """
    SSE endpoint — streams Baymax response token by token.

    Each token:  data: <text>\\n\\n
    End of stream: data: [DONE]\\n\\n
    """
    session = _get_session(session_id)
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def on_token(text: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, text)

    async def run_chat():
        try:
            await loop.run_in_executor(
                None,
                lambda: session.chat(message, stream_callback=on_token),
            )
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, f"\n\n[Error: {e}]")
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    async def event_generator():
        asyncio.ensure_future(run_chat())
        while True:
            token = await queue.get()
            if token is None:
                yield "data: [DONE]\n\n"
                break
            safe = token.replace("\n", "\\n")
            yield f"data: {safe}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


class ResetRequest(BaseModel):
    session_id: str


@app.post("/api/reset")
async def reset_session(body: ResetRequest):
    """Reset conversation history for a session."""
    session = _get_session(body.session_id)
    session.reset()
    return {"ok": True}


@app.get("/api/speak")
async def speak(text: str = Query(...)):
    """
    Convert text to speech via ElevenLabs and stream audio/mpeg back.
    Frontend fetches this after each Baymax response and autoplays it.
    """
    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="ELEVENLABS_API_KEY not set.")

    def generate_audio():
        from elevenlabs.client import ElevenLabs
        client = ElevenLabs(api_key=api_key)
        audio_stream = client.text_to_speech.convert(
            voice_id="pNInz6obpgDQGcFmaJgB",   # Adam — same voice as CLI
            text=text,
            model_id="eleven_turbo_v2_5",
        )
        for chunk in audio_stream:
            yield chunk

    audio_iter = await asyncio.get_event_loop().run_in_executor(
        None, lambda: list(generate_audio())
    )

    def iter_chunks():
        for chunk in audio_iter:
            yield chunk

    return StreamingResponse(
        iter_chunks(),
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "active_sessions": len(SESSION_STORE)}
