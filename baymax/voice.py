"""
voice.py — Voice interface for Baymax.

Stack:
  STT:  RealtimeSTT (faster-whisper + Silero VAD) — single always-on recorder
  TTS:  ElevenLabs API

Activation modes:
  1. Wake word — "Hey Baymax" → greeting → listens for requests
  2. Distress  — "ouch", "ow", "ahh" etc. → health scan mode
     → stays active until user says "I am satisfied with my care"
"""
import os
import re
import logging
import warnings
import threading
import tempfile
import subprocess
from pathlib import Path
from rich.console import Console

warnings.filterwarnings("ignore", category=DeprecationWarning)

console = Console()

# RealtimeSTT floods the root logger with "Error receiving data from connection"
# whenever the audio stream is paused during TTS playback. Filter it out.
class _SuppressSTTConnectionNoise(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "Error receiving data from connection" not in record.getMessage()

logging.getLogger().addFilter(_SuppressSTTConnectionNoise())

ELEVENLABS_VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam — free tier premade voice
ELEVENLABS_MODEL    = "eleven_turbo_v2_5"

# ── Wake word ──────────────────────────────────────────────────
# Catches "hey baymax", "baymax", "hi baymax", "okay baymax", whisper mishearings
WAKE_WORD = re.compile(
    r"\b(baymax|bay\s*max|baym\w*|hey\s+\w*\s*max|hi\s+\w*\s*max)\b",
    re.IGNORECASE,
)

# ── Distress trigger words ─────────────────────────────────────
DISTRESS_WORDS = re.compile(
    r"\b(ouch|ow+|oww+|ahh+|argh|ugh|ooh+|aah+|ow+ch|"
    # Whisper mishearings of short exclamations
    r"^out\.?$|out\s+out|out\s+out\s+out|oh\s+no|oh\s+don|ow\s+ow|auch|ooch|"
    r"i\s+would|i\s+would+\s+i\s+would|"  # "I would I would" = "ouch ouch"
    r"it\s+hurts?|i(?:'m|\s+am)\s+hurt|i(?:'m|\s+am)\s+in\s+pain|"
    r"help\s+me|something\s+hurts?|i\s+fell|i\s+cut|i\s+burned?|"
    r"i\s+feel\s+sick|i\s+feel\s+terrible|i\s+feel\s+awful|"
    r"i(?:'m|\s+am)\s+bleeding|i(?:'m|\s+am)\s+dizzy|i\s+can't\s+breathe)\b",
    re.IGNORECASE,
)

# ── Satisfied / deactivation phrases ──────────────────────────
SATISFIED_WORDS = re.compile(
    r"\b(i\s+am\s+satisfied\s+with\s+(?:my\s+)?care|"
    r"i(?:'m|\s+am)\s+(?:okay|ok|fine|better|good\s+now|alright\s+now)|"
    r"i\s+feel\s+better|thank\s+you\s+baymax|that(?:'s|\s+is)\s+enough|"
    r"you\s+can\s+(?:go|stop|rest)|i\s+don'?t\s+need\s+help)\b",
    re.IGNORECASE,
)

# ── Health scan questions ──────────────────────────────────────
SCAN_QUESTIONS = [
    "On a scale of 1 to 10, how would you rate your pain?",
    "Where does it hurt?",
    "Have you taken any medication for this?",
    "Are you experiencing any other symptoms — dizziness, nausea, or difficulty breathing?",
]


class VoiceInterface:
    def __init__(self):
        self._recorder = None
        self._tts_client = None
        self._awake = False
        self._in_scan_mode = False
        self._setup()

    # ── Setup ─────────────────────────────────────────────────

    def _setup(self):
        try:
            from RealtimeSTT import AudioToTextRecorder
            self._recorder = AudioToTextRecorder(
                model="small.en",
                language="en",
                post_speech_silence_duration=1.2,
                spinner=False,
                enable_realtime_transcription=False,
            )
            console.print("[green]✓ STT ready (Whisper small.en)[/green]")
        except Exception as e:
            console.print(f"[red]STT setup failed:[/red] {e}")
            raise

        try:
            from elevenlabs.client import ElevenLabs
            api_key = os.getenv("ELEVENLABS_API_KEY")
            if not api_key:
                raise RuntimeError("ELEVENLABS_API_KEY not set")
            self._tts_client = ElevenLabs(api_key=api_key)
            console.print("[green]✓ TTS ready (ElevenLabs)[/green]")
        except Exception as e:
            console.print(f"[yellow]TTS unavailable:[/yellow] {e} — text-only mode.")
            self._tts_client = None

    # ── STT ───────────────────────────────────────────────────

    def _listen(self) -> str:
        """Block until one utterance is fully spoken. Returns transcript."""
        return self._recorder.text() or ""

    # ── TTS ───────────────────────────────────────────────────

    def speak(self, text: str) -> None:
        if not self._tts_client or not text.strip():
            return
        from elevenlabs import save
        import time
        try:
            audio = self._tts_client.text_to_speech.convert(
                voice_id=ELEVENLABS_VOICE_ID,
                text=text,
                model_id=ELEVENLABS_MODEL,
            )
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                save(audio, f.name)
                tmp_path = f.name
            # Stop recorder so mic doesn't pick up Baymax's own voice
            try:
                self._recorder.stop()
            except Exception:
                pass
            subprocess.run(["afplay", tmp_path], check=True)
            Path(tmp_path).unlink(missing_ok=True)
            time.sleep(0.4)  # let echo clear before listening again
            # Resume recorder
            try:
                self._recorder.start()
            except Exception:
                pass
        except Exception as e:
            console.print(f"[yellow]TTS error:[/yellow] {e}")

    # ── Helpers ───────────────────────────────────────────────

    def _is_distress(self, text: str) -> bool:
        return bool(DISTRESS_WORDS.search(text))

    def _is_satisfied(self, text: str) -> bool:
        return bool(SATISFIED_WORDS.search(text))

    def _baymax_say(self, msg: str) -> None:
        console.print(f"[bold cyan]Baymax:[/bold cyan] {msg}")
        self.speak(msg)

    # ── Health scan ───────────────────────────────────────────

    def _enter_scan_mode(self, trigger_text: str) -> None:
        self._in_scan_mode = True
        scan_data = {"trigger": trigger_text}

        from baymax import health, brain

        self._baymax_say(
            "Hello. I am Baymax, your personal healthcare companion. "
            "I heard that. I will scan you now."
        )

        for i, question in enumerate(SCAN_QUESTIONS):
            self._baymax_say(question)
            answer = self._listen()
            if not answer:
                continue

            console.print(f"[dim]You:[/dim] {answer}")
            scan_data[f"q{i+1}"] = answer

            if self._is_satisfied(answer):
                self._conclude_scan()
                return

            if i == 0:
                pain_match = re.search(r"\b([1-9]|10)\b", answer)
                if pain_match:
                    pain_level = int(pain_match.group(1))
                    scan_data["pain_level"] = pain_level
                    try:
                        health.log_symptom(trigger_text[:50], severity=pain_level, notes=answer)
                    except Exception:
                        pass

        # Claude assessment
        prompt = (
            f"User triggered distress: '{trigger_text}'. "
            f"Health scan data: {scan_data}. "
            "Give a caring, Baymax-style response. Assess severity, "
            "give immediate care advice, and ask if they need anything else. "
            "Do NOT deactivate — stay with them until they say they are satisfied with care."
        )
        console.print("[bold cyan]Baymax:[/bold cyan] ", end="")
        full_response = ""

        def collect(chunk):
            nonlocal full_response
            full_response += chunk
            print(chunk, end="", flush=True)

        brain.chat(prompt, stream_callback=collect)
        print()
        self.speak(full_response)

        self._care_loop()

    def _care_loop(self) -> None:
        from baymax import brain

        not_satisfied = (
            "I cannot deactivate until I know you are satisfied with your care. "
            "Is there anything else I can do for you?"
        )

        while True:
            console.print(
                "\n[bold cyan]Baymax:[/bold cyan] "
                "[dim]I am still here. Say 'I am satisfied with my care' when you feel okay.[/dim]"
            )
            user_input = self._listen()
            if not user_input:
                continue

            console.print(f"[dim]You:[/dim] {user_input}")

            if self._is_satisfied(user_input):
                self._conclude_scan()
                return

            if any(w in user_input.lower() for w in ("goodbye", "bye", "stop", "go away", "shut down")):
                self._baymax_say(not_satisfied)
                continue

            console.print("[bold cyan]Baymax:[/bold cyan] ", end="")
            full_response = ""

            def collect(chunk):
                nonlocal full_response
                full_response += chunk
                print(chunk, end="", flush=True)

            brain.chat(user_input, stream_callback=collect)
            print()
            self.speak(full_response)

    def _conclude_scan(self) -> None:
        self._in_scan_mode = False
        self._awake = False
        self._baymax_say("I am glad you are feeling better. I am here whenever you need me.")
        console.print("[dim]Health scan complete. Returning to standby.[/dim]\n")

    # ── Main loop ─────────────────────────────────────────────

    def run(self) -> None:
        from baymax import brain
        from baymax.commands import parse

        console.print(
            "[bold cyan]Baymax:[/bold cyan] "
            "[dim]Ready. Say 'Hey Baymax' or a distress word to activate.[/dim]"
        )

        while True:
            try:
                text = self._listen()
                if not text:
                    continue

                console.print(f"[dim](heard):[/dim] {text}")

                # ── Distress — always fires, no wake word needed ──
                if self._is_distress(text) and not self._in_scan_mode:
                    self._enter_scan_mode(text)
                    continue

                # ── Wake word ─────────────────────────────────────
                if WAKE_WORD.search(text):
                    self._awake = True
                    console.print("[bold cyan]Baymax:[/bold cyan] ", end="")
                    full_response = ""

                    def greet_collect(chunk):
                        nonlocal full_response
                        full_response += chunk
                        print(chunk, end="", flush=True)

                    brain.chat(
                        "[wake]",
                        stream_callback=greet_collect,
                    )
                    print()
                    self.speak(full_response)
                    continue

                # ── Ignore speech until awake ─────────────────────
                if not self._awake:
                    continue

                # ── Shutdown ──────────────────────────────────────
                if re.search(r"\b(goodbye|bye|shut\s+down)\s+baymax\b", text, re.IGNORECASE):
                    self._baymax_say("I will be here whenever you need me. Take care of yourself.")
                    self._awake = False
                    continue

                # ── Normal conversation ───────────────────────────
                parse(text)
                console.print("[bold cyan]Baymax:[/bold cyan] ", end="")
                full_response = ""

                def collect(chunk):
                    nonlocal full_response
                    full_response += chunk
                    print(chunk, end="", flush=True)

                brain.chat(text, stream_callback=collect)
                print()
                self.speak(full_response)

            except KeyboardInterrupt:
                console.print("\n[dim]Baymax: Shutting down. Take care![/dim]")
                break
