"use client";

import { useState, KeyboardEvent, useRef, useEffect } from "react";

interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export default function ChatInput({ onSend, disabled, placeholder }: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 128)}px`;
  }, [value]);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="px-4 pb-6 pt-2">
      <div
        className="flex items-end gap-3 bg-white/8 rounded-2xl px-4 py-3
                   border border-white/10 focus-within:border-bh-red/50 transition-colors"
        style={{ background: "rgba(255,255,255,0.05)" }}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={disabled}
          placeholder={
            disabled ? "Baymax is thinking..." : (placeholder ?? "How are you feeling today?")
          }
          rows={1}
          className="flex-1 bg-transparent text-white placeholder-white/30 text-sm
                     resize-none outline-none leading-relaxed"
        />
        <button
          onClick={submit}
          disabled={disabled || !value.trim()}
          aria-label="Send"
          className="w-9 h-9 rounded-xl bg-bh-red disabled:opacity-30
                     hover:bg-bh-red-dark flex-shrink-0 flex items-center
                     justify-center transition-colors"
        >
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="white"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>
      <p className="text-center text-white/20 text-xs mt-2">
        Enter to send · Shift+Enter for newline
      </p>
    </div>
  );
}
