"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import ChatBubble from "@/components/ChatBubble";
import BaymaxAvatar from "@/components/BaymaxAvatar";
import TypingIndicator from "@/components/TypingIndicator";
import VoiceInput from "@/components/VoiceInput";

type Role = "user" | "assistant";
interface Message { id: string; role: Role; text: string; }

// ── Same patterns as voice.py ─────────────────────────────────────
const WAKE_WORD = /\b(baymax|bay\s*max|baym\w*|hey\s+\w*\s*max|hi\s+\w*\s*max)\b/i;
const DISTRESS  = /\b(ouch|ow+|oww+|ahh+|argh|ugh|it\s+hurts?|i(?:'m|\s+am)\s+hurt|i(?:'m|\s+am)\s+in\s+pain|help\s+me|something\s+hurts?|i\s+fell|i\s+cut|i\s+burned?|i\s+feel\s+sick|i\s+feel\s+terrible|i\s+feel\s+awful|i(?:'m|\s+am)\s+bleeding|i(?:'m|\s+am)\s+dizzy|i\s+can't\s+breathe)\b/i;
const GOODBYE   = /\b(goodbye\s+baymax|bye\s+baymax|shut\s+down\s+baymax)\b/i;
const SATISFIED = /\b(i\s+am\s+satisfied\s+with\s+(?:my\s+)?care|i(?:'m|\s+am)\s+(?:okay|ok|fine|better|good\s+now|alright)|i\s+feel\s+better|thank\s+you\s+baymax)\b/i;

export default function Home() {
  const [sessionId, setSessionId]         = useState<string | null>(null);
  const [messages, setMessages]           = useState<Message[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [isStreaming, setIsStreaming]     = useState(false);
  const [isAwake, setIsAwake]             = useState(false);
  const [voiceOn, setVoiceOn]             = useState(true);
  const [isListening, setIsListening]     = useState(false);
  const [isSpeaking, setIsSpeaking]       = useState(false);
  const [interimText, setInterimText]     = useState("");
  const [hasSpeechAPI, setHasSpeechAPI]   = useState(false);

  const bottomRef    = useRef<HTMLDivElement>(null);
  const esRef        = useRef<EventSource | null>(null);
  const audioRef     = useRef<HTMLAudioElement | null>(null);
  const recognRef    = useRef<SpeechRecognition | null>(null);
  const isAwakeRef   = useRef(false);          // ref copy for use inside recognition callbacks
  const isSpeakingRef = useRef(false);

  // Keep refs in sync with state
  useEffect(() => { isAwakeRef.current   = isAwake;   }, [isAwake]);
  useEffect(() => { isSpeakingRef.current = isSpeaking; }, [isSpeaking]);

  // ── Client-only detection (avoids hydration mismatch) ────────
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const w = window as any;
    setHasSpeechAPI(!!(w.SpeechRecognition || w.webkitSpeechRecognition));
  }, []);

  // ── Session init ──────────────────────────────────────────────
  useEffect(() => {
    const stored = localStorage.getItem("baymax_session_id");
    if (stored) { setSessionId(stored); return; }
    fetch("http://localhost:8000/api/session", { method: "POST" })
      .then(r => r.json())
      .then(data => {
        localStorage.setItem("baymax_session_id", data.session_id);
        setSessionId(data.session_id);
      });
  }, []);

  // ── Auto-scroll ───────────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  // ── TTS ───────────────────────────────────────────────────────
  const playResponse = useCallback(async (text: string) => {
    if (!voiceOn || !text.trim()) return;
    if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }

    // Pause mic while Baymax speaks
    recognRef.current?.stop();
    setIsSpeaking(true);
    isSpeakingRef.current = true;

    try {
      const res = await fetch(`http://localhost:8000/api/speak?text=${encodeURIComponent(text)}`);
      if (!res.ok) throw new Error("TTS failed");
      const blob  = await res.blob();
      const url   = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;

      await new Promise<void>(resolve => {
        audio.onended  = () => { URL.revokeObjectURL(url); resolve(); };
        audio.onerror  = () => resolve();
        audio.play();
      });
    } catch { /* non-critical */ }

    // Resume mic after Baymax finishes speaking
    setIsSpeaking(false);
    isSpeakingRef.current = false;
    startListening();
  }, [voiceOn]);

  // ── Stream to backend ─────────────────────────────────────────
  const streamMessage = useCallback((text: string, sid: string) => {
    setIsStreaming(true);
    setStreamingText("");

    const url = `http://localhost:8000/api/stream?session_id=${encodeURIComponent(sid)}&message=${encodeURIComponent(text)}`;
    const es  = new EventSource(url);
    esRef.current = es;
    let accumulated = "";

    es.onmessage = event => {
      if (event.data === "[DONE]") {
        es.close();
        setMessages(prev => [...prev, { id: crypto.randomUUID(), role: "assistant", text: accumulated }]);
        setStreamingText("");
        setIsStreaming(false);
        playResponse(accumulated);
        return;
      }
      accumulated += event.data.replace(/\\n/g, "\n");
      setStreamingText(accumulated);
    };

    es.onerror = () => { es.close(); setIsStreaming(false); };
  }, [playResponse]);

  // ── Wake / distress state machine ────────────────────────────
  const handleTranscript = useCallback((text: string, sid: string) => {
    if (!text.trim()) return;
    setInterimText("");

    setMessages(prev => [...prev, { id: crypto.randomUUID(), role: "user", text }]);

    if (isAwakeRef.current && GOODBYE.test(text)) {
      setIsAwake(false);
      const bye = "I will be here whenever you need me. Take care of yourself.";
      setMessages(prev => [...prev, { id: crypto.randomUUID(), role: "assistant", text: bye }]);
      playResponse(bye);
      fetch("http://localhost:8000/api/reset", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: sid }) }).catch(() => {});
      return;
    }

    if (isAwakeRef.current && SATISFIED.test(text)) {
      streamMessage(text, sid);
      setIsAwake(false);
      return;
    }

    if (DISTRESS.test(text)) {
      setIsAwake(true);
      streamMessage(text, sid);
      return;
    }

    if (!isAwakeRef.current && WAKE_WORD.test(text)) {
      setIsAwake(true);
      streamMessage(text, sid);
      return;
    }

    if (isAwakeRef.current) {
      streamMessage(text, sid);
      return;
    }

    // Asleep + no wake word — silent ignore (don't clutter the screen)
  }, [streamMessage, playResponse]);

  // ── Web Speech API ────────────────────────────────────────────
  const startListening = useCallback(() => {
    if (typeof window === "undefined") return;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const w = window as any;
    const SR: (new () => SpeechRecognition) | undefined = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!SR) return;

    // Don't start a new session while Baymax is speaking
    if (isSpeakingRef.current) return;

    const recog = new SR();
    recog.continuous      = false;   // one utterance at a time — more reliable
    recog.interimResults  = true;
    recog.lang            = "en-US";

    recog.onstart  = () => setIsListening(true);
    recog.onend    = () => {
      setIsListening(false);
      setInterimText("");
      // Auto-restart unless Baymax is speaking
      if (!isSpeakingRef.current) setTimeout(startListening, 200);
    };

    recog.onresult = (event: SpeechRecognitionEvent) => {
      let interim = "";
      let final   = "";
      for (let i = 0; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) final   += result[0].transcript + " ";
        else                interim += result[0].transcript;
      }
      setInterimText(interim || final);
      if (final.trim()) {
        setInterimText("");
        // Grab session ID from closure — need to read from DOM via ref trick below
        setSessionId(sid => { if (sid) handleTranscript(final.trim(), sid); return sid; });
      }
    };

    recog.onerror = (e) => {
      if (e.error !== "no-speech" && e.error !== "aborted") console.warn("STT error:", e.error);
    };

    recognRef.current = recog;
    recog.start();
  }, [handleTranscript]);

  // ── Start listening once session is ready ─────────────────────
  useEffect(() => {
    if (sessionId) startListening();
    return () => { recognRef.current?.stop(); };
  }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Reset ─────────────────────────────────────────────────────
  const resetSession = async () => {
    esRef.current?.close();
    if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }
    try {
      await fetch("http://localhost:8000/api/reset", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
    } catch {}
    setMessages([]); setStreamingText(""); setIsStreaming(false); setIsAwake(false);
  };

  // ── Render ────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-screen" style={{ background: "#1a1a2e" }}>

      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
        <div className="flex items-center gap-3">
          <div className="relative">
            <BaymaxAvatar size="md" />
            <span className={`absolute bottom-0 right-0 w-3 h-3 rounded-full border-2 transition-colors duration-500 ${isAwake ? "bg-green-400" : "bg-gray-500"}`}
              style={{ borderColor: "#1a1a2e" }} />
          </div>
          <div>
            <h1 className="text-white font-semibold text-lg leading-tight">Baymax</h1>
            <p className="text-xs" style={{ color: "#7a7a9a" }}>
              {isAwake ? "Active — I am here with you" : "Standby — Say 'Hey Baymax'"}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button onClick={() => {
            if (voiceOn && audioRef.current) { audioRef.current.pause(); audioRef.current = null; }
            setVoiceOn(v => !v);
          }}
            title={voiceOn ? "Mute voice" : "Unmute voice"}
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: voiceOn ? "rgba(214,59,59,0.15)" : "rgba(255,255,255,0.07)" }}>
            {voiceOn ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#D63B3B" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                <path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#7a7a9a" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                <line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/>
              </svg>
            )}
          </button>
          <button onClick={resetSession}
            className="text-sm px-3 py-1.5 rounded-lg"
            style={{ color: "#7a7a9a" }}
            onMouseEnter={e => (e.currentTarget.style.color = "white")}
            onMouseLeave={e => (e.currentTarget.style.color = "#7a7a9a")}>
            New Chat
          </button>
        </div>
      </header>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto chat-scroll px-4 py-6 space-y-4">
        {messages.length === 0 && !isStreaming && (
          <div className="flex flex-col items-center justify-center h-full gap-5">
            <div style={{ opacity: isAwake ? 1 : 0.45, transition: "opacity 0.4s" }}>
              <BaymaxAvatar size="lg" />
            </div>
            <div className="text-center">
              {isAwake ? (
                <>
                  <p className="text-white font-medium mb-1">Hello. I am Baymax.</p>
                  <p className="text-sm" style={{ color: "#7a7a9a" }}>Your personal healthcare companion.</p>
                </>
              ) : (
                <>
                  <p className="font-medium mb-1" style={{ color: "rgba(255,255,255,0.5)" }}>I am in standby.</p>
                  <p className="text-sm" style={{ color: "#7a7a9a" }}>
                    Say <span style={{ color: "#D63B3B", fontWeight: 600 }}>"Hey Baymax"</span> to begin.
                  </p>
                </>
              )}
            </div>
          </div>
        )}

        {messages.map(msg => <ChatBubble key={msg.id} role={msg.role} text={msg.text} />)}

        {isStreaming && streamingText && <ChatBubble role="assistant" text={streamingText} isStreaming />}
        {isStreaming && !streamingText && <TypingIndicator />}

        <div ref={bottomRef} />
      </main>

      {/* Voice indicator or fallback */}
      {hasSpeechAPI ? (
        <VoiceInput
          isListening={isListening}
          isSpeaking={isSpeaking}
          isAwake={isAwake}
          interimText={interimText}
        />
      ) : (
        <div className="px-4 pb-6 pt-2 text-center">
          <p className="text-sm" style={{ color: "#D63B3B" }}>
            Voice not supported in this browser. Use Chrome or Safari.
          </p>
        </div>
      )}
    </div>
  );
}
