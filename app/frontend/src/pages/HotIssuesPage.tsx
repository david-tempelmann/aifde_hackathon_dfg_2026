import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Flame, MapPin, ChevronDown, ArrowUpRight } from "lucide-react";
import { fetchHotIssues } from "../api";
import type { HotIssueCard, HotSignal } from "../types";
import MiniGraph from "../components/MiniGraph";
import { issueIcon, issueColor } from "../issueMeta";

const DIR = {
  opportunity: { label: "opportunity", bar: "bg-emerald-500", dot: "bg-emerald-500", border: "border-t-emerald-500" },
  risk: { label: "risk", bar: "bg-rose-500", dot: "bg-rose-500", border: "border-t-rose-500" },
  watch: { label: "watch", bar: "bg-slate-400", dot: "bg-slate-400", border: "border-t-slate-400" },
} as const;

type Dir = keyof typeof DIR;

export default function HotIssuesPage() {
  const navigate = useNavigate();
  const [cards, setCards] = useState<HotIssueCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchHotIssues(4)
      .then((r) => setCards(r.cards))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load hot issues"));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-bold text-navy">
          <Flame className="h-5 w-5 text-accent-600" />
          Hot issues
        </h1>
        <p className="max-w-3xl text-sm text-navy-400">
          The issue &times; place hotspots heating up right now. Expand one to see its signals — each
          with an explained knowledge-graph link back to what it concerns, affects, involves, and
          references.
        </p>
        <p className="mt-1 max-w-3xl text-xs text-navy-300">
          <span className="font-semibold text-navy-400">Heat (0–100)</span> blends the hotspot's top
          signal priority (35%), signal volume (30%), recency (20%), and cross-source corroboration (15%).
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</div>
      )}

      {!cards && !error && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-64 animate-pulse rounded-2xl bg-black/5" />
          ))}
        </div>
      )}

      {cards && (
        <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
          {cards.map((c) => (
            <Card key={`${c.issue}-${c.place}-${c.state}`} c={c} onSeeSignals={() =>
              navigate(`/signals?state=${encodeURIComponent(c.state)}&issue=${encodeURIComponent(c.issue)}`)
            } />
          ))}
        </div>
      )}
    </div>
  );
}

function Card({ c, onSeeSignals }: { c: HotIssueCard; onSeeSignals: () => void }) {
  const [open, setOpen] = useState(false);
  const dom = (["opportunity", "risk", "watch"].includes(c.dom) ? c.dom : "watch") as Dir;
  const Icon = issueIcon(c.issue);
  const comp = c.components;

  return (
    <section
      className={`rounded-2xl border border-black/5 border-t-4 bg-white p-5 shadow-md transition duration-200 hover:-translate-y-0.5 hover:shadow-xl ${DIR[dom].border}`}
    >
      <div className="flex items-start gap-3">
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-navy text-sm font-bold text-white">
          {c.rank}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="flex items-center gap-1.5 text-base font-bold text-navy">
            <Icon className={`h-4 w-4 shrink-0 ${issueColor(c.issue)}`} />
            {c.issue}
          </h3>
          <div className="text-[13px] text-navy-400">
            <MapPin className="mr-0.5 inline h-3.5 w-3.5" />
            {c.place}, {c.state} <span className="opacity-70">({c.level})</span>
          </div>
        </div>
        <div
          className="shrink-0 rounded-xl bg-accent-50 px-2.5 py-1 text-center"
          title={`Heat ${c.heat} = priority ${Math.round(comp.priority * 100)} · volume ${Math.round(
            comp.volume * 100,
          )} · recency ${Math.round(comp.recency * 100)} · corroboration ${Math.round(comp.corroboration * 100)}`}
        >
          <div className="text-sm font-bold text-accent-600">🔥 {c.heat}</div>
          <div className="text-[10px] font-semibold text-navy-400">HEAT</div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        <Chip>
          <b>{c.n}</b> signals
        </Chip>
        <Chip>
          Top priority <b>{c.top_priority}</b>
        </Chip>
        {c.latest && <Chip>latest {c.latest}</Chip>}
        {c.nextup && <Chip accent>upcoming {c.nextup}</Chip>}
      </div>

      {/* Direction bar + legend */}
      <div className="mt-2.5 flex h-2 gap-[2px] overflow-hidden rounded-full bg-black/[0.05]">
        {(["opportunity", "risk", "watch"] as Dir[]).map((d) => {
          const v = d === "opportunity" ? c.n_opp : d === "risk" ? c.n_risk : c.n_watch;
          return v > 0 ? <div key={d} className={DIR[d].bar} style={{ width: `${(100 * v) / c.n}%` }} /> : null;
        })}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 text-[12px] text-navy-500">
        {(["opportunity", "risk", "watch"] as Dir[]).map((d) => {
          const v = d === "opportunity" ? c.n_opp : d === "risk" ? c.n_risk : c.n_watch;
          return v > 0 ? (
            <span key={d} className="inline-flex items-center gap-1">
              <span className={`h-2 w-2 rounded-full ${DIR[d].dot}`} /> {v} {DIR[d].label}
            </span>
          ) : null;
        })}
      </div>

      {/* Sources */}
      {c.sources.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[12px]">
          <span className="text-[11px] uppercase tracking-wide text-navy-300">Sources ({c.sources.length})</span>
          {c.sources.map((s) => (
            <span key={s} className="rounded-full bg-black/5 px-2 py-0.5 text-navy-500">{s}</span>
          ))}
        </div>
      )}

      {/* Drill-down: signals + KG mini sub-graphs */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="mt-3 flex items-center gap-1 text-[13px] font-semibold text-accent-600 hover:text-accent-700"
      >
        <ChevronDown className={`h-4 w-4 transition ${open ? "rotate-180" : ""}`} />
        {open ? "Hide" : "Show"} the {c.n} signals + their knowledge-graph links
      </button>
      <div className="mt-1.5 flex justify-between">
        <button onClick={onSeeSignals} className="inline-flex items-center gap-1 text-[12px] font-semibold text-brand-600 hover:underline">
          See these signals <ArrowUpRight className="h-3.5 w-3.5" />
        </button>
      </div>

      {open && (
        <ul className="mt-2 space-y-3">
          {c.signals.map((s) => (
            <SignalRow key={s.signal_id} s={s} />
          ))}
        </ul>
      )}
    </section>
  );
}

function SignalRow({ s }: { s: HotSignal }) {
  const dir = (["opportunity", "risk", "watch"].includes(s.dir ?? "") ? s.dir : "watch") as Dir;
  return (
    <li className="border-t border-black/5 pt-3 first:border-t-0 first:pt-0">
      <div className="flex items-start gap-2">
        <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${DIR[dir].dot}`} />
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-medium leading-snug text-navy">{s.summary}</div>
          <div className="mt-0.5 text-[11px] text-navy-400">
            {s.type} · {s.date}
            {s.source && (
              <>
                {" · "}
                {s.url ? (
                  <a href={s.url} target="_blank" rel="noreferrer" className="text-navy-500 hover:underline">
                    {s.source} ↗
                  </a>
                ) : (
                  s.source
                )}
              </>
            )}
          </div>
          <MiniGraph sig={s} />
        </div>
      </div>
    </li>
  );
}

function Chip({ children, accent }: { children: React.ReactNode; accent?: boolean }) {
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-[12px] ${accent ? "bg-accent-50 font-semibold text-accent-700" : "bg-black/5 text-navy-500"}`}>
      {children}
    </span>
  );
}
