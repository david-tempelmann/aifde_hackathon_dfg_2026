import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { MapPin, Clock, ArrowUpRight, ChevronDown } from "lucide-react";
import { fetchOverview } from "../api";
import type { Hotspot, OverviewResponse } from "../types";
import { formatDate } from "../lib";
import { issueIcon, issueColor } from "../issueMeta";
import CountUp from "../components/CountUp";

// Direction semantics, shared across the page. Watch is intentionally neutral
// (gray); opportunity/risk keep the app-wide emerald/rose. Because emerald and
// rose sit close for red-green colour vision, every use here pairs them with a
// legend, direct counts, and a gap between segments — never colour alone.
const DIRS = [
  { key: "opp", dir: "opportunity", label: "Opportunity", fill: "bg-emerald-500", dot: "bg-emerald-500", stroke: "stroke-emerald-500" },
  { key: "risk", dir: "risk", label: "Risk", fill: "bg-rose-500", dot: "bg-rose-500", stroke: "stroke-rose-500" },
  { key: "watch", dir: "watch", label: "Watch", fill: "bg-slate-400", dot: "bg-slate-400", stroke: "stroke-slate-400" },
] as const;

interface IssueAgg {
  n: number;
  opp: number;
  risk: number;
  watch: number;
}

// Reveal on scroll: fires once when the element enters the viewport.
function useInView<T extends HTMLElement>(): [React.RefObject<T | null>, boolean] {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setInView(true);
          io.disconnect();
        }
      },
      { threshold: 0.15 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return [ref, inView];
}

