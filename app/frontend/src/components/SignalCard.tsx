import { ArrowRight, CalendarDays, ExternalLink, MapPin, Quote, TrendingUp } from "lucide-react";
import type { Signal } from "../types";
import {
  citationLink,
  confidenceColor,
  confidenceLabel,
  directionStyle,
  formatDate,
  humanizeType,
} from "../lib";

export default function SignalCard({
  signal,
  selected = false,
  onSelect,
}: {
  signal: Signal;
  selected?: boolean;
  onSelect?: (id: string) => void;
}) {
  const dir = directionStyle(signal.relevance_direction);
  const date = signal.event_date ?? signal.published_date;
  const conf = signal.confidence;
  const link = citationLink(signal.url, signal.quote);

  return (
    <article
      id={`signal-${signal.signal_id}`}
      onClick={onSelect ? () => onSelect(signal.signal_id) : undefined}
      className={`rounded-xl border bg-white p-5 shadow-sm transition border-l-4 ${dir.accent} ${
        onSelect ? "cursor-pointer" : ""
      } ${
        selected
          ? "border-brand-300 shadow-md ring-2 ring-brand-400"
          : "border-black/10 hover:shadow-md"
      }`}
    >
      {/* Header: direction, issue, place, date */}
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-semibold ring-1 ${dir.badge}`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${dir.dot}`} />
          {dir.label}
        </span>
        {signal.issue_label && (
          <span className="rounded-full bg-brand-50 px-2.5 py-1 font-medium text-brand-700">
            {signal.issue_label}
          </span>
        )}
        {signal.signal_type && (
          <span className="rounded-full bg-navy/5 px-2.5 py-1 text-navy-500">
            {humanizeType(signal.signal_type)}
          </span>
        )}
        {signal.priority_score != null && (
          <span
            className="inline-flex items-center gap-1 rounded-full bg-gold-100 px-2.5 py-1 font-semibold text-navy"
            title="Priority score (impact, urgency, locality, evidence)"
          >
            <TrendingUp className="h-3 w-3" />
            {Math.round(signal.priority_score)}
          </span>
        )}
        <span className="ml-auto flex items-center gap-3 text-navy-400">
          {(signal.place_name || signal.state) && (
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3.5 w-3.5" />
              {signal.place_name || signal.state}
              {signal.place_name && signal.state ? `, ${signal.state}` : ""}
            </span>
          )}
          {date && (
            <span className="inline-flex items-center gap-1">
              <CalendarDays className="h-3.5 w-3.5" />
              {formatDate(date)}
            </span>
          )}
        </span>
      </div>

      {/* Summary */}
      <p className="text-[15px] font-semibold leading-snug text-navy">
        {signal.summary}
      </p>

      {/* Why GO cares */}
      {signal.why_go && (
        <div className="mt-3 rounded-lg border-l-2 border-brand-500 bg-brand-50/70 p-3 text-sm text-navy">
          <span className="font-semibold text-brand-700">Why GO cares: </span>
          {signal.why_go}
        </div>
      )}

      {/* Recommended outreach action */}
      {signal.recommended_action && (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-accent-100 bg-accent-50/60 p-3 text-sm text-navy">
          <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-accent-600" />
          <span>
            <span className="font-semibold text-accent-700">Recommended action: </span>
            {signal.recommended_action}
          </span>
        </div>
      )}

      {/* Affected populations */}
      {Array.isArray(signal.affected_populations) && signal.affected_populations.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {signal.affected_populations.map((p) => (
            <span
              key={p}
              className="rounded-md bg-navy/[0.04] px-2 py-0.5 text-xs text-navy-500 ring-1 ring-navy/10"
            >
              {p}
            </span>
          ))}
        </div>
      )}

      {/* Citation */}
      {signal.quote && (
        <blockquote className="mt-4 flex gap-2 border-l-2 border-navy/15 pl-3 text-sm italic text-navy-500">
          <Quote className="mt-0.5 h-3.5 w-3.5 shrink-0 text-navy-400" />
          <span className="line-clamp-3">{signal.quote}</span>
        </blockquote>
      )}

      {/* Footer: source link + confidence */}
      <div className="mt-4 flex items-center justify-between gap-3 border-t border-black/5 pt-3 text-xs">
        {link ? (
          <a
            href={link}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="inline-flex items-center gap-1 font-medium text-brand-600 hover:text-brand-700 hover:underline"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            {signal.source || "Open source"}
          </a>
        ) : (
          <span className="text-navy-400">{signal.source || "No source"}</span>
        )}

        <div className="flex items-center gap-2" title={conf != null ? `${Math.round(conf * 100)}% confidence` : ""}>
          <span className="text-navy-400">{confidenceLabel(conf)} confidence</span>
          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-navy/10">
            <div
              className={`h-full ${confidenceColor(conf)}`}
              style={{ width: `${Math.round((conf ?? 0) * 100)}%` }}
            />
          </div>
        </div>
      </div>
    </article>
  );
}
