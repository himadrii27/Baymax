"use client";

interface Props {
  isListening: boolean;
  isSpeaking: boolean;
  isAwake: boolean;
  interimText: string;
}

export default function VoiceInput({ isListening, isSpeaking, isAwake, interimText }: Props) {
  return (
    <div className="flex flex-col items-center gap-4 pb-10 pt-4">

      {/* Interim transcript */}
      <div className="h-6 text-center">
        {interimText && (
          <p className="text-sm px-4 py-1 rounded-full"
            style={{ color: "rgba(255,255,255,0.5)", fontStyle: "italic" }}>
            {interimText}
          </p>
        )}
      </div>

      {/* Mic orb */}
      <div className="relative flex items-center justify-center">

        {/* Pulse rings — only when awake and listening */}
        {isAwake && isListening && !isSpeaking && (
          <>
            <span className="absolute w-24 h-24 rounded-full"
              style={{ background: "rgba(214,59,59,0.12)", animation: "ping 1.5s cubic-bezier(0,0,0.2,1) infinite" }} />
            <span className="absolute w-20 h-20 rounded-full"
              style={{ background: "rgba(214,59,59,0.12)", animation: "ping 1.5s cubic-bezier(0,0,0.2,1) infinite 0.3s" }} />
          </>
        )}

        {/* Core circle */}
        <div className="w-16 h-16 rounded-full flex items-center justify-center relative z-10 transition-all duration-300"
          style={{
            background: isSpeaking
              ? "rgba(255,255,255,0.07)"
              : isAwake
                ? "#D63B3B"
                : "rgba(255,255,255,0.07)",
            boxShadow: isAwake && !isSpeaking ? "0 0 24px rgba(214,59,59,0.4)" : "none",
          }}>
          {isSpeaking ? (
            // Sound wave icon while Baymax speaks
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.5)" strokeWidth="2" strokeLinecap="round">
              <path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>
            </svg>
          ) : isListening ? (
            // Mic icon
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
              <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
              <line x1="12" y1="19" x2="12" y2="23"/>
              <line x1="8" y1="23" x2="16" y2="23"/>
            </svg>
          ) : (
            // Mic off / error
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="1" y1="1" x2="23" y2="23"/>
              <path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6"/>
              <path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23"/>
              <line x1="12" y1="19" x2="12" y2="23"/>
              <line x1="8" y1="23" x2="16" y2="23"/>
            </svg>
          )}
        </div>
      </div>

      {/* Status label */}
      <p className="text-xs" style={{ color: "#7a7a9a" }}>
        {isSpeaking
          ? "Baymax is speaking..."
          : isAwake && isListening
            ? "Listening..."
            : isListening
              ? "Say 'Hey Baymax' to begin"
              : "Microphone unavailable — use a text fallback"}
      </p>
    </div>
  );
}
