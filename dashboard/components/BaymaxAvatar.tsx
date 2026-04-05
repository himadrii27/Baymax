interface Props {
  size?: "sm" | "md" | "lg";
}

const sizes = {
  sm: "w-8 h-8",
  md: "w-10 h-10",
  lg: "w-20 h-20",
};

export default function BaymaxAvatar({ size = "md" }: Props) {
  return (
    <div
      className={`${sizes[size]} rounded-full overflow-hidden bg-white flex-shrink-0
                  shadow-lg shadow-bh-red/20 ring-2 ring-bh-red/40`}
    >
      <img
        src="/baymax.png"
        alt="Baymax"
        className="w-full h-full object-cover"
      />
    </div>
  );
}
