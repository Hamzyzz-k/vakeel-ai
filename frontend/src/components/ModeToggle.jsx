const MODES = ["Advice", "Research"];

export default function ModeToggle({ mode, onChange }) {
  return (
    <div className="relative flex items-center bg-[var(--sage-soft)] p-1">
      <span
        className="absolute bottom-1 top-1 bg-[var(--olive-dark)] shadow-sm transition-all duration-300 ease-in-out"
        style={{ width: "calc(50% - 4px)", left: mode === "Advice" ? "4px" : "calc(50%)" }}
      />
      {MODES.map((m) => (
        <button
          key={m}
          onClick={() => onChange(m)}
          aria-pressed={mode === m}
          className={`relative z-10 select-none px-3 py-1.5 font-mono text-[10px] font-medium transition-colors duration-300 sm:px-4 ${
            mode === m ? "text-[var(--ivory)]" : "text-[var(--ink-muted)] hover:text-[var(--ink)]"
          }`}
        >
          {m}
        </button>
      ))}
    </div>
  );
}
