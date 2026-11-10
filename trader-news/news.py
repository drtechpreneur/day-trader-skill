#!/usr/bin/env python3
"""NSE corporate-announcement monitor for trader-news. Standard library only.

    python3 news.py --tickers RELIANCE INFY
    python3 news.py --tickers RELIANCE --hours 24 --json

Reads NSE India equity corporate announcements. This tool does not read US
headlines, SEC filings, or prices. Offline: --offline DIR reads nse-<SYMBOL>.json.
"""

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

NSE_URL = "https://www.nseindia.com/api/corporate-announcements"
NSE_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
NSE_TZ = _dt.timezone(_dt.timedelta(hours=5, minutes=30))
KEEP_DAYS = 30


class NewsError(Exception):
    pass


def nse_symbol(symbol):
    """Convert the scanner's Yahoo-style NSE suffix to the exchange symbol."""
    symbol = symbol.upper()
    return symbol[:-3] if symbol.endswith(".NS") else symbol


def parse_time(value):
    """Parse NSE's displayed date or an ISO timestamp."""
    if not value:
        return None
    try:
        return _dt.datetime.strptime(value, "%d-%b-%Y %H:%M:%S").replace(tzinfo=NSE_TZ)
    except (TypeError, ValueError):
        pass
    try:
        parsed = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=NSE_TZ) if parsed.tzinfo is None else parsed
    except (TypeError, ValueError):
        return None


def load_json(path):
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def watch_from_files(portfolio="trader/portfolio.json", watchlist="trader/watchlist.json",
                     plan="trader/plan.json"):
    """{symbol: name or None}: NSE symbols from the watchlist, plan and holdings."""
    out = {}
    wl = load_json(watchlist) or {}
    for hit in wl.get("hits", []):
        symbol = hit.get("symbol") or hit.get("ticker")
        if symbol:
            out[symbol.upper()] = hit.get("name")
    planned = load_json(plan) or {}
    if planned.get("symbol"):
        out.setdefault(planned["symbol"].upper(), planned.get("name"))
    portfolio_data = load_json(portfolio) or {}
    for position in portfolio_data.get("positions", []):
        symbol = position.get("ticker") or position.get("symbol")
        if symbol:
            out[symbol.upper()] = position.get("name") or out.get(symbol.upper())
    return out


class Fetcher:
    def __init__(self, offline=None, pause=0.2):
        self.offline = offline
        self.pause = pause
        self._last = 0.0

    def get(self, symbol, from_date, to_date):
        exchange_symbol = nse_symbol(symbol)
        filename = "nse-%s.json" % exchange_symbol
        if self.offline:
            path = os.path.join(self.offline, filename)
            if not os.path.isfile(path):
                raise NewsError("offline: no file %s" % path)
            with open(path, "rb") as fh:
                return fh.read()
        gap = time.time() - self._last
        if gap < self.pause:
            time.sleep(self.pause - gap)
        self._last = time.time()
        query = urllib.parse.urlencode({
            "index": "equities",
            "symbol": exchange_symbol,
            "from_date": from_date.strftime("%d-%m-%Y"),
            "to_date": to_date.strftime("%d-%m-%Y"),
        })
        url = "%s?%s" % (NSE_URL, query)
        headers = {"User-Agent": NSE_UA, "Accept": "application/json, text/plain, */*",
                   "Referer": "https://www.nseindia.com/", "Accept-Encoding": "gzip"}
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    data = gzip.decompress(data)
                return data
        except urllib.error.HTTPError as exc:
            raise NewsError("NSE HTTP %s for %s" % (exc.code, exchange_symbol))
        except urllib.error.URLError as exc:
            raise NewsError("could not reach NSE for %s: %s" % (exchange_symbol, exc.reason))


def parse_announcements(data, symbol):
    """Parse NSE's corporate-announcements JSON response for one NSE symbol."""
    try:
        rows = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
    except (ValueError, UnicodeError, TypeError) as exc:
        raise NewsError("NSE announcements for %s are not valid JSON: %s" % (symbol, exc))
    if not isinstance(rows, list):
        raise NewsError("NSE announcements for %s have an unexpected format" % symbol)
    out = []
    for row in rows:
        if not isinstance(row, dict) or str(row.get("symbol", "")).upper() != nse_symbol(symbol):
            continue
        seq = str(row.get("seq_id") or "")
        title = str(row.get("desc") or "Corporate announcement").strip()
        summary = str(row.get("attchmntText") or "").strip()
        link = str(row.get("attchmntFile") or "").strip()
        published = str(row.get("an_dt") or row.get("exchdisstime") or "").strip()
        out.append({
            "id": "nse:%s" % (seq or hashlib.sha1(
                (symbol + published + title + link).encode("utf-8")).hexdigest()),
            "source": "NSE India",
            "kind": "corporate announcement",
            "ticker": symbol.upper(),
            "company": str(row.get("sm_name") or "").strip(),
            "title": title,
            "summary": summary,
            "link": link,
            "time": parse_time(published),
        })
    return out


