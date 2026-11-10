import datetime
import json
import unittest
import urllib.error
import io

from _load import load

tm = load("trader-timemachine", "timemachine")

DT = datetime.datetime
D = datetime.date
DAY = D(2026, 10, 19)
SYMBOL = "RELIANCE.NS"
EPOCH = DT(1970, 1, 1)


def epoch(local):
    return int((tm.market_clock.ist_to_utc(local) - EPOCH).total_seconds())


def synthetic_chart():
    dates = []
    d = D(2026, 8, 3)
    while d < DAY:
        if tm.market_clock.trading_day(d)[0]:
            dates.append(d)
        d += datetime.timedelta(days=1)
    dates.append(DAY)
    timestamps, opens, highs, lows, closes, volumes = [], [], [], [], [], []
    for day_index, day in enumerate(dates):
        count = 9 if day == DAY else tm.SESSION_BARS
        previous = 100.0 + day_index * 0.005
        for slot in range(count):
            start = DT.combine(day, datetime.time(9, 15)) + datetime.timedelta(minutes=5 * slot)
            change = ((slot % 7) - 3) * 0.0007
            close = previous * (1 + change)
            timestamps.append(epoch(start))
            opens.append(previous)
            highs.append(max(previous, close) * 1.004)
            lows.append(min(previous, close) * 0.996)
            closes.append(close)
            volumes.append(10000)
            previous = close
    rmt = epoch(DT(2026, 10, 19, 10, 0))
    return json.dumps({"chart": {"result": [{
        "meta": {"symbol": SYMBOL, "currency": "INR", "dataGranularity": "5m", "regularMarketTime": rmt},
        "timestamp": timestamps,
        "indicators": {"quote": [{"open": opens, "high": highs, "low": lows,
                                   "close": closes, "volume": volumes}]},
    }], "error": None}})


def plan(**overrides):
    data = {"created_by": "trader-exit", "symbol": SYMBOL, "side": "buy", "date": DAY.isoformat(),
            "setup": "orb", "entry": 100.0, "entry_time": "09:45 AM", "entry_bar": 5,
            "interval": "5m", "opening_range": {"high": 101.0, "low": 99.0, "minutes": 15},
            "stop": 99.0, "target": 102.0, "stop_rule": "or_mid", "flat_by": "15:25"}
    data.update(overrides)
    return tm.normalize_plan(data)


class NSEData(unittest.TestCase):
    def test_clock_symbol_and_market_calendar(self):
        self.assertEqual(tm.parse_now("2026-10-19 10:15"), DT(2026, 10, 19, 4, 45))
        self.assertIn("chart/RELIANCE.NS?", tm.chart_url("reliance"))
        with self.assertRaises(tm.TMError) as cm:
            plan(date="2026-11-10")
        self.assertIn("NSE cash market is closed", str(cm.exception))

    def test_parser_keeps_full_ist_sessions_and_discards_off_grid_prints(self):
        text = synthetic_chart()
        doc = json.loads(text)
        r = doc["chart"]["result"][0]
        r["timestamp"].append(r["timestamp"][-1] + 30)
        q = r["indicators"]["quote"][0]
        for key, value in (("open", 100.0), ("high", 101.0), ("low", 99.0),
                           ("close", 100.5), ("volume", 1)):
            q[key].append(value)
        _, bars, dropped = tm.parse_bars(r, tm.parse_now("2026-10-19 10:00"))
        self.assertGreaterEqual(len(tm.full_sessions(tm.split_sessions(bars), DAY.isoformat())[0]), 20)
        self.assertGreater(dropped["off_grid"], 0)
        self.assertEqual(bars[0]["start"], "09:15")
        self.assertTrue(all(b["date"] != "2026-10-17" for b in bars))

    def test_plan_requires_a_valid_nse_bar_and_price_order(self):
        p = plan()
        self.assertEqual((p["symbol"], p["entry_time"], p["entry_bar"]), (SYMBOL, "9:45 AM", 5))
        with self.assertRaises(tm.TMError) as cm:
            plan(entry_bar=6)
        self.assertIn("disagrees with itself", str(cm.exception))
        with self.assertRaises(tm.TMError):
            plan(stop=100.0)
        with self.assertRaises(tm.TMError):
            plan(entry_time="09:47 AM", entry_bar=None)


class Replay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = synthetic_chart()
        cls.now = tm.parse_now("2026-10-19 10:00")

    def run_machine(self, **kw):
        return tm.time_machine(self.text, plan(), self.now, replays=200, seed=19, **kw)

    def test_simulation_and_history_are_deterministic_for_nse_data(self):
        a = self.run_machine()
        b = self.run_machine()
        self.assertEqual(a["mc"], b["mc"])
        self.assertEqual(a["plan"]["symbol"], SYMBOL)
        self.assertGreaterEqual(a["mc"]["pool_sessions"], 20)
        self.assertEqual((a["mc"]["replays"], a["mc"]["until"]), (200, "15:30"))
        self.assertAlmostEqual(a["mc"]["p_target"] + a["mc"]["p_stop"] + a["mc"]["p_neither"], 1.0)
        self.assertEqual(a["mc"]["band_times"][0], "09:45")
        self.assertEqual(a["mc"]["band_times"][-1], "15:30")
        self.assertEqual(a["history"]["sessions"], a["mc"]["pool_sessions"])
        self.assertIn("not a prediction", a["note"])
        self.assertIn(SYMBOL, "\n".join(tm.report(a)))

    def test_seed_and_until_change_replay_without_changing_the_contract(self):
        first = self.run_machine(window=0)["mc"]
        second = self.run_machine(window=0, until="15:25")["mc"]
        self.assertEqual(first["window"], 0)
        self.assertEqual((second["until"], second["band_times"][-1]), ("15:25", "15:25"))
        self.assertNotEqual(first["band_times"], second["band_times"])
        self.assertEqual(tm.verdict({"p_target": 0.0, "p_stop": 0.0, "until": "15:25"}),
                         "No replay reached the target or the stop by 3:25 PM: the price at 3:25 PM decides every one.")

    def test_requires_enough_full_sessions_and_a_complete_entry_bar(self):
        short = json.loads(self.text)
        r = short["chart"]["result"][0]
        q = r["indicators"]["quote"][0]
        start = next(i for i, t in enumerate(r["timestamp"]) if tm.to_ist(tm.utc_of(t)).date() == DAY)
        keep = list(range(start, len(r["timestamp"])))
        r["timestamp"] = [r["timestamp"][i] for i in keep]
        for key in q:
            q[key] = [q[key][i] for i in keep]
        with self.assertRaises(tm.TMError) as cm:
            tm.time_machine(json.dumps(short), plan(), self.now, replays=10)
        self.assertIn("needs at least 20", str(cm.exception))


class YahooApi(unittest.TestCase):
    def test_retry_uses_the_canonical_nse_ticker(self):
        calls, sleeps = [], []

        def fake(url, timeout=20):
            calls.append(url)
            if len(calls) == 1:
                raise urllib.error.HTTPError(url, 429, "busy", {}, io.BytesIO())
            return synthetic_chart()

        saved = tm._get, tm._sleep
        tm._get, tm._sleep = fake, sleeps.append
        try:
            text = tm.fetch_chart("reliance")
        finally:
            tm._get, tm._sleep = saved
        self.assertIn('"RELIANCE.NS"', text)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all("chart/RELIANCE.NS?range=60d&interval=5m" in u for u in calls))
        self.assertEqual(sleeps, [tm.BACKOFF])


if __name__ == "__main__":
    unittest.main()
