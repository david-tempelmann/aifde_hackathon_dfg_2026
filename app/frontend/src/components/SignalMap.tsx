import { useEffect, useMemo } from "react";
import { GeoJSON, MapContainer, Marker, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { Signal } from "../types";
import {
  buildStateColors,
  centroidOf,
  resolveCoords,
  spread,
  stateCentroid,
  STATE_CODE_TO_NAME,
  STATE_NAME_TO_CODE,
  type LatLng,
} from "../geo";
import usStates from "../data/usStates.json";

const US_STATES = usStates as unknown as GeoJSON.FeatureCollection;

// Mainland only — drop Alaska / Hawaii / Puerto Rico so the overview frames the
// lower 48 instead of spanning the whole hemisphere.
const MAINLAND_STATES: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: US_STATES.features.filter((f) => {
    const n = (f.properties as { name?: string })?.name;
    return n !== "Alaska" && n !== "Hawaii" && n !== "Puerto Rico";
  }),
};

// Zoom used when flying to a single selected signal.
const FOCUS_ZOOM = 7;

// Continental-US bounds. `US_START` is the overview starting view — ~25% more
// zoomed than fitting the whole lower-48 (edges crop slightly).
const US_BOUNDS = L.latLngBounds([24.5, -125], [49.4, -66.9]);
const US_START = US_BOUNDS.pad(-0.1);

const DIR_COLOR: Record<string, string> = {
  opportunity: "#10b981",
  risk: "#f43f5e",
  watch: "#94a3b8",
};

