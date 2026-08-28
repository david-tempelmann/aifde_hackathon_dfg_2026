import {
  Handshake,
  CalendarClock,
  Banknote,
  Siren,
  MapPin,
  Link2,
  Sparkles,
  ExternalLink,
  ShieldCheck,
} from "lucide-react";
import type { Finding, DeepDivePayload } from "../types";

/** Render **bold** markdown spans inside otherwise-plain text. */
function boldMd(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={i} className="font-semibold text-navy">
        {part.slice(2, -2)}
      </strong>
    ) : (
      <span key={i}>{part}</span>
    ),
  );
}

function priorityColor(m: number | null): string {
  if (m == null) return "bg-slate-400";
  if (m >= 80) return "bg-accent-600";
  if (m >= 60) return "bg-accent-500";
  if (m >= 40) return "bg-gold-400 text-navy";
  return "bg-slate-400";
}

function byCategory(findings: Finding[], cat: string) {
  return findings.filter((f) => f.category === cat);
}

/** Deep-link to the source, highlighting the exact quote via a URL Text Fragment. */
function citationHref(f: Finding): string | null {
  if (!f.source_url) return null;
  if (!f.quote) return f.source_url;
  return `${f.source_url}#:~:text=${encodeURIComponent(f.quote.trim().slice(0, 120))}`;
}

function SourceChip({ f }: { f: Finding }) {
  if (!f.source) return null;
  const href = citationHref(f);
  const base = "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium";
  if (href) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className={`${base} bg-brand-50 text-brand-600 hover:bg-brand-100 hover:underline`}
        title={f.quote ?? f.source}
      >
        {f.source} <ExternalLink className="h-3 w-3" />
      </a>
    );
  }
  return <span className={`${base} bg-navy/5 text-navy-500`}>{f.source}</span>;
}

function ScoredRow({ f }: { f: Finding }) {
  return (
    <li className="flex items-start gap-3 border-t border-black/5 py-2.5 first:border-t-0 first:pt-0">
      <span
        className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg text-sm font-bold text-white ${priorityColor(
          f.metric,
        )}`}
      >
        {f.metric ?? "—"}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[13.5px] font-medium leading-snug text-navy">{f.subject}</div>
        {f.quote && (
          <div className="mt-1 border-l-2 border-brand-200 pl-2 text-[12px] italic text-navy-500">
            &ldquo;{f.quote}&rdquo;
          </div>
        )}
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11.5px] text-navy-400">
          {f.detail && <span>{f.detail}</span>}
          {f.event_date && <span>· {f.event_date}</span>}
          {f.source && <span>·</span>}
          <SourceChip f={f} />
        </div>
      </div>
    </li>
  );
}

// Each finding type gets its own hue — a tinted card, matching border, a solid
// icon chip, and a colored heading — so the bubbles read as distinct at a glance.
const THEME = {
  brand: { card: "border-brand-200 bg-brand-50/50 shadow-brand-500/20", chip: "bg-brand-500 text-white", head: "text-brand-700" },
  accent: { card: "border-accent-500/30 bg-accent-50/60 shadow-accent-500/20", chip: "bg-accent-500 text-white", head: "text-accent-700" },
  emerald: { card: "border-emerald-200 bg-emerald-50/50 shadow-emerald-500/20", chip: "bg-emerald-500 text-white", head: "text-emerald-700" },
  rose: { card: "border-rose-200 bg-rose-50/50 shadow-rose-500/20", chip: "bg-rose-500 text-white", head: "text-rose-700" },
  indigo: { card: "border-indigo-200 bg-indigo-50/50 shadow-indigo-500/20", chip: "bg-indigo-500 text-white", head: "text-indigo-700" },
  gold: { card: "border-gold-400/50 bg-gold-100/50 shadow-gold-400/30", chip: "bg-gold-400 text-navy", head: "text-[#8a6d00]" },
};

/** A titled bubble — one per finding type, with a meaning-coded color. */
function Bubble({
  icon,
  title,
  count,
  sub,
  tone = "brand",
  className = "",
  delay = 0,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  count?: number;
  sub?: string;
  tone?: keyof typeof THEME;
  className?: string;
  delay?: number;
  children: React.ReactNode;
}) {
  const t = THEME[tone];
  return (
    <section
      className={`animate-slide-up rounded-2xl border p-5 shadow-md transition-shadow hover:shadow-lg motion-reduce:animate-none ${t.card} ${className}`}
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="mb-3 flex items-center gap-2.5">
        <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl shadow-sm ${t.chip}`}>
          {icon}
        </span>
        <h3 className={`text-[15px] font-bold ${t.head}`}>{title}</h3>
        {count != null && (
          <span className={`rounded-full bg-white/70 px-1.5 text-xs font-bold ${t.head}`}>{count}</span>
        )}
        {sub && <span className="ml-auto hidden text-xs text-navy-400 sm:block">{sub}</span>}
      </div>
      {children}
    </section>
  );
}