export default function HomePage() {
  const navigate = useNavigate();
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    fetchOverview()
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!data) return;
    const raf = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(raf);
  }, [data]);

  const { issues, states, matrix, max, issueAgg, stateTotals, maxIssueTotal, maxStateTotal } =
    useMemo(() => {
      const matrix: Record<string, Record<string, Hotspot>> = {};
      const stateTotals: Record<string, number> = {};
      const issueAgg: Record<string, IssueAgg> = {};
      let max = 0;
      for (const h of data?.hotspots ?? []) {
        (matrix[h.issue] ??= {})[h.state] = h;
        stateTotals[h.state] = (stateTotals[h.state] ?? 0) + h.n;
        const ia = (issueAgg[h.issue] ??= { n: 0, opp: 0, risk: 0, watch: 0 });
        ia.n += h.n;
        ia.opp += h.opportunities;
        ia.risk += h.risks;
        ia.watch += h.watch;
        if (h.n > max) max = h.n;
      }
      const issues = Object.keys(issueAgg).sort((a, b) => issueAgg[b].n - issueAgg[a].n);
      const states = Object.keys(stateTotals).sort(
        (a, b) => stateTotals[b] - stateTotals[a] || a.localeCompare(b),
      );
      const maxIssueTotal = Math.max(1, ...issues.map((i) => issueAgg[i].n));
      const maxStateTotal = Math.max(1, ...states.map((s) => stateTotals[s]));
      return { issues, states, matrix, max, issueAgg, stateTotals, maxIssueTotal, maxStateTotal };
    }, [data]);

  const s = data?.summary ?? {};
  const total = s.total ?? 0;
  const mix = [
    { ...DIRS[0], value: s.opportunities ?? 0 },
    { ...DIRS[1], value: s.risks ?? 0 },
    { ...DIRS[2], value: s.watch ?? 0 },
  ];

  const scrollToExplore = () =>
    document.getElementById("explore")?.scrollIntoView({ behavior: "smooth", block: "start" });

  if (loading) {
    return (
      <div className="flex min-h-[70vh] items-center justify-center">
        <div className="h-64 w-64 animate-pulse rounded-full bg-black/5" />
      </div>
    );
  }

  return (
    <div>
      {/* ── Hero: simple, eye-catching signal-mix breakdown ─────────────── */}
      <section className="relative -mx-6 flex min-h-[80vh] flex-col items-center justify-center overflow-hidden px-6 py-12 text-center">
        <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
          <div className="absolute left-[10%] top-[8%] h-72 w-72 rounded-full bg-brand-500/20 blur-3xl" />
          <div className="absolute right-[8%] top-[18%] h-72 w-72 rounded-full bg-accent-500/20 blur-3xl" />
          <div className="absolute bottom-[8%] left-[42%] h-72 w-72 rounded-full bg-gold-400/25 blur-3xl" />
        </div>

        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-black/5 bg-white/70 px-3 py-1 text-xs font-semibold text-navy-500 backdrop-blur">
          <span className="relative flex h-2 w-2" aria-hidden>
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
          </span>
          Live signal intelligence
        </div>
        <p className="mb-8 max-w-xl text-base leading-relaxed text-navy-500 sm:text-lg">
          <span className="font-bold text-navy">Outreach Signals</span> turns local
          child-welfare news and policy shifts into timely opportunities to grow{" "}
          <span className="font-semibold text-accent-600">CarePortal</span> partnerships.
        </p>
        <h1 className="mb-10 max-w-2xl text-3xl font-bold tracking-tight text-navy sm:text-4xl">
          Today's signals <span className="text-accent-600">at a glance</span>
        </h1>

        <MixDonut total={total} mix={mix} mounted={mounted} />

        <div className="mt-10 grid w-full max-w-2xl grid-cols-1 gap-3 sm:grid-cols-3">
          {mix.map((m) => (
            <button
              key={m.key}
              onClick={() => navigate(`/signals?direction=${m.dir}`)}
              className="group rounded-2xl border border-black/5 bg-white/70 p-4 text-left backdrop-blur transition hover:-translate-y-0.5 hover:border-black/10 hover:bg-white hover:shadow-md"
            >
              <div className="flex items-center gap-2">
                <span className={`h-2.5 w-2.5 rounded-full ${m.dot}`} />
                <span className="text-sm font-semibold text-navy-500">{m.label}</span>
                <ArrowUpRight className="ml-auto h-4 w-4 text-navy-300 opacity-0 transition group-hover:opacity-100" />
              </div>
              <div className="mt-1 text-3xl font-extrabold text-navy">
                <CountUp value={m.value} />
              </div>
              <div className="text-xs font-medium text-navy-400">
                {Math.round((m.value / (total || 1)) * 100)}% of signals
              </div>
            </button>
          ))}
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-center gap-x-5 gap-y-1 text-xs text-navy-400">
          <span className="inline-flex items-center gap-1">
            <MapPin className="h-3.5 w-3.5" />
            {s.states ?? 0} states
          </span>
          <span className="inline-flex items-center gap-1">
            <Clock className="h-3.5 w-3.5" />
            latest {formatDate(s.latest ?? null) || "—"}
          </span>
        </div>

        <button
          onClick={scrollToExplore}
          className="mt-10 inline-flex flex-col items-center gap-1 text-navy-400 transition hover:text-navy"
        >
          <span className="text-xs font-medium">Scroll to explore</span>
          <ChevronDown className="h-5 w-5 animate-bounce" />
        </button>
      </section>

      {/* ── Scroll-revealed detail charts ───────────────────────────────── */}
      <div id="explore" className="space-y-16 py-8">
        <TopIssues
          issues={issues}
          issueAgg={issueAgg}
          maxIssueTotal={maxIssueTotal}
          onOpen={(issue) => navigate(`/signals?issue=${encodeURIComponent(issue)}`)}
        />
        <ActiveStates
          states={states}
          stateTotals={stateTotals}
          maxStateTotal={maxStateTotal}
          onOpen={(st) => navigate(`/signals?state=${encodeURIComponent(st)}`)}
        />
        <Hotspots
          issues={issues}
          states={states}
          matrix={matrix}
          max={max}
          onOpen={(st, issue) =>
            navigate(`/signals?state=${encodeURIComponent(st)}&issue=${encodeURIComponent(issue)}`)
          }
        />
      </div>
    </div>
  );
}

// ── Hero donut ─────────────────────────────────────────────────────────────
function MixDonut({
  total,
  mix,
  mounted,
}: {
  total: number;
  mix: { key: string; label: string; stroke: string; value: number }[];
  mounted: boolean;
}) {
  const R = 92;
  const SW = 26;
  const C = 2 * Math.PI * R;
  const GAP = total > 0 ? 6 : 0; // px gap along the circumference between segments
  let cum = 0;
  const arcs = mix.map((m) => {
    const frac = total > 0 ? m.value / total : 0;
    const start = cum;
    cum += frac * C;
    return { ...m, len: Math.max(0, frac * C - GAP), start };
  });

  return (
    <div className="relative mx-auto h-64 w-64">
      <svg viewBox="0 0 240 240" className="h-full w-full -rotate-90">
        <circle cx="120" cy="120" r={R} fill="none" strokeWidth={SW} className="stroke-black/[0.05]" />
        {arcs.map(
          (a) =>
            a.len > 0 && (
              <circle
                key={a.key}
                cx="120"
                cy="120"
                r={R}
                fill="none"
                strokeWidth={SW}
                strokeLinecap="butt"
                className={`${a.stroke} transition-[stroke-dasharray] duration-1000 ease-out`}
                style={{
                  strokeDasharray: mounted ? `${a.len} ${C - a.len}` : `0 ${C}`,
                  strokeDashoffset: -a.start,
                }}
              />
            ),
        )}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-5xl font-extrabold leading-none text-navy">
          <CountUp value={total} />
        </div>
        <div className="mt-1 text-[11px] font-semibold uppercase tracking-wide text-navy-400">
          signals tracked
        </div>
      </div>
    </div>
  );
}

