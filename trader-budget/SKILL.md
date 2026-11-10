---
name: trader-budget
description: >-
  NSE Budget Manager. Sizes local paper proposals for whole-share Indian cash
  equities in INR, using a plan's entry, stop and target plus account limits.
  Nothing is placed or sent to a broker. Use for NSE-only paper sizing,
  position limits, or after trader-exit creates a plan.
argument-hint: "[budget in INR]"
---

# trader-budget

This tool sizes one NSE cash-equity paper proposal or splits a budget across
weights. It only writes a local JSON proposal. It cannot connect to, route to,
or place an order with any broker or exchange. trader-risk checks the proposal;
trader-broker only keeps a local paper journal.

```bash
python3 "${CLAUDE_SKILL_DIR}/size.py" --write
python3 "${CLAUDE_SKILL_DIR}/size.py" --limit --write
python3 "${CLAUDE_SKILL_DIR}/size.py" --targets "${CLAUDE_SKILL_DIR}/targets.example.json" \
  --prices trader/prices.json --whole-shares
python3 "${CLAUDE_SKILL_DIR}/size.py" --now "2026-11-09 10:15" --json
```

Times without an offset are IST. NSE regular cash-market hours are 09:15–15:30
IST on trading days; the example avoids new entries after 15:15 and targets
being flat by 15:25. The risk tool uses the published NSE 2026 cash-market
calendar and any extra dates listed in `nse_holidays`. Calendars after 2026
are unknown in this package, so confirm the official NSE calendar yourself.

## Configuration and assumptions

Copy `config.example.json` to `trader/config.json`. Monetary values are INR:
`budget`, `max_order_inr`, `min_order_inr`, `max_loss_per_trade_inr`, and
`max_daily_loss_inr`. Example limits are ₹50,000 budget, ₹40,000 per order,
₹50 minimum order, ₹500 max risk per trade, and ₹1,500 daily risk. Adjust them
only to the user's stated paper-account limits.

NSE cash-equity assumptions: long-only, whole shares, regular-session DAY
orders, no options, margin, fractional quantity, or short selling. The config
must keep `broker` as `local-paper` and `paper` as `true`; other destinations
or live mode are rejected.

The plan-mode size is the smallest of max loss, position cap, max order, and
cash after the buffer. A fresh price above the planned entry increases the
measured risk. A zero-share result, invalid stop/target, below-minimum order,
or reward:risk below the configured floor produces no proposal.

## Example

Illustrative only: RELIANCE at ₹2,500, stop ₹2,440, target ₹2,560; ₹50,000
budget and ₹500 max loss. Risk is ₹60/share, so max loss allows 8 shares
(₹20,000), less than the other example limits. Prices and this plan are not
market data or a recommendation.

## Weights mode

`targets.example.json` contains illustrative NSE tickers and weights, not
current index weights or a recommendation. Whole-share proposals require
prices (`--prices`) and `--whole-shares`; fractionals/notional orders are not
supported for NSE cash-market proposals.

## Safety

- Education and tooling, not financial advice. A passed size is not a trade recommendation.
- Never infer a budget, price, stop, target, or user's risk tolerance.
- This tool never connects to or calls a broker or exchange.
- Keep all proposals paper-only; execution is not implemented.
- Any later order must pass `/trader-risk` and receive your explicit `yes`
  in `/trader-broker`; sizing a proposal is not approval.
