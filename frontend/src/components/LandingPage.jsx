import { memo } from "react";
import {
  ArrowRight,
  ArrowSquareOut,
  BookOpenText,
  CheckCircle,
  FileText,
  Fingerprint,
  Quotes,
  ShieldCheck,
  Sparkle,
} from "@phosphor-icons/react";
import {
  motion,
  useMotionValue,
  useReducedMotion,
  useSpring,
  useTransform,
} from "motion/react";
import BrandMark from "./BrandMark.jsx";

const SPRING = { type: "spring", stiffness: 120, damping: 22 };

const reveal = {
  hidden: { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0, transition: SPRING },
};

function MagneticButton({ children, onClick, secondary = false }) {
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const springX = useSpring(x, { stiffness: 190, damping: 18 });
  const springY = useSpring(y, { stiffness: 190, damping: 18 });
  const iconX = useTransform(springX, (value) => value * 0.2);

  function move(event) {
    const bounds = event.currentTarget.getBoundingClientRect();
    x.set((event.clientX - bounds.left - bounds.width / 2) * 0.13);
    y.set((event.clientY - bounds.top - bounds.height / 2) * 0.13);
  }

  function reset() {
    x.set(0);
    y.set(0);
  }

  return (
    <motion.button
      type="button"
      onClick={onClick}
      onMouseMove={move}
      onMouseLeave={reset}
      style={{ x: springX, y: springY }}
      whileTap={{ scale: 0.98 }}
      className={`group inline-flex items-center justify-center gap-2.5 rounded-full px-5 py-3 text-sm font-semibold transition-colors ${
        secondary
          ? "border border-[var(--line-strong)] bg-[var(--paper)] text-[var(--ink)] hover:bg-[var(--sage-soft)]"
          : "bg-[var(--olive-dark)] text-[var(--ivory)] hover:bg-[var(--olive)]"
      }`}
    >
      {children}
      <motion.span style={{ x: iconX }}>
        <ArrowRight size={16} weight="bold" aria-hidden="true" />
      </motion.span>
    </motion.button>
  );
}

const OFFICIAL_ACTS = [
  {
    label: "Indian Contract Act, 1872",
    url: "https://www.indiacode.nic.in/bitstream/123456789/2187/2/A187209.pdf",
  },
  {
    label: "Sale of Goods Act, 1930",
    url: "https://www.indiacode.nic.in/bitstream/123456789/2390/1/193003.pdf",
  },
  {
    label: "Consumer Protection Act, 2019",
    url: "https://www.indiacode.nic.in/bitstream/123456789/12808/1/the_consumer_protection_act,_2019_no._35_of_2019_date_09.08.2019.pdf",
  },
  {
    label: "Bharatiya Nyaya Sanhita, 2023",
    url: "https://www.indiacode.nic.in/bitstream/123456789/20062/1/a202345.pdf",
  },
];

const ScenarioPreview = memo(function ScenarioPreview() {
  const reduceMotion = useReducedMotion();

  return (
    <div className="relative min-h-[430px] overflow-hidden rounded-[2rem] border border-[var(--line-strong)] bg-[var(--taupe)] p-5 text-[var(--ink)] shadow-[0_28px_70px_-32px_rgba(86,103,63,0.32)] sm:p-7">
      <motion.div
        aria-hidden="true"
        animate={reduceMotion ? undefined : { rotate: [0, 7, 0], scale: [1, 1.06, 1] }}
        transition={{ duration: 12, repeat: Infinity, ...SPRING }}
        className="absolute -right-20 -top-20 h-64 w-64 rounded-full border border-[var(--olive)]/25"
      />
      <div className="relative flex items-center justify-between border-b border-[var(--olive-dark)]/15 pb-4">
        <span className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--olive-dark)]">
          <Quotes size={18} weight="duotone" aria-hidden="true" /> Advice preview
        </span>
        <motion.span
          animate={reduceMotion ? undefined : { y: [0, -2, 0] }}
          transition={{ duration: 2.4, repeat: Infinity, ...SPRING }}
          className="rounded-full bg-[var(--sage-soft)] px-3 py-1 text-[10px] font-semibold text-[var(--olive-dark)]"
        >
          Sale of goods
        </motion.span>
      </div>

      <div className="relative ml-auto mt-7 max-w-[88%] rounded-3xl rounded-br-lg bg-[var(--olive-dark)] px-4 py-3 text-sm leading-relaxed text-[var(--ivory)]">
        The delivered goods do not match the seller&apos;s description. What should I do?
      </div>

      <motion.div
        initial={{ opacity: 0, y: 22 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.35, ...SPRING }}
        className="relative mr-6 mt-4 rounded-3xl rounded-bl-lg border border-[var(--olive-dark)]/10 bg-[var(--ivory)] p-5"
      >
        <p className="text-sm leading-relaxed text-[var(--ink)]">
          Start with Section 15: goods sold by description must correspond with that description. Keep the listing, invoice, and delivery photos, then notify the seller in writing before treating the goods as accepted.
        </p>
        <div className="mt-4 border-t border-[var(--taupe)] pt-3">
          <a
            href={OFFICIAL_ACTS[1].url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 text-xs font-semibold text-[var(--olive-dark)] underline decoration-[var(--sage)] decoration-2 underline-offset-4 hover:text-[var(--olive)]"
          >
            Open the official Act · find Section 15 <ArrowSquareOut size={13} weight="bold" aria-hidden="true" />
          </a>
        </div>
      </motion.div>
    </div>
  );
});

