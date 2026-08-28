import { useEffect } from "react";
import { ArrowRight, CalendarDays, ExternalLink, MapPin, Quote, TrendingUp, X } from "lucide-react";
import type { Signal } from "../types";
import {
  citationLink,
  confidenceColor,
  confidenceLabel,
  directionStyle,
  formatDate,
  humanizeType,
} from "../lib";
import OutreachStudio from "./OutreachStudio";
import { issueIcon, issueColor } from "../issueMeta";

function Meta({ label, value }: { label: string; value: React.ReactNode }) {
  if (value == null || value === "") return null;
  return (
    <div>
      <dt className="text-xs font-medium text-navy-400">{label}</dt>
      <dd className="text-sm font-medium text-navy">{value}</dd>
    </div>
  );
}

export default function SignalDrawer({
  signal,
  onClose,
}: {
  signal: Signal | null;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!signal) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [signal, onClose]);

  if (!signal) return null;

  const dir = directionStyle(signal.relevance_direction);
  const IssueIcon = issueIcon(signal.issue_label);
  const date = signal.event_date ?? signal.published_date;
  const conf = signal.confidence;
  const link = citationLink(signal.url, signal.quote);
  const place =
    signal.place_name && signal.state && signal.place_name !== signal.state
      ? `${signal.place_name}, ${signal.state}`
      : signal.place_name || signal.state;

  return (
    <div className="fixed inset-0 z-50">
      <div
        className="absolute inset-0 bg-navy/40 backdrop-blur-[1px]"
        onClick={onClose}
        aria-hidden
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={signal.summary ?? "Signal detail"}
        className="absolute right-0 top-0 flex h-full w-full flex-col bg-canvas shadow-2xl md:w-1/2"
      >
        <div className={`flex items-start gap-3 border-b border-black/5 border-l-4 ${dir.accent} bg-white px-5 py-4`}>
          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-semibold ring-1 ${dir.badge}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${dir.dot}`} />
                {dir.label}
              </span>
              {signal.priority_score != null && (
                <span className="inline-flex items-center gap-1 rounded-full bg-gold-100 px-2.5 py-1 font-semibold text-navy">
                  <TrendingUp className="h-3 w-3" />
                  Priority {Math.round(signal.priority_score * 100)}
                </span>
              )}
            </div>
            <h2 className="text-lg font-bold leading-snug text-navy">{signal.summary}</h2>
            <div className="flex flex-wrap items-center gap-3 text-xs text-navy-400">
              {place && (
                <span className="inline-flex items-center gap-1">
                  <MapPin className="h-3.5 w-3.5" />
                  {place}
                </span>
              )}
              {date && (
                <span className="inline-flex items-center gap-1">
                  <CalendarDays className="h-3.5 w-3.5" />
                  {formatDate(date)}
                </span>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-1.5 text-navy-400 transition hover:bg-brand-50 hover:text-navy"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
          {signal.why_go && (
            <section className="rounded-lg border-l-2 border-brand-500 bg-brand-50/70 p-3 text-sm text-navy">
              <span className="font-semibold text-brand-700">Why GO cares: </span>
              {signal.why_go}
            </section>
          )}

          {signal.recommended_action && (
            <section className="flex items-start gap-2 rounded-lg border border-accent-100 bg-accent-50/60 p-3 text-sm text-navy">
              <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-accent-600" />
              <span>
                <span className="font-semibold text-accent-700">Recommended action: </span>
                {signal.recommended_action}
              </span>
            </section>
          )}

          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
            <Meta
              label="Issue"
              value={
                signal.issue_label ? (
                  <span className="inline-flex items-center gap-1.5">
                    <IssueIcon className={`h-3.5 w-3.5 ${issueColor(signal.issue_label)}`} />
                    {signal.issue_label}
                  </span>
                ) : null
              }
            />
            <Meta label="Signal type" value={humanizeType(signal.signal_type)} />
            <Meta label="Place" value={place} />
            <Meta label="Event date" value={formatDate(date)} />
            <Meta label="Source type" value={signal.source_type} />
            <Meta
              label="Confidence"
              value={
                conf != null ? (
                  <span className="flex items-center gap-2">
                    {confidenceLabel(conf)} ({Math.round(conf * 100)}%)
                    <span className="h-1.5 w-16 overflow-hidden rounded-full bg-navy/10">
                      <span
                        className={`block h-full ${confidenceColor(conf)}`}
                        style={{ width: `${Math.round(conf * 100)}%` }}
                      />
                    </span>
                  </span>
                ) : null
              }
            />
          </dl>

          {Array.isArray(signal.affected_populations) && signal.affected_populations.length > 0 && (
            <section>
              <div className="mb-1.5 text-xs font-medium text-navy-400">Affected populations</div>
              <div className="flex flex-wrap gap-1.5">
                {signal.affected_populations.map((p) => (
                  <span
                    key={p}
                    className="rounded-md bg-navy/[0.04] px-2 py-0.5 text-xs text-navy-500 ring-1 ring-navy/10"
                  >
                    {p}
                  </span>
                ))}
              </div>
            </section>
          )}

          {signal.quote && (
            <section>
              <div className="mb-1.5 text-xs font-medium text-navy-400">Evidence</div>
              <blockquote className="flex gap-2 rounded-lg border border-black/5 bg-white p-3 text-sm italic text-navy-600">
                <Quote className="mt-0.5 h-4 w-4 shrink-0 text-navy-400" />
                <span>{signal.quote}</span>
              </blockquote>
            </section>
          )}

          {/* Action studio — grounded outreach drafts */}
          <OutreachStudio opportunityId={signal.signal_id} />
        </div>

        <div className="border-t border-black/5 bg-white px-5 py-3">
          {link ? (
            <a
              href={link}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-brand-600 hover:text-brand-700 hover:underline"
            >
              <ExternalLink className="h-4 w-4" />
              {signal.quote ? "Open exact passage" : "Open source"}
              {signal.source ? <span className="font-normal text-navy-400"> · {signal.source}</span> : null}
            </a>
          ) : (
            <span className="text-sm text-navy-400">{signal.source || "No source"}</span>
          )}
        </div>
      </aside>
    </div>
  );
}
