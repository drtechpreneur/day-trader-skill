import datetime
import io
import json
import os
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout

from _load import load

entry = load("trader-entry", "entry")

ROOT = os.path.dirname(__file__)
DT = datetime.datetime
DAY = datetime.date(2026, 10, 19)
SYMBOL = "RELIANCE.NS"
EPOCH = DT(1970, 1, 1)


def stamp(day, clock):
    local = DT.combine(day, datetime.datetime.strptime(clock, "%H:%M").time())
    return int((entry.ist_to_utc(local) - EPOCH).total_seconds())


def chart_doc(symbol=SYMBOL, closes=None, with_tick=False):
    closes = closes or [100.5, 101.0, 100.8, 100.9, 101.0, 102.5, 102.0, 102.2, 102.1]
    times, opens, highs, lows, volumes = [], [], [], [], []
    for i, close in enumerate(closes):
        times.append(stamp(DAY, (DT.combine(DAY, datetime.time(9, 15)) +
                                 datetime.timedelta(minutes=5 * i)).strftime("%H:%M")))
        opens.append(close - 0.1)
        highs.append([101.0, 102.0, 101.2][i] if i < 3 else close + 0.15)
        lows.append([99.0, 99.5, 99.8][i] if i < 3 else close - 0.15)
        volumes.append(3000 if i < 3 else 5000)
    if with_tick:
        times.append(stamp(DAY, "10:00") + 30)
        opens.append(104.0)
        highs.append(105.0)
        lows.append(103.0)
        closes.append(104.5)
        volumes.append(1)
    return {"chart": {"result": [{
        "meta": {"symbol": symbol, "currency": "INR", "exchangeName": "NSI",
                 "dataGranularity": "5m", "previousClose": 99.0, "regularMarketTime": None},
        "timestamp": times,
        "indicators": {"quote": [{"open": opens, "high": highs, "low": lows,
                                   "close": closes, "volume": volumes}]},
    }], "error": None}}


def parsed(doc=None):
    return entry.parse_chart(json.dumps(doc or chart_doc()), SYMBOL)


def at(clock, data=None, **options):
    return entry.evaluate(parsed(data), entry.parse_now(DAY.isoformat() + " " + clock), **options)


