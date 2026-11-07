import { memo, useRef, useState } from "react";
import { ArrowDown, ArrowRight, CaretRight, Check } from "@phosphor-icons/react";
import { useMotionValueEvent, useReducedMotion, useScroll } from "motion/react";

const CLOSED_SUIT_IMAGE = "/vakeelai-buttoned-black-suit.png";
const OPEN_SUIT_IMAGE = "/vakeelai-opened-black-suit-scene.png";
const clamp = (value) => Math.min(1, Math.max(0, value));

const ScrollCue = memo(function ScrollCue({ opacity }) {
  return (
    <div aria-hidden="true" style={{ opacity }} className="zip-scroll-cue">
      <span>Scroll to open</span>
      <ArrowDown size={15} />
    </div>
  );
});

export default function SuitReveal({ onEnter }) {
  const target = useRef(null);
  const [rawProgress, setRawProgress] = useState(0);
  const reduceMotion = useReducedMotion();
  const { scrollYProgress } = useScroll({ target, offset: ["start start", "end end"] });

  useMotionValueEvent(scrollYProgress, "change", setRawProgress);

  const progress = reduceMotion ? 1 : rawProgress;
  const jacketOpen = clamp((progress - 0.15) / 0.2);
  const paperBlend = clamp((progress - 0.57) / 0.16);
  const copyVisible = clamp((progress - 0.71) / 0.17);
  const uiVisible = clamp((progress - 0.81) / 0.15);
  const openSceneOpacity = clamp((progress - 0.16) / 0.15) * (1 - clamp((progress - 0.54) / 0.16));

  const sceneStyle = {
    "--zip-suit-scale": `${1 + clamp(progress / 0.35) * 0.43}`,
    "--zip-suit-opacity": `${1 - jacketOpen}`,
    "--zip-jacket-open": `${jacketOpen}`,
    "--zip-open-opacity": `${openSceneOpacity}`,
    "--zip-paper-blend": `${paperBlend}`,
    "--zip-copy-visible": `${copyVisible}`,
    "--zip-ui-visible": `${uiVisible}`,
  };

  return (
    <section id="top" ref={target} className="zip-hero-stage">
      <div className="zip-hero-sticky" style={sceneStyle}>
        <div className="zip-suit-reveal" aria-hidden="true">
          <div className="zip-hero-ink" />
          <div className="zip-paper-wash" />
          <div className="zip-suit-light zip-suit-light-left" />
          <div className="zip-suit-light zip-suit-light-right" />
          <img className="zip-opened-suit-scene" src={OPEN_SUIT_IMAGE} alt="" draggable="false" />
          <div className="zip-suit-composition">
            <div className="zip-suit-shadow" />
            <img className="zip-tailored-suit-image" src={CLOSED_SUIT_IMAGE} alt="" draggable="false" />
          </div>
          <div className="zip-reveal-spark zip-reveal-spark-one" />
          <div className="zip-reveal-spark zip-reveal-spark-two" />
        </div>

        {!reduceMotion && <ScrollCue opacity={1 - copyVisible} />}

        <div className="zip-hero-copy">
          <div className="max-w-[690px]">
            <p className="mb-4 font-mono text-[10px] font-medium uppercase tracking-[0.11em] text-[var(--forest)]">Indian legal research · with receipts</p>
            <h1 className="max-w-[650px] font-serif text-[clamp(50px,7vw,106px)] font-semibold leading-[0.84] tracking-[-0.065em]">Start with the provision.<br /><em className="font-medium text-[var(--forest)]">Follow the evidence.</em></h1>
            <p className="mt-7 max-w-[510px] text-sm leading-[1.7] sm:text-base">VakeelAI retrieves the law, verifies the citation, and makes its coverage limits plain before it explains.</p>
            <div className="zip-hero-ui mt-7 flex flex-wrap gap-3">
              <button type="button" onClick={() => onEnter("Advice")} className="group inline-flex min-h-12 items-center gap-2.5 rounded-[2px] bg-[var(--forest)] px-5 text-xs font-bold text-[var(--paper)] transition-transform duration-200 hover:-translate-y-1 active:scale-[0.97]">Ask your question <ArrowRight size={17} className="transition-transform group-hover:translate-x-1" /></button>
              <a href="#method" className="group inline-flex min-h-12 items-center gap-2.5 rounded-[2px] border border-[var(--ink)]/35 px-5 text-xs font-bold transition-colors duration-200 hover:bg-[var(--ink)] hover:text-[var(--paper)]">See the method <CaretRight size={17} className="transition-transform group-hover:translate-x-1" /></a>
            </div>
            <div className="zip-hero-ui mt-6 flex flex-wrap gap-x-5 gap-y-2 font-mono text-[9px] text-[var(--ink-muted)]">
              {["Exact source text", "Visible coverage limits", "Local conversation history"].map((item) => <span key={item} className="inline-flex items-center gap-1.5"><Check size={13} weight="bold" className="text-[var(--forest)]" />{item}</span>)}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
