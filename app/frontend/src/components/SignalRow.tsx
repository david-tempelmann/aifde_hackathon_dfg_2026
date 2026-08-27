import { CalendarDays, MapPin, TrendingUp } from "lucide-react";
import type { Signal } from "../types";
import { confidenceColor, directionStyle, formatDate } from "../lib";

// Concise, scannable representation of a signal used in both the list and the
// map's side column. Clicking it opens the full detail drawer — no full detail
// is shown inline (that lives only in the drawer).
export default function SignalRow({
  signal,
  selected = false,
  onSelect,
}: {
  signal: Signal;
  selected?: boolean;
  onSelect: (id: string) => void;
}) {
  const dir = directionStyle(signal.relevance_direction);
  const date = signal.event_date ?? signal.published_date;
  const conf = signal.confidence;
  const place =
    signal.place_name && signal.state && signal.place_name !== signal.state
      ? `${signal.place_name}, ${signal.state}`
      : signal.place_name || signal.state;

  return (
    <button
      id={`signal-${signal.signal_id}`}
      onClick={() => onSelect(signal.signal_id)}
      className={`w-full rounded-xl border border-l-4 bg-white p-3.5 text-left shadow-sm transition hover:shadow-md ${dir.accent} ${
        selected ? "border-brand-300 ring-2 ring-brand-400" : "border-black/10"
      }`}
    >
      <div className="mb-1.5 flex flex-wrap items-center gap-1.5 text-[11px]">
        {signal.issue_label && (
          <span className="rounded-full bg-brand-50 px-2 py-0.5 font-medium text-brand-700">
            {signal.issue_label}
          </span>
        )}
        {signal.priority_score != null && (
          <span
            className="ml-auto inline-flex items-center gap-1 rounded-full bg-gold-100 px-2 py-0.5 font-semibold text-navy"
            title="Priority score (impact, urgency, locality, evidence)"
          >
            <TrendingUp className="h-3 w-3" />
            {Math.round(signal.priority_score * 100)}
          </span>
        )}
      </div>

      <p className="line-clamp-2 text-sm font-semibold leading-snug text-navy">{signal.summary}</p>

      <div className="mt-2 flex items-center gap-3 text-[11px] text-navy-400">
        {place && (
          <span className="inline-flex items-center gap-1">
            <MapPin className="h-3 w-3" />
            {place}
          </span>
        )}
        {date && (
          <span className="inline-flex items-center gap-1">
            <CalendarDays className="h-3 w-3" />
            {formatDate(date)}
          </span>
        )}
        {conf != null && (
          <span className="ml-auto inline-flex items-center gap-1.5" title={`${Math.round(conf * 100)}% confidence`}>
            <span className="h-1.5 w-12 overflow-hidden rounded-full bg-navy/10">
              <span className={`block h-full ${confidenceColor(conf)}`} style={{ width: `${Math.round(conf * 100)}%` }} />
            </span>
          </span>
        )}
      </div>
    </button>
  );
}
