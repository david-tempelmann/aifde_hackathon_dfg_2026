import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { fetchOverview } from "../api";
import type { Hotspot, OverviewResponse } from "../types";
import { formatDate } from "../lib";

const STATES = ["NY", "CA", "VA"];

export default function OverviewPage() {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchOverview()
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  // Pivot hotspot rows into { issue -> { state -> Hotspot } }.
  const { issues, matrix, max } = useMemo(() => {
    const matrix: Record<string, Record<string, Hotspot>> = {};
    let max = 0;
    for (const h of data?.hotspots ?? []) {
      (matrix[h.issue] ??= {})[h.state] = h;
      if (h.n > max) max = h.n;
    }
    const issues = Object.keys(matrix).sort(
      (a, b) => total(matrix[b]) - total(matrix[a]),
    );
    return { issues, matrix, max };
  }, [data]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-400">
        <Loader2 className="h-6 w-6 animate-spin" />
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
        <Stat label="Total signals" value={s.total} />
        <Stat label="Opportunities" value={s.opportunities} tone="text-emerald-600" />
        <Stat label="Risks" value={s.risks} tone="text-rose-600" />
        <Stat label="Watch" value={s.watch} tone="text-slate-500" />
        <Stat label="Latest" value={formatDate(s.latest ?? null)} />
      </div>

      {/* Hotspot matrix */}
      <div className="rounded-xl border border-black/5 bg-white p-5 shadow-sm">
        <h2 className="mb-1 text-sm font-semibold text-navy">Issue × State hotspots</h2>
        <p className="mb-4 text-xs text-navy-400">
          Signal count per issue and state (NY / CA / VA). Darker = more activity; bars show
          opportunity / risk / watch split.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full border-separate border-spacing-1 text-sm">
            <thead>
              <tr>
                <th className="w-64 text-left text-xs font-medium text-navy-400">Issue</th>
                {STATES.map((st) => (
                  <th key={st} className="px-2 text-center text-xs font-semibold text-navy-600">
                    {st}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {issues.map((issue) => (
                <tr key={issue}>
                  <td className="py-1 pr-2 text-navy">{issue}</td>
                  {STATES.map((st) => (
                    <td key={st} className="p-0">
                      <Cell h={matrix[issue]?.[st]} max={max} />
                    </td>
                  ))}
                </tr>
              ))}
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

function Stat({
  label,
  value,
  tone = "text-navy",
}: {
  label: string;
  value: number | string | undefined;
  tone?: string;
}) {
  return (
    <div className="rounded-xl border border-black/5 bg-white p-4 shadow-sm">
      <div className={`text-2xl font-bold ${tone}`}>{value ?? "—"}</div>
      <div className="mt-0.5 text-xs font-medium text-navy-400">{label}</div>
    </div>
  );
}

function Cell({ h, max }: { h?: Hotspot; max: number }) {
  if (!h || h.n === 0) {
    return <div className="h-full min-h-[52px] rounded-lg bg-black/[0.03]" />;
  }
  const intensity = max > 0 ? h.n / max : 0;
  const bg = `rgba(7, 115, 167, ${0.08 + intensity * 0.55})`; // CarePortal light blue
  const opp = h.opportunities;
  const risk = h.risks;
  const watch = h.watch;
  return (
    <div
      className="flex min-h-[52px] flex-col justify-center gap-1 rounded-lg px-2 py-1.5"
      style={{ backgroundColor: bg }}
      title={`${h.n} signals — ${opp} opportunity, ${risk} risk, ${watch} watch · latest ${formatDate(
        h.latest,
      )}`}
    >
      <span className="text-center text-base font-bold text-navy">{h.n}</span>
      <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-white/60">
        {opp > 0 && <div className="bg-emerald-500" style={{ flex: opp }} />}
        {risk > 0 && <div className="bg-rose-500" style={{ flex: risk }} />}
        {watch > 0 && <div className="bg-slate-400" style={{ flex: watch }} />}
      </div>
    </div>
  );
}
