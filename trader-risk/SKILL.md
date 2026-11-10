---
name: trader-risk
description: >-
  NSE paper Risk Manager. Checks whole-share Indian cash-equity proposals
  against INR loss, cash, position, duplicate, and IST session rules. Rejects
  live broker configuration and never routes an order. Use before any
  trader-broker local simulation.
argument-hint: "[path to orders.json]"
---

# trader-risk

The risk gate checks each proposal against `trader/config.json`, the local
portfolio, prices, and the local paper journal. PASS is not a recommendation
or an exchange order; trader-broker remains local-only.

```bash
python3 "${CLAUDE_SKILL_DIR}/check.py"
python3 "${CLAUDE_SKILL_DIR}/check.py" --no-write
python3 "${CLAUDE_SKILL_DIR}/check.py" --now "2026-11-09 10:15"
```

Times without offsets are interpreted as IST. NSE regular cash session is
09:15–15:30 IST. The default entry window is 09:30–15:15; weekends and the
published NSE 2026 cash-market holidays are blocked. Additional dates can be
configured in `nse_holidays`. Calendars after 2026 are unknown, so verify them
before using paper checks. Regular-session logic does not model special
sessions.

## Checks

- Whole-share quantities only; notional/fractional orders and non-DAY time-in-force are blocked.
- Options, margin, and short sales are disallowed; sells must close holdings.
- Enforces the blocked list, INR min/max order, position cap, cash buffer,
  required stop, max loss per trade, minimum reward:risk, daily loss, trades
  per day, entry window, duplicates, and daily order count.
- Exits that reduce an existing position are not blocked by entry-only limits.
- Market-order risk uses the higher of the plan entry and a fresh price;
  limit orders use their limit price.
- `broker` must be `local-paper` and `paper` must be `true`. Live mode and all
  external broker configurations are rejected. There is no PDT guard: it is
  a US-specific concept and no India-specific replacement is asserted here.

Amounts in config and output are INR (₹). Budgets and portfolio cash values
must use INR as well. Proposals are checked in file order as if each PASS had
filled, so combined orders cannot evade limits.

## Workflow

1. Refresh prices when the plan may be stale.
2. Run `check.py`; BLOCK means do not pass the proposal to the journal.
3. Explain the INR risk, reward:risk, used daily limits, and any warnings.
4. If an order changes, rerun the check. trader-broker only shows a proposal
   as ready when its exact fingerprint passed today.
5. A pass is not approval: the user must explicitly say yes to one proposal
   in trader-broker before recording a local simulation.

Education and tooling, not financial advice.
