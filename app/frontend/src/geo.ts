import type { Signal } from "./types";

// Coordinate resolution for the map: signal lat/lng (once added to dim_places)
// → built-in Contract B place lookup → state centroid. Works today without a DB
// change and upgrades automatically to DB-driven coordinates later.

export type LatLng = [number, number];

// Canonical place name (dim_places.canonical_name) -> [lat, lng].
const PLACE_COORDS: Record<string, LatLng> = {
  "New York": [42.75, -75.5],
  "New York City": [40.7128, -74.006],
  Buffalo: [42.8864, -78.8784],
  California: [36.8, -119.4],
  "San Diego": [32.7157, -117.1611],
  "Los Angeles": [34.0522, -118.2437],
  Virginia: [37.8, -78.6],
  "Fairfax County": [38.8462, -77.3064],
  Richmond: [37.5407, -77.436],
};

// State code -> centroid, used when a place has no specific coordinates.
const STATE_COORDS: Record<string, LatLng> = {
  NY: [42.75, -75.5],
  CA: [36.8, -119.4],
  VA: [37.8, -78.6],
};

/** Centroid for a state code (or null if unknown). */
export function stateCentroid(code: string): LatLng | null {
  return STATE_COORDS[code] ?? null;
}

/** Mean of a set of coordinates (used to place a state's cluster marker). */
export function centroidOf(coords: LatLng[]): LatLng | null {
  if (coords.length === 0) return null;
  const lat = coords.reduce((a, c) => a + c[0], 0) / coords.length;
  const lng = coords.reduce((a, c) => a + c[1], 0) / coords.length;
  return [lat, lng];
}

// Full US state name -> 2-letter code, to match the GeoJSON `properties.name`
// against signal.state (which uses codes).
export const STATE_NAME_TO_CODE: Record<string, string> = {
  Alabama: "AL", Alaska: "AK", Arizona: "AZ", Arkansas: "AR", California: "CA",
  Colorado: "CO", Connecticut: "CT", Delaware: "DE", "District of Columbia": "DC",
  Florida: "FL", Georgia: "GA", Hawaii: "HI", Idaho: "ID", Illinois: "IL",
  Indiana: "IN", Iowa: "IA", Kansas: "KS", Kentucky: "KY", Louisiana: "LA",
  Maine: "ME", Maryland: "MD", Massachusetts: "MA", Michigan: "MI", Minnesota: "MN",
  Mississippi: "MS", Missouri: "MO", Montana: "MT", Nebraska: "NE", Nevada: "NV",
  "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
  "North Carolina": "NC", "North Dakota": "ND", Ohio: "OH", Oklahoma: "OK",
  Oregon: "OR", Pennsylvania: "PA", "Puerto Rico": "PR", "Rhode Island": "RI",
  "South Carolina": "SC", "South Dakota": "SD", Tennessee: "TN", Texas: "TX",
  Utah: "UT", Vermont: "VT", Virginia: "VA", Washington: "WA",
  "West Virginia": "WV", Wisconsin: "WI", Wyoming: "WY",
};

/** 2-letter code -> full state name. */
export const STATE_CODE_TO_NAME: Record<string, string> = Object.fromEntries(
  Object.entries(STATE_NAME_TO_CODE).map(([name, code]) => [code, name]),
);

// Per-state palette shared by the map (fill + cluster dot) and the list (group
// headers) so a state reads as the same colour everywhere.
export const STATE_PALETTE = [
  "#0773a7", // brand blue
  "#e8833a", // warm orange
  "#3fa66a", // green
  "#7c6bd6", // violet
  "#d9569b", // pink
  "#f2a900", // gold
  "#0e9aa7", // teal
  "#ef6f53", // coral
];

/** Assign each state code a stable palette colour (by sorted order). */
export function buildStateColors(codes: string[]): Map<string, string> {
  const m = new Map<string, string>();
  [...new Set(codes)]
    .sort()
    .forEach((code, i) => m.set(code, STATE_PALETTE[i % STATE_PALETTE.length]));
  return m;
}

/** Best-effort [lat, lng] for a signal, or null if we can't place it. */
export function resolveCoords(signal: Signal): LatLng | null {
  if (typeof signal.latitude === "number" && typeof signal.longitude === "number") {
    return [signal.latitude, signal.longitude];
  }
  if (signal.place_name && PLACE_COORDS[signal.place_name]) {
    return PLACE_COORDS[signal.place_name];
  }
  if (signal.state && STATE_COORDS[signal.state]) {
    return STATE_COORDS[signal.state];
  }
  return null;
}

// Small deterministic spread so multiple signals at the same coordinate don't
// stack into a single unclickable pin. Offsets ~0.04° on a ring by index.
export function spread(coords: LatLng, index: number, count: number): LatLng {
  if (count <= 1) return coords;
  const radius = 0.05;
  const angle = (2 * Math.PI * index) / count;
  return [coords[0] + radius * Math.sin(angle), coords[1] + radius * Math.cos(angle)];
}