function StatuteRibbon() {
  const reduceMotion = useReducedMotion();
  return (
    <div className="overflow-hidden border-y border-[var(--line-strong)] bg-[var(--sage-soft)] py-3">
      <motion.div
        animate={reduceMotion ? undefined : { x: ["0%", "-50%"] }}
        transition={{ duration: 32, repeat: Infinity, ease: "linear", repeatType: "loop" }}
        className="flex w-max will-change-transform"
      >
        {[0, 1].map((track) => (
          <div key={track} aria-hidden={track === 1} className="flex min-w-[100vw] shrink-0 items-center justify-around gap-10 px-8">
            {OFFICIAL_ACTS.map((item) => (
              <a
                key={`${track}-${item.label}`}
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                tabIndex={track === 1 ? -1 : 0}
                className="group flex shrink-0 items-center gap-3 text-xs font-semibold text-[var(--ink-muted)] transition-colors hover:text-[var(--olive-dark)]"
                title={`Open the official ${item.label}`}
              >
                <Sparkle size={12} weight="fill" className="text-[var(--olive)] transition-transform group-hover:rotate-45" aria-hidden="true" />
                {item.label}
                <ArrowSquareOut size={11} weight="bold" className="opacity-45 group-hover:opacity-100" aria-hidden="true" />
              </a>
            ))}
          </div>
        ))}
      </motion.div>
    </div>
  );
}

function SectionHeading({ eyebrow, title, body }) {
  return (
    <motion.div variants={reveal} initial="hidden" whileInView="visible" viewport={{ once: true, amount: 0.35 }}>
      <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--olive)]">{eyebrow}</p>
      <h2 className="mt-4 max-w-3xl text-3xl font-semibold leading-[1.05] tracking-[-0.045em] text-[var(--ink)] sm:text-5xl">{title}</h2>
      {body && <p className="mt-5 max-w-[62ch] text-base leading-relaxed text-[var(--ink-muted)]">{body}</p>}
    </motion.div>
  );
}