class ClockAndParsing(unittest.TestCase):
    def test_ist_clock_session_and_canonical_yahoo_path(self):
        self.assertEqual(entry.parse_now("2026-10-19 09:15"), DT(2026, 10, 19, 3, 45))
        self.assertEqual(entry.session(DAY), (datetime.time(9, 15), datetime.time(15, 30)))
        self.assertEqual(entry.yahoo_symbol("reliance"), SYMBOL)
        self.assertEqual(entry.chart_path("reliance", "1d", "5m"),
                         "/v8/finance/chart/RELIANCE.NS?range=1d&interval=5m")

    def test_chart_parser_keeps_nse_bars_and_drops_null_close(self):
        doc = chart_doc(with_tick=True)
        doc["chart"]["result"][0]["timestamp"].insert(3, None)
        doc["chart"]["result"][0]["indicators"]["quote"][0]["close"].insert(3, None)
        ch = parsed(doc)
        self.assertEqual(ch["symbol"], SYMBOL)
        self.assertEqual(len(ch["bars"]), 10)
        self.assertEqual(ch["bars"][0]["t"], stamp(DAY, "09:15"))
        with self.assertRaises(entry.EntryError):
            entry.parse_chart("<html>", SYMBOL)

    def test_orb_waits_for_completed_bars_and_triggers_above_range(self):
        self.assertEqual(at("09:44")["status"], "waiting")
        res = at("09:45")
        self.assertEqual((res["status"], res["phase"]), ("triggered", "open"))
        self.assertEqual((res["opens"], res["closes"]), ("09:15", "15:30"))
        self.assertEqual((res["opening_range"]["high"], res["opening_range"]["low"]), (102.0, 99.0))
        self.assertEqual((res["trigger"]["bar_start"], res["trigger"]["time"],
                          res["trigger"]["bar_index"], res["trigger"]["price"]),
                         ("09:40", "9:45 AM", 5, 102.5))
        self.assertEqual(at("09:44:59")["status"], "waiting")

    def test_range_forms_from_the_0915_open_and_volume_can_confirm(self):
        res = at("09:25")
        self.assertEqual((res["phase"], res["opening_range"]["bars"], res["opening_range"]["complete"]),
                         ("forming", 2, False))
        thin = chart_doc()
        thin["chart"]["result"][0]["indicators"]["quote"][0]["volume"][5] = 100
        res = at("09:45", thin, min_volume_x=1.0)
        self.assertEqual(res["status"], "waiting")
        self.assertIn("under your 1.00x", res["reason"])

    def test_off_grid_live_tick_cannot_create_a_breakout(self):
        closes = [100.5, 101.0, 100.8, 100.9, 101.0, 101.2, 101.0, 101.3, 101.4]
        res = at("10:01", chart_doc(closes=closes, with_tick=True))
        self.assertNotEqual(res["status"], "triggered")
        self.assertTrue(all(b["t"] % 300 == 0 for b in res["_bars"]))
        self.assertEqual(res["_bars"][-1]["et"].strftime("%H:%M"), "09:55")

    def test_level_cutoff_closed_days_and_bad_setup(self):
        res = at("09:50", setup="level", level=102.0)
        self.assertEqual(res["trigger"]["bar_start"], "09:40")
        no_break = chart_doc(closes=[100.5, 101.0, 100.8, 100.9, 101.0, 101.2, 101.3])
        res = at("15:30", no_break)
        self.assertEqual(res["status"], "expired")
        self.assertIn("by 15:30", res["reason"])
        closed = entry.evaluate(parsed(), entry.parse_now("2026-10-17 10:00"))
        self.assertEqual((closed["status"], closed["phase"]), ("no-data", "closed"))
        self.assertEqual(closed["next_open"], "2026-10-19 09:15")
        with self.assertRaises(entry.EntryError):
            at("10:00", setup="level")

    def test_yahoo_404_is_a_plain_no_data_error(self):
        bad = json.dumps({"chart": {"result": None, "error": {"description": "No data found"}}})
        with self.assertRaises(entry.EntryError) as cm:
            entry.parse_chart(bad, "UNKNOWN.NS")
        self.assertIn("No data found", str(cm.exception))


class NetworkAndCli(unittest.TestCase):
    def test_fetch_retries_and_uses_nse_chart_path(self):
        calls, sleeps = [], []
        body = json.dumps(chart_doc())

        def fake(url, timeout=20):
            calls.append(url)
            if len(calls) == 1:
                raise urllib.error.HTTPError(url, 429, "busy", {}, io.BytesIO())
            return body

        saved = entry._open_url, entry._sleep
        entry._open_url, entry._sleep = fake, sleeps.append
        try:
            result = entry.get_chart("RELIANCE", "5m", DAY, today=DAY)
        finally:
            entry._open_url, entry._sleep = saved
        self.assertEqual(result["symbol"], SYMBOL)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all("/chart/RELIANCE.NS?range=1d&interval=5m" in u for u in calls))
        self.assertEqual(sleeps, [entry.BACKOFF])

    def test_offline_cli_writes_nse_entry_plan_without_placing_an_order(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            data = os.path.join(folder, SYMBOL + ".json")
            with open(data, "w", encoding="utf-8") as fh:
                json.dump(chart_doc(), fh)
            os.mkdir(os.path.join(folder, "trader"))
            cwd = os.getcwd()
            try:
                os.chdir(folder)
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    code = entry.main(["check", "RELIANCE", "--offline", data,
                                       "--now", DAY.isoformat() + " 09:45", "--write"])
                self.assertEqual(code, 0, err.getvalue())
                self.assertIn("RELIANCE.NS", out.getvalue())
                with open(os.path.join("trader", "entry.json"), encoding="utf-8") as fh:
                    doc = json.load(fh)
                self.assertEqual((doc["symbol"], doc["status"]), (SYMBOL, "triggered"))
                self.assertEqual(doc["date"], DAY.isoformat())
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
