import datetime
import unittest

import trader_market


class NseMarket(unittest.TestCase):
    def test_ist_conversion(self):
        utc = datetime.datetime(2026, 11, 9, 3, 45)
        local = trader_market.to_ist(utc)
        self.assertEqual(local, datetime.datetime(2026, 11, 9, 9, 15))
        self.assertEqual(trader_market.ist_to_utc(local), utc)
        self.assertEqual(trader_market.timestamp_to_ist(1794195900), local)

    def test_session_and_holiday(self):
        self.assertEqual(trader_market.session(datetime.date(2026, 11, 9)),
                         (datetime.time(9, 15), datetime.time(15, 30)))
        self.assertIsNone(trader_market.session(datetime.date(2026, 11, 10)))
        self.assertEqual(trader_market.trading_day(datetime.date(2026, 11, 10)),
                         (False, "NSE holiday: Diwali-Balipratipada"))
        self.assertFalse(trader_market.calendar_known(datetime.date(2027, 1, 1)))

    def test_yahoo_nse_symbols(self):
        self.assertEqual(trader_market.yahoo_symbol("reliance"), "RELIANCE.NS")
        self.assertEqual(trader_market.yahoo_symbol("M&M.NS"), "M&M.NS")
        self.assertEqual(trader_market.yahoo_symbol_path("M&M"), "M%26M.NS")


if __name__ == "__main__":
    unittest.main()
