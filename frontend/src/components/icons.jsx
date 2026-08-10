// Small authored icon set, one consistent stroke (1.75, round caps/joins) --
// no emoji or unicode glyphs standing in for icons.
const base = { fill: "none", stroke: "currentColor", strokeWidth: 1.75, strokeLinecap: "round", strokeLinejoin: "round" };

export function IconScale(props) {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" {...base} {...props}>
      <path d="M12 3v18M12 3l-6 3M12 3l6 3" />
      <path d="M3 8l3 6a3 3 0 0 0 6 0l-3-6M15 8l3 6a3 3 0 0 0 6 0l-3-6" />
      <path d="M8 21h8" />
    </svg>
  );
}

export function IconSend(props) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" {...base} {...props}>
      <path d="M4.5 12L20 4.5 12.5 20l-2-6.5-6-1.5Z" />
    </svg>
  );
}

export function IconExternal(props) {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" {...base} {...props}>
      <path d="M9 6h9v9" />
      <path d="M17.5 6.5L7 17" />
    </svg>
  );
}

export function IconChevron(props) {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" {...base} {...props}>
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

export function IconWarning(props) {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" {...base} {...props}>
      <path d="M12 4L3 20h18L12 4Z" />
      <path d="M12 10v4" />
      <circle cx="12" cy="17" r="0.8" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function IconClock(props) {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" {...base} {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </svg>
  );
}

export function IconGavel(props) {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" {...base} {...props}>
      <path d="M6.5 13.5l4-4M9 16l4.5-4.5" />
      <path d="M12.5 8.5l4-4 3 3-4 4Z" />
      <path d="M3 21l5-5" />
      <path d="M2 21h7" />
    </svg>
  );
}

export function IconRetry(props) {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" {...base} {...props}>
      <path d="M3 12a9 9 0 1 1 2.6 6.3" />
      <path d="M3 21v-6h6" />
    </svg>
  );
}