export default function FindingsPanel({ data }: { data: DeepDivePayload }) {
  const responders = byCategory(data.findings, "named_responder");
  const events = byCategory(data.findings, "upcoming_event").sort(
    (a, b) => (b.metric ?? 0) - (a.metric ?? 0),
  );
  const funding = byCategory(data.findings, "funding_hook");
  const crises = byCategory(data.findings, "crisis_signal");
  const places = byCategory(data.findings, "hot_place");
  const related = byCategory(data.findings, "related_issue");
  const maxPlace = Math.max(1, ...places.map((p) => Number(p.metric) || 0));

  return (
    <div className="space-y-4">
      {/* Hero — headline + the one best next step */}
      <section className="animate-slide-up overflow-hidden rounded-2xl border border-accent-100 bg-gradient-to-br from-accent-50 via-white to-brand-50 p-6 shadow-sm motion-reduce:animate-none">
        <div className="flex items-start justify-between gap-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-navy-400">
            {data.topic} · {data.region === "All" ? "National" : data.region} · {data.row_count} findings
          </div>
          <span className="shrink-0 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-bold text-emerald-600">
            ✓ {data.genie_status}
          </span>
        </div>
        <h2 className="mt-1 text-[20px] font-bold leading-tight text-navy">{data.headline}</h2>
        <div className="mt-4 flex items-start gap-2.5 rounded-xl bg-white/70 px-3.5 py-2.5 ring-1 ring-accent-100">
          <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-accent-600" />
          <p className="text-[13.5px] text-navy">
            <span className="font-semibold text-accent-700">Best next step: </span>
            {data.recommended_play}
          </p>
        </div>
      </section>

      {/* Narrative bubble */}
      {data.narrative && (
        <section
          className="animate-slide-up rounded-2xl border border-black/5 bg-white p-5 text-[14px] leading-relaxed text-navy-600 shadow-sm motion-reduce:animate-none"
          style={{ animationDelay: "80ms" }}
        >
          {boldMd(data.narrative)}
        </section>
      )}

      {/* Recruit now — full width, the headline action (who to call) */}
      {responders.length > 0 && (
        <Bubble
          icon={<Handshake className="h-4 w-4" />}
          title="Recruit now — named responders"
          count={responders.length}
          sub="nonprofits & churches already connected"
          tone="brand"
          delay={160}
        >
          <div className="flex flex-wrap gap-2">
            {[...responders]
              .sort((a, b) => Number(b.detail === "nonprofit") - Number(a.detail === "nonprofit"))
              .map((r, i) => {
                const np = r.detail === "nonprofit";
                return (
                  <span
                    key={i}
                    className={`inline-flex items-center gap-2 rounded-xl border bg-white px-2.5 py-1.5 text-sm ${
                      np ? "border-brand-200" : "border-black/10"
                    }`}
                  >
                    <span className="font-semibold text-navy">{r.subject}</span>
                    <span
                      className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                        np ? "bg-brand-500 text-white" : "bg-slate-200 text-slate-600"
                      }`}
                    >
                      {r.detail}
                    </span>
                  </span>
                );
              })}
          </div>
        </Bubble>
      )}

      {/* The rest of the findings stacked full-width, one after another with spacing */}
      <div className="space-y-4">
        {places.length > 0 && (
          <Bubble
            icon={<MapPin className="h-4 w-4" />}
            title="Where the need clusters"
            count={places.length}
            sub="signal count"
            tone="indigo"
            delay={240}
          >
            <div className="space-y-1.5">
              {places.map((p, i) => (
                <div key={i} className="flex items-center gap-3 text-[13px]">
                  <span className="w-36 shrink-0 truncate text-navy">
                    {p.subject} <span className="text-navy-400">{p.detail}</span>
                  </span>
                  <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-black/5">
                    <span
                      className="block h-full rounded-full bg-accent-500"
                      style={{ width: `${(100 * (Number(p.metric) || 0)) / maxPlace}%` }}
                    />
                  </span>
                  <span className="w-6 text-right text-xs text-navy-500">{p.metric}</span>
                </div>
              ))}
            </div>
          </Bubble>
        )}

        {events.length > 0 && (
          <Bubble
            icon={<CalendarClock className="h-4 w-4" />}
            title="Best entry points"
            count={events.length}
            sub="ranked by priority"
            tone="accent"
            delay={300}
          >
            <ul>
              {events.map((f, i) => (
                <li key={i} className="relative">
                  {i === 0 && (
                    <span className="absolute right-0 top-0 rounded-full bg-accent-100 px-2 py-0.5 text-[10px] font-bold text-accent-700">
                      best
                    </span>
                  )}
                  <ScoredRow f={f} />
                </li>
              ))}
            </ul>
          </Bubble>
        )}

        {funding.length > 0 && (
          <Bubble
            icon={<Banknote className="h-4 w-4" />}
            title="Funding already in play"
            count={funding.length}
            sub="who received it"
            tone="emerald"
            delay={360}
          >
            <ul>{funding.map((f, i) => <ScoredRow key={i} f={f} />)}</ul>
          </Bubble>
        )}

        {crises.length > 0 && (
          <Bubble
            icon={<Siren className="h-4 w-4" />}
            title="Families in acute crisis now"
            count={crises.length}
            tone="rose"
            delay={420}
          >
            <ul>{crises.map((f, i) => <ScoredRow key={i} f={f} />)}</ul>
          </Bubble>
        )}

        {related.length > 0 && (
          <Bubble
            icon={<Link2 className="h-4 w-4" />}
            title="Related needs co-occurring"
            count={related.length}
            tone="gold"
            delay={480}
          >
            <div className="flex flex-wrap gap-2">
              {related.map((r, i) => (
                <span key={i} className="rounded-full bg-black/5 px-3 py-1 text-[13px] text-navy">
                  {r.subject} <span className="font-bold text-accent-600">×{r.metric}</span>
                </span>
              ))}
            </div>
          </Bubble>
        )}
      </div>

      {/* Watch-outs */}
      <section
        className="animate-slide-up flex items-start gap-2 rounded-2xl border border-gold-400/30 bg-gold-100/40 px-5 py-3 text-[12px] text-navy-500 motion-reduce:animate-none"
        style={{ animationDelay: "540ms" }}
      >
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-[#8a6d00]" />
        <span>
          <span className="font-semibold text-navy">Verify before outreach:</span> {data.watch_outs}
        </span>
      </section>
    </div>
  );
}
