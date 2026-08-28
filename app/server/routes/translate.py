"""Translation endpoint — ai_translate (warehouse) + an LLM quality/culture score."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config, llm, warehouse

router = APIRouter()

# Curated languages relevant to NY / CA / VA communities. `code` is the
# ai_translate target-language code; `label` is shown in the UI.
LANGUAGES = [
    {"code": "es", "label": "Spanish"},
    {"code": "zh", "label": "Chinese"},
    {"code": "vi", "label": "Vietnamese"},
    {"code": "ko", "label": "Korean"},
    {"code": "ar", "label": "Arabic"},
    {"code": "ru", "label": "Russian"},
    {"code": "fr", "label": "French"},
    {"code": "pt", "label": "Portuguese"},
]


class TranslateRequest(BaseModel):
    text: str
    target_lang: str


@router.get("/translate/languages")
def translate_languages():
    return {"languages": LANGUAGES}


@router.post("/translate")
def translate(body: TranslateRequest):
    """Translate outreach text and score the translation for the target community."""
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Nothing to translate")
    try:
        translated = warehouse.ai_translate(text, body.target_lang)
    except Exception as exc:  # surface warehouse/ai_translate errors to the UI
        raise HTTPException(status_code=502, detail=f"Translation failed: {exc}")

    score = llm.score_translation(text, translated, body.target_lang)
    return {
        "target_lang": body.target_lang,
        "translated": translated,
        "score": score["score"],
        "assessment": score["assessment"],
        "model": config.SERVING_ENDPOINT,
    }
