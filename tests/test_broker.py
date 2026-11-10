import contextlib
import io
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from _load import load, ROOT

ticket = load("trader-broker", "ticket")
check = load("trader-risk", "check")
CFG_PATH = os.path.join(ROOT, "trader-budget", "config.example.json")
TODAY = "2026-11-09"
NOW = "2026-11-09 10:15"
ORDER = {"symbol": "RELIANCE", "side": "buy", "qty": "8", "type": "market", "time_in_force": "day",
         "order_class": "bracket", "take_profit_limit_price": "2560.00", "stop_loss_stop_price": "2440.00",
         "plan": {"entry": 2500, "stop": 2440, "target": 2560, "max_loss_inr": 480}}


def cfg(**over):
    with open(CFG_PATH, encoding="utf-8") as fh:
        result = json.load(fh)
    result.update(over)
    return result


def now():
    return ticket.parse_now(NOW)


def risk_doc():
    return check.check([ORDER], cfg(), now=check.parse_now(NOW))


class LocalPaperJournal(unittest.TestCase):
    def test_explicit_yes_is_single_order_and_amount_specific(self):
        for reply in ("yes", "Yes.", "YES", "yes 8 RELIANCE", "yes 2440"):
            self.assertTrue(ticket.parse_yes(reply, ORDER)[0], reply)
        for reply in ("sure", "yes to all", "yes 9 RELIANCE", "yes but later", "yes?", "no"):
            self.assertFalse(ticket.parse_yes(reply, ORDER)[0], reply)

    def test_rupee_ticket_and_simulation_payload_are_local_only(self):
        paper_order = ticket.paper_order(ORDER)
        self.assertEqual(paper_order["qty"], "8")
        self.assertNotIn("plan", paper_order)
        self.assertNotIn("why", paper_order)
        self.assertIn("₹480", ticket.plain(ORDER))
        rendered, ready = ticket.render(ORDER, 1, 1, cfg(), risk_doc(), {"orders": []}, TODAY)
        self.assertTrue(ready)
        self.assertIn("LOCAL NSE PAPER SIMULATION", rendered)
        self.assertIn("no broker, network route, or live order", rendered)
        self.assertIn("Nothing is sent", rendered)
        self.assertNotIn("Alpaca", rendered)
        self.assertNotIn("IBKR", rendered)
        doc = ticket.ticket_json(ORDER, 1, cfg(), risk_doc(), {"orders": []}, TODAY)
        self.assertEqual(doc["destination"], "local-paper-journal")
        self.assertEqual(doc["simulation_order"], paper_order)
        self.assertNotIn("tool", doc)
        self.assertNotIn("broker", doc)

    def test_approval_only_records_local_consent(self):
        risk = risk_doc()
        documents = {
            "orders": {"orders": [ORDER]},
            "config": cfg(),
            "risk": risk,
            "state": {"orders": []},
        }
        written = []
        args = SimpleNamespace(orders="orders", config="config", risk="risk", state="state",
                               now=NOW, today=None, index=1, reply="yes 8 RELIANCE")
        read = lambda path, what, required=True: documents.get(path)
        output = io.StringIO()
        with patch.object(ticket, "read_json", side_effect=read), \
                patch.object(ticket, "write_json", side_effect=lambda path, value: written.append(value)), \
                contextlib.redirect_stdout(output):
            self.assertEqual(ticket.cmd_approve(args), 0)
        self.assertEqual(written[0]["orders"][0]["destination"], "local-paper-journal")
        self.assertEqual(written[0]["orders"][0]["status"], "approved")
        self.assertIn("No order was sent", output.getvalue())
        self.assertNotIn("place_stock_order", output.getvalue())

    def test_result_records_simulation_without_broker_identifier(self):
        risk = risk_doc()
        approved = {"fingerprint": ticket.fingerprint(ORDER), "date": TODAY, "status": "approved",
                    "symbol": "RELIANCE", "side": "buy", "plain": ticket.plain(ORDER),
                    "kind": "entry", "max_loss_inr": 480, "qty": "8"}
        documents = {"orders": {"orders": [ORDER]}, "config": cfg(), "risk": risk,
                     "state": {"orders": [approved]}}
        written = []
        args = SimpleNamespace(orders="orders", config="config", risk="risk", state="state",
                               now=NOW, today=None, index=1, status="simulated", filled_qty=None,
                               filled_price=None, note=None, portfolio="portfolio")
        read = lambda path, what, required=True: documents.get(path)
        with patch.object(ticket, "read_json", side_effect=read), \
                patch.object(ticket, "write_json", side_effect=lambda path, value: written.append(value)), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ticket.cmd_result(args), 0)
        self.assertEqual(written[0]["orders"][-1]["status"], "simulated")
        self.assertEqual(written[0]["orders"][-1]["max_loss_inr"], 480)
        self.assertNotIn("broker_order_id", written[0]["orders"][-1])

    def test_non_local_and_live_configurations_are_rejected(self):
        for overrides in ({"paper": False}, {"broker": "alpaca"}, {"broker": "ibkr"},
                          {"allow_margin": True}, {"allow_short": True}, {"fractional": True}):
            with self.subTest(overrides=overrides), \
                    patch.object(ticket, "read_json", return_value=cfg(**overrides)), \
                    self.assertRaises(ticket.TicketError):
                ticket.load_config("config")

    def test_desktop_example_does_not_configure_a_connector(self):
        path = os.path.join(ROOT, "trader-broker", "claude_desktop_config.example.json")
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {})


if __name__ == "__main__":
    unittest.main()
