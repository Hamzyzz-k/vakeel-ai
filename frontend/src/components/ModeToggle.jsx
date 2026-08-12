import { useRef } from "react";

const MODES = ["Adviser", "Lawyer"];
const DOUBLE_TAP_MS = 350;

export default function ModeToggle({ mode, onChange, isMobile = false }) {
  const lastTap = useRef({ Adviser: 0, Lawyer: 0 });

  function handleClick(m) {
    if (!isMobile) {
      onChange(m);
      return;
    }
    const now = Date.now();
    if (now - lastTap.current[m] < DOUBLE_TAP_MS) {
      onChange(m);
      lastTap.current[m] = 0;
    } else {
      lastTap.current[m] = now;
    }
  }

  return (
    <div className="relative flex items-center bg-black/6 rounded-full p-1">
      <span
        className="absolute top-1 bottom-1 rounded-full bg-black shadow-sm transition-all duration-300 ease-in-out"
        style={{ width: "calc(50% - 4px)", left: mode === "Adviser" ? "4px" : "calc(50%)" }}
      />
      {MODES.map((m) => (
        <button
          key={m}
          onClick={() => handleClick(m)}
          title={isMobile ? "Double-tap to switch" : undefined}
          className={`relative z-10 px-3 sm:px-4 py-1.5 rounded-full text-xs sm:text-sm font-medium transition-colors duration-300 select-none ${
            mode === m ? "text-white" : "text-black/45 hover:text-black/75"
          }`}
        >
          {m}
        </button>
      ))}
    </div>
  );
}
