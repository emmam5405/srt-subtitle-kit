"""Unit tests for srt-subtitle-kit core.

Run with:  PYTHONPATH=src python -m unittest discover -s tests
"""

import unittest

from srt_subtitle_kit import (
    Subtitle,
    SRTParser,
    SRTRenderer,
    parse_srt,
    render_srt,
    from_milliseconds,
    to_milliseconds,
)


class TestTimeHelpers(unittest.TestCase):

    def test_from_milliseconds_basic(self):
        self.assertEqual(from_milliseconds(0), "00:00:00,000")
        self.assertEqual(from_milliseconds(1), "00:00:00,001")
        self.assertEqual(from_milliseconds(999), "00:00:00,999")
        self.assertEqual(from_milliseconds(1000), "00:00:01,000")
        self.assertEqual(from_milliseconds(60000), "00:01:00,000")
        self.assertEqual(from_milliseconds(3600000), "01:00:00,000")
        self.assertEqual(
            from_milliseconds(3661500), "01:01:01,500"
        )

    def test_to_milliseconds_basic(self):
        self.assertEqual(to_milliseconds("00:00:00,000"), 0)
        self.assertEqual(to_milliseconds("00:00:00,001"), 1)
        self.assertEqual(to_milliseconds("00:00:00,999"), 999)
        self.assertEqual(to_milliseconds("00:00:01,000"), 1000)
        self.assertEqual(to_milliseconds("00:01:00,000"), 60000)
        self.assertEqual(to_milliseconds("01:00:00,000"), 3600000)
        self.assertEqual(to_milliseconds("01:01:01,500"), 3661500)

    def test_round_trip(self):
        for ms in [0, 1, 500, 999, 1000, 59999, 60000, 3600000, 3661500]:
            self.assertEqual(to_milliseconds(from_milliseconds(ms)), ms)

    def test_to_milliseconds_accepts_dot_separator(self):
        # Some real files use a dot instead of a comma; we accept it.
        self.assertEqual(to_milliseconds("00:00:01,500"), 1500)
        self.assertEqual(to_milliseconds("00:00:01.500"), 1500)

    def test_to_milliseconds_rejects_garbage(self):
        with self.assertRaises(ValueError):
            to_milliseconds("not a time")
        with self.assertRaises(ValueError):
            to_milliseconds("00:00:00")

    def test_from_milliseconds_rejects_negative(self):
        with self.assertRaises(ValueError):
            from_milliseconds(-1)


class TestSubtitleDataclass(unittest.TestCase):

    def test_construction(self):
        s = Subtitle(start=1000, end=2000, text="hello")
        self.assertEqual(s.start, 1000)
        self.assertEqual(s.end, 2000)
        self.assertEqual(s.text, "hello")
        self.assertIsNone(s.index)

    def test_frozen(self):
        s = Subtitle(0, 1, "x")
        with self.assertRaises(Exception):
            s.start = 5  # type: ignore[misc]

    def test_rejects_end_before_start(self):
        with self.assertRaises(ValueError):
            Subtitle(start=2000, end=1000)

    def test_rejects_negative_times(self):
        with self.assertRaises(ValueError):
            Subtitle(start=-1, end=0)
        with self.assertRaises(ValueError):
            Subtitle(start=0, end=-1)

    def test_zero_duration_allowed(self):
        # A cue whose end equals its start is degenerate but not ill-formed.
        s = Subtitle(start=1000, end=1000)
        self.assertEqual(s.start, s.end)


