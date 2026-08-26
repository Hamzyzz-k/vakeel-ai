import { Scales } from "@phosphor-icons/react";

export default function BrandMark({ compact = false, inverse = false, className = "" }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <span
        className={`grid shrink-0 place-items-center rounded-xl ${compact ? "h-8 w-8" : "h-10 w-10"} ${
          inverse ? "bg-[var(--ivory)] text-[var(--olive-dark)]" : "bg-[var(--olive)] text-[var(--ivory)]"
        }`}
      >
        <Scales size={compact ? 17 : 21} weight="bold" aria-hidden="true" />
      </span>
      <span className={`${compact ? "text-sm" : "text-base"} font-semibold tracking-[-0.02em]`}>Vakeel AI</span>
    </span>
  );
}