def collect(fetcher, watch, from_date, to_date, errors=None):
    errors = [] if errors is None else errors
    items = []
    for symbol in sorted(watch):
        try:
            items.extend(parse_announcements(fetcher.get(symbol, from_date, to_date), symbol))
        except NewsError as exc:
            errors.append("announcements for %s: %s" % (symbol, exc))
    return items


def fingerprint(item):
    return hashlib.sha1(item["id"].encode("utf-8")).hexdigest()[:16]


def select(items, state, now, hours=48, show_all=False):
    """Items in the time window, only unseen unless requested."""
    seen = state.setdefault("seen", {})
    cutoff = now - _dt.timedelta(hours=hours)
    ahead = now + _dt.timedelta(minutes=10)
    out = []
    for item in items:
        if item["time"] is not None:
            stamp = item["time"].astimezone(_dt.timezone.utc)
            if stamp < cutoff or stamp > ahead:
                continue
        fp = fingerprint(item)
        item["new"] = fp not in seen
        if item["new"] or show_all:
            out.append(item)
    out.sort(key=lambda item: (item["time"] or now), reverse=True)
    return out


def remember(items, state, now):
    seen = state.setdefault("seen", {})
    stamp = now.isoformat()
    for item in items:
        seen.setdefault(fingerprint(item), stamp)
    cutoff = (now - _dt.timedelta(days=KEEP_DAYS)).isoformat()
    state["seen"] = {key: value for key, value in seen.items() if value >= cutoff}
    state["last_check"] = stamp


def _json_ready(items):
    return [dict(item, time=item["time"].isoformat() if item["time"] else None)
            for item in items]


def render(items, errors, now):
    lines = []
    if not items:
        lines.append("No new NSE corporate announcements.")
    for item in items:
        when = item["time"].strftime("%Y-%m-%d %H:%M IST") if item["time"] else "time unknown"
        name = " (%s)" % item["company"] if item["company"] else ""
        lines.append("  %s  %s%s  %s" % (when, item["ticker"], name, item["title"]))
        if item["summary"]:
            lines.append("      %s" % item["summary"])
        if item["link"]:
            lines.append("      %s" % item["link"])
    for error in errors:
        lines.append("note: %s" % error)
    lines.append("Source: NSE India corporate announcements. No US filings, headlines or price data.")
    lines.append("Checked %s. Verify the linked exchange filing; not financial advice." %
                 now.astimezone(NSE_TZ).strftime("%Y-%m-%d %H:%M IST"))
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tickers", nargs="*",
                    help="NSE equity symbols (optionally with .NS); default: watchlist + plan + portfolio")
    ap.add_argument("--portfolio", default="trader/portfolio.json")
    ap.add_argument("--watchlist", default="trader/watchlist.json")
    ap.add_argument("--plan", default="trader/plan.json")
    ap.add_argument("--state", default="trader/state/news.json")
    ap.add_argument("--hours", type=float, default=48, help="ignore announcements older than this")
    ap.add_argument("--all", action="store_true", help="show seen announcements too")
    ap.add_argument("--offline", metavar="DIR", help="read nse-<SYMBOL>.json files from DIR")
    ap.add_argument("--now", help="ISO timestamp, for reproducible runs")
    ap.add_argument("--dry-run", action="store_true", help="do not update the state file")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.tickers:
        watch = {symbol.upper(): None for symbol in args.tickers}
        known = watch_from_files(args.portfolio, args.watchlist, args.plan)
        watch.update({symbol: known[symbol] for symbol in watch if known.get(symbol)})
    else:
        watch = watch_from_files(args.portfolio, args.watchlist, args.plan)
    if not watch:
        print("news: no NSE symbols. Pass --tickers or provide an NSE-symbol watchlist.",
              file=sys.stderr)
        return 2
    if args.hours <= 0:
        print("news: --hours must be greater than zero", file=sys.stderr)
        return 2
    now = parse_time(args.now) if args.now else _dt.datetime.now(_dt.timezone.utc)
    if now is None:
        print("news: --now must be an ISO timestamp", file=sys.stderr)
        return 2
    state = load_json(args.state) or {}
    errors = []
    now_ist = now.astimezone(NSE_TZ)
    start_ist = now_ist - _dt.timedelta(hours=args.hours)
    items = collect(Fetcher(offline=args.offline), watch, start_ist.date(), now_ist.date(), errors)
    shown = select(items, state, now.astimezone(_dt.timezone.utc), args.hours, args.all)
    if args.json:
        print(json.dumps({"checked": now.isoformat(), "items": _json_ready(shown),
                          "notes": errors}, indent=2))
    else:
        sys.stdout.write(render(shown, errors, now))
    if not args.dry_run:
        remember(items, state, now.astimezone(_dt.timezone.utc))
        folder = os.path.dirname(args.state)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(args.state, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
            fh.write("\n")
    return 0 if any(item["new"] for item in shown) else 1


if __name__ == "__main__":
    sys.exit(main())
