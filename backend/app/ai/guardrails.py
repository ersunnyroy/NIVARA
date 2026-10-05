"""Guardrails for AI text: the AI explains structured data, it must not manufacture it.

* Every number in AI output must match (within rounding tolerance) a number present in the input data;
  otherwise it is flagged as unverified.
* Certainty / guarantee language is flagged and neutralised.
"""
from __future__ import annotations

import re

NUM = re.compile(r"(?<![A-Za-z])[-+]?(?:₹\s*)?\d[\d,]*(?:\.\d+)?")
BANNED = [
    (re.compile(r"\bguarantee[sd]?\b", re.I), "may"),
    (re.compile(r"\b(risk[- ]free|sure[- ]shot|can(?:no|')t lose|certain(?:ly)? (?:to|will))\b", re.I), "may"),
    (re.compile(r"\b(will definitely|definitely will|100% (?:sure|certain))\b", re.I), "could"),
]
IGNORE_SMALL = {0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 12.0, 20.0, 50.0, 100.0, 200.0}  # periods / generic counts


def _to_float(s: str) -> float | None:
    try:
        return float(s.replace("₹", "").replace(",", "").strip())
    except ValueError:
        return None


def numbers_in(obj) -> set[float]:
    out: set[float] = set()
    if isinstance(obj, dict):
        for v in obj.values():
            out |= numbers_in(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out |= numbers_in(v)
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, str):
        for m in NUM.findall(obj):
            f = _to_float(m)
            if f is not None:
                out.add(f)
    return out


def _matches(x: float, allowed: set[float]) -> bool:
    if abs(x) in IGNORE_SMALL:
        return True
    for a in allowed:
        if a == 0:
            continue
        for cand in (a, a / 1e7, a / 1e5, a * 100, a / 100):  # ₹ crore / lakh, fraction ↔ percent
            if abs(cand - x) <= max(0.011 * abs(cand), 0.051):
                return True
    return False


def check_text(text: str, allowed: set[float]) -> tuple[str, list[str]]:
    flags: list[str] = []
    for pat, repl in BANNED:
        if pat.search(text):
            flags.append(f"certainty language removed: {pat.search(text).group(0)!r}")
            text = pat.sub(repl, text)
    for m in NUM.findall(text):
        f = _to_float(m)
        if f is not None and not _matches(abs(f), {abs(a) for a in allowed}):
            flags.append(f"unverified number in AI text: {m.strip()}")
    return text, flags


def check_obj(obj, allowed: set[float]):
    """Apply check_text to every string in a nested structure."""
    flags: list[str] = []

    def walk(o):
        if isinstance(o, str):
            t, f = check_text(o, allowed)
            flags.extend(f)
            return t
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        if isinstance(o, list):
            return [walk(v) for v in o]
        return o

    return walk(obj), flags
