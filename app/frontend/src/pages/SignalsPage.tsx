import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Inbox, Map as MapIcon, Check, ArrowLeft } from "lucide-react";
import { fetchSignals } from "../api";
import type { Signal } from "../types";
import { buildStateColors, resolveCoords, STATE_CODE_TO_NAME } from "../geo";
import { confidenceBucket, directionStyle } from "../lib";
import FilterPanel, {
  EMPTY_FILTERS,
  type FilterFacet,
  type SignalFilters,
} from "../components/FilterPanel";
import SignalRow from "../components/SignalRow";
import SignalMap from "../components/SignalMap";
import SignalDrawer from "../components/SignalDrawer";

const DIRECTIONS = ["opportunity", "risk", "watch"];
// Swim-lane order for the card board.
const LANE_KEYS = ["opportunity", "risk", "watch"] as const;
const LANE_CAP = 3; // cards per swim lane before "+N more"

export default function SignalsPage() {
  const [searchParams] = useSearchParams();
  const [all, setAll] = useState<Signal[]>([]);
  // Initialise filters from ?state=/?issue= (e.g. arriving from an Overview cell).
  const [filters, setFilters] = useState<SignalFilters>(() => {
    const init = { ...EMPTY_FILTERS };
    const st = searchParams.get("state");
    const issue = searchParams.get("issue");
    if (st) init.states = [st];
    if (issue) init.issues = [issue];
    return init;
  });
  const [sort, setSort] = useState("priority");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showMap, setShowMap] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [expandedLanes, setExpandedLanes] = useState<Set<string>>(new Set());

  // Fetch the whole (small) set once; all filtering/sorting is client-side so
  // multi-select tags and confidence buckets stay instant.
  useEffect(() => {
    setLoading(true);
    fetchSignals({ limit: 200 })
      .then((r) => setAll(r.signals))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  // Facet options + counts, derived from the full set.
  const facets = useMemo(() => {
    const tally = (get: (s: Signal) => string | null | undefined) => {
      const m = new Map<string, number>();
      for (const s of all) {
        const v = get(s);
        if (v) m.set(v, (m.get(v) ?? 0) + 1);
      }
      return [...m.entries()]
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
        .map(([value, count]) => ({ value, count }));
    };
    return {
      states: tally((s) => s.state),
      directions: DIRECTIONS.map((value) => ({
        value,
        count: all.filter((s) => s.relevance_direction === value).length,
      })).filter((o) => o.count > 0),
      issues: tally((s) => s.issue_label),
      types: tally((s) => s.signal_type),
    };
  }, [all]);

  const debouncedSearch = useDebounce(filters.search, 250);

  // Apply filters (multi-select = OR within a facet, AND across facets).
  const filtered = useMemo(() => {
    const q = debouncedSearch.trim().toLowerCase();
    return all.filter((s) => {
      if (filters.states.length && !filters.states.includes(s.state ?? "")) return false;
      if (filters.directions.length && !filters.directions.includes(s.relevance_direction ?? "")) return false;
      if (filters.issues.length && !filters.issues.includes(s.issue_label ?? "")) return false;
      if (filters.types.length && !filters.types.includes(s.signal_type ?? "")) return false;
      if (filters.confidence.length && !filters.confidence.includes(confidenceBucket(s.confidence))) return false;
      if (q) {
        const hay = [s.summary, s.why_go, s.quote, s.issue_label, s.place_name, s.state]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [all, filters, debouncedSearch]);

  // Sort client-side.
  const signals = useMemo(() => {
    const dateVal = (s: Signal) => Date.parse(s.event_date ?? s.published_date ?? "") || 0;
    const arr = [...filtered];
    if (sort === "recent") {
      arr.sort((a, b) => dateVal(b) - dateVal(a) || (b.priority_score ?? 0) - (a.priority_score ?? 0));
    } else if (sort === "confidence") {
      arr.sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0) || (b.priority_score ?? 0) - (a.priority_score ?? 0));
    } else {
      arr.sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0) || dateVal(b) - dateVal(a));
    }
    return arr;
  }, [filtered, sort]);

  // Reset "show more" state whenever the query changes.
  useEffect(() => {
    setExpandedLanes(new Set());
  }, [filters, sort]);

  // Drop stale selection/detail when no longer in the result set.
  useEffect(() => {
    if (selectedId && !signals.some((s) => s.signal_id === selectedId)) setSelectedId(null);
    if (detailId && !signals.some((s) => s.signal_id === detailId)) setDetailId(null);
  }, [signals, selectedId, detailId]);

  const toggle = (facet: FilterFacet, value: string) =>
    setFilters((f) => {
      const arr = f[facet];
      const next = arr.includes(value) ? arr.filter((v) => v !== value) : [...arr, value];
      return { ...f, [facet]: next };
    });

  const openDetail = (id: string) => {
    setSelectedId(id);
    setDetailId(id);
    requestAnimationFrame(() => {
      document.getElementById(`signal-${id}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  };

  // Clicking a state (map or card header) applies it as a state-level filter.
  const toggleStateFilter = (code: string) => {
    setShowMap(true);
    setFilters((f) => ({
      ...f,
      states: f.states.includes(code) ? f.states.filter((s) => s !== code) : [...f.states, code],
    }));
  };

  const clearStates = () => setFilters((f) => ({ ...f, states: [] }));

  const detailSignal = useMemo(
    () => signals.find((s) => s.signal_id === detailId) ?? null,
    [signals, detailId],
  );

  const mappable = useMemo(() => signals.filter((s) => resolveCoords(s) !== null).length, [signals]);

  // Group signals by state, most-active first.
  const grouped = useMemo(() => {
    const m = new Map<string, Signal[]>();
    for (const s of signals) {
      const code = s.state ?? "Other";
      const arr = m.get(code);
      if (arr) arr.push(s);
      else m.set(code, [s]);
    }
    return [...m.entries()].sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]));
  }, [signals]);

  const stateColors = useMemo(
    () => buildStateColors(grouped.map(([c]) => c).filter((c) => c !== "Other")),
    [grouped],
  );

  const sortControl = (
    <label className="inline-flex items-center gap-1.5">
      <span className="text-xs font-medium text-navy-400">Sort by</span>
      <select
        value={sort}
        onChange={(e) => setSort(e.target.value)}
        aria-label="Sort signals"
        className="rounded-lg border border-navy/15 bg-white px-2.5 py-1.5 text-sm text-navy shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
      >
        <option value="priority">Priority</option>
        <option value="recent">Most recent</option>
        <option value="confidence">Highest confidence</option>
      </select>
    </label>
  );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold text-navy">Outreach signals</h1>
        <p className="text-sm text-navy-400">
          Region-specific legislative and community signals — each cited, dated, and scored — to help
          State Directors recruit CarePortal partners and craft outreach that resonates.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[19rem_minmax(0,1fr)]">
        {/* Filters — sidebar */}
        <aside className="lg:sticky lg:top-24 lg:self-start lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto lg:pr-1">
          <FilterPanel
            facets={facets}
            filters={filters}
            onToggle={toggle}
            onSearch={(v) => setFilters((f) => ({ ...f, search: v }))}
            onReset={() => setFilters(EMPTY_FILTERS)}
          />
        </aside>

        {/* Results */}
        <div className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-navy-400">
            <span>
              {loading
                ? "Loading…"
                : `${signals.length} signal${signals.length === 1 ? "" : "s"}` +
                  (showMap && mappable < signals.length ? ` · ${mappable} on map` : "")}
            </span>
            <div className="flex items-center gap-2">
              {!showMap && sortControl}
              <button
                onClick={() => setShowMap((v) => !v)}
                className={`inline-flex items-center gap-1.5 rounded-lg border border-navy/15 px-3 py-1.5 text-sm font-semibold shadow-sm transition ${
                  showMap ? "bg-brand-50 text-brand-700" : "bg-white text-navy-400 hover:text-navy"
                }`}
                aria-pressed={showMap}
              >
                <MapIcon className="h-4 w-4" />
                {showMap ? "Hide map" : "Show map"}
              </button>
            </div>
          </div>

          {showMap && !loading && signals.length > 0 && (
            <div className="relative isolate z-0 h-72 overflow-hidden rounded-xl sm:h-80">
              <SignalMap
                signals={signals}
                selectedId={selectedId}
                onSelect={openDetail}
                selectedStates={filters.states}
                onToggleState={toggleStateFilter}
              />
              {filters.states.length > 0 && (
                <button
                  onClick={clearStates}
                  className="absolute right-3 top-3 z-[1000] inline-flex items-center gap-1.5 rounded-lg border border-navy/15 bg-white/95 px-3 py-1.5 text-xs font-semibold text-navy shadow-md backdrop-blur transition hover:bg-white"
                >
                  <ArrowLeft className="h-3.5 w-3.5" /> Go back to full view
                </button>
              )}
              {/* Legend */}
              <div className="absolute bottom-3 left-3 z-[1000] rounded-lg bg-white/90 px-2.5 py-2 text-[10px] shadow-sm ring-1 ring-black/5 backdrop-blur">
                <div className="mb-1 font-semibold uppercase tracking-wide text-navy-400">Signals</div>
                <div className="flex flex-col gap-0.5 text-navy-500">
                  <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-emerald-500" /> Opportunity</span>
                  <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-rose-500" /> Risk</span>
                  <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-slate-400" /> Watch</span>
                </div>
              </div>
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
              Failed to load signals: {error}
            </div>
          )}

          {loading ? (
            <div className="grid gap-3 md:grid-cols-3">
              {[0, 1, 2].map((col) => (
                <div key={col} className="space-y-2">
                  <div className="h-4 w-24 animate-pulse rounded bg-black/5" />
                  {[0, 1, 2].map((i) => (
                    <div key={i} className="h-28 animate-pulse rounded-xl bg-black/5" />
                  ))}
                </div>
              ))}
            </div>
          ) : signals.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-20 text-navy-400">
              <Inbox className="h-8 w-8" />
              <p className="text-sm">No signals match these filters.</p>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Sort sits under the map when the map is shown; when hidden it
                  moves up next to the Hide/Show map button. */}
              {showMap && <div className="flex justify-end">{sortControl}</div>}

              <div className="space-y-6">
                {grouped.map(([code, group]) => {
                const isSelected = filters.states.includes(code);
                const clickable = code !== "Other";
                return (
                  <section key={code} id={`state-${code}`} className="scroll-mt-24 space-y-3">
                    <button
                      onClick={() => clickable && toggleStateFilter(code)}
                      disabled={!clickable}
                      className={`group flex items-center gap-2 rounded-lg px-2 py-1 text-left transition ${
                        isSelected ? "bg-brand-50" : clickable ? "hover:bg-brand-50/60" : ""
                      }`}
                      title={!clickable ? undefined : isSelected ? "Clear state filter" : "Filter to this state"}
                    >
                      <span
                        className="h-2.5 w-2.5 shrink-0 rounded-full ring-2 ring-white"
                        style={{ backgroundColor: stateColors.get(code) ?? "#cbd5e1" }}
                      />
                      <span
                        className={`text-sm font-bold ${
                          isSelected ? "text-brand-700" : "text-navy group-hover:text-brand-700"
                        }`}
                      >
                        {STATE_CODE_TO_NAME[code] ?? code}
                      </span>
                      <span className="rounded-full bg-navy/5 px-2 py-0.5 text-xs font-semibold text-navy-500">
                        {group.length}
                      </span>
                      {clickable &&
                        (isSelected ? (
                          <span className="inline-flex items-center gap-1 text-xs font-medium text-brand-600">
                            <Check className="h-3.5 w-3.5" /> Filtered
                          </span>
                        ) : (
                          <MapIcon className="h-3.5 w-3.5 text-navy-300 transition group-hover:text-brand-500" />
                        ))}
                    </button>

                    {/* Swim lanes: opportunity / risk / watch */}
                    <div className="grid gap-3 md:grid-cols-3">
                      {LANE_KEYS.map((key) => {
                        const ls = directionStyle(key);
                        const laneCards = group.filter((s) => (s.relevance_direction ?? "watch") === key);
                        const laneKey = `${code}|${key}`;
                        const laneExpanded = expandedLanes.has(laneKey);
                        const shown = laneExpanded ? laneCards : laneCards.slice(0, LANE_CAP);
                        return (
                          <div key={key} className="space-y-2">
                            <div className="flex items-center gap-1.5 border-b border-black/5 pb-1 text-xs font-semibold text-navy-500">
                              <span className={`h-2 w-2 rounded-full ${ls.dot}`} />
                              {ls.label}
                              <span className="text-navy-300">({laneCards.length})</span>
                            </div>
                            {laneCards.length === 0 ? (
                              <p className="rounded-lg border border-dashed border-black/10 px-2 py-3 text-center text-xs text-navy-300">
                                None
                              </p>
                            ) : (
                              <>
                                {shown.map((s) => (
                                  <SignalRow
                                    key={s.signal_id}
                                    signal={s}
                                    selected={s.signal_id === selectedId}
                                    onSelect={openDetail}
                                  />
                                ))}
                                {laneCards.length > LANE_CAP && !laneExpanded && (
                                  <button
                                    onClick={() =>
                                      setExpandedLanes((prev) => new Set(prev).add(laneKey))
                                    }
                                    className="w-full rounded-lg border border-dashed border-navy/20 py-1.5 text-xs font-semibold text-brand-600 transition hover:bg-brand-50"
                                  >
                                    +{laneCards.length - LANE_CAP} more
                                  </button>
                                )}
                              </>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </section>
                );
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      <SignalDrawer signal={detailSignal} onClose={() => setDetailId(null)} />
    </div>
  );
}

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}
