import BaymaxAvatar from "./BaymaxAvatar";

interface Props {
  role: "user" | "assistant";
  text: string;
  isStreaming?: boolean;
}

export default function ChatBubble({ role, text, isStreaming }: Props) {
  const isAssistant = role === "assistant";

  return (
    <div
      className={`flex items-end gap-3 animate-slide-up
                  ${isAssistant ? "flex-row" : "flex-row-reverse"}`}
    >
      {isAssistant && <BaymaxAvatar size="sm" />}

      <div
        className={`
          max-w-[75%] px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap
          ${isAssistant
            ? "bg-white/10 text-white rounded-bl-sm"
            : "bg-bh-red text-white rounded-br-sm"
          }
          ${isStreaming ? "streaming-cursor" : ""}
        `}
      >
        {text}
      </div>
    </div>
  );
}
