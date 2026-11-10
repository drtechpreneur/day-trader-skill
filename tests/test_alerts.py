import datetime
import io
import json
import os
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout

from _load import load

alerts = load("trader-alerts", "alerts")

ROOT = os.path.dirname(__file__)
DT = datetime.datetime
DAY = "2026-10-19"
SYMBOL = "RELIANCE.NS"


def now(text):
    return alerts.parse_now(text)


def quote_doc(price=101.25, previous=100.0):
    stamp = alerts.market_clock.ist_to_utc(DT(2026, 10, 19, 10, 15))
    epoch = int((stamp - DT(1970, 1, 1)).total_seconds())
    return json.dumps({"chart": {"result": [{
        "meta": {"symbol": SYMBOL, "currency": "INR", "regularMarketPrice": price,
                 "previousClose": previous, "regularMarketTime": epoch,
                 "regularMarketDayHigh": 102.0, "regularMarketDayLow": 99.0},
        "indicators": {"quote": [{"open": [100.5]}]},
    }], "error": None}})


class Clock(unittest.TestCase):
    def test_ist_input_and_utc_input(self):
        self.assertEqual(now("2026-10-19 09:15"), DT(2026, 10, 19, 3, 45))
        self.assertEqual(now("2026-10-19T03:45:00Z"), DT(2026, 10, 19, 3, 45))
        self.assertEqual(alerts.market_status(now("2026-10-19 09:14"))["next_open"], "2026-10-19 09:15")
        status = alerts.market_status(now("2026-10-19 09:15"))
        self.assertTrue(status["open"])
        self.assertEqual((status["opens"], status["closes"]), ("09:15", "15:30"))
        self.assertEqual(status["now_ist"], "2026-10-19 09:15")
        with self.assertRaises(alerts.AlertError):
            now("tomorrow")

    def test_2026_nse_holiday_and_weekend_calendar(self):
        self.assertIn("2026-11-10", alerts.market_clock.NSE_HOLIDAYS)
        holiday = alerts.market_status(now("2026-11-10 10:00"))
        self.assertFalse(holiday["open"])
        self.assertIn("Diwali-Balipratipada", holiday["reason"])
        self.assertEqual(holiday["next_open"], "2026-11-11 09:15")
        self.assertEqual(alerts.market_status(now("2026-10-17 10:00"))["reason"], "weekend")
        self.assertFalse(alerts.market_status(now("2027-03-01 10:00"))["calendar_known"])


class Quotes(unittest.TestCase):
    def test_yahoo_parser_and_nse_url(self):
        q = alerts.parse_yahoo(quote_doc(), "reliance")
        self.assertEqual(q["symbol"], SYMBOL)
        self.assertEqual((q["price"], q["prev_close"], q["open"]), (101.25, 100.0, 100.5))
        self.assertEqual(q["currency"], "INR")
        self.assertEqual(q["time"], "2026-10-19 10:15:00 IST")
        self.assertEqual(alerts.yahoo_url("reliance"),
                         "https://query2.finance.yahoo.com/v8/finance/chart/RELIANCE.NS?range=1d&interval=1d")
        with self.assertRaises(alerts.AlertError):
            alerts.parse_yahoo("<html>", SYMBOL)

    def test_offline_quote_normalizes_symbols_and_reports_missing_data(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            with open(os.path.join(folder, "yahoo-" + SYMBOL + ".json"), "w", encoding="utf-8") as fh:
                fh.write(quote_doc())
            quotes, errors = alerts.get_quotes(["RELIANCE", "TCS"], offline=folder)
        self.assertEqual(list(quotes), [SYMBOL])
        self.assertEqual(quotes[SYMBOL]["price"], 101.25)
        self.assertEqual(len(errors), 1)
        self.assertIn("no offline quote file", errors[0])

    def test_yahoo_retries_429_with_same_nse_url(self):
        calls, sleeps = [], []

        def fake(req, timeout=None):
            calls.append((req.full_url, req.get_header("User-agent")))
            if len(calls) == 1:
                raise urllib.error.HTTPError(req.full_url, 429, "busy", {}, io.BytesIO())
            return io.BytesIO(quote_doc().encode())

        saved = alerts._urlopen, alerts._sleep
        alerts._urlopen, alerts._sleep = fake, sleeps.append
        try:
            quotes, errors = alerts.get_quotes(["reliance"])
        finally:
            alerts._urlopen, alerts._sleep = saved
        self.assertFalse(errors)
        self.assertEqual(quotes[SYMBOL]["price"], 101.25)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all("/chart/RELIANCE.NS?" in call[0] for call in calls))
        self.assertEqual(sleeps, [alerts.BACKOFF])


