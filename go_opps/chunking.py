"""Simple character-window chunking.

The corpus today is small — most items fit in a single extraction call — but we
expect larger scraped documents later, so extraction runs *per chunk* from the
start. A short document produces exactly one chunk, so the small case costs
nothing; a long one splits into overlapping windows so no window exceeds the
model's comfortable input size.

Deliberately simple: fixed-size character windows with overlap, preferring to
break on a nearby whitespace boundary so we don't slice mid-word. This is not a
semantic chunker — it is a robustness floor. Offsets are character positions
into the exact text passed in (the document's ``full_text``), so a citation can
be located later.
"""

from __future__ import annotations

from dataclasses import dataclass

# Defaults chosen so typical items stay single-chunk while genuinely long
# documents split. Overridable from the notebook.
DEFAULT_MAX_CHARS = 6000
DEFAULT_OVERLAP = 400
# When looking for a whitespace break near the window end, don't scan back
# further than this (avoids tiny chunks on text with no whitespace).
_BREAK_SEARCH_WINDOW = 200


@dataclass(frozen=True)
class Chunk:
    chunk_index: int
    char_start: int
    char_end: int  # exclusive
    text: str


def chunk_text(
    text: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    """Split ``text`` into overlapping character windows.

    Returns at least one chunk for any non-empty text (a short document → one
    chunk spanning the whole thing). Empty/whitespace-only text → no chunks.
    """
    if text is None:
        return []
    n = len(text)
    if n == 0 or not text.strip():
        return []
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    # Overlap must leave forward progress.
    overlap = max(0, min(overlap, max_chars - 1))

    chunks: list[Chunk] = []
    start = 0
    idx = 0
    while start < n:
        end = min(start + max_chars, n)
        # Prefer to end on a whitespace boundary near the target end (unless
        # this is the final chunk, which takes whatever remains).
        if end < n:
            break_at = _find_break(text, end)
            if break_at > start:
                end = break_at
        chunks.append(Chunk(idx, start, end, text[start:end]))
        idx += 1
        if end >= n:
            break
        # Step forward, keeping ``overlap`` characters of context.
        start = max(end - overlap, start + 1)
    return chunks


def _find_break(text: str, target_end: int) -> int:
    """Return an end offset at whitespace at/just before ``target_end``.

    Scans back up to ``_BREAK_SEARCH_WINDOW`` chars; falls back to
    ``target_end`` if no whitespace is found in that window.
    """
    lo = max(0, target_end - _BREAK_SEARCH_WINDOW)
    for i in range(target_end, lo, -1):
        if text[i - 1].isspace():
            return i
    return target_end
