import { useState } from "react";
import { ChevronDown, Search, X } from "lucide-react";
import type { ConfidenceBucket } from "../lib";
import { directionStyle, humanizeType } from "../lib";
import { issueIcon } from "../issueMeta";

export type FilterFacet = "states" | "directions" | "issues" | "types" | "confidence";

export interface SignalFilters {
  states: string[];
  directions: string[];
  issues: string[];
  types: string[];
  confidence: string[];
  search: string;
}

export interface FacetOption {
  value: string;
  count: number;
}

export const EMPTY_FILTERS: SignalFilters = {
  states: [],
  directions: [],
  issues: [],
  types: [],
  confidence: [],
  search: "",
};

const CONFIDENCE_BUCKETS: { key: ConfidenceBucket; label: string; desc: string; dot: string }[] = [
  { key: "high", label: "High confidence", desc: "Strong, well-corroborated evidence — safe to act on.", dot: "bg-emerald-500" },
  { key: "medium", label: "Medium confidence", desc: "Reasonable evidence — worth a quick check before acting.", dot: "bg-amber-500" },
  { key: "low", label: "Low confidence", desc: "An early or thin signal — treat it as a lead to verify.", dot: "bg-rose-400" },
];

function Tag({
  active,
  onClick,
  title,
  children,
}: {
  active: boolean;
  onClick: () => void;
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-pressed={active}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition ${
        active
          ? "border-brand-600 bg-brand-600 text-white shadow-sm"
          : "border-navy/15 bg-white text-navy-500 hover:border-brand-400 hover:text-navy"
      }`}
    >
      {children}
    </button>
  );
}

function Section({
  title,
  count = 0,
  defaultOpen = true,
  children,
}: {
  title: string;
  count?: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between py-1 text-left"
      >
        <span className="text-xs font-semibold uppercase tracking-wide text-navy-400">{title}</span>
        <span className="flex items-center gap-1.5">
          {count > 0 && (
            <span className="rounded-full bg-brand-100 px-1.5 text-[10px] font-bold text-brand-700">{count}</span>
          )}
          <ChevronDown className={`h-4 w-4 text-navy-300 transition ${open ? "" : "-rotate-90"}`} />
        </span>
      </button>
      {open && <div className="mt-1.5">{children}</div>}
    </div>
  );
}

interface Props {
  facets: { states: FacetOption[]; directions: FacetOption[]; issues: FacetOption[]; types: FacetOption[] };
  filters: SignalFilters;
  onToggle: (facet: FilterFacet, value: string) => void;
  onSearch: (value: string) => void;
  onReset: () => void;
}

export default function FilterPanel({ facets, filters, onToggle, onSearch, onReset }: Props) {
  const hasFilters =
    filters.states.length > 0 ||
    filters.directions.length > 0 ||
    filters.issues.length > 0 ||
    filters.types.length > 0 ||
    filters.confidence.length > 0 ||
    filters.search.trim().length > 0;

  return (
    <div className="space-y-4 rounded-xl border border-black/5 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <span className="text-sm font-bold text-navy">Filters</span>
        {hasFilters && (
          <button
            onClick={onReset}
            className="inline-flex items-center gap-1 text-xs font-medium text-navy-400 hover:text-navy"
          >
            <X className="h-3.5 w-3.5" /> Clear all
          </button>
        )}
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-navy-400" />
        <input
          type="text"
          value={filters.search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Search issue, place, keyword…"
          className="w-full rounded-lg border border-navy/15 bg-white py-2 pl-8 pr-2.5 text-sm text-navy shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
      </div>

      {/* Direction */}
      {facets.directions.length > 0 && (
        <Section title="Direction" count={filters.directions.length}>
          <div className="flex flex-wrap gap-1.5">
            {facets.directions.map((o) => {
              const dir = directionStyle(o.value);
              return (
                <Tag
                  key={o.value}
                  active={filters.directions.includes(o.value)}
                  onClick={() => onToggle("directions", o.value)}
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${dir.dot}`} />
                  {dir.label} ({o.count})
                </Tag>
              );
            })}
          </div>
        </Section>
      )}

      {/* Confidence buckets — compact, with visible plain-language descriptions. */}
      <Section title="Confidence" count={filters.confidence.length}>
        <div className="space-y-1">
          {CONFIDENCE_BUCKETS.map((b) => {
            const active = filters.confidence.includes(b.key);
            return (
              <button
                key={b.key}
                type="button"
                onClick={() => onToggle("confidence", b.key)}
                aria-pressed={active}
                className={`w-full rounded-lg border px-2.5 py-1.5 text-left transition ${
                  active
                    ? "border-brand-400 bg-brand-50 ring-1 ring-brand-300"
                    : "border-navy/15 bg-white hover:border-brand-300"
                }`}
              >
                <div className="flex items-center gap-1.5">
                  <span className={`h-1.5 w-1.5 rounded-full ${b.dot}`} />
                  <span className="text-xs font-semibold text-navy">{b.label}</span>
                </div>
                <p className="mt-0.5 text-[11px] leading-tight text-navy-400">{b.desc}</p>
              </button>
            );
          })}
        </div>
      </Section>

      {/* State */}
      {facets.states.length > 0 && (
        <Section title="State" count={filters.states.length}>
          <div className="flex flex-wrap gap-1.5">
            {facets.states.map((o) => (
              <Tag
                key={o.value}
                active={filters.states.includes(o.value)}
                onClick={() => onToggle("states", o.value)}
              >
                {o.value} ({o.count})
              </Tag>
            ))}
          </div>
        </Section>
      )}

      {/* Issue */}
      {facets.issues.length > 0 && (
        <Section title="Issue" count={filters.issues.length} defaultOpen={false}>
          <div className="flex flex-wrap gap-1.5">
            {facets.issues.map((o) => {
              const Icon = issueIcon(o.value);
              return (
                <Tag
                  key={o.value}
                  active={filters.issues.includes(o.value)}
                  onClick={() => onToggle("issues", o.value)}
                >
                  <Icon className="h-3 w-3" />
                  {o.value}
                </Tag>
              );
            })}
          </div>
        </Section>
      )}

      {/* Signal type */}
      {facets.types.length > 0 && (
        <Section title="Type" count={filters.types.length} defaultOpen={false}>
          <div className="flex flex-wrap gap-1.5">
            {facets.types.map((o) => (
              <Tag
                key={o.value}
                active={filters.types.includes(o.value)}
                onClick={() => onToggle("types", o.value)}
              >
                {humanizeType(o.value)} ({o.count})
              </Tag>
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}
