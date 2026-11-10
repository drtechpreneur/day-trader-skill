---
name: trader-news
description: >-
  NSE News Monitor. Checks NSE India equity corporate announcements for
  symbols in the watchlist, plan or portfolio. Use for questions about recent
  NSE-listed company announcements. This tool does not fetch US news, SEC
  filings or prices; only NSE symbols are supported.
argument-hint: "[NSE symbols]"
---

# trader-news

This tool checks official NSE India equity corporate announcements. The NSE
JSON endpoint was exercised successfully during this migration; access can
still vary by network, and NSE may change the endpoint. The tool does not
silently fall back to US feeds.

```bash
python3 "${CLAUDE_SKILL_DIR}/news.py"
python3 "${CLAUDE_SKILL_DIR}/news.py" --tickers RELIANCE INFY --hours 24
python3 "${CLAUDE_SKILL_DIR}/news.py" --tickers RELIANCE.NS INFY.NS
python3 "${CLAUDE_SKILL_DIR}/news.py" --tickers RELIANCE --json
```

## What it reads

- NSE equity announcements from
  `https://www.nseindia.com/api/corporate-announcements` with the symbol and
  requested date range as query parameters.
- NSE symbol lists from `trader/watchlist.json`, `trader/plan.json` and
  `trader/portfolio.json`, unless `--tickers` is supplied.
- Symbols may be bare NSE symbols or use the scanner's `.NS` suffix; the
  suffix is removed for the NSE API lookup.
- `trader/state/news.json` to avoid repeating the same announcement; state
  entries are retained for 30 days.

The announcement description, exchange-provided text, publication time and
attached filing link are shown when present. Times are displayed in IST. A
missing attachment or description is reported as missing; the tool does not
invent one. `--offline DIR` reads `nse-<SYMBOL>.json` files for fixture-based
testing. `--dry-run` does not update state.

## Limits

- This is an NSE announcements check, not a general news service, price feed,
  financial-statement parser, or BSE monitor. It does not claim that an empty
  response means there is no relevant news elsewhere.
- Corporate announcements are leads. Open the linked exchange filing and
  verify the details before relying on them.
- Network or exchange access errors are shown as notes; no alternate US feed
  is used.
- Never infer a buy/sell signal or predict a price move from an announcement.
- The monitor does not score the importance of a filing or judge its impact.
- Symbol matching is exact after normalization; similar company names are not
  treated as the same issuer.
- The saved state is only a local de-duplication cache, not a record of all
  filings published by the exchange.
- Use `--dry-run` when checking a new setup so that the local cache is not
  changed.
- A ticker with no returned items may reflect access limits, date-range
  differences, or a quiet issuer; it is not evidence that no filing exists.
- Exchange endpoints and response fields can change without notice. Review
  the linked filing and contact NSE documentation if responses stop matching.
- This tool does not trade, set alerts, or alter a plan.

Education and tooling, not financial advice. This skill only reads and reports.
Nothing places an order except `/trader-broker`, after `/trader-risk` passes
and the user explicitly approves the order.
