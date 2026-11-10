import datetime
import json
import os
import unittest

from _load import load, ROOT

check = load("trader-risk", "check")
ticket = load("trader-broker", "ticket")
CFG_PATH = os.path.join(ROOT, "trader-budget", "config.example.json")
TODAY = "2026-11-09"
NOW = "2026-11-09 10:15"
ORDER = {"symbol": "RELIANCE", "side": "buy", "qty": "8", "type": "market", "time_in_force": "day",
         "order_class": "bracket", "take_profit_limit_price": "2560.00", "stop_loss_stop_price": "2440.00",
         "plan": {"entry": 2500, "stop": 2440, "target": 2560}}


def cfg(**over):
    with open(CFG_PATH, encoding="utf-8") as fh:
        result = json.load(fh)
    result.update(over)
    return result


def at(text):
    return check.parse_now(text)


def reasons(result):
    return " | ".join(result["results"][0]["reasons"])


class NSERisk(unittest.TestCase):
    def test_ist_conversion_and_pass(self):
        now = at(NOW)
        self.assertEqual(now, datetime.datetime(2026, 11, 9, 4, 45))
        self.assertEqual(check.to_ist(now).strftime("%Y-%m-%d %H:%M"), NOW)
        result = check.check([ORDER], cfg(), now=now)
        row = result["results"][0]
        self.assertEqual((row["verdict"], row["max_loss_inr"], row["value_inr"]), ("PASS", 480, 20000))
        self.assertEqual(result["now_ist"], NOW)
        self.assertTrue(result["paper"])
        self.assertEqual(result["warnings"], [])
        self.assertIn("₹480", check.report(result))
        self.assertIn("local paper", check.report(result))

    def test_trade_loss_and_daily_loss_are_inr_limits(self):
        too_many = check.check([dict(ORDER, qty="9")], cfg(), now=at(NOW))
        self.assertEqual(too_many["results"][0]["verdict"], "BLOCK")
        self.assertIn("₹540", reasons(too_many))
        daily = check.check([ORDER], cfg(max_daily_loss_inr=400), now=at(NOW))
        self.assertIn("daily loss", reasons(daily))
        self.assertIn("₹400", reasons(daily))

    def test_ist_entry_window_and_nse_calendar(self):
        cases = [
            ("2026-11-09 09:29", "no new entries before 09:30 IST"),
            ("2026-11-09 15:16", "no new entries after 15:15 IST"),
            ("2026-11-09 09:14", "NSE regular cash session is closed"),
            ("2026-11-09 15:30", "NSE regular cash session is closed"),
            ("2026-11-08 10:15", "weekend"),
        ]
        for now, expected in cases:
            with self.subTest(now=now):
                result = check.check([ORDER], cfg(), now=at(now))
                self.assertIn(expected, reasons(result))
        built_in_holiday = check.check([ORDER], cfg(), now=at("2026-11-10 10:15"))
        self.assertIn("Diwali-Balipratipada", reasons(built_in_holiday))
        unknown_calendar = check.check([ORDER], cfg(), now=at("2027-01-04 10:15"))
        self.assertTrue(any("calendar for 2027 is unknown" in warning
                            for warning in unknown_calendar["warnings"]))
        holiday = check.check([ORDER], cfg(nse_holidays=[TODAY]), now=at(NOW))
        self.assertIn("NSE holiday", reasons(holiday))
        with self.assertRaises(check.RiskError):
            check.check([ORDER], cfg(nse_holidays=["not-a-date"]), now=at(NOW))

    def test_fresh_higher_price_increases_the_risk(self):
        now = at(NOW)
        quote_time = at("2026-11-09 10:10")
        result = check.check([ORDER], cfg(), prices={"RELIANCE": 2520}, now=now,
                             price_times={"RELIANCE": quote_time})
        self.assertIn("₹640", reasons(result))

    def test_nse_cash_market_rejects_notional_fractional_and_non_day_orders(self):
        cases = [
            ({"symbol": "RELIANCE", "side": "buy", "notional": "1000", "type": "market",
              "time_in_force": "day"}, "notional orders are unsupported"),
            (dict(ORDER, qty="1.5"), "whole number of shares"),
            (dict(ORDER, time_in_force="gtc"), "supports day orders only"),
        ]
        for order, expected in cases:
            with self.subTest(order=order):
                result = check.check([order], cfg(), now=at(NOW))
                self.assertEqual(result["results"][0]["verdict"], "BLOCK")
                self.assertIn(expected, " ".join(result["results"][0]["reasons"]))

    def test_live_and_non_cash_configurations_are_rejected(self):
        for overrides in ({"paper": False}, {"broker": "alpaca"}, {"broker": "ibkr"},
                          {"allow_options": True}, {"allow_margin": True}, {"allow_short": True}):
            with self.subTest(overrides=overrides), self.assertRaises(check.RiskError):
                check.check([ORDER], cfg(**overrides), now=at(NOW))

    def test_exact_fingerprint_matches_the_journal(self):
        self.assertEqual(check.fingerprint(ORDER), ticket.fingerprint(ORDER))
        self.assertEqual(check.ORDER_FIELDS, ticket.ORDER_FIELDS)
        self.assertNotEqual(check.fingerprint(ORDER), check.fingerprint(dict(ORDER, qty="9")))

    def test_simulated_fill_is_not_double_counted_in_daily_limits(self):
        state = {"orders": [
            {"status": "simulated", "date": TODAY, "symbol": "RELIANCE", "side": "buy",
             "kind": "entry", "max_loss_inr": 480},
            {"status": "filled", "date": TODAY, "symbol": "RELIANCE", "side": "buy"},
        ]}
        result = check.check([dict(ORDER, symbol="TCS")], cfg(), state=state, now=at(NOW))
        self.assertEqual(result["today"]["orders_simulated"], 1)
        self.assertEqual(result["today"]["entries_simulated"], 1)
        self.assertEqual(result["today"]["loss_at_risk_inr"], 480)

    def test_exit_is_not_blocked_by_entry_cutoff_or_limits(self):
        sell = {"symbol": "RELIANCE", "side": "sell", "qty": "8", "type": "market", "time_in_force": "day"}
        result = check.check([sell], cfg(max_order_inr=1, max_trades_per_day=0),
                             portfolio={"cash": 0, "positions": [{"ticker": "RELIANCE", "shares": 8}]},
                             prices={"RELIANCE": 2500}, now=at("2026-11-09 15:20"))
        self.assertEqual(result["results"][0]["verdict"], "PASS")
        self.assertEqual(result["results"][0]["kind"], "exit")


if __name__ == "__main__":
    unittest.main()
