import type { HotSignal } from "../types";

// Node hues by entity type; signal node hue by relevance direction.
const TYPE_COLOR: Record<string, string> = {
  issue: "#0773a7", // brand blue
  place: "#10b981", // emerald
  organization: "#7c3aed", // violet
  policy: "#d97706", // amber
};
const DIR_COLOR: Record<string, string> = {
  opportunity: "#10b981",
  risk: "#f43f5e",
  watch: "#94a3b8",
};
const PRED: Record<string, string> = {
  CONCERNS: "concerns",
  AFFECTS: "affects",
  INVOLVES: "involves",
  REFERENCES: "references",
};

/** A tiny explained sub-graph: the signal and what it concerns/affects/involves/
 *  references. Labels are real HTML (foreignObject) so they ellipsis cleanly and
 *  never clip; capped to ~5 nodes so it stays legible, never a hairball. */
export default function MiniGraph({ sig }: { sig: HotSignal }) {
  const edges = sig.edges ?? [];
  if (!edges.length) return null;

  const byPred: Record<string, HotSignal["edges"]> = {};
  for (const e of edges) (byPred[e.predicate] ??= []).push(e);
  for (const k in byPred) byPred[k].sort((a, b) => b.conf - a.conf);

  const picks: { pred: string; type: string; label: string }[] = [];
  const extra: string[] = [];
  const take = (pred: string, type: string, max: number) => {
    const items = byPred[pred] ?? [];
    items.slice(0, max).forEach((e) => picks.push({ pred: PRED[pred] ?? pred, type, label: e.dst_label }));
    if (items.length > max) {
      const more = items.length - max;
      extra.push(`+${more} more ${type}${more > 1 ? "s" : ""}`);
    }
  };
  take("CONCERNS", "issue", 1);
  take("AFFECTS", "place", 1);
  take("INVOLVES", "organization", 2);
  take("REFERENCES", "policy", 1);
  if (!picks.length) return null;

  const ROW = 40;
  const TOP = 12;
  const W = 540;
  const EW = 286; // entity node width
  const EX = 246; // entity node x  (EX + EW = 532 < W, so nothing clips)
  const SW = 132; // signal node width
  const SX = 6;
  const NH = 30; // entity node height
  const H = TOP * 2 + picks.length * ROW;
  const sy = H / 2;
  const mx = (SX + SW + EX) / 2;
  const dcol = DIR_COLOR[sig.dir ?? "watch"] ?? "#94a3b8";

  return (
    <div className="mt-2 overflow-hidden rounded-xl border border-black/5 bg-white p-2">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: W }}>
        {/* connectors + predicate labels */}
        {picks.map((p, i) => {
          const cy = TOP + i * ROW + ROW / 2;
          return (
            <g key={`c${i}`}>
              <path
                d={`M${SX + SW} ${sy} C${mx} ${sy}, ${mx} ${cy}, ${EX} ${cy}`}
                stroke="#e2e8f0"
                strokeWidth="1.5"
                fill="none"
              />
              <text x={mx} y={(sy + cy) / 2 - 4} fill="#94a3b8" fontSize="9.5" fontStyle="italic" textAnchor="middle">
                {p.pred}
              </text>
            </g>
          );
        })}

        {/* signal node */}
        <foreignObject x={SX} y={sy - 20} width={SW} height={40}>
          <div
            className="flex h-full flex-col items-center justify-center rounded-xl px-2 text-center leading-tight"
            style={{ background: dcol }}
          >
            <span className="text-[10px] font-bold text-white">SIGNAL</span>
            <span className="max-w-full truncate text-[9px] text-white/90">{sig.type}</span>
          </div>
        </foreignObject>

        {/* entity nodes */}
        {picks.map((p, i) => {
          const cy = TOP + i * ROW + ROW / 2;
          const col = TYPE_COLOR[p.type] ?? "#64748b";
          return (
            <foreignObject key={`e${i}`} x={EX} y={cy - NH / 2} width={EW} height={NH}>
              <div
                className="flex h-full items-center gap-2 rounded-lg border px-2.5"
                style={{ borderColor: col, background: `${col}14` }}
                title={p.label}
              >
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: col }} />
                <span className="truncate text-[11px] font-semibold text-navy">{p.label}</span>
              </div>
            </foreignObject>
          );
        })}
      </svg>
      {extra.length > 0 && <div className="mt-1 px-1 text-[10.5px] text-navy-400">{extra.join(" · ")}</div>}
      {sig.why_go && (
        <div className="mt-1.5 px-1 text-[12px] leading-snug text-navy-600">
          <span className="font-semibold text-navy">Why GO cares:</span> {sig.why_go}
        </div>
      )}
      {sig.url && (
        <a
          href={sig.url}
          target="_blank"
          rel="noreferrer"
          className="mt-1 inline-block px-1 text-[11px] font-semibold text-brand-600 hover:underline"
        >
          Open source ↗
        </a>
      )}
    </div>
  );
}
