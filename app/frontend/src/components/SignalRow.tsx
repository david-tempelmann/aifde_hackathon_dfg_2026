import { CalendarDays, MapPin } from "lucide-react";
import type { Signal } from "../types";
import { confidenceColor, directionStyle, formatDate } from "../lib";
import { issueIcon, issueColor } from "../issueMeta";
import ScoreGauge from "./ScoreGauge";

// Compact card for the state swim lanes; clicking opens the detail drawer.
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
  const IssueIcon = issueIcon(signal.issue_label);
  const date = signal.event_date ?? signal.published_date;
  const conf = signal.confidence;
  const score = signal.priority_score != null ? Math.round(signal.priority_score * 100) : null;
  const hasCity = !!(signal.place_name && signal.state && signal.place_name !== signal.state);

  return (
    <button
      id={`signal-${signal.signal_id}`}
      onClick={() => onSelect(signal.signal_id)}
      className={`w-full rounded-xl border border-l-4 bg-white px-4 py-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md ${dir.accent} ${
        selected ? "border-brand-300 ring-2 ring-brand-400" : "border-black/10"
      }`}
    >
      <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[10px]">
        {signal.issue_label && (
          <span className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-2 py-0.5 font-medium text-brand-700">
            <IssueIcon className={`h-3 w-3 ${issueColor(signal.issue_label)}`} />
            {signal.issue_label}
          </span>
        )}
        {score != null && (
          <span
            className="ml-auto inline-flex items-center gap-1 text-[10px] font-medium text-navy-400"
            title="Priority score (impact, urgency, locality, evidence)"
          >
            Priority
            <ScoreGauge score={score} />
          </span>
        )}
      </div>

      <p className="line-clamp-3 min-h-[3.4rem] text-[13px] font-semibold leading-snug text-navy">{signal.summary}</p>

      <div className="mt-3 flex min-h-[1.75rem] items-center gap-3 text-[10px] text-navy-400">
        {hasCity ? (
          <span className="inline-flex items-start gap-1">
            <MapPin className="mt-0.5 h-3 w-3 shrink-0" />
            <span className="flex flex-col leading-tight">
              <span>{signal.place_name}</span>
              <span>{signal.state}</span>
            </span>
          </span>
        ) : (
          (signal.place_name || signal.state) && (
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3 w-3" />
              {signal.place_name || signal.state}
            </span>
          )
        )}
        {date && (
          <span className="inline-flex items-center gap-1">
            <CalendarDays className="h-3 w-3" />
            {formatDate(date)}
          </span>
        )}
        {conf != null && (
          <span className="ml-auto inline-flex items-center gap-1.5" title={`${Math.round(conf * 100)}% confidence`}>
            Confidence
            <span className="h-1.5 w-12 overflow-hidden rounded-full bg-navy/10">
              <span className={`block h-full ${confidenceColor(conf)}`} style={{ width: `${Math.round(conf * 100)}%` }} />
            </span>
          </span>
        )}
      </div>
    </button>
  );
}
