import BaymaxAvatar from "./BaymaxAvatar";

export default function TypingIndicator() {
  return (
    <div className="flex items-end gap-3 animate-fade-in">
      <BaymaxAvatar size="sm" />
      <div className="bg-white/10 rounded-2xl rounded-bl-sm px-4 py-3 flex gap-1.5 items-center">
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className="w-2 h-2 rounded-full bg-white/50 animate-blink"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </div>
    </div>
  );
}
