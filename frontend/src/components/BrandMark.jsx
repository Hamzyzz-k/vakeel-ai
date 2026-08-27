export default function BrandMark({ compact = false, inverse = false, className = "" }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <img src="/vakeelai-mark_c5f0cf62.png" alt="" className={`${compact ? "h-7 w-7" : "h-10 w-10"} shrink-0 object-contain ${inverse ? "brightness-0 invert" : ""}`} />
      <span className={`${compact ? "text-[19px]" : "text-2xl"} font-serif font-bold tracking-[0.015em] leading-none`}>
        <span className="inline-block pr-px text-[1.12em] font-semibold italic">V</span>akeelAI
      </span>
    </span>
  );
}
