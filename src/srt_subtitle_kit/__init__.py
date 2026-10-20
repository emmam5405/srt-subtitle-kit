# srt-subtitle-kit
"""srt-subtitle-kit: parse and serialize SubRip (.srt) files.

Exposes:
    Subtitle       -- one cue: index, start, end, text
    SRTParser      -- parse SRT text into a list[Subtitle]
    SRTRenderer    -- render a list[Subtitle] back to SRT text
    parse_srt      -- convenience function wrapping SRTParser
    render_srt     -- convenience function wrapping SRTRenderer
    from_milliseconds / to_milliseconds -- time helpers
"""

from .core import (
    Subtitle,
    SRTParser,
    SRTRenderer,
    parse_srt,
    render_srt,
    from_milliseconds,
    to_milliseconds,
)

__all__ = [
    "Subtitle",
    "SRTParser",
    "SRTRenderer",
    "parse_srt",
    "render_srt",
    "from_milliseconds",
    "to_milliseconds",
]

__version__ = "1.0.0"
