import unittest

from serenity_digest import build_serenity_digest, format_serenity_section


class SerenityDigestTests(unittest.TestCase):
    def test_build_digest_for_june_11(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        digest = build_serenity_digest(
            days_ago=2,
            now=datetime(2026, 6, 13, 10, 0, tzinfo=ZoneInfo("Australia/Sydney")),
        )
        self.assertEqual(digest.target_date, "2026-06-11")
        self.assertIn("FOCI", digest.tickers)
        self.assertEqual(digest.sentiment_label, "偏看涨")

    def test_format_section_contains_themes(self):
        digest = build_serenity_digest(
            days_ago=2,
            now=__import__("datetime").datetime(
                2026, 6, 13, 10, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Australia/Sydney")
            ),
        )
        text = "\n".join(format_serenity_section(digest))
        self.assertIn("Serenity", text)
        self.assertIn("核心观点", text)


if __name__ == "__main__":
    unittest.main()
