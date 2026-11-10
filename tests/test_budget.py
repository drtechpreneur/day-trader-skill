import json
import os
import unittest

from _load import load, ROOT

size = load("trader-budget", "size")
CFG_PATH = os.path.join(ROOT, "trader-budget", "config.example.json")
TARGETS_PATH = os.path.join(ROOT, "trader-budget", "targets.example.json")
TODAY = "2026-11-09"
PLAN = {"symbol": "RELIANCE", "side": "buy", "date": TODAY, "entry": 2500.0, "stop": 2440.0,
        "target": 2560.0, "setup": "orb", "entry_time": "10:15"}


def cfg(**over):
    with open(CFG_PATH, encoding="utf-8") as fh:
        result = json.load(fh)
    result.update(over)
    return result


class NSEBudget(unittest.TestCase):
    def test_example_config_is_inr_ist_and_local_paper_only(self):
        c = cfg()
        self.assertEqual((c["broker"], c["paper"]), ("local-paper", True))
        self.assertEqual((c["max_order_inr"], c["min_order_inr"],
                          c["max_loss_per_trade_inr"], c["max_daily_loss_inr"]),
                         (40000, 50, 500, 1500))
        self.assertEqual((c["no_entries_before"], c["no_entries_after"], c["flat_by"]),
                         ("09:30", "15:15", "15:25"))
        self.assertEqual(c["nse_holidays"], [])
        self.assertNotIn("pdt_guard", c)
        with open(TARGETS_PATH, encoding="utf-8") as fh:
            targets = json.load(fh)
        self.assertEqual({r["ticker"] for r in targets["weights"]}, {"RELIANCE", "HDFCBANK", "INFY"})
        self.assertIn("Illustrative", targets["source"])

    def test_plan_is_sized_to_inr_max_loss_and_makes_local_proposal(self):
        result = size.size_trade(PLAN, cfg(), today=TODAY)
        self.assertEqual((result["qty"], result["bound_by"]), (8, "max loss"))
        self.assertEqual((result["cost_inr"], result["max_loss_inr"]), (20000, 480))
        self.assertEqual(result["max_loss_per_trade_inr"], 500)
        self.assertEqual(result["limits"][0]["inr"], 500)
        order = size.bracket_order(result)
        self.assertEqual((order["symbol"], order["qty"], order["type"]), ("RELIANCE", "8", "market"))
        self.assertEqual(order["plan"]["max_loss_inr"], 480)
        self.assertEqual(order["stop_loss_stop_price"], "2440.00")
        self.assertIn("₹500", order["why"])
        self.assertIn("₹480", order["why"])
        self.assertIn("₹20,000", size.plan_report(result, order))

    def test_no_proposal_for_invalid_day_or_too_wide_stop(self):
        with self.assertRaises(size.SizeError):
            size.size_trade(dict(PLAN, date="2026-11-06"), cfg(), today=TODAY)
        refused = size.size_trade(dict(PLAN, stop=1800), cfg(), today=TODAY)
        self.assertEqual(refused["qty"], 0)
        self.assertIsNone(size.bracket_order(refused))
        self.assertIn("₹500 max loss", refused["refusal"])

    def test_live_and_non_cash_modes_are_rejected(self):
        for overrides in ({"paper": False}, {"broker": "alpaca"}, {"broker": "ibkr"},
                          {"fractional": True}, {"allow_margin": True}, {"allow_short": True},
                          {"allow_options": True}):
            with self.subTest(overrides=overrides), self.assertRaises(size.SizeError):
                size.size_trade(PLAN, cfg(**overrides), today=TODAY)

    def test_weights_create_whole_share_orders_inr_only(self):
        with open(TARGETS_PATH, encoding="utf-8") as fh:
            targets = json.load(fh)
        prices = {"RELIANCE": 2500, "HDFCBANK": 1700, "INFY": 1500}
        result = size.size(size.parse_weights(targets), cfg(), prices=prices)
        self.assertTrue(result["whole_shares"])
        self.assertEqual(result["invested_inr"] + result["idle_inr"], result["investable_inr"])
        self.assertTrue(all("amount_inr" in p and "dollars" not in p for p in result["positions"]))
        orders = size.orders_from(result, targets["source"])
        self.assertTrue(orders)
        self.assertTrue(all("qty" in o and "notional" not in o for o in orders))
        self.assertIn("local simulation only", size.report(result, orders))

    def test_money_uses_rupee_labels(self):
        self.assertEqual(size.money(1234.5), "₹1,234.50")
        self.assertEqual(size.money(500), "₹500")


if __name__ == "__main__":
    unittest.main()