// ── Section shell (centered header + scroll reveal) ─────────────────────────
function SectionHeader({ kicker, title, sub }: { kicker: string; title: string; sub?: string }) {
  return (
    <div className="mb-6 text-center">
      <div className="text-xs font-semibold uppercase tracking-wider text-brand-600">{kicker}</div>
      <h2 className="mt-1 text-2xl font-bold text-navy">{title}</h2>
      {sub && <p className="mx-auto mt-1 max-w-xl text-sm text-navy-400">{sub}</p>}
    </div>
  );
}

function revealCls(inView: boolean) {
  return `transition-all duration-700 ease-out ${
    inView ? "translate-y-0 opacity-100" : "translate-y-8 opacity-0"
  }`;
}

function Legend() {
  return (
    <div className="flex items-center justify-center gap-4 text-[11px] text-navy-400">
      {DIRS.map((d) => (
        <span key={d.key} className="inline-flex items-center gap-1">
          <span className={`h-2 w-2 rounded-full ${d.dot}`} />
          {d.label}
        </span>
      ))}
    </div>
  );
}

// ── Top issues (ranked stacked bars) ────────────────────────────────────────
function TopIssues({
  issues,
  issueAgg,
  maxIssueTotal,
  onOpen,
}: {
  issues: string[];
  issueAgg: Record<string, IssueAgg>;
  maxIssueTotal: number;
  onOpen: (issue: string) => void;
}) {
  const [ref, inView] = useInView<HTMLElement>();
  return (
    <section ref={ref} className={revealCls(inView)}>
      <SectionHeader
        kicker="By issue"
        title="Top issues"
        sub="Signal volume by issue — each bar shows the opportunity / risk / watch mix."
      />
      <div className="mx-auto max-w-3xl rounded-2xl border border-black/5 bg-white p-6 shadow-sm">
        <div className="mb-4">
          <Legend />
        </div>
        <ul className="space-y-3.5">
          {issues.slice(0, 8).map((issue) => {
            const ia = issueAgg[issue];
            const Icon = issueIcon(issue);
            const segs = [
              { ...DIRS[0], value: ia.opp },
              { ...DIRS[1], value: ia.risk },
              { ...DIRS[2], value: ia.watch },
            ];
            return (
              <li key={issue}>
                <button onClick={() => onOpen(issue)} className="group w-full text-left">
                  <div className="mb-1 flex items-center gap-2">
                    <Icon className={`h-4 w-4 shrink-0 ${issueColor(issue)}`} />
                    <span className="truncate text-sm font-medium text-navy group-hover:text-brand-700">
                      {issue}
                    </span>
                    <span className="ml-auto text-sm font-bold tabular-nums text-navy">{ia.n}</span>
                    <ArrowUpRight className="h-3.5 w-3.5 text-navy-300 opacity-0 transition group-hover:opacity-100" />
                  </div>
                  <div className="flex h-2.5 w-full gap-[2px] overflow-hidden rounded-full bg-black/[0.04]">
                    {segs.map((seg) =>
                      seg.value > 0 ? (
                        <div
                          key={seg.key}
                          className={`h-full ${seg.fill} transition-[width] duration-700 ease-out first:rounded-l-full last:rounded-r-full`}
                          style={{ width: inView ? `${(seg.value / maxIssueTotal) * 100}%` : "0%" }}
                          title={`${seg.label}: ${seg.value}`}
                        />
                      ) : null,
                    )}
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}

// ── Most active states (ranked bars) ────────────────────────────────────────
function ActiveStates({
  states,
  stateTotals,
  maxStateTotal,
  onOpen,
}: {
  states: string[];
  stateTotals: Record<string, number>;
  maxStateTotal: number;
  onOpen: (st: string) => void;
}) {
  const [ref, inView] = useInView<HTMLElement>();
  return (
    <section ref={ref} className={revealCls(inView)}>
      <SectionHeader kicker="By state" title="Most active states" sub="Total signals per state." />
      <div className="mx-auto max-w-3xl rounded-2xl border border-black/5 bg-white p-6 shadow-sm">
        <ul className="space-y-2.5">
          {states.slice(0, 10).map((st, i) => {
            const n = stateTotals[st];
            return (
              <li key={st}>
                <button
                  onClick={() => onOpen(st)}
                  className="group flex w-full items-center gap-3 text-left"
                >
                  <span className="w-5 shrink-0 text-xs font-semibold tabular-nums text-navy-300">
                    {i + 1}
                  </span>
                  <span className="w-9 shrink-0 text-sm font-semibold text-navy group-hover:text-brand-700">
                    {st}
                  </span>
                  <div className="h-6 flex-1 overflow-hidden rounded-md bg-black/[0.04]">
                    <div
                      className="flex h-full items-center justify-end rounded-md bg-gradient-to-r from-brand-500 to-brand-600 pr-2 transition-[width] duration-700 ease-out"
                      style={{ width: inView ? `${(n / maxStateTotal) * 100}%` : "0%" }}
                    >
                      <span className="text-xs font-bold tabular-nums text-white">{n}</span>
                    </div>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}

// ── Issue × state hotspots ──────────────────────────────────────────────────
function Hotspots({
  issues,
  states,
  matrix,
  max,
  onOpen,
}: {
  issues: string[];
  states: string[];
  matrix: Record<string, Record<string, Hotspot>>;
  max: number;
  onOpen: (st: string, issue: string) => void;
}) {
  const [ref, inView] = useInView<HTMLElement>();
  return (
    <section ref={ref} className={revealCls(inView)}>
      <SectionHeader
        kicker="Issue × state"
        title="Hotspot matrix"
        sub="Signal count per issue and state. Click any cell to open its filtered feed."
      />
      <div className="rounded-2xl border border-black/5 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center justify-end gap-2 text-[11px] text-navy-400">
          <span>Fewer</span>
          <div className="h-2.5 w-24 rounded-full bg-gradient-to-r from-brand-50 to-brand-600" />
          <span>More</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full border-separate border-spacing-1 text-sm">
            <thead>
              <tr>
                <th className="w-64 text-left text-xs font-medium text-navy-400">Issue</th>
                {states.map((st) => (
                  <th key={st} className="px-2 text-center text-xs font-semibold text-navy-600">
                    {st}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {issues.map((issue) => {
                const Icon = issueIcon(issue);
                return (
                  <tr key={issue}>
                    <td className="py-1 pr-2 text-navy">
                      <span className="inline-flex items-center gap-1.5">
                        <Icon className={`h-3.5 w-3.5 ${issueColor(issue)}`} />
                        <span className="truncate">{issue}</span>
                      </span>
                    </td>
                    {states.map((st) => (
                      <td key={st} className="p-0">
                        <Cell h={matrix[issue]?.[st]} max={max} onClick={() => onOpen(st, issue)} />
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

function Cell({ h, max, onClick }: { h?: Hotspot; max: number; onClick?: () => void }) {
  if (!h || h.n === 0) {
    return <div className="h-full min-h-[52px] rounded-lg bg-black/[0.02]" />;
  }
  const intensity = max > 0 ? h.n / max : 0;
  const bg = `rgba(7, 115, 167, ${0.08 + intensity * 0.62})`; // CarePortal light blue ramp
  const light = intensity < 0.45;
  const { opportunities: opp, risks: risk, watch } = h;
  return (
    <button
      onClick={onClick}
      className="flex min-h-[52px] w-full flex-col justify-center gap-1 rounded-lg px-2 py-1.5 transition hover:ring-2 hover:ring-brand-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
      style={{ backgroundColor: bg }}
      title={`${h.n} signals — ${opp} opportunity, ${risk} risk, ${watch} watch · latest ${formatDate(
        h.latest,
      )} · click to view`}
    >
      <span className={`text-center text-base font-bold ${light ? "text-navy" : "text-white"}`}>
        {h.n}
      </span>
      <div className="flex h-1.5 w-full gap-[1px] overflow-hidden rounded-full bg-white/50">
        {opp > 0 && <div className="bg-emerald-500" style={{ flex: opp }} />}
        {risk > 0 && <div className="bg-rose-500" style={{ flex: risk }} />}
        {watch > 0 && <div className="bg-slate-300" style={{ flex: watch }} />}
      </div>
    </button>
  );
}
