# NSE Day Trader skill pack

11 Claude skills for researching and reviewing NSE-listed Indian equities:
scan daily charts, monitor company news, check entries and exits, replay past
setups, manage risk in INR, and keep a paper-trading journal.

The tools are plain Python and use free, unofficial Yahoo Finance chart data.
They do not place orders or promise trading results. The broker tool is a
local paper journal only; no Indian broker is connected.

## Install

In Claude Code:

```text
/plugin marketplace add Jakeschincariol/day-trader-skill
/plugin install day-trader-skill@day-trader-skill
```

For a local checkout:

```bash
git clone https://github.com/Jakeschincariol/day-trader-skill.git
cd day-trader-skill
python3 -m unittest discover -s tests -v
```

The market clock helper `trader_market.py` is shared by the standalone tools;
keep it at the repository root when running a script from its skill folder.
Python 3.8 or newer is required. No packages need installing.

## The skills

| command | purpose |
| --- | --- |
| `/trader-scanner` | Scan daily setups or intraday opening-range breakouts from an NSE watchlist. |
| `/trader-news` | Review Indian company news and market announcements. |
| `/trader-entry` | Check an entry against completed bars. |
| `/trader-exit` | Set a stop and target before a trade. |
| `/trader-timemachine` | Replay a planned trade against historical bars; simulation, not prediction. |
| `/trader-risk` | Check proposed trades against INR limits and account rules. |
| `/trader-budget` | Size paper positions within a budget and max loss. |
| `/trader-broker` | Review approvals, paper fills, and a local paper journal; no live broker integration. |
| `/trader-alerts` | Check prices, levels, and IST session times. |
| `/trader-analyst` | Refuses US SEC data for NSE tickers; direct official exchange filings are the fallback. |
| `/trader-pelosi` | US Congress tracker disabled; no verified Indian insider-disclosure replacement is wired. |

Tools share files under `trader/`. The suggested research flow is:

```text
scanner -> news -> entry -> exit -> timemachine -> budget -> risk -> paper journal
```

Each command is separate; running the scanner does not automatically invoke
the other skills.

## Run a Nifty 500 daily scan

The repository includes a plain-text sample constituent list at
`trader/nifty500.txt`. It is a point-in-time list; verify and update constituents
from an authoritative index source before relying on it.

```bash
python3 trader-scanner/scan.py daily \
  --market nse \
  --watchlist trader/nifty500.txt \
  --out trader/nifty500_watchlist.json
```

The scan checks up to three months of daily closes for a 20-day closing-high
breakout, bull flag, reclaim of the 20-day average, oversold RSI, or an
oversold bounce. Defaults require a price of at least ₹5 and volume of at
least 1,000,000 shares. It reports matches, not buy/sell recommendations.

For the intraday opening-range breakout scan, run during the NSE session after
the range has formed:

```bash
python3 trader-scanner/scan.py orb \
  --market nse \
  --watchlist trader/nifty500.txt \
  --at 10:15
```

The regular NSE cash-market session is 09:15-15:30 IST. `--now` accepts an
IST wall-clock time or a timestamp with `Z` for UTC. Daily scans can run when
the market is closed; they use the latest completed daily bars available from
Yahoo. Check the returned data date, since Yahoo can lag or provide irregular
timestamps.

The code currently includes the official NSE 2026 capital-market holiday list.
Holiday dates for later years are not yet embedded, so confirm the exchange
calendar before using time-window checks in another year.

## Safety and limitations

- **Not financial advice.** Day trading can result in losses.
- **No live order execution.** The broker tool only journals paper decisions
  and fills. No Alpaca, Interactive Brokers, or Indian broker API is wired.
- **Unofficial data.** Yahoo Finance can lag, rate-limit, or return incomplete
  data. Verify important quotes, dates, and exchange announcements with
  official NSE/BSE or broker sources.
- **No predictions.** Chart scans and historical replays do not tell you what
  a stock will do next.
- **Indian regulatory and tax treatment.** This software does not determine
  suitability, exchange rules, brokerage charges, STT, GST, stamp duty, or tax
  liability. Confirm those independently with a qualified professional.
- **Stop orders are not guaranteed fills.** Gaps or fast markets can fill past
  the intended stop.

MIT license.