class Rules(unittest.TestCase):
    def setUp(self):
        self.open = alerts.market_status(now(DAY + " 10:00"))
        self.q = {SYMBOL: {"price": 101.25, "prev_close": 100.0, "open": 100.5}}

    def evaluate(self, rules, clock="10:00", state=None, quotes=None):
        t = now(DAY + " " + clock)
        return alerts.evaluate(rules, quotes if quotes is not None else self.q,
                               alerts.market_status(t), state or {}, t)

    def test_price_alert_is_one_shot_and_rearms_when_requested(self):
        rule = {"id": "risk-stop", "type": "stop", "symbol": "reliance", "price": 100.0, "rearm": True}
        rings, state = self.evaluate([rule])
        self.assertEqual(rings, [])
        q = {SYMBOL: dict(self.q[SYMBOL], price=99.0)}
        rings, state = self.evaluate([rule], state=state, quotes=q)
        self.assertEqual(rings[0]["symbol"], SYMBOL)
        self.assertIn("₹99.00", rings[0]["message"])
        self.assertIn("₹100.", rings[0]["message"])
        self.assertEqual(self.evaluate([rule], state=state, quotes=q)[0], [])
        _, state = self.evaluate([rule], state=state)
        rings, _ = self.evaluate([rule], state=state, quotes=q)
        self.assertEqual(len(rings), 1)

    def test_pct_move_and_opening_bell_ring_once(self):
        pct = {"id": "move", "type": "pct_move", "symbol": SYMBOL, "pct": 1}
        bells = {"id": "bell", "type": "opening_bell"}
        rings, state = self.evaluate([pct, bells])
        self.assertEqual([r["id"] for r in rings], ["move", "bell"])
        self.assertIn("+1.25%", rings[0]["message"])
        self.assertEqual(self.evaluate([pct, bells], state=state)[0], [])

    def test_flat_by_time_uses_ist_and_is_not_an_order(self):
        rule = {"id": "flat", "type": "time", "at": "15:25", "label": "flat by close",
                "before_close": True, "symbol": SYMBOL}
        self.assertEqual(self.evaluate([rule], clock="15:24")[0], [])
        rings, state = self.evaluate([rule], clock="15:25")
        self.assertIn("15:25 IST", rings[0]["message"])
        self.assertIn("market closes at 15:30", rings[0]["message"])
        self.assertIn("trader-broker flatten --symbol RELIANCE.NS", rings[0]["message"])
        self.assertEqual(self.evaluate([rule], clock="15:29", state=state)[0], [])

    def test_plan_rules_and_invalid_rules(self):
        rules = alerts.rules_from_plan({"symbol": SYMBOL, "date": DAY, "stop": 99.0,
                                        "target": 103.0, "flat_by": "15:25"})
        self.assertEqual([r["type"] for r in rules], ["stop", "target", "time"])
        self.assertTrue(all(r["symbol"] == SYMBOL for r in rules))
        with self.assertRaises(alerts.AlertError):
            alerts.evaluate([{"id": "bad", "type": "moon"}], self.q, self.open, {}, now(DAY + " 10:00"))


class Cli(unittest.TestCase):
    def test_add_and_check_use_nse_contract(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            rules = os.path.join(folder, "alerts.json")
            state = os.path.join(folder, "state.json")
            prices = os.path.join(folder, "prices.json")
            quote_folder = os.path.join(folder, "quotes")
            os.mkdir(quote_folder)
            with open(os.path.join(quote_folder, "yahoo-" + SYMBOL + ".json"), "w", encoding="utf-8") as fh:
                fh.write(quote_doc())
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = alerts.main(["add", "--rules", rules, "--symbol", "RELIANCE", "--target", "101"])
            self.assertEqual(code, 0, err.getvalue())
            with open(rules, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["rules"][0]["symbol"], SYMBOL)
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = alerts.main(["check", "--rules", rules, "--state", state, "--prices-out", prices,
                                    "--offline", quote_folder, "--now", DAY + " 10:15"])
            self.assertEqual(code, 0, err.getvalue())
            self.assertIn("ALERT", out.getvalue())
            with open(prices, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["prices"], {SYMBOL: 101.25})


if __name__ == "__main__":
    unittest.main()
