"""Core parse / serialize logic for SubRip (.srt) subtitles.

Design decisions (stated plainly so tests and users share one reality):

1. Timing is normalized internally to integer milliseconds. The canonical
   SubRip timestamp format is HH:MM:SS,mmm with exactly three fractional
   digits, so every well-formed timestamp maps losslessly to an int. We keep
   the milliseconds as a plain int -- not a datetime, not a float -- so
   comparisons are exact and there is never a float-equality trap.

2. Text blocks are preserved verbatim, including internal newlines, but
   trailing blank lines on a cue are trimmed. A subtitle cue ends at the
   first blank line (or at end-of-file); any additional blank lines between
   cues collapse to a single separator on round-trip. This is the common
   behaviour of real players and editors.

3. Parsing is tolerant of Windows and Unix line endings and of a BOM at the
   start of the file. It does NOT silently repair malformed timestamps -- a
   bad timestamp raises ValueError with the cue index, because guessing
   tends to produce silently-shifted subtitles, which is worse than failing.

4. The serial index of a cue (the number before the timestamp line) is only
   advisory on input; on output every cue is renumbered 1..N in order. This
   matches what every editor does on save and avoids carrying broken input
   numbering forward.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

_MS_PER_HOUR = 3_600_000
_MS_PER_MINUTE = 60_000
_MS_PER_SECOND = 1_000

# Canonical format: HH:MM:SS,mmm  (comma, not dot, is the SubRip convention).
_TS_RE = re.compile(
    r"^(\d{1,2}):(\d{1,2}):(\d{1,2})[,.](\d{1,3})$"
)


def from_milliseconds(ms: int) -> str:
    """Convert integer milliseconds into the canonical SRT timestamp string.

    Hours are emitted without leading-zero padding beyond two digits because
    real subtitles never exceed a few hours, but the format itself places no
    upper bound on the hour field. Minutes, seconds, and milliseconds are
    zero-padded to two, two, and three digits respectively.
    """
    if ms < 0:
        raise ValueError("milliseconds must be non-negative")
    h, rem = divmod(ms, _MS_PER_HOUR)
    m, rem = divmod(rem, _MS_PER_MINUTE)
    s, milli = divmod(rem, _MS_PER_SECOND)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def to_milliseconds(ts: str) -> int:
    """Parse a SubRip timestamp into integer milliseconds.

    Accepts either a comma or a dot as the sub-second separator because some
    real-world files use the wrong one. Requires exactly 1-3 fractional digits;
    values with more digits are rejected rather than truncated, so that a
    malformed timestamp is loud rather than silently wrong.
    """
    match = _TS_RE.match(ts.strip())
    if not match:
        raise ValueError(f"invalid timestamp: {ts!r}")
    h, m, s, frac = match.groups()
    # Pad the fractional part to exactly three digits so "5" means 500ms, not
    # 0.5ms or 50ms. This is the SubRip interpretation: it is always
    # milliseconds written as an integer, never a decimal fraction.
    frac_ms = int(frac.ljust(3, "0"))
    return (
        int(h) * _MS_PER_HOUR
        + int(m) * _MS_PER_MINUTE
        + int(s) * _MS_PER_SECOND
        + frac_ms
    )


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Subtitle:
    """A single subtitle cue.

    Attributes:
        start: start time in milliseconds (int >= 0).
        end:   end time in milliseconds (int >= 0).
        text:  the cue text, verbatim internal newlines included, with no
               trailing blank lines. May be empty.
        index: the 1-based serial from the source file, if known. Not used
               for serialization; SRTRenderer always renumbers.
    """
    start: int
    end: int
    text: str = ""
    index: Optional[int] = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < 0:
            raise ValueError("start and end must be non-negative milliseconds")
        if self.end < self.start:
            raise ValueError(
                f"end ({self.end}) must not precede start ({self.start})"
            )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class SRTParser:
    """Parse SubRip text into a list of Subtitle records.

    The parser is intentionally line-oriented rather than regex-driven on the
    whole file: a cue can contain arbitrary text including lines that look
    like timestamps, so splitting on blank-line boundaries first is the only
    robust way to delimit cues.
    """

    _ARROW_RE = re.compile(r"\s*-->\s*")

    def __init__(self, text: str) -> None:
        self._text = text

    def parse(self) -> List[Subtitle]:
        # Strip a leading BOM if present -- some Windows editors write one.
        text = self._text
        if text.startswith("\ufeff"):
            text = text[1:]
        # Normalize all line endings to \n so splitting is uniform.
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = text.split("\n")

        subtitles: List[Subtitle] = []
        i = 0
        n = len(lines)

        while i < n:
            line = lines[i]
            # Skip leading blank lines between cues.
            if line.strip() == "":
                i += 1
                continue

            block, consumed = self._read_cue(lines, i, n)
            if block is not None:
                subtitles.append(block)
            i += consumed

        return subtitles

    def _read_cue(
        self, lines: List[str], i: int, n: int
    ):
        """Read one cue starting at line index *i*.

        Returns (Subtitle, lines_consumed). If the block cannot be parsed as
        a cue, returns (None, 1) so the caller advances past the offending
        line rather than spinning forever.
        """
        start = i
        idx: Optional[int] = None

        # First line: optional numeric index. We accept it if present but do
        # not require it, because some files omit it.
        first = lines[i].strip()
        if first.isdigit():
            idx = int(first)
            i += 1
            if i >= n:
                return None, i - start

        # The timing line.
        timing_line = lines[i]
        timing = self._parse_timing(timing_line, idx)
        if timing is None:
            return None, 1
        start_ms, end_ms = timing
        i += 1

        # Everything until a blank line (or EOF) is the cue text.
        body: List[str] = []
        while i < n and lines[i].strip() != "":
            body.append(lines[i])
            i += 1

        # Trim trailing blank lines that were part of the separator.
        text = "\n".join(body).rstrip("\n")

        return (
            Subtitle(start=start_ms, end=end_ms, text=text, index=idx),
            i - start,
        )

    def _parse_timing(self, line: str, idx: Optional[int]):
        """Parse 'HH:MM:SS,mmm --> HH:MM:SS,mmm'. Returns (start, end) in ms."""
        if not self._ARROW_RE.search(line):
            return None
        parts = self._ARROW_RE.split(line.strip(), maxsplit=1)
        if len(parts) != 2:
            return None
        left, right = parts[0].strip(), parts[1].strip()
        try:
            start_ms = to_milliseconds(left)
            end_ms = to_milliseconds(right)
        except ValueError as exc:
            label = f"cue {idx}" if idx is not None else "a cue"
            raise ValueError(f"bad timing in {label}: {exc}") from exc
        return start_ms, end_ms


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class SRTRenderer:
    """Render a list of Subtitle records into canonical SRT text."""

    def render(self, subtitles: List[Subtitle]) -> str:
        chunks: List[str] = []
        for pos, sub in enumerate(subtitles, start=1):
            chunks.append(
                f"{pos}\n"
                f"{from_milliseconds(sub.start)} --> "
                f"{from_milliseconds(sub.end)}\n"
                f"{sub.text}"
            )
        return "\n\n".join(chunks)


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def parse_srt(text: str) -> List[Subtitle]:
    """Parse SRT text and return a list of Subtitle records."""
    return SRTParser(text).parse()


def render_srt(subtitles: List[Subtitle]) -> str:
    """Render a list of Subtitle records into SRT text."""
    return SRTRenderer().render(subtitles)
