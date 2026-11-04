"""checks.py: the safety checks on Muse's answer, in plain words.

The idea: Muse can't claim something unless our code confirms it.
  1. Every "Dr. Name" in the answer must have come from a tool.
  2. Every quote in the answer must appear word for word in a real review or
     community post that a tool returned.
If a check fails, agent.py asks Muse to rewrite the answer once.
No AI is in this file, so Muse can't talk its way past the checks.
(The idea of checking claims in code comes from Meta's agent workshop.)
"""
import re

_FIXES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                        "–": "-", "—": "-", " ": " "})


def normalize(text):
    """Lowercase, straighten curly quotes, ignore punctuation and extra spaces."""
    t = (text or "").translate(_FIXES).lower()
    t = re.sub(r"[.,!?;:]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def extract_quotes(answer):
    """Quoted phrases of 3+ words (so plan names like "Aetna PPO" are not checked).
    Quote marks are paired in order: open, close, open, close."""
    found, start = [], None
    for i, ch in enumerate(answer or ""):
        if ch == "\u201c" or (ch == '"' and start is None):
            start = i + 1
        elif ch in ('"', "\u201d") and start is not None:
            found.append(answer[start:i])
            start = None
    return [q for q in found if 12 <= len(q) <= 240 and len(q.split()) >= 3]


def quote_in_sources(quote, sources):
    """True if the quote is in a real review. '...' inside a quote is allowed."""
    pieces = [normalize(p) for p in re.split(r"\.\.\.|…", quote)]
    pieces = [p for p in pieces if len(p) >= 8]
    if not pieces:
        return True
    texts = [normalize(s) for s in sources]
    return all(any(p in t for t in texts) for p in pieces)


def unknown_names(answer, seen_names):
    """Doctor names in the answer that no tool ever returned."""
    said = set(re.findall(r"Dr\.\s+[A-Z][\w'’-]+(?:\s+[A-Z][\w'’-]+)?", answer))
    return sorted(n for n in said if n not in seen_names)
