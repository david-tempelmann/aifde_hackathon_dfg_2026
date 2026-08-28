import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Telescope, Loader2, RefreshCw, AlertTriangle, Radar } from "lucide-react";
import { fetchDeepDive, fetchDeepDiveOptions } from "../api";
import type { DeepDivePayload } from "../types";
import FindingsPanel from "../components/FindingsPanel";

const FALLBACK_TOPICS = [
  "Housing stability & homelessness",
  "Poverty & economic support",
  "Education access",
  "Family preservation & foster care",
  "Child welfare & protection",
  "Youth mental health",
  "Healthcare access",
  "Emergency & disaster response",
  "Food & material needs",
];
const FALLBACK_REGIONS = ["All", "CA", "NY", "VA"];

export default function DeepDivePage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [topics, setTopics] = useState<string[]>(FALLBACK_TOPICS);
  const [regions, setRegions] = useState<string[]>(FALLBACK_REGIONS);

  const [topic, setTopic] = useState(params.get("topic") ?? FALLBACK_TOPICS[0]);
  const [region, setRegion] = useState(params.get("region") ?? "VA");

  const [data, setData] = useState<DeepDivePayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchDeepDiveOptions()
      .then((o) => {
        if (o.topics?.length) setTopics(o.topics);
        if (o.regions?.length) setRegions(o.regions);
      })
      .catch(() => {/* keep fallbacks */});
  }, []);

  function seeSignals() {
    const p = new URLSearchParams();
    if (region && region !== "All") p.set("state", region);
    p.set("issue", topic);
    navigate(`/signals?${p.toString()}`);
  }

  async function run(refresh = false) {
    setLoading(true);
    setError(null);
    setParams({ topic, region }, { replace: true });
    try {
      const payload = await fetchDeepDive({ topic, region, refresh });
      setData(payload);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Deep-dive failed");
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-bold text-navy">
          <Telescope className="h-5 w-5 text-accent-600" />
          Topic Deep-Dive
        </h1>
        <p className="text-sm text-navy-400">
          Ask the Genie agent for decision-oriented findings on a topic — who to recruit, the best
          upcoming hearing, funding already in play, and where families are in acute crisis — grounded
          in the scraped signals.
        </p>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-black/5 bg-white p-4 shadow-sm">
        <label className="flex flex-col gap-1 text-xs font-medium text-navy-400">
          Topic
          <select
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            className="min-w-[16rem] rounded-lg border border-black/10 px-3 py-2 text-sm text-navy focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
          >
            {topics.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-navy-400">
          Region
          <select
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            className="rounded-lg border border-black/10 px-3 py-2 text-sm text-navy focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
          >
            {regions.map((r) => (
              <option key={r} value={r}>{r === "All" ? "National" : r}</option>
            ))}
          </select>
        </label>
        <button
          onClick={() => run(false)}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg bg-accent-500 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-accent-600 disabled:opacity-60"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Telescope className="h-4 w-4" />}
          {loading ? "Asking Genie…" : "Run analysis"}
        </button>
        {data && !loading && (
          <button
            onClick={() => run(true)}
            className="inline-flex items-center gap-2 rounded-lg border border-black/10 bg-white px-3 py-2 text-sm font-semibold text-navy-500 transition hover:bg-black/[0.03]"
            title="Re-run Genie (bypass cache)"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        )}
        <button
          onClick={seeSignals}
          className="inline-flex items-center gap-2 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-sm font-semibold text-brand-600 transition hover:bg-brand-100"
          title="Open the Signals feed filtered to this topic and region"
        >
          <Radar className="h-4 w-4" />
          See signals
        </button>
        {data?.cached && !loading && (
          <span className="text-xs text-navy-400">cached · {new Date(data.generated_at).toLocaleString()}</span>
        )}
      </div>

      {/* States */}
      {loading && (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-black/5 bg-white py-16 text-navy-400 shadow-sm">
          <Loader2 className="h-8 w-8 animate-spin text-accent-500" />
          <p className="text-sm">Genie is running its certified findings query — this can take 20–40s on a cold run.</p>
        </div>
      )}

      {error && !loading && (
        <div className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <div>
            <div className="font-semibold">Couldn't get findings</div>
            <div className="mt-0.5 text-rose-600">{error}</div>
          </div>
        </div>
      )}

      {!loading && !error && !data && (
        <div className="rounded-xl border border-dashed border-black/10 bg-white/60 py-16 text-center text-sm text-navy-400">
          Pick a topic and region, then <span className="font-semibold text-navy-500">Run analysis</span>.
        </div>
      )}

      {data && !loading && <FindingsPanel data={data} />}
    </div>
  );
}