class TestParser(unittest.TestCase):

    def test_basic_two_cues(self):
        text = (
            "1\n"
            "00:00:01,000 --> 00:00:02,000\n"
            "Hello world\n\n"
            "2\n"
            "00:00:03,000 --> 00:00:04,000\n"
            "Goodbye\n"
        )
        subs = parse_srt(text)
        self.assertEqual(len(subs), 2)
        self.assertEqual(subs[0].start, 1000)
        self.assertEqual(subs[0].end, 2000)
        self.assertEqual(subs[0].text, "Hello world")
        self.assertEqual(subs[0].index, 1)
        self.assertEqual(subs[1].start, 3000)
        self.assertEqual(subs[1].text, "Goodbye")
        self.assertEqual(subs[1].index, 2)

    def test_no_trailing_newline(self):
        text = (
            "1\n"
            "00:00:01,000 --> 00:00:02,000\n"
            "Last cue, no newline at end"
        )
        subs = parse_srt(text)
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0].text, "Last cue, no newline at end")

    def test_windows_crlf_line_endings(self):
        text = (
            "1\r\n"
            "00:00:01,000 --> 00:00:02,000\r\n"
            "Windows line endings\r\n"
        )
        subs = parse_srt(text)
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0].text, "Windows line endings")

    def test_leading_bom(self):
        text = (
            "\ufeff1\n"
            "00:00:01,000 --> 00:00:02,000\n"
            "BOM stripped\n"
        )
        subs = parse_srt(text)
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0].text, "BOM stripped")
        self.assertEqual(subs[0].index, 1)

    def test_multiline_text_preserved(self):
        text = (
            "1\n"
            "00:00:01,000 --> 00:00:02,000\n"
            "Line one\n"
            "Line two\n"
            "Line three\n"
        )
        subs = parse_srt(text)
        self.assertEqual(
            subs[0].text, "Line one\nLine two\nLine three"
        )

    def test_dot_separator_in_timestamp(self):
        text = (
            "1\n"
            "00:00:01.000 --> 00:00:02.000\n"
            "Dot separator\n"
        )
        subs = parse_srt(text)
        self.assertEqual(subs[0].start, 1000)
        self.assertEqual(subs[0].end, 2000)

    def test_empty_text(self):
        text = (
            "1\n"
            "00:00:01,000 --> 00:00:02,000\n"
            "\n"
            "2\n"
            "00:00:03,000 --> 00:00:04,000\n"
            "After\n"
        )
        subs = parse_srt(text)
        self.assertEqual(len(subs), 2)
        self.assertEqual(subs[0].text, "")
        self.assertEqual(subs[1].text, "After")

    def test_extra_blank_lines_between_cues(self):
        text = (
            "1\n"
            "00:00:01,000 --> 00:00:02,000\n"
            "First\n\n\n\n"
            "2\n"
            "00:00:03,000 --> 00:00:04,000\n"
            "Second\n"
        )
        subs = parse_srt(text)
        self.assertEqual(len(subs), 2)
        self.assertEqual(subs[0].text, "First")
        self.assertEqual(subs[1].text, "Second")

    def test_omitted_index(self):
        # Some files skip the numeric index line entirely.
        text = (
            "00:00:01,000 --> 00:00:02,000\n"
            "No index\n"
        )
        subs = parse_srt(text)
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0].text, "No index")
        self.assertIsNone(subs[0].index)

    def test_empty_string(self):
        self.assertEqual(parse_srt(""), [])

    def test_only_blank_lines(self):
        self.assertEqual(parse_srt("\n\n\n"), [])

    def test_bad_timing_raises(self):
        text = (
            "1\n"
            "00:00:01,000 --> not-a-time\n"
            "Broken\n"
        )
        with self.assertRaises(ValueError):
            parse_srt(text)

    def test_text_containing_arrow_like_line(self):
        # A line in the body that happens to contain --> must NOT be treated
        # as a timing line; it is just text.
        text = (
            "1\n"
            "00:00:01,000 --> 00:00:02,000\n"
            "See --> this\n"
        )
        subs = parse_srt(text)
        self.assertEqual(subs[0].text, "See --> this")


class TestRenderer(unittest.TestCase):

    def test_basic_render(self):
        subs = [
            Subtitle(start=1000, end=2000, text="Hello"),
            Subtitle(start=3000, end=4000, text="World"),
        ]
        out = render_srt(subs)
        self.assertTrue(out.startswith("1\n"))
        self.assertIn("00:00:01,000 --> 00:00:02,000\nHello", out)
        self.assertIn("2\n00:00:03,000 --> 00:00:04,000\nWorld", out)
        # Cues are separated by a single blank line.
        self.assertIn("Hello\n\n2\n", out)

    def test_renumbers_ignoring_source_index(self):
        subs = [
            Subtitle(start=1000, end=2000, text="A", index=99),
            Subtitle(start=3000, end=4000, text="B", index=7),
        ]
        out = render_srt(subs)
        self.assertIn("1\n00:00:01,000", out)
        self.assertIn("2\n00:00:03,000", out)
        self.assertNotIn("99\n", out)
        self.assertNotIn("7\n00:00:03", out)

    def test_multiline_text_rendered(self):
        sub = Subtitle(start=0, end=1000, text="Line one\nLine two")
        out = render_srt([sub])
        self.assertIn("Line one\nLine two", out)


class TestRoundTrip(unittest.TestCase):

    def test_round_trip_preserves_content(self):
        original = (
            "1\n"
            "00:00:01,000 --> 00:00:02,000\n"
            "Hello world\n\n"
            "2\n"
            "00:00:03,500 --> 00:00:04,750\n"
            "Multi\nline\n"
        )
        subs = parse_srt(original)
        rendered = render_srt(subs)
        # Re-parse the rendered output and compare structurally.
        subs2 = parse_srt(rendered)
        self.assertEqual(len(subs), len(subs2))
        for a, b in zip(subs, subs2):
            self.assertEqual(a.start, b.start)
            self.assertEqual(a.end, b.end)
            self.assertEqual(a.text, b.text)

    def test_round_trip_stable(self):
        # Rendering then re-rendering should produce identical text.
        subs = [
            Subtitle(start=0, end=1000, text="A"),
            Subtitle(start=2000, end=3000, text="B\nC"),
        ]
        once = render_srt(subs)
        twice = render_srt(parse_srt(once))
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
