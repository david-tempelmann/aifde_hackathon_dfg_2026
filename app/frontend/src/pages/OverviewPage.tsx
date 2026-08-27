import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Activity, TrendingUp, AlertTriangle, Eye, Clock, type LucideIcon } from "lucide-react";
import { fetchOverview } from "../api";
import type { Hotspot, OverviewResponse } from "../types";
import { formatDate } from "../lib";
import { issueIcon } from "../issueMeta";
import CountUp from "../components/CountUp";

export default function OverviewPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchOverview()
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  // Pivot hotspot rows into { issue -> { state -> Hotspot } }, deriving the
  // issue rows and state columns from whatever the current data contains.
  const { issues, states, matrix, max } = useMemo(() => {
    const matrix: Record<string, Record<string, Hotspot>> = {};
    const stateTotals: Record<string, number> = {};
    let max = 0;
    for (const h of data?.hotspots ?? []) {
      (matrix[h.issue] ??= {})[h.state] = h;
      stateTotals[h.state] = (stateTotals[h.state] ?? 0) + h.n;
      if (h.n > max) max = h.n;
    }
    const issues = Object.keys(matrix).sort(
      (a, b) => total(matrix[b]) - total(matrix[a]),
    );
    const states = Object.keys(stateTotals).sort(
      (a, b) => stateTotals[b] - stateTotals[a] || a.localeCompare(b),
    );
    return { issues, states, matrix, max };
  }, [data]);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-[72px] animate-pulse rounded-xl bg-black/5" />
          ))}
        </div>
        <div className="h-72 animate-pulse rounded-xl bg-black/5" />
      </div>
    );
  }

  const s = data?.summary ?? {};

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-navy">Overview</h1>
        <p className="text-sm text-navy-400">
          Where the pressure is — signal density across issues and states to focus CarePortal
          partner outreach and advocacy.
        </p>
      </div>

      {/* Stat tiles */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Stat label="Total signals" value={s.total} icon={Activity} accent="brand" />
        <Stat label="Opportunities" value={s.opportunities} icon={TrendingUp} accent="emerald" />
        <Stat label="Risks" value={s.risks} icon={AlertTriangle} accent="rose" />
        <Stat label="Watch" value={s.watch} icon={Eye} accent="slate" />
        <Stat label="Latest" text={formatDate(s.latest ?? null)} icon={Clock} accent="navy" />
      </div>

      {/* Hotspot matrix */}
      <div className="rounded-xl border border-black/5 bg-white p-5 shadow-sm">
        <h2 className="mb-1 text-sm font-semibold text-navy">Issue × State hotspots</h2>
        <p className="mb-4 text-xs text-navy-400">
          Signal count per issue and state. Darker = more activity; bars show
          opportunity / risk / watch split.
        </p>
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
                      <Icon className="h-3.5 w-3.5 text-brand-600" />
                      {issue}
                    </span>
                  </td>
                  {states.map((st) => (
                    <td key={st} className="p-0">
                      <Cell
                        h={matrix[issue]?.[st]}
                        max={max}
                        onClick={() =>
                          navigate(`/?state=${encodeURIComponent(st)}&issue=${encodeURIComponent(issue)}`)
                        }
                      />
                    </td>
                  ))}
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function total(row: Record<string, Hotspot>): number {
  return Object.values(row).reduce((acc, h) => acc + h.n, 0);
}

const STAT_ACCENTS: Record<string, string> = {
  brand: "bg-brand-50 text-brand-600",
  emerald: "bg-emerald-50 text-emerald-600",
  rose: "bg-rose-50 text-rose-600",
  slate: "bg-slate-100 text-slate-500",
  navy: "bg-navy/5 text-navy",
};

function Stat({
  label,
  value,
  text,
  icon: Icon,
  accent = "navy",
}: {
  label: string;
  value?: number;
  text?: string;
  icon: LucideIcon;
  accent?: keyof typeof STAT_ACCENTS;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-black/5 bg-white p-4 shadow-sm transition hover:shadow-md">
      <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${STAT_ACCENTS[accent]}`}>
        <Icon className="h-5 w-5" />
      </span>
      <div className="min-w-0">
        <div className="text-2xl font-bold leading-none text-navy">
          {value != null ? <CountUp value={value} /> : (text ?? "—")}
        </div>
        <div className="mt-1 text-xs font-medium text-navy-400">{label}</div>
      </div>
    </div>
  );
}

function Cell({ h, max, onClick }: { h?: Hotspot; max: number; onClick?: () => void }) {
  if (!h || h.n === 0) {
    return <div className="h-full min-h-[52px] rounded-lg bg-black/[0.03]" />;
  }
  const intensity = max > 0 ? h.n / max : 0;
  const bg = `rgba(7, 115, 167, ${0.08 + intensity * 0.55})`; // CarePortal light blue
  const opp = h.opportunities;
  const risk = h.risks;
  const watch = h.watch;
  return (
    <button
      onClick={onClick}
      className="flex min-h-[52px] w-full flex-col justify-center gap-1 rounded-lg px-2 py-1.5 transition hover:ring-2 hover:ring-brand-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
      style={{ backgroundColor: bg }}
      title={`${h.n} signals — ${opp} opportunity, ${risk} risk, ${watch} watch · latest ${formatDate(
        h.latest,
      )} · click to view`}
    >
      <span className="text-center text-base font-bold text-navy">{h.n}</span>
      <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-white/60">
        {opp > 0 && <div className="bg-emerald-500" style={{ flex: opp }} />}
        {risk > 0 && <div className="bg-rose-500" style={{ flex: risk }} />}
        {watch > 0 && <div className="bg-slate-400" style={{ flex: watch }} />}
      </div>
    </button>
  );
}
