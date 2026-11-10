import datetime
import json
import os
import tempfile
import unittest

from _load import load

scan = load("trader-scanner", "scan")

ROOT = os.path.dirname(__file__)
DT = datetime.datetime
D = datetime.date
DAY = D(2026, 10, 19)
EPOCH = DT(1970, 1, 1)


def local_stamp(day, clock):
    local = DT.combine(day, datetime.datetime.strptime(clock, "%H:%M").time())
    return int((scan.local_to_utc(local) - EPOCH).total_seconds())


def series(day=DAY, closes=None, highs=None, lows=None, volume=None, start="09:15"):
    closes = closes or [100.5, 101.0, 100.8, 100.9, 101.0, 102.5]
    highs = highs or [101.0, 102.0, 101.2] + [c + 0.15 for c in closes[3:]]
    lows = lows or [99.0, 99.5, 99.8] + [c - 0.15 for c in closes[3:]]
    clocks = [(DT.combine(day, datetime.datetime.strptime(start, "%H:%M").time()) +
               datetime.timedelta(minutes=5 * i)).strftime("%H:%M") for i in range(len(closes))]
    return {"t": [local_stamp(day, c) for c in clocks], "c": list(closes),
            "h": list(highs), "l": list(lows), "v": list(volume or [1000] * len(closes)), "meta": {}}


