import { useEffect, useState } from "react";
import { Check, Copy, Languages as LanguagesIcon, Loader2, Sparkles } from "lucide-react";
import { draftOutreach, fetchDraftOptions, fetchLanguages, translateDraft } from "../api";
import type { DraftOption, DraftVariant, Language, TranslateResponse } from "../types";

// Grounded outreach-draft generator for one opportunity. Lets the worker pick a
// partner name + audience/channel variants, generates drafts, and lets them
// edit and copy each. Every draft is AI-generated and flagged for review.
export default function OutreachStudio({ opportunityId }: { opportunityId: string }) {
  const [options, setOptions] = useState<DraftOption[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [partner, setPartner] = useState("");
  const [drafts, setDrafts] = useState<DraftVariant[]>([]);
  const [languages, setLanguages] = useState<Language[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchDraftOptions()
      .then((o) => {
        setOptions(o.variants);
        setSelected(o.defaults);
      })
      .catch(() => setOptions([]));
    fetchLanguages().then((l) => setLanguages(l.languages)).catch(() => setLanguages([]));
    // Reset when the opportunity changes.
    setDrafts([]);
    setError(null);
  }, [opportunityId]);

  const toggle = (key: string) =>
    setSelected((s) => (s.includes(key) ? s.filter((k) => k !== key) : [...s, key]));

  const generate = () => {
    setLoading(true);
    setError(null);
    draftOutreach(opportunityId, { partner_name: partner || undefined, variants: selected })
      .then((r) => setDrafts(r.drafts))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  return (
    <section className="rounded-xl border border-accent-200 bg-accent-50/40 p-4">
      <div className="mb-1 flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-accent-600" />
        <h3 className="text-sm font-bold text-navy">Draft outreach</h3>
      </div>
      <p className="mb-3 text-xs text-navy-400">
        AI-generated from this opportunity's cited evidence and approved GO facts — review and edit
        before sending.
      </p>

      {/* Partner name */}
      <label className="mb-3 block text-xs font-medium text-navy-400">
        Recipient (optional)
        <input
          value={partner}
          onChange={(e) => setPartner(e.target.value)}
          placeholder="e.g. Grace Community Church"
          className="mt-1 w-full rounded-lg border border-navy/15 bg-white px-2.5 py-2 text-sm font-normal text-navy shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
      </label>

      {/* Variant chips */}
      <div className="mb-3 flex flex-wrap gap-1.5">
        {options.map((o) => {
          const on = selected.includes(o.key);
          return (
            <button
              key={o.key}
              onClick={() => toggle(o.key)}
              className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition ${
                on
                  ? "border-accent-500 bg-accent-500 text-white"
                  : "border-navy/15 bg-white text-navy-500 hover:border-accent-300"
              }`}
            >
              {on && <Check className="h-3 w-3" />}
              {o.label}
            </button>
          );
        })}
      </div>

      <button
        onClick={generate}
        disabled={loading || selected.length === 0}
        className="inline-flex items-center gap-1.5 rounded-lg bg-accent-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-accent-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
        {loading ? "Drafting…" : drafts.length ? "Regenerate" : `Generate ${selected.length} draft${selected.length === 1 ? "" : "s"}`}
      </button>

      {error && <p className="mt-2 text-xs text-rose-700">Failed to draft: {error}</p>}

      {/* Drafts */}
      {drafts.length > 0 && (
        <div className="mt-4 space-y-3">
          {drafts.map((d) => (
            <DraftBlock key={d.key} draft={d} languages={languages} />
          ))}
        </div>
      )}
    </section>
  );
}

function scoreColor(score: number | null): string {
  if (score == null) return "bg-navy/10 text-navy-500";
  if (score >= 80) return "bg-emerald-100 text-emerald-800";
  if (score >= 60) return "bg-amber-100 text-amber-800";
  return "bg-rose-100 text-rose-800";
}

function CopyButton({ getText }: { getText: () => string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(getText());
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard may be blocked; ignore */
    }
  };
  return (
    <button
      onClick={copy}
      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-brand-600 hover:bg-brand-50"
    >
      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function DraftBlock({ draft, languages }: { draft: DraftVariant; languages: Language[] }) {
  const [text, setText] = useState(draft.draft);
  const [lang, setLang] = useState("es");
  const [translating, setTranslating] = useState(false);
  const [translation, setTranslation] = useState<TranslateResponse | null>(null);
  const [tError, setTError] = useState<string | null>(null);

  // Keep local edits, but reset when a new generation arrives.
  useEffect(() => {
    setText(draft.draft);
    setTranslation(null);
    setTError(null);
  }, [draft.draft]);

  const translate = () => {
    setTranslating(true);
    setTError(null);
    translateDraft(text, lang)
      .then(setTranslation)
      .catch((e) => setTError(String(e.message ?? e)))
      .finally(() => setTranslating(false));
  };

  const langLabel = languages.find((l) => l.code === translation?.target_lang)?.label ?? translation?.target_lang;

  return (
    <div className="rounded-lg border border-black/10 bg-white p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs">
          <span className="font-semibold text-navy">{draft.label}</span>
          <span className="rounded-full bg-navy/5 px-2 py-0.5 text-navy-500">{draft.channel}</span>
        </div>
        <CopyButton getText={() => text} />
      </div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={Math.min(12, Math.max(4, text.split("\n").length + 1))}
        className="w-full resize-y rounded-md border border-navy/10 bg-canvas p-2.5 text-sm text-navy focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
      />

      {/* Translate control */}
      <div className="mt-2 flex items-center gap-2">
        <LanguagesIcon className="h-3.5 w-3.5 text-navy-400" />
        <span className="text-xs font-medium text-navy-500">English</span>
        <span className="text-navy-400">→</span>
        <select
          value={lang}
          onChange={(e) => setLang(e.target.value)}
          aria-label="Translate to language"
          className="rounded-md border border-navy/15 bg-white px-2 py-1 text-xs text-navy focus:border-brand-500 focus:outline-none"
        >
          {languages.map((l) => (
            <option key={l.code} value={l.code}>
              {l.label}
            </option>
          ))}
        </select>
        <button
          onClick={translate}
          disabled={translating}
          className="inline-flex items-center gap-1 rounded-md border border-navy/15 px-2 py-1 text-xs font-medium text-navy-500 hover:bg-brand-50 hover:text-navy disabled:opacity-50"
        >
          {translating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <LanguagesIcon className="h-3.5 w-3.5" />}
          Translate
        </button>
      </div>

      {tError && <p className="mt-1 text-xs text-rose-700">{tError}</p>}

      {/* Translated result + quality score */}
      {translation && (
        <div className="mt-2 rounded-md border border-brand-100 bg-brand-50/40 p-2.5">
          <div className="mb-1.5 flex items-center justify-between gap-2 text-xs">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-navy">{langLabel}</span>
              <span
                className={`rounded-full px-2 py-0.5 font-semibold ${scoreColor(translation.score)}`}
                title="AI translation-quality & cultural-fit score"
              >
                {translation.score != null ? `Quality ${translation.score}` : "Scored"}
              </span>
            </div>
            <CopyButton getText={() => translation.translated} />
          </div>
          <textarea
            defaultValue={translation.translated}
            rows={Math.min(12, Math.max(3, translation.translated.split("\n").length + 1))}
            className="w-full resize-y rounded-md border border-navy/10 bg-white p-2.5 text-sm text-navy focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
          {translation.assessment && (
            <p className="mt-1.5 text-xs text-navy-500">
              <span className="font-medium text-navy">Reviewer note: </span>
              {translation.assessment}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
