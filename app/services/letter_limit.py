"""Length limits for cover letters ("max 300 words", "max 1500 characters").

Application forms often cap the text. The user enters the cap when generating; the prompt asks the model to
respect it, and fit_to_limit() guarantees it afterwards (models miscount), cutting the least important
sentences first and never the opening or the sign-off paragraph.
"""
import re
from typing import List

WORDS, CHARS = "words", "chars"
LIMITS = {WORDS: (50, 1500), CHARS: (200, 10000)}      # allowed range per unit


def count(text: str, unit: str) -> int:
    """Words, or characters including spaces and line breaks (how application forms usually count)."""
    return len(text.split()) if unit == WORDS else len(text)


def validate(unit: str, limit: int) -> None:
    if unit not in LIMITS:
        raise ValueError("limit_unit must be 'words' or 'chars'")
    lo, hi = LIMITS[unit]
    if not lo <= limit <= hi:
        raise ValueError(f"A {unit} limit must be between {lo} and {hi}")


def prompt_line(unit: str, limit: int) -> str:
    """Replacement for the default length instruction in the generation prompt."""
    if unit == WORDS:
        target = max(40, int(limit * 0.92))
        shape = "1-2 short paragraphs" if limit < 160 else "3 paragraphs" if limit < 280 else "3-4 paragraphs"
        return f"Length: HARD LIMIT of {limit} words in total (aim for about {target}); {shape}. Never exceed it."
    target = int(limit * 0.92)
    shape = "1-2 short paragraphs" if limit < 900 else "3 paragraphs" if limit < 1800 else "3-4 paragraphs"
    return (f"Length: HARD LIMIT of {limit} characters including spaces and line breaks (aim for about {target}); "
            f"{shape}. Never exceed it.")


def _sentences(paragraph: str) -> List[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", paragraph.strip()) if s]


def fit_to_limit(body: str, unit: str, limit: int) -> str:
    """Return body shortened to at most `limit` words/characters. Unchanged when it already fits."""
    if count(body, unit) <= limit:
        return body
    paras = [p.strip() for p in body.replace("\r\n", "\n").split("\n\n") if p.strip()]

    def joined() -> str:
        return "\n\n".join(paras)

    # 1. Drop the last sentence of the longest middle paragraph (keep the opening and the close intact).
    while count(joined(), unit) > limit and len(paras) > 2:
        middle = range(1, len(paras) - 1)
        i = max(middle, key=lambda j: len(paras[j]))
        sents = _sentences(paras[i])
        if len(sents) > 1:
            paras[i] = " ".join(sents[:-1])
        else:
            del paras[i]                                  # a one-sentence middle paragraph goes whole
    # 2. Still too long (a 1 or 2 paragraph letter): trim sentences from the end of the longest paragraph,
    #    but keep the final paragraph's last line (the sign-off).
    while count(joined(), unit) > limit and any(len(_sentences(p)) > 1 for p in paras):
        i = max(range(len(paras)), key=lambda j: len(paras[j]) if len(_sentences(paras[j])) > 1 else -1)
        sents = _sentences(paras[i])
        paras[i] = " ".join(sents[:-1])
    text = joined()
    if count(text, unit) <= limit:
        return text
    # 3. Last resort: cut at a word boundary.
    if unit == WORDS:
        return " ".join(text.split()[:limit])
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;: ")