class MarketAndSymbols(unittest.TestCase):
    def test_nse_symbol_normalization_and_encoded_urls(self):
        self.assertEqual(scan.normalize_symbol("reliance", "nse"), "RELIANCE.NS")
        self.assertEqual(scan.normalize_symbol("reliance.ns", "nse"), "RELIANCE.NS")
        self.assertEqual(scan.to_yahoo("reliance.ns"), "RELIANCE.NS")
        self.assertEqual(scan.spark_path(["RELIANCE.NS", "M&M.NS"], "3mo", "1d"),
                         "/v7/finance/spark?symbols=RELIANCE.NS,M%26M.NS&range=3mo&interval=1d")
        self.assertEqual(scan.chart_path("RELIANCE.NS", "3mo", "1d"),
                         "/v8/finance/chart/RELIANCE.NS?range=3mo&interval=1d")
        with self.assertRaises(scan.ScanError):
            scan.normalize_symbol("RELIANCE.B", "nse")

    def test_ist_clock_and_regular_session(self):
        self.assertEqual(scan.parse_now("2026-10-19 10:15"), DT(2026, 10, 19, 4, 45))
        self.assertEqual(scan.session(DAY), (datetime.time(9, 15), datetime.time(15, 30)))
        self.assertEqual(scan.to_local(DT(2026, 10, 19, 4, 45)), DT(2026, 10, 19, 10, 15))
        self.assertEqual(scan.clock_label(DT(2026, 10, 19, 9, 15)), "9:15 AM")
        self.assertIn("Diwali-Balipratipada", scan.trading_day(D(2026, 11, 10))[1])

    def test_watchlist_file_is_nse_and_deduplicated_by_caller(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path = os.path.join(folder, "watchlist.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"hits": [{"symbol": "reliance"}, {"symbol": "TCS.NS"}]}, fh)
            self.assertEqual(scan.symbols_from_file(path), ["RELIANCE.NS", "TCS.NS"])


class Parsing(unittest.TestCase):
    def test_spark_parser_preserves_nse_symbols(self):
        sym = series()
        doc = {"spark": {"result": [{
            "symbol": "RELIANCE.NS",
            "response": [{"timestamp": sym["t"], "indicators": {"quote": [{"close": sym["c"]}]},
                          "meta": {"currency": "INR"}}],
        }]}}
        parsed = scan.parse_spark(doc)
        self.assertIn("RELIANCE.NS", parsed)
        self.assertEqual(parsed["RELIANCE.NS"]["c"], sym["c"])
        self.assertEqual(parsed["RELIANCE.NS"]["meta"]["currency"], "INR")
        with self.assertRaises(scan.ScanError):
            scan.parse_spark({"not_spark": {}})

    def test_daily_bar_is_ignored_until_the_ist_close(self):
        dates = [D(2026, 10, 16), DAY]
        data = {"t": [local_stamp(d, "09:15") for d in dates], "c": [100.0, 105.0]}
        before_close = scan.daily_closes(data, scan.parse_now(DAY.isoformat() + " 15:29"))
        after_close = scan.daily_closes(data, scan.parse_now(DAY.isoformat() + " 15:30"))
        self.assertEqual(before_close, [(dates[0], 100.0)])
        self.assertEqual(after_close, [(dates[0], 100.0), (DAY, 105.0)])

    def test_daily_breakout_flag_and_oversold_algorithms(self):
        rising = [100.0] * 16 + [101.5, 103.0, 105.0, 107.0, 109.0,
                                 111.0, 112.0, 112.2, 112.1, 112.3, 112.4,
                                 112.2, 112.3, 112.1, 112.5]
        tags, facts = scan.find_setups(rising)
        self.assertIn("breakout_20d", tags)
        self.assertIn("bull_flag", tags)
        self.assertGreater(facts["run_pct"], 10)
        falling = [120.0 - i for i in range(31)]
        tags, facts = scan.find_setups(falling)
        self.assertIn("oversold", tags)
        self.assertLess(facts["rsi"], 30)


class OpeningRange(unittest.TestCase):
    def test_nse_orb_uses_opening_range_and_first_completed_close(self):
        s = series()
        cutoff = DT(2026, 10, 19, 9, 45)
        bars = scan.session_bars(s, DAY, cutoff)
        self.assertEqual(len(bars), 6)
        self.assertEqual(bars[0]["start"], DT(2026, 10, 19, 9, 15))
        self.assertTrue(scan.usable(bars, DAY, cutoff, 3))
        self.assertTrue(scan.orb_candidate(bars, 3))
        hit = scan.orb_hit(bars, 3)
        self.assertEqual((hit["bar_start"], hit["at"], hit["bar_index"]), ("09:40", "9:45 AM", 5))
        self.assertEqual((hit["or_high"], hit["or_low"], hit["price"]), (102.0, 99.0, 102.5))

    def test_scan_confirms_candidates_and_reports_failed_fetches(self):
        spark = series()
        confirmed = []

        def fetch(sym):
            confirmed.append(sym)
            return series()

        hits, counts, errors = scan.scan_orb({"RELIANCE.NS": spark}, ["RELIANCE.NS"], DAY,
                                             DT(2026, 10, 19, 9, 45), 15,
                                             confirm=fetch)
        self.assertEqual([h["symbol"] for h in hits], ["RELIANCE.NS"])
        self.assertEqual(counts["candidates"], 1)
        self.assertEqual(confirmed, ["RELIANCE.NS"])
        self.assertEqual(errors, {})

        def fail(_):
            raise scan.ScanError("Yahoo answered HTTP 429")
        hits, _, errors = scan.scan_orb({"RELIANCE.NS": spark}, ["RELIANCE.NS"], DAY,
                                        DT(2026, 10, 19, 9, 45), 15, confirm=fail)
        self.assertEqual(hits, [])
        self.assertIn("429", errors["RELIANCE.NS"])

    def test_incomplete_missing_and_out_of_session_bars_are_not_usable(self):
        s = series()
        self.assertEqual(len(scan.session_bars(s, DAY, DT(2026, 10, 19, 9, 44))), 5)
        missing = dict(s, t=s["t"][:4] + s["t"][5:], c=s["c"][:4] + s["c"][5:],
                       h=s["h"][:4] + s["h"][5:], l=s["l"][:4] + s["l"][5:],
                       v=s["v"][:4] + s["v"][5:])
        bars = scan.session_bars(missing, DAY, DT(2026, 10, 19, 9, 45))
        self.assertFalse(scan.usable(bars, DAY, DT(2026, 10, 19, 9, 45), 3))

    def test_orb_window_respects_nse_holiday_and_session(self):
        with self.assertRaises(scan.ScanError) as cm:
            scan.orb_window(scan.parse_now("2026-11-10 10:00"), None, 15, datetime.time(15, 30))
        self.assertIn("market is closed", str(cm.exception))
        with self.assertRaises(scan.ScanError) as cm:
            scan.orb_window(scan.parse_now("2026-10-19 09:30"), None, 15, datetime.time(15, 30))
        self.assertIn("Run orb again after 9:35 AM", str(cm.exception))
        with self.assertRaises(scan.ScanError) as cm:
            scan.orb_window(scan.parse_now("2026-10-19 15:45"), None, 15, datetime.time(15, 30))
        self.assertIn("3:30 PM IST", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
