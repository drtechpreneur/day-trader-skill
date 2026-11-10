import datetime
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal

from _load import load

exitp = load("trader-exit", "exit")

ROOT = os.path.dirname(__file__)
DAY = datetime.date(2026, 10, 19)
SYMBOL = "RELIANCE.NS"
DT = datetime.datetime
EPOCH = DT(1970, 1, 1)


def stamp(slot):
    local = DT.combine(DAY, datetime.time(9, 15)) + datetime.timedelta(minutes=5 * slot)
    return int((exitp.ist_to_utc(local) - EPOCH).total_seconds())


def chart_doc(symbol=SYMBOL, count=10):
    closes = [100.0 + i * 0.2 for i in range(count)]
    return {"chart": {"result": [{
        "meta": {"symbol": symbol, "dataGranularity": "5m", "regularMarketTime": None},
        "timestamp": [stamp(i) for i in range(count)],
        "indicators": {"quote": [{"open": [c - 0.1 for c in closes],
                                   "high": [c + 1.0 for c in closes],
                                   "low": [c - 1.0 for c in closes],
                                   "close": closes, "volume": [1000] * count}]},
    }], "error": None}}


class RiskMath(unittest.TestCase):
    def test_inr_rounding_and_opening_range_stops(self):
        sr, sp = exitp.parse_stop("or-mid")
        tr, tp = exitp.parse_target("1R")
        p = exitp.compute(103.0, sr, sp, tr, tp, 102.01, 99.0)
        self.assertEqual((p["entry"], p["stop"], p["target"], p["risk"]),
                         (Decimal("103.00"), Decimal("100.50"), Decimal("105.50"), Decimal("2.50")))
        self.assertEqual(p["stop_label"], "opening-range midpoint")
        self.assertEqual(p["target_label"], "1R (one times the risk)")
        self.assertIn("rounded down", p["stop_detail"])
        p = exitp.compute(103.0, *exitp.parse_stop("or-low"), *exitp.parse_target("2R"), 102.0, 99.0)
        self.assertEqual((p["stop"], p["target"]), (Decimal("99.00"), Decimal("111.00")))

    def test_percent_atr_and_price_stops(self):
        p = exitp.compute(100.0, *exitp.parse_stop("pct:1"), *exitp.parse_target("2R"))
        self.assertEqual((p["stop"], p["risk"], p["target"]), (Decimal("99.00"), Decimal("1.00"), Decimal("102.00")))
        p = exitp.compute(100.0, *exitp.parse_stop("atr:1.5"), *exitp.parse_target("1R"), atr=2.0, atr_bars=9)
        self.assertEqual((p["stop"], p["target"]), (Decimal("97.00"), Decimal("103.00")))
        p = exitp.compute(100.0, *exitp.parse_stop("price:99.01"), *exitp.parse_target("price:101.49"))
        self.assertEqual(p["target"], Decimal("101.49"))

    def test_refuses_unsafe_or_malformed_plans(self):
        for stop, target in (("price:103", "2R"), ("pct:0.01", "2R"), ("or-mid", "price:102")):
            with self.subTest(stop=stop, target=target), self.assertRaises(exitp.PlanError):
                exitp.compute(103.0, *exitp.parse_stop(stop), *exitp.parse_target(target),
                              102.0, 99.0)
        with self.assertRaises(exitp.PlanError):
            exitp.parse_stop("atr:-1")
        with self.assertRaises(exitp.PlanError):
            exitp.parse_target("0R")
        with self.assertRaises(exitp.PlanError):
            exitp.compute(0, *exitp.parse_stop("price:-1"), *exitp.parse_target("2R"))


class SessionData(unittest.TestCase):
    def test_nse_atr_uses_only_regular_session_bars(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path = os.path.join(folder, SYMBOL + ".json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(chart_doc(count=18), fh)
            chart = exitp.load_chart("reliance", "5m", DAY, path)
        bars = exitp.session_bars(chart, DAY, "5m", upto_slot=8)
        self.assertEqual(len(bars), 9)
        self.assertEqual(bars[0]["t"], stamp(0))
        atr, n = exitp.atr_of(bars)
        self.assertEqual(n, 9)
        self.assertAlmostEqual(atr, 2.0)
        self.assertEqual(exitp.session_bars(chart, datetime.date(2026, 10, 17), "5m"), [])

    def test_rejects_mismatched_offline_symbol(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path = os.path.join(folder, "wrong.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(chart_doc("TCS.NS"), fh)
            with self.assertRaises(exitp.PlanError) as cm:
                exitp.load_chart("RELIANCE", "5m", DAY, path)
        self.assertIn("holds TCS.NS, not RELIANCE", str(cm.exception))


class PlanCli(unittest.TestCase):
    def test_cli_writes_nse_plan_and_never_places_an_order(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            os.mkdir(os.path.join(folder, "trader"))
            cwd = os.getcwd()
            try:
                os.chdir(folder)
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    code = exitp.main(["plan", "--symbol", "RELIANCE", "--entry", "103",
                                       "--date", DAY.isoformat(), "--time", "09:45",
                                       "--or-high", "102", "--or-low", "99", "--target", "1R",
                                       "--now", DAY.isoformat() + " 10:00", "--write"])
                self.assertEqual(code, 0, err.getvalue())
                self.assertIn("RELIANCE.NS", out.getvalue())
                self.assertIn("₹", out.getvalue())
                self.assertIn("Set before the entry", out.getvalue())
                self.assertIn("not a guarantee", out.getvalue())
                with open(os.path.join("trader", "plan.json"), encoding="utf-8") as fh:
                    plan = json.load(fh)
                self.assertEqual((plan["symbol"], plan["stop"], plan["target"], plan["flat_by"]),
                                 (SYMBOL, 100.5, 105.5, "15:25"))
            finally:
                os.chdir(cwd)

    def test_cli_rejects_closed_nse_holiday(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            os.mkdir(os.path.join(folder, "trader"))
            cwd = os.getcwd()
            try:
                os.chdir(folder)
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    code = exitp.main(["plan", "--symbol", "RELIANCE.NS", "--entry", "103",
                                       "--date", "2026-11-10", "--or-high", "102", "--or-low", "99"])
                self.assertEqual(code, 1)
                self.assertIn("NSE cash market is closed", err.getvalue())
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
