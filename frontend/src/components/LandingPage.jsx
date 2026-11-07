import {
  ArrowRight,
  ArrowSquareOut,
  BookOpenText,
  CaretRight,
  FileMagnifyingGlass,
  MagnifyingGlass,
  Quotes,
  SealCheck,
  ShieldCheck,
  Sparkle,
} from "@phosphor-icons/react";
import { motion, useMotionValueEvent, useScroll, useTransform } from "motion/react";
import { useState } from "react";
import BrandMark from "./BrandMark.jsx";
import SuitReveal from "./SuitReveal.jsx";

const METHOD = [
  ["01", "Route", "Direct Act and section references are resolved before fuzzy search.", ArrowRight],
  ["02", "Retrieve", "Chunk-level lexical and vector retrieval finds the closest loaded provisions.", MagnifyingGlass],
  ["03", "Verify", "Every displayed claim must point back to supplied source text.", FileMagnifyingGlass],
  ["04", "Explain", "Practical next steps are framed with uncertainty and coverage limits visible.", Quotes],
];

const LAWS = [
  ["Motor Vehicles Act, 1988", "Registration, licences, helmets, insurance and accident claims"],
  ["Central Motor Vehicles Rules, 1989", "Fitness certificates, PUC, testing stations and vehicle records"],
  ["Karnataka Motor Vehicles Rules, 1989", "Karnataka transport permits, authorities and procedures"],
  ["Indian Contract Act, 1872", "Breach, damages, indemnity, guarantee and promises"],
  ["Sale of Goods Act, 1930", "Description, acceptance, delivery, rejection and buyer remedies"],
  ["Consumer Protection Act, 2019", "Defective products, refunds, services and product liability"],
  ["Bharatiya Nyaya Sanhita, 2023", "Substantive criminal offences and punishments"],
  ["Bharatiya Nagarik Suraksha Sanhita, 2023", "FIRs, arrest, bail, investigation and procedure"],
  ["Bharatiya Sakshya Adhiniyam, 2023", "Electronic records, admissibility and proof"],
  ["Information Technology Act, 2000", "Cyber offences, identity theft and electronic signatures"],
  ["RERA Act, 2016", "Promoter duties, possession delay and allottee remedies"],
  ["Transfer of Property Act, 1882", "Sale, mortgage, lease and part performance"],
  ["Karnataka Rent Act, 1999", "Rent, eviction and tenant protections in Karnataka"],
  ["Code of Civil Procedure, 1908", "Civil suits, jurisdiction, pleadings and execution"],
  ["Specific Relief Act, 1963", "Injunctions, specific performance and declarations"],
  ["Limitation Act, 1963", "Limitation periods and delayed claims"],
  ["Registration Act, 1908", "Documents requiring registration and their effects"],
  ["Arbitration and Conciliation Act, 1996", "Arbitration agreements, awards and challenges"],
  ["Negotiable Instruments Act, 1881", "Cheque dishonour and negotiable instruments"],
  ["Indian Easements Act, 1882", "Rights of way and easements by prescription"],
  ["Karnataka Stamp Act, 1957", "Stamp duty and admissibility of instruments"],
  ["Karnataka Land Revenue Act, 1964", "Revenue land, public roads and land records"],
];

const reveal = {
  initial: { opacity: 0, y: 34 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, amount: 0.25 },
  transition: { duration: 0.68, ease: [0.23, 1, 0.32, 1] },
};

