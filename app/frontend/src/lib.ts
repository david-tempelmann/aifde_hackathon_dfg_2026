import type { Direction } from "./types";

// Visual treatment per relevance direction.
export const DIRECTION_STYLE: Record<
  Direction,
  { label: string; badge: string; dot: string; accent: string }
> = {
  opportunity: {
    label: "Opportunity",
    badge: "bg-emerald-100 text-emerald-800 ring-emerald-200",
    dot: "bg-emerald-500",
    accent: "border-l-emerald-400",
  },
  risk: {
    label: "Risk",
    badge: "bg-rose-100 text-rose-800 ring-rose-200",
    dot: "bg-rose-500",
    accent: "border-l-rose-400",
  },
  watch: {
    label: "Watch",
    badge: "bg-slate-100 text-slate-700 ring-slate-200",
    dot: "bg-slate-400",
    accent: "border-l-slate-300",
  },
};

export function directionStyle(d: string | null) {
  return DIRECTION_STYLE[(d as Direction) ?? "watch"] ?? DIRECTION_STYLE.watch;
}

// Turn a signal_type slug ("bill_introduced") into a readable label.
export function humanizeType(t: string | null): string {
  if (!t) return "";
  return t.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatDate(d: string | null): string {
  if (!d) return "";
  const dt = new Date(d);
  if (isNaN(dt.getTime())) return d;
  return dt.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

// Build a citation deep-link using a URL Text Fragment so the browser scrolls
// to and highlights the exact quote on the source page (falls back to the
// plain URL if the fragment doesn't match).
export function citationLink(url: string | null, quote: string | null): string | null {
  if (!url || !/^https?:\/\//i.test(url)) return url;
  if (!quote) return url;
  const snippet = quote.trim().slice(0, 200);
  if (!snippet) return url;
  return `${url}#:~:text=${encodeURIComponent(snippet)}`;
}

export function confidenceLabel(c: number | null): string {
  if (c == null) return "—";
  if (c >= 0.75) return "High";
  if (c >= 0.5) return "Medium";
  return "Low";
}

export type PriorityBucket = "high" | "medium" | "low";

// Priority score (0..1) → coarse bucket. Thresholds are tunable.
export function priorityBucket(score: number | null | undefined): PriorityBucket {
  const v = score ?? 0;
  if (v >= 0.7) return "high";
  if (v >= 0.5) return "medium";
  return "low";
}

// Presentation for each priority bucket (a warm "heat" ramp).
export const PRIORITY_META: Record<
  PriorityBucket,
  { label: string; short: string; chipBg: string; text: string; dot: string }
> = {
  high: { label: "High priority", short: "High", chipBg: "bg-amber-100", text: "text-amber-800", dot: "bg-amber-500" },
  medium: { label: "Medium priority", short: "Medium", chipBg: "bg-gold-100", text: "text-amber-700", dot: "bg-gold-400" },
  low: { label: "Low priority", short: "Low", chipBg: "bg-slate-100", text: "text-slate-500", dot: "bg-slate-400" },
};

export type ConfidenceBucket = "high" | "medium" | "low";

// Coarse confidence band used by the bucket filter (thresholds match
// confidenceLabel). Null/unknown confidence falls into "low".
export function confidenceBucket(c: number | null | undefined): ConfidenceBucket {
  if (c != null && c >= 0.75) return "high";
  if (c != null && c >= 0.5) return "medium";
  return "low";
}

export function confidenceColor(c: number | null): string {
  if (c == null) return "bg-slate-300";
  if (c >= 0.75) return "bg-emerald-500";
  if (c >= 0.5) return "bg-amber-500";
  return "bg-rose-400";
}