function pinIcon(direction: string | null, selected: boolean): L.DivIcon {
  const color = DIR_COLOR[direction ?? "watch"] ?? DIR_COLOR.watch;
  const size = selected ? 22 : 15;
  const ring = selected ? "box-shadow:0 0 0 4px rgba(7,115,167,0.35);" : "";
  return L.divIcon({
    className: "",
    html: `<span style="display:block;width:${size}px;height:${size}px;border-radius:9999px;background:${color};border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,0.35);${ring}"></span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function clusterIcon(count: number, color: string): L.DivIcon {
  const size = 40;
  return L.divIcon({
    className: "",
    html: `<span style="display:flex;align-items:center;justify-content:center;width:${size}px;height:${size}px;border-radius:9999px;background:${color};color:#fff;font-weight:700;font-size:15px;border:3px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,0.35);cursor:pointer;">${count}</span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

// Rich hover-tooltip: a state-level summary (counts, direction split, top issue).
function stateSummaryHtml(name: string, signals: Signal[], selected: boolean): string {
  const n = signals.length;
  const opp = signals.filter((s) => s.relevance_direction === "opportunity").length;
  const risk = signals.filter((s) => s.relevance_direction === "risk").length;
  const watch = signals.filter((s) => s.relevance_direction === "watch").length;
  const issueCounts = new Map<string, number>();
  for (const s of signals) {
    if (s.issue_label) issueCounts.set(s.issue_label, (issueCounts.get(s.issue_label) ?? 0) + 1);
  }
  const topIssue = [...issueCounts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
  const hint = selected ? "Click to go back to all states" : "Click to focus this state →";
  return `
    <div style="min-width:172px">
      <div style="font-weight:700;color:#172936;font-size:13px">${name}</div>
      <div style="color:#3a5566;font-size:12px;margin:1px 0 5px">${n} signal${n === 1 ? "" : "s"}</div>
      <div style="display:flex;gap:9px;font-size:11px;color:#3a5566">
        <span><span style="color:#10b981">●</span> ${opp} opportunity</span>
        <span><span style="color:#f43f5e">●</span> ${risk} risk</span>
      </div>
      <div style="font-size:11px;color:#3a5566;margin-top:2px"><span style="color:#94a3b8">●</span> ${watch} watch</div>
      ${topIssue ? `<div style="margin-top:5px;font-size:11px;color:#5b7385">Top issue: <b>${topIssue}</b></div>` : ""}
      <div style="margin-top:6px;font-size:11px;font-weight:600;color:#0773a7">${hint}</div>
    </div>`;
}

interface Group {
  signals: Signal[];
  coords: LatLng[];
}

/** Place a state's signals as individual, spread-out points. */
function placeSignals(signals: Signal[]): { signal: Signal; pos: LatLng }[] {
  const byCoord = new Map<string, number>();
  const bases: { signal: Signal; base: LatLng }[] = [];
  for (const s of signals) {
    const base = resolveCoords(s);
    if (!base) continue;
    bases.push({ signal: s, base });
  }
  const totals = new Map<string, number>();
  for (const { base } of bases) {
    const k = base.join(",");
    totals.set(k, (totals.get(k) ?? 0) + 1);
  }
  return bases.map(({ signal, base }) => {
    const k = base.join(",");
    const idx = byCoord.get(k) ?? 0;
    byCoord.set(k, idx + 1);
    return { signal, pos: spread(base, idx, totals.get(k)!) };
  });
}

function MapLayers({
  signals,
  selectedId,
  onSelect,
  selectedStates,
  onToggleState,
}: {
  signals: Signal[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  selectedStates: string[];
  onToggleState: (code: string) => void;
}) {
  const map = useMap();
  const selectedSet = useMemo(() => new Set(selectedStates), [selectedStates]);
  const selKey = useMemo(() => [...selectedStates].sort().join(","), [selectedStates]);

  // Group signals by state.
  const groups = useMemo(() => {
    const m = new Map<string, Group>();
    for (const s of signals) {
      if (!s.state) continue;
      const g = m.get(s.state) ?? { signals: [], coords: [] };
      g.signals.push(s);
      const c = resolveCoords(s);
      if (c) g.coords.push(c);
      m.set(s.state, g);
    }
    return m;
  }, [signals]);

  const activeStates = useMemo(() => new Set(groups.keys()), [groups]);
  const activeKey = useMemo(() => [...activeStates].sort().join(","), [activeStates]);
  const stateColors = useMemo(() => buildStateColors([...activeStates]), [activeKey]);

  // Full view (nothing selected) is locked to the whole US. When a state is
  // selected, fit to that state's signal points — with a guard for the case
  // where points are coincident (all fell back to one centroid), which would
  // otherwise zoom to max on an empty spot.
  useEffect(() => {
    const fit = () => {
      map.invalidateSize();
      if (selectedSet.size === 0) {
        map.fitBounds(US_START, { padding: [2, 2] });
        return;
      }
      const pts: LatLng[] = [];
      for (const [code, g] of groups) if (selectedSet.has(code)) pts.push(...g.coords);
      if (pts.length === 0) {
        map.fitBounds(US_START, { padding: [2, 2] });
        return;
      }
      const lats = pts.map((p) => p[0]);
      const lons = pts.map((p) => p[1]);
      const spanLat = Math.max(...lats) - Math.min(...lats);
      const spanLon = Math.max(...lons) - Math.min(...lons);
      const center: LatLng = [(Math.max(...lats) + Math.min(...lats)) / 2, (Math.max(...lons) + Math.min(...lons)) / 2];
      if (spanLat < 0.3 && spanLon < 0.3) {
        map.setView(center, 6);
      } else {
        map.fitBounds(L.latLngBounds(pts), { padding: [36, 36], maxZoom: 6 });
      }
    };
    // Defer so the map container has its final size before fitting (avoids the
    // layout race that leaves the map zoomed all the way out).
    const t = setTimeout(fit, 80);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeKey, selKey]);

  // Pan to a selected signal (only meaningful when its state is expanded).
  useEffect(() => {
    if (!selectedId) return;
    for (const [code, g] of groups) {
      if (!selectedSet.has(code)) continue;
      const hit = g.signals.find((s) => s.signal_id === selectedId);
      if (hit) {
        const c = resolveCoords(hit);
        if (c) map.flyTo(c, Math.max(map.getZoom(), FOCUS_ZOOM), { duration: 0.5 });
        break;
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const styleFeature = (feature?: GeoJSON.Feature): L.PathOptions => {
    const code = STATE_NAME_TO_CODE[(feature?.properties as { name?: string })?.name ?? ""];
    const color = code ? stateColors.get(code) : undefined;
    if (!color) return { color: "#cbd5e1", weight: 1, fillColor: "#eef1f4", fillOpacity: 1, opacity: 1 };
    if (code && selectedSet.has(code)) {
      return { color: "#111827", weight: 3, fillColor: color, fillOpacity: 0.34, opacity: 1 };
    }
    return { color, weight: 2, fillColor: color, fillOpacity: 0.28, opacity: 1 };
  };

  const onEachFeature = (feature: GeoJSON.Feature, layer: L.Layer) => {
    const code = STATE_NAME_TO_CODE[(feature.properties as { name?: string })?.name ?? ""];
    const g = code ? groups.get(code) : undefined;
    if (code && g) {
      layer.bindTooltip(stateSummaryHtml(STATE_CODE_TO_NAME[code] ?? code, g.signals, selectedSet.has(code)), {
        sticky: true,
        direction: "top",
        opacity: 1,
      });
      layer.on({ click: () => onToggleState(code) });
    }
  };

  return (
    <>
      <GeoJSON key={`${activeKey}|${selKey}`} data={MAINLAND_STATES} style={styleFeature} onEachFeature={onEachFeature} />
      {[...groups].flatMap(([code, g]) => {
        if (selectedSet.has(code)) {
          // State-level view: individual dots.
          return placeSignals(g.signals).map(({ signal, pos }) => (
            <Marker
              key={signal.signal_id}
              position={pos}
              icon={pinIcon(signal.relevance_direction, signal.signal_id === selectedId)}
              zIndexOffset={signal.signal_id === selectedId ? 1000 : 0}
              eventHandlers={{ click: () => onSelect(signal.signal_id) }}
            />
          ));
        }
        // Overview: one big numbered dot per state.
        const pos = centroidOf(g.coords) ?? stateCentroid(code);
        if (!pos) return [];
        return [
          <Marker
            key={`cluster-${code}`}
            position={pos}
            icon={clusterIcon(g.signals.length, stateColors.get(code) ?? "#0773a7")}
            eventHandlers={{ click: () => onToggleState(code) }}
          />,
        ];
      })}
    </>
  );
}

export default function SignalMap({
  signals,
  selectedId,
  onSelect,
  selectedStates,
  onToggleState,
}: {
  signals: Signal[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  selectedStates: string[];
  onToggleState: (code: string) => void;
}) {
  return (
    <MapContainer
      bounds={US_START}
      boundsOptions={{ padding: [2, 2] }}
      maxBounds={US_BOUNDS.pad(0.35)}
      maxBoundsViscosity={0.9}
      minZoom={3}
      scrollWheelZoom={false}
      doubleClickZoom={false}
      zoomControl={false}
      dragging
      className="h-full w-full"
      style={{ background: "#ffffff" }}
    >
      <MapLayers
        signals={signals}
        selectedId={selectedId}
        onSelect={onSelect}
        selectedStates={selectedStates}
        onToggleState={onToggleState}
      />
    </MapContainer>
  );
}