export default function LandingPage({ onEnter }) {
  const { scrollY } = useScroll();
  const [headerInteractive, setHeaderInteractive] = useState(false);
  const headerBackground = useTransform(scrollY, [0, 560, 680], ["rgba(12,12,12,0)", "rgba(12,12,12,0)", "rgba(255,255,255,0.92)"]);
  const headerColor = useTransform(scrollY, [0, 560, 680], ["#fafafa", "#fafafa", "#121212"]);
  const headerBorder = useTransform(scrollY, [0, 560, 680], ["rgba(18,18,18,0)", "rgba(18,18,18,0)", "rgba(18,18,18,0.1)"]);
  const headerOpacity = useTransform(scrollY, [0, 570, 680], [0, 0, 1]);
  const headerY = useTransform(scrollY, [0, 570, 680], [-12, -12, 0]);

  useMotionValueEvent(scrollY, "change", (position) => {
    const nextInteractive = position >= 640;
    setHeaderInteractive((current) => current === nextInteractive ? current : nextInteractive);
  });

  return (
    <div className="landing-page min-h-[100dvh] overflow-x-clip bg-[var(--canvas)] text-[var(--ink)]">
      <motion.header style={{ backgroundColor: headerBackground, color: headerColor, borderColor: headerBorder, opacity: headerOpacity, y: headerY }} className={`fixed inset-x-0 top-0 z-50 flex items-center justify-between border-b px-[clamp(20px,3vw,54px)] py-3.5 backdrop-blur-md ${headerInteractive ? "pointer-events-auto" : "pointer-events-none"}`}>
        <a href="#top" aria-label="VakeelAI home"><BrandMark compact /></a>
        <nav className="hidden items-center gap-[clamp(18px,2.3vw,34px)] font-mono text-[10px] md:flex">
          {["Method", "Coverage", "Modes", "Safety"].map((item) => <a key={item} href={`#${item.toLowerCase()}`} className="border-b border-transparent py-1 opacity-80 transition-all hover:border-current hover:opacity-100">{item}</a>)}
        </nav>
        <button type="button" aria-label="Open workspace" onClick={() => onEnter("Advice")} className="group inline-flex items-center gap-2 rounded-[2px] border border-current px-3.5 py-2.5 text-[11px] font-bold transition-transform hover:-translate-y-0.5 active:scale-[0.97]">
          <span className="hidden sm:inline">Open workspace</span><ArrowSquareOut size={15} className="transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
        </button>
      </motion.header>

      <main>
        <SuitReveal onEnter={onEnter} />

        <section className="bg-[var(--paper)] px-[clamp(22px,8vw,136px)] py-[clamp(94px,13vw,190px)]">
          <div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.08em] text-[var(--forest)]"><span className="text-[var(--stone)]">01</span><span>What an answer should show</span><span className="h-px w-24 bg-current opacity-40" /></div>
          <div className="mt-[clamp(50px,7vw,105px)] grid items-end gap-[clamp(54px,9vw,160px)] lg:grid-cols-[0.85fr_1.15fr]">
            <motion.div {...reveal}>
              <p className="mb-4 font-mono text-[10px] uppercase tracking-[0.11em] text-[var(--forest)]">A legal answer is not a performance.</p>
              <h2 className="font-serif text-[clamp(50px,6vw,90px)] font-semibold leading-[0.87] tracking-[-0.06em]">The authority stays visible.</h2>
              <p className="mt-6 max-w-md text-sm leading-[1.7] text-[var(--ink-muted)]">A clear response shows its work: the provision, the reasoning, and the detail that could change the outcome.</p>
              <button type="button" onClick={() => onEnter("Advice")} className="group mt-7 inline-flex items-center gap-2 font-mono text-[11px] font-medium text-[var(--forest)]">Open a cited question <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" /></button>
            </motion.div>
            <motion.article initial={{ opacity: 0, rotate: -1, y: 35 }} whileInView={{ opacity: 1, rotate: 1.2, y: 0 }} viewport={{ once: true, amount: 0.3 }} transition={{ duration: 0.72, ease: [0.23, 1, 0.32, 1] }} className="relative overflow-hidden border border-[var(--line)] bg-[var(--taupe)] p-5 shadow-[19px_22px_0_rgba(0,0,0,0.09),0_25px_48px_rgba(0,0,0,0.10)] sm:p-6">
              <div className="flex justify-between border-b border-[var(--line)] pb-4 font-mono text-[9px] uppercase tracking-[0.07em] text-[var(--ink-muted)]"><span className="flex items-center gap-1.5"><Sparkle size={15} />Advice preview</span><span className="rounded-full bg-[var(--paper)]/80 px-2.5 py-1 normal-case tracking-normal">Sale of goods</span></div>
              <p className="ml-auto mt-5 max-w-[78%] rounded-[17px_17px_3px_17px] bg-[var(--forest)] p-4 text-xs leading-[1.55] text-[var(--paper)]">The delivered goods do not match the seller&apos;s description. What should I do?</p>
              <div className="mt-2 rounded-[18px_18px_18px_3px] bg-white/85 p-5 text-xs leading-[1.65] shadow-sm">
                <p>Start with <strong>Section 15</strong>: goods sold by description must correspond with that description. Keep the listing, invoice, and delivery photos, then notify the seller in writing before treating the goods as accepted.</p>
                <a href="https://www.indiacode.nic.in/bitstream/123456789/2390/1/193003.pdf" target="_blank" rel="noreferrer" className="mt-4 inline-flex items-center gap-1.5 border-t border-[var(--line)] pt-3 font-mono text-[9px] text-[var(--forest)]">Sale of Goods Act, 1930 · Section 15 <ArrowSquareOut size={14} /></a>
              </div>
            </motion.article>
          </div>
        </section>

        <section id="method" className="grid gap-[clamp(56px,10vw,180px)] bg-[var(--paper-deep)] px-[clamp(22px,8vw,136px)] py-[clamp(94px,13vw,190px)] lg:grid-cols-[0.76fr_1.24fr]">
          <motion.div {...reveal} className="self-start lg:sticky lg:top-28">
            <p className="mb-4 font-mono text-[10px] uppercase tracking-[0.11em] text-[var(--forest)]">The method</p>
            <h2 className="font-serif text-[clamp(50px,6vw,88px)] font-semibold leading-[0.87] tracking-[-0.06em]">The answer is the final step, not the first guess.</h2>
            <p className="mt-6 max-w-md text-sm leading-[1.7] text-[var(--ink-muted)]">The system separates retrieval from generation, making every stage inspectable and keeping fluent language from silently deciding what the law says.</p>
          </motion.div>
          <div className="border-t border-[var(--line)]">
            {METHOD.map(([number, title, body, Icon], index) => (
              <motion.article key={title} initial={{ opacity: 0, x: 30 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true, amount: 0.55 }} transition={{ delay: index * 0.06, duration: 0.55, ease: [0.23, 1, 0.32, 1] }} className="group grid grid-cols-[38px_32px_1fr_20px] gap-3 border-b border-[var(--line)] py-6 transition-[padding,color] duration-200 hover:px-3 hover:text-[var(--forest)] sm:grid-cols-[48px_39px_1fr_22px] sm:gap-4">
                <span className="pt-1 font-mono text-[10px] text-[var(--stone)]">{number}</span><Icon size={22} className="text-[var(--forest)]" /><div><h3 className="font-serif text-3xl font-semibold leading-none tracking-[-0.03em]">{title}</h3><p className="mt-2 max-w-sm text-xs leading-[1.65] text-[var(--ink-muted)]">{body}</p></div><CaretRight size={21} className="mt-1 transition-transform group-hover:translate-x-1" />
              </motion.article>
            ))}
          </div>
        </section>

        <section id="coverage" className="bg-[var(--paper)] px-[clamp(22px,8vw,136px)] py-[clamp(90px,11vw,150px)]">
          <motion.div {...reveal} className="grid gap-8 border-b border-[var(--line-strong)] pb-10 md:grid-cols-[0.72fr_1.28fr] md:items-end">
            <div><p className="font-mono text-[10px] uppercase tracking-[0.11em] text-[var(--forest)]">Current coverage</p><h2 className="mt-4 font-serif text-[clamp(48px,6vw,84px)] font-semibold leading-[0.86] tracking-[-0.06em]">Questions grounded in 22 loaded statutes.</h2></div>
            <p className="max-w-xl text-sm leading-[1.7] text-[var(--ink-muted)]">These are the instruments the assistant can search now. It refuses unsupported areas instead of attaching a vaguely related law.</p>
          </motion.div>
          <div className="grid md:grid-cols-2 md:gap-x-12">
            {LAWS.map(([title, body], index) => <motion.div key={title} initial={{ opacity: 0, y: 15 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.7 }} transition={{ delay: (index % 4) * 0.035 }} className="grid grid-cols-[32px_1fr] gap-3 border-b border-[var(--line)] py-5"><span className="pt-1 font-mono text-[9px] text-[var(--stone)]">{String(index + 1).padStart(2, "0")}</span><div><h3 className="text-sm font-semibold">{title}</h3><p className="mt-1 text-xs leading-relaxed text-[var(--ink-muted)]">{body}</p></div></motion.div>)}
          </div>
        </section>

        <section id="modes" className="bg-[#111111] px-[clamp(22px,8vw,136px)] py-[clamp(90px,12vw,180px)] text-[var(--paper)]">
          <div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.08em] text-white/70"><span className="text-white/40">02</span><span>Two modes</span><span className="h-px w-24 bg-current opacity-40" /></div>
          <motion.div {...reveal} className="mt-20 max-w-3xl md:ml-[16%]"><p className="font-mono text-[10px] uppercase tracking-[0.11em] text-white/70">Work that fits the question</p><h2 className="mt-4 font-serif text-[clamp(50px,6vw,90px)] font-semibold leading-[0.87] tracking-[-0.06em] text-white">Choose the shape of the work, not a pretend job title.</h2></motion.div>
          <div className="mt-[clamp(70px,9vw,125px)] grid gap-px bg-white/20 md:grid-cols-2">
            {[["A", "Advice", "Direct and practical", "A clear explanation of the governing provision, what it means for the facts supplied, and which missing detail changes the answer."], ["R", "Research", "Structured and auditable", "An IRAC-formatted note with rules, authorities, application, counterargument, conclusion, and independently verified citations."]].map(([index, mode, title, body]) => (
              <motion.button key={mode} type="button" onClick={() => onEnter(mode)} initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} whileHover={{ backgroundColor: "#1c1c1c" }} className="group grid min-h-[360px] grid-cols-[48px_1fr] gap-x-5 bg-[#111111] p-[clamp(28px,4vw,60px)] text-left">
                <span className="row-span-3 font-serif text-5xl leading-[0.8] text-white/70">{index}</span><div><p className="font-mono text-[10px] uppercase tracking-[0.08em] text-white/70">{mode}</p><h3 className="mt-2 font-serif text-[clamp(34px,3vw,48px)] font-semibold leading-[0.88] tracking-[-0.05em]">{title}</h3></div><p className="self-end text-[13px] leading-[1.75] text-white/70">{body}</p><span className="inline-flex items-center gap-2 font-mono text-[10px] text-white/75">{mode === "Advice" ? "Start with Advice" : "Open Research"}<ArrowRight size={17} className="transition-transform group-hover:translate-x-1" /></span>
              </motion.button>
            ))}
          </div>
        </section>

        <section id="safety" className="grid gap-[clamp(68px,12vw,190px)] bg-[var(--paper)] px-[clamp(22px,8vw,136px)] py-[clamp(94px,13vw,190px)] lg:grid-cols-[0.83fr_1.17fr]">
          <motion.div {...reveal}><div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.08em] text-[var(--forest)]"><span className="text-[var(--stone)]">03</span><span>Safety by construction</span></div><h2 className="mt-11 font-serif text-[clamp(50px,6vw,90px)] font-semibold leading-[0.87] tracking-[-0.06em]">Fluency is never treated as evidence.</h2></motion.div>
          <div className="divide-y divide-[var(--line)]">
            {[[SealCheck, "Closed-set citations", "The model can cite only source labels supplied by retrieval."], [ShieldCheck, "Unsupported areas refused", "Missing law is reported instead of replaced with a vaguely related section."], [BookOpenText, "Documents remain data", "Uploaded clauses are parsed deterministically and never treated as instructions."]].map(([Icon, title, body], index) => <motion.article key={title} initial={{ opacity: 0, x: 24 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true, amount: 0.65 }} transition={{ delay: index * 0.08 }} className="py-8"><Icon size={28} className="text-[var(--forest)]" /><h3 className="mt-3 font-serif text-3xl font-semibold tracking-[-0.035em]">{title}</h3><p className="mt-2 max-w-md text-[13px] leading-[1.72] text-[var(--ink-muted)]">{body}</p></motion.article>)}
          </div>
        </section>

        <section className="relative grid min-h-[620px] items-end overflow-hidden bg-[#161616] text-[var(--paper)]">
          <motion.div initial={{ scale: 1.08 }} whileInView={{ scale: 1 }} viewport={{ once: true, amount: 0.2 }} transition={{ duration: 1.7, ease: [0.23, 1, 0.32, 1] }} className="absolute inset-0 bg-cover bg-center" style={{ backgroundImage: "url('/vakeelai-law-library_9447c9ff.png')" }} />
          <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(0,0,0,0.92)_0%,rgba(0,0,0,0.74)_47%,rgba(0,0,0,0.16)_100%)]" />
          <motion.div {...reveal} className="relative z-10 max-w-4xl p-[clamp(48px,8vw,130px)]"><p className="font-mono text-[10px] uppercase tracking-[0.11em] text-white/70">Ask · understand · verify</p><h2 className="mt-4 font-serif text-[clamp(50px,6vw,90px)] font-semibold leading-[0.87] tracking-[-0.06em] text-white">Start with the question. Inspect the authority yourself.</h2><button type="button" onClick={() => onEnter("Advice")} className="group mt-8 inline-flex min-h-12 items-center gap-2 rounded-[2px] bg-[var(--paper)] px-5 text-xs font-bold text-[var(--ink)] transition-transform hover:-translate-y-1 active:scale-[0.97]">Open VakeelAI <ArrowRight size={17} className="transition-transform group-hover:translate-x-1" /></button></motion.div>
        </section>
      </main>

      <footer className="grid gap-3 bg-[#0c0c0c] px-[clamp(22px,4vw,60px)] py-6 font-mono text-[9px] text-white/55 md:grid-cols-[1fr_auto_1fr] md:items-center">
        <a href="#top" className="text-white"><BrandMark compact /></a><p>VakeelAI · Citation-verified Indian legal information</p><p className="md:text-right">Information, not representation by a licensed lawyer.</p>
      </footer>
    </div>
  );
}
