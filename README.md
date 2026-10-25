# srt-subtitle-kit

Parses SubRip (.srt) subtitle files into structured `Subtitle` records (start, end, text) and serializes them back to canonical SRT text. Standard library only, no dependencies.

## Usage

```python
from srt_subtitle_kit import parse_srt, render_srt, Subtitle

subs = parse_srt("""1
00:00:01,000 --> 00:00:02,000
Hello world

2
00:00:03,000 --> 00:00:04,000
Goodbye
""")

for s in subs:
    print(s.start, s.end, repr(s.text))

# Build a cue programmatically and render it.
subs.append(Subtitle(start=5000, end=6000, text="Added later"))
print(render_srt(subs))
```

Exported names: `Subtitle`, `SRTParser`, `SRTRenderer`, `parse_srt`, `render_srt`, `from_milliseconds`, `to_milliseconds`.

## Why this exists

Every video toolchain eventually needs to read or adjust `.srt` files, and most reach for a heavy dependency when the format is small enough to handle with the standard library. This library exists to do that one job without pulling in anything external. The trade-off: it handles only the core SubRip format. It does not parse SSA/ASS, VTT, or embedded styling tags. If you need those, use a fuller library.

## Edge cases you will hit

- **Timestamps are normalized to integer milliseconds.** The SubRip format uses `HH:MM:SS,mmm` with three fractional digits, which maps losslessly to an int. We keep times as ints throughout so comparisons are exact. A dot (`.`) is accepted as the sub-second separator on input (some files get it wrong), but output always uses the canonical comma.
- **Cue numbering is renumbered on output.** The serial number before each timestamp in the source file is advisory; `render_srt` always emits `1..N` in order, matching what editors do on save.
- **Malformed timestamps raise `ValueError`** rather than being silently repaired. A guessed timestamp is usually silently wrong, which is worse than a loud failure.
- **Trailing blank lines within a cue are trimmed**, and multiple blank lines between cues collapse to a single separator on round-trip.
- **A leading BOM is stripped.** Windows and Unix line endings are both accepted.

## Running tests

```
PYTHONPATH=src python -m unittest discover -s tests
```

## Design notes

The window stores values eagerly rather than keeping running aggregates. Running
sums drift with floating point over long streams, and recomputing from a small
buffer is cheap enough that the drift is not worth the speed.

