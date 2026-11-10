"""NSE cash-market clock and symbol helpers shared by the trading tools."""

import datetime
import urllib.parse

IST_OFFSET = datetime.timedelta(hours=5, minutes=30)
MARKET_OPEN = datetime.time(9, 15)
MARKET_CLOSE = datetime.time(15, 30)

# NSE capital-market holidays published at nseindia.com/api/holiday-master?type=trading.
NSE_HOLIDAYS = {
    "2026-01-15": "Municipal Corporation Election - Maharashtra",
    "2026-01-26": "Republic Day",
    "2026-03-03": "Holi",
    "2026-03-26": "Shri Ram Navami",
    "2026-03-31": "Shri Mahavir Jayanti",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-28": "Bakri Id",
    "2026-06-26": "Muharram",
    "2026-09-14": "Ganesh Chaturthi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-10": "Diwali-Balipratipada",
    "2026-11-24": "Prakash Gurpurb Sri Guru Nanak Dev",
    "2026-12-25": "Christmas",
}


def to_ist(utc):
    """Convert naive UTC datetime to naive IST."""
    return utc.replace(tzinfo=None) + IST_OFFSET


def ist_to_utc(local):
    """Convert naive IST datetime to naive UTC."""
    return local - IST_OFFSET


def timestamp_to_ist(timestamp):
    return to_ist(datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=int(timestamp)))


def yahoo_symbol(symbol):
    """Canonical Yahoo symbol for an NSE cash-market ticker."""
    value = str(symbol or "").strip().upper().replace(" ", "")
    if not value:
        return value
    if not value.endswith(".NS"):
        value += ".NS"
    return value


def yahoo_symbol_path(symbol):
    return urllib.parse.quote(yahoo_symbol(symbol), safe=".-")


def trading_day(day):
    """Return (is_open, reason). The published 2026 holiday list is known."""
    if day.weekday() >= 5:
        return False, "weekend"
    holiday = NSE_HOLIDAYS.get(day.isoformat())
    if holiday:
        return False, "NSE holiday: " + holiday
    return True, ""


def calendar_known(day):
    return day.year == 2026


def session(day):
    ok, _ = trading_day(day)
    return (MARKET_OPEN, MARKET_CLOSE) if ok else None


def next_open(day):
    candidate = day + datetime.timedelta(days=1)
    for _ in range(15):
        if trading_day(candidate)[0]:
            return "%s 09:15" % candidate.isoformat()
        candidate += datetime.timedelta(days=1)
    return None


def in_session(local):
    hours = session(local.date())
    return bool(hours and hours[0] <= local.time() < hours[1])
