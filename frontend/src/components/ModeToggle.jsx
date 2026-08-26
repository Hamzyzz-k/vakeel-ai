const MODES = ["Advice", "Research"];

export default function ModeToggle({ mode, onChange }) {
  return (
    <div className="relative flex items-center bg-[var(--sage-soft)] rounded-full p-1">
      <span
        className="absolute top-1 bottom-1 rounded-full bg-[var(--olive-dark)] shadow-sm transition-all duration-300 ease-in-out"
        style={{ width: "calc(50% - 4px)", left: mode === "Advice" ? "4px" : "calc(50%)" }}
      />
      {MODES.map((m) => (
        <button
          key={m}
          onClick={() => onChange(m)}
          aria-pressed={mode === m}
          className={`relative z-10 px-3 sm:px-4 py-1.5 rounded-full text-xs sm:text-sm font-medium transition-colors duration-300 select-none ${
            mode === m ? "text-[var(--ivory)]" : "text-[var(--ink-muted)] hover:text-[var(--ink)]"
          }`}
        >
          {m}
        </button>
      ))}
    </div>
  );
}