export default function LandingPage({ onEnter }) {
  const reduceMotion = useReducedMotion();
  const steps = [
    ["01", "Route", "Direct Act and section references are resolved before fuzzy search."],
    ["02", "Retrieve", "Chunk-level lexical and vector retrieval finds the closest loaded provisions."],
    ["03", "Verify", "Every displayed claim must point back to supplied source text."],
    ["04", "Explain", "You receive a practical answer with uncertainty and coverage limits visible."],
  ];

  return (
    <div className="landing-shell min-h-[100dvh] overflow-x-hidden bg-[var(--canvas)] text-[var(--ink)]">
      <header className="sticky top-0 z-30 border-b border-[var(--line)] bg-[color:var(--canvas)]/88 backdrop-blur-xl">
        <nav className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3.5 sm:px-6 lg:px-8" aria-label="Primary navigation">
          <a href="#top" className="rounded-xl text-[var(--ink)]" aria-label="Vakeel AI home">
            <BrandMark compact />
          </a>
          <div className="hidden items-center gap-7 text-sm text-[var(--ink-muted)] md:flex">
            <a href="#method" className="transition-colors hover:text-[var(--ink)]">Method</a>
            <a href="#modes" className="transition-colors hover:text-[var(--ink)]">Modes</a>
            <a href="#safety" className="transition-colors hover:text-[var(--ink)]">Safety</a>
          </div>
          <button
            type="button"
            onClick={() => onEnter("Advice")}
            className="inline-flex items-center gap-2 rounded-full bg-[var(--olive-dark)] px-4 py-2 text-xs font-semibold text-[var(--ivory)] transition-transform active:scale-[0.98] sm:text-sm"
          >
            Open workspace <ArrowRight size={14} weight="bold" aria-hidden="true" />
          </button>
        </nav>
      </header>

      <main id="top">
        <section className="relative mx-auto grid min-h-[calc(100dvh-68px)] max-w-7xl grid-cols-1 items-center gap-12 px-4 py-14 sm:px-6 md:py-20 lg:grid-cols-[1.08fr_0.92fr] lg:gap-20 lg:px-8">
          <motion.div
            initial="hidden"
            animate="visible"
            variants={{ visible: { transition: { staggerChildren: 0.12 } } }}
            className="relative"
          >
            <motion.p variants={reveal} className="mb-7 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--olive)]">
              Indian legal research · with receipts
            </motion.p>
            <motion.h1 variants={reveal} className="max-w-[720px] text-5xl font-semibold leading-[0.96] tracking-[-0.06em] text-[var(--ink)] sm:text-6xl lg:text-[4.6rem]">
              Useful legal information without invented authority.
            </motion.h1>
            <motion.p variants={reveal} className="mt-7 max-w-[58ch] text-base leading-relaxed text-[var(--ink-muted)] sm:text-lg">
              Ask against the law currently loaded. Vakeel retrieves the provision, verifies every citation, and refuses areas it cannot support.
            </motion.p>
            <motion.div variants={reveal} className="mt-8 flex flex-col items-start gap-3 sm:flex-row sm:items-center">
              <MagneticButton onClick={() => onEnter("Advice")}>Start with Advice</MagneticButton>
              <MagneticButton onClick={() => onEnter("Research")} secondary>Open Research mode</MagneticButton>
            </motion.div>
            <motion.div variants={reveal} className="mt-10 flex flex-wrap gap-x-7 gap-y-3 text-xs text-[var(--ink-muted)]">
              {["Exact source text", "Visible coverage limits", "Local conversation history"].map((item) => (
                <span key={item} className="inline-flex items-center gap-2">
                  <CheckCircle size={15} weight="fill" className="text-[var(--olive)]" aria-hidden="true" /> {item}
                </span>
              ))}
            </motion.div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: 44, rotate: 1.5 }}
            animate={{ opacity: 1, x: 0, rotate: 0 }}
            transition={{ delay: 0.15, ...SPRING }}
            className="relative lg:-mr-5"
          >
            <motion.div
              aria-hidden="true"
              animate={reduceMotion ? undefined : { y: [0, -12, 0], rotate: [0, 2, 0] }}
              transition={{ duration: 7, repeat: Infinity, ...SPRING }}
              className="absolute -left-7 -top-8 h-24 w-24 rounded-[1.7rem] bg-[var(--sage)]/35"
            />
            <ScenarioPreview />
          </motion.div>
        </section>

        <StatuteRibbon />

        <section id="method" className="bg-[var(--ivory)]">
          <div className="mx-auto max-w-7xl px-4 py-24 sm:px-6 md:py-32 lg:px-8">
          <SectionHeading
            eyebrow="The method"
            title="The answer is the final step, not the first guess."
            body="The system separates retrieval from generation. That makes each stage testable and keeps a fluent model from quietly deciding what the law says."
          />
          <div className="mt-16 border-t border-[var(--line-strong)]">
            {steps.map(([number, title, body], index) => (
              <motion.div
                key={number}
                initial={{ opacity: 0, x: index % 2 ? 26 : -26 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, amount: 0.45 }}
                transition={{ delay: index * 0.05, ...SPRING }}
                className="grid grid-cols-[44px_1fr] gap-4 border-b border-[var(--line)] py-7 sm:grid-cols-[80px_180px_1fr] sm:items-center"
              >
                <span className="font-mono text-xs text-[var(--olive)]">{number}</span>
                <h3 className="text-xl font-semibold tracking-[-0.03em]">{title}</h3>
                <p className="col-start-2 max-w-[58ch] text-sm leading-relaxed text-[var(--ink-muted)] sm:col-start-3">{body}</p>
              </motion.div>
            ))}
          </div>
          </div>
        </section>

        <section id="modes" className="border-y border-[var(--line)] bg-[var(--sage-soft)]">
          <div className="mx-auto max-w-7xl px-4 py-24 sm:px-6 md:py-32 lg:px-8">
            <SectionHeading eyebrow="Two modes" title="Choose the shape of the work, not a pretend job title." />
            <div className="mt-14 grid grid-cols-1 gap-5 lg:grid-cols-[0.86fr_1.14fr]">
              <motion.div
                whileHover={{ y: -5 }}
                transition={SPRING}
                className="rounded-[2rem] border border-[var(--line-strong)] bg-[var(--taupe)]/55 p-7 sm:p-9"
              >
                <Quotes size={28} weight="duotone" className="text-[var(--olive)]" aria-hidden="true" />
                <p className="mt-12 text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--olive)]">Advice</p>
                <h3 className="mt-3 text-3xl font-semibold tracking-[-0.04em]">Direct and practical</h3>
                <p className="mt-4 max-w-[44ch] text-sm leading-relaxed text-[var(--ink-muted)]">A clear explanation of the governing provision, what it means for the facts supplied, and what information is still missing.</p>
              </motion.div>
              <motion.div
                whileHover={{ y: -5 }}
                transition={SPRING}
                className="relative overflow-hidden rounded-[2rem] bg-[var(--olive-dark)] p-7 text-[var(--ivory)] sm:p-9"
              >
                <BookOpenText size={30} weight="duotone" className="text-[var(--sage)]" aria-hidden="true" />
                <motion.div
                  aria-hidden="true"
                  animate={reduceMotion ? undefined : { x: [0, 180, 0] }}
                  transition={{ duration: 9, repeat: Infinity, ...SPRING }}
                  className="absolute right-12 top-12 h-px w-44 bg-gradient-to-r from-transparent via-[var(--sage)] to-transparent opacity-40"
                />
                <p className="mt-12 text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--sage)]">Research</p>
                <h3 className="mt-3 text-3xl font-semibold tracking-[-0.04em]">Structured and auditable</h3>
                <p className="mt-4 max-w-[52ch] text-sm leading-relaxed text-white/58">An IRAC-formatted note with rules, authorities, application, counterargument, conclusion, and independently verified citations.</p>
              </motion.div>
            </div>
          </div>
        </section>

        <section id="safety" className="mx-auto grid max-w-7xl grid-cols-1 gap-14 px-4 py-24 sm:px-6 md:py-32 lg:grid-cols-[0.8fr_1.2fr] lg:px-8">
          <SectionHeading eyebrow="Safety by construction" title="Fluency is never treated as evidence." body="The app is intentionally narrow. It exposes what is loaded, strips unsupported claims, and keeps uploaded documents out of model prompts." />
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, amount: 0.25 }}
            variants={{ visible: { transition: { staggerChildren: 0.1 } } }}
            className="divide-y divide-[var(--line)] border-y border-[var(--line-strong)]"
          >
            {[
              [ShieldCheck, "Closed-set citations", "The model can cite only source labels supplied by retrieval."],
              [Fingerprint, "Unsupported areas refused", "Missing law is reported instead of replaced by a vaguely related section."],
              [FileText, "Documents remain data", "Uploaded clauses are parsed deterministically and never treated as instructions."],
            ].map(([Icon, title, body]) => (
              <motion.div variants={reveal} key={title} className="grid grid-cols-[38px_1fr] gap-4 py-7">
                <Icon size={24} weight="duotone" className="text-[var(--olive)]" aria-hidden="true" />
                <div>
                  <h3 className="font-semibold tracking-[-0.02em]">{title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-[var(--ink-muted)]">{body}</p>
                </div>
              </motion.div>
            ))}
          </motion.div>
        </section>

        <section className="mx-auto max-w-7xl px-4 pb-24 sm:px-6 lg:px-8">
          <motion.div
            initial={{ opacity: 0, scale: 0.97 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true, amount: 0.45 }}
            transition={SPRING}
            className="grid gap-8 rounded-[2rem] border border-[var(--line-strong)] bg-[var(--taupe)] p-7 sm:p-10 md:grid-cols-[1fr_auto] md:items-end"
          >
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--olive-dark)]">Ask · understand · verify</p>
              <h2 className="mt-5 max-w-2xl text-3xl font-semibold leading-tight tracking-[-0.045em] sm:text-5xl">Start with the question. Inspect the authority yourself.</h2>
            </div>
            <MagneticButton onClick={() => onEnter("Advice")}>Open Vakeel AI</MagneticButton>
          </motion.div>
        </section>
      </main>

      <footer className="border-t border-[var(--line)]">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-7 text-xs text-[var(--ink-muted)] sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
          <span>Vakeel AI · Citation-verified Indian legal information</span>
          <span>Information, not representation by a licensed lawyer.</span>
        </div>
      </footer>
    </div>
  );
}
