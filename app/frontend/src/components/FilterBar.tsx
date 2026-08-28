import { Search, X } from "lucide-react";
import type { FilterOptions, SignalQuery } from "../types";

interface Props {
  options: FilterOptions;
  query: SignalQuery;
  onChange: (patch: Partial<SignalQuery>) => void;
  onReset: () => void;
}

function Select({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string | undefined;
  onChange: (v: string) => void;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs font-medium text-navy-400">
      {label}
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-navy/15 bg-white px-2.5 py-2 text-sm font-normal text-navy shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
      >
        {children}
      </select>
    </label>
  );
}

export default function FilterBar({ options, query, onChange, onReset }: Props) {
  const states = options.state ?? [];
  const issues = options.issue ?? [];
  const types = options.signal_type ?? [];
  const hasFilters =
    !!query.state ||
    !!query.direction ||
    !!query.issue ||
    !!query.signal_type ||
    !!query.search ||
    (query.min_confidence ?? 0) > 0;

  return (
    <div className="rounded-xl border border-black/5 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-end gap-3">
        {/* Search */}
        <label className="flex min-w-[220px] flex-1 flex-col gap-1 text-xs font-medium text-navy-400">
          Search
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-navy-400" />
            <input
              type="text"
              value={query.search ?? ""}
              onChange={(e) => onChange({ search: e.target.value })}
              placeholder="issue, place, keyword…"
              className="w-full rounded-lg border border-navy/15 bg-white py-2 pl-8 pr-2.5 text-sm font-normal text-navy shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>
        </label>

        <Select label="State" value={query.state} onChange={(v) => onChange({ state: v })}>
          <option value="">All states</option>
          {states.map((o) => (
            <option key={o.value} value={o.value}>
              {o.value} ({o.count})
            </option>
          ))}
        </Select>

        <Select
          label="Direction"
          value={query.direction}
          onChange={(v) => onChange({ direction: v })}
        >
          <option value="">All</option>
          <option value="opportunity">Opportunity</option>
          <option value="risk">Risk</option>
          <option value="watch">Watch</option>
        </Select>

        <Select label="Issue" value={query.issue} onChange={(v) => onChange({ issue: v })}>
          <option value="">All issues</option>
          {issues.map((o) => (
            <option key={o.value} value={o.value}>
              {o.value}
            </option>
          ))}
        </Select>

        <Select
          label="Type"
          value={query.signal_type}
          onChange={(v) => onChange({ signal_type: v })}
        >
          <option value="">All types</option>
          {types.map((o) => (
            <option key={o.value} value={o.value}>
              {o.value.replace(/_/g, " ")} ({o.count})
            </option>
          ))}
        </Select>

        <Select label="Sort" value={query.sort} onChange={(v) => onChange({ sort: v })}>
          <option value="priority">Top priority</option>
          <option value="recent">Most recent</option>
          <option value="confidence">Highest confidence</option>
        </Select>

        {/* Min confidence */}
        <label className="flex w-40 flex-col gap-1 text-xs font-medium text-navy-400">
          Min confidence: {Math.round((query.min_confidence ?? 0) * 100)}%
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={query.min_confidence ?? 0}
            onChange={(e) => onChange({ min_confidence: Number(e.target.value) })}
            className="accent-brand-500"
          />
        </label>

        {hasFilters && (
          <button
            onClick={onReset}
            className="inline-flex items-center gap-1 rounded-lg px-2.5 py-2 text-sm font-medium text-navy-400 hover:bg-brand-50 hover:text-navy"
          >
            <X className="h-4 w-4" /> Clear
          </button>
        )}
      </div>
    </div>
  );
}
