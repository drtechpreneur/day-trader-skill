import datetime
import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout

from _load import FIX, load

news = load("trader-news", "news")
DIR = os.path.join(FIX, "trader-news")
NOW = "2026-11-08T23:59:00+05:30"


def raw(name):
    with open(os.path.join(DIR, name), "rb") as fh:
        return fh.read()


def run(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = news.main(args)
    return code, out.getvalue(), err.getvalue()


class NSEAnnouncements(unittest.TestCase):
    def test_parses_exchange_announcement(self):
        items = news.parse_announcements(raw("nse-RELIANCE.json"), "RELIANCE")
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["source"], "NSE India")
        self.assertEqual(item["ticker"], "RELIANCE")
        self.assertEqual(item["company"], "Reliance Industries Limited")
        self.assertEqual(item["title"], "Analysts/Institutional Investor Meet/Con. Call Updates")
        self.assertEqual(item["id"], "nse:106851483")
        self.assertTrue(item["link"].startswith("https://nsearchives.nseindia.com/"))
        self.assertEqual(item["time"].isoformat(), "2026-11-06T19:10:58+05:30")

    def test_ignores_rows_for_other_symbols(self):
        data = json.dumps([
            {"symbol": "RELIANCE", "desc": "R", "seq_id": "1"},
            {"symbol": "AAPL", "desc": "Not an NSE result", "seq_id": "2"},
        ])
        self.assertEqual([x["ticker"] for x in news.parse_announcements(data, "RELIANCE")],
                         ["RELIANCE"])

    def test_rejects_unexpected_responses(self):
        with self.assertRaises(news.NewsError):
            news.parse_announcements(b"not json", "RELIANCE")
        with self.assertRaises(news.NewsError):
            news.parse_announcements(b'{"unexpected": []}', "RELIANCE")

    def test_times_are_india_local(self):
        parsed = news.parse_time("06-Nov-2026 19:10:58")
        self.assertEqual(parsed.utcoffset(), datetime.timedelta(hours=5, minutes=30))
        self.assertIsNone(news.parse_time("not a timestamp"))


class Filtering(unittest.TestCase):
    def test_window_dedupes_seen_items(self):
        item = news.parse_announcements(raw("nse-RELIANCE.json"), "RELIANCE")[0]
        now = news.parse_time(NOW).astimezone(datetime.timezone.utc)
        state = {}
        self.assertEqual(len(news.select([item], state, now, hours=72)), 1)
        fp = news.fingerprint(item)
        state["seen"] = {fp: now.isoformat()}
        self.assertEqual(news.select([item], state, now, hours=72), [])
        self.assertEqual(len(news.select([item], state, now, hours=72, show_all=True)), 1)
        self.assertEqual(news.select([item], {}, now, hours=24), [])

    def test_offline_cli_outputs_only_exchange_data(self):
        code, out, err = run(["--tickers", "RELIANCE", "--hours", "72", "--offline", DIR,
                              "--dry-run", "--now", NOW, "--json"])
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(data["items"][0]["source"], "NSE India")
        self.assertEqual(data["items"][0]["ticker"], "RELIANCE")
        self.assertEqual(data["items"][0]["time"], "2026-11-06T19:10:58+05:30")
        self.assertNotIn("SEC", out)
        self.assertNotIn("Yahoo", out)

    def test_scanner_nse_suffix_is_normalized_for_exchange_lookup(self):
        code, out, err = run(["--tickers", "RELIANCE.NS", "--hours", "72", "--offline", DIR,
                              "--dry-run", "--now", NOW, "--json"])
        self.assertEqual(code, 0, err)
        item = json.loads(out)["items"][0]
        self.assertEqual(item["ticker"], "RELIANCE.NS")
        self.assertEqual(item["company"], "Reliance Industries Limited")

    def test_us_symbol_does_not_fall_back_to_us_data(self):
        code, out, err = run(["--tickers", "AAPL", "--offline", DIR, "--dry-run",
                              "--now", NOW, "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(err, "")
        self.assertEqual(json.loads(out)["items"], [])
        self.assertIn("no file", json.loads(out)["notes"][0])

    def test_no_symbols_is_an_error(self):
        code, _, err = run(["--tickers", "--offline", DIR, "--dry-run",
                            "--portfolio", "tests/nonexistent-portfolio.json",
                            "--watchlist", "tests/nonexistent-watchlist.json",
                            "--plan", "tests/nonexistent-plan.json"])
        self.assertEqual(code, 2)
        self.assertIn("no NSE symbols", err)


if __name__ == "__main__":
    unittest.main()
