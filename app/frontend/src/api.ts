import type {
  DraftOption,
  DraftResponse,
  FilterOptions,
  Language,
  OverviewResponse,
  SignalQuery,
  SignalsResponse,
  TranslateResponse,
} from "./types";

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export function fetchSignals(query: SignalQuery): Promise<SignalsResponse> {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  });
  return getJSON<SignalsResponse>(`/api/signals?${params.toString()}`);
}

export function fetchFilters(): Promise<FilterOptions> {
  return getJSON<FilterOptions>("/api/filters");
}

export function fetchOverview(): Promise<OverviewResponse> {
  return getJSON<OverviewResponse>("/api/overview");
}

export function fetchStats(): Promise<{ total: number }> {
  return getJSON<{ total: number }>("/api/stats");
}

export function fetchDraftOptions(): Promise<{ variants: DraftOption[]; defaults: string[] }> {
  return getJSON<{ variants: DraftOption[]; defaults: string[] }>("/api/draft/options");
}

export async function draftOutreach(
  opportunityId: string,
  body: { partner_name?: string; variants?: string[] },
): Promise<DraftResponse> {
  const res = await fetch(`/api/signals/${encodeURIComponent(opportunityId)}/draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<DraftResponse>;
}

export function fetchLanguages(): Promise<{ languages: Language[] }> {
  return getJSON<{ languages: Language[] }>("/api/translate/languages");
}

export async function translateDraft(text: string, targetLang: string): Promise<TranslateResponse> {
  const res = await fetch("/api/translate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, target_lang: targetLang }),
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (j.detail) detail = j.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<TranslateResponse>;
}
