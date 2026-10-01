"""Page change detection with noise suppression.

Two snapshots of the same page differ constantly for boring reasons: dates, counters, cookie banners,
rotating testimonials. We diff at line level, then drop line pairs whose only difference is numeric/date
tokens, and only report a change when enough substantive text moved.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

NUMERIC_RE = re.compile(r"\d[\d,./:%-]*")
MONTHS_RE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b|\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)
NOISE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^\s*(?:accept|reject|manage)\s+(?:all\s+)?cookies?\b",
        r"cookie (?:policy|settings|preferences)",
        r"^\s*©",
        r"all rights reserved",
        r"^\s*\d+\s*(?:min|minute)s?\s*read\s*$",
        r"^\s*(?:share|tweet|copy link)\s*$",
        r"^\s*(?:loading|skip to (?:main )?content)\b",
    )
]


@dataclass
class PageDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed_chars: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.added and not self.removed

    def as_dict(self) -> dict:
        return {"added": self.added, "removed": self.removed, "changed_chars": self.changed_chars}


def _skeleton(line: str) -> str:
    """Line with numbers and month/day words removed, used to detect 'only the date changed'."""
    s = NUMERIC_RE.sub("#", line)
    s = MONTHS_RE.sub("@", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _is_noise(line: str) -> bool:
    if len(line.strip()) < 4:
        return True
    return any(p.search(line) for p in NOISE_PATTERNS)


def _normalize_lines(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.split("\n"):
        line = re.sub(r"\s+", " ", raw).strip()
        if line and not _is_noise(line):
            out.append(line)
    return out


def diff_page_text(before: str, after: str, *, ignore_patterns: list[str] | None = None) -> PageDiff:
    extra = [re.compile(p, re.IGNORECASE) for p in (ignore_patterns or [])]
    a_lines = [line for line in _normalize_lines(before) if not any(p.search(line) for p in extra)]
    b_lines = [line for line in _normalize_lines(after) if not any(p.search(line) for p in extra)]

    matcher = difflib.SequenceMatcher(a=a_lines, b=b_lines, autojunk=False)
    added: list[str] = []
    removed: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        old = a_lines[i1:i2]
        new = b_lines[j1:j2]
        if tag == "replace":
            # Pair up lines; drop pairs that differ only by numbers/dates.
            old_sk = {_skeleton(line) for line in old}
            new_sk = {_skeleton(line) for line in new}
            removed.extend(line for line in old if _skeleton(line) not in new_sk)
            added.extend(line for line in new if _skeleton(line) not in old_sk)
        elif tag == "delete":
            removed.extend(old)
        elif tag == "insert":
            added.extend(new)

    # Lines that merely moved are not a change.
    moved = set(added) & set(removed)
    added = [line for line in added if line not in moved]
    removed = [line for line in removed if line not in moved]
    changed = sum(len(line) for line in added) + sum(len(line) for line in removed)
    return PageDiff(added=added[:80], removed=removed[:80], changed_chars=changed)


def render_diff_for_llm(diff: PageDiff, max_chars: int = 6000) -> str:
    parts: list[str] = []
    if diff.removed:
        parts.append("REMOVED / PREVIOUS WORDING:\n" + "\n".join(f"- {line}" for line in diff.removed))
    if diff.added:
        parts.append("ADDED / NEW WORDING:\n" + "\n".join(f"+ {line}" for line in diff.added))
    text = "\n\n".join(parts)
    return text[:max_chars]
