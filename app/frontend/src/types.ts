export type Direction = "opportunity" | "risk" | "watch";

export interface Signal {
  signal_id: string;
  state: string | null;
  relevance_direction: Direction | null;
  signal_type: string | null;
  event_date: string | null;
  published_date: string | null;
  summary: string | null;
  why_go: string | null;
  quote: string | null;
  confidence: number | null;
  url: string | null;
  source: string | null;
  source_type: string | null;
  affected_populations: string[] | null;
  issue_label: string | null;
  place_name: string | null;
  place_level: string | null;
  recommended_action: string | null;
  priority_score: number | null;
  // Optional geo — present once dim_places carries lat/long and the query
  // selects it; the map falls back to a built-in lookup when absent.
  latitude?: number | null;
  longitude?: number | null;
}

export interface SignalsResponse {
  count: number;
  signals: Signal[];
}

export interface FilterOption {
  value: string;
  count: number;
}

export type FilterOptions = Record<string, FilterOption[]>;

export interface Hotspot {
  issue: string;
  state: string;
  n: number;
  opportunities: number;
  risks: number;
  watch: number;
  latest: string | null;
}

export interface OverviewResponse {
  summary: {
    total?: number;
    opportunities?: number;
    risks?: number;
    watch?: number;
    states?: number;
    latest?: string | null;
  };
  hotspots: Hotspot[];
}

export interface DraftOption {
  key: string;
  label: string;
  channel: string;
}

export interface DraftVariant {
  key: string;
  label: string;
  channel: string;
  draft: string;
}

export interface DraftResponse {
  opportunity_id: string;
  model: string;
  drafts: DraftVariant[];
  citations: { quote: string | null; source_name: string | null; source_url: string | null }[];
}

export interface Language {
  code: string;
  label: string;
}

export interface TranslateResponse {
  target_lang: string;
  translated: string;
  score: number | null;
  assessment: string;
  model: string;
}

export type FindingCategory =
  | "hot_place"
  | "named_responder"
  | "related_issue"
  | "upcoming_event"
  | "funding_hook"
  | "crisis_signal";

export interface Finding {
  category: FindingCategory | string;
  subject: string;
  detail: string | null;
  metric: number | null;
  event_date: string | null;
  source: string | null;
  source_url: string | null;
  quote: string | null;
  finding: string;
  so_what: string;
}

export interface DeepDivePayload {
  topic: string;
  region: string;
  card_context: Record<string, string | null>;
  generated_at: string;
  genie_space_id: string;
  genie_status: string;
  row_count: number;
  headline: string;
  findings: Finding[];
  who_to_recruit: string[];
  recommended_play: string;
  watch_outs: string;
  narrative: string;
  cached?: boolean;
}

export interface DeepDiveOptions {
  topics: string[];
  regions: string[];
}

export interface DeepDiveQuery {
  topic: string;
  region?: string;
  signal_count?: string;
  signal_mix?: string;
  sources?: string;
  key_dates?: string;
  latest?: string;
  refresh?: boolean;
}

export interface SignalQuery {
  state?: string;
  direction?: string;
  issue?: string;
  signal_type?: string;
  min_confidence?: number;
  search?: string;
  sort?: string;
  limit?: number;
}
